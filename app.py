"""
WSI Viewer - FastAPI Backend
Session-based multi-tenant viewer with UUID tokens.
Each session has its own slides directory, overlay, and converter.
"""

import os
import asyncio
import json
import zipfile
import tempfile
import shutil
import argparse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query, Request, Depends
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from session_manager import (
    SessionManager,
    ALLOWED_EXTENSIONS,
    is_gcs_path,
    is_url,
    is_zip_path,
    is_direct_slide_url,
    url_to_slide_filename,
)


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
parser.add_argument("--slides", type=str, nargs='*', default=None,
                    help="One or more GCS paths (gs://bucket/path or https://storage.googleapis.com/...)")
parser.add_argument("--slides-local", type=str, nargs='*', default=None,
                    help="One or more local paths to slides")
parser.add_argument("--overlay", type=str, nargs='*', default=None,
                    help="Overlay sources: local directory, local .zip, or http(s) URL to a .zip (e.g. signed URL)")
parser.add_argument("--thumbnails", type=str, nargs='*', default=None,
                    help="Thumbnail sources: local directory, local .zip, http(s) URL to .zip, or GCS prefix (gs://bucket/prefix/)")
parser.add_argument("--session-ttl", type=int, default=30,
                    help="Session TTL in minutes (default: 30)")
args, unknown = parser.parse_known_args()

# Determine which slides source to use
if args.slides and args.slides_local:
    raise ValueError("Cannot specify both --slides and --slides-local")

# Build list of slide paths
slide_paths = []
if args.slides:
    slide_paths.extend(args.slides)
elif args.slides_local:
    slide_paths.extend(args.slides_local)
else:
    slide_paths = ["uploads"]  # Default to local uploads

# Build list of overlay paths
overlay_paths = args.overlay if args.overlay else []
thumbnail_paths = args.thumbnails if args.thumbnails else []

# Cloud Run / GKE: override from environment (no CLI in container)
_PORT = os.getenv("PORT", "8511")
PORT = int(_PORT) if str(_PORT).isdigit() else 8511
if os.getenv("SLIDE_PATHS"):
    slide_paths = [p.strip() for p in os.getenv("SLIDE_PATHS", "").split(",") if p.strip()]
if os.getenv("OVERLAY_PATHS"):
    overlay_paths = [p.strip() for p in os.getenv("OVERLAY_PATHS", "").split(",") if p.strip()]
if os.getenv("THUMBNAIL_PATHS"):
    thumbnail_paths = [p.strip() for p in os.getenv("THUMBNAIL_PATHS", "").split(",") if p.strip()]

# Initialize session manager (no cache dir needed without conversion)
session_mgr = SessionManager(ttl_minutes=args.session_ttl)

# ========================================
# Authorization (HTTP Basic Auth)
# ========================================
# Auth is required only for global API: create/list/delete sessions, heartbeat, GCS.
# Session viewer routes (/{token}/...) do NOT require auth; the token in the URL is the credential.
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "satya@4basecare.com")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "satya123")
security = HTTPBasic()


