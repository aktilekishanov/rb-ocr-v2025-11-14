# Python Virtual Environment Setup Issue - Troubleshooting Report

**Date**: 2025-11-28  
**Server**: rb-ocr-dev-app-uv01  
**Issue**: Unable to create Python virtual environment on offline Ubuntu server  
**Status**: ✅ RESOLVED

---

## Executive Summary

Attempted to create a Python virtual environment on an offline Ubuntu server but encountered errors due to missing system packages (`python3-venv`) and pip bootstrap wheels. Successfully resolved by copying required files from a working server to the new server.

---

## Problem Description

### Initial Error

When attempting to create a virtual environment:

```bash
cd ~/rb-loan-deferment-idp/fastapi-service
python3 -m venv venv
```

**Error Message**:
```
The virtual environment was not created successfully because ensurepip is not
available.  On Debian/Ubuntu systems, you need to install the python3-venv
package using the following command.

    apt install python3.11-venv

You may need to use sudo with that command.  After installing the python3-venv
package, recreate your virtual environment.

Failing command: /home/rb_admin/rb-loan-deferment-idp/fastapi-service/venv/bin/python3
```

### Secondary Error (After Copying ensurepip)

After copying the `ensurepip` module, a second error occurred:

```bash
python3 -m venv venv
```

**Error Message**:
```
Error: Command '['/home/rb_admin/rb-loan-deferment-idp/venv/bin/python3', '-m', 'ensurepip', '--upgrade', '--default-pip']' returned non-zero exit status 1.
```

---

## Root Cause Analysis

### Primary Cause: Missing `python3.11-venv` Package

Ubuntu/Debian systems do not include the `venv` module by default with Python installations. The `python3.11-venv` package must be installed separately.

**What was missing**:
- `/usr/lib/python3.11/ensurepip/` - Module for bootstrapping pip in virtual environments
- `/usr/share/doc/python3.11-venv/` - Documentation files
- `/usr/share/lintian/overrides/python3.11-venv` - Linting configuration

### Secondary Cause: Missing Pip Bootstrap Wheels

Even after installing the `ensurepip` module, the virtual environment creation failed because the pip and setuptools wheel files were missing.

**What was missing**:
- `/usr/share/python-wheels/pip-23.0.1-py3-none-any.whl` - Pip wheel for bootstrapping
- `/usr/share/python-wheels/setuptools-66.1.1-py3-none-any.whl` - Setuptools wheel for bootstrapping

### Why This Happened

The server has **no internet access**, so:
1. Cannot run `apt install python3.11-venv` (requires internet to download packages)
2. Cannot download pip wheels from PyPI during venv creation
3. Standard installation procedures don't work

---

## Solution Overview

