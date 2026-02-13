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

# Copy application files
COPY app.py .
COPY session_manager.py .
COPY index.html .
COPY viewer.js .
COPY styles.css .

# Create necessary directories
RUN mkdir -p /app/uploads /app/cache

# Default port (can be overridden by PORT env var)
ENV PORT=8511

# Expose the application port
EXPOSE $PORT

# Health check (using Python's urllib - no extra dependencies needed)
# Note: Health checks don't support ENV substitution, so we check multiple ports
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os; from urllib.request import urlopen; port=os.getenv('PORT', '8511'); urlopen(f'http://localhost:{port}/docs', timeout=5)"

# Run the application
# Note: Using 0.0.0.0 to bind to all interfaces (required for Docker/Cloud Run)
# The PORT environment variable is automatically set by Cloud Run
CMD uvicorn app:app --host 0.0.0.0 --port $PORT
