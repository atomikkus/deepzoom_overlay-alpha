# Cloud Run & GKE Deployment

The WSI Viewer is configured to run on **Google Cloud Run** and **GKE** (Google Kubernetes Engine) with minimal changes.

## What’s Included

- **PORT** – App listens on `PORT` (Cloud Run sets `PORT=8080` by default).
- **/health** – Unauthenticated readiness/liveness endpoint for probes.
- **SLIDE_PATHS / OVERLAY_PATHS** – Optional env vars to set slide and overlay paths without CLI (comma-separated).
- **Auth split** – Only global API (create session, list/delete sessions, GCS) requires HTTP Basic Auth. Viewer routes `/{token}/...` do not; the session URL is the credential (shareable links).
- **Dockerfile** – Uses `PORT` at runtime and a `/health`-based healthcheck.
- **Graceful shutdown** – Handles SIGTERM and stops the cleanup loop.

## Cloud Run

### 1. Create Artifact Registry repository (one-time)

The image must live in a **Docker repository** in Artifact Registry. Create one if you don’t have it:

```bash
export REGION=asia-south1
export PROJECT=in-4bc-engineering
export REPO_NAME=docker

gcloud artifacts repositories create ${REPO_NAME} \
  --repository-format=docker \
  --location=${REGION} \
  --project=${PROJECT}
```

If the repository already exists, you’ll see an error; that’s fine. Set `REPO_NAME` to your actual repo name (e.g. `docker`, `containers`, `wsi-viewer`).

### 2. Build and push the image

Run from the **project root** (where `Dockerfile` is):

```bash
# Use your actual REGION, PROJECT, and REPO_NAME
export REGION=asia-south1
export PROJECT=in-4bc-engineering
export REPO_NAME=docker

# Build and push (Cloud Build uses the project's default service account)
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT}/${REPO_NAME}/wsi-viewer
```

Wait until the build finishes. The image will be at `asia-south1-docker.pkg.dev/in-4bc-engineering/docker/wsi-viewer` (or your `REPO_NAME`).

### 3. Deploy to Cloud Run

```bash
export REGION=asia-south1
export PROJECT=in-4bc-engineering
export REPO_NAME=docker

gcloud run deploy wsi-viewer \
  --image ${REGION}-docker.pkg.dev/${PROJECT}/${REPO_NAME}/wsi-viewer \
  --platform managed \
  --region ${REGION} \
  --project ${PROJECT} \
  --allow-unauthenticated \
  --set-env-vars "SLIDE_PATHS=gs://your-bucket/slides/" \
  --set-env-vars "AUTH_USERNAME=satya@4basecare.com" \
  --set-env-vars "AUTH_PASSWORD=satya123"
```

- Replace `gs://your-bucket/slides/` with your real GCS path(s).
- For production, use `--set-secrets "AUTH_PASSWORD=your-secret-name:latest"` instead of `AUTH_PASSWORD` in env.
- Omit `--allow-unauthenticated` if you use IAM or a load balancer for auth.
- For private GCS, add `--set-env-vars "GCS_SERVICE_ACCOUNT_PATH=..."` and mount the key (e.g. via secrets).

### Environment variables (Cloud Run)

| Variable | Required | Description |
|----------|----------|-------------|
| `PORT` | No (set by Cloud Run) | Port the container listens on (default 8080). |
| `SLIDE_PATHS` | Recommended | Comma-separated list of GCS URLs or paths (e.g. `gs://b/path/,https://storage.googleapis.com/b/f.svs`). Omit to use default `uploads` (only works if you mount a volume). |
| `OVERLAY_PATHS` | No | Comma-separated overlay directories (not used if overlays are in GCS and not yet supported from GCS). |
| `AUTH_USERNAME` | No | HTTP Basic username (default in code). Prefer Secret Manager. |
| `AUTH_PASSWORD` | No | HTTP Basic password. **Use Secret Manager in production.** |
| `GCS_SERVICE_ACCOUNT_PATH` | For private GCS | Path to service account JSON (e.g. mounted secret). |
| `GCS_BUCKET_NAME` | No | Default bucket for GCS endpoints (download, proxy, list, signed-url). |
| `SESSION_TTL` | No | Session TTL in minutes (default 30). |

