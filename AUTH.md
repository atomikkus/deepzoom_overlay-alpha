# Authentication Guide

## Overview

The WSI Viewer API uses HTTP Basic Authentication to protect sensitive endpoints:
- Creating new sessions
- Deleting sessions
- Downloading GCS files

**Session-specific endpoints** (viewing slides, uploading, etc.) are protected by session tokens and do not require separate authentication.

## Quick Start

### Default Credentials (Development)

```
Username: admin
Password: admin
```

⚠️ **IMPORTANT**: Change these credentials in production!

## Configuration

### Method 1: Environment Variables (Development)

Set plain text credentials (not recommended for production):

```bash
export AUTH_USERNAME=myuser
export AUTH_PASSWORD=mypassword
```

### Method 2: Password Hash (Production - Recommended)

1. Generate a password hash:
   ```bash
   python generate_password_hash.py
   ```

2. Set environment variables:
   ```bash
   export AUTH_USERNAME=myuser
   export AUTH_PASSWORD_HASH='$2b$12$...'
   ```

3. Or add to `.env` file:
   ```env
   AUTH_USERNAME=myuser
   AUTH_PASSWORD_HASH=$2b$12$...
   ```

### Method 3: Disable Authentication (Development Only)

```bash
export AUTH_ENABLED=false
```

## Using the API with Authentication

### cURL Examples

```bash
# Create a new session
curl -u admin:admin -X POST http://localhost:8511/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "slides": ["gs://bucket/slide1.svs", "gs://bucket/slide2.svs"],
    "overlay": ["/path/to/overlays"]
  }'

# Delete a session
curl -u admin:admin -X DELETE http://localhost:8511/api/sessions/{token}

# Download GCS file
curl -u admin:admin -X POST "http://localhost:8511/api/gcs/download?blob_path=path/to/file.svs"
```

### Python Example

```python
import requests
from requests.auth import HTTPBasicAuth

# Create session
response = requests.post(
    "http://localhost:8511/api/sessions",
    json={
        "slides": ["gs://bucket/slide1.svs"],
        "overlay": []
    },
    auth=HTTPBasicAuth("admin", "admin")
)
session_data = response.json()
print(f"Session token: {session_data['token']}")

# Access session (no auth needed - uses token)
viewer_url = f"http://localhost:8511/{session_data['token']}/"
print(f"Viewer URL: {viewer_url}")
```

### JavaScript Example

```javascript
// Browser
const username = 'admin';
const password = 'admin';
const credentials = btoa(`${username}:${password}`);

fetch('http://localhost:8511/api/sessions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Basic ${credentials}`
  },
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

### Requires Authentication ✓

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions` | Create new session |
| DELETE | `/api/sessions/{token}` | Delete session |
| POST | `/api/sessions/{token}/delete` | Delete session (alternative) |
| POST | `/api/gcs/download` | Download GCS file |

### No Authentication Required ✗

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/{token}/` | View session (protected by token) |
| GET | `/{token}/api/slides` | List slides in session |
| GET | `/{token}/api/info/{slide_name}` | Get slide info |
| POST | `/{token}/api/upload` | Upload file to session |
| DELETE | `/{token}/api/delete/{slide_name}` | Delete slide from session |
| GET | `/{token}/api/raw_slides/{filename}` | Stream slide file |
| GET | `/{token}/api/overlay/{slide_name}` | Get overlay data |
| POST | `/{token}/api/sessions/{token}/heartbeat` | Keep session alive |
| GET | `/docs` | API documentation |

## Security Best Practices

### 1. Use Strong Passwords

```bash
# Generate a secure random password
openssl rand -base64 32
```

**Note:** The app hashes passwords with SHA256 then bcrypt, so `AUTH_PASSWORD` can be any length (no 72-byte limit). If you previously set `AUTH_PASSWORD_HASH` with an older script, regenerate it with `python generate_password_hash.py`.

### 2. Use Password Hashes in Production

