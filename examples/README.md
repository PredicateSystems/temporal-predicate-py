# Predicate Temporal Python Examples

This directory contains examples demonstrating how to use `predicate-temporal` to secure Temporal activities.

## Prerequisites

1. Install dependencies:
   ```bash
   pip install temporalio predicate-authority predicate-temporal
   ```

2. Start the Predicate Authority daemon:
   ```bash
   # Download from https://github.com/PredicateSystems/predicate-authority-sidecar/releases
   ./predicate-authorityd --port 8787 --policy-file policy.json
   ```

3. Start a local Temporal server:
   ```bash
   temporal server start-dev
   ```

## Examples

### Basic Example (`basic_worker.py`)

A minimal example showing:
- Setting up activities with Predicate interceptor
- Running a workflow that executes secured activities
- Handling authorization denials

Run with:
```bash
python basic_worker.py
```

### E-commerce Example (`ecommerce_worker.py`)

A realistic e-commerce scenario with:
- Order processing activities
- Payment handling
- Inventory management
- Policy-based access control

Run with:
```bash
python ecommerce_worker.py
```

## Policy File

The `policy.json` file defines which activities are allowed. Example:

```json
{
  "rules": [
    {
      "name": "allow-order-processing",
      "effect": "allow",
      "principals": ["temporal-worker"],
      "actions": ["process_order", "check_inventory", "send_confirmation"],
      "resources": ["*"]
    },
    {
      "name": "deny-admin-actions",
      "effect": "deny",
      "principals": ["*"],
      "actions": ["delete_*", "admin_*"],
      "resources": ["*"]
    }
  ]
}
```
