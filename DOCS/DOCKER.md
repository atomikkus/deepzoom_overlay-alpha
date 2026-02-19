# Docker Deployment Guide

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Build and start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

The application will be available at `http://localhost:8511`

### Using Docker CLI

```bash
# Build the image
docker build -t wsi-viewer .

# Run the container
docker run -d -p 8511:8511 --name wsi-viewer wsi-viewer
```

## Authentication

The API requires authentication by default. See [AUTH.md](AUTH.md) for complete details.

**Default credentials:**
- Username: `admin`
- Password: `admin`

**Configure via environment variables:**

```bash
# Set custom credentials
docker run -d \
  -e AUTH_USERNAME=myuser \
  -e AUTH_PASSWORD=mypassword \
  -p 8511:8511 \
  wsi-viewer
```

**For production, use password hash:**

```bash
# Generate hash
python generate_password_hash.py

# Use in Docker
docker run -d \
  -e AUTH_USERNAME=produser \
  -e AUTH_PASSWORD_HASH='$2b$12$...' \
  -p 8511:8511 \
  wsi-viewer
```

**Disable authentication (development only):**

```bash
docker run -d \
  -e AUTH_ENABLED=false \
  -p 8511:8511 \
  wsi-viewer
```

## Configuration Options

### 1. Local Files

Mount your local slides directory:

```bash
docker run -d \
  -p 8511:8511 \
  -v /path/to/your/slides:/app/slides \
  wsi-viewer \
  python app.py --slides-local /app/slides
```

Or with docker-compose:

```yaml
services:
  wsi-viewer:
    volumes:
      - /path/to/your/slides:/app/slides
    command: ["python", "app.py", "--slides-local", "/app/slides"]
```

### 2. GCS Files (Public Buckets)

```bash
docker run -d \
  -p 8511:8511 \
  wsi-viewer \
  python app.py --slides gs://your-bucket/path/
```

### 3. GCS Files (Private Buckets)

Mount your GCS credentials:

```bash
docker run -d \
  -p 8511:8511 \
  -v ~/.config/gcloud:/root/.config/gcloud:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/root/.config/gcloud/application_default_credentials.json \
  wsi-viewer \
  python app.py --slides gs://private-bucket/path/
```

Or use a service account key file:

```bash
docker run -d \
  -p 8511:8511 \
  -v /path/to/service-account.json:/app/gcs-key.json:ro \
  -e GCS_SERVICE_ACCOUNT_PATH=/app/gcs-key.json \
  wsi-viewer \
  python app.py --slides gs://private-bucket/path/
```

### 4. Multiple Paths

```bash
docker run -d \
  -p 8511:8511 \
  wsi-viewer \
  python app.py --slides \
    gs://bucket1/slide1.svs \
    gs://bucket2/slide2.svs \
    https://storage.googleapis.com/bucket3/slide3.svs
```

### 5. With Overlays

```bash
docker run -d \
  -p 8511:8511 \
  -v /path/to/slides:/app/slides \
  -v /path/to/overlays:/app/overlays \
  wsi-viewer \
  python app.py --slides-local /app/slides --overlay /app/overlays
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AUTH_ENABLED` | Enable/disable authentication | `true` |
| `AUTH_USERNAME` | API username | `admin` |
| `AUTH_PASSWORD` | API password (dev only) | `admin` |
| `AUTH_PASSWORD_HASH` | API password hash (production) | None |
| `GCS_SERVICE_ACCOUNT_PATH` | Path to GCS service account JSON | None |
| `GOOGLE_APPLICATION_CREDENTIALS` | Google Cloud credentials path | None |
| `SESSION_TTL` | Session timeout in minutes | 30 |

## Volume Mounts

| Container Path | Purpose | Recommended |
|----------------|---------|-------------|
| `/app/uploads` | Default local slides directory | Yes |
| `/app/overlays` | Overlay files directory | Optional |
| `/app/cache` | Cache directory (future use) | Optional |

## Docker Compose Examples

### Example 1: Local Slides Only

```yaml
version: '3.8'
services:
  wsi-viewer:
    build: .
    ports:
      - "8511:8511"
    volumes:
      - ./my-slides:/app/slides
    command: ["python", "app.py", "--slides-local", "/app/slides"]
    restart: unless-stopped
```

### Example 2: GCS with Private Bucket

```yaml
version: '3.8'
services:
  wsi-viewer:
    build: .
    ports:
      - "8511:8511"
    volumes:
      - ./gcs-credentials.json:/app/gcs-key.json:ro
    environment:
      - GCS_SERVICE_ACCOUNT_PATH=/app/gcs-key.json
    command: ["python", "app.py", "--slides", "gs://private-bucket/slides/"]
    restart: unless-stopped
```

### Example 3: Mixed Sources

```yaml
version: '3.8'
services:
  wsi-viewer:
    build: .
    ports:
      - "8511:8511"
    volumes:
      - ./local-slides:/app/local
      - ./overlays:/app/overlays
    command: 
      - python
      - app.py
      - --slides
      - gs://public-bucket/remote-slide.svs
      - --slides-local
      - /app/local
      - --overlay
      - /app/overlays
    restart: unless-stopped
```

## Production Deployment

### Security Considerations

1. **Use secrets management** for GCS credentials:
   ```yaml
   secrets:
     gcs_key:
       file: ./gcs-key.json
   services:
     wsi-viewer:
       secrets:
         - gcs_key
       environment:
         - GCS_SERVICE_ACCOUNT_PATH=/run/secrets/gcs_key
   ```

2. **Run as non-root user** (update Dockerfile):
   ```dockerfile
   RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
   USER appuser
   ```

3. **Use HTTPS** with a reverse proxy (nginx/traefik)

4. **Set resource limits**:
   ```yaml
   services:
     wsi-viewer:
       deploy:
         resources:
           limits:
             cpus: '2'
             memory: 4G
           reservations:
             cpus: '1'
             memory: 2G
   ```

### With Nginx Reverse Proxy

```yaml
version: '3.8'

services:
  wsi-viewer:
    build: .
    expose:
      - "8511"
    # ... other config ...

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - wsi-viewer
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker logs wsi-viewer

# Check if port is already in use
netstat -an | grep 8511
```

### Cannot access from host
```bash
# Verify container is running
docker ps

# Check port mapping
docker port wsi-viewer

# Access from inside container
docker exec -it wsi-viewer curl http://localhost:8511/docs
```

### GCS authentication issues
```bash
# Verify credentials are mounted
docker exec -it wsi-viewer ls -la /app/gcs-key.json

# Test GCS access
docker exec -it wsi-viewer python -c "from google.cloud import storage; print(storage.Client())"
```

### Performance issues with large files
```bash
# Increase container memory
docker run -m 8g ...

# Or in docker-compose.yml:
services:
  wsi-viewer:
    mem_limit: 8g
```

## Building for Different Platforms

```bash
# For ARM64 (e.g., Apple M1/M2)
docker buildx build --platform linux/arm64 -t wsi-viewer:arm64 .

# For AMD64
docker buildx build --platform linux/amd64 -t wsi-viewer:amd64 .

# Multi-platform
docker buildx build --platform linux/amd64,linux/arm64 -t wsi-viewer:latest .
```
