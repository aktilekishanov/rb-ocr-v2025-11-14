# 🧪 Load Testing Guide

Test your FastAPI service capacity with concurrent requests.

---

## 📁 Setup

### 1. Create Test Directory

```bash
mkdir -p sample-docs
```

### 2. Add Test Files

Put 20 PDF or image files in `sample-docs/`:

```bash
# Copy some test files
cp /path/to/test1.pdf sample-docs/
cp /path/to/test2.pdf sample-docs/
# ... add 20 files total
```

Or create dummy PDFs for testing:
```bash
# Install imagemagick if needed
# macOS: brew install imagemagick
# Ubuntu: sudo apt install imagemagick

# Create 20 dummy PDFs
for i in {1..20}; do
    convert -size 800x600 xc:white -pointsize 30 \
        -draw "text 300,300 'Test Document $i'" \
        "sample-docs/test_$i.pdf"
done
```

---

## 🐍 Python Version (Recommended)

### Install Dependencies

```bash
pip install httpx
```

### Run Load Test

```bash
# Basic usage (20 files in sample-docs/)
python load_test.py

# Custom directory
python load_test.py --dir /path/to/docs

# Custom URL (for remote server)
python load_test.py --url http://10.0.97.164:8001/v1/verify

# Limit number of files
python load_test.py --max-files 10

# All options
python load_test.py \
    --dir sample-docs \
    --url http://localhost:8001/v1/verify \
    --fio "Тестов Тест Тестович" \
    --max-files 20
```

### Output Example

```
======================================================================
🚀 LOAD TEST STARTING
======================================================================
Directory:    sample-docs
Files found:  20
Target URL:   http://localhost:8001/v1/verify
FIO:          Иванов Иван Иванович
======================================================================

⏱️  Starting all 20 requests at once...

📤 Request  1: Sending test_1.pdf...
📤 Request  2: Sending test_2.pdf...
...
✅ Request  1: Success! Verdict=True Time=15.23s ProcessTime=15.10s
✅ Request  2: Success! Verdict=True Time=15.45s ProcessTime=15.22s
✅ Request  3: Success! Verdict=True Time=16.01s ProcessTime=15.89s
✅ Request  4: Success! Verdict=True Time=16.33s ProcessTime=16.11s
✅ Request  5: Success! Verdict=True Time=30.12s ProcessTime=15.45s  ← Waited in queue
...

======================================================================
📊 LOAD TEST SUMMARY
======================================================================
Total requests:   20
Total time:       75.34s
✅ Successful:     20
❌ Errors:         0
💥 Exceptions:     0

⏱️  Timing (wall clock):
   Min:  15.23s    ← First 4 processed immediately
   Max:  75.12s    ← Last 4 waited longest
   Avg:  45.67s

⚙️  Processing time (server-side):
   Avg:  15.34s    ← Actual processing is consistent
======================================================================

💾 Results saved to: sample-docs/load_test_results.json
```

---

## 🐚 Bash Version (Simple Alternative)

### Run Load Test

```bash
# Make executable
chmod +x load_test.sh

# Basic usage
./load_test.sh

# Custom directory and URL
./load_test.sh sample-docs http://localhost:8001/v1/verify "Иванов Иван Иванович"
```

---

## 📊 Understanding Results

### With 4 Workers

**Expected behavior:**
- Requests 1-4: Process immediately (~15s each)
- Requests 5-8: Wait ~15s in queue, then process (~30s total)
- Requests 9-12: Wait ~30s in queue, then process (~45s total)
- Requests 13-16: Wait ~45s in queue, then process (~60s total)
- Requests 17-20: Wait ~60s in queue, then process (~75s total)

**Key metrics to watch:**
- **Min time**: Should be ~15s (first batch, no queue)
- **Max time**: Should be ~75s (last batch, max queue time)
- **Total time**: Should be ~75s (all 20 finish by then)

### With 24 Workers

**Expected behavior:**
- All 20 requests: Process simultaneously (~15s each)

**Key metrics:**
- **Min time**: ~15s
- **Max time**: ~17s (slight variation)
- **Total time**: ~17s (all finish together)

---

## 🎯 What to Test

### 1. Current Capacity (4 workers)

```bash
python load_test.py --max-files 20
```

Should see:
- ✅ All requests succeed
- ⏱️ Last requests take 60-75s total
- 📊 Clear batching pattern

### 2. Queue Behavior

```bash
python load_test.py --max-files 50
```

Should see:
- ✅ All queued properly
- ⚠️ Some might timeout if > 60s total wait

### 3. After Optimization (24 workers)

```bash
# After increasing workers to 24
python load_test.py --max-files 24
```

Should see:
- ✅ All process simultaneously
- ⏱️ All finish in ~15-20s
- 📊 No queue waiting

---

## 🔍 Analyzing Results

### JSON Output

Results are saved to `sample-docs/load_test_results.json`:

```json
{
  "summary": {
    "total_requests": 20,
    "total_time": 75.34,
    "successful": 20,
    "errors": 0,
    "exceptions": 0
  },
  "results": [
    {
      "request_num": 1,
      "file": "test_1.pdf",
      "status": "success",
      "verdict": true,
      "elapsed_time": 15.23,
      "processing_time": 15.10,
      "run_id": "20251127_132900_abc123"
    },
    ...
  ]
}
```

### Plot Results (Optional)

```python
import json
import matplotlib.pyplot as plt

with open('sample-docs/load_test_results.json') as f:
    data = json.load(f)

results = data['results']
success = [r for r in results if r['status'] == 'success']

# Plot elapsed time vs request number
plt.figure(figsize=(12, 6))
plt.plot([r['request_num'] for r in success], 
         [r['elapsed_time'] for r in success], 
         'o-', label='Elapsed Time')
plt.plot([r['request_num'] for r in success], 
         [r['processing_time'] for r in success], 
         'o-', label='Processing Time')
plt.xlabel('Request Number')
plt.ylabel('Time (seconds)')
plt.title('Load Test Results - 4 Workers')
plt.legend()
plt.grid()
plt.savefig('load_test_plot.png')
```

---

## ⚠️ Troubleshooting

### Connection Refused
```
💥 Request 1: Exception! Connection refused
```

**Fix**: Make sure service is running
```bash
sudo systemctl status rb-ocr-fastapi
```

### Timeout Errors
```
💥 Request 20: Exception! Timeout
```

**Fix**: Increase timeout in script or reduce number of concurrent requests

### All Fail with 500
```
❌ Request 1: Failed! Status=500
```

**Fix**: Check server logs
```bash
sudo journalctl -u rb-ocr-fastapi -n 100
```

---

## 🎓 Next Steps

1. **Test current config** (4 workers)
2. **Increase workers** to 16-24
3. **Re-test** to see improvement
4. **Compare results** before/after

**Expected improvement:**
- 4 workers: 20 requests in ~75s
- 24 workers: 20 requests in ~20s
- **3-4x faster!** 🚀