def verify_basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Auth credentials. Used only on global API routes. Raises 401 if invalid."""
    if credentials.username != AUTH_USERNAME or credentials.password != AUTH_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ========================================
# Liveness / Readiness (Cloud Run, GKE)
# ========================================
@app.get("/health", tags=["Health"])
async def health():
    """No-auth health check for load balancers and orchestrators."""
    return {"status": "ok"}


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


def find_file_in_session(session, filename: str):
    """Find a file across all slide paths in the session.
    Returns:
    - For direct URL: ("url", url_str)
    - For GCS: (True, (bucket_name, blob_path, blob))
    - For local: (False, file_path)
    Raises HTTPException if not found.
    """
    for slide_path in session.slide_paths:
        if is_direct_slide_url(slide_path) and url_to_slide_filename(slide_path) == filename:
            return "url", slide_path
        if is_gcs_path(slide_path):
            # Try GCS
            try:
                bucket_name, prefix = parse_gcs_location(slide_path)
                bucket = gcs_client.bucket(bucket_name)
                
                # Check if slide_path is a single file
                if prefix and "." in prefix.rsplit("/", 1)[-1]:
                    # Single file path
                    file_name = Path(prefix).name
                    if file_name == filename:
                        blob = bucket.blob(prefix)
                        if blob.exists():
                            return True, (bucket_name, prefix, blob)
                else:
                    # Directory path
                    blob_path = join_blob_path(prefix, filename)
                    blob = bucket.blob(blob_path)
                    if blob.exists():
                        return True, (bucket_name, blob_path, blob)
            except Exception as e:
                print(f"Error checking GCS path {slide_path}: {e}")
                continue
        else:
            # Try local path
            p = Path(slide_path)
            if p.is_file():
                # Single file
                if p.name == filename:
                    return False, p
            else:
                # Directory
                file_path = p / filename
                if file_path.exists():
                    return False, file_path
    
    raise HTTPException(status_code=404, detail=f"File not found: {filename}")


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
    slides: List[str]  # List of slide paths (GCS or local)
    overlay: Optional[List[str]] = None  # Overlay dirs/zips/URLs
    thumbnail: Optional[List[str]] = None  # Thumbnail dirs/zips/URLs or GCS prefix
    metadata: Optional[dict] = None  # Optional slide metadata: width, height, mpp, objective_power, vendor, thumbnail_url (for scale/physical units)


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest, _: str = Depends(verify_basic_auth)):
    """Create a new viewer session."""
    for slide_path in req.slides:
        if not is_gcs_path(slide_path):
            if not Path(slide_path).exists():
                raise HTTPException(status_code=400, detail=f"Path not found: {slide_path}")
    
    overlay_paths = req.overlay if req.overlay else []
    thumb_paths = req.thumbnail if req.thumbnail else []
    session = session_mgr.create_session(req.slides, overlay_paths, thumbnail_paths=thumb_paths, metadata=req.metadata)
    return {
        "token": session.token,
        "url": f"/{session.token}/",
        "slide_paths": session.slide_paths,
        "overlay_paths": session.overlay_paths,
        "thumbnail_paths": session.thumbnail_paths,
        "metadata": session.metadata,
    }


@app.delete("/api/sessions/{token}")
@app.post("/api/sessions/{token}/delete")
async def delete_session(token: str, _: str = Depends(verify_basic_auth)):
    """Delete a session explicitly via API."""
    deleted = session_mgr.delete_session(token)
    return {"deleted": deleted}


@app.post("/api/sessions/{token}/heartbeat")
async def heartbeat(token: str, _: str = Depends(verify_basic_auth)):
    """Keep a session alive."""
    session = session_mgr.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok", "last_accessed": session.last_accessed.isoformat()}


@app.get("/api/sessions")
async def list_sessions(_: str = Depends(verify_basic_auth)):
    """List all active sessions."""
    return {
        "sessions": [
            {
                "token": s.token,
                "slide_paths": s.slide_paths,
                "overlay_paths": s.overlay_paths,
                "thumbnail_paths": s.thumbnail_paths,
                "metadata": s.metadata,
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
    """List slides available in this session. Each slide includes a thumbnail URL if available."""
    session = get_session_or_404(token)
    await resolve_overlay_zip(session)
    try:
        all_slides = []
        seen_filenames = set()  # To deduplicate slides with same filename
        
        for slide_path in session.slide_paths:
            if is_direct_slide_url(slide_path):
                filename = url_to_slide_filename(slide_path)
                if not filename or filename in seen_filenames:
                    continue
                stem = Path(filename).stem
                all_slides.append({
                    'name': stem,
                    'filename': filename,
                    'size': 0,
                    'viewable': True,
                    'thumbnail': f"/{token}/api/thumbnail/{stem}",
                })
                seen_filenames.add(filename)
                continue
            if is_gcs_path(slide_path):
                if not GCS_AVAILABLE or gcs_client is None:
                    print(f"Warning: GCS path specified but GCS not available: {slide_path}")
                    continue

                bucket_name, prefix = parse_gcs_location(slide_path)
                bucket = gcs_client.bucket(bucket_name)
                
                # Check if this is a direct file path or a directory
                is_single_file = False
                if prefix:
                    # Check if it ends with an extension
                    ext = prefix.rsplit(".", 1)[-1].lower() if "." in prefix else ""
                    if ext in ALLOWED_EXTENSIONS:
                        is_single_file = True
                
                if is_single_file:
                    # Handle single file
                    blob = bucket.blob(prefix)
                    if blob.exists():
                        filename = Path(prefix).name
                        if filename not in seen_filenames:
                            stem = Path(filename).stem
                            all_slides.append({
                                'name': stem,
                                'filename': filename,
                                'size': blob.size or 0,
                                'viewable': True,
                                'thumbnail': f"/{token}/api/thumbnail/{stem}",
                            })
                            seen_filenames.add(filename)
                else:
                    # List all files in the directory/prefix
                    blobs = bucket.list_blobs(prefix=prefix)
                    for blob in blobs:
                        filename = Path(blob.name).name
                        if not filename or not allowed_file(filename):
                            continue
                        
                        if filename not in seen_filenames:
                            stem = Path(filename).stem
                            all_slides.append({
                                'name': stem,
                                'filename': filename,
                                'size': blob.size or 0,
                                'viewable': True,
                                'thumbnail': f"/{token}/api/thumbnail/{stem}",
                            })
                            seen_filenames.add(filename)
            
            else:
                # Local path
                p = Path(slide_path)
                if not p.exists():
                    print(f"Warning: Local path does not exist: {slide_path}")
                    continue
                
                if p.is_file():
                    # Single file
                    if allowed_file(p.name) and p.name not in seen_filenames:
                        all_slides.append({
                            'name': p.stem,
                            'filename': p.name,
                            'size': p.stat().st_size,
                            'viewable': True,
                            'thumbnail': f"/{token}/api/thumbnail/{p.stem}",
                        })
                        seen_filenames.add(p.name)
                else:
                    # Directory
                    for fp in p.iterdir():
                        if fp.is_file() and allowed_file(fp.name) and fp.name not in seen_filenames:
                            all_slides.append({
                                'name': fp.stem,
                                'filename': fp.name,
                                'size': fp.stat().st_size,
                                'viewable': True,
                                'thumbnail': f"/{token}/api/thumbnail/{fp.stem}",
                            })
                            seen_filenames.add(fp.name)
        
        return {"slides": all_slides}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/{token}/api/info/{slide_name}")
async def get_slide_info(token: str, slide_name: str):
    """Get metadata for a slide."""
    session = get_session_or_404(token)
    try:
        # Search all slide paths for this slide
        for slide_path in session.slide_paths:
            if is_direct_slide_url(slide_path):
                filename = url_to_slide_filename(slide_path)
                if filename and Path(filename).stem == slide_name:
                    return {
                        'filename': filename,
                        'size': 0,
                        'properties': {'slide_source': 'url', 'url': slide_path},
                        'dimensions': [0, 0],
                        'level_count': 1,
                    }
                continue
            if is_gcs_path(slide_path):
                # Try GCS
                try:
                    bucket_name, prefix = parse_gcs_location(slide_path)
                    bucket = gcs_client.bucket(bucket_name)
                    
                    # Try to find the slide file
                    for ext in ALLOWED_EXTENSIONS:
                        test_blob_path = join_blob_path(prefix, f"{slide_name}.{ext}")
                        test_blob = bucket.blob(test_blob_path)
                        if test_blob.exists():
                            metadata = get_gcs_slide_metadata(bucket_name, test_blob_path, test_blob)
                            return {
                                'filename': metadata['filename'],
                                'size': metadata['size'],
                                'content_type': metadata['content_type'],
                                'updated': metadata['updated'],
                                'properties': {
                                    'slide_source': 'gcs',
                                    'bucket': bucket_name,
                                    'path': test_blob_path
                                },
                                'dimensions': [0, 0],
                                'level_count': 1,
                            }
                except Exception as e:
                    print(f"Error checking GCS path {slide_path}: {e}")
                    continue
            else:
                # Try local path
                p = Path(slide_path)
                if p.is_file():
                    # Single file - check if it matches
                    if p.stem == slide_name:
                        return {
                            'filename': p.name,
                            'size': p.stat().st_size,
                            'properties': {
                                'slide_source': 'local',
                                'path': str(p)
                            },
                            'dimensions': [0, 0],
                            'level_count': 1,
                        }
                else:
                    # Directory - search for matching file
                    slide_files = list(p.glob(f"{slide_name}.*"))
                    if slide_files:
                        slide_file = slide_files[0]
                        return {
                            'filename': slide_file.name,
                            'size': slide_file.stat().st_size,
                            'properties': {
                                'slide_source': 'local',
                                'path': str(slide_file)
                            },
                            'dimensions': [0, 0],
                            'level_count': 1,
                        }
        
        raise HTTPException(status_code=404, detail="Slide not found in any configured path")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/{token}/api/upload")
async def upload_file(token: str, file: UploadFile = File(...)):
    """Handle file upload to session's first local slides directory."""
    session = get_session_or_404(token)
    try:
        # Find the first local (non-GCS) slide path
        upload_dir = None
        for slide_path in session.slide_paths:
            if not is_gcs_path(slide_path):
                p = Path(slide_path)
                if p.is_dir():
                    upload_dir = p
                    break
                else:
                    # If it's a file, use its parent directory
                    upload_dir = p.parent
                    break
        
        if upload_dir is None:
            raise HTTPException(status_code=400, detail="Upload is not supported for GCS-only sessions")

        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected")
        if not allowed_file(file.filename):
            raise HTTPException(status_code=400, detail="File type not supported")

        upload_dir.mkdir(exist_ok=True)
        file_path = upload_dir / file.filename

        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        return {'success': True, 'filename': file.filename, 'name': file_path.stem}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/{token}/api/delete/{slide_name}")
