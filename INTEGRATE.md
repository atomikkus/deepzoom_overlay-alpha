# INTEGRATE.md

Base URL: `http://localhost:8000` (or wherever the server is hosted)

All protected endpoints require the header:
```
Authorization: Bearer <token>
```

---

## 1. Login

**`POST /user/login`**

```json
// Request body
{
  "email": "admin@ecrf.com",
  "password": "4bc@2022"
}
```

```json
// Response 200
{
  "success": true,
  "message": "welcome to ",
  "payLoad": {
    "appUserId": 11,
    "fullName": "CDM Admin",
    "email": "admin@ecrf.com",
    "mobileNumber": "8123754261",
    "role": "ADMIN",
    "authToken": "a3f8c2...d9e1",
    "organisation": "4baseCare",
    "is4BaseCare": true,
    "orgShortName": "4bc",
    "accessLevel": 1,
    "lastLogin": "2026-02-24",
    "countryRegion": "IN"
  }
}
```

Save `payLoad.authToken` for all subsequent requests.

```json
// Response 401 — wrong credentials
{ "detail": "Invalid credentials" }
```

---

## 2. List Patients

**`GET /patients`**

Returns all patients with their events and available slide IDs — use this to populate selection dropdowns.

```
GET /patients
Authorization: Bearer a3f8c2...d9e1
```

```json
// Response 200
{
  "success": true,
  "payLoad": [
    {
      "patient_id": "a1ce9f01-218d-4505-9906-957549121805",
      "events": [
        {
          "event_id": "189704",
          "slide_ids": ["B1", "B3", "B4", "B2"]
        }
      ]
    }
  ]
}
```

---

## 3. Fetch Pathology Images

**`GET /pathology_image/all`**

Returns all blocks and slides for a given patient+event combination. `slide_id` is echoed back as `selected_slide_id` in the response (used by the UI to highlight the chosen slide).

```
GET /pathology_image/all?patient_id=a1ce9f01-218d-4505-9906-957549121805&event_id=189704&slide_id=B1
Authorization: Bearer a3f8c2...d9e1
```

```json
// Response 200
{
  "success": true,
  "message": "Images fetched successfully.",
  "payLoad": {
    "patient_id": "a1ce9f01-218d-4505-9906-957549121805",
    "event_id": 189704,
    "selected_slide_id": "B1",
    "blocks": [
      {
        "block_id": "A1",
        "slides": [
          {
            "id": 1,
            "slide_id": "B1",
            "slide_url": "https://storage.googleapis.com/wsi_viewer_test/1087-25.svs",
            "thumbnail_url": "https://storage.googleapis.com/wsi_viewer_test/1087-25_thumbnail.png",
            "tca_url": null,
            "status": "FINISHED",
            "tca_status": null,
            "meta_data": {
              "width": "112000",
              "height": "86000",
              "mpp": "0.2527",
              "objective_power": "40",
              "vendor": "aperio"
            }
          },
          {
            "id": 2,
            "slide_id": "B3",
            "slide_url": "https://storage.googleapis.com/wsi_viewer_test/Head_neck_pathology.svs",
            "thumbnail_url": null,
            "tca_url": null,
            "status": "FINISHED",
            "tca_status": null,
            "meta_data": {
              "width": "98304",
              "height": "74240",
              "mpp": "0.5",
              "objective_power": "20",
              "vendor": "leica"
            }
          }
        ]
      },
      {
        "block_id": "A2",
        "slides": [
          {
            "id": 4,
            "slide_id": "B2",
            "slide_url": "https://storage.googleapis.com/wsi_viewer_test/TCGA-C5-A8YQ-...",
            "thumbnail_url": null,
            "tca_url": null,
            "status": "PENDING",
            "tca_status": null,
            "meta_data": {
              "width": "75264",
              "height": "55040",
              "mpp": "0.4942",
              "objective_power": "20",
              "vendor": "hamamatsu"
            }
          }
        ]
      }
    ]
  }
}
```

```json
// Response 404 — unknown patient/event combination
{ "detail": "No images found for patient_id=xxx, event_id=yyy" }
```

```json
// Response 401 — missing or invalid token
{ "detail": "Invalid or expired token" }
```

---

## Typical Integration Flow

```
POST /user/login          →  get authToken
GET  /patients            →  list patient_ids, event_ids, slide_ids
GET  /pathology_image/all →  fetch blocks & slides for selected patient+event
```

Slide `status` values: `PENDING`, `FINISHED`, `FAILED`, or `null`.

`meta_data` fields (all values are strings, field may be `null` if unavailable):

| Field | Description |
|---|---|
| `width` | Image width in pixels |
| `height` | Image height in pixels |
| `mpp` | Microns per pixel (physical resolution) |
| `objective_power` | Magnification level (e.g. `"20"`, `"40"`) |
| `vendor` | Scanner vendor (e.g. `"aperio"`, `"hamamatsu"`, `"leica"`) |