Since the server is offline, we copied the required files from a working server (colleague's server: `cfo-prod-llm-uv01`) that had the same Ubuntu version and Python 3.11 installation.

### Solution Architecture

```
Working Server (cfo-prod-llm-uv01)
    ↓ (identify required files)
    ↓ (create tarball)
    ↓ (manual transfer via download/upload)
New Server (rb-ocr-dev-app-uv01)
    ↓ (extract to system directories)
    ✓ (venv creation successful)
```

---

## Complete Solution Steps

### Phase 1: Copy python3.11-venv Files

#### On Working Server (cfo-prod-llm-uv01)

```bash
# 1. Identify installed files
dpkg -L python3.11-venv

# Output showed:
# /usr/lib/python3.11/ensurepip
# /usr/share/lintian/overrides/python3.11-venv
# /usr/share/doc/python3.11-venv

# 2. Create tarball of these files
sudo tar -czf python3.11-venv-files.tar.gz \
  /usr/lib/python3.11/ensurepip \
  /usr/share/lintian/overrides/python3.11-venv \
  /usr/share/doc/python3.11-venv

# Note: Warning "Removing leading `/` from member names" is normal and expected

# 3. Verify tarball was created
ls -lh python3.11-venv-files.tar.gz
# Output: -rw-r--r-- 1 root root 9.7K Nov 28 14:33 python3.11-venv-files.tar.gz
```

#### Transfer to New Server

```bash
# Option A: Direct SCP (if network accessible)
scp python3.11-venv-files.tar.gz rb_admin@rb-ocr-dev-app-uv01:~/

# Option B: Manual transfer (used in this case due to connection issues)
# 1. Download from working server to local PC
# 2. Upload to new server
```

#### On New Server (rb-ocr-dev-app-uv01)

```bash
# 4. Verify file was transferred
ls -lh ~/python3.11-venv-files.tar.gz

# 5. Extract to system directories
cd ~
sudo tar -xzf python3.11-venv-files.tar.gz -C /

# 6. Verify extraction
ls -la /usr/lib/python3.11/ensurepip
# Should show: __init__.py, __main__.py, _uninstall.py, __pycache__

# 7. Test if venv module is available
python3 -m venv --help
# Should display help message without errors
```

### Phase 2: Copy Pip Bootstrap Wheels

#### On Working Server (cfo-prod-llm-uv01)

```bash
# 1. Identify pip wheel files
dpkg -L python3-pip-whl

# Output showed:
# /usr/share/python-wheels/pip-23.0.1-py3-none-any.whl

# 2. Check for other wheels in the directory
ls -lh /usr/share/python-wheels/

# Output:
# pip-23.0.1-py3-none-any.whl (1.7M)
# setuptools-66.1.1-py3-none-any.whl (1.3M)

# 3. Copy both wheels to home directory
cp /usr/share/python-wheels/pip-23.0.1-py3-none-any.whl ~/
cp /usr/share/python-wheels/setuptools-66.1.1-py3-none-any.whl ~/
```

#### Transfer to New Server

```bash
# Manual transfer (download from working server, upload to new server)
# Files transferred to: ~/rb-ocr-dev-app-uv01/
```

#### On New Server (rb-ocr-dev-app-uv01)

```bash
# 4. Create python-wheels directory
sudo mkdir -p /usr/share/python-wheels

# 5. Copy wheels to system directory
sudo cp ~/pip-23.0.1-py3-none-any.whl /usr/share/python-wheels/
sudo cp ~/setuptools-66.1.1-py3-none-any.whl /usr/share/python-wheels/

# 6. Verify wheels are in place
ls -lh /usr/share/python-wheels/

# Output:
# -rw-r--r-- 1 root root 1.7M Nov 28 14:56 pip-23.0.1-py3-none-any.whl
# -rw-r--r-- 1 root root 1.3M Nov 28 14:56 setuptools-66.1.1-py3-none-any.whl
```

### Phase 3: Create Virtual Environment

```bash
# 1. Navigate to project directory
cd ~/rb-loan-deferment-idp

# 2. Create virtual environment (should work now!)
python3 -m venv venv

# Success! No errors

# 3. Activate virtual environment
source venv/bin/activate

# 4. Verify activation
which python
# Output: /home/rb_admin/rb-loan-deferment-idp/venv/bin/python

# 5. Install dependencies from local wheels
pip install --no-index --find-links=./unified-wheels/core-server -r fastapi-service/requirements.txt

# Success! All packages installed:
# - fastapi-0.104.1
# - uvicorn-0.24.0
# - gunicorn-21.2.0
# - httpx-0.25.1
# - pydantic-2.5.0
# - pypdf-3.17.1
# - pillow-10.1.0
# - rapidfuzz-3.5.2
# - and all dependencies
```

### Phase 4: Test FastAPI Service

```bash
# 1. Navigate to service directory
cd fastapi-service

# 2. Run with Uvicorn (development mode)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 3. Test via Swagger UI
# Open browser: http://<server-ip>:8000/docs
# ✅ Service working properly!
```

---

## Files Transferred Summary

### From Working Server to New Server

| File | Size | Source Path | Destination Path |
|------|------|-------------|------------------|
| python3.11-venv-files.tar.gz | 9.7K | ~ | ~ |
| pip-23.0.1-py3-none-any.whl | 1.7M | ~ | /usr/share/python-wheels/ |
| setuptools-66.1.1-py3-none-any.whl | 1.3M | ~ | /usr/share/python-wheels/ |

### Extracted System Files

| File/Directory | Location |
|----------------|----------|
| ensurepip module | /usr/lib/python3.11/ensurepip/ |
| Documentation | /usr/share/doc/python3.11-venv/ |
| Linting overrides | /usr/share/lintian/overrides/python3.11-venv |
| Pip wheel | /usr/share/python-wheels/pip-23.0.1-py3-none-any.whl |
| Setuptools wheel | /usr/share/python-wheels/setuptools-66.1.1-py3-none-any.whl |

---

## Quick Reference: Complete Command List

### On Working Server (cfo-prod-llm-uv01)

```bash
# Create venv files tarball
sudo tar -czf python3.11-venv-files.tar.gz \
  /usr/lib/python3.11/ensurepip \
  /usr/share/lintian/overrides/python3.11-venv \
  /usr/share/doc/python3.11-venv

# Copy pip wheels
cp /usr/share/python-wheels/pip-23.0.1-py3-none-any.whl ~/
cp /usr/share/python-wheels/setuptools-66.1.1-py3-none-any.whl ~/

# Transfer files to new server (manual or scp)
```

### On New Server (rb-ocr-dev-app-uv01)

```bash
# Extract venv files
cd ~
sudo tar -xzf python3.11-venv-files.tar.gz -C /

# Create wheels directory and copy wheels
sudo mkdir -p /usr/share/python-wheels
sudo cp pip-23.0.1-py3-none-any.whl /usr/share/python-wheels/
sudo cp setuptools-66.1.1-py3-none-any.whl /usr/share/python-wheels/

# Create virtual environment
cd ~/rb-loan-deferment-idp
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --no-index --find-links=./unified-wheels/core-server -r fastapi-service/requirements.txt

# Run service
cd fastapi-service
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Key Learnings

### 1. Ubuntu/Debian Python venv Requirements

- `python3-venv` package is **NOT** included by default
- Must be installed separately via `apt install python3.11-venv`
- Contains the `ensurepip` module needed for pip bootstrapping

### 2. Offline Server Challenges

- Cannot use standard `apt install` commands
- Must manually transfer `.deb` packages or copy installed files
- Requires matching Ubuntu versions between source and destination servers

### 3. Virtual Environment Bootstrap Process

The venv creation process requires:
1. **ensurepip module** - Python module for bootstrapping pip
2. **pip wheel** - Pre-built pip package
3. **setuptools wheel** - Pre-built setuptools package

Without these, `python3 -m venv` will fail even if the venv module is available.

### 4. File Transfer Strategy

For offline servers:
- **Option A**: Transfer `.deb` packages and install with `dpkg -i`
- **Option B**: Copy installed files directly from working server (used in this case)
- Option B is simpler when both servers have identical OS/Python versions

---

## Prerequisites for This Solution

✅ Access to a working server with same Ubuntu version  
✅ Same Python version (3.11) on both servers  
✅ Ability to transfer files between servers (manual or scp)  
✅ Sudo access on new server  

---

## Verification Checklist

After completing the solution, verify:

- [ ] `python3 -m venv --help` displays help without errors
- [ ] `/usr/lib/python3.11/ensurepip/` directory exists
- [ ] `/usr/share/python-wheels/pip-*.whl` exists
- [ ] `/usr/share/python-wheels/setuptools-*.whl` exists
- [ ] `python3 -m venv venv` creates venv without errors
- [ ] `source venv/bin/activate` activates the environment
- [ ] `which python` shows venv python path
- [ ] `pip install` works with local wheels
- [ ] FastAPI service runs successfully

---

## Alternative Solutions (Not Used)

### If Server Had Internet Access

```bash
# Simple one-line solution
sudo apt update
sudo apt install python3.11-venv -y
```

### If Different Ubuntu Versions

Would need to:
1. Download matching `.deb` packages from Ubuntu repositories
2. Transfer and install with `dpkg -i`
3. Handle dependency resolution manually

---

## Troubleshooting Tips

### If venv creation still fails after copying files

1. **Check file permissions**:
   ```bash
   ls -la /usr/lib/python3.11/ensurepip/
   ls -la /usr/share/python-wheels/
   ```
   Files should be readable by all users.

2. **Verify Python version match**:
   ```bash
   python3 --version
   ```
   Must be Python 3.11.x on both servers.

3. **Check for missing dependencies**:
   ```bash
   python3 -m ensurepip --version
   ```

### If pip install fails

1. **Verify wheels directory**:
   ```bash
   ls -la unified-wheels/core-server/
   ```

2. **Check venv activation**:
   ```bash
   which python  # Should show venv path
   ```

3. **Try installing packages individually**:
   ```bash
   pip install --no-index --find-links=./unified-wheels/core-server fastapi
   ```

---

## Conclusion

Successfully resolved Python virtual environment creation issues on an offline Ubuntu server by:
1. Copying `python3.11-venv` package files from a working server
2. Copying pip and setuptools bootstrap wheels
3. Creating virtual environment in parent project directory
4. Installing all dependencies from local wheels

**Result**: FastAPI service now running successfully on the new server with all dependencies installed offline.

**Time to Resolution**: ~45 minutes  
**Files Transferred**: 3 (total ~3MB)  
**Packages Installed**: 27 Python packages  

---

## References

- Ubuntu Python venv documentation: https://docs.python.org/3/library/venv.html
- Debian python3-venv package: https://packages.debian.org/search?keywords=python3-venv
- Python ensurepip module: https://docs.python.org/3/library/ensurepip.html
