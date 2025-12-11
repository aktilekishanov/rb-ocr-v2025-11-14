FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (if any needed for streamlit/pillow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy offline wheels from parent directory
COPY wheels/wheels-ui /tmp/wheels/ui

# Copy requirements file
COPY ui/requirements.txt .

# Install from offline wheels (NO INTERNET NEEDED)
# We move all wheels to the root of /tmp/wheels/ui to handle subdirectories
RUN find /tmp/wheels/ui -name "*.whl" -exec mv {} /tmp/wheels/ui/ \; && \
    pip install --no-index \
    --find-links=/tmp/wheels/ui \
    -r requirements.txt && \
    rm -rf /tmp/wheels

# Copy application code
COPY ui/ .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