Never store plain passwords. Always use `AUTH_PASSWORD_HASH`:

```bash
python generate_password_hash.py
```

### 3. Use HTTPS in Production

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

### 4. Rotate Credentials Regularly

Change passwords periodically:

```bash
# Generate new hash
python generate_password_hash.py

# Update environment variable
export AUTH_PASSWORD_HASH='new_hash'

# Restart application
```

### 5. Use Environment-Specific Credentials

```bash
# Development
export AUTH_USERNAME=dev_user
export AUTH_PASSWORD=dev_pass

# Staging
export AUTH_USERNAME=staging_user
export AUTH_PASSWORD_HASH='$2b$12$staging_hash'

# Production
export AUTH_USERNAME=prod_user
export AUTH_PASSWORD_HASH='$2b$12$production_hash'
```

## Docker Deployment

### docker-compose.yml

```yaml
version: '3.8'

services:
  wsi-viewer:
    build: .
    environment:
      - AUTH_ENABLED=true
      - AUTH_USERNAME=${AUTH_USERNAME:-admin}
      - AUTH_PASSWORD_HASH=${AUTH_PASSWORD_HASH}
    env_file:
      - .env
    ports:
      - "8511:8511"
```

### .env file

```env
AUTH_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD_HASH=$2b$12$your_generated_hash_here
```

### Docker Secrets (Production)

```yaml
version: '3.8'

services:
  wsi-viewer:
    build: .
    environment:
      - AUTH_ENABLED=true
      - AUTH_USERNAME_FILE=/run/secrets/auth_username
      - AUTH_PASSWORD_HASH_FILE=/run/secrets/auth_password_hash
    secrets:
      - auth_username
      - auth_password_hash

secrets:
  auth_username:
    file: ./secrets/auth_username.txt
  auth_password_hash:
    file: ./secrets/auth_password_hash.txt
```

## Troubleshooting

### 401 Unauthorized

```bash
# Verify credentials
curl -v -u admin:admin http://localhost:8511/api/sessions

# Check environment variables
echo $AUTH_USERNAME
echo $AUTH_PASSWORD_HASH
```

### Invalid credentials error

1. Verify username matches: `AUTH_USERNAME`
2. Regenerate password hash: `python generate_password_hash.py`
3. Ensure no extra whitespace in environment variables
4. Check if using plain password or hash (not both)

### Authentication bypassed

If `AUTH_ENABLED=false`, authentication is disabled. Set to `true`:

```bash
export AUTH_ENABLED=true
```

### Browser password prompt

HTTP Basic Auth triggers browser password prompts. This is expected behavior. Use API tokens or session tokens for programmatic access.

## Migration from No-Auth

If upgrading from a version without authentication:

1. **Enable auth gradually**:
   ```bash
   # Start with auth disabled
   AUTH_ENABLED=false
   
   # Then enable with default password
   AUTH_ENABLED=true
   AUTH_PASSWORD=changeme
   
   # Finally, use secure hash
   AUTH_ENABLED=true
   AUTH_PASSWORD_HASH=$2b$12$...
   ```

2. **Update clients**: Add authentication to API calls
3. **Test**: Verify all integrations work with new auth
4. **Deploy**: Roll out to production

## FAQ

**Q: Do I need authentication for viewing slides?**  
A: No. Once a session is created (which requires auth), the session token provides access.

**Q: Can I use custom authentication?**  
A: Yes. Modify the `verify_credentials` function in `app.py` to integrate with your auth system (LDAP, OAuth, etc.).

**Q: How do I add multiple users?**  
A: Currently supports one user. For multiple users, extend the authentication system to use a database or user store.

**Q: Is this secure for production?**  
A: Yes, when used with HTTPS and strong passwords. HTTP Basic Auth over HTTPS is secure and widely supported.

**Q: Can I use API keys instead?**  
A: You can extend the code to support API keys using FastAPI's `APIKeyHeader` dependency.
