---
name: auth0
description: Auth0 authentication reference for Next.js apps and M2M agent auth. Use when adding login/logout, protecting routes, implementing machine-to-machine auth for AI agents, configuring RBAC roles, or integrating Auth0 into the Commons hackathon project.
---

# Auth0 (Next.js SDK v4 + M2M)

## Overview

Auth0 provides authentication and authorization for the Commons platform. The Next.js SDK v4 handles journalist login/sessions, while the Client Credentials (M2M) flow authenticates the AI investigation agent to call backend APIs securely.

## Quick Setup (Next.js SDK v4)

```bash
npm install @auth0/nextjs-auth0
```

### Environment Variables

```env
# .env.local
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_CLIENT_ID=your_client_id
AUTH0_CLIENT_SECRET=your_client_secret
AUTH0_SECRET=a-random-32-byte-secret-string
APP_BASE_URL=http://localhost:3000
```

### Auth0 Client (Server-Side)

```typescript
// src/lib/auth0.ts
import { Auth0Client } from '@auth0/nextjs-auth0/server';

export const auth0 = new Auth0Client();
```

### Proxy (Route Handler)

```typescript
// src/proxy.ts (v4 uses proxy, not API routes)
import { auth0 } from "./lib/auth0";

export async function proxy(request: Request) {
  return await auth0.middleware(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
};
```

This auto-mounts these routes (NOT `/api/auth/*` like v3):
- `/auth/login` — Redirect to Auth0 login
- `/auth/logout` — Clear session and redirect
- `/auth/callback` — Handle OAuth callback
- `/auth/profile` — User profile endpoint
- `/auth/access-token` — Get access token

### Layout with Auth0Provider

```tsx
// src/app/layout.tsx
import { Auth0Provider } from "@auth0/nextjs-auth0/client";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Auth0Provider>{children}</Auth0Provider>
      </body>
    </html>
  );
}
```

### Protected Server Component

```tsx
// src/app/page.tsx
import { auth0 } from "@/lib/auth0";

export default async function Home() {
  const session = await auth0.getSession();
  const user = session?.user;

  if (!user) {
    return <a href="/auth/login">Sign in</a>;
  }

  return (
    <div>
      <p>Welcome, {user.name}</p>
      <img src={user.picture} alt={user.name} />
      <a href="/auth/logout">Sign out</a>
    </div>
  );
}
```

### Client Components

```tsx
// src/components/LoginButton.tsx
"use client";
export default function LoginButton() {
  return <a href="/auth/login">Sign in with Auth0</a>;
}

// src/components/LogoutButton.tsx
"use client";
export default function LogoutButton() {
  return <a href="/auth/logout">Sign out</a>;
}
```

## Machine-to-Machine (M2M) Auth for AI Agent

The investigation agent authenticates using Client Credentials Flow:

```python
import requests

AUTH0_DOMAIN = "your-tenant.auth0.com"
AUTH0_CLIENT_ID = "agent_client_id"
AUTH0_CLIENT_SECRET = "agent_client_secret"
API_AUDIENCE = "https://api.commons.dev"

def get_agent_token():
    """Get an M2M access token for the investigation agent."""
    response = requests.post(
        f"https://{AUTH0_DOMAIN}/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": AUTH0_CLIENT_ID,
            "client_secret": AUTH0_CLIENT_SECRET,
            "audience": API_AUDIENCE
        },
        headers={"Content-Type": "application/json"}
    )
    data = response.json()
    return data["access_token"]  # JWT, expires in 86400s (24h)

# Use the token to call protected APIs
token = get_agent_token()
headers = {"Authorization": f"Bearer {token}"}
response = requests.get("https://api.commons.dev/investigate", headers=headers)
```

### Validate M2M Token (Python Backend)

```python
from jose import jwt
import requests

AUTH0_DOMAIN = "your-tenant.auth0.com"
API_AUDIENCE = "https://api.commons.dev"
ALGORITHMS = ["RS256"]

def get_jwks():
    """Fetch Auth0 JWKS for token verification."""
    jwks_url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
    return requests.get(jwks_url).json()

def verify_token(token: str) -> dict:
    """Verify and decode an Auth0 JWT access token."""
    jwks = get_jwks()
    unverified_header = jwt.get_unverified_header(token)

    rsa_key = {}
    for key in jwks["keys"]:
        if key["kid"] == unverified_header["kid"]:
            rsa_key = {
                "kty": key["kty"], "kid": key["kid"],
                "use": key["use"], "n": key["n"], "e": key["e"]
            }

    payload = jwt.decode(
        token, rsa_key,
        algorithms=ALGORITHMS,
        audience=API_AUDIENCE,
        issuer=f"https://{AUTH0_DOMAIN}/"
    )
    return payload
```

## Auth0 Dashboard Setup Checklist

### For the Web App (Journalist Login):
1. Create **Regular Web Application**
2. Set Allowed Callback URLs: `http://localhost:3000/auth/callback`
3. Set Allowed Logout URLs: `http://localhost:3000`
4. Note Client ID + Client Secret → `.env.local`

### For the AI Agent (M2M):
1. Create **Machine to Machine Application**
2. Select/create an API (Identifier = your audience URL)
3. Authorize the M2M app to call the API
4. Define scopes: `investigate:read`, `investigate:write`, `graph:read`
5. Note Client ID + Client Secret → agent config

### For the API:
1. Go to Applications → APIs → Create API
2. Name: "Commons API"
3. Identifier: `https://api.commons.dev` (this is the audience)
4. Define permissions/scopes

## Agent Skills Shortcut

Auth0 provides AI agent skills for automated setup:

```bash
npx skills add auth0/agent-skills --skill auth0-quickstart --skill auth0-nextjs
```

Then ask your AI assistant: "Add Auth0 authentication to my Next.js app"

## Commons Auth Flow Summary

| Flow | Who | How | Purpose |
|------|-----|-----|---------|
| Interactive Login | Journalist | Next.js SDK v4 | Browser session, view investigations |
| M2M Credentials | AI Agent | Client Credentials | API access for automated investigations |
| Anonymous | Public | No auth | View published findings (read-only) |

## Critical Rules

- v4 SDK uses `/auth/*` routes, NOT `/api/auth/*` (breaking change from v3)
- v4 uses `proxy.ts` NOT `[...auth0].ts` API route
- `Auth0Provider` is optional in v4 — only needed for `useUser()` hook
- M2M tokens expire in 86400s (24h) — cache and refresh before expiry
- Always validate tokens server-side using JWKS, never trust client-side
- Use `AUTH0_SECRET` of at least 32 bytes for session encryption
- Store secrets in `.env.local` (gitignored), never commit to repo

## Resources

- `references/nextjs-setup.md` — Step-by-step Next.js integration guide
- `references/m2m-flow.md` — M2M auth flow details and token management
