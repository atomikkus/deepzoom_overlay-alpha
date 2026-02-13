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

# Expose the application port
EXPOSE 8511

# Health check (using Python's urllib - no extra dependencies needed)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8511/docs', timeout=5)"

# Run the application
# Note: Using 0.0.0.0 to bind to all interfaces (required for Docker)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8511"]
