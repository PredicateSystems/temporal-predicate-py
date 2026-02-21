"""
Basic example demonstrating Predicate Temporal interceptor.

This example shows:
1. Setting up a Temporal worker with Predicate authorization
2. Defining activities that will be secured
3. Running a workflow that executes those activities

Prerequisites:
- Temporal server running locally (temporal server start-dev)
- Predicate Authority daemon running (./predicate-authorityd --port 8787 --policy-file policy.json)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

from predicate_authority import AuthorityClient
from predicate_temporal import PredicateInterceptor


# ============================================================================
# Activities - These will be secured by Predicate Authority
# ============================================================================


@activity.defn
async def greet(name: str) -> str:
    """Simple greeting activity - allowed by policy."""
    return f"Hello, {name}!"


@activity.defn
async def fetch_data(data_id: str) -> dict:
    """Fetch data activity - allowed by policy."""
    # Simulate fetching data from a database
    return {"id": data_id, "value": "sample_data", "status": "active"}


@activity.defn
async def process_data(data: dict) -> dict:
    """Process data activity - allowed by policy."""
    # Simulate processing
    return {**data, "processed": True, "processed_by": "temporal-worker"}


@activity.defn
async def delete_all_records() -> str:
    """
    Dangerous activity - DENIED by policy.

    This activity matches the "deny-dangerous-operations" rule
    and will be blocked before execution.
    """
    # This code will NEVER run due to Predicate authorization
    return "All records deleted!"


# ============================================================================
# Workflow
# ============================================================================


@dataclass
class WorkflowInput:
    name: str
    data_id: str


@dataclass
class WorkflowResult:
    greeting: str
    processed_data: dict


@workflow.defn
class BasicWorkflow:
    """Basic workflow demonstrating secured activities."""

    @workflow.run
    async def run(self, input: WorkflowInput) -> WorkflowResult:
        # This activity will be allowed
        greeting = await workflow.execute_activity(
            greet,
            input.name,
            start_to_close_timeout=timedelta(seconds=10),
        )

        # This activity will be allowed
        data = await workflow.execute_activity(
            fetch_data,
            input.data_id,
            start_to_close_timeout=timedelta(seconds=10),
        )

        # This activity will be allowed
        processed = await workflow.execute_activity(
            process_data,
            data,
            start_to_close_timeout=timedelta(seconds=10),
        )

        return WorkflowResult(greeting=greeting, processed_data=processed)


@workflow.defn
class DangerousWorkflow:
    """Workflow that attempts a dangerous operation - will be blocked."""

    @workflow.run
    async def run(self) -> str:
        # This will raise PermissionError due to Predicate denial
        return await workflow.execute_activity(
            delete_all_records,
            start_to_close_timeout=timedelta(seconds=10),
        )


# ============================================================================
# Main
# ============================================================================


async def main():
    """Run the example worker and execute workflows."""

    # Connect to Temporal
    client = await Client.connect("localhost:7233")

    # Initialize Predicate Authority client
    # This connects to the predicate-authorityd daemon
    authority_ctx = AuthorityClient.from_policy_file(
        policy_file="policy.json",
        secret_key="demo-secret-key-for-signing",
        ttl_seconds=300,
    )

    # Create the Predicate interceptor
    interceptor = PredicateInterceptor(
        authority_client=authority_ctx.client,
        principal="temporal-worker",
    )

    # Create worker with the interceptor
    worker = Worker(
        client,
        task_queue="predicate-demo-queue",
        workflows=[BasicWorkflow, DangerousWorkflow],
        activities=[greet, fetch_data, process_data, delete_all_records],
        interceptors=[interceptor],
    )

    print("Starting worker with Predicate authorization...")
    print("=" * 60)

    # Run worker in background
    async with worker:
        # Execute the basic workflow - should succeed
        print("\n[1] Running BasicWorkflow (should succeed)...")
        try:
            result = await client.execute_workflow(
                BasicWorkflow.run,
                WorkflowInput(name="Alice", data_id="data-123"),
                id="basic-workflow-1",
                task_queue="predicate-demo-queue",
            )
            print(f"    Greeting: {result.greeting}")
            print(f"    Processed data: {result.processed_data}")
            print("    Status: SUCCESS")
        except Exception as e:
            print(f"    Status: FAILED - {e}")

        # Execute the dangerous workflow - should be blocked
        print("\n[2] Running DangerousWorkflow (should be blocked)...")
        try:
            result = await client.execute_workflow(
                DangerousWorkflow.run,
                id="dangerous-workflow-1",
                task_queue="predicate-demo-queue",
            )
            print(f"    Result: {result}")
            print("    Status: SUCCESS (unexpected!)")
        except Exception as e:
            print(f"    Status: BLOCKED by Predicate Authority")
            print(f"    Error: {type(e).__name__}: {e}")

        print("\n" + "=" * 60)
        print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())
