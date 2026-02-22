#!/bin/bash
#
# Predicate Temporal Demo - Quick Start
#
# This script runs the full "Hack vs Fix" demo using Docker.
# Shows how Predicate Authority blocks dangerous Temporal activities.
#
# Usage: ./start-demo.sh
#

set -e

cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "  Predicate Temporal: Hack vs Fix Demo"
echo "========================================"
echo ""

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is required but not installed."
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check for docker compose
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "Error: docker compose is required but not installed."
    exit 1
fi

echo "Building and starting containers..."
echo ""

# Build and run
$COMPOSE_CMD -f docker-compose.demo.yml up --build --abort-on-container-exit

# Cleanup
echo ""
echo "Cleaning up containers..."
$COMPOSE_CMD -f docker-compose.demo.yml down

echo ""
echo "Done! To run again: ./start-demo.sh"
echo ""
