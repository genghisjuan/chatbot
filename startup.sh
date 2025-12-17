#!/bin/bash
set -e

echo "=== Starting Database Migration ==="
python migrate_db.py || {
    echo "ERROR: Migration failed!"
    exit 1
}
echo "=== Migration Complete ==="

echo "=== Starting Application ==="
uvicorn app.main:app --host 0.0.0.0 --port $PORT
