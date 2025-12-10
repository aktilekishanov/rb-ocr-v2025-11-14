FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
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
COPY create_db_table.py /app/db_setup.py

# Copy and setup entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

# Use entrypoint script to set umask before running Gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]
