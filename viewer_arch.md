# WSI Viewer — Architecture & integration reference

Architecture and integration reference for the WSI viewer’s URL-only entry point. The integrating application opens the viewer via a single URL; no prior API call is required. The viewer creates or reuses a session from the query parameters.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11, FastAPI, uvicorn (ASGI) |
| **HTTP client** | httpx (async) for external API (login, pathology images) |
| **Validation / config** | pydantic, python-multipart |
| **Storage (optional)** | google-cloud-storage for GCS slide/thumbnail paths |
| **Frontend** | Vanilla JavaScript (no framework) |
| **Viewer** | OpenSeadragon 4.1 (zoom/pan, tile loading) |
| **Raster tiles** | geotiff-tilesource (GeoTIFF / COG) |
| **UI** | HTML5, CSS3, Google Fonts |

The backend serves static assets (index.html, viewer.js, styles.css, logo.svg) and REST endpoints for slides, thumbnails, raw slide files, and overlay config. The external pathology API is invoked server-side (login + fetch by patient/event/slide); credentials are read from `integrate_config.json` or environment variables.

---

## System design

A diagram is provided in **viewer_system_design.drawio** (open with [draw.io](https://app.diagrams.net/) or VS Code draw.io extension). Below is an ASCII sketch of the same.

### Components

```
┌─────────────────────┐     GET /wsi-viewer/?patient_id=...&event_id=...&selected_slide_id=...
│  Integrating app     │ ────────────────────────────────────────────────────────────────────►
│  (e.g. EMR / portal) │
└─────────────────────┘
          │
          │  User opens URL (same tab / new tab / iframe)
          ▼
┌─────────────────────┐     GET /wsi-viewer/...   GET /wsi-viewer/api/slides?...   GET /wsi-viewer/api/raw_slides/...
│  Browser            │ ◄──────────────────────  ◄──────────────────────────────  ◄────────────────────────────────
│  (viewer UI)        │     HTML, CSS, JS         JSON (slide list)               binary (slide / tiles)
└─────────────────────┘
          │
          ▼
┌─────────────────────┐     get_or_create_wsi_session() → on miss: login + GET pathology_image/all
│  WSI Viewer backend  │ ─────────────────────────────────────────────────────────────────────►
│  (FastAPI + uvicorn) │                                                                        │
│  In-memory sessions  │ ◄────────────────────────────────────────────────────────────────────  │
│  Key: pid_<pid>_     │     JSON (blocks, slides, slide_url, thumbnail_url, tca_url)          │
│  <eid>_<slide_id>    │                                                                        ▼
└─────────────────────┘                              ┌─────────────────────┐
          │                                           │  External API       │
          │  (optional) GCS / signed URLs             │  (pathology / EMR)  │
          ▼                                           │  POST /user/login   │
┌─────────────────────┐                               │  GET pathology_    │
│  Google Cloud       │                               │    image/all        │
│  Storage (optional) │                               └─────────────────────┘
└─────────────────────┘
```

### Request flow

1. User follows a link to  
   `https://<viewer-host>/wsi-viewer/?patient_id=<uuid>&event_id=<id>&selected_slide_id=<sid>`.
2. Browser sends `GET /wsi-viewer/` with those query parameters.
3. Backend runs `get_or_create_wsi_session(patient_id, event_id, selected_slide_id)`:
   - Derives internal key `pid_<pid>_<eid>_<sid>` (slugified).
   - If a session exists in memory, returns it.
   - Otherwise: calls the external API (login, then pathology images for that triple), builds the slide list, creates a session in memory, returns it.
4. Backend responds with **index.html** (200). Browser loads HTML, then viewer.js, styles.css, etc. under `/wsi-viewer/`.
5. viewer.js detects path segment `wsi-viewer`, sets `API_BASE='/wsi-viewer'` and `API_QUERY` from the current URL. It then issues:
   - `GET /wsi-viewer/api/slides?patient_id=...&event_id=...&selected_slide_id=...` for the slide list and default slide.
   - `GET /wsi-viewer/api/raw_slides/<file>` (and tile URLs) with the same query params for the chosen slide.
   - Same query params for thumbnails, overlay-config, and overlay-file requests.
6. Each API request is handled by a route that uses the **get_wsi_session_dep** dependency: the dependency reads `patient_id`, `event_id`, `selected_slide_id` from the query, calls `get_or_create_wsi_session` (which returns the existing session), and the handler uses that session to serve slides, thumbnails, and overlays (from external URLs, GCS, or local paths).

### Session and data flow

- **Input:** `patient_id`, `event_id`, `selected_slide_id` (from the URL query).
- **External API response:** Blocks/slides with `slide_url`, `thumbnail_url`, `tca_url` (overlay zip), `meta_data`. The backend orders slides so the selected one is first.
- **In-memory session:** `slide_paths` (URLs), `api_slides`, `thumbnail_paths`, `default_slide_id`, overlay paths. Session key: `pid_<slug>`.
- **TTL:** Same as token-based sessions (e.g. idle timeout). No token is present in the URL.

### Deployment

The viewer is a single FastAPI application and can run behind a reverse proxy (e.g. Cloud Run, load balancer). The external API base URL must be reachable from the viewer (e.g. via `EXTERNAL_API_BASE_URL`). For the URL-only entry point, the viewer does not enforce auth on the URL; access is effectively “who has the link.”

---

## URL contract

**Path:** `/wsi-viewer/` (trailing slash). A request to `/wsi-viewer` without trailing slash is redirected to `/wsi-viewer/` with the same query string.

**Query parameters (all required):**

| Parameter | Description |
|-----------|-------------|
| `patient_id` | Patient UUID |
| `event_id` | Event / row id |
| `selected_slide_id` | Slide id (e.g. `B1`) |

**Example:**

```
https://viewer.example.com/wsi-viewer/?patient_id=a1ce9f01-218d-4505-9906-957549121805&event_id=189704&selected_slide_id=B1
```

---

## Backend design

### Session key

- Internal key: **`pid_<patient_id>_<event_id>_<selected_slide_id>`** (slugified).
- Stored in the same in-memory session store as token-based sessions; same TTL (e.g. idle expiry).
- No random token is exposed in the URL.

### Route ordering

All `/wsi-viewer/...` routes are registered **before** any `/{token}/...` route so that a request to `/wsi-viewer/api/slides?...` is not matched as `token="wsi-viewer"`.

- **Page:** `GET /wsi-viewer/` with query params → get_or_create_wsi_session → serve index.html.
- **Static assets:** `GET /wsi-viewer/styles.css`, `/wsi-viewer/viewer.js`, `/wsi-viewer/logo.svg` (no query required).
- **API:**  
  `GET /wsi-viewer/api/slides`, `/wsi-viewer/api/info/{slide_name}`, `/wsi-viewer/api/thumbnail/{slide_name}`, `/wsi-viewer/api/raw_slides/{filename}`, `/wsi-viewer/api/overlay-config/{slide_name}`, `/wsi-viewer/api/overlay-file/{filename}`.  
  All require `patient_id`, `event_id`, `selected_slide_id` in the query. The shared dependency **get_wsi_session_dep** resolves the session; responses that include URLs use the same query params so the client can call them without a token.

### External API configuration

- Session creation uses the same external API as the `create_session_pid` endpoint (pathology images by patient/event/slide).
- Config: **integrate_config.json** (`base_url`, `email`, `password`) or env **EXTERNAL_API_BASE_URL**, **EXTERNAL_API_EMAIL**, **EXTERNAL_API_PASSWORD**.
- If not configured, the app returns 503 when a request would require creating a session.

---

## Frontend design (wsi-viewer mode)

- Path first segment `wsi-viewer` → **IS_WSI_VIEWER = true**; **SESSION_TOKEN** is not set.
- **API_QUERY:** `new URLSearchParams(window.location.search).toString()` so the current page query is appended to every API request.
- **apiPath(path):** returns `API_BASE + path + (API_QUERY ? '?' + API_QUERY : '')`, so all slide/overlay/thumbnail requests include `patient_id`, `event_id`, `selected_slide_id`.
- No heartbeat is sent in wsi-viewer mode; the session is keyed by the triple and reused on each request.

---

## Integration (how to open the viewer)

- **Same window:**  
  `window.location.href = '/wsi-viewer/?patient_id=' + encodeURIComponent(patientId) + '&event_id=' + encodeURIComponent(eventId) + '&selected_slide_id=' + encodeURIComponent(selectedSlideId);`
- **New tab:**  
  `window.open(url, '_blank');`
- **Iframe:**  
  `iframe.src = url;`
- **Link:**  
  `<a href="/wsi-viewer/?patient_id=...&event_id=...&selected_slide_id=...">View slides</a>`

The integrating application does not send credentials; the viewer backend uses its own config to call the external API. Anyone with the URL can open that case (no secret token in the URL).

---

## Summary

| Aspect | Detail |
|--------|--------|
| **URL** | `/wsi-viewer/?patient_id=&event_id=&selected_slide_id=` |
| **Token in URL** | None |
| **Session** | Server-side, keyed by `(patient_id, event_id, selected_slide_id)`; get-or-create on first request. |
| **Integrating app** | Opens the URL only; no `create_session_pid` call required. |
| **Config** | External API (integrate_config or EXTERNAL_API_* env) required for session creation. |
