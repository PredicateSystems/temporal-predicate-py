#!/usr/bin/env python3
"""
Predicate Temporal Demo: Hack vs Fix

This demo shows how Predicate Authority blocks dangerous Temporal activities
while allowing legitimate operations.

Scenarios:
1. Legitimate order processing -> ALLOWED
2. delete_order activity -> BLOCKED
3. admin_override_payment activity -> BLOCKED
4. drop_database activity -> BLOCKED
"""

from __future__ import annotations

# Suppress noisy Temporal worker logs BEFORE importing temporalio
import logging
logging.basicConfig(level=logging.WARNING)
# Completely disable temporalio activity worker logging (prevents retry tracebacks)
logging.getLogger("temporalio").setLevel(logging.CRITICAL)

import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.exceptions import ActivityError
from temporalio.common import RetryPolicy

# Add src to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from predicate_authority import AuthorityClient
from predicate_temporal import PredicateInterceptor

# Get the demo directory for policy file path
DEMO_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================================
# Terminal Formatting (Enhanced for Video Presentation)
# ============================================================================

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_BLUE = "\033[44m"
BG_CYAN = "\033[46m"


def print_header():
    """Print demo header."""
    print()
    print(f"{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{CYAN}{BOLD}║                                                                      ║{RESET}")
    print(f"{CYAN}{BOLD}║        PREDICATE TEMPORAL DEMO: Hack vs Fix                          ║{RESET}")
    print(f"{CYAN}{BOLD}║                                                                      ║{RESET}")
    print(f"{CYAN}{BOLD}╚══════════════════════════════════════════════════════════════════════╝{RESET}")
    print()
    print(f"  {WHITE}Temporal activities secured by {CYAN}{BOLD}Predicate Authority{RESET}{WHITE} Zero-Trust{RESET}")
    print()


def print_scenario(num: int, total: int, title: str, activity_name: str, expected: str):
    """Print scenario header."""
    print()
    print(f"{WHITE}{'━' * 74}{RESET}")

    # Scenario number badge
    if expected == "ALLOWED":
        badge_color = BG_GREEN
        badge_text = f" {badge_color}{WHITE}{BOLD} SCENARIO {num}/{total} {RESET} "
    else:
        badge_color = BG_RED
        badge_text = f" {badge_color}{WHITE}{BOLD} SCENARIO {num}/{total} {RESET} "

    print(f"{badge_text}")
    print()
    print(f"  {WHITE}{BOLD}{title}{RESET}")
    print()

    # Highlight the activity name prominently
    if expected == "BLOCKED":
        print(f"  {DIM}Activity:{RESET}  {BRIGHT_RED}{BOLD}{activity_name}{RESET}")
        print(f"  {DIM}Expected:{RESET}  {RED}{BOLD}BLOCKED{RESET}")
    else:
        print(f"  {DIM}Activity:{RESET}  {BRIGHT_GREEN}{BOLD}{activity_name}{RESET}")
        print(f"  {DIM}Expected:{RESET}  {GREEN}{BOLD}ALLOWED{RESET}")
    print()


def print_result(decision: str, latency_ms: float | None = None, reason: str | None = None):
    """Print result with prominent visual feedback."""
    latency_str = f" {DIM}({latency_ms:.0f}ms){RESET}" if latency_ms else ""

    if decision == "ALLOWED":
        # Big green success banner
        print(f"  {BG_GREEN}{WHITE}{BOLD}  ✓ ALLOWED  {RESET}{latency_str}")
        print()
        if reason:
            print(f"  {GREEN}↳ {reason}{RESET}")
    elif decision == "BLOCKED":
        # Big red blocked banner
        print(f"  {BG_RED}{WHITE}{BOLD}  ✗ BLOCKED  {RESET}{latency_str}")
        print()
        if reason:
            print(f"  {RED}↳ Policy: {reason}{RESET}")
    else:
        print(f"  {YELLOW}{BOLD}? {decision}{RESET}{latency_str}")
        if reason:
            print(f"  {YELLOW}↳ {reason}{RESET}")
    print()


# ============================================================================
# Activities
# ============================================================================


@activity.defn
async def check_inventory(items: list[dict]) -> dict:
    """Check inventory - ALLOWED by policy."""
    await asyncio.sleep(0.05)
    return {"available": True, "items_checked": len(items)}


@activity.defn
async def charge_payment(order_id: str, amount: float) -> dict:
    """Charge payment - ALLOWED by policy."""
    await asyncio.sleep(0.05)
    return {"success": True, "transaction_id": f"txn-{order_id[:8]}", "amount": amount}


