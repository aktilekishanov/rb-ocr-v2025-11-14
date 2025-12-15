# Database Connection Analysis

## 1. Current System Status

Based on the logs and environment files you provided, here is where your data is currently being inserted:

*   **Application Server:** `rb-ocr-dev-app-uv01`
    *   *Evidence:* The terminal prompt in your logs is `rb_admin@rb-ocr-dev-app-uv01`.
*   **Database Host:** `10.0.94.227`
*   **Database Port:** `5432`
*   **Database Name:** `rbocrdb`
*   **Database User:** `rbocruser`

**Log Evidence:**
The logs explicitly verify this connection during startup:
> `Creating database connection pool to 10.0.94.227:5432/rbocrdb`

And confirm successful insertion:
> `✅ DB INSERT SUCCESS on attempt 1/5 | run_id=... | status=success`

## 2. Steps to Change Database

To switch to a different database with new credentials, you need to update the **Environment Variables** passed to the backend container.

Since you are using `docker-compose.yml`, you should modify the `environment` section of the `backend` service in that file.

### File to Edit:
`apps/docker-compose.yml`

### Changes Required:

Locate the `backend` service and update the following lines with your NEW credentials:

```yaml
services:
  backend:
    ...
    environment:
      - TZ=Asia/Almaty
      - DB_HOST=<NEW_HOST_IP>      # Change this
      - DB_PORT=<NEW_PORT>         # Change this (usually 5432)
      - DB_NAME=<NEW_DB_NAME>      # Change this
      - DB_USER=<NEW_USER>         # Change this
      - DB_PASSWORD=<NEW_PASSWORD> # Change this
```

### Applying the Changes:

After saving the file, you must restart the container for the new environment variables to take effect:

```bash
docker compose up -d --force-recreate backend
```
