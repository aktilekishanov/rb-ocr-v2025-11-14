# Implementation Plan: Remove entrypoint.sh

## Goal
Simplify the Docker deployment by removing the `entrypoint.sh` script and moving its logic directly into the `Dockerfile`. This reduces the number of files to manage and makes the startup command more explicit in the Docker configuration.

## 1. Analyze `entrypoint.sh`
The current `entrypoint.sh` performs two tasks:
1.  Sets `umask 0002` (for group-writable permissions).
2.  Executes `gunicorn` with specific arguments.

## 2. Update `fastapi-service/Dockerfile`
We will replace the `COPY` and `ENTRYPOINT` instructions with a direct `CMD`.

- **File:** `apps/fastapi-service/Dockerfile`
- **Changes:**
    - Remove `COPY entrypoint.sh /app/entrypoint.sh`
    - Remove `RUN chmod +x /app/entrypoint.sh`
    - Replace `ENTRYPOINT ["/app/entrypoint.sh"]` with:
      ```dockerfile
      # Set umask to 0002 globally for the shell
      # Note: Setting umask in Dockerfile RUN commands only affects that layer.
      # To persist it for the runtime CMD, we can wrap the CMD in /bin/bash -c
      
      CMD ["/bin/bash", "-c", "umask 0002 && exec gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 60 --access-logfile - --error-logfile -"]
      ```

## 3. Delete `entrypoint.sh`
Remove the now obsolete file.

- **File:** `apps/fastapi-service/entrypoint.sh`
- **Action:** Delete file.

## 4. Verification
- Rebuild the Docker image: `docker-compose build backend`
- Run the container: `docker-compose up backend`
- Verify the app starts correctly and permissions (umask) are respected (if critical).
