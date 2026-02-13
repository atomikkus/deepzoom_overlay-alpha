# WSI DeepZoom Viewer

A modern, high-performance web application for viewing Whole Slide Imaging (WSI) files with DeepZoom support. Session-based multi-tenant architecture with overlay support, GCS integration, and on-the-fly tile generation.

![WSI Viewer](https://img.shields.io/badge/status-ready-success)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![FastAPI](https://img.shields.io/badge/fastapi-0.109-green)

## ✨ Features

- 🔬 **Multi-Format Support**: Aperio (.svs), Hamamatsu (.ndpi), Leica (.scn), and more
- ⚡ **Flexible Viewing**: On-the-fly tile generation, optional pre-conversion, or direct GeoTIFF viewing
- 🎨 **Modern UI**: Dark theme with glassmorphism effects
- 📤 **Drag & Drop Upload**: Easy file upload with progress indication
- 🔍 **Interactive Viewer**: Zoom, pan, rotate, and fullscreen support using OpenSeadragon
- 📊 **Overlay Support**: Cancer density overlay with opacity control and metadata display
- 🔐 **Session-Based**: Multi-tenant with UUID tokens; each session has its own slides and overlay
- 🔒 **Authentication**: HTTP Basic Auth for API endpoints with configurable credentials
- ☁️ **GCS Integration**: Optional Google Cloud Storage for listing and downloading slides
- 📍 **Multiple Paths**: Support for multiple slide sources (local and GCS) in a single session
- 🐳 **Docker Ready**: Containerized deployment support

## 📋 Supported Formats

- **Aperio**: `.svs`, `.tif`
- **Hamamatsu**: `.vms`, `.vmu`, `.ndpi`
- **Leica**: `.scn`
- **MIRAX**: `.mrxs`
- **Philips**: `.tiff`
- **Sakura**: `.svslide`
- **Ventana**: `.bif`, `.tif`
- **Generic tiled TIFF**: `.tif`

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- OpenSlide library (see installation below)

### Installation

#### 1. Install OpenSlide Library

**macOS:**
```bash
brew install openslide
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install openslide-tools libopenslide-dev
```

**Windows:**
Download and install from: https://openslide.org/download/

#### 2. Install Python Dependencies

```bash
# Navigate to project directory
cd deepzoom_overlay-alpha

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate   # macOS/Linux
.\venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt
```

Or use the setup script:

```bash
chmod +x setup.sh
./setup.sh
```

### Running the Application

**Option A: Direct run**
```bash
python app.py
```

**Option B: Via run script**
```bash
./run.sh
```

**Option C: Via uvicorn (custom port)**
```bash
uvicorn app:app --host 0.0.0.0 --port 8009 --reload
```

The server starts at **http://localhost:8009** (default port 8009).

A default session is created at startup. Open: **http://localhost:8009/{token}/** (token shown in terminal).

### CLI Arguments

```bash
python app.py [OPTIONS]

Options:
  --slides PATH       Path to WSI slides directory or single slide file (default: uploads)
  --cache PATH        Path to DeepZoom tiles cache directory (default: cache)
  --overlay PATH      Path to overlay files directory (optional)
  --session-ttl N     Session TTL in minutes (default: 30)
```

## 📖 Usage

### 1. Session-Based Access

- **Default session**: Created automatically at startup; URL printed in terminal
- **Create new session**: `POST /api/sessions` with `{"slides": "/path/to/slides", "overlay": "/path/to/overlay"}`
- Each session has its own URL: `/{token}/`

### 2. Upload or Add Slides

- **Drag and drop** a WSI file onto the upload area, or
- **Click** the upload area to browse and select a file
- Supported extensions: `.svs`, `.tif`, `.tiff`, `.vms`, `.vmu`, `.ndpi`, `.scn`, `.mrxs`, `.svslide`, `.bif`

### 3. Viewing Options

- **Direct viewing**: GeoTIFF/tiled formats can be viewed without conversion
- **On-the-fly**: Tiles are generated on demand and cached
- **Pre-conversion**: Optional; convert via API for faster subsequent loads

### 4. Overlay Support

Place overlay files alongside slides or in `--overlay` directory:

- `{slide_name}_density.png` – Cancer density heatmap
- `{slide_name}_metadata.json` – Metadata
- `{slide_name}_grid.json` – Grid data

Use the "Show Cancer Density" button to toggle the overlay with opacity control.

### 5. GCS (Optional)

Configure `GCS_SERVICE_ACCOUNT_PATH` and `GCS_BUCKET_NAME` to use Google Cloud Storage:

- List files: `GET /api/gcs/files`
- Download: `POST /api/gcs/download?blob_path=...`
- Signed URLs: `GET /api/gcs/signed-url?blob_path=...`

## 🏗️ Architecture

### Backend (FastAPI + OpenSlide)

- **`app.py`**: FastAPI server with session-scoped endpoints
- **`session_manager.py`**: Multi-tenant session management with TTL
- **`converter.py`**: WSI to DeepZoom conversion and on-the-fly tile generation
- **`uploads/`**: Directory for uploaded WSI files
- **`cache/`**: Directory for cached DeepZoom tiles

### Frontend (HTML + JavaScript + OpenSeadragon)

- **`index.html`**: Main web interface
- **`styles.css`**: Dark theme styling
- **`viewer.js`**: OpenSeadragon integration, density overlay, GeoTIFF support

### API Endpoints

**Session (global)**
- `POST /api/sessions` – Create session
- `DELETE /api/sessions/{token}` – Delete session
- `POST /api/sessions/{token}/heartbeat` – Keep session alive
- `GET /api/sessions` – List active sessions

**Session-scoped** (prefix `/{token}/`)
- `GET /api/slides` – List slides
- `POST /api/upload` – Upload slide
- `POST /api/convert/{slide_name}` – Convert to DeepZoom
- `GET /api/info/{slide_name}` – Get metadata
- `GET /api/dynamic_dzi/{slide_name}.dzi` – DZI descriptor
- `GET /api/tiles/{slide_name}/{level}/{col}_{row}.{format}` – Serve tile
- `GET /api/raw_slides/{filename}` – Serve raw slide (range support)
- `GET /api/overlay-config/{slide_name}` – Overlay config
- `DELETE /api/delete/{slide_name}` – Delete slide

**GCS** (global, optional)
- `GET /api/gcs/files` – List GCS files
- `POST /api/gcs/download` – Download from GCS
- `GET /api/gcs/signed-url` – Get signed URL
- `GET /api/gcs/status` – Check GCS availability

## 🐳 Docker

```bash
docker build -t wsi-viewer .
docker run -p 8009:8009 -v $(pwd)/uploads:/app/uploads -v $(pwd)/cache:/app/cache wsi-viewer
```

## 📚 Documentation

- **[AUTH.md](AUTH.md)** - Authentication setup and configuration
- **[USAGE.md](USAGE.md)** - Usage guide and examples
- **[DOCKER.md](DOCKER.md)** - Docker deployment guide
- **[CLOUD_RUN.md](CLOUD_RUN.md)** - Google Cloud Run deployment guide
- **[GCS_ARCHITECTURE.md](GCS_ARCHITECTURE.md)** - GCS integration architecture

## ⚙️ Configuration

### Authentication

Default credentials (change in production!):
- Username: `admin`
- Password: `admin`

Configure via environment variables:
```bash
export AUTH_USERNAME=your_username
export AUTH_PASSWORD=your_password
# Or use password hash for production
export AUTH_PASSWORD_HASH='$2b$12$...'
```

See [AUTH.md](AUTH.md) for complete authentication guide.

### Application Settings

Edit `app.py` or use environment variables:

- **Authentication**: `AUTH_ENABLED`, `AUTH_USERNAME`, `AUTH_PASSWORD`, `AUTH_PASSWORD_HASH`
- **GCS**: `GCS_SERVICE_ACCOUNT_PATH`, `GCS_BUCKET_NAME`
- **Port**: Default 8511 (set in `app.py` or via uvicorn)
- **Session TTL**: `--session-ttl` (default: 30 minutes)

## 🔧 Troubleshooting

### OpenSlide Installation Issues (Windows)

1. Download OpenSlide Windows binaries from https://openslide.org/download/
2. Extract to a location (e.g., `C:\OpenSlide`)
3. Add the `bin` folder to PATH
4. Restart terminal/IDE

### Viewer Not Loading

- Check browser console for errors
- Ensure the slide path exists and is valid
- Verify network requests reach the server (default port 8009)

### GCS Not Working

- Ensure `google-cloud-storage` is installed
- Place service account JSON in project root (or set `GCS_SERVICE_ACCOUNT_PATH`)
- Check `GET /api/gcs/status` for diagnostics

## 📚 Technologies Used

- **Backend**: FastAPI, Uvicorn, OpenSlide, Pillow, google-cloud-storage
- **Frontend**: OpenSeadragon, GeoTIFF TileSource, Vanilla JavaScript, CSS3

## 🙏 Acknowledgments

- [OpenSlide](https://openslide.org/) – C library for reading WSI files
- [OpenSeadragon](https://openseadragon.github.io/) – JavaScript viewer for zoomable images
- [FastAPI](https://fastapi.tiangolo.com/) – Python web framework