async def delete_slide(token: str, slide_name: str):
    """Delete a slide (local files only, not supported for GCS)."""
    session = get_session_or_404(token)
    
    try:
        # Search all local slide paths for the file (skip GCS and direct URL)
        deleted = False
        for slide_path in session.slide_paths:
            if is_direct_slide_url(slide_path) or is_gcs_path(slide_path):
                continue

            p = Path(slide_path)
            if p.is_dir():
                slide_files = list(p.glob(f"{slide_name}.*"))
                if slide_files:
                    for sf in slide_files:
                        sf.unlink()
                    deleted = True
                    break
            else:
                # Single file
                if p.stem == slide_name:
                    p.unlink()
                    deleted = True
                    break
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Slide not found or is in GCS/URL (delete not supported)")
        
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


def _head_direct_url(url: str):
    """Perform HEAD request to URL; return (content_length, accept_ranges). Raises on failure."""
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as resp:
        cl = resp.headers.get("Content-Length")
        content_length = int(cl) if cl and cl.isdigit() else 0
        accept_ranges = resp.headers.get("Accept-Ranges", "bytes")
    return content_length, accept_ranges


def _fetch_url_range(url: str, range_header: Optional[str] = None):
    """GET url with optional Range header; return (status_code, headers_dict, body_bytes)."""
    req = urllib.request.Request(url)
    if range_header:
        req.add_header("Range", range_header)
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
    status = resp.status
    out_headers = {}
    for key in ("Content-Length", "Content-Range", "Content-Type", "Accept-Ranges"):
        if resp.headers.get(key):
            out_headers[key] = resp.headers[key]
    return status, out_headers, body


