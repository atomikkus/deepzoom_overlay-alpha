# Google Cloud Run Deployment Guide

## Quick Deploy

```bash
# Deploy from source (Cloud Run will build using Dockerfile)
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated
```

The application will automatically use Cloud Run's `PORT` environment variable (default: 8080).

## Configuration

### Authentication

Set authentication credentials as environment variables:

```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --platform managed \
  --region asia-south1 \
  --set-env-vars AUTH_USERNAME=admin,AUTH_PASSWORD=your_secure_password \
  --allow-unauthenticated
```

**For production, use password hash:**

```bash
# 1. Generate hash locally
python generate_password_hash.py

# 2. Deploy with hash (escape the $ in the hash)
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --platform managed \
  --region asia-south1 \
  --set-env-vars AUTH_USERNAME=admin,AUTH_PASSWORD_HASH='$2b$12$...' \
  --allow-unauthenticated
```

### GCS Integration

For GCS slide access, use Cloud Run's built-in service account:

```bash
# 1. Get the Cloud Run service account
gcloud run services describe deepzoom-overlay-alpha \
  --region asia-south1 \
  --format='value(spec.template.spec.serviceAccountName)'

# 2. Grant Storage Object Viewer role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/storage.objectViewer"

# 3. Deploy with GCS enabled (no credentials needed)
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated
```

### Memory and CPU

For large slide files, increase memory allocation:

```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --platform managed \
  --region asia-south1 \
  --memory 4Gi \
  --cpu 2 \
  --timeout 300 \
  --allow-unauthenticated
```

### Session TTL

```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --platform managed \
  --region asia-south1 \
  --set-env-vars SESSION_TTL=60 \
  --allow-unauthenticated
```

## Complete Deployment Example

```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --platform managed \
  --region asia-south1 \
  --memory 4Gi \
  --cpu 2 \
  --timeout 300 \
  --set-env-vars AUTH_USERNAME=admin,AUTH_PASSWORD_HASH='$2b$12$...',SESSION_TTL=60,AUTH_ENABLED=true \
  --allow-unauthenticated \
  --max-instances 10 \
  --min-instances 0 \
  --concurrency 80
```

## Using GCS Slides

Once deployed, create a session with GCS URLs:

```bash
# Get your Cloud Run service URL
SERVICE_URL=$(gcloud run services describe deepzoom-overlay-alpha \
  --region asia-south1 \
  --format='value(status.url)')

# Create session with GCS slides
curl -u admin:password -X POST "$SERVICE_URL/api/sessions" \
  -H "Content-Type: application/json" \
  -d '{
    "slides": [
      "gs://your-bucket/slide1.svs",
      "gs://your-bucket/slide2.svs"
    ],
    "overlay": []
  }'
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `PORT` | Port to listen on | 8080 (Cloud Run) | Auto-set |
| `AUTH_ENABLED` | Enable authentication | true | No |
| `AUTH_USERNAME` | API username | admin | No |
| `AUTH_PASSWORD` | API password (dev) | admin | No |
| `AUTH_PASSWORD_HASH` | Password hash (prod) | None | Recommended |
| `SESSION_TTL` | Session timeout (minutes) | 30 | No |
| `GCS_SERVICE_ACCOUNT_PATH` | GCS credentials path | None | No (uses IAM) |

## Viewing Logs

```bash
# View logs
gcloud run services logs read deepzoom-overlay-alpha \
  --region asia-south1 \
  --limit 50

# Follow logs in real-time
gcloud run services logs tail deepzoom-overlay-alpha \
  --region asia-south1
```

## Troubleshooting

### Container failed to start

**Error**: `The user-provided container failed to start and listen on the port`

**Solution**: This is now fixed. The application reads the `PORT` environment variable automatically.

**Verify**:
```bash
# Check logs for port binding
gcloud run services logs read deepzoom-overlay-alpha \
  --region asia-south1 \
  --limit 50
```

### Memory issues

**Error**: Container instances exceeded memory limits

**Solution**: Increase memory allocation:
```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --memory 8Gi \
  --region asia-south1
```

### Timeout issues

**Error**: Request timed out

**Solution**: Increase timeout (max 3600s for HTTP):
```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --timeout 3600 \
  --region asia-south1
