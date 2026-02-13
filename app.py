"""
WSI Viewer - FastAPI Backend
Session-based multi-tenant viewer with UUID tokens.
Each session has its own slides directory, overlay, and converter.
"""

import os
import argparse
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from session_manager import SessionManager, ALLOWED_EXTENSIONS, is_gcs_path


# Google Cloud Storage imports
try:
    from google.cloud import storage
    from google.oauth2 import service_account
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    print("Warning: google-cloud-storage not installed. GCS features disabled.")

# Initialize FastAPI app
app = FastAPI(
    title="WSI Viewer",
    description="Session-based whole slide imaging viewer",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Parse CLI arguments
parser = argparse.ArgumentParser(description="WSI Viewer Server")
parser.add_argument("--slides", type=str, default=None,
                    help="GCS path (gs://bucket/path or https://storage.googleapis.com/...)")
parser.add_argument("--slides-local", type=str, default=None,
                    help="Local path to WSI slides directory or single slide file")
parser.add_argument("--overlay", type=str, default=None,
                    help="Path to overlay files directory")
parser.add_argument("--session-ttl", type=int, default=30,
                    help="Session TTL in minutes (default: 30)")
args, unknown = parser.parse_known_args()

# Determine which slides source to use
if args.slides and args.slides_local:
    raise ValueError("Cannot specify both --slides and --slides-local")
if not args.slides and not args.slides_local:
    args.slides_local = "uploads"  # Default to local uploads

# Set the active slides path
slides_path = args.slides if args.slides else args.slides_local

# Initialize session manager (no cache dir needed without conversion)
session_mgr = SessionManager(ttl_minutes=args.session_ttl)

# GCS setup
GCS_SERVICE_ACCOUNT_PATH = os.getenv('GCS_SERVICE_ACCOUNT_PATH',
                                      'in-4bc-engineering-1f84a3a8a86d-read-access.json')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'wsi_bucket53')
gcs_client = None

if GCS_AVAILABLE:
    if os.path.exists(GCS_SERVICE_ACCOUNT_PATH):
        try:
            credentials = service_account.Credentials.from_service_account_file(GCS_SERVICE_ACCOUNT_PATH)
            gcs_client = storage.Client(credentials=credentials, project=credentials.project_id)
            print(f"✓ GCS client initialized with credentials for bucket: {GCS_BUCKET_NAME}")
        except Exception as e:
            print(f"Warning: Failed to initialize GCS client with credentials: {e}")
    else:
        # Initialize anonymous client for public buckets
        try:
            gcs_client = storage.Client.create_anonymous_client()
            print(f"✓ GCS anonymous client initialized (for public buckets)")
        except Exception as e:
            print(f"Warning: Failed to initialize anonymous GCS client: {e}")
else:
    print("GCS features disabled (google-cloud-storage library not installed)")

# Progress tracker (for future features if needed)
progress_tracker = {}


def get_session_or_404(token: str):
    """Get session by token or raise 404."""
    session = session_mgr.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session


def parse_gcs_location(path: str) -> Tuple[str, str]:
    """Parse a GCS URI/URL into (bucket, object path/prefix)."""
    raw = (path or "").strip()
    if raw.startswith("gs://") or raw.startswith("gcs://"):
        without_scheme = raw.split("://", 1)[1]
        parts = without_scheme.split("/", 1)
        bucket = parts[0]
        object_path = parts[1] if len(parts) > 1 else ""
        return bucket, object_path.strip("/")

    if raw.startswith("https://storage.googleapis.com/"):
        without_host = raw[len("https://storage.googleapis.com/"):]
        parts = without_host.split("/", 1)
        bucket = parts[0]
        object_path = parts[1] if len(parts) > 1 else ""
        return bucket, object_path.strip("/")

    if raw.startswith("https://storage.cloud.google.com/"):
        without_host = raw[len("https://storage.cloud.google.com/"):]
        parts = without_host.split("/", 1)
        bucket = parts[0]
        object_path = parts[1] if len(parts) > 1 else ""
        return bucket, object_path.strip("/")

    # Fallback: treat as bucket-relative path for default configured bucket.
    return GCS_BUCKET_NAME, raw.strip("/")


