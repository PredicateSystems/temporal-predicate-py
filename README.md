# predicate-temporal

Temporal.io Worker Interceptor for Predicate Authority Zero-Trust authorization.

This package provides a pre-execution security gate for all Temporal Activities, enforcing cryptographic authorization mandates before any activity code runs.

## Prerequisites

This package requires the **Predicate Authority Sidecar** daemon to be running. The sidecar is a lightweight Rust binary that handles policy evaluation and mandate signing.

| Resource | Link |
|----------|------|
| Sidecar Repository | [github.com/PredicateSystems/predicate-authority-sidecar](https://github.com/PredicateSystems/predicate-authority-sidecar) |
| Download Binaries | [Latest Releases](https://github.com/PredicateSystems/predicate-authority-sidecar/releases) |
| License | MIT / Apache 2.0 |

### Quick Sidecar Setup

```bash
# Download the latest release for your platform
# Linux x64, macOS x64/ARM64, Windows x64 available

# Extract and run
tar -xzf predicate-authorityd-*.tar.gz
chmod +x predicate-authorityd

# Start with a policy file
./predicate-authorityd --port 8787 --policy-file policy.json
```

## Installation

```bash
pip install predicate-temporal
```

## Quick Start

```python
from temporalio.worker import Worker
from predicate_temporal import PredicateInterceptor
from predicate_authority import AuthorityClient

# Initialize the Predicate Authority client
ctx = AuthorityClient.from_env()

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
    interceptors=[interceptor],
)
```

## How It Works

The interceptor sits in the Temporal activity execution pipeline:

1. Temporal dispatches an activity to your worker
2. **Before** the activity code runs, the interceptor extracts:
   - Activity name (action)
   - Activity arguments (context)
3. The interceptor calls `AuthorityClient.authorize()` to request a mandate
4. If **denied**: raises `PermissionError` - activity never executes
5. If **approved**: activity proceeds normally

This ensures that no untrusted code or payload reaches your OS until it has been cryptographically authorized.

## Configuration

### Environment Variables

Set these environment variables for the Authority client:

```bash
export PREDICATE_AUTHORITY_POLICY_FILE=/path/to/policy.json
export PREDICATE_AUTHORITY_SIGNING_KEY=your-secret-key
export PREDICATE_AUTHORITY_MANDATE_TTL_SECONDS=300
```

### Policy File

Create a policy file that defines allowed activities:

```json
{
  "rules": [
    {
      "name": "allow-safe-activities",
      "effect": "allow",
      "principals": ["temporal-worker"],
      "actions": ["process_order", "send_notification"],
      "resources": ["*"]
    },
    {
      "name": "deny-dangerous-activities",
      "effect": "deny",
      "principals": ["*"],
      "actions": ["delete_*", "admin_*"],
      "resources": ["*"]
    }
  ]
}
```

## API Reference

### PredicateInterceptor

```python
PredicateInterceptor(
    authority_client: AuthorityClient,
    principal: str = "temporal-worker",
    tenant_id: str | None = None,
    session_id: str | None = None,
)
```

**Parameters:**

- `authority_client`: The Predicate Authority client instance
- `principal`: Principal ID used for authorization requests (default: "temporal-worker")
- `tenant_id`: Optional tenant ID for multi-tenant setups
- `session_id`: Optional session ID for request correlation

### PredicateActivityInterceptor

The inbound interceptor that performs the actual authorization check. Created automatically by `PredicateInterceptor`.

## Error Handling

When authorization is denied, the interceptor raises a `PermissionError`:

```python
try:
    await workflow.execute_activity(
        dangerous_activity,
        args,
        start_to_close_timeout=timedelta(seconds=30),
    )
except ActivityError as e:
    if isinstance(e.cause, ApplicationError):
        # Handle authorization denial
        print(f"Activity blocked: {e.cause.message}")
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src

# Linting
ruff check src tests
ruff format src tests
```

## License

MIT
