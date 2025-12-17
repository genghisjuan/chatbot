#!/bin/bash
set -e

echo "=== Starting Application ==="
uvicorn app.main:app --host 0.0.0.0 --port $PORT
