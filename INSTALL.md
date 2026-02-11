# WSI DeepZoom Viewer - Installation Guide (Ubuntu Server)

## Prerequisites

- Ubuntu 20.04 or later
- Python 3.8 or higher
- OpenSlide libraries

## Quick Installation

### 1. Install System Dependencies

```bash
# Update package list
sudo apt-get update

# Install Python and build tools
sudo apt-get install -y python3 python3-pip python3-venv

# Install OpenSlide libraries (required for openslide-python)
sudo apt-get install -y openslide-tools libopenslide-dev

# Install other dependencies
sudo apt-get install -y build-essential
```

### 2. Clone or Download the Project

```bash
# If using git
git clone <repository-url>
cd deepzoom_overlay

# Or extract from zip/tar
cd deepzoom_overlay
```

### 3. Run Setup Script

```bash
# Make setup script executable
chmod +x setup.sh

# Run setup
./setup.sh
```

The setup script will:
- Create a Python virtual environment
- Install all required Python packages
- Verify installation

### 4. Configure Google Cloud Storage (Optional)

If you want to use GCS features:

1. Place your GCS service account JSON file in the project root
2. Update `app.py` or set environment variables:
   ```bash
   export GCS_SERVICE_ACCOUNT_PATH="your-service-account.json"
   export GCS_BUCKET_NAME="your-bucket-name"
   ```

### 5. Run the Application

**Option A: Manual Start**
```bash
# Activate virtual environment
source venv/bin/activate

# Run the server
./run.sh
# Or directly:
uvicorn app:app --reload --port 8000
```

**Option B: Run as Systemd Service (Recommended for Production)**

See `SYSTEMD_SERVICE.md` for instructions on setting up as a systemd service.

## Access the Application

Once running, access the viewer at:
- **Local**: http://localhost:8000
- **Remote**: http://your-server-ip:8000

## Troubleshooting

### OpenSlide Installation Issues

If you get errors about OpenSlide:

```bash
# Check if OpenSlide is installed
openslide-show-properties --version

# If not found, install:
sudo apt-get install -y openslide-tools libopenslide-dev
```

### Port Already in Use

If port 8000 is already in use:

```bash
# Change port in run.sh or app.py
uvicorn app:app --reload --port 8001
```

### Permission Issues

```bash
# Make scripts executable
chmod +x setup.sh run.sh

# Ensure uploads and cache directories are writable
chmod 755 uploads cache
```

## Production Deployment

For production use:

1. Use a production WSGI server (Gunicorn with Uvicorn workers)
2. Set up reverse proxy (Nginx)
3. Configure SSL/TLS certificates
4. Set up firewall rules
5. Configure systemd service for auto-start

See `PRODUCTION.md` for detailed production setup instructions.