@app.head("/{token}/api/raw_slides/{filename:path}")
async def head_raw_slide(token: str, filename: str):
    """Handle HEAD requests for GeoTIFFTileSource compatibility."""
    session = get_session_or_404(token)
    try:
        result = find_file_in_session(session, filename)
        is_gcs, location = result[0], result[1]

        if is_gcs == "url":
            file_size, accept_ranges = await asyncio.get_event_loop().run_in_executor(
                None, _head_direct_url, location
            )
            if not file_size:
                raise HTTPException(status_code=404, detail="File not found or empty")
        elif is_gcs:
            _, _, blob = location
            blob.reload()  # Force reload to get size
            file_size = blob.size
            if not file_size or file_size == 0:
                raise HTTPException(status_code=404, detail=f"File not found or empty")
            print(f"HEAD request - GCS file size: {file_size}")
            accept_ranges = "bytes"
        else:
            file_path = location
            file_size = file_path.stat().st_size
            accept_ranges = "bytes"

        ext = filename.rsplit('.', 1)[-1].lower() if "." in filename else ""
        content_type_map = {
            'svs': 'image/tiff', 'tif': 'image/tiff', 'tiff': 'image/tiff',
        }
        content_type = content_type_map.get(ext, 'application/octet-stream')

        return Response(status_code=200, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
            'Access-Control-Expose-Headers': 'Content-Length, Content-Type, Accept-Ranges',
            'Accept-Ranges': accept_ranges,
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

        # Find file across all slide paths
        result = find_file_in_session(session, filename)
        is_gcs, location = result[0], result[1]

        if is_gcs == "url":
            # Direct URL (public or signed): proxy GET with Range
            range_header = request.headers.get("range")
            status, out_headers, body = await asyncio.get_event_loop().run_in_executor(
                None, _fetch_url_range, location, range_header
            )
            if status >= 400:
                raise HTTPException(status_code=502, detail="Upstream request failed")
            resp_headers = {**cors_headers, **out_headers}
            if "Accept-Ranges" not in resp_headers:
                resp_headers["Accept-Ranges"] = "bytes"
            return Response(content=body, status_code=status, headers=resp_headers)

        if is_gcs:
            # GCS files: proxy with range request support
            _, _, blob = location
            
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
            file_path = location
            
            # Security check: ensure file is in one of the authorized slide paths
            is_authorized = False
            resolved_file = file_path.resolve()
            for slide_path in session.slide_paths:
                if not is_gcs_path(slide_path):
                    resolved_slide_path = Path(slide_path).resolve()
                    if resolved_slide_path.is_file():
                        # If slide_path is a file, check if it's the same file
                        if resolved_file == resolved_slide_path:
                            is_authorized = True
                            break
                    else:
                        # If slide_path is a directory, check if file is within it
                        try:
                            if hasattr(resolved_file, 'is_relative_to'):
                                if resolved_file.is_relative_to(resolved_slide_path):
                                    is_authorized = True
                                    break
                            else:
                                # Fallback for Python < 3.9
                                try:
                                    resolved_file.relative_to(resolved_slide_path)
                                    is_authorized = True
                                    break
                                except ValueError:
                                    pass
                        except:
                            pass
            
            if not is_authorized:
                raise HTTPException(status_code=403, detail="Access denied")

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


def _extract_zip_to_tempdir(zip_source: str) -> str:
    """
    Download (if URL) and extract a .zip archive to a new temp directory.
    Returns the path to the extracted temp directory.
    """
    tmp_dir = tempfile.mkdtemp(prefix="wsi_overlay_")
    try:
        if is_url(zip_source):
            # Download to a temp file first
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
                tmp_zip_path = tmp_zip.name
            try:
                urllib.request.urlretrieve(zip_source, tmp_zip_path)
                with zipfile.ZipFile(tmp_zip_path, 'r') as zf:
                    zf.extractall(tmp_dir)
            finally:
                os.unlink(tmp_zip_path)
        else:
            # Local zip file
            with zipfile.ZipFile(zip_source, 'r') as zf:
                zf.extractall(tmp_dir)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return tmp_dir


async def resolve_overlay_zip(session) -> None:
    """
    For any overlay_path that is a URL or local .zip, download and extract once.
    Extracted files land in a single temp directory stored on session.overlay_extracted_dir.
    No-op if already resolved.
    """
    if session.overlay_extracted_dir:
        return  # Already resolved

    zip_sources = [
        p for p in session.overlay_paths
        if is_zip_path(p) or (is_url(p) and not is_gcs_path(p))
    ]
    if not zip_sources:
        return

    import asyncio
    loop = asyncio.get_event_loop()

    tmp_dir = tempfile.mkdtemp(prefix="wsi_overlay_")
    try:
        for source in zip_sources:
            extracted = await loop.run_in_executor(None, _extract_zip_to_tempdir, source)
            # Move all files from this extraction into the shared tmp_dir
            for item in Path(extracted).rglob("*"):
                if item.is_file():
                    dest = Path(tmp_dir) / item.relative_to(extracted)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(item), str(dest))
            shutil.rmtree(extracted, ignore_errors=True)
        session.overlay_extracted_dir = tmp_dir
        print(f"Overlay zip extracted to: {tmp_dir}")
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"Warning: Failed to extract overlay zip: {e}")


