# Database Migration Scripts

## Setup Instructions

### One-Time Table Creation

> **Note**: Server is offline - run setup from Docker container where asyncpg is pre-installed.

**Option 1: Run from running container**
```bash
# Find container name
docker ps

# Execute setup script
docker exec -it <container_name> python /app/db_setup.py
```

**Option 2: Run as one-off container**
```bash
# Using host network for DNS resolution
sudo docker run --rm --network host --entrypoint="" rb-ocr-backend:latest python /app/db_setup.py
```

**Expected Output:**
```
🔧 Connecting to 10.0.94.227:5432/rbocrdb...
✅ Connected successfully!

📋 Creating table 'verification_runs'...
✅ Table created!

🔍 Creating indexes...
  ✅ verification_runs_trace_id
  ✅ verification_runs_created_at
  ... (6 indexes total)

💬 Adding comments...
✅ Comments added!

📊 Table has 29 columns
📈 Current records: 0

🎉 Database setup complete!
```

---

## Scripts

### `create_db_table.py`
Creates the `verification_runs` table with:
- 29 columns for storing final.json data
- 6 indexes for query optimization
- Comments for documentation
- **Idempotent**: Safe to run multiple times

**Location in Docker image**: `/app/db_setup.py`

---

## Notes

- The script is copied into the Docker image during build (see Dockerfile)
- Uses IP address `10.0.94.227` instead of hostname for DNS compatibility
- All SQL statements use `IF NOT EXISTS` for idempotency
- No manual wheel installation needed - asyncpg bundled in image
