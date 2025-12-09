#!/bin/bash
set -e

# Set umask for group-writable directories (775 permissions)
# This ensures all directories created at runtime are accessible
umask 0002

# Execute the main command
exec gunicorn main:app \
     --workers 4 \
     --worker-class uvicorn.workers.UvicornWorker \
     --bind 0.0.0.0:8000 \
     --timeout 60 \
     --access-logfile - \
     --error-logfile -
