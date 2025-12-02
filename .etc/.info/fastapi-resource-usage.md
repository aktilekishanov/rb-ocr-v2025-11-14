# 🔧 FastAPI Service - Resource Usage & Capacity Analysis

> **Server**: `cfo-prod-llm-uv01`  
> **Service**: RB-OCR Document Verification API  
> **Last Updated**: 2025-11-27

---

## 📊 Server Hardware Specifications

### CPU Resources
```
Model:           Intel(R) Xeon(R) Gold 6240R CPU @ 2.40GHz
Total CPUs:      32 cores
Architecture:    x86_64
Sockets:         32
Threads/core:    1
NUMA nodes:      2 (0-15, 16-31)
```

### Memory Resources
**⚠️ To check, run on server:**
```bash
free -h              # Human-readable memory info
cat /proc/meminfo    # Detailed memory stats
```

### Storage
**⚠️ To check, run on server:**
```bash
df -h                # Disk space
df -i                # Inode usage
```

---

## 🎯 Current FastAPI Service Configuration

### Worker Configuration
```ini
Workers:              4
Worker Type:          uvicorn.workers.UvicornWorker
Timeout:              60 seconds
Bind Address:         0.0.0.0:8001
```

### Resource Utilization (Current)

| Resource | Allocated | Total Available | Utilization % |
|----------|-----------|-----------------|---------------|
| **CPU Cores** | 4 | 32 | **12.5%** |
| **Workers** | 4 | ~30 max | **13.3%** |
| **Memory** | ~1-2 GB | TBD | TBD |

---

## 💾 Memory Management Analysis

### Per-Worker Memory Breakdown

Each Gunicorn+Uvicorn worker typically uses:

| Component | Memory Usage |
|-----------|--------------|
| **Python Interpreter** | ~50-100 MB |
| **FastAPI Framework** | ~20-30 MB |
| **Loaded Models/Pipeline** | ~100-300 MB |
| **Request Processing** | ~50-200 MB |
| **OS Overhead** | ~20-50 MB |
| **Total per Worker** | ~250-500 MB |

### Memory Calculation by Worker Count

| Workers | Base Memory | Processing Peak | Total Estimated |
|---------|-------------|-----------------|-----------------|
| **4** | 1-2 GB | 2-3 GB | **~2-3 GB** |
| **8** | 2-4 GB | 4-6 GB | **~4-6 GB** |
| **16** | 4-8 GB | 8-12 GB | **~8-12 GB** |
| **24** | 6-12 GB | 12-18 GB | **~12-18 GB** |
| **32** | 8-16 GB | 16-24 GB | **~16-24 GB** |

> **Note**: Peak memory occurs when all workers process documents simultaneously

---

## 📈 Current vs Optimized Capacity

### Throughput Comparison (15 sec avg per document)

| Configuration | Workers | Simultaneous | Per Minute | Per Hour | Per Day | Per Month |
|---------------|---------|--------------|------------|----------|---------|-----------|
| **Current** | 4 | 4 | 16 | 960 | 23,040 | 691,200 |
| **Conservative** | 16 | 16 | 64 | 3,840 | 92,160 | 2,764,800 |
| **Balanced** | 24 | 24 | 96 | 5,760 | 138,240 | 4,147,200 |
| **Maximum** | 30 | 30 | 120 | 7,200 | 172,800 | 5,184,000 |

### Performance Scaling

```
Current (4 workers):   ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  12.5% CPU
Conservative (16):     ████████████████░░░░░░░░░░░░░░░░  50% CPU
Balanced (24):         ████████████████████████░░░░░░░░  75% CPU
Maximum (30):          ██████████████████████████████░░  94% CPU
```

---

## 🔍 Resource Monitoring Commands

### CPU Monitoring

```bash
# Real-time CPU usage per process
htop

# Top CPU consumers
top -b -n 1 | head -20

# Gunicorn worker CPU usage
ps aux | grep gunicorn

# Average CPU load
uptime
```

### Memory Monitoring

```bash
# Overall memory status
free -h

# Detailed memory info
cat /proc/meminfo | grep -E 'MemTotal|MemFree|MemAvailable|Cached'

# Per-process memory
ps aux --sort=-%mem | head -20

# FastAPI service memory
ps aux | grep gunicorn | awk '{sum+=$6} END {print "Total RSS: " sum/1024 " MB"}'
```

### Disk I/O Monitoring

```bash
# Disk usage
df -h

# I/O statistics
iostat -x 1 5

# Active I/O processes
iotop
```

### Network Monitoring

```bash
# Network connections
ss -tunap | grep :8001

# Bandwidth usage
iftop

# Connection count
netstat -an | grep :8001 | wc -l
```

---

## ⚠️ Memory Management Strategies

