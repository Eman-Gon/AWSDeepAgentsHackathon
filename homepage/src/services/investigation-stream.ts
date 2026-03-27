/**
 * SSE client for consuming the investigation stream from the Python backend.
 *
 * Uses the Fetch API with streaming response body (ReadableStream) rather than
 * the EventSource API, because EventSource doesn't support custom headers
 * (we may need Authorization in the future) and has limited error handling.
 *
 * Flow:
 *   1. Frontend calls streamInvestigation(query, onStep)
 *   2. Opens a fetch to /api/investigate?q=<query>
 *   3. Reads SSE lines from the response stream
 *   4. Parses each "data: {...}" line as an AgentStep
 *   5. Calls onStep(step) for each parsed step
 *   6. Returns when it receives "data: [DONE]" or the stream closes
 */

import type { AgentStep } from '@/types';

// The backend URL is proxied through Vite in dev (/api → http://127.0.0.1:8000)
// and through Vercel serverless functions in production
const INVESTIGATE_URL = '/api/investigate';

/**
 * Open an SSE connection to the investigation backend and call onStep
 * for each AgentStep event received.
 *
 * @param query - The investigation query (e.g. "Recology SF")
 * @param onStep - Callback invoked with each AgentStep as it arrives
 * @param signal - Optional AbortSignal to cancel the stream (e.g. when
 *                 the user starts a new investigation before this one finishes)
 * @returns Promise that resolves when the stream completes
 */
export async function streamInvestigation(
  query: string,
  onStep: (step: AgentStep) => void,
  signal?: AbortSignal,
): Promise<void> {
  // Build the SSE URL with the query parameter
  const url = `${INVESTIGATE_URL}?q=${encodeURIComponent(query)}`;

  // Fetch with streaming — the response body is a ReadableStream
  const response = await fetch(url, {
    method: 'GET',
    headers: { Accept: 'text/event-stream' },
    signal,
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Investigation failed (${response.status}): ${body}`);
  }

  if (!response.body) {
    throw new Error('No response body — streaming not supported');
  }

  // Read the SSE stream line by line using a ReadableStream reader
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';  // accumulates partial lines between chunks

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Decode the chunk and add to our line buffer
      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by double newlines (\n\n)
      // Process all complete events in the buffer
      const parts = buffer.split('\n\n');

      // The last element might be incomplete, keep it in the buffer
      buffer = parts.pop() ?? '';

      for (const part of parts) {
        // Each SSE event line starts with "data: "
        const line = part.trim();
        if (!line.startsWith('data: ')) continue;

        const payload = line.slice(6);  // strip "data: " prefix

        // Check for the stream-complete sentinel
        if (payload === '[DONE]') return;

        // Parse the JSON AgentStep
        try {
          const step = JSON.parse(payload) as AgentStep;
          onStep(step);
        } catch {
          // Skip malformed events (shouldn't happen, but be resilient)
          console.warn('[commons] Failed to parse SSE event:', payload);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