### Health checks

Cloud Run uses HTTP GET on the container port. The app exposes:

- **`/health`** – Returns `200` and `{"status":"ok"}`. No authentication. Use this as the startup/liveness probe if you configure custom probes.

### Local Docker run (same image as Cloud Run)

```bash
docker build -t wsi-viewer .
docker run -d -p 8080:8080 \
  -e SLIDE_PATHS="gs://your-bucket/slides/" \
  -e AUTH_USERNAME=satya@4basecare.com \
  -e AUTH_PASSWORD=satya123 \
  wsi-viewer
```

Open `http://localhost:8080`. For port 8511: `-p 8511:8511 -e PORT=8511`.

---

## GKE

### Use the same image

Build and push the image as above (or use your GKE cluster’s registry). The same Dockerfile and env vars apply.

### Example Kubernetes manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wsi-viewer
spec:
  replicas: 1
  selector:
    matchLabels:
      app: wsi-viewer
  template:
    metadata:
      labels:
        app: wsi-viewer
    spec:
      containers:
        - name: wsi-viewer
          image: REGION-docker.pkg.dev/PROJECT/REPO/wsi-viewer:latest
          ports:
            - containerPort: 8080
          env:
            - name: PORT
              value: "8080"
            - name: SLIDE_PATHS
              value: "gs://your-bucket/slides/"
            - name: AUTH_USERNAME
              valueFrom:
                secretKeyRef:
                  name: wsi-viewer-auth
                  key: username
            - name: AUTH_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: wsi-viewer-auth
                  key: password
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1"
---
apiVersion: v1
kind: Service
metadata:
  name: wsi-viewer
spec:
  selector:
    app: wsi-viewer
  ports:
    - port: 80
      targetPort: 8080
  type: LoadBalancer
```

- For private GCS, use a secret for the service account JSON and set `GCS_SERVICE_ACCOUNT_PATH` to the mount path.
- **Session affinity:** Sessions are in-memory per replica. For sticky sessions, set `sessionAffinity: ClientIP` (or use an ingress with cookie-based affinity) if you need the same instance for a given user.

### Ingress (optional)

Use an Ingress resource or GKE Ingress controller to add TLS and a hostname; point the backend to the `wsi-viewer` service on port 8080.

---

## Limitations and notes

1. **Sessions in memory** – Each Cloud Run instance or GKE pod has its own sessions. Scaling to multiple instances means a user might hit a different instance and lose the default session; use **POST /api/sessions** to create sessions and share the session URL, or use a single instance / session affinity if you rely on the default session.
2. **Local paths** – `uploads` and local overlay paths only work if the filesystem is writable and persistent (e.g. volume mount). On Cloud Run, prefer GCS-only `SLIDE_PATHS`.
3. **GCS** – For private buckets, set `GCS_SERVICE_ACCOUNT_PATH` to a path that exists in the container (e.g. secret mount). Cloud Run and GKE can also use Workload Identity so the default credentials work without a key file.
4. **HTTPS** – Cloud Run and GKE Ingress provide TLS; the app itself is HTTP and relies on the platform for termination.

---

## Quick checklist

- [ ] Image built and pushed to Artifact Registry (or your registry).
- [ ] `PORT` not overridden (or set to 8080) so the container listens on the expected port.
- [ ] `SLIDE_PATHS` set to GCS URLs (and optionally overlay paths) when not using CLI.
- [ ] `AUTH_USERNAME` / `AUTH_PASSWORD` set (prefer secrets).
- [ ] For private GCS: service account key mounted or Workload Identity configured.
- [ ] Probes use `/health` (or default HTTP on port).
- [ ] Consider session affinity if using multiple replicas and default session.