```

### GCS access denied

**Error**: 403 Forbidden when accessing GCS

**Solution**: Grant IAM permissions to Cloud Run service account:
```bash
# Get service account
SA=$(gcloud run services describe deepzoom-overlay-alpha \
  --region asia-south1 \
  --format='value(spec.template.spec.serviceAccountName)')

# Grant Storage Object Viewer
gsutil iam ch serviceAccount:$SA:roles/storage.objectViewer gs://your-bucket
```

### Authentication not working

**Error**: 401 Unauthorized

**Solution**: Check environment variables are set correctly:
```bash
gcloud run services describe deepzoom-overlay-alpha \
  --region asia-south1 \
  --format='yaml(spec.template.spec.containers[0].env)'
```

## Custom Domain

### Set up custom domain

```bash
# Map domain
gcloud run domain-mappings create \
  --service deepzoom-overlay-alpha \
  --domain wsi-viewer.example.com \
  --region asia-south1
```

### Configure DNS

Follow the instructions from the command output to add DNS records.

## CI/CD with Cloud Build

Create `cloudbuild.yaml`:

```yaml
steps:
  # Build the container image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/deepzoom-overlay-alpha', '.']
  
  # Push the container image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/deepzoom-overlay-alpha']
  
  # Deploy to Cloud Run
  - name: 'gcr.io/cloud-builders/gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'deepzoom-overlay-alpha'
      - '--image'
      - 'gcr.io/$PROJECT_ID/deepzoom-overlay-alpha'
      - '--region'
      - 'asia-south1'
      - '--platform'
      - 'managed'
      - '--allow-unauthenticated'
      - '--memory'
      - '4Gi'

images:
  - 'gcr.io/$PROJECT_ID/deepzoom-overlay-alpha'
```

Deploy with Cloud Build:
```bash
gcloud builds submit --config cloudbuild.yaml
```

## Cost Optimization

### Auto-scaling

```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --min-instances 0 \
  --max-instances 10 \
  --region asia-south1
```

### Request timeout

Set appropriate timeout to avoid unnecessary charges:
```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --timeout 60 \
  --region asia-south1
```

### Concurrency

Optimize concurrent requests per instance:
```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --concurrency 80 \
  --region asia-south1
```

## Security Best Practices

### 1. Use IAM Authentication

Instead of `--allow-unauthenticated`, require authentication:

```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --no-allow-unauthenticated \
  --region asia-south1
```

### 2. Use Secret Manager

Store sensitive values in Secret Manager:

```bash
# Create secret
echo -n "your_password_hash" | gcloud secrets create auth-password-hash --data-file=-

# Grant access to Cloud Run service account
gcloud secrets add-iam-policy-binding auth-password-hash \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/secretmanager.secretAccessor"

# Deploy with secret
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --update-secrets AUTH_PASSWORD_HASH=auth-password-hash:latest \
  --region asia-south1
```

### 3. VPC Connector (for private GCS)

For private GCS buckets, use VPC connector:

```bash
gcloud run deploy deepzoom-overlay-alpha \
  --source . \
  --vpc-connector YOUR_VPC_CONNECTOR \
  --region asia-south1
```

## Monitoring

### Cloud Monitoring Dashboard

View metrics in Cloud Console:
- Request count
- Request latency
- Memory utilization
- CPU utilization
- Container instance count

### Alerts

Set up alerts for errors:
```bash
# Create alert policy (via Console or gcloud)
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="WSI Viewer Error Alert" \
  --condition-display-name="High error rate" \
  --condition-threshold-value=5
```

## Testing Deployment

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe deepzoom-overlay-alpha \
  --region asia-south1 \
  --format='value(status.url)')

# Test health
curl "$SERVICE_URL/docs"

# Create session
curl -u admin:password -X POST "$SERVICE_URL/api/sessions" \
  -H "Content-Type: application/json" \
  -d '{"slides": ["gs://bucket/slide.svs"], "overlay": []}'
```

## Rollback

If something goes wrong, rollback to previous revision:

```bash
# List revisions
gcloud run revisions list --service deepzoom-overlay-alpha --region asia-south1

# Rollback
gcloud run services update-traffic deepzoom-overlay-alpha \
  --to-revisions REVISION_NAME=100 \
  --region asia-south1
```

## Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Run Pricing](https://cloud.google.com/run/pricing)
- [Best Practices](https://cloud.google.com/run/docs/tips)
- [Troubleshooting](https://cloud.google.com/run/docs/troubleshooting)
