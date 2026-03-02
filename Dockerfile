# Multi-stage build for WSI Viewer Application
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies (if needed for any Python packages)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files (do not copy integrate_config.json — use env vars in deployment)
COPY app.py .
COPY session_manager.py .
COPY index.html .
COPY viewer.js .
COPY styles.css .
COPY logo.svg .

# Create necessary directories
RUN mkdir -p /app/uploads /app/cache

# Cloud Run sets PORT at runtime (default 8080); GKE can set it too
ENV PORT=8080
EXPOSE 8080

# Required at runtime when using protected APIs (create/list/delete sessions, GCS, etc.):
#   AUTH_USERNAME, AUTH_PASSWORD
# Optional — for create_session_pid (external API); use a URL reachable from the container, not localhost:
#   EXTERNAL_API_BASE_URL, EXTERNAL_API_EMAIL, EXTERNAL_API_PASSWORD
# Optional — public base URL for viewer; when set, create_session and create_session_pid responses include full_url:
#   VIEWER_PUBLIC_BASE_URL (e.g. https://viewer.example.com)

# Health check: use PORT so Cloud Run/GKE can probe correctly
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import os; from urllib.request import urlopen; port=os.environ.get('PORT','8080'); urlopen(f'http://localhost:{port}/health', timeout=5)"

# Run the application; PORT is read at runtime (Cloud Run injects it)
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
