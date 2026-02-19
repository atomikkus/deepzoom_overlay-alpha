# Authentication Guide

## Overview

The WSI Viewer uses **HTTP Basic Authentication** (FastAPI Security) to protect **all** endpoints:
- Session management (create, delete, list, heartbeat)
- Viewer UI and static assets (`/{token}/`, CSS, JS)
- Slide listing, metadata, raw slide streaming
- Overlay config and overlay files
- GCS proxy, download, signed URLs

Unauthenticated requests receive `401 Unauthorized` with `WWW-Authenticate: Basic`; the browser will prompt for username and password.

## Quick Start

### Default Credentials

```
Username: satya@4basecare.com
Password: satya123
```

Override via environment variables in production.

## Configuration

### Environment Variables

Set credentials (recommended for production):

```bash
export AUTH_USERNAME=your-user@example.com
export AUTH_PASSWORD=your-secure-password
```

Or in `.env`:

```env
AUTH_USERNAME=your-user@example.com
AUTH_PASSWORD=your-secure-password
```

## Using the API with Authentication

### Browser

Open the viewer URL (e.g. `http://localhost:8511/{token}/`). The browser will prompt for username and password. After login, all requests (slides, tiles, overlays) send credentials automatically.

### cURL Examples

```bash
# Create a new session
curl -u satya@4basecare.com:satya123 -X POST http://localhost:8511/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "slides": ["gs://bucket/slide1.svs", "gs://bucket/slide2.svs"],
    "overlay": ["/path/to/overlays"]
  }'

# Delete a session
curl -u satya@4basecare.com:satya123 -X DELETE http://localhost:8511/api/sessions/{token}

# List slides in a session
curl -u satya@4basecare.com:satya123 "http://localhost:8511/{token}/api/slides"

# Download GCS file
curl -u satya@4basecare.com:satya123 -X POST "http://localhost:8511/api/gcs/download?blob_path=path/to/file.svs"
```

### Python Example

```python
import requests
from requests.auth import HTTPBasicAuth

auth = HTTPBasicAuth("satya@4basecare.com", "satya123")

# Create session
response = requests.post(
    "http://localhost:8511/api/sessions",
    json={
        "slides": ["gs://bucket/slide1.svs"],
        "overlay": []
    },
    auth=auth
)
session_data = response.json()
print(f"Session token: {session_data['token']}")

# All subsequent requests need auth
viewer_url = f"http://localhost:8511/{session_data['token']}/"
slides = requests.get(f"http://localhost:8511/{session_data['token']}/api/slides", auth=auth)
```

### JavaScript Example

```javascript
// Browser: use credentials so HTTP Basic is sent
fetch('http://localhost:8511/api/sessions', {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    slides: ['gs://bucket/slide1.svs'],
    overlay: []
  })
})
.then(response => response.json())
.then(data => {
  console.log('Session token:', data.token);
  console.log('Viewer URL:', `http://localhost:8511/${data.token}/`);
});
```

## Protected Endpoints

All of the following require HTTP Basic Authentication (same username/password):

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions` | Create new session |
| GET | `/api/sessions` | List sessions |
| DELETE | `/api/sessions/{token}` | Delete session |
| POST | `/{token}/` | Viewer HTML |
| GET | `/{token}/api/slides` | List slides |
| GET | `/{token}/api/raw_slides/{filename}` | Stream slide file |
| GET | `/{token}/api/overlay-config/...`, `.../overlay-file/...` | Overlay data |
| POST | `/api/gcs/download`, GET `/api/gcs/...` | GCS proxy and download |
| * | All other API routes | All require auth |

## Security Best Practices

### 1. Use Strong Passwords

```bash
# Generate a secure random password
openssl rand -base64 32
```

Set via environment: `AUTH_USERNAME` and `AUTH_PASSWORD`. Do not commit credentials to source control.

### 2. Use HTTPS in Production

HTTP Basic Auth sends credentials base64-encoded (not encrypted). Always use HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name wsi-viewer.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8511;
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }
}
```

### 3. Rotate Credentials Regularly

Change passwords periodically via `AUTH_USERNAME` and `AUTH_PASSWORD`, then restart the application.

### 4. Use Environment-Specific Credentials

```bash
# Development
export AUTH_USERNAME=dev@example.com
export AUTH_PASSWORD=dev_pass

# Production (e.g. from secrets manager)
export AUTH_USERNAME=prod@example.com
export AUTH_PASSWORD=secure_prod_password
```

## Docker Deployment

### docker-compose.yml

```yaml
version: '3.8'

services:
  wsi-viewer:
    build: .
    environment:
      - AUTH_USERNAME=${AUTH_USERNAME:-satya@4basecare.com}
      - AUTH_PASSWORD=${AUTH_PASSWORD:-satya123}
    env_file:
      - .env
    ports:
      - "8511:8511"
```

### .env file

```env
AUTH_USERNAME=satya@4basecare.com
AUTH_PASSWORD=satya123
```

### Docker Secrets (Production)

```yaml
version: '3.8'

services:
  wsi-viewer:
    build: .
    environment:
      - AUTH_USERNAME_FILE=/run/secrets/auth_username
      - AUTH_PASSWORD_FILE=/run/secrets/auth_password
    secrets:
      - auth_username
      - auth_password

secrets:
  auth_username:
    file: ./secrets/auth_username.txt
  auth_password:
    file: ./secrets/auth_password.txt
```

(If your app reads `*_FILE` env vars, mount secrets there; otherwise pass `AUTH_USERNAME` and `AUTH_PASSWORD` from a secrets manager.)

## Troubleshooting

### 401 Unauthorized

```bash
# Verify credentials
curl -v -u satya@4basecare.com:satya123 http://localhost:8511/api/sessions

# Check environment variables (if using env override)
echo $AUTH_USERNAME
echo $AUTH_PASSWORD
```

### Invalid credentials error

1. Verify username and password match `AUTH_USERNAME` and `AUTH_PASSWORD` (or defaults).
2. Ensure no extra whitespace in environment variables.
3. Use the exact username (e.g. `satya@4basecare.com`) and password.

### Browser password prompt

HTTP Basic Auth triggers browser password prompts. This is expected behavior. Use API tokens or session tokens for programmatic access.

## Migration from No-Auth

If upgrading from a version without authentication:

1. **Set credentials**: Use `AUTH_USERNAME` and `AUTH_PASSWORD` (or rely on defaults).
2. **Update clients**: Add HTTP Basic Auth to all API calls (e.g. `curl -u user:pass`, or `credentials: 'include'` in fetch).
3. **Test**: Verify browser login and API access with the new credentials.
4. **Deploy**: Roll out to production.

## FAQ

**Q: Do I need authentication for viewing slides?**  
A: Yes. All endpoints (including viewing slides) require HTTP Basic Auth. The session token identifies the session; the username/password authorizes access.

**Q: Can I use custom authentication?**  
A: Yes. Modify the `verify_credentials` function in `app.py` to integrate with your auth system (LDAP, OAuth, etc.).

**Q: How do I add multiple users?**  
A: Currently supports one user. For multiple users, extend the authentication system to use a database or user store.

**Q: Is this secure for production?**  
A: Yes, when used with HTTPS and strong passwords. HTTP Basic Auth over HTTPS is secure and widely supported.

**Q: Can I use API keys instead?**  
A: You can extend the code to support API keys using FastAPI's `APIKeyHeader` dependency.
