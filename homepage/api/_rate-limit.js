/**
 * Simple in-memory rate limiter for Edge Functions.
 * 100 requests per minute per IP.
 */
const store = new Map();

export async function checkRateLimit(req) {
  const ip = req.headers.get('x-forwarded-for') || 'unknown';
  const now = Date.now();
  const window = 60_000;
  const limit = 100;

  let entry = store.get(ip);
  if (!entry || now - entry.start > window) {
    entry = { start: now, count: 0 };
    store.set(ip, entry);
  }

  entry.count++;
  if (entry.count > limit) {
    return new Response(JSON.stringify({ error: 'Rate limited' }), {
      status: 429,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  return null;
}
