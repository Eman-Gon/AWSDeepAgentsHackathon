import { createRemoteJWKSet, jwtVerify } from 'jose';
import { setCorsHeaders } from './_cors.js';

const domain = process.env.AUTH0_DOMAIN;
const audience = process.env.AUTH0_AUDIENCE;
const claimsNamespace = process.env.AUTH0_CLAIMS_NAMESPACE || 'https://commons.app';
const issuer = domain ? `https://${domain}/` : '';
const jwks = issuer ? createRemoteJWKSet(new URL(`${issuer}.well-known/jwks.json`)) : null;

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
  });
}

function getBearerToken(req) {
  const authHeader = req.headers.get('authorization') || '';
  if (!authHeader.startsWith('Bearer ')) return null;
  return authHeader.slice('Bearer '.length);
}

function getRoles(payload) {
  const roles = payload[`${claimsNamespace}/roles`];
  return Array.isArray(roles) ? roles : [];
}

function getScopes(payload) {
  if (typeof payload.scope !== 'string') return [];
  return payload.scope.split(' ').filter(Boolean);
}

function isAgentToken(payload) {
  return payload.gty === 'client-credentials' || String(payload.sub || '').includes('@clients');
}

export async function requirePrincipal(req, mode = 'human') {
  if (!domain || !audience || !jwks) {
    return {
      error: json(500, { error: 'Missing Auth0 server configuration' }),
    };
  }

  const token = getBearerToken(req);
  if (!token) {
    return {
      error: json(401, { error: 'Missing bearer token' }),
    };
  }

  try {
    const { payload } = await jwtVerify(token, jwks, {
      issuer,
      audience,
    });

    const roles = getRoles(payload);
    const scopes = getScopes(payload);
    const agent = isAgentToken(payload);
    const principal = {
      sub: String(payload.sub || ''),
      roles,
      scopes,
      isAgent: agent,
      isHuman: !agent,
      payload,
      permissions: {
        canInvestigate: roles.includes('journalist') || roles.includes('editor'),
        canPublish: !agent && roles.includes('editor'),
        canWriteLogs: agent && (scopes.includes('agent:write_logs') || scopes.includes('write:logs')),
      },
    };

    if (mode === 'human' && principal.isAgent) {
      return { error: json(403, { error: 'Agent tokens are not allowed for this action' }) };
    }
    if (mode === 'agent' && !principal.isAgent) {
      return { error: json(403, { error: 'Only agent tokens are allowed for this action' }) };
    }

    return { principal };
  } catch {
    return {
      error: json(401, { error: 'Invalid or expired token' }),
    };
  }
}

export async function requireInvestigationAccess(req) {
  const result = await requirePrincipal(req, 'human');
  if (result.error) return result;
  if (!result.principal.permissions.canInvestigate) {
    return { error: json(403, { error: 'Investigation permission denied' }) };
  }
  return result;
}

export async function requirePublishAccess(req) {
  const result = await requirePrincipal(req, 'human');
  if (result.error) return result;
  if (!result.principal.permissions.canPublish) {
    return { error: json(403, { error: 'Publish permission denied' }) };
  }
  return result;
}

export async function requireAgentLogAccess(req) {
  const result = await requirePrincipal(req, 'agent');
  if (result.error) return result;
  if (!result.principal.permissions.canWriteLogs) {
    return { error: json(403, { error: 'Agent log permission denied' }) };
  }
  return result;
}