def join_blob_path(prefix: str, filename: str) -> str:
    """Join GCS prefix and filename properly."""
    prefix_clean = (prefix or "").strip("/")
    file_clean = (filename or "").strip("/")
    if not prefix_clean:
        return file_clean
    if not file_clean:
        return prefix_clean
    return f"{prefix_clean}/{file_clean}"


def get_gcs_blob_for_session(session, filename: str = ""):
    if not GCS_AVAILABLE or gcs_client is None:
        raise HTTPException(status_code=503, detail="GCS features not available")

    bucket_name, base_prefix = parse_gcs_location(session.slides_dir)
    target_name = session.single_slide if session.single_slide else filename
    if not target_name:
        raise HTTPException(status_code=400, detail="Missing slide filename")

    blob_path = join_blob_path(base_prefix, target_name)
    bucket = gcs_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    # Don't check exists() here - let download fail if needed
    return bucket_name, blob_path, blob


def get_gcs_slide_metadata(bucket_name: str, blob_path: str, blob):
    """Get basic metadata from GCS blob without OpenSlide."""
    return {
        'filename': Path(blob_path).name,
        'size': blob.size or 0,
        'content_type': blob.content_type or 'application/octet-stream',
        'updated': blob.updated.isoformat() if blob.updated else None,
    }


def ensure_gcs_blob_accessible(session, slide_name: str):
    """Verify GCS blob exists and return metadata."""
    if not is_gcs_path(session.slides_dir):
        raise HTTPException(status_code=400, detail="Not a GCS session")

    bucket_name, base_prefix = parse_gcs_location(session.slides_dir)
    bucket = gcs_client.bucket(bucket_name) if gcs_client else None
    if bucket is None:
        raise HTTPException(status_code=503, detail="GCS client not initialized")

    candidate_name = session.single_slide
    if candidate_name:
        blob_path = join_blob_path(base_prefix, candidate_name)
        blob = bucket.blob(blob_path)
        if not blob.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {blob_path}")
        return bucket_name, blob_path, blob
    else:
        # Try to find slide by name
        for ext in ALLOWED_EXTENSIONS:
            test_blob_path = join_blob_path(base_prefix, f"{slide_name}.{ext}")
            test_blob = bucket.blob(test_blob_path)
            if test_blob.exists():
                return bucket_name, test_blob_path, test_blob
        raise HTTPException(status_code=404, detail="Slide not found in GCS")


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ========================================
# Session Management Endpoints (global)
# ========================================

class CreateSessionRequest(BaseModel):
    slides: str
    overlay: Optional[str] = None


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    """Create a new viewer session."""
    # Allow both local paths and GCS URLs
    if not is_gcs_path(req.slides):
        if not Path(req.slides).exists():
            raise HTTPException(status_code=400, detail=f"Path not found: {req.slides}")
    session = session_mgr.create_session(req.slides, req.overlay)
    return {
        "token": session.token,
        "url": f"/{session.token}/",
        "slides_dir": session.slides_dir,
        "single_slide": session.single_slide,
        "overlay_dir": session.overlay_dir,
    }


@app.delete("/api/sessions/{token}")
@app.post("/api/sessions/{token}/delete")
async def delete_session(token: str):
    """Delete a session explicitly via API."""
    deleted = session_mgr.delete_session(token)
    return {"deleted": deleted}


@app.post("/api/sessions/{token}/heartbeat")
async def heartbeat(token: str):
    """Keep a session alive."""
    session = session_mgr.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok", "last_accessed": session.last_accessed.isoformat()}


@app.get("/api/sessions")
async def list_sessions():
    """List all active sessions."""
    return {
        "sessions": [
            {
                "token": s.token,
                "slides_dir": s.slides_dir,
                "single_slide": s.single_slide,
                "created_at": s.created_at.isoformat(),
                "last_accessed": s.last_accessed.isoformat(),
            }
            for s in session_mgr.sessions.values()
        ]
    }


# ========================================
# Session-Scoped: Static Files
# ========================================

@app.get("/{token}/")
async def session_index(token: str):
    """Serve the viewer HTML for a session."""
    get_session_or_404(token)
    return FileResponse('index.html')


@app.get("/{token}/styles.css")
async def session_css(token: str):
    get_session_or_404(token)
    return FileResponse('styles.css', media_type='text/css')


@app.get("/{token}/viewer.js")
async def session_js(token: str):
    get_session_or_404(token)
    return FileResponse('viewer.js', media_type='application/javascript')


# ========================================
# Session-Scoped: Slide API Endpoints
# ========================================

@app.get("/{token}/api/slides")
async def list_slides(token: str):
    """List slides available in this session."""
    session = get_session_or_404(token)
    try:
        if is_gcs_path(session.slides_dir):
            if not GCS_AVAILABLE or gcs_client is None:
                raise HTTPException(status_code=503, detail="GCS features not available")

            bucket_name, prefix = parse_gcs_location(session.slides_dir)
            bucket = gcs_client.bucket(bucket_name)
            slides = []
            target_filename = session.single_slide

            # Single-file GCS sessions should resolve directly instead of scanning bucket.
            if target_filename:
                blob_path = join_blob_path(prefix, target_filename)
                blob = bucket.blob(blob_path)
                if not blob.exists():
                    return {"slides": []}
                stem = Path(target_filename).stem
                return {"slides": [{
                    'name': stem,
                    'filename': target_filename,
                    'size': blob.size or 0,
                    'viewable': True,
                }]}

            blobs = bucket.list_blobs(prefix=prefix)
            for blob in blobs:
                filename = Path(blob.name).name
                if not filename or not allowed_file(filename):
                    continue

                stem = Path(filename).stem
                slides.append({
                    'name': stem,
                    'filename': filename,
                    'size': blob.size or 0,
                    'viewable': True,  # Always viewable with GeoTIFFTileSource
                })
            return {"slides": slides}

        # Local files
        upload_dir = Path(session.slides_dir)
        if not upload_dir.exists():
            return {"slides": []}

        slides = []
        for fp in upload_dir.iterdir():
            if fp.is_file() and allowed_file(fp.name):
                if session.single_slide and fp.name != session.single_slide:
                    continue
                slides.append({
                    'name': fp.stem,
                    'filename': fp.name,
                    'size': fp.stat().st_size,
                    'viewable': True,  # Always viewable with GeoTIFFTileSource
                })
        return {"slides": slides}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/{token}/api/info/{slide_name}")