async def resolve_thumbnail_zip(session) -> None:
    """Extract any thumbnail_paths that are zips/URLs into session.thumbnail_extracted_dir."""
    if session.thumbnail_extracted_dir:
        return
    zip_sources = [
        p for p in session.thumbnail_paths
        if is_zip_path(p) or (is_url(p) and not is_gcs_path(p))
    ]
    if not zip_sources:
        return
    import asyncio
    loop = asyncio.get_event_loop()
    tmp_dir = tempfile.mkdtemp(prefix="wsi_thumb_")
    try:
        for source in zip_sources:
            extracted = await loop.run_in_executor(None, _extract_zip_to_tempdir, source)
            for item in Path(extracted).rglob("*"):
                if item.is_file():
                    dest = Path(tmp_dir) / item.relative_to(extracted)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(item), str(dest))
            shutil.rmtree(extracted, ignore_errors=True)
        session.thumbnail_extracted_dir = tmp_dir
        print(f"Thumbnail zip extracted to: {tmp_dir}")
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"Warning: Failed to extract thumbnail zip: {e}")


def _stream_thumbnail_from_direct_url(session, slide_name: str):
    """If thumbnail_paths contains a direct http(s) URL to a PNG for this slide, download and return (bytes, type)."""
    suffixes = ("_tb.png", "_thumb.png", "_thumbnail.png")
    for url in session.thumbnail_paths:
        if not is_url(url) or is_gcs_path(url):
            continue
        # Strip query string for matching
        path_part = url.split("?")[0].rstrip("/")
        for suffix in suffixes:
            if path_part.endswith(f"{slide_name}{suffix}"):
                try:
                    with urllib.request.urlopen(url, timeout=30) as resp:
                        data = resp.read()
                    return (data, "image/png")
                except Exception:
                    return None
    return None


