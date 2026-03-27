"""
SSE (Server-Sent Events) backend server for the Commons investigation platform.

This HTTP server bridges the Preact frontend to the Python investigation agent.
It exposes these endpoints:

  GET  /api/investigate?q=<query>  →  SSE stream of AgentStep events
  GET  /api/health                 →  Health check / readiness probe
  OPTIONS /api/*                   →  CORS preflight responses

Each SSE event is a JSON-serialized AgentStep dict that the frontend
progressively renders into the graph, globe, narrative, and findings panels.

Usage:
    export GEMINI_API_KEY=<your-key>
    python -m agent.server                    # default: port 8000
    python -m agent.server --port 3001        # custom port
    python -m agent.server --host 0.0.0.0     # bind all interfaces
"""

import argparse
import json
import signal
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from agent.investigator import investigate_stream

# ── CORS configuration ──────────────────────────────────────────────────
# Allow requests from the Vite dev server and common deployment origins
ALLOWED_ORIGINS = [
    "http://localhost:5173",      # Vite default dev server
    "http://localhost:5174",      # Vite alternate port
    "http://localhost:3000",      # common dev port
    "http://127.0.0.1:5173",
]


def _cors_origin(request_origin: str | None) -> str:
    """Return the allowed origin for CORS headers.
    
    If the request origin is in our allowlist, echo it back.
    Otherwise return the first allowed origin (won't match browser's
    check, effectively blocking the request).
    """
    if request_origin and request_origin in ALLOWED_ORIGINS:
        return request_origin
    return ALLOWED_ORIGINS[0]


class InvestigationHandler(BaseHTTPRequestHandler):
    """HTTP request handler with SSE streaming for investigations.
    
    Routes:
      GET /api/investigate?q=<query>  — Streams AgentStep events via SSE
      GET /api/health                 — Returns 200 with status JSON
      OPTIONS *                       — CORS preflight
    """

    def do_OPTIONS(self):
        """Handle CORS preflight requests.
        
        Browsers send OPTIONS before cross-origin requests. We respond
        with the appropriate Access-Control headers to allow the request.
        """
        origin = self.headers.get("Origin")
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", _cors_origin(origin))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")  # cache preflight for 24h
        self.end_headers()

    def do_GET(self):
        """Route GET requests to the appropriate handler."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/investigate":
            self._handle_investigate(parsed)
        elif path == "/api/health":
            self._handle_health()
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_health(self):
        """Health check endpoint — returns server status.
        
        Useful for load balancers, Vercel proxies, or just verifying
        the server is running before sending investigation requests.
        """
        self._send_json({"status": "ok", "service": "commons-agent"})

    def _handle_investigate(self, parsed):
        """Stream an investigation as Server-Sent Events (SSE).
        
        The frontend opens an EventSource connection to this endpoint.
        We run the investigation agent and yield each AgentStep as an
        SSE `data:` line. The frontend parses each event and updates
        the graph, narrative, and findings panels in real time.
        
        SSE format:
          data: {"tool":"search_entity","message":"...","nodes":[...],...}
          
          data: {"tool":"traverse_connections","message":"...","nodes":[...],...}
          
          data: [DONE]
        
        The final `[DONE]` sentinel tells the frontend the stream is over.
        """
        # Parse the query parameter
        params = parse_qs(parsed.query)
        query = params.get("q", [None])[0]

        if not query:
            self._send_json({"error": "Missing ?q= parameter"}, 400)
            return

        # Validate query length to prevent abuse
        if len(query) > 500:
            self._send_json({"error": "Query too long (max 500 chars)"}, 400)
            return

        origin = self.headers.get("Origin")

        # Set up SSE response headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", _cors_origin(origin))
        self.send_header("X-Accel-Buffering", "no")  # disable nginx buffering
        self.end_headers()

        try:
            # Run the streaming investigation and emit each step as SSE
            for step in investigate_stream(query, verbose=True, max_turns=15):
                # Format as SSE: "data: <json>\n\n"
                event_data = json.dumps(step, default=str)
                self.wfile.write(f"data: {event_data}\n\n".encode())
                self.wfile.flush()  # flush immediately so frontend gets it

            # Send the completion sentinel
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected mid-stream — this is normal (e.g., user
            # started a new investigation before the previous one finished)
            pass
        except Exception as e:
            # Send error as SSE event so frontend can display it
            error_event = json.dumps({"error": str(e)})
            try:
                self.wfile.write(f"data: {error_event}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _send_json(self, data: dict, status: int = 200):
        """Send a JSON response with CORS headers.
        
        Used for non-streaming responses like health checks and errors.
        """
        origin = self.headers.get("Origin")
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", _cors_origin(origin))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Override default logging to add a prefix for clarity."""
        print(f"[commons-agent] {args[0]} {args[1]} {args[2]}")


def serve(host: str = "127.0.0.1", port: int = 8000):
    """Start the HTTP server and block until interrupted.
    
    Args:
        host: Network interface to bind to. Use "0.0.0.0" for all interfaces.
        port: TCP port number. Default 8000 to avoid conflicting with Vite (5173).
    """
    server = HTTPServer((host, port), InvestigationHandler)
    print(f"[commons-agent] SSE server running at http://{host}:{port}")
    print(f"[commons-agent] Investigation endpoint: http://{host}:{port}/api/investigate?q=<query>")
    print(f"[commons-agent] Health check: http://{host}:{port}/api/health")
    print(f"[commons-agent] Press Ctrl+C to stop")

    # Handle graceful shutdown on SIGINT/SIGTERM
    def shutdown(signum, frame):
        print("\n[commons-agent] Shutting down...")
        # Shut down in a separate thread to avoid deadlock
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Commons Investigation SSE Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()
    serve(args.host, args.port)
