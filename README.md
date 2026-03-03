# WSI Viewer

Web viewer for whole slide imaging. Supports **SVS** format only. Session-based; open a slide by patient, event, and slide ID.

## Viewer URL

Open a slide at:

```
https://[BASE_URL]/wsi-viewer/?patient_id=[PATIENT_ID]&event_id=[EVENT_ID]&selected_slide_id=[SLIDE_ID]
```

- **BASE_URL**: Your deployed viewer base URL (e.g. `wsi-viewer-xxxx-uc.a.run.app`).
- **PATIENT_ID**: Patient identifier.
- **EVENT_ID**: Event identifier.
- **SLIDE_ID**: Slide identifier to load.

## Deploy to Cloud Run

```bash
gcloud run deploy wsi-viewer \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "AUTH_USERNAME=your_user,AUTH_PASSWORD=your_secret_password" \
  --set-env-vars "VIEWER_PUBLIC_BASE_URL=https://wsi-viewer-xxxx.run.app"
```

After the first deploy, replace `https://wsi-viewer-xxxx.run.app` with the URL Cloud Run prints (e.g. `https://wsi-viewer-xxxx-uc.a.run.app`) and redeploy so `VIEWER_PUBLIC_BASE_URL` matches the real service URL.

## Environment variables

| Variable | Description |
|----------|-------------|
| **AUTH_USERNAME** | Username for server authentication (create/list/delete sessions). |
| **AUTH_PASSWORD** | Password for server authentication. |
| **VIEWER_PUBLIC_BASE_URL** | Public base URL of the viewer (e.g. `https://wsi-viewer-xxxx.run.app`). Used so session responses can return full viewer URLs. |

**PORT** is set by Cloud Run; do not set it yourself.
