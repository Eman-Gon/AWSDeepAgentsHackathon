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
import mimetypes
import os
import signal
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ── LLM backend selection ───────────────────────────────────────────────
# When TRUEFOUNDRY_BASE_URL is set, route LLM calls through TrueFoundry's
# AI Gateway (OpenAI-compatible). Otherwise use the default Gemini backend.
# Both backends expose the same investigate_stream() interface.
_TF_BASE_URL = os.environ.get("TRUEFOUNDRY_BASE_URL", "")
if _TF_BASE_URL:
    from agent.truefoundry_backend import investigate_stream
    _BACKEND_NAME = f"truefoundry ({_TF_BASE_URL})"
else:
    from agent.investigator import investigate_stream
    _BACKEND_NAME = "gemini-flash"

# ── CORS configuration ──────────────────────────────────────────────────
# Allow requests from the Vite dev server and common deployment origins
ALLOWED_ORIGINS = [
    "http://localhost:5173",      # Vite default dev server
    "http://localhost:5174",      # Vite alternate port
    "http://localhost:3000",      # common dev port
    "http://127.0.0.1:5173",
]

# ── Static file serving (production) ────────────────────────────────────
# In production the Python server also serves the built Vite frontend.
# In dev, Vite's dev server proxies /api requests to us instead.
STATIC_DIR = Path(__file__).resolve().parent.parent / "homepage" / "dist"

# Common MIME types for static assets (mimetypes module may miss some)
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/webp", ".webp")


def _cors_origin(request_origin: str | None) -> str:
    """Return the allowed origin for CORS headers.
    
    If the request origin is in our allowlist or matches a *.onrender.com
    domain, echo it back. Otherwise return the first allowed origin
    (won't match browser's check, effectively blocking the request).
    """
    if request_origin:
        if request_origin in ALLOWED_ORIGINS:
            return request_origin
        # Accept any *.onrender.com origin for Render deployments
        if request_origin.endswith(".onrender.com"):
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
            # Serve static frontend files from homepage/dist/ in production
            self._serve_static(path)

    def _handle_health(self):
        """Health check endpoint — returns server status.
        
        Useful for load balancers, Vercel proxies, or just verifying
        the server is running before sending investigation requests.
        """
        self._send_json({"status": "ok", "service": "commons-agent", "llm_backend": _BACKEND_NAME})

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

    def _serve_static(self, path: str):
        """Serve static files from the Vite build output.

        Handles SPA routing by falling back to index.html for paths
        that don't match a real file (e.g. /investigate → index.html).
        """
        if not STATIC_DIR.is_dir():
            self._send_json({"error": "Frontend not built. Run: cd homepage && npm run build"}, 404)
            return

        # Map URL path to a file on disk
        # Strip leading slash and resolve relative to STATIC_DIR
        rel_path = path.lstrip("/")
        file_path = STATIC_DIR / rel_path if rel_path else STATIC_DIR / "index.html"

        # If the path points to a directory, look for index.html inside it
        if file_path.is_dir():
            file_path = file_path / "index.html"

        # SPA fallback: if no matching file, serve index.html
        # so the frontend router can handle the URL
        if not file_path.is_file():
            file_path = STATIC_DIR / "index.html"

        if not file_path.is_file():
            self._send_json({"error": "Not found"}, 404)
            return

        # Security: ensure the resolved path is inside STATIC_DIR
        # to prevent directory traversal attacks (e.g. ../../etc/passwd)
        try:
            file_path.resolve().relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._send_json({"error": "Forbidden"}, 403)
            return

        # Determine Content-Type from the file extension
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"

        # Read and serve the file
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Cache static assets with hashed filenames aggressively
        if "/assets/" in path:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

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
    print(f"[commons-agent] LLM backend: {_BACKEND_NAME}")
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
    # Render (and most PaaS) inject PORT env var — use it if present
    port = int(os.environ.get("PORT", args.port))
    serve(args.host, port)
