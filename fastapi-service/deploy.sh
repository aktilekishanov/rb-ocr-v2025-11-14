#!/bin/bash
set -e

echo "Deploying RB-OCR FastAPI Service..."

# Activate venv
source .venv/bin/activate

# Verify dependencies
echo "Verifying dependencies..."
pip check

# Test import
echo "Testing imports..."
python3 -c "from pipeline.orchestrator import run_pipeline; from api.schemas import VerifyResponse; print('✅ Imports OK')"

# Create log directory
sudo mkdir -p /var/log/rb-ocr-api
sudo chown rb_admin2:rb_admin2 /var/log/rb-ocr-api

# Install systemd service
echo "Installing systemd service..."
sudo cp system/rb-ocr-fastapi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rb-ocr-fastapi
sudo systemctl restart rb-ocr-fastapi

# Check status
sleep 2
sudo systemctl status rb-ocr-fastapi --no-pager

echo "✅ Deployment complete!"
echo "Check logs: sudo journalctl -u rb-ocr-fastapi -f"
echo "API Docs: http://localhost:8001/docs"
