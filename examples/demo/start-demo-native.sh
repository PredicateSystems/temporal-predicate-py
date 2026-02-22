#!/bin/bash
#
# Predicate Temporal Demo - Native Quick Start
#
# This script runs the demo natively on your machine.
# Requires: Python 3.11+, Temporal server
#
# The demo uses local policy evaluation (no sidecar required).
#
# Usage: ./start-demo-native.sh
#

set -e

cd "$(dirname "$0")"
DEMO_DIR="$(pwd)"
REPO_ROOT="$(cd ../.. && pwd)"

echo ""
echo "========================================"
echo "  Predicate Temporal: Hack vs Fix Demo"
echo "========================================"
echo ""

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# Check for Temporal CLI
if ! command -v temporal &> /dev/null; then
    echo ""
    echo "Temporal CLI not found. Installing..."
    if command -v brew &> /dev/null; then
        brew install temporal
    else
        echo "Please install Temporal CLI: https://docs.temporal.io/cli"
        exit 1
    fi
fi

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
cd "$REPO_ROOT"
pip install -e ".[dev]" --quiet 2>/dev/null || pip install -e ".[dev]"

# Start Temporal server in background
echo ""
echo "Starting Temporal server (dev mode)..."
temporal server start-dev --headless &
TEMPORAL_PID=$!

# Wait for Temporal to be ready
echo "Waiting for Temporal to be ready..."
for i in {1..30}; do
    if temporal operator namespace describe default > /dev/null 2>&1; then
        echo "Temporal is ready."
        break
    fi
    sleep 1
done

# Run demo
echo ""
echo "Running demo..."
echo ""

cd "$REPO_ROOT"
POLICY_FILE="$DEMO_DIR/policy.demo.json" TEMPORAL_ADDRESS=localhost:7233 python3 "$DEMO_DIR/demo.py"

# Cleanup
echo ""
echo "Cleaning up..."
kill $TEMPORAL_PID 2>/dev/null || true

echo ""
echo "Done! To run again: ./start-demo-native.sh"
echo ""
