import { setCorsHeaders } from './_cors.js';
import { checkRateLimit } from './_rate-limit.js';

export const config = { runtime: 'edge' };

/**
 * Anonymous tip submission proxy.
 *
 * This Vercel Edge Function proxies tip submissions to the Python backend.
 * No authentication required — this is the "anonymous source" auth track.
 *
 * POST /api/tips  { "content": "..." }
 *   → Backend generates a one-time token and returns it to the tipster
 *
 * GET  /api/tips/<token>
 *   → Returns the tip content and burns the token (one-time use)
 *
 * Rate limiting is applied to prevent abuse, but no Auth0 login is needed.
 */

const AGENT_BACKEND_URL =
  process.env.AGENT_BACKEND_URL || 'https://commons-ovyq.onrender.com';

export default async function handler(req) {
  // CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: setCorsHeaders({}) });
  }

  // Rate limit by IP to prevent spam submissions
  const limited = await checkRateLimit(req);
  if (limited) return limited;

  const url = new URL(req.url);
  const backendUrl = `${AGENT_BACKEND_URL}${url.pathname}`;

  // Proxy POST (submit tip) or GET (retrieve tip) to backend
  if (req.method === 'POST') {
    // Validate content length before forwarding
    const body = await req.text();
    let parsed;
    try {
      parsed = JSON.parse(body);
    } catch {
      return new Response(JSON.stringify({ error: 'Invalid JSON' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
      });
    }

    if (!parsed.content || typeof parsed.content !== 'string' || parsed.content.trim().length === 0) {
      return new Response(JSON.stringify({ error: "Missing 'content' field" }), {
        status: 400,
        headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
      });
    }

    // Enforce max tip length (10KB)
    if (parsed.content.length > 10_000) {
      return new Response(JSON.stringify({ error: 'Tip content too long (max 10,000 chars)' }), {
        status: 413,
        headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
      });
    }

    // Forward to backend
    let upstream;
    try {
      upstream = await fetch(backendUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: parsed.content }),
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: 'Backend unavailable', detail: String(err) }), {
        status: 503,
        headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
      });
    }

    const result = await upstream.json();
    return new Response(JSON.stringify(result), {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
    });

  } else if (req.method === 'GET') {
    // GET /api/tips/<token> — retrieve a tip
    let upstream;
    try {
      upstream = await fetch(backendUrl);
    } catch (err) {
      return new Response(JSON.stringify({ error: 'Backend unavailable', detail: String(err) }), {
        status: 503,
        headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
      });
    }
    const result = await upstream.json();
    return new Response(JSON.stringify(result), {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
    });
  }

  return new Response(JSON.stringify({ error: 'Method not allowed' }), {
    status: 405,
    headers: { 'Content-Type': 'application/json', ...setCorsHeaders({}) },
  });
}
