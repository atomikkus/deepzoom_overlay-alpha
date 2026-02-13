# GeoTIFFTileSource Implementation - Local & GCS Support

## Overview

This implementation uses [GeoTIFFTileSource](https://github.com/pearcetm/GeoTIFFTileSource) for efficient client-side streaming of SVS/TIFF files via HTTP range requests. **Works with both local files and GCS buckets.**

## Key Features

### 1. **No OpenSlide/DZI Conversion Needed**
- Removed all OpenSlide and PIL dependencies
- No server-side tile generation required
- GeoTIFFTileSource handles everything in the browser

### 2. **Efficient Range Request Streaming**
- Only downloads the parts of the file currently being viewed
- Works for multi-GB files without downloading entire file
- Backend acts as CORS-friendly proxy

### 3. **Dual Support: Local + GCS**
Following GeoTIFFTileSource documentation:
> "GeoTIFFTileSource accepts both local and remote GeoTIFF files"

#### Local Files
```bash
python app.py --slides /path/to/slides/
python app.py --slides /path/to/slide.svs
```

#### GCS Files (Public Buckets)
```bash
python app.py --slides gs://bucket/path/slide.svs
python app.py --slides https://storage.googleapis.com/bucket/path/slide.svs
python app.py --slides gs://bucket/folder/
```

### 4. **Cancer Density Overlay Preserved**
All overlay functionality remains intact:
- `GET /{token}/api/overlay-config/{slide_name}`
- `GET /{token}/api/overlay-file/{filename}`
- Density heatmap visualization
- Grid-based cell counting

## Architecture

```
┌─────────────┐              ┌──────────────┐              ┌──────────────┐
│   Browser   │              │   Backend    │              │ Local / GCS  │
│ GeoTIFFTile │              │   (FastAPI)  │              │              │
│   Source    │              │              │              │              │
└─────────────┘              └──────────────┘              └──────────────┘
       │                            │                             │
       │ 1. Load slide info         │                             │
       ├───────────────────────────>│                             │
       │   GET /api/info/slide1     │                             │
       │<───────────────────────────┤                             │
       │   { properties, size }     │                             │
       │                            │                             │
       │ 2. Request via range       │                             │
       ├───────────────────────────>│ 3. Proxy/serve with range   │
       │   Range: bytes=1000-2000   ├────────────────────────────>│
       │                            │<────────────────────────────┤
       │<───────────────────────────┤   206 Partial Content       │
       │   206 + CORS headers       │                             │
       │                            │                             │
       │ 4. Repeat for each tile    │                             │
       ├───────────────────────────>├────────────────────────────>│
```

## Simplified Dependencies

### requirements.txt
```
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6
google-cloud-storage>=2.10.0
pydantic>=2.0.0
```

**Removed:**
- ~~openslide-python~~
- ~~Pillow~~
- ~~openslide_bin~~

## Frontend Flow

1. **Load Slide**: `GET /api/info/{slide_name}` returns metadata
2. **Detect Format**: All SVS/TIFF files use GeoTIFFTileSource
3. **Stream via Range Requests**: 
   ```javascript
   const rawSlideUrl = `${API_BASE}/api/raw_slides/${filename}`;
   await OpenSeadragon.GeoTIFFTileSource.getAllTileSources(rawSlideUrl, {
       logLatency: true,
       useRangeRequests: true
   });
   ```

## Backend Endpoints

### Slide Operations
- `GET /{token}/api/slides` - List slides (local or GCS)
- `GET /{token}/api/info/{slide_name}` - Get slide metadata
- `GET /{token}/api/raw_slides/{filename}` - **Range request proxy** (CORS-enabled)

### Overlay Operations (Preserved)
- `GET /{token}/api/overlay-config/{slide_name}` - Get overlay config
- `GET /{token}/api/overlay-file/{filename}` - Serve overlay files

### Removed (No longer needed)
- ~~POST /{token}/api/convert/{slide_name}~~ - No conversion needed
- ~~GET /{token}/api/dynamic_dzi/{slide_name}.dzi~~ - GeoTIFFTileSource replaces DZI
- ~~GET /{token}/api/tiles/{slide_name}/{level}/{col}_{row}.{format}~~ - Client-side tiling

## GCS Anonymous Access

For public GCS buckets, the backend automatically uses anonymous client:

```python
if os.path.exists(GCS_SERVICE_ACCOUNT_PATH):
    gcs_client = storage.Client(credentials=...)
else:
    gcs_client = storage.Client.create_anonymous_client()
```

## Testing

### Local Files
```bash
python app.py --slides /path/to/slides/
# Visit: http://localhost:8511/{token}/
```

### Public GCS Bucket
```bash
python app.py --slides https://storage.googleapis.com/wsi_viewer_test/TCGA-C5-A7CM-01Z-00-DX1.A1886113-2505-4EE3-8170-389AB304EE6C.svs
# Visit: http://localhost:8511/{token}/
```

Check browser DevTools Network tab for:
- Multiple small range requests (KB-MB each)
- `206 Partial Content` responses
- `Range: bytes=...` request headers

## Performance

### Before (with OpenSlide/DZI)
- Full file download + conversion: 30-300 seconds
- Large disk cache required
- Heavy server CPU/memory usage

### After (GeoTIFFTileSource)
- Initial load: ~1-2 seconds (metadata only)
- Per-tile: ~50-200ms (only requested bytes)
- No disk cache needed
- Minimal server resources

## What Was Removed

1. ✅ All OpenSlide/PIL code
2. ✅ DeepZoom tile generation
3. ✅ DZI conversion endpoints
4. ✅ Tile cache management
5. ✅ Heavy dependencies

## What Was Kept

1. ✅ Session management
2. ✅ Cancer density overlays
3. ✅ Slide listing
4. ✅ GCS support (enhanced with anonymous client)
5. ✅ Local file support
6. ✅ CORS handling
