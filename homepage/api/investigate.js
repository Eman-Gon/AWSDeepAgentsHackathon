import { setCorsHeaders } from './_cors.js';
import { checkRateLimit } from './_rate-limit.js';
import { requireInvestigationAccess } from './_auth.js';

export const config = { runtime: 'edge' };

/**
 * SSE proxy to the Python investigation backend on Render.
 *
 * This Vercel Edge Function:
 *  1. Authenticates the request via Auth0 JWT
 *  2. Rate-limits by IP
 *  3. Proxies to AGENT_BACKEND_URL (the Render Python service) as SSE
 *
 * The Python backend runs the Gemini-powered investigation agent and
 * streams AgentStep events that the frontend renders in real time.
 *
 * Set AGENT_BACKEND_URL in Vercel env vars (or .env.local for dev):
 *   AGENT_BACKEND_URL=https://commons-ovyq.onrender.com
 */

// Backend URL — defaults to Render deployment, overridable via env var
const AGENT_BACKEND_URL =
  process.env.AGENT_BACKEND_URL || 'https://commons-ovyq.onrender.com';

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

  // Proxy the request to the Python backend SSE endpoint.
  // The backend streams AgentStep JSON events separated by "\n\n".
  // We forward those directly to the browser as a ReadableStream.
  const backendUrl = `${AGENT_BACKEND_URL}/api/investigate?q=${encodeURIComponent(query)}`;

  let upstream;
  try {
    upstream = await fetch(backendUrl, {
      // Forward the Authorization header so the backend can log the actor
      headers: {
        'X-Commons-Actor': auth.principal.sub,
        'X-Commons-Role': auth.principal.role || 'journalist',
        'Accept': 'text/event-stream',
      },
      // Edge runtime signal for 60s timeout (investigations can take a while)
      signal: AbortSignal.timeout(60_000),
    });
  } catch (err) {
    // Backend unreachable (probably sleeping on Render free tier — cold start)
    return new Response(
      JSON.stringify({
        error: 'Investigation backend is starting up. Please retry in 30 seconds.',
        detail: String(err),
      }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
      }
    );
  }

  if (!upstream.ok) {
    const text = await upstream.text();
    return new Response(
      JSON.stringify({ error: `Backend error ${upstream.status}`, detail: text }),
      {
        status: upstream.status,
        headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
      }
    );
  }

  // Stream the SSE response directly to the browser
  return new Response(upstream.body, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
      ...setCorsHeaders({}),
    },
  });
}