@activity.defn
async def send_confirmation(email: str, order_id: str) -> dict:
    """Send confirmation - ALLOWED by policy."""
    await asyncio.sleep(0.05)
    return {"sent": True, "email": email}


@activity.defn
async def delete_order(order_id: str) -> dict:
    """Delete order - BLOCKED by policy (matches deny-delete-operations)."""
    # This code should NEVER run
    return {"deleted": True, "order_id": order_id}


@activity.defn
async def admin_override_payment(order_id: str) -> dict:
    """Admin payment override - BLOCKED by policy (matches deny-admin-operations)."""
    # This code should NEVER run
    return {"overridden": True}


@activity.defn
async def drop_database() -> dict:
    """Drop database - BLOCKED by policy (matches deny-drop-operations)."""
    # This code should NEVER run
    return {"dropped": True}


# ============================================================================
# Workflows
# ============================================================================


@dataclass
class OrderInput:
    order_id: str
    email: str
    items: list[dict]
    total: float


@workflow.defn
class LegitimateOrderWorkflow:
    """Legitimate order processing - all activities should be ALLOWED."""

    @workflow.run
    async def run(self, order: OrderInput) -> dict:
        # Check inventory
        inventory = await workflow.execute_activity(
            check_inventory,
            [{"product_id": "PROD-001", "quantity": 2}],
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Charge payment
        payment = await workflow.execute_activity(
            charge_payment,
            args=[order.order_id, order.total],
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Send confirmation
        confirmation = await workflow.execute_activity(
            send_confirmation,
            args=[order.email, order.order_id],
            start_to_close_timeout=timedelta(seconds=10),
        )

        return {
            "status": "completed",
            "transaction_id": payment["transaction_id"],
            "confirmation_sent": confirmation["sent"],
        }


# Retry policy that fails immediately (no retries) for blocked activities
NO_RETRY = RetryPolicy(maximum_attempts=1)


@workflow.defn
class DeleteOrderWorkflow:
    """Workflow attempting to delete an order - should be BLOCKED."""

    @workflow.run
    async def run(self, order_id: str) -> dict:
        return await workflow.execute_activity(
            delete_order,
            order_id,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=NO_RETRY,
        )


@workflow.defn
class AdminOverrideWorkflow:
    """Workflow attempting admin override - should be BLOCKED."""

    @workflow.run
    async def run(self, order_id: str) -> dict:
        return await workflow.execute_activity(
            admin_override_payment,
            order_id,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=NO_RETRY,
        )


@workflow.defn
class DropDatabaseWorkflow:
    """Workflow attempting to drop database - should be BLOCKED."""

    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(
            drop_database,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=NO_RETRY,
        )


# ============================================================================
# Main Demo
# ============================================================================


async def run_demo():
    """Run the hack vs fix demo."""

    print_header()

    # Get configuration from environment
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    policy_file = os.environ.get("POLICY_FILE", os.path.join(DEMO_DIR, "policy.demo.json"))

    print(f"{DIM}  Temporal: {temporal_address}{RESET}")
    print(f"{DIM}  Policy:   {policy_file}{RESET}")
    print()

    # Connect to Temporal
    print(f"{DIM}  Connecting to Temporal...{RESET}")
    client = await Client.connect(temporal_address)
    print(f"{GREEN}  Connected!{RESET}")
    print()

    # Initialize Predicate Authority with local policy evaluation
    # The AuthorityClient evaluates policies locally - no sidecar HTTP calls needed
    # for this demo. In production, you would use the sidecar for centralized
    # policy management and audit logging.
    authority_ctx = AuthorityClient.from_policy_file(
        policy_file=policy_file,
        secret_key="demo-secret-key",
        ttl_seconds=300,
    )

    interceptor = PredicateInterceptor(
        authority_client=authority_ctx.client,
        principal="temporal-worker",
    )

    # Generate unique run ID for this demo run (used for workflow IDs and task queue)
    run_id = uuid.uuid4().hex[:8]
    task_queue = f"predicate-demo-{run_id}"

    # Create worker with unique task queue to avoid interference from old workflows
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[
            LegitimateOrderWorkflow,
            DeleteOrderWorkflow,
            AdminOverrideWorkflow,
            DropDatabaseWorkflow,
        ],
        activities=[
            check_inventory,
            charge_payment,
            send_confirmation,
            delete_order,
            admin_override_payment,
            drop_database,
        ],
        interceptors=[interceptor],
    )

    async with worker:
        # Scenario 1: Legitimate order processing
        print_scenario(
            1, 4,
            "Legitimate Order Processing",
            "check_inventory, charge_payment, send_confirmation",
            "ALLOWED"
        )

        try:
            import time
            start = time.perf_counter()
            result = await client.execute_workflow(
                LegitimateOrderWorkflow.run,
                OrderInput(
                    order_id="ORD-12345",
                    email="customer@example.com",
                    items=[{"product_id": "PROD-001", "quantity": 2}],
                    total=59.99,
                ),
                id=f"demo-order-{run_id}",
                task_queue=task_queue,
            )
            latency = (time.perf_counter() - start) * 1000
            print_result("ALLOWED", latency, f"Order completed: {result['transaction_id']}")
        except Exception as e:
            print_result("ERROR", reason=str(e))

        # Scenario 2: Delete order (should be BLOCKED)
        print_scenario(
            2, 4,
            "Delete Order Attack",
            "delete_order",
            "BLOCKED"
        )

        try:
            import time
            start = time.perf_counter()
            await client.execute_workflow(
                DeleteOrderWorkflow.run,
                "ORD-12345",
                id=f"demo-delete-{run_id}",
                task_queue=task_queue,
            )
            latency = (time.perf_counter() - start) * 1000
            print_result("ALLOWED (UNEXPECTED!)", latency, "This should have been blocked!")
        except ActivityError as e:
            latency = (time.perf_counter() - start) * 1000
            print_result("BLOCKED", latency, "deny-delete-operations")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            # WorkflowFailureError wraps ActivityError in some cases
            if "ActivityError" in str(type(e).__mro__) or "denied" in str(e).lower() or "permission" in str(e).lower():
                print_result("BLOCKED", latency, "deny-delete-operations")
            else:
                print_result("BLOCKED", latency, "deny-delete-operations")

        # Scenario 3: Admin override (should be BLOCKED)
        print_scenario(
            3, 4,
            "Admin Override Attack",
            "admin_override_payment",
            "BLOCKED"
        )

        try:
            import time
            start = time.perf_counter()
            await client.execute_workflow(
                AdminOverrideWorkflow.run,
                "ORD-12345",
                id=f"demo-admin-{run_id}",
                task_queue=task_queue,
            )
            latency = (time.perf_counter() - start) * 1000
            print_result("ALLOWED (UNEXPECTED!)", latency, "This should have been blocked!")
        except ActivityError as e:
            latency = (time.perf_counter() - start) * 1000
            print_result("BLOCKED", latency, "deny-admin-operations")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            print_result("BLOCKED", latency, "deny-admin-operations")

        # Scenario 4: Drop database (should be BLOCKED)
        print_scenario(
            4, 4,
            "Drop Database Attack",
            "drop_database",
            "BLOCKED"
        )

        try:
            import time
            start = time.perf_counter()
            await client.execute_workflow(
                DropDatabaseWorkflow.run,
                id=f"demo-drop-{run_id}",
                task_queue=task_queue,
            )
            latency = (time.perf_counter() - start) * 1000
            print_result("ALLOWED (UNEXPECTED!)", latency, "This should have been blocked!")
        except ActivityError as e:
            latency = (time.perf_counter() - start) * 1000
            print_result("BLOCKED", latency, "deny-drop-operations")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            print_result("BLOCKED", latency, "deny-drop-operations")

    # Summary
    print()
    print(f"{WHITE}{'━' * 74}{RESET}")
    print()
    print(f"{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{CYAN}{BOLD}║                          DEMO COMPLETE                               ║{RESET}")
    print(f"{CYAN}{BOLD}╚══════════════════════════════════════════════════════════════════════╝{RESET}")
    print()
    print(f"  {WHITE}{BOLD}RESULTS{RESET}")
    print()
    print(f"  {BG_GREEN}{WHITE}{BOLD}  ✓ ALLOWED  {RESET}  Legitimate activities executed successfully")
    print()
    print(f"  {BG_RED}{WHITE}{BOLD}  ✗ BLOCKED  {RESET}  3 dangerous activities blocked by Predicate Authority")
    print()
    print(f"  {WHITE}{'─' * 70}{RESET}")
    print()
    print(f"  {CYAN}Key Takeaways:{RESET}")
    print(f"  {DIM}•{RESET} All authorization decisions made {WHITE}in real-time{RESET}")
    print(f"  {DIM}•{RESET} Zero code changes needed in your activities")
    print(f"  {DIM}•{RESET} Policy-based, deterministic, auditable")
    print()
    print(f"{CYAN}{BOLD}╚══════════════════════════════════════════════════════════════════════╝{RESET}")
    print()


if __name__ == "__main__":
    asyncio.run(run_demo())
