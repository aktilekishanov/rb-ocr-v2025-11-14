#!/bin/bash

# Define source and destination directories
SOURCE="wheels/wheels-backend/bulk_download"
BACKEND="wheels/wheels-backend"
UI="wheels/wheels-ui"

# Create directories if they don't exist
mkdir -p $BACKEND/{fastapi,pydantic,http,db,minio,pdf,image,utils}
mkdir -p $UI/{streamlit,data,image,http,utils}

echo "Organizing wheels from $SOURCE..."

# Function to move or copy wheels
# Usage: move_wheel "pattern" "destination" "keep_copy"
move_wheel() {
    pattern=$1
    dest=$2
    keep=$3
    
    # Find files matching pattern in source
    for file in $SOURCE/$pattern*.whl; do
        if [ -f "$file" ]; then
            if [ "$keep" = "true" ]; then
                cp "$file" "$dest/"
                echo "Copied $(basename "$file") to $dest"
            else
                mv "$file" "$dest/"
                echo "Moved $(basename "$file") to $dest"
            fi
        fi
    done
}

# --- SHARED DEPENDENCIES (Copy to both) ---
echo "Processing shared dependencies..."
# HTTP / Networking
move_wheel "requests" "$BACKEND/http" "true"
move_wheel "requests" "$UI/http" "false"

move_wheel "urllib3" "$BACKEND/http" "true"
move_wheel "urllib3" "$UI/http" "false"

move_wheel "certifi" "$BACKEND/http" "true"
move_wheel "certifi" "$UI/http" "false"

move_wheel "idna" "$BACKEND/http" "true"
move_wheel "idna" "$UI/http" "false"

move_wheel "charset_normalizer" "$BACKEND/http" "true"
move_wheel "charset_normalizer" "$UI/http" "false"

# Images
move_wheel "Pillow" "$BACKEND/image" "true"
move_wheel "Pillow" "$UI/image" "false"
move_wheel "pillow" "$BACKEND/image" "true" # Case insensitive check usually but glob is sensitive
move_wheel "pillow" "$UI/image" "false"

# Utils / Common
move_wheel "packaging" "$BACKEND/utils" "true"
move_wheel "packaging" "$UI/utils" "false"

move_wheel "typing_extensions" "$BACKEND/pydantic" "true"
move_wheel "typing_extensions" "$UI/utils" "false"

move_wheel "click" "$BACKEND/utils" "true"
move_wheel "click" "$UI/utils" "false"

move_wheel "pyyaml" "$BACKEND/utils" "true"
move_wheel "pyyaml" "$UI/utils" "false"

move_wheel "six" "$BACKEND/utils" "true"
move_wheel "six" "$UI/utils" "false"

move_wheel "markupsafe" "$BACKEND/utils" "true"
move_wheel "markupsafe" "$UI/utils" "false"

move_wheel "attrs" "$BACKEND/utils" "true"
move_wheel "attrs" "$UI/utils" "false"

move_wheel "protobuf" "$BACKEND/utils" "true"
move_wheel "protobuf" "$UI/utils" "false"

# --- BACKEND SPECIFIC ---
echo "Processing backend dependencies..."
move_wheel "fastapi" "$BACKEND/fastapi" "false"
move_wheel "uvicorn" "$BACKEND/fastapi" "false"
move_wheel "gunicorn" "$BACKEND/fastapi" "false"
move_wheel "starlette" "$BACKEND/fastapi" "false"
move_wheel "uvloop" "$BACKEND/fastapi" "false"
move_wheel "watchfiles" "$BACKEND/fastapi" "false"
move_wheel "websockets" "$BACKEND/fastapi" "false"
move_wheel "h11" "$BACKEND/fastapi" "false"
move_wheel "httptools" "$BACKEND/fastapi" "false"
move_wheel "python_multipart" "$BACKEND/fastapi" "false"

move_wheel "pydantic" "$BACKEND/pydantic" "false"
move_wheel "annotated_types" "$BACKEND/pydantic" "false"
move_wheel "pydantic_core" "$BACKEND/pydantic" "false"

move_wheel "httpx" "$BACKEND/http" "false"
move_wheel "httpcore" "$BACKEND/http" "false"
move_wheel "sniffio" "$BACKEND/http" "false"
move_wheel "anyio" "$BACKEND/http" "false"

move_wheel "asyncpg" "$BACKEND/db" "false"
move_wheel "async_timeout" "$BACKEND/db" "false"

move_wheel "minio" "$BACKEND/minio" "false"
move_wheel "argon2" "$BACKEND/minio" "false"
move_wheel "cffi" "$BACKEND/minio" "false"
move_wheel "pycparser" "$BACKEND/minio" "false"
move_wheel "pycryptodome" "$BACKEND/minio" "false"

move_wheel "pypdf" "$BACKEND/pdf" "false"

move_wheel "rapidfuzz" "$BACKEND/utils" "false"
move_wheel "python_dotenv" "$BACKEND/utils" "false"

# --- UI SPECIFIC ---
echo "Processing UI dependencies..."
move_wheel "streamlit" "$UI/streamlit" "false"
move_wheel "altair" "$UI/streamlit" "false"
move_wheel "blinker" "$UI/streamlit" "false"
move_wheel "cachetools" "$UI/streamlit" "false"
move_wheel "gitpython" "$UI/streamlit" "false"
move_wheel "gitdb" "$UI/streamlit" "false"
move_wheel "smmap" "$UI/streamlit" "false"
move_wheel "pydeck" "$UI/streamlit" "false"
move_wheel "tenacity" "$UI/streamlit" "false"
move_wheel "toml" "$UI/streamlit" "false"
move_wheel "tornado" "$UI/streamlit" "false"
move_wheel "watchdog" "$UI/streamlit" "false"
move_wheel "jinja2" "$UI/streamlit" "false"
move_wheel "jsonschema" "$UI/streamlit" "false"
move_wheel "referencing" "$UI/streamlit" "false"
move_wheel "rpds_py" "$UI/streamlit" "false"
move_wheel "narwhals" "$UI/streamlit" "false"
move_wheel "rich" "$UI/streamlit" "false"
move_wheel "validators" "$UI/streamlit" "false"
move_wheel "annotated_doc" "$UI/streamlit" "false"

move_wheel "pandas" "$UI/data" "false"
move_wheel "numpy" "$UI/data" "false"
move_wheel "pyarrow" "$UI/data" "false"
move_wheel "python_dateutil" "$UI/data" "false"
move_wheel "pytz" "$UI/data" "false"
move_wheel "tzdata" "$UI/data" "false"

echo "Cleanup empty bulk folder..."
rmdir $SOURCE 2>/dev/null || echo "Bulk folder not empty, keeping it."

echo "Organization complete!"