def _stream_thumbnail_from_gcs(session, slide_name: str):
    """Try to find and stream thumbnail from GCS thumbnail_paths (direct object URL or prefix). Returns (content_bytes, content_type) or None."""
    if not GCS_AVAILABLE or gcs_client is None:
        return None
    suffixes = ("_tb.png", "_thumb.png", "_thumbnail.png")
    for tp in session.thumbnail_paths:
        if not is_gcs_path(tp):
            continue
        try:
            bucket_name, object_path = parse_gcs_location(tp)
            bucket = gcs_client.bucket(bucket_name)
            path_clean = (object_path or "").strip("/")
            # Direct object URL (e.g. gs://bucket/Head_neck_pathology_tb.png)
            for suffix in suffixes:
                if path_clean.endswith(f"{slide_name}{suffix}"):
                    blob = bucket.blob(path_clean)
                    if blob.exists():
                        data = blob.download_as_bytes()
                        return (data, "image/png")
            # Prefix: look for prefix/slide_name_suffix
            for suffix in suffixes:
                blob_path = f"{path_clean}/{slide_name}{suffix}" if path_clean else f"{slide_name}{suffix}"
                blob = bucket.blob(blob_path)
                if blob.exists():
                    data = blob.download_as_bytes()
                    return (data, "image/png")
        except Exception:
            continue
    return None


@app.get("/{token}/api/thumbnail/{slide_name}")
async def serve_thumbnail(token: str, slide_name: str):
    """Serve thumbnail for a slide from overlay, slide dir, thumbnail_paths (dir/zip/direct URL), or GCS."""
    session = get_session_or_404(token)
    await resolve_overlay_zip(session)
    await resolve_thumbnail_zip(session)
    path = session.find_thumbnail(slide_name)
    if path:
        return FileResponse(path, media_type="image/png")
    loop = asyncio.get_event_loop()
    # Direct thumbnail URL (e.g. --thumbnails https://.../Head_neck_pathology_tb.png)
    direct = await loop.run_in_executor(None, _stream_thumbnail_from_direct_url, session, slide_name)
    if direct:
        content, media_type = direct
        return Response(content=content, media_type=media_type)
    # GCS prefix in thumbnail_paths
    gcs_result = await loop.run_in_executor(None, _stream_thumbnail_from_gcs, session, slide_name)
    if gcs_result:
        content, media_type = gcs_result
        return Response(content=content, media_type=media_type)
    raise HTTPException(status_code=404, detail=f"Thumbnail not found for slide: {slide_name}")


