"""
E-commerce example demonstrating Predicate Temporal interceptor in a realistic scenario.

This example simulates an order processing system with:
- Inventory management
- Payment processing
- Order confirmation
- Policy-based access control

Prerequisites:
- Temporal server running locally (temporal server start-dev)
- Predicate Authority daemon running (./predicate-authorityd --port 8787 --policy-file policy.json)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import List
import random

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.exceptions import ActivityError

from predicate_authority import AuthorityClient
from predicate_temporal import PredicateInterceptor


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class OrderItem:
    product_id: str
    quantity: int
    price: float


@dataclass
class Order:
    order_id: str
    customer_email: str
    items: List[OrderItem]

    @property
    def total(self) -> float:
        return sum(item.price * item.quantity for item in self.items)


@dataclass
class InventoryResult:
    available: bool
    reserved_items: List[str]


@dataclass
class PaymentResult:
    success: bool
    transaction_id: str
    amount: float


@dataclass
class OrderResult:
    order_id: str
    status: str
    transaction_id: str | None
    confirmation_sent: bool


# ============================================================================
# Activities - Secured by Predicate Authority
# ============================================================================


@activity.defn
async def check_inventory(items: List[dict]) -> dict:
    """Check if items are available in inventory."""
    activity.logger.info(f"Checking inventory for {len(items)} items")

    # Simulate inventory check
    await asyncio.sleep(0.1)

    return {
        "available": True,
        "checked_items": [item["product_id"] for item in items],
    }


@activity.defn
async def reserve_inventory(items: List[dict]) -> dict:
    """Reserve items in inventory."""
    activity.logger.info(f"Reserving {len(items)} items")

    # Simulate reservation
    await asyncio.sleep(0.1)

    return {
        "reserved": True,
        "reservation_id": f"res-{random.randint(1000, 9999)}",
    }


@activity.defn
async def charge_payment(order_id: str, amount: float, email: str) -> dict:
    """Process payment for the order."""
    activity.logger.info(f"Charging ${amount:.2f} for order {order_id}")

    # Simulate payment processing
    await asyncio.sleep(0.2)

    return {
        "success": True,
        "transaction_id": f"txn-{random.randint(10000, 99999)}",
        "amount": amount,
    }


@activity.defn
async def refund_payment(transaction_id: str, amount: float) -> dict:
    """Refund a payment (used for compensation)."""
    activity.logger.info(f"Refunding ${amount:.2f} for transaction {transaction_id}")

    await asyncio.sleep(0.1)

    return {
        "refunded": True,
        "refund_id": f"ref-{random.randint(10000, 99999)}",
    }


@activity.defn
async def send_confirmation(email: str, order_id: str, transaction_id: str) -> dict:
    """Send order confirmation email."""
    activity.logger.info(f"Sending confirmation to {email} for order {order_id}")

    await asyncio.sleep(0.1)

    return {
        "sent": True,
        "email": email,
        "order_id": order_id,
    }


@activity.defn
async def process_order(order: dict) -> dict:
    """Main order processing activity."""
    activity.logger.info(f"Processing order {order['order_id']}")

    return {
        "processed": True,
        "order_id": order["order_id"],
    }


# Dangerous activities - will be BLOCKED by policy


@activity.defn
async def delete_order(order_id: str) -> dict:
    """Delete an order - BLOCKED by policy."""
    # This will never execute
    return {"deleted": True, "order_id": order_id}


@activity.defn
async def admin_override_payment(order_id: str) -> dict:
    """Admin payment override - BLOCKED by policy."""
    # This will never execute
    return {"overridden": True}


# ============================================================================
# Workflows
# ============================================================================


@workflow.defn
class OrderProcessingWorkflow:
    """
    Order processing workflow with Predicate authorization.

    All activities are checked against the policy before execution.
    """

    @workflow.run
    async def run(self, order: dict) -> dict:
        order_id = order["order_id"]
        items = order["items"]
        email = order["customer_email"]
        total = sum(item["price"] * item["quantity"] for item in items)

        workflow.logger.info(f"Starting order processing for {order_id}")

        # Step 1: Check inventory (allowed)
        inventory = await workflow.execute_activity(
            check_inventory,
            items,
            start_to_close_timeout=timedelta(seconds=30),
        )

        if not inventory["available"]:
            return {
                "order_id": order_id,
                "status": "failed",
                "reason": "inventory_unavailable",
            }

        # Step 2: Reserve inventory (allowed)
        reservation = await workflow.execute_activity(
            reserve_inventory,
            items,
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Step 3: Process payment (allowed)
        payment = await workflow.execute_activity(
            charge_payment,
            args=[order_id, total, email],
            start_to_close_timeout=timedelta(seconds=60),
        )

        if not payment["success"]:
            # Compensation would go here
            return {
                "order_id": order_id,
                "status": "failed",
                "reason": "payment_failed",
            }

        # Step 4: Process order (allowed)
        await workflow.execute_activity(
            process_order,
            order,
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Step 5: Send confirmation (allowed)
        confirmation = await workflow.execute_activity(
            send_confirmation,
            args=[email, order_id, payment["transaction_id"]],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return {
            "order_id": order_id,
            "status": "completed",
            "transaction_id": payment["transaction_id"],
            "confirmation_sent": confirmation["sent"],
        }


@workflow.defn
class MaliciousWorkflow:
    """
    Workflow attempting unauthorized operations.

    These activities will be BLOCKED by Predicate Authority.
    """

    @workflow.run
    async def run(self, order_id: str) -> dict:
        results = {"attempted": [], "blocked": []}

        # Attempt 1: Try to delete an order (BLOCKED)
        try:
            await workflow.execute_activity(
                delete_order,
                order_id,
                start_to_close_timeout=timedelta(seconds=10),
            )
            results["attempted"].append("delete_order")
        except ActivityError:
            results["blocked"].append("delete_order")

        # Attempt 2: Try admin override (BLOCKED)
        try:
            await workflow.execute_activity(
                admin_override_payment,
                order_id,
                start_to_close_timeout=timedelta(seconds=10),
            )
            results["attempted"].append("admin_override_payment")
        except ActivityError:
            results["blocked"].append("admin_override_payment")

        return results


# ============================================================================
# Main
# ============================================================================


async def main():
    """Run the e-commerce demo."""

    client = await Client.connect("localhost:7233")

    # Initialize Predicate Authority
    authority_ctx = AuthorityClient.from_policy_file(
        policy_file="policy.json",
        secret_key="ecommerce-demo-signing-key",
        ttl_seconds=300,
    )

    interceptor = PredicateInterceptor(
        authority_client=authority_ctx.client,
        principal="temporal-worker",
        tenant_id="ecommerce-store",
    )

    worker = Worker(
        client,
        task_queue="ecommerce-queue",
        workflows=[OrderProcessingWorkflow, MaliciousWorkflow],
        activities=[
            check_inventory,
            reserve_inventory,
            charge_payment,
            refund_payment,
            send_confirmation,
            process_order,
            delete_order,
            admin_override_payment,
        ],
        interceptors=[interceptor],
    )

    print("=" * 70)
    print("E-commerce Order Processing with Predicate Zero-Trust Authorization")
    print("=" * 70)

    async with worker:
        # Demo 1: Legitimate order processing
        print("\n[Demo 1] Processing a legitimate order...")
        print("-" * 50)

        order = {
            "order_id": "ORD-12345",
            "customer_email": "customer@example.com",
            "items": [
                {"product_id": "PROD-001", "quantity": 2, "price": 29.99},
                {"product_id": "PROD-002", "quantity": 1, "price": 49.99},
            ],
        }

        try:
            result = await client.execute_workflow(
                OrderProcessingWorkflow.run,
                order,
                id="order-workflow-1",
                task_queue="ecommerce-queue",
            )
            print(f"  Order ID: {result['order_id']}")
            print(f"  Status: {result['status']}")
            print(f"  Transaction: {result.get('transaction_id', 'N/A')}")
            print(f"  Confirmation sent: {result.get('confirmation_sent', False)}")
        except Exception as e:
            print(f"  Error: {e}")

        # Demo 2: Attempted malicious operations
        print("\n[Demo 2] Attempting unauthorized operations...")
        print("-" * 50)

        try:
            result = await client.execute_workflow(
                MaliciousWorkflow.run,
                "ORD-12345",
                id="malicious-workflow-1",
                task_queue="ecommerce-queue",
            )
            print(f"  Blocked activities: {result['blocked']}")
            print(f"  (These activities were denied by Predicate Authority)")
        except Exception as e:
            print(f"  Error: {e}")

        print("\n" + "=" * 70)
        print("Demo complete! All dangerous operations were blocked.")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
