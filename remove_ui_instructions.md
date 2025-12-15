# Removing UI from Docker Deployment

Since you only need the backend service for **rb-ocr**, follow these steps to remove the UI component from your Docker configuration.

## 1. Modify `docker-compose.yml`

You need to remove the `ui` service definition from your `docker-compose.yml` file.

**Current File:**
```yaml
services:
  backend:
    ...
  ui:  <-- Remove from here down to the end of the file
    build: ./ui
    platform: linux/amd64
    image: rb-ocr-ui:latest
    ...
```

**New `docker-compose.yml` Content:**
```yaml
services:
  backend:
    build: ./fastapi-service
    platform: linux/amd64
    image: rb-ocr-backend:latest
    container_name: rb-ocr-backend
    restart: always
    ports:
      - "8000:8000"
    volumes:
      - ./runs:/app/runs
    environment:
      - TZ=Asia/Almaty
      - DB_HOST=10.0.94.227
      - DB_PORT=5432
      - DB_NAME=rbocrdb
      - DB_USER=rbocruser
      - DB_PASSWORD=rbocruserDEV
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## 2. Apply Changes

Run the following command to update your running services. The `--remove-orphans` flag is critical as it shuts down and removes containers not defined in the compose file (e.g., the UI container).

```bash
docker compose up -d --remove-orphans
```

## 3. Clean Setup (Optional)

If you want to completely clean up the old UI image to save space:

```bash
# Stop all containers
docker compose down

# Remove the UI image
docker rmi rb-ocr-ui:latest

# Start backend only
docker compose up -d
```

## 4. Verify

Check that only the backend is running:

```bash
docker ps
```
You should only see `rb-ocr-backend`.