@app.get("/{token}/api/overlay-config/{slide_name}")
async def get_overlay_config(token: str, slide_name: str):
    """Get per-slide overlay configuration. Includes slide_metadata for scale (mpp, etc.) when metadata.json exists."""
    session = get_session_or_404(token)
    await resolve_overlay_zip(session)
    density = session.find_overlay_file(slide_name, '_density.png')
    metadata_path = session.find_overlay_file(slide_name, '_metadata.json')
    grid = session.find_overlay_file(slide_name, '_grid.json')
    thumb = session.find_thumbnail(slide_name)
    available = density is not None and metadata_path is not None

    thumbnail_url = f"/{token}/api/thumbnail/{slide_name}" if thumb else None
    metadata_url = f"/{token}/api/overlay-file/{slide_name}_metadata.json" if metadata_path else None

    # slide_metadata for scale (mpp → physical units). From overlay metadata.json and/or session.metadata (create session).
    # Expected keys: width, height, mpp, objective_power, vendor, thumbnail_url (all optional).
    slide_metadata = None
    if metadata_path:
        try:
            raw = Path(metadata_path).read_text(encoding='utf-8')
            data = json.loads(raw)
            slide_metadata = {
                "width": data.get("width"),
                "height": data.get("height"),
                "mpp": data.get("mpp"),
                "objective_power": data.get("objective_power"),
                "vendor": data.get("vendor"),
                "thumbnail_url": thumbnail_url,
            }
        except Exception:
            slide_metadata = {"thumbnail_url": thumbnail_url}
    if session.metadata and isinstance(session.metadata, dict):
        base = dict(session.metadata)
        base.setdefault("thumbnail_url", thumbnail_url)
        if slide_metadata:
            for k in ("width", "height", "mpp", "objective_power", "vendor"):
                if slide_metadata.get(k) is not None:
                    base[k] = slide_metadata[k]
            slide_metadata = base
        else:
            slide_metadata = base

    return {
        "available": available,
        "density_image": f"/{token}/api/overlay-file/{slide_name}_density.png" if density else None,
        "metadata": metadata_url,
        "grid": f"/{token}/api/overlay-file/{slide_name}_grid.json" if grid else None,
        "thumbnail": thumbnail_url,
        "slide_metadata": slide_metadata,
    }


@app.get("/{token}/api/overlay-file/{filename}")
async def serve_overlay_file(token: str, filename: str):
    """Serve an overlay file from overlay dir or slides dir."""
    session = get_session_or_404(token)
    await resolve_overlay_zip(session)
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
async def download_gcs_file(blob_path: str = Query(..., description="Path to blob in GCS bucket"), _: str = Depends(verify_basic_auth)):
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
async def proxy_gcs_file(blob_path: str, _: str = Depends(verify_basic_auth)):
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
async def list_gcs_files(prefix: Optional[str] = Query(None), _: str = Depends(verify_basic_auth)):
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
async def get_gcs_status(_: str = Depends(verify_basic_auth)):
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
async def get_gcs_signed_url(blob_path: str = Query(...), expiration_hours: int = Query(24), _: str = Depends(verify_basic_auth)):
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
    default_session = session_mgr.create_session(slide_paths, overlay_paths, thumbnail_paths=thumbnail_paths)

    # Start background cleanup
    await session_mgr.start_cleanup_loop(interval_minutes=5)

    is_gcs = any(is_gcs_path(p) for p in slide_paths)
    has_local = any(not is_gcs_path(p) for p in slide_paths)
    
    if is_gcs and has_local:
        mode = "Mixed (GCS + Local)"
    elif is_gcs:
        mode = "GCS"
    else:
        mode = "Local"
    
    print("=" * 60)
    print("WSI Viewer Server - GeoTIFFTileSource Streaming")
    print("=" * 60)
    print(f"Mode: {mode}")
    print(f"Slide paths ({len(slide_paths)}):")
    for i, path in enumerate(slide_paths, 1):
        print(f"  {i}. {path}")
    if overlay_paths:
        print(f"Overlay paths ({len(overlay_paths)}):")
        for i, path in enumerate(overlay_paths, 1):
            print(f"  {i}. {path}")
    if thumbnail_paths:
        print(f"Thumbnail paths ({len(thumbnail_paths)}):")
        for i, path in enumerate(thumbnail_paths, 1):
            print(f"  {i}. {path}")
    print(f"Default session: http://localhost:{PORT}/{default_session.token}/")
    print(f"Create new sessions: POST http://localhost:{PORT}/api/sessions")
    print(f"API docs: http://localhost:{PORT}/docs")
    print(f"Session TTL: {args.session_ttl} minutes")
    print(f"GCS Client: {'✓ Available' if gcs_client else '✗ Not available'}")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Stop the cleanup loop."""
    session_mgr.stop_cleanup_loop()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=True)
