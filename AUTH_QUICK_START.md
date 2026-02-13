# Authentication Quick Start

## Default Setup (Development)

The application comes with default credentials:
- **Username**: `admin`
- **Password**: `admin`

⚠️ **Change these before deploying to production!**

## Quick Configuration

### Option 1: Environment Variables (Simplest)

```bash
# Set custom credentials
export AUTH_USERNAME=myuser
export AUTH_PASSWORD=mypassword

# Start the application
python app.py --slides-local ./slides
```

### Option 2: Password Hash (Production)

```bash
# 1. Generate password hash
python generate_password_hash.py

# 2. Set environment variables
export AUTH_USERNAME=produser
export AUTH_PASSWORD_HASH='$2b$12$your_hash_here'

# 3. Start the application
python app.py --slides-local ./slides
```

### Option 3: .env File

```bash
# 1. Copy example file
cp .env.example .env

# 2. Edit .env
AUTH_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD=your_secure_password

# 3. Start (loads .env automatically with python-dotenv)
python app.py --slides-local ./slides
```

## Testing Authentication

### Using cURL

```bash
# Create a session (requires auth)
curl -u admin:admin -X POST http://localhost:8511/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"slides": ["./uploads"], "overlay": []}'

# Response will include session token
# {"token": "uuid-here", "url": "/uuid-here/", ...}

# Access session viewer (no auth needed - uses token)
curl http://localhost:8511/uuid-here/
```

### Using Python

```python
import requests
from requests.auth import HTTPBasicAuth

# Create session with auth
response = requests.post(
    "http://localhost:8511/api/sessions",
    json={"slides": ["./uploads"], "overlay": []},
    auth=HTTPBasicAuth("admin", "admin")
)

session = response.json()
print(f"Session URL: http://localhost:8511/{session['token']}/")
```

### Using Browser

1. Open API docs: http://localhost:8511/docs
2. Click "Authorize" button
3. Enter username and password
4. Try endpoints in the interactive API

## Disable Authentication (Development Only)

```bash
export AUTH_ENABLED=false
python app.py --slides-local ./slides
```

## Common Issues

### 401 Unauthorized
- Check username/password are correct
- Verify environment variables are set
- Check if `AUTH_ENABLED=true`

### No password prompt in browser
- Clear browser cache
- Use incognito/private mode
- Try different browser

### Docker authentication
```bash
# Pass credentials to Docker
docker run -e AUTH_USERNAME=user -e AUTH_PASSWORD=pass -p 8511:8511 wsi-viewer
```

## Full Documentation

See [AUTH.md](AUTH.md) for complete authentication guide including:
- Security best practices
- Multiple users setup
- HTTPS configuration
- Docker secrets
- Troubleshooting
