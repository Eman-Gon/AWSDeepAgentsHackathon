# Auth0 Machine-to-Machine (M2M) Authentication

## Overview

The Client Credentials Flow allows machine-to-machine applications (like the Commons AI investigation agent) to authenticate and call protected APIs without user interaction.

## Auth0 Dashboard Setup

### 1. Create the API

1. Dashboard → Applications → APIs → Create API
2. **Name**: Commons Investigation API
3. **Identifier** (audience): `https://api.commons.dev`
4. **Signing Algorithm**: RS256
5. Define permissions/scopes:
   - `investigate:read` — Read investigation data
   - `investigate:write` — Create/update investigations
   - `graph:read` — Query entity graph
   - `graph:write` — Modify entity graph
   - `agent:execute` — Execute agent actions

### 2. Create M2M Application

1. Dashboard → Applications → Create Application
2. Select **Machine to Machine Applications**
3. Choose the Commons Investigation API
4. Select authorized scopes
5. Note **Client ID** and **Client Secret**

## Token Request (Python)

```python
import requests
import time

class Auth0M2MClient:
    """Manages M2M authentication tokens with caching."""

    def __init__(self, domain, client_id, client_secret, audience):
        self.domain = domain
        self.client_id = client_id
        self.client_secret = client_secret
        self.audience = audience
        self._token = None
        self._expires_at = 0

    def get_token(self):
        """Get a valid access token, refreshing if expired."""
        if self._token and time.time() < self._expires_at - 60:
            return self._token  # Return cached token (with 60s buffer)

        response = requests.post(
            f"https://{self.domain}/oauth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "audience": self.audience
            },
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()

        self._token = data["access_token"]
        self._expires_at = time.time() + data["expires_in"]
        return self._token

    def auth_headers(self):
        """Get Authorization headers for API calls."""
        return {"Authorization": f"Bearer {self.get_token()}"}


# Usage
auth = Auth0M2MClient(
    domain="your-tenant.auth0.com",
    client_id="AGENT_CLIENT_ID",
    client_secret="AGENT_CLIENT_SECRET",
    audience="https://api.commons.dev"
)

# Call protected API
response = requests.get(
    "https://api.commons.dev/api/investigate",
    headers=auth.auth_headers()
)
```

## Token Verification (Python Backend)

```python
# pip install python-jose[cryptography] requests
from jose import jwt, JWTError
from functools import lru_cache
import requests

AUTH0_DOMAIN = "your-tenant.auth0.com"
API_AUDIENCE = "https://api.commons.dev"
ALGORITHMS = ["RS256"]

@lru_cache(maxsize=1)
def get_jwks():
    """Fetch and cache Auth0 JWKS (JSON Web Key Set)."""
    response = requests.get(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json")
    return response.json()

def verify_and_decode_token(token: str) -> dict:
    """
    Verify an Auth0 JWT access token.
    Returns decoded payload on success, raises on failure.
    """
    try:
        jwks = get_jwks()
        unverified_header = jwt.get_unverified_header(token)

        # Find the matching RSA key
        rsa_key = None
        for key in jwks["keys"]:
            if key["kid"] == unverified_header.get("kid"):
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
                break

        if not rsa_key:
            raise JWTError("Unable to find matching key")

        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=ALGORITHMS,
            audience=API_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/"
        )
        return payload

    except JWTError as e:
        raise ValueError(f"Token verification failed: {e}")


# FastAPI middleware example
from fastapi import Request, HTTPException

async def require_auth(request: Request):
    """FastAPI dependency for token verification."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")

    token = auth_header.split(" ", 1)[1]
    try:
        payload = verify_and_decode_token(token)
        request.state.auth = payload
    except ValueError as e:
        raise HTTPException(401, str(e))
```

## Token Response Format

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Ii0tLSJ9...",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

Decoded JWT payload:
```json
{
  "iss": "https://your-tenant.auth0.com/",
  "sub": "CLIENT_ID@clients",
  "aud": "https://api.commons.dev",
  "iat": 1700000000,
  "exp": 1700086400,
  "scope": "investigate:read investigate:write graph:read",
  "azp": "CLIENT_ID",
  "gty": "client-credentials"
}
```

## cURL Example

```bash
# Get token
curl --request POST \
  --url "https://your-tenant.auth0.com/oauth/token" \
  --header "Content-Type: application/json" \
  --data '{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "audience": "https://api.commons.dev",
    "grant_type": "client_credentials"
  }'

# Use token
curl --request GET \
  --url "https://api.commons.dev/api/investigate" \
  --header "Authorization: Bearer ACCESS_TOKEN"
```

## Security Best Practices

- Store client secrets in environment variables, never in code
- Cache tokens until near expiry (use 60s buffer)
- Use HTTPS for all token requests and API calls
- Rotate client secrets periodically
- Define minimal scopes for each M2M application
- Log token issuance for audit trails
- Use RS256 (asymmetric) signing, not HS256
