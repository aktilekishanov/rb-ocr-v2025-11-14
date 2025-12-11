FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# SKIPPED: Server is air-gapped. Tesseract must be installed manually via .deb files if needed.
# RUN apt-get update && apt-get install -y ...

# Copy offline wheels from parent directory
COPY wheels/wheels-backend /tmp/wheels/backend

# Copy requirements file
COPY fastapi-service/requirements.txt .

# Install from offline wheels (NO INTERNET NEEDED)
# We move all wheels to the root of /tmp/wheels/backend to handle subdirectories
RUN find /tmp/wheels/backend -name "*.whl" -exec mv {} /tmp/wheels/backend/ \; && \
    pip install --no-index \
    --find-links=/tmp/wheels/backend \
    -r requirements.txt && \
    rm -rf /tmp/wheels

# Copy application code
COPY fastapi-service/ .

# Create runs directory with group-writable permissions
RUN mkdir -p /app/runs && chmod 775 /app/runs

# Copy database setup script (for offline server deployment)
COPY fastapi-service/create_db_table.py /app/db_setup.py

# Copy and setup entrypoint script
COPY fastapi-service/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

# Use entrypoint script to set umask before running Gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]
