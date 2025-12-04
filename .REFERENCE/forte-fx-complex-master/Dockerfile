# Stage 1: Base build stage
FROM python:3.13-slim-amd64 AS builder

# Create the app directory
RUN mkdir /app

# Set the working directory
WORKDIR /app

# Set environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HTTP_PROXY=http://headproxy03.fortebank.com:8080
ENV http_proxy=http://headproxy03.fortebank.com:8080
ENV ftp_proxy=http://headproxy03.fortebank.com:8080

RUN rm -f /etc/apt/sources.list.d/debian.sources
RUN echo "deb http://mirror.ps.kz/debian bookworm main contrib non-free" > /etc/apt/sources.list && \
    echo "deb http://mirror.ps.kz/debian bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
    apt-get update
RUN apt-get update && apt-get install --no-install-suggests --no-install-recommends --yes \
    libgl1-mesa-glx \
    libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    tesseract-ocr-kaz \
    tesseract-ocr-rus \
    tesseract-ocr-eng

# Upgrade pip and install dependencies
RUN pip config set global.proxy $HTTP_PROXY
RUN pip install --upgrade pip

# Copy the requirements file first (better caching)
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Production stage
FROM python:3.13-slim-amd64

RUN useradd -m -r appuser && \
   mkdir /src && \
   chown -R appuser /src

# Copy the Python dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /usr/lib/x86_64-linux-gnu/ /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/bin/pdfinfo /usr/bin/pdfinfo
COPY --from=builder /usr/bin/pdftoppm /usr/bin/pdftoppm
COPY --from=builder /usr/bin/tesseract /usr/bin/tesseract
COPY --from=builder /usr/share/tesseract-ocr/ /usr/share/tesseract-ocr/

# Set the working directory
WORKDIR /src

# Copy application code
COPY --chown=appuser:appuser . .

# Set environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2 \
    MALLOC_TRIM_THRESHOLD_=131072

# Switch to non-root user
USER appuser

# Expose the application port
EXPOSE 8000


# Start the application using Gunicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]