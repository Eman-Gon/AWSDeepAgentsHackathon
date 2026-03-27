# Auth0 — Trust Architecture

## Three Distinct Auth Flows

### 1. Journalist Authentication (User-to-Agent)

- Auth0 Universal Login with organization support
- Roles: `journalist`, `editor`, `newsroom_admin`, `public_reader`
- Role-based data visibility:
  - `public_reader` → public graph only
  - `journalist` → public graph + their private investigation workspace
  - `editor` → public graph + all investigations in their newsroom
  - `newsroom_admin` → everything + user management

```javascript
// Auth0 Action: Post-Login — Attach role-based permissions
exports.onExecutePostLogin = async (event, api) => {
  const roles = event.authorization?.roles || [];

  if (roles.includes('journalist')) {
    api.accessToken.setCustomClaim('commons/permissions', [
      'read:public_graph',
      'read:own_investigations',
      'write:own_investigations',
      'create:investigation'
    ]);
  }

  if (roles.includes('newsroom_admin')) {
    api.accessToken.setCustomClaim('commons/permissions', [
      'read:public_graph',
      'read:all_investigations',
      'write:all_investigations',
      'publish:findings',
      'manage:users'
    ]);
  }
};
```

### 2. Agent Authentication (Machine-to-Machine)

- Investigation agent runs autonomously — monitors filings, checks patterns, triggers alerts
- Auth0 M2M client credentials flow
- Scoped token: agent can READ all data sources and WRITE investigation log, but CANNOT publish to public graph
- Short-lived tokens (1 hour) with automatic refresh

```
// M2M Token for Investigation Agent
// Grant type: client_credentials
// Scopes: read:data_sources, write:investigation_log, read:graph
// NOT scoped for: publish:findings (requires human approval)
```

### 3. Anonymous Tip Submission

- NO account creation required
- Auth0 generates a one-time retrieval token (not tied to any identity)
- Tipster checks status using only the token
- Tip associated with investigation but tipster identity never stored
- Implementation: Auth0 Actions + custom token generation

### 4. Fine-Grained Authorization (OpenFGA) — Stretch

Relationship-based access model:
- `investigation:X` → `owner` → `journalist:Y`
- `investigation:X` → `viewer` → `newsroom:Z` (all members can view)
- `tip:A` → `associated_with` → `investigation:X` (no relation to tipster identity)

## Key Design Points

- Fred (Auth0 sponsor) emphasized M2M auth for agent-to-agent communication and OpenFGA
- Most teams add a login button — we build three distinct auth flows
- Source protection (anonymous tips) and autonomous agent auth are real journalism security needs
