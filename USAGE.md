# Usage Guide

## Running the Server

### For GCS Files (Remote)
```bash
# Single GCS file
python app.py --slides gs://wsi_viewer_test/TCGA-C5-A7CM-01Z-00-DX1.A1886113-2505-4EE3-8170-389AB304EE6C.svs

# Or with HTTPS URL
python app.py --slides https://storage.googleapis.com/wsi_viewer_test/TCGA-C5-A7CM-01Z-00-DX1.A1886113-2505-4EE3-8170-389AB304EE6C.svs

# GCS folder
python app.py --slides gs://my-bucket/slides-folder/
```

### For Local Files
```bash
# Local directory
python app.py --slides-local /path/to/slides/

# Single local file
python app.py --slides-local /path/to/slide.svs

# With overlay directory
python app.py --slides-local /path/to/slides/ --overlay /path/to/overlays/
```

### Default (No Arguments)
```bash
# Uses local "uploads" directory by default
python app.py
```

## How It Works

### Local Files
1. Files served directly from local filesystem
2. Range requests handled by Python file I/O
3. No download needed - instant access

### GCS Files
1. Files streamed from Google Cloud Storage
2. Range requests proxied through backend
3. Only requested byte ranges are downloaded
4. Works with public buckets (no credentials needed)
5. For private buckets, set `GCS_SERVICE_ACCOUNT_PATH` env var

## Browser Access

After starting the server, you'll see:
```
============================================================
WSI Viewer Server - GeoTIFFTileSource Streaming
============================================================
Mode: Local (or GCS)
Slides: /path/to/slides (or gs://bucket/path)
Default session: http://localhost:8511/4d8be0cd-.../
...
============================================================
```

Open the URL in your browser to view slides!

## Checking Logs

The server logs will show:
- `Local file size: 123456789` - File size detected
- `Local Range: bytes=0-1000 | Size: 123456789 | Start: 0, End: 1000` - Range request received
- `✅ Valid range, reading bytes 0-1000` - Processing range
- `✅ Read 1001 bytes` - Completed successfully

Or for GCS:
- `GCS file size: 123456789`
- `GCS Range: bytes=0-1000 | ...`
- `✅ Downloaded 1001 bytes`

If you see `❌ Invalid: ...` then there's a range calculation bug.

## Troubleshooting

### Local Files Not Working
1. Check the path exists: `ls -la /path/to/slides/`
2. Check file permissions: `ls -l /path/to/slides/*.svs`
3. Look for error logs in terminal
4. Check browser DevTools Console for errors

### GCS Files Not Working
1. Verify GCS client initialized: Look for `✓ GCS anonymous client initialized`
2. Check the file exists: `gsutil ls gs://bucket/path/file.svs`
3. Ensure bucket is public OR credentials are set
4. Check for 403/404 errors in browser DevTools Network tab

### Range Request Errors (416)
- This usually means `blob.size` is returning 0 or None
- The `blob.reload()` call should fix this
- Check logs for actual file size

## Performance

### Local Files
- First tile: ~50-100ms
- Subsequent tiles: ~20-50ms
- Total load time: ~1-2 seconds

### GCS Files  
- First tile: ~200-500ms (network latency)
- Subsequent tiles: ~100-300ms
- Total load time: ~2-5 seconds

Both modes stream efficiently - only visible tiles are loaded!
