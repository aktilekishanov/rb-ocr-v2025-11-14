# FastAPI Service Setup Guide (Server)

This guide explains how to set up a virtual environment and test the FastAPI service on the `rb_admin/rb-loan-deferment-idp/` server without using systemd.

## Directory Structure

```
rb_admin/rb-loan-deferment-idp/
├── fastapi-service/
│   ├── main.py
│   ├── requirements.txt
│   ├── api/
│   ├── pipeline/
│   └── ...
└── unified-wheels/
    ├── core-server/
    ├── pillow/
    ├── pypdf/
    ├── rapidfuzz/
    └── streamlit/
```

## Step 1: Create Virtual Environment

SSH into the server and navigate to the fastapi-service directory:

```bash
cd ~/rb_admin/rb-loan-deferment-idp/fastapi-service
```

Create a Python virtual environment:

```bash
python3 -m venv venv
```

Activate the virtual environment:

```bash
source venv/bin/activate
```

> [!NOTE]
> You should see `(venv)` prefix in your terminal prompt indicating the virtual environment is active.

## Step 2: Install Dependencies from Wheels

Install all dependencies from the unified-wheels directory:

```bash
pip install --no-index --find-links=../unified-wheels/core-server -r requirements.txt
```

This command:
- `--no-index`: Prevents pip from downloading from PyPI (offline installation)
- `--find-links=../unified-wheels/core-server`: Points to the local wheel directory
- `-r requirements.txt`: Installs all packages listed in requirements.txt

> [!TIP]
> If you encounter any missing dependencies, you can check what's available in the unified-wheels directory and install them manually.

## Step 3: Verify Installation

Check that all packages are installed correctly:

```bash
pip list
```

You should see packages like:
- fastapi
- uvicorn
- gunicorn
- httpx
- rapidfuzz
- pypdf
- pillow
- pydantic

## Step 4: Test the FastAPI Service

### Option A: Using Uvicorn (Development Server)

Run the service with uvicorn for quick testing:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Parameters:
- `main:app`: Points to the `app` object in `main.py`
- `--host 0.0.0.0`: Allows external connections
- `--port 8000`: Service port (change if needed)
- `--reload`: Auto-reloads on code changes (remove for production)

### Option B: Using Gunicorn (Production-like)

Run the service with gunicorn and uvicorn workers:

```bash
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
```

Parameters:
- `--workers 4`: Number of worker processes (adjust based on CPU cores)
- `--worker-class uvicorn.workers.UvicornWorker`: Use Uvicorn workers for async support
- `--bind 0.0.0.0:8000`: Bind to all interfaces on port 8000
- `--timeout 120`: Request timeout in seconds
- `--access-logfile -`: Log access to stdout
- `--error-logfile -`: Log errors to stdout

> [!IMPORTANT]
> For production deployment, use Option B (Gunicorn) as it provides better process management and stability.

## Step 5: Test the API

Once the service is running, test it from another terminal or machine:

### Check Health Endpoint

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-28T14:07:08+05:00"
}
```

### Test Document Verification

```bash
curl -X POST http://localhost:8000/v1/verify \
  -F "file=@/path/to/test-document.pdf" \
  -F "doc_type=NID"
```

Replace `/path/to/test-document.pdf` with an actual document path.

### View API Documentation

Open in a browser:
- Swagger UI: `http://<server-ip>:8000/docs`
- ReDoc: `http://<server-ip>:8000/redoc`

## Step 6: Stop the Service

To stop the service, press `Ctrl+C` in the terminal where it's running.

## Step 7: Deactivate Virtual Environment

When done testing:

```bash
deactivate
```

## Troubleshooting

### Port Already in Use

If port 8000 is already in use, change the port:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

### Missing Dependencies

If a package is missing, check the unified-wheels directory:

```bash
ls -la ../unified-wheels/core-server/*.whl
```

Install a specific wheel:

```bash
pip install ../unified-wheels/core-server/package-name.whl
```

### Permission Issues

If you get permission errors, ensure you have write access to the directory:

```bash
chmod -R u+w ~/rb_admin/rb-loan-deferment-idp/fastapi-service
```

### Python Version

Ensure you're using Python 3.11 (the wheels are built for cp311):

```bash
python3 --version
```

## Running in Background (Without systemd)

If you want to run the service in the background temporarily:

### Using nohup

```bash
nohup gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile access.log \
  --error-logfile error.log \
  > output.log 2>&1 &
```

Check the process:

```bash
ps aux | grep gunicorn
```

Stop the service:

```bash
# Find the process ID
ps aux | grep gunicorn

# Kill the process
kill <PID>
```

### Using screen

Start a screen session:

```bash
screen -S fastapi
```

Run the service:

```bash
source venv/bin/activate
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Detach from screen: Press `Ctrl+A` then `D`

Reattach to screen:

```bash
screen -r fastapi
```

Stop the service: Reattach and press `Ctrl+C`

## Quick Reference Commands

```bash
# Setup
cd ~/rb_admin/rb-loan-deferment-idp/fastapi-service
python3 -m venv venv
source venv/bin/activate
pip install --no-index --find-links=../unified-wheels/core-server -r requirements.txt

# Run (Development)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Run (Production-like)
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Test
curl http://localhost:8000/health

# Stop
# Press Ctrl+C

# Cleanup
deactivate
```

## Next Steps

Once you've verified the service works correctly:

1. Set up the systemd service for automatic startup (see deployment documentation)
2. Configure nginx as a reverse proxy
3. Set up SSL/TLS certificates
4. Configure firewall rules
5. Set up monitoring and logging
