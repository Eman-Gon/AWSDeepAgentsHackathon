import { setCorsHeaders } from './_cors.js';
import { checkRateLimit } from './_rate-limit.js';
import { requirePublishAccess } from './_auth.js';

export const config = { runtime: 'edge' };

export default async function handler(req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: setCorsHeaders({}) });
  }

  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), {
      status: 405,
      headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
    });
  }

  const limited = await checkRateLimit(req);
  if (limited) return limited;

  const auth = await requirePublishAccess(req);
  if (auth.error) return auth.error;

  const body = await req.json().catch(() => null);
  const findings = Array.isArray(body?.findings) ? body.findings : [];

  if (findings.length === 0) {
    return new Response(JSON.stringify({ error: 'No findings supplied' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
    });
  }

  return new Response(JSON.stringify({
    status: 'published',
    publishedBy: auth.principal.sub,
    findingsCount: findings.length,
  }), {
    headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
  });
}
