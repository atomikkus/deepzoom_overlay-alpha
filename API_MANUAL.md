# WSI Viewer – API Manual

This document describes the HTTP API for the WSI (Whole Slide Imaging) Viewer. Use it to create sessions, list and stream slides, manage overlays, and interact with Google Cloud Storage.

---

## Table of Contents

1. [Base URL and Conventions](#1-base-url-and-conventions)
2. [Authentication](#2-authentication)
3. [Health Check](#3-health-check)
4. [Session Management](#4-session-management)
5. [Session-Scoped Static Assets](#5-session-scoped-static-assets)
6. [Slides API](#6-slides-api)
7. [Raw Slide Streaming](#7-raw-slide-streaming)
8. [Overlay API](#8-overlay-api)
9. [GCS Endpoints](#9-gcs-endpoints)
10. [Error Reference](#10-error-reference)
11. [Examples](#11-examples)

---

## 1. Base URL and Conventions

- **Base URL:** `http://localhost:8511` (or your deployment host/port).
- **Authentication:** Only **global API** (session create/list/delete, heartbeat, GCS) requires HTTP Basic Auth. **Session viewer** routes `/{token}/...` do not; the token in the URL is the credential.
- **Path parameters:** `{token}` is a session UUID; `{slide_name}` is the slide filename without extension; `{filename}` is the full filename.
- **JSON:** Request bodies and many responses are JSON; `Content-Type: application/json` for POST bodies.
- **Allowed slide extensions:** `svs`, `tif`, `tiff`, `vms`, `vmu`, `ndpi`, `scn`, `mrxs`, `svslide`, `bif`.

---

## 2. Authentication

**Global API** (create session, list/delete sessions, heartbeat, GCS) requires **HTTP Basic Auth**. **Session viewer** (`/{token}/`, `/{token}/api/slides`, overlay, raw slide streaming, etc.) does **not** require auth — the session token in the URL is sufficient. Share `https://host/{token}/` and the recipient can view without a password.

| When | Auth |
|------|------|
| **Global API** (e.g. `POST /api/sessions`, `GET /api/sessions`, GCS) | Required: `curl -u USERNAME:PASSWORD`, or `Authorization: Basic ...` |
| **Session URLs** (`/{token}/`, `/{token}/api/slides`, etc.) | Not required; token in path is the credential. |

Default credentials for global API (override with env vars `AUTH_USERNAME` and `AUTH_PASSWORD`):

- **Username:** `satya@4basecare.com`
- **Password:** `satya123`

See [DOCS/AUTH.md](DOCS/AUTH.md) for configuration and security details.

---

## 3. Health Check

**`GET /health`** — No authentication.

Used by load balancers and orchestrators (e.g. Cloud Run, GKE). Returns `200 OK` with `{"status": "ok"}`.

---

## 4. Session Management

Sessions are created with a list of slide paths (GCS and/or local) and optional overlay paths. Each session has a unique **token** used in all session-scoped URLs.

### 3.1 Create session

**`POST /api/sessions`**

Creates a new viewer session with the given slide and overlay paths.

**Request body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slides` | array of strings | Yes | List of slide paths: GCS URIs (`gs://bucket/path` or `https://storage.googleapis.com/...`) and/or local paths. Can be files or directories. |
| `overlay` | array of strings | No | Overlay sources: local directory, local `.zip` path, or http(s) URL to a `.zip` (e.g. signed URL). Zips are downloaded/extracted once per session; overlay files are searched in the extracted dir (and in plain dirs). |

**Example request (directories):**

```json
{
  "slides": ["/path/to/local/slides"],
  "overlay": ["/path/to/overlays"]
}
```

**Example request (overlay from zip URL):**

```json
{
  "slides": ["https://storage.googleapis.com/bucket/slide.svs"],
  "overlay": ["https://storage.googleapis.com/bucket/overlays.zip?X-Goog-Signature=..."]
}
```

**Response:** `200 OK`

```json
{
  "token": "550e8400-e29b-41d4-a716-446655440000",
  "url": "/550e8400-e29b-41d4-a716-446655440000/",
  "slide_paths": ["gs://my-bucket/slides/slide1.svs", "..."],
  "overlay_paths": ["/path/to/overlays"]
}
```

**Errors:**

| Code | Condition |
|------|-----------|
| 400 | A path in `slides` is local and does not exist. |
| 401 | Missing or invalid Basic Auth. |

---

### 3.2 List sessions

**`GET /api/sessions`**

Returns all active sessions (created at server start or via this API).

**Response:** `200 OK`

```json
{
  "sessions": [
    {
      "token": "550e8400-e29b-41d4-a716-446655440000",
      "slide_paths": ["gs://bucket/path/"],
      "overlay_paths": ["/overlays"],
      "created_at": "2025-02-13T10:00:00",
      "last_accessed": "2025-02-13T10:15:00"
    }
  ]
}
```

---

### 3.3 Delete session

**`DELETE /api/sessions/{token}`**  
**`POST /api/sessions/{token}/delete`**

Deletes the session identified by `token`.

**Response:** `200 OK`

```json
{
  "deleted": true
}
```

If the session did not exist, `deleted` is `false` (still 200).

---

### 3.4 Heartbeat

**`POST /api/sessions/{token}/heartbeat`**

Updates the session’s last-accessed time to prevent TTL expiry.

**Response:** `200 OK`

```json
{
  "status": "ok",
  "last_accessed": "2025-02-13T10:20:00"
}
```

**Errors:**

| Code | Condition |
|------|-----------|
| 404 | Session not found or expired. |

---

## 5. Session-Scoped Static Assets

These endpoints serve the viewer UI and assets for a given session. The session must exist.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/{token}/` | Viewer HTML (`index.html`) |
| GET | `/{token}/styles.css` | Stylesheet |
| GET | `/{token}/viewer.js` | Viewer application script |

**Response:** `200 OK` with the file content; `Content-Type` set appropriately.

**Errors:** `404` if the session token is invalid or expired.

---

## 6. Slides API

All slide endpoints are under `/{token}/api/` and require only a valid session token (no HTTP Basic Auth).

### 5.1 List slides

**`GET /{token}/api/slides`**

Lists all slides available in the session (from all configured slide paths, deduplicated by filename).

**Response:** `200 OK`

```json
{
  "slides": [
    {
      "name": "slide1",
      "filename": "slide1.svs",
      "size": 1234567890,
      "viewable": true
    }
  ]
}
```

- `name`: Basename without extension.
- `filename`: Full filename (with extension).
- `size`: File size in bytes (0 for some GCS listings if not loaded).
- `viewable`: Always `true` when listed (GeoTIFFTileSource can stream these).

**Errors:** `404` if session not found; `500` on server error.

---

### 5.2 Get slide info

**`GET /{token}/api/info/{slide_name}`**

Returns metadata for the slide. `slide_name` is the stem (e.g. `slide1` for `slide1.svs`).

**Response:** `200 OK`

**For a GCS slide:**

```json
{
  "filename": "slide1.svs",
  "size": 1234567890,
  "content_type": "image/tiff",
  "updated": "2025-01-01T00:00:00",
  "properties": {
    "slide_source": "gcs",
    "bucket": "my-bucket",
    "path": "slides/slide1.svs"
  },
  "dimensions": [0, 0],
  "level_count": 1
}
```

**For a local slide:**

```json
{
  "filename": "slide1.svs",
  "size": 1234567890,
  "properties": {
    "slide_source": "local",
    "path": "/path/to/slide1.svs"
  },
  "dimensions": [0, 0],
  "level_count": 1
}
```

**Errors:**

| Code | Condition |
|------|-----------|
| 404 | Slide not found in any configured path. |

---

### 5.3 Upload file

**`POST /{token}/api/upload`**

Uploads a slide file into the session’s first local slide path. Not supported for GCS-only sessions.

**Request:** `multipart/form-data` with a file field named `file`.

**Response:** `200 OK`

```json
{
  "success": true,
  "filename": "uploaded.svs",
  "name": "uploaded"
}
```

**Errors:**

| Code | Condition |
|------|-----------|
| 400 | No file, unsupported type, or GCS-only session. |
| 404 | Session not found. |

---

### 5.4 Delete slide

**`DELETE /{token}/api/delete/{slide_name}`**

Deletes the slide from the first local path where it is found. Not supported for GCS-backed slides.

**Response:** `200 OK`

```json
{
  "success": true,
  "message": "Slide deleted"
}
```

**Errors:**

| Code | Condition |
|------|-----------|
| 404 | Slide not found or only exists in GCS. |

---

## 7. Raw Slide Streaming

The viewer streams slide files (e.g. SVS/TIFF) via range requests. These endpoints support CORS and `Accept-Ranges: bytes` for GeoTIFFTileSource and similar clients.

Base path: **`/{token}/api/raw_slides/{filename}`**  
`filename` is the full filename (e.g. `slide1.svs`).

### 6.1 OPTIONS (CORS preflight)

**`OPTIONS /{token}/api/raw_slides/{filename:path}`**

Returns CORS and range-request headers. No body. Use for preflight before GET/HEAD.

---

### 6.2 HEAD (metadata)

**`HEAD /{token}/api/raw_slides/{filename:path}`**

Returns headers only: file size and content type. Used by the client to discover size and support range requests.

**Response headers (typical):**

- `Content-Length`: file size in bytes  
- `Content-Type`: e.g. `image/tiff` for `.svs`/`.tif`  
- `Accept-Ranges`: `bytes`

**Errors:** `404` if session or file not found.

---

### 6.3 GET (full or range)

**`GET /{token}/api/raw_slides/{filename:path}`**

Streams the file. Clients should send a `Range` header for partial content.

**Request header (optional):**

- `Range: bytes=START-END` — inclusive byte range (e.g. `bytes=0-65535`).

**Response:**

- **With valid Range:** `206 Partial Content`  
  - `Content-Range: bytes START-END/TOTAL`  
  - Body: bytes in that range.
- **Without Range:** `200 OK` with full file body.

**Response headers (typical):**

- `Content-Type`: e.g. `image/tiff`  
- `Accept-Ranges: bytes`  
- `Access-Control-*`: CORS headers for browser clients  

**Errors:**

| Code | Condition |
|------|-----------|
| 404 | Session or file not found. |
| 416 | Range not satisfiable (e.g. start beyond file size). |
| 403 | Path traversal / access denied (local files). |

---

## 8. Overlay API

Overlays (e.g. density maps) are per-slide files: `{slide_name}_density.png`, `{slide_name}_metadata.json`, `{slide_name}_grid.json`. Overlay sources can be:

- **Local directory** — files at `dir/{slide_name}_density.png`, etc.
- **Local or URL .zip** — archive is extracted once per session; files are looked up at the extracted root or inside a single top-level folder (e.g. `SlideName/SlideName_density.png`).

The API exposes config and file URLs, then serves the files via the overlay endpoints below.

### 7.1 Overlay config

**`GET /{token}/api/overlay-config/{slide_name}`**

Returns whether overlay data exists for the slide and relative URLs to the overlay image and JSON files.

**Response:** `200 OK`

```json
{
  "available": true,
  "density_image": "/{token}/api/overlay-file/slide1_density.png",
  "metadata": "/{token}/api/overlay-file/slide1_metadata.json",
  "grid": "/{token}/api/overlay-file/slide1_grid.json"
}
```

If overlay files are missing, `available` is `false` and the URL fields may be `null`.

**Errors:** `404` if session not found.

---

### 7.2 Overlay file

**`GET /{token}/api/overlay-file/{filename}`**

Serves a single overlay file. `filename` must end with one of: `_density.png`, `_metadata.json`, `_grid.json`.

**Response:** `200 OK` with body:

- PNG: binary image, `Content-Type: image/png`
- JSON: `Content-Type: application/json`

**Errors:** `404` if the overlay file is not found for the session.

---

## 9. GCS Endpoints

These endpoints are **global** (not session-scoped) and use the server’s GCS configuration (bucket name, credentials). They are intended for listing, downloading, proxying, and signing blobs in that bucket.

### 8.1 Download from GCS to local

**`POST /api/gcs/download?blob_path=...`**

Downloads a blob from the configured GCS bucket into the server’s `uploads` directory.

**Query parameters:**

| Name | Required | Description |
|------|----------|-------------|
| `blob_path` | Yes | Path inside the bucket (e.g. `folder/slide.svs`). Can also be a full URL containing the bucket name; the path after the bucket is used. |

**Response:** `200 OK`

```json
{
  "success": true,
  "filename": "slide.svs",
  "name": "slide",
  "size": 1234567890,
  "downloaded": true
}
```

If the file already exists locally:

```json
{
  "success": true,
  "filename": "slide.svs",
  "name": "slide",
  "message": "File already exists locally",
  "downloaded": false
}
```

**Errors:**

| Code | Condition |
|------|-----------|
| 404 | Blob not found in bucket. |
| 503 | GCS not available or client not initialized. |

---

### 8.2 Proxy GCS file

**`GET /api/gcs/proxy/{blob_path:path}`**

Streams a GCS blob through the server (e.g. to avoid CORS). The full path after `/api/gcs/proxy/` is the blob path. URL segments are allowed.

**Response:** `200 OK` with blob content and appropriate `Content-Type` and `Content-Disposition`.

**Errors:** `404` if blob not found; `503` if GCS not available.

---

### 8.3 List GCS files

**`GET /api/gcs/files?prefix=...`**

Lists WSI files (by extension) in the configured bucket, optionally under a prefix.

**Query parameters:**

| Name | Required | Description |
|------|----------|-------------|
| `prefix` | No | Blob prefix (e.g. `slides/`). |

**Response:** `200 OK`

```json
{
  "files": [
    {
      "name": "slide1.svs",
      "path": "slides/slide1.svs",
      "size": 1234567890,
      "updated": "2025-01-01T00:00:00"
    }
  ]
}
```

**Errors:** `503` if GCS not available.

---

### 8.4 GCS status

**`GET /api/gcs/status`**

Returns whether GCS is available and how it is configured.

**Response:** `200 OK`

```json
{
  "available": true,
  "library_installed": true,
  "credentials_found": true,
  "client_initialized": true,
  "bucket_name": "my-bucket",
  "error": null
}
```

When not available, `available` is `false` and `error` describes the reason (e.g. library not installed, credentials not found, client failed to initialize).

---

### 8.5 Signed URL

**`GET /api/gcs/signed-url?blob_path=...&expiration_hours=...`**

Generates a time-limited signed URL for a blob.

**Query parameters:**

| Name | Required | Default | Description |
|------|----------|---------|-------------|
| `blob_path` | Yes | — | Path inside the bucket. |
| `expiration_hours` | No | 24 | URL validity in hours. |

**Response:** `200 OK`

```json
{
  "success": true,
  "signed_url": "https://storage.googleapis.com/...",
  "filename": "slide.svs",
  "name": "slide",
  "expires_at": "2025-02-14T10:00:00",
  "is_directly_viewable": true
}
```

`is_directly_viewable` is `true` for `.svs`, `.tif`, `.tiff` (client can stream via GeoTIFFTileSource if CORS allows).

**Errors:** `404` if blob not found; `503` if GCS not available.

---

## 10. Error Reference

| HTTP Code | Meaning |
|-----------|---------|
| 400 | Bad request (e.g. invalid body, path not found for create session, unsupported upload). |
| 401 | Unauthorized — missing or invalid HTTP Basic credentials (global API only). |
| 403 | Forbidden — e.g. raw slide path not under allowed directories. |
| 404 | Not found — session, slide, overlay file, or GCS blob. |
| 416 | Range not satisfiable — invalid or out-of-range byte range for raw slide. |
| 500 | Internal server error — exception message may be in response body. |
| 503 | Service unavailable — e.g. GCS library missing or client not initialized. |

Error responses are JSON when the client accepts JSON, for example:

```json
{
  "detail": "Session not found or expired"
}
```

For 401, the response includes a `WWW-Authenticate: Basic` header so browsers can show a login dialog.

---

## 11. Examples

### 10.1 cURL

```bash
# Create session (GCS + local)
curl -u satya@4basecare.com:satya123 -X POST http://localhost:8511/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "slides": [
      "https://storage.googleapis.com/bucket/slide1.svs",
      "/path/to/local/slides"
    ],
    "overlay": ["/path/to/overlays"]
  }'

# List slides in session (no auth — token in URL is enough)
curl "http://localhost:8511/TOKEN/api/slides"

# Get overlay config for a slide
curl "http://localhost:8511/TOKEN/api/overlay-config/slide1"

# HEAD raw slide (for range requests)
curl -I "http://localhost:8511/TOKEN/api/raw_slides/slide1.svs"

# Download from GCS to server
curl -u satya@4basecare.com:satya123 -X POST \
  "http://localhost:8511/api/gcs/download?blob_path=path/to/slide.svs"
```

### 10.2 Python

```python
import requests
from requests.auth import HTTPBasicAuth

BASE = "http://localhost:8511"
AUTH = HTTPBasicAuth("satya@4basecare.com", "satya123")

# Create session
r = requests.post(
    f"{BASE}/api/sessions",
    json={
        "slides": ["gs://bucket/slides/", "/local/slides"],
        "overlay": ["/local/overlays"],
    },
    auth=AUTH,
)
r.raise_for_status()
data = r.json()
token = data["token"]
print("Session URL:", f"{BASE}/{token}/")

# List slides (session URL — no auth needed)
r = requests.get(f"{BASE}/{token}/api/slides")
r.raise_for_status()
slides = r.json()["slides"]
for s in slides:
    print(s["filename"], s["size"])

# Get slide info
r = requests.get(f"{BASE}/{token}/api/info/slide1")
r.raise_for_status()
info = r.json()
print(info["properties"]["slide_source"], info["filename"])

# Stream raw slide (first 64KB)
r = requests.get(
    f"{BASE}/{token}/api/raw_slides/slide1.svs",
    headers={"Range": "bytes=0-65535"},
)
print(r.status_code, len(r.content))  # 206, 65536
```

### 10.3 JavaScript (browser)

Session URLs do not require auth; the token in the path is enough. Use plain `fetch` (optionally `credentials: 'include'` for same-origin):

```javascript
const base = 'http://localhost:8511';
const token = '550e8400-e29b-41d4-a716-446655440000';

// List slides
const res = await fetch(`${base}/${token}/api/slides`);
const { slides } = await res.json();

// Overlay config
const configRes = await fetch(`${base}/${token}/api/overlay-config/slide1`);
const config = await configRes.json();
if (config.available) {
  const metaRes = await fetch(`${base}${config.metadata}`);
  const metadata = await metaRes.json();
}
```

### 10.4 Typical viewer flow

1. **Create session** — `POST /api/sessions` with slide and overlay paths (requires Basic Auth).
2. **Open viewer** — Navigate to `/{token}/`; no login — the session URL is the credential.
3. **List slides** — Frontend calls `GET /{token}/api/slides` and displays the list.
4. **Load slide** — Client uses `/{token}/api/raw_slides/{filename}` with range requests (e.g. via GeoTIFFTileSource).
5. **Overlays** — `GET /{token}/api/overlay-config/{slide_name}` then fetch `density_image`, `metadata`, and `grid` URLs as needed.
6. **Keep session alive** — Periodically `POST /api/sessions/{token}/heartbeat`.

---

For authentication setup and security, see [DOCS/AUTH.md](DOCS/AUTH.md).  
For server usage and CLI options, see [USAGE.md](USAGE.md).
