FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create runs directory with group-writable permissions
RUN mkdir -p /app/runs && chmod 775 /app/runs

# Copy database setup script (for offline server deployment)
COPY scripts/init_db.py /app/db_setup.py

EXPOSE 8000

# Use bash to set umask before running gunicorn
CMD ["/bin/bash", "-c", "umask 0002 && exec gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 60 --access-logfile - --error-logfile -"]