### 1. **Prevent Memory Leaks**

#### Current Code Review
Your [main.py](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/main.py) already handles this well:

```python
# ✅ GOOD: Temp file cleanup in finally block
finally:
    try:
        os.unlink(tmp_path)  # Always deletes temp file
    except Exception:
        pass
```

#### Recommendations

**Add memory limits to workers:**
```bash
# In systemd service
[Service]
MemoryMax=1G          # Kill worker if exceeds 1GB
MemoryHigh=800M       # Start throttling at 800MB
```

**Worker restart strategy:**
```bash
# Restart workers after N requests (prevents memory buildup)
gunicorn main:app \
    --workers 24 \
    --max-requests 1000 \        # Restart after 1000 requests
    --max-requests-jitter 50     # Add randomness
```

### 2. **Optimize File Handling**

```python
# Instead of loading entire file into memory
with tempfile.NamedTemporaryFile(delete=False) as tmp:
    content = await file.read()  # ⚠️ Loads entire file
    tmp.write(content)

# Better: Stream large files
async with aiofiles.open(tmp_path, 'wb') as f:
    while chunk := await file.read(8192):  # 8KB chunks
        await f.write(chunk)
```

### 3. **Limit Upload Size**

Add to [main.py](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/main.py):

```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

app = FastAPI()

# Limit upload size to 50MB
@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 50_000_000:  # 50MB
            raise HTTPException(413, "File too large")
    return await call_next(request)
```

### 4. **Garbage Collection**

```python
import gc

@app.on_event("startup")
async def configure_gc():
    # Tune garbage collection for better memory handling
    gc.set_threshold(700, 10, 10)  # More aggressive GC
```

---

## 📊 Recommended Configuration

### Optimal Setup (assuming 64GB+ RAM)

**Update systemd service to:**

```ini
[Service]
Type=simple
User=rb_admin2
WorkingDirectory=/home/rb_admin2/apps/fastapi-service
Environment="PATH=/home/rb_admin2/apps/fastapi-service/.venv/bin"

# Memory management
MemoryMax=20G
MemoryHigh=16G

# Optimized worker config
ExecStart=/home/rb_admin2/apps/fastapi-service/.venv/bin/gunicorn main:app \
    --workers 24 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8001 \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --worker-tmp-dir /dev/shm \
    --access-logfile /var/log/rb-ocr-api/access.log \
    --error-logfile /var/log/rb-ocr-api/error.log \
    --log-level info

Restart=always
RestartSec=10
```

### Key Changes Explained

| Setting | Value | Reason |
|---------|-------|--------|
| `--workers 24` | 24 | Use 75% of 32 CPUs |
| `--timeout 120` | 120s | Allow time for large PDFs |
| `--max-requests 1000` | 1000 | Restart worker after 1000 reqs (prevent leaks) |
| `--max-requests-jitter 100` | 100 | Randomize restart (avoid all workers restarting together) |
| `--worker-tmp-dir /dev/shm` | RAM disk | Faster temp file operations |
| `MemoryMax=20G` | 20GB | Hard limit per service |
| `MemoryHigh=16G` | 16GB | Start throttling warning |

---

## 🎯 Disk I/O Optimization

### Current Temp File Strategy

```python
# Your current approach
with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
    # Uses /tmp by default (usually on disk)
```

### Optimized: Use RAM Disk

```python
import tempfile
import os

# Set temp directory to RAM disk
os.environ['TMPDIR'] = '/dev/shm'

# Now all temp files go to RAM (much faster)
with tempfile.NamedTemporaryFile(delete=False) as tmp:
    # This now uses RAM instead of disk
```

### Benefits
- **10-100x faster** file I/O
- Reduces disk wear
- Better for concurrent operations
- Auto-cleared on reboot

### Gunicorn Config
```bash
--worker-tmp-dir /dev/shm  # Use RAM disk for workers
```

---

## 📈 Load Testing & Benchmarking

### Test Current Capacity

```bash
# Install Apache Bench
sudo apt install apache2-utils

# Test with 100 requests, 4 concurrent
ab -n 100 -c 4 -p test.pdf -T 'multipart/form-data' \
   http://localhost:8001/v1/verify

# Load test with locust
pip install locust
```

### Example Locust Test

Create `locustfile.py`:

```python
from locust import HttpUser, task, between

class DocumentVerificationUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def verify_document(self):
        files = {'file': open('test.pdf', 'rb')}
        data = {'fio': 'Тест Тестов Тестович'}
        self.client.post("/v1/verify", files=files, data=data)
```

Run:
```bash
locust -f locustfile.py --host=http://localhost:8001
# Visit http://localhost:8089 for UI
```

---

## 🚨 Alerts & Monitoring Thresholds