async def get_slide_info(token: str, slide_name: str):
    """Get metadata for a slide."""
    session = get_session_or_404(token)
    try:
        if is_gcs_path(session.slides_dir):
            bucket_name, blob_path, blob = ensure_gcs_blob_accessible(session, slide_name)
            metadata = get_gcs_slide_metadata(bucket_name, blob_path, blob)
            
            # Return basic info with slide_source marker for frontend
            return {
                'filename': metadata['filename'],
                'size': metadata['size'],
                'content_type': metadata['content_type'],
                'updated': metadata['updated'],
                'properties': {
                    'slide_source': 'gcs',
                    'bucket': bucket_name,
                    'path': blob_path
                },
                # Dummy dimensions for compatibility (GeoTIFFTileSource reads these from file)
                'dimensions': [0, 0],
                'level_count': 1,
            }
        else:
            # Local file
            slide_files = list(Path(session.slides_dir).glob(f"{slide_name}.*"))
            if not slide_files:
                raise HTTPException(status_code=404, detail="Slide not found")
            
            slide_path = slide_files[0]
            return {
                'filename': slide_path.name,
                'size': slide_path.stat().st_size,
                'properties': {
                    'slide_source': 'local',
                    'path': str(slide_path)
                },
                # Dummy dimensions for compatibility (GeoTIFFTileSource reads these from file)
                'dimensions': [0, 0],
                'level_count': 1,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/{token}/api/upload")
async def upload_file(token: str, file: UploadFile = File(...)):
    """Handle file upload to session's slides directory."""
    session = get_session_or_404(token)
    try:
        if is_gcs_path(session.slides_dir):
            raise HTTPException(status_code=400, detail="Upload is not supported for GCS-backed sessions")

        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected")
        if not allowed_file(file.filename):
            raise HTTPException(status_code=400, detail="File type not supported")

        upload_dir = Path(session.slides_dir)
        upload_dir.mkdir(exist_ok=True)
        file_path = upload_dir / file.filename

        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        slide_info = session.converter.get_slide_info(file_path)
        return {'success': True, 'filename': file.filename, 'name': file_path.stem, 'info': slide_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/{token}/api/delete/{slide_name}")
async def delete_slide(token: str, slide_name: str):
    """Delete a slide (local files only, not supported for GCS)."""
    session = get_session_or_404(token)
    if is_gcs_path(session.slides_dir):
        raise HTTPException(status_code=400, detail="Delete not supported for GCS slides")
    
    try:
        slide_files = list(Path(session.slides_dir).glob(f"{slide_name}.*"))
        if not slide_files:
            raise HTTPException(status_code=404, detail="Slide not found")
        for sf in slide_files:
            sf.unlink()
        return {'success': True, 'message': 'Slide deleted'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.options("/{token}/api/raw_slides/{filename:path}")
async def options_raw_slide(token: str, filename: str):
    return Response(status_code=200, headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
        'Access-Control-Allow-Headers': 'Range, Content-Type, Accept',
        'Access-Control-Expose-Headers': 'Content-Length, Content-Type, Content-Range, Accept-Ranges',
        'Access-Control-Max-Age': '3600'
    })


@app.head("/{token}/api/raw_slides/{filename:path}")
async def head_raw_slide(token: str, filename: str):
    """Handle HEAD requests for GeoTIFFTileSource compatibility."""
    session = get_session_or_404(token)
    try:
        if is_gcs_path(session.slides_dir):
            _, _, blob = get_gcs_blob_for_session(session, filename)
            blob.reload()  # Force reload to get size
            file_size = blob.size
            if not file_size or file_size == 0:
                raise HTTPException(status_code=404, detail=f"File not found or empty")
            print(f"HEAD request - GCS file size: {file_size}")
        else:
            file_path = Path(session.slides_dir) / filename
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="File not found")
            file_size = file_path.stat().st_size
        
        ext = filename.rsplit('.', 1)[-1].lower() if "." in filename else ""
        content_type_map = {
            'svs': 'image/tiff', 'tif': 'image/tiff', 'tiff': 'image/tiff',
        }
        content_type = content_type_map.get(ext, 'application/octet-stream')
        
        return Response(status_code=200, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
            'Access-Control-Expose-Headers': 'Content-Length, Content-Type, Accept-Ranges',
            'Accept-Ranges': 'bytes',
            'Content-Type': content_type,
            'Content-Length': str(file_size)
        })
    except HTTPException:
        raise
    except Exception as e:
        print(f"HEAD error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/{token}/api/raw_slides/{filename:path}")
