import { setCorsHeaders } from './_cors.js';
import { checkRateLimit } from './_rate-limit.js';
import { requireAgentLogAccess } from './_auth.js';

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

  const auth = await requireAgentLogAccess(req);
  if (auth.error) return auth.error;

  const body = await req.json().catch(() => null);
  const message = typeof body?.message === 'string' ? body.message.trim() : '';

  if (!message) {
    return new Response(JSON.stringify({ error: 'Missing log message' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
    });
  }

  return new Response(JSON.stringify({
    status: 'logged',
    agentId: auth.principal.sub,
    message,
    at: new Date().toISOString(),
  }), {
    headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
  });
}
