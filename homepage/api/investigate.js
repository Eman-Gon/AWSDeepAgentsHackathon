import { setCorsHeaders } from './_cors.js';
import { checkRateLimit } from './_rate-limit.js';
import { requireInvestigationAccess } from './_auth.js';

export const config = { runtime: 'edge' };

/**
 * SSE endpoint for investigation queries.
 * Proxies to the backend agent and streams AgentStep events.
 *
 * For now returns mock data. Replace with real agent backend URL.
 */
export default async function handler(req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: setCorsHeaders({}) });
  }

  const limited = await checkRateLimit(req);
  if (limited) return limited;

  const auth = await requireInvestigationAccess(req);
  if (auth.error) return auth.error;

  const { searchParams } = new URL(req.url);
  const query = searchParams.get('q');

  if (!query) {
    return new Response(JSON.stringify({ error: 'Missing ?q= parameter' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
    });
  }

  // TODO: Replace with real backend agent SSE proxy
  // const upstream = await fetch(`${AGENT_BACKEND_URL}/investigate?q=${encodeURIComponent(query)}`);
  // return new Response(upstream.body, { headers: { 'Content-Type': 'text/event-stream', ...setCorsHeaders({}) } });

  return new Response(JSON.stringify({
    status: 'ok',
    query,
    actor: auth.principal.sub,
    message: 'Agent backend not yet connected. Using client-side mock data.',
  }), {
    headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
  });
}
