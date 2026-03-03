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
  --set-env-vars "AUTH_USERNAME=<value>,AUTH_PASSWORD=<value>" \
  --set-env-vars "EXTERNAL_API_BASE_URL=<value>,EXTERNAL_API_EMAIL=<value>,EXTERNAL_API_PASSWORD=<value>"
```

## Environment variables

| Variable | Description |
|----------|-------------|
| **AUTH_USERNAME** | Username for server authentication (create/list/delete sessions). |
| **AUTH_PASSWORD** | Password for server authentication. |
| **EXTERNAL_API_BASE_URL** | Base URL of the external API (used with email/password for `create_session_pid`). |
| **EXTERNAL_API_EMAIL** | Email for external API authentication. |
| **EXTERNAL_API_PASSWORD** | Password for external API authentication. |

**PORT** is set by Cloud Run; do not set it yourself.