async def serve_raw_slide(token: str, filename: str, request: Request):
    """Serve raw slide files with range request support (CORS proxy for GCS, direct serve for local)."""
    session = get_session_or_404(token)
    try:
        ext = filename.rsplit('.', 1)[-1].lower() if "." in filename else ""
        content_type_map = {
            'svs': 'image/tiff', 'tif': 'image/tiff', 'tiff': 'image/tiff',
        }
        content_type = content_type_map.get(ext, 'application/octet-stream')

        cors_headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
            'Access-Control-Allow-Headers': 'Range, Content-Type, Accept',
            'Access-Control-Expose-Headers': 'Content-Length, Content-Type, Content-Range, Accept-Ranges',
            'Accept-Ranges': 'bytes',
            'Content-Type': content_type
        }

        if is_gcs_path(session.slides_dir):
            # GCS files: proxy with range request support
            _, _, blob = get_gcs_blob_for_session(session, filename)
            
            # Reload blob to get size
            blob.reload()
            file_size = blob.size
            
            if not file_size or file_size == 0:
                raise HTTPException(status_code=404, detail=f"File not found or empty")
            
            print(f"GCS file size: {file_size}")
            range_header = request.headers.get('range')
            
            if range_header:
                range_match = range_header.replace('bytes=', '').split('-')
                start = int(range_match[0]) if range_match[0] else 0
                end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else file_size - 1
                
                print(f"GCS Range: {range_header} | Size: {file_size} | Start: {start}, End: {end}")
                
                # Validate start position
                if start >= file_size or start < 0:
                    print(f"❌ Invalid start: {start}, size={file_size}")
                    return Response(status_code=416, headers={
                        **cors_headers, 
                        'Content-Range': f'bytes */{file_size}'
                    })
                
                # Clamp end to file size - 1 (inclusive end byte)
                if end >= file_size:
                    print(f"⚠️  End {end} exceeds file size {file_size}, clamping to {file_size - 1}")
                    end = file_size - 1
                
                if start > end:
                    print(f"❌ Invalid: start > end ({start} > {end})")
                    return Response(status_code=416, headers={
                        **cors_headers, 
                        'Content-Range': f'bytes */{file_size}'
                    })
                
                # GCS download_as_bytes uses inclusive start, exclusive end
                # So end + 1 for the GCS API call
                print(f"✅ Valid range, downloading bytes {start}-{end}")
                content = blob.download_as_bytes(start=start, end=end + 1)
                print(f"✅ Downloaded {len(content)} bytes")
                return Response(content=content, status_code=206, headers={
                    **cors_headers, 
                    'Content-Length': str(len(content)),
                    'Content-Range': f'bytes {start}-{end}/{file_size}'
                })

            content = blob.download_as_bytes()
            return Response(content=content, status_code=200, headers={
                **cors_headers,
                'Content-Length': str(file_size),
                'Content-Disposition': f'inline; filename="{Path(blob.name).name}"'
            })
        else:
            # Local files: serve with range request support
            file_path = Path(session.slides_dir) / filename
            try:
                if not file_path.resolve().is_relative_to(Path(session.slides_dir).resolve()):
                    raise HTTPException(status_code=403, detail="Access denied")
            except AttributeError:
                try:
                    file_path.resolve().relative_to(Path(session.slides_dir).resolve())
                except ValueError:
                    raise HTTPException(status_code=403, detail="Access denied")

            if not file_path.exists():
                raise HTTPException(status_code=404, detail="File not found")

            file_size = file_path.stat().st_size
            print(f"Local file size: {file_size}")
            range_header = request.headers.get('range')
            
            if range_header:
                range_match = range_header.replace('bytes=', '').split('-')
                start = int(range_match[0]) if range_match[0] else 0
                end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else file_size - 1
                
                print(f"Local Range: {range_header} | Size: {file_size} | Start: {start}, End: {end}")
                
                # Validate start position
                if start >= file_size or start < 0:
                    print(f"❌ Invalid start: {start}, size={file_size}")
                    return Response(status_code=416, headers={
                        **cors_headers, 
                        'Content-Range': f'bytes */{file_size}'
                    })
                
                # Clamp end to file size - 1 (inclusive end byte)
                if end >= file_size:
                    print(f"⚠️  End {end} exceeds file size {file_size}, clamping to {file_size - 1}")
                    end = file_size - 1
                
                if start > end:
                    print(f"❌ Invalid: start > end ({start} > {end})")
                    return Response(status_code=416, headers={
                        **cors_headers, 
                        'Content-Range': f'bytes */{file_size}'
                    })
                
                print(f"✅ Valid range, reading bytes {start}-{end}")
                with open(file_path, 'rb') as f:
                    f.seek(start)
                    content = f.read(end - start + 1)
                print(f"✅ Read {len(content)} bytes")
                return Response(content=content, status_code=206, headers={
                    **cors_headers, 
                    'Content-Length': str(len(content)),
                    'Content-Range': f'bytes {start}-{end}/{file_size}'
                })
            else:
                print(f"No range header, serving full file")
                return FileResponse(path=str(file_path), media_type=content_type, headers=cors_headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to serve file: {str(e)}")


@app.get("/{token}/api/overlay-config/{slide_name}")
async def get_overlay_config(token: str, slide_name: str):
    """Get per-slide overlay configuration."""
    session = get_session_or_404(token)
    density = session.find_overlay_file(slide_name, '_density.png')
    metadata = session.find_overlay_file(slide_name, '_metadata.json')
    grid = session.find_overlay_file(slide_name, '_grid.json')
    available = density is not None and metadata is not None
    return {
        "available": available,
        "density_image": f"/{token}/api/overlay-file/{slide_name}_density.png" if density else None,
        "metadata": f"/{token}/api/overlay-file/{slide_name}_metadata.json" if metadata else None,
        "grid": f"/{token}/api/overlay-file/{slide_name}_grid.json" if grid else None,
    }


@app.get("/{token}/api/overlay-file/{filename}")
async def serve_overlay_file(token: str, filename: str):
    """Serve an overlay file from overlay dir or slides dir."""
    session = get_session_or_404(token)
    for suffix in ['_density.png', '_metadata.json', '_grid.json']:
        if filename.endswith(suffix):
            slide_name = filename[:-len(suffix)]
            file_path = session.find_overlay_file(slide_name, suffix)
            if file_path:
                media_type = 'image/png' if suffix.endswith('.png') else 'application/json'
                return FileResponse(file_path, media_type=media_type)
            break
    raise HTTPException(status_code=404, detail=f"Overlay file not found: {filename}")


# ========================================
# GCS Endpoints (global, not session-scoped)
# ========================================

@app.post("/api/gcs/download")
async def download_gcs_file(blob_path: str = Query(..., description="Path to blob in GCS bucket")):
    """Download a file from GCS to local uploads folder."""
    if not GCS_AVAILABLE:
        raise HTTPException(status_code=503, detail="GCS library not installed")
    if gcs_client is None:
        raise HTTPException(status_code=503, detail="GCS client not initialized")
    try:
        original_blob_path = blob_path
        if blob_path.startswith('http'):
            if 'storage.cloud.google.com' in blob_path or 'storage.googleapis.com' in blob_path:
                parts = blob_path.split(f'{GCS_BUCKET_NAME}/')
                if len(parts) > 1:
                    blob_path = parts[1]
        if blob_path.startswith(f'{GCS_BUCKET_NAME}/'):
            blob_path = blob_path[len(f'{GCS_BUCKET_NAME}/'):]

        bucket = gcs_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        if not blob.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {blob_path}")

        filename = blob_path.split('/')[-1]
        slide_name = Path(filename).stem
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        local_path = upload_dir / filename

        if local_path.exists():
            return {'success': True, 'filename': filename, 'name': slide_name,
                    'message': 'File already exists locally', 'downloaded': False}

        print(f"Downloading {filename} from GCS...")
        blob.download_to_filename(str(local_path))
        print(f"✓ Downloaded {filename} to {local_path}")
        return {'success': True, 'filename': filename, 'name': slide_name,
                'size': local_path.stat().st_size, 'downloaded': True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download GCS file: {str(e)}")


@app.get("/api/gcs/proxy/{blob_path:path}")
async def proxy_gcs_file(blob_path: str):
    """Proxy GCS file through server to avoid CORS issues."""
    if not GCS_AVAILABLE or gcs_client is None:
        raise HTTPException(status_code=503, detail="GCS features not available")
    try:
        if blob_path.startswith('http'):
            if 'storage.cloud.google.com' in blob_path or 'storage.googleapis.com' in blob_path:
                parts = blob_path.split(f'{GCS_BUCKET_NAME}/')
                if len(parts) > 1:
                    blob_path = parts[1]
        if blob_path.startswith(f'{GCS_BUCKET_NAME}/'):
            blob_path = blob_path[len(f'{GCS_BUCKET_NAME}/'):]

        bucket = gcs_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        if not blob.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {blob_path}")

        content = blob.download_as_bytes()
        content_type = blob.content_type or 'application/octet-stream'
        return Response(content=content, media_type=content_type, headers={
            'Access-Control-Allow-Origin': '*',
            'Content-Disposition': f'inline; filename="{blob_path.split("/")[-1]}"'
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to proxy GCS file: {str(e)}")


@app.get("/api/gcs/files")
async def list_gcs_files(prefix: Optional[str] = Query(None)):
    """List WSI files in GCS bucket."""
    if not GCS_AVAILABLE or gcs_client is None:
        raise HTTPException(status_code=503, detail="GCS features not available")
    try:
        bucket = gcs_client.bucket(GCS_BUCKET_NAME)
        blobs = bucket.list_blobs(prefix=prefix)
        files = []
        for blob in blobs:
            if '.' in blob.name:
                ext = blob.name.rsplit('.', 1)[1].lower()
                if ext in ALLOWED_EXTENSIONS:
                    files.append({
                        'name': blob.name.split('/')[-1], 'path': blob.name,
                        'size': blob.size, 'updated': blob.updated.isoformat() if blob.updated else None
                    })
        return {'files': files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list GCS files: {str(e)}")


@app.get("/api/gcs/status")
async def get_gcs_status():
    """Check GCS availability."""
    status = {
        'available': False,
        'library_installed': GCS_AVAILABLE,
        'credentials_found': os.path.exists(GCS_SERVICE_ACCOUNT_PATH) if GCS_AVAILABLE else False,
        'client_initialized': gcs_client is not None,
        'bucket_name': GCS_BUCKET_NAME,
        'error': None
    }
    if not GCS_AVAILABLE:
        status['error'] = 'google-cloud-storage not installed'
    elif not os.path.exists(GCS_SERVICE_ACCOUNT_PATH):
        status['error'] = f'Service account not found: {GCS_SERVICE_ACCOUNT_PATH}'
    elif gcs_client is None:
        status['error'] = 'GCS client failed to initialize'
    else:
        status['available'] = True
    return status


@app.get("/api/gcs/signed-url")
async def get_gcs_signed_url(blob_path: str = Query(...), expiration_hours: int = Query(24)):
    """Generate a signed URL for a GCS blob."""
    if not GCS_AVAILABLE:
        raise HTTPException(status_code=503, detail="GCS library not installed")
    if gcs_client is None:
        raise HTTPException(status_code=503, detail="GCS client not initialized")
    try:
        if blob_path.startswith('http'):
            parts = blob_path.split(f'{GCS_BUCKET_NAME}/')
            if len(parts) > 1:
                blob_path = parts[1]
        if blob_path.startswith(f'{GCS_BUCKET_NAME}/'):
            blob_path = blob_path[len(f'{GCS_BUCKET_NAME}/'):]

        bucket = gcs_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        if not blob.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {blob_path}")

        from datetime import timedelta
        expiration = datetime.utcnow() + timedelta(hours=expiration_hours)
        signed_url = blob.generate_signed_url(expiration=expiration, method='GET', version='v4')
        filename = blob_path.split('/')[-1]
        return {
            'success': True, 'signed_url': signed_url, 'filename': filename,
            'name': Path(filename).stem, 'expires_at': expiration.isoformat(),
            'is_directly_viewable': Path(filename).suffix.lower() in ['.svs', '.tif', '.tiff']
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate signed URL: {str(e)}")


# ========================================
# Startup & Shutdown
# ========================================

@app.on_event("startup")
async def startup_event():
    """Create default session from CLI args and start cleanup loop."""
    # Create default session from CLI arguments
    default_session = session_mgr.create_session(slides_path, args.overlay)

    # Start background cleanup
    await session_mgr.start_cleanup_loop(interval_minutes=5)

    is_gcs = is_gcs_path(slides_path)
    mode = "GCS" if is_gcs else "Local"
    
    print("=" * 60)
    print("WSI Viewer Server - GeoTIFFTileSource Streaming")
    print("=" * 60)
    print(f"Mode: {mode}")
    print(f"Slides: {slides_path}")
    if args.overlay:
        print(f"Overlay: {args.overlay}")
    print(f"Default session: http://localhost:8511/{default_session.token}/")
    print(f"Create new sessions: POST http://localhost:8511/api/sessions")
    print(f"API docs: http://localhost:8511/docs")
    print(f"Session TTL: {args.session_ttl} minutes")
    print(f"GCS Client: {'✓ Available' if gcs_client else '✗ Not available'}")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Stop the cleanup loop."""
    session_mgr.stop_cleanup_loop()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8511, reload=True)
