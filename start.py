#!/usr/bin/env python3
import os
import subprocess

# Get PORT from environment, default to 8000
port = os.getenv("PORT", "8000")

# Run uvicorn with the port
subprocess.run([
    "uvicorn",
    "app.main:app",
    "--host", "0.0.0.0",
    "--port", port
])
