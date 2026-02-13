# GCS Support Architecture for CORS

## Overview

This implementation adds support for Google Cloud Storage (GCS) bucket paths in the `--slides` parameter, enabling efficient viewing of remote slide files without downloading entire files to the server.

## Key Principle: Client-Side Range Requests

Following the [GeoTIFFTileSource](https://github.com/pearcetm/GeoTIFFTileSource) library design, this implementation uses **HTTP range requests** to stream only the needed parts of large TIFF/SVS files directly from the backend to the browser.

### Why This Matters

- **Efficient**: Only downloads the tiles/regions currently being viewed
- **Fast**: No need to download entire multi-GB files before viewing
- **Scalable**: Backend acts as a CORS-friendly proxy without storing full files

## Architecture

```
┌─────────────┐                    ┌──────────────┐                   ┌──────────────┐
│   Browser   │                    │   Backend    │                   │  GCS Bucket  │
│             │                    │   (FastAPI)  │                   │              │
└─────────────┘                    └──────────────┘                   └──────────────┘
       │                                   │                                  │
       │ 1. Load slide                     │                                  │
       ├──────────────────────────────────>│                                  │
       │   GET /api/info/slide1            │                                  │
       │                                   │ 2. Download for OpenSlide        │
       │                                   │  (metadata reading only)         │
       │                                   ├─────────────────────────────────>│
       │                                   │<─────────────────────────────────┤
       │<──────────────────────────────────┤                                  │
       │   { dimensions, properties,       │                                  │
       │     slide_source: "gcs" }         │                                  │
       │                                   │                                  │
       │ 3. Load with GeoTIFFTileSource    │                                  │
       │    URL: /api/raw_slides/file.svs  │                                  │
       │                                   │                                  │
       │ 4. Range request for tile data    │                                  │
       ├──────────────────────────────────>│                                  │
       │   Range: bytes=1000-2000          │ 5. Proxy range request           │
       │                                   ├─────────────────────────────────>│
       │                                   │<─────────────────────────────────┤
       │<──────────────────────────────────┤   206 Partial Content            │
       │   206 Partial Content             │                                  │
       │   + CORS headers                  │                                  │
       │                                   │                                  │
       │ 6. Repeat for each visible tile   │                                  │
       ├──────────────────────────────────>│                                  │
       │   Range: bytes=3000-4000          ├─────────────────────────────────>│
       │<──────────────────────────────────┤<─────────────────────────────────┤
```

## Implementation Details

### Backend (`app.py`)

1. **Session Creation** (`create_session`)
   - Accepts GCS URIs: `gs://bucket/path/file.svs`, `https://storage.googleapis.com/bucket/path/file.svs`
   - Parses bucket name and blob path
   - Sets `single_slide` for direct file paths

2. **Slide Info** (`get_slide_info`)
   - Downloads file to local cache **only when needed** (for OpenSlide metadata reading)
   - Adds `slide_source: "gcs"` to response so frontend knows to use range requests

3. **Raw Slides Endpoint** (`serve_raw_slide`)
   - For GCS files: proxies range requests directly to GCS
   - Returns proper CORS headers:
     - `Access-Control-Allow-Origin: *`
     - `Access-Control-Expose-Headers: Content-Range, Accept-Ranges`
     - `Accept-Ranges: bytes`
   - Handles both full file and partial content (206) responses

4. **Tile/Conversion Operations** (`convert_slide`, `serve_tile`)
   - Downloads to cache only when needed for DeepZoom tile generation
   - Uses cached file for OpenSlide operations

### Frontend (`viewer.js`)

1. **Detection**: Checks `slideInfo.properties.slide_source === 'gcs'`

2. **GeoTIFFTileSource**: For GCS files, uses direct viewing:
   ```javascript
   const rawSlideUrl = `${API_BASE}/api/raw_slides/${slide.filename}`;
   await OpenSeadragon.GeoTIFFTileSource.getAllTileSources(rawSlideUrl, {
       logLatency: true,
       useRangeRequests: true
   });
   ```

3. **Benefits**:
   - No full file download
   - Efficient streaming via HTTP range requests
   - CORS handled by backend proxy

## Supported GCS Path Formats

```bash
# Direct file URLs
--slides https://storage.googleapis.com/bucket_name/path/to/slide.svs
--slides https://storage.cloud.google.com/bucket_name/path/to/slide.svs

# GCS URIs
--slides gs://bucket_name/path/to/slide.svs

# Folder/prefix paths (lists all slides in prefix)
--slides gs://bucket_name/path/to/folder/
--slides https://storage.googleapis.com/bucket_name/path/to/folder/
```

## CORS Requirements

The backend (`/{token}/api/raw_slides/{filename}`) provides:

- **Preflight support**: `OPTIONS` handler with proper CORS headers
- **Range request support**: Handles `Range: bytes=start-end` header
- **Proper headers**:
  - `Accept-Ranges: bytes`
  - `Content-Range: bytes start-end/total`
  - `Access-Control-Allow-Origin: *`
  - `Access-Control-Allow-Headers: Range, Content-Type, Accept`
  - `Access-Control-Expose-Headers: Content-Length, Content-Range, Accept-Ranges`

## Performance Characteristics

### With This Implementation (Range Requests)
- Initial load: ~1-2 seconds (metadata only)
- Per-tile load: ~50-200ms (only requested tiles)
- Total data transferred: ~5-50 MB (depends on zoom/pan)

### Without Range Requests (Full Download)
- Initial load: 30-300 seconds (full file download)
- Per-tile load: instant (from cache)
- Total data transferred: entire file size (often 1-10 GB)

## Testing

Test with the example file:
```bash
python app.py --slides https://storage.googleapis.com/wsi_viewer_test/TCGA-C5-A7CM-01Z-00-DX1.A1886113-2505-4EE3-8170-389AB304EE6C.svs
```

Check browser DevTools Network tab for:
- Multiple small range requests (KB to MB each)
- `206 Partial Content` responses
- `Range: bytes=...` request headers
- `Content-Range: bytes ...` response headers
