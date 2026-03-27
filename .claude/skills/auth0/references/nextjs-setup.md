# Auth0 Next.js v4 Setup Guide

## Step-by-Step Integration

### 1. Install SDK

```bash
npm install @auth0/nextjs-auth0
```

### 2. Create Auth0 Application

1. Go to [Auth0 Dashboard](https://manage.auth0.com/) → Applications
2. Click "Create Application"
3. Select "Regular Web Application"
4. Go to Settings tab
5. Note: **Domain**, **Client ID**, **Client Secret**
6. Set **Allowed Callback URLs**: `http://localhost:3000/auth/callback`
7. Set **Allowed Logout URLs**: `http://localhost:3000`
8. Set **Allowed Web Origins**: `http://localhost:3000`
9. Save Changes

### 3. Environment Variables

```env
# .env.local (MUST be gitignored)
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_CLIENT_ID=your_client_id
AUTH0_CLIENT_SECRET=your_client_secret
AUTH0_SECRET=use-openssl-rand-base64-32-to-generate
APP_BASE_URL=http://localhost:3000
```

Generate AUTH0_SECRET:
```bash
openssl rand -base64 32
```

### 4. Create Project Files

```bash
mkdir -p src/lib src/components
touch src/lib/auth0.ts src/proxy.ts
touch src/components/LoginButton.tsx src/components/LogoutButton.tsx src/components/Profile.tsx
```

### 5. Auth0 Client

```typescript
// src/lib/auth0.ts
import { Auth0Client } from '@auth0/nextjs-auth0/server';

export const auth0 = new Auth0Client();
```

### 6. Proxy (Middleware)

```typescript
// src/proxy.ts
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

### 7. Layout with Provider

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

### 8. Protected Page

```tsx
// src/app/page.tsx
import { auth0 } from "@/lib/auth0";
import LoginButton from "@/components/LoginButton";
import LogoutButton from "@/components/LogoutButton";

export default async function Home() {
  const session = await auth0.getSession();
  const user = session?.user;

  return (
    <main>
      {user ? (
        <div>
          <p>Welcome, {user.name}</p>
          <img src={user.picture} alt={user.name} />
          <LogoutButton />
        </div>
      ) : (
        <div>
          <p>Sign in to access investigations</p>
          <LoginButton />
        </div>
      )}
    </main>
  );
}
```

### 9. Components

```tsx
// src/components/LoginButton.tsx
"use client";
export default function LoginButton() {
  return (
    <a href="/auth/login"
       className="px-6 py-3 bg-blue-600 text-white rounded-lg">
      Sign in with Auth0
    </a>
  );
}

// src/components/LogoutButton.tsx
"use client";
export default function LogoutButton() {
  return (
    <a href="/auth/logout"
       className="px-6 py-3 bg-gray-600 text-white rounded-lg">
      Sign out
    </a>
  );
}

// src/components/Profile.tsx
"use client";
import { useUser } from "@auth0/nextjs-auth0/client";

export default function Profile() {
  const { user, isLoading } = useUser();
  if (isLoading) return <div>Loading...</div>;
  if (!user) return null;

  return (
    <div>
      <img src={user.picture || ""} alt={user.name || ""} />
      <h2>{user.name}</h2>
      <p>{user.email}</p>
    </div>
  );
}
```

## v3 → v4 Migration Notes

| v3 | v4 |
|----|----|
| `pages/api/auth/[...auth0].ts` | `src/proxy.ts` |
| `/api/auth/login` | `/auth/login` |
| `UserProvider` | `Auth0Provider` (optional) |
| `getSession(req, res)` | `auth0.getSession()` |
| `withApiAuthRequired` | Server-side `auth0.getSession()` check |
| `withPageAuthRequired` | Server-side `auth0.getSession()` check |

## Protecting API Routes (v4)

```typescript
// src/app/api/investigate/route.ts
import { auth0 } from "@/lib/auth0";
import { NextResponse } from "next/server";

export async function GET() {
  const session = await auth0.getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // User is authenticated
  const userId = session.user.sub;
  // ... handle investigation request
  return NextResponse.json({ user: session.user });
}
```

## Roles & Permissions (RBAC)

1. In Auth0 Dashboard → User Management → Roles
2. Create roles: `journalist`, `editor`, `admin`
3. Assign permissions to roles
4. Enable RBAC in API settings
5. Access roles in the token:

```typescript
// After enabling "Add Permissions in the Access Token" in API settings
const session = await auth0.getSession();
const permissions = session?.accessTokenScope; // space-separated scopes
```