### Set Up Monitoring

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| **CPU Usage** | > 80% | > 95% | Check if workers need adjustment |
| **Memory Usage** | > 70% | > 90% | Reduce workers or add RAM |
| **Worker Restarts** | > 5/hour | > 20/hour | Check for crashes/OOM |
| **Queue Depth** | > 10 | > 50 | Increase workers |
| **Response Time** | > 30s | > 60s | Check pipeline performance |
| **Error Rate** | > 1% | > 5% | Review logs immediately |

### Monitoring Script

Create `/home/rb_admin2/apps/fastapi-service/monitor.sh`:

```bash
#!/bin/bash

echo "=== FastAPI Service Health Check ==="
echo "Time: $(date)"
echo ""

# Worker count
WORKERS=$(ps aux | grep gunicorn | grep -v grep | wc -l)
echo "Active Workers: $WORKERS"

# CPU usage
CPU=$(ps aux | grep gunicorn | awk '{sum+=$3} END {print sum}')
echo "Total CPU: ${CPU}%"

# Memory usage
MEM=$(ps aux | grep gunicorn | awk '{sum+=$6} END {print sum/1024}')
echo "Total Memory: ${MEM} MB"

# Request count (from logs)
REQUESTS=$(tail -1000 /var/log/rb-ocr-api/access.log | wc -l)
echo "Recent Requests (last 1000): $REQUESTS"

# Error rate
ERRORS=$(tail -1000 /var/log/rb-ocr-api/error.log | grep ERROR | wc -l)
echo "Recent Errors: $ERRORS"

# Service status
systemctl is-active rb-ocr-fastapi
```

Run every 5 minutes via cron:
```bash
*/5 * * * * /home/rb_admin2/apps/fastapi-service/monitor.sh >> /var/log/rb-ocr-api/health.log
```

---

## 🎯 Action Items Checklist

### Immediate Actions

- [ ] Check available RAM: `free -h`
- [ ] Check disk space: `df -h`
- [ ] Monitor current memory usage: `ps aux | grep gunicorn`
- [ ] Review current error logs: `tail -100 /var/log/rb-ocr-api/error.log`

### Short-term Optimization (This Week)

- [ ] Increase workers from 4 to 16-24 (based on RAM availability)
- [ ] Add `max-requests` to prevent memory leaks
- [ ] Configure RAM disk for temp files (`/dev/shm`)
- [ ] Add upload size limits
- [ ] Set up basic monitoring script

### Long-term Improvements (This Month)

- [ ] Implement streaming file upload for large files
- [ ] Add memory limits in systemd service
- [ ] Set up proper monitoring/alerting (Prometheus + Grafana)
- [ ] Load test with different worker counts
- [ ] Optimize pipeline code for memory efficiency
- [ ] Consider Redis for request queuing if needed

---

## 📋 Quick Reference Commands

```bash
# Check current service config
systemctl cat rb-ocr-fastapi

# View worker processes
ps aux | grep gunicorn

# Real-time resource monitoring
htop -p $(pgrep -d',' gunicorn)

# Memory usage of service
systemctl status rb-ocr-fastapi | grep Memory

# Restart with new config
sudo systemctl daemon-reload
sudo systemctl restart rb-ocr-fastapi

# Watch logs
sudo journalctl -u rb-ocr-fastapi -f

# Check if workers are recycling properly
watch 'ps aux | grep gunicorn'
```

---

## 🎓 Understanding Resource Limits

### How Much RAM Do You Need?

**Formula**: 
```
Required RAM = (Workers × Memory per Worker) + System Overhead + Buffer

Example:
24 workers × 500MB = 12GB
System overhead      = 2GB
Buffer (20%)         = 3GB
Total               ≈ 17GB recommended minimum
                     (20-24GB safe for 24 workers)
```

### Bottleneck Analysis

**If CPU at 100%, Memory OK**: ✅ Increase workers  
**If Memory at 90%, CPU OK**: ⚠️ Reduce workers or add RAM  
**If Both high**: 🔴 At capacity, need more hardware  
**If Both low, slow responses**: 🔍 Check pipeline/network/disk I/O

---

## 📞 Support & Troubleshooting

### Common Issues

**1. Out of Memory (OOM) Kills**
```bash
# Check OOM logs
dmesg | grep -i "killed process"

# Solution: Reduce workers or add MemoryMax limit
```

**2. Workers Keep Restarting**
```bash
# Check why
sudo journalctl -u rb-ocr-fastapi | grep -i error

# Solutions: Fix bugs, increase timeout, add max-requests
```

**3. Slow Performance**
```bash
# Check what's slow
time curl -X POST http://localhost:8001/v1/verify ...

# Profile pipeline code for bottlenecks
```

---

> **Next Steps**: Run the immediate action items to get baseline metrics, then optimize based on actual usage patterns.
