# Predicate Temporal Demo: Hack vs Fix

**See how Predicate Authority blocks dangerous Temporal activities in real-time.**

This demo shows Temporal workflows attempting to:
1. Process a legitimate order (allowed)
2. Delete an order (blocked)
3. Override payment as admin (blocked)
4. Drop the database (blocked)

## Quick Start

```bash
git clone https://github.com/PredicateSystems/predicate-temporal
cd predicate-temporal/examples/demo
./start-demo-native.sh
```

That's it. The script starts Temporal and runs the demo with local policy evaluation.

## What You'll See

```
========================================
  PREDICATE TEMPORAL: Hack vs Fix Demo
========================================

  Temporal: localhost:7233
  Policy:   /path/to/policy.demo.json

  Connecting to Temporal...
  Connected!

──────────────────────────────────────────────────────────────────────
  [1/4] Legitimate Order Processing
  Activity: check_inventory, charge_payment, send_confirmation
  Expected: ALLOWED

  ✓ ALLOWED (245ms)
  Reason: Order completed: txn-ORD-1234

──────────────────────────────────────────────────────────────────────
  [2/4] Delete Order Attack
  Activity: delete_order
  Expected: BLOCKED

  ✗ BLOCKED (18ms)
  Reason: deny-delete-operations

──────────────────────────────────────────────────────────────────────
  [3/4] Admin Override Attack
  Activity: admin_override_payment
  Expected: BLOCKED

  ✗ BLOCKED (15ms)
  Reason: deny-admin-operations

──────────────────────────────────────────────────────────────────────
  [4/4] Drop Database Attack
  Activity: drop_database
  Expected: BLOCKED

  ✗ BLOCKED (12ms)
  Reason: deny-drop-operations

======================================================================

  Demo Complete!

  Results:
  ✓ Legitimate activities executed successfully
  ✗ 3 dangerous activities blocked by Predicate Authority

  All authorization decisions made in real-time by Predicate Authority.
  Zero code changes needed in your activities.

======================================================================
```

## How It Works

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────┐
│  Temporal   │───▶│   Predicate      │───▶│  Sidecar    │
│  Worker     │    │   Interceptor    │    │  (policy)   │
│             │    │                  │    │             │
│ activity:   │    │ action:          │    │  DENY or    │
│ delete_order│    │ delete_order     │    │  ALLOW      │
└─────────────┘    └──────────────────┘    └─────────────┘
                          │
                          ▼
                   PermissionError
                   (Activity never runs)
```

1. Temporal dispatches an activity to the worker
2. **Before** the activity code runs, the `PredicateInterceptor` extracts the activity name
3. The interceptor calls the sidecar's `/v1/authorize` endpoint
4. Decision returned in <25ms
5. DENY = raise `PermissionError`, ALLOW = execute activity

## Key Properties

| Property | Value |
|----------|-------|
| **Deterministic** | Policy-based rules, not probabilistic |
| **Fast** | p50 < 25ms authorization latency |
| **Auditable** | Every decision logged with mandate ID |
| **Fail-closed** | Sidecar errors block execution |
| **Zero code changes** | Activities don't need modification |

## Customize the Policy

Edit `policy.demo.json` to add your own rules:

```json
{
  "rules": [
    {
      "name": "deny-dangerous-ops",
      "effect": "deny",
      "principals": ["*"],
      "actions": ["delete_*", "drop_*", "admin_*"],
      "resources": ["*"]
    },
    {
      "name": "allow-order-processing",
      "effect": "allow",
      "principals": ["temporal-worker"],
      "actions": ["check_inventory", "charge_payment", "send_confirmation"],
      "resources": ["*"]
    }
  ]
}
```

Then re-run `./start-demo.sh`.

## Requirements

- Docker (with Docker Compose)

No other dependencies. Everything runs in containers.

## Native Mode (No Docker)

If you prefer to run without Docker:

```bash
./start-demo-native.sh
```

This requires:
- Python 3.11+
- Temporal CLI (`brew install temporal`)
- Predicate sidecar binary (auto-downloaded)

## Install in Your Project

```bash
pip install predicate-temporal predicate-authority
```

```python
from temporalio.worker import Worker
from predicate_temporal import PredicateInterceptor
from predicate_authority import AuthorityClient

# Initialize Predicate Authority
ctx = AuthorityClient.from_sidecar(sidecar_url="http://localhost:8787")

# Create the interceptor
interceptor = PredicateInterceptor(
    authority_client=ctx.client,
    principal="temporal-worker",
)

# Create worker with the interceptor
worker = Worker(
    client=temporal_client,
    task_queue="my-task-queue",
    workflows=[MyWorkflow],
    activities=[my_activity],
    interceptors=[interceptor],  # <-- This is all you need
)
```

## Links

- [GitHub: predicate-temporal](https://github.com/PredicateSystems/predicate-temporal)
- [PyPI: predicate-temporal](https://pypi.org/project/predicate-temporal/)
- [Predicate Authority SDK (Python)](https://github.com/PredicateSystems/predicate-authority)
- [Predicate Authority Sidecar](https://github.com/PredicateSystems/predicate-authority-sidecar)

## License

MIT / Apache 2.0
