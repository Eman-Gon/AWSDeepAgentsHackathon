"""
SSE (Server-Sent Events) backend server for the Commons investigation platform.

This HTTP server bridges the Preact frontend to the Python investigation agent.
It exposes these endpoints:

  GET  /api/investigate?q=<query>  →  SSE stream of AgentStep events
  GET  /api/health                 →  Health check / readiness probe
  GET  /api/investigations         →  List saved investigations
  POST /api/investigations         →  Save a new investigation
  GET  /api/investigations/<id>    →  Get a specific investigation
  PATCH /api/investigations/<id>   →  Update investigation outcome
  GET  /api/pattern-confidence     →  Historical pattern confidence stats
  POST /api/tips                   →  Submit an anonymous tip (returns one-time token)
  GET  /api/tips/<token>           →  Retrieve a tip by one-time token (burns token)
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
import hashlib
import json
import mimetypes
import os
import re
import secrets
import signal
import sqlite3
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Load .env before importing the investigator so GEMINI_API_KEY, TURSO_*, etc. are available.
from dotenv import load_dotenv
load_dotenv()

from agent.graph_queries import (
    file_investigation,
    get_investigation,
    get_pattern_confidence,
    list_investigations,
    update_investigation_outcome,
)

# ── Backend selection: TrueFoundry gateway or direct Gemini ──────────────
# If TRUEFOUNDRY_BASE_URL is set in the environment, route all LLM calls
# through TrueFoundry AI Gateway (gives token cost tracking + observability).
# Otherwise fall back to direct Gemini (agent/investigator.py).
_BACKEND = "gemini"
if os.environ.get("TRUEFOUNDRY_BASE_URL"):
    try:
        from agent.truefoundry_backend import investigate_stream
        _BACKEND = "truefoundry"
    except ImportError:
        from agent.investigator import investigate_stream
else:
    from agent.investigator import investigate_stream

# ── CORS configuration ──────────────────────────────────────────────────
# Allow requests from the Vite dev server and common deployment origins
ALLOWED_ORIGINS = [
    "http://localhost:5173",      # Vite default dev server
    "http://localhost:5174",      # Vite alternate port
    "http://localhost:3000",      # common dev port
    "http://127.0.0.1:5173",
]

# ── Static file serving ──────────────────────────────────────────────────
# Path to the compiled Vite frontend (built by homepage/npm run build)
_STATIC_ROOT = Path(__file__).parent.parent / "homepage" / "dist"

# Wildcard Render origin pattern — allow any *.onrender.com subdomain
_RENDER_ORIGIN_SUFFIX = ".onrender.com"

# ── Anonymous tip database ─────────────────────────────────────────────────
# Tips are stored as one-time-retrieval records. The token stored in the DB
# is a SHA-256 hash of the raw token given to the tipster, so a DB breach
# cannot be used to retrieve tips without the original token.
_TIPS_DB_PATH = Path(__file__).parent.parent / "data" / "commons_tips.db"


def _tips_db() -> sqlite3.Connection:
    """Open (or create) the tips SQLite database."""
    _TIPS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_TIPS_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tips (
            token_hash TEXT PRIMARY KEY,  -- SHA-256 of the raw token given to tipster
            content    TEXT NOT NULL,      -- encrypted or plain tip content
            retrieved  INTEGER DEFAULT 0, -- 1 after the tip is retrieved (one-time)
            created_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bland_tips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT UNIQUE,
            transcript TEXT,
            summary TEXT,
            caller_number TEXT,
            call_length REAL,
            entities TEXT,  -- JSON array of extracted entity names
            status TEXT DEFAULT 'new',  -- new | reviewed | investigating
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def _cors_origin(request_origin: str | None) -> str:
    """Return the allowed origin for CORS headers.

    Allows:
      - Any origin explicitly in ALLOWED_ORIGINS (local dev)
      - Any *.onrender.com origin (production Render deployment)

    Otherwise falls back to the first allowed origin, which browsers
    will reject — effectively blocking unknown cross-origin requests.
    """
    if not request_origin:
        return ALLOWED_ORIGINS[0]
    if request_origin in ALLOWED_ORIGINS:
        return request_origin
    # Allow any Render subdomain (commons-ovyq.onrender.com, etc.)
    if request_origin.endswith(_RENDER_ORIGIN_SUFFIX):
        return request_origin
    return ALLOWED_ORIGINS[0]


def _extract_entities_from_transcript(text: str) -> list[str]:
    """Extract potential entity names from call transcript."""
    entities = set()

    # Multi-word capitalized names (e.g., "John Smith", "Recology Inc")
    for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text):
        name = match.group(1)
        # Skip common phrases
        if name.lower() not in ('thank you', 'good morning', 'good afternoon', 'good evening', 'how are'):
            entities.add(name)

    # Company patterns (word + LLC/Inc/Corp/Ltd)
    for match in re.finditer(r'\b([A-Z][\w]*(?:\s+\w+)*\s+(?:LLC|Inc|Corp|Ltd|Company|Group|Foundation))\b', text):
        entities.add(match.group(1))

    # Street addresses (number + street name)
    for match in re.finditer(r'\b(\d+\s+[A-Z][a-z]+(?:\s+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Way|Ct|Court|Pl|Place|Ln|Lane)\.?))\b', text):
        entities.add(match.group(1))

    return sorted(entities)


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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")  # cache preflight for 24h
        self.end_headers()

    def do_GET(self):
        """Route GET requests to the appropriate handler.

        API paths go to the Python handlers. Everything else is treated
        as a static file request and served from homepage/dist/. Unknown
        paths fall back to index.html (SPA client-side routing).
        """
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/investigate":
            self._handle_investigate(parsed)
        elif path == "/api/health":
            self._handle_health()
        elif path == "/api/investigations":
            self._handle_list_investigations()
        elif path.startswith("/api/investigations/"):
            inv_id = path[len("/api/investigations/"):]
            self._handle_get_investigation(inv_id)
        elif path == "/api/pattern-confidence":
            self._handle_pattern_confidence()
        elif path == "/api/bland-tips":
            self._handle_get_bland_tips(parsed)
        elif path.startswith("/api/tips/"):
            # GET /api/tips/<token> — retrieve a tip (one-time use)
            token = path[len("/api/tips/"):]
            self._handle_get_tip(token)
        elif path.startswith("/api/"):
            self._send_json({"error": "Not found"}, 404)
        else:
            # Serve static frontend files — fallback to index.html for SPA routing
            self._handle_static(path or "/")

    def do_POST(self):
        """Route POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/tips":
            self._handle_submit_tip()
        elif path == "/api/investigations":
            self._handle_save_investigation()
        elif path == "/api/bland-webhook":
            self._handle_bland_webhook()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_PATCH(self):
        """Route PATCH requests (investigation outcome updates)."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path.startswith("/api/investigations/"):
            inv_id = path[len("/api/investigations/"):]
            self._handle_update_outcome(inv_id)
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_submit_tip(self):
        """Accept an anonymous tip and return a one-time retrieval token.

        Auth flow explanation:
          - No Auth0 login required: any anonymous source can submit
          - A cryptographically random token is generated (256 bits)
          - Only the SHA-256 hash of that token is stored in the DB
          - The raw token is returned ONCE to the tipster — they must save it
          - A journalist can retrieve the tip by presenting the raw token
          - After retrieval the tip is marked 'retrieved' and cannot be read again

        This is the 'anonymous source' third auth track: tipsters never need
        an account, and the one-time nature means even a DB breach can't be
        used to re-read tips that have already been retrieved.
        """
        # Read request body (JSON)
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0 or content_length > 10_000:
            self._send_json({"error": "Invalid content length"}, 400)
            return

        try:
            body = json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        content = body.get("content", "").strip()
        if not content:
            self._send_json({"error": "Missing 'content' field"}, 400)
            return

        # Generate a 32-byte (256-bit) random token — this is what we give to the tipster
        raw_token = secrets.token_urlsafe(32)
        # Store only the hash — if the DB leaks, tokens are not exposed
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        conn = _tips_db()
        try:
            conn.execute(
                "INSERT INTO tips (token_hash, content, retrieved, created_at) VALUES (?, ?, 0, ?)",
                [token_hash, content, time.time()]
            )
            conn.commit()
        finally:
            conn.close()

        # Return the raw token once — the tipster must save it
        self._send_json({
            "status": "received",
            "token": raw_token,
            "message": (
                "Tip received. Save this token — it is the only way to retrieve your tip. "
                "Share it with a journalist via a secure channel."
            ),
        }, 201)

    def _handle_get_tip(self, raw_token: str):
        """Retrieve a tip by its one-time token (burns the token after retrieval).

        A journalist presents the raw token they received from a source.
        We hash it, look it up, return the content, and mark it retrieved.
        After this call the tip cannot be retrieved again.
        """
        if not raw_token or len(raw_token) > 100:
            self._send_json({"error": "Invalid token"}, 400)
            return

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        conn = _tips_db()
        try:
            row = conn.execute(
                "SELECT * FROM tips WHERE token_hash = ?", [token_hash]
            ).fetchone()

            if not row:
                self._send_json({"error": "Tip not found"}, 404)
                return

            if row["retrieved"]:
                self._send_json({"error": "Tip already retrieved (one-time use)"}, 410)
                return

            # Mark as retrieved BEFORE returning (no double-reads)
            conn.execute(
                "UPDATE tips SET retrieved = 1 WHERE token_hash = ?", [token_hash]
            )
            conn.commit()

            self._send_json({
                "status": "ok",
                "content": row["content"],
                "created_at": row["created_at"],
                "note": "This tip has now been permanently marked as retrieved and cannot be read again.",
            })
        finally:
            conn.close()

    # ── Investigation management endpoints ─────────────────────────────────

    def _handle_list_investigations(self):
        """Return all saved investigations (most recent first)."""
        self._send_json(list_investigations())

    def _handle_get_investigation(self, inv_id: str):
        """Return a single investigation by ID with full findings."""
        result = get_investigation(inv_id)
        if not result:
            self._send_json({"error": "Investigation not found"}, 404)
            return
        self._send_json(result)

    def _handle_save_investigation(self):
        """Save an investigation from the frontend.

        Expects JSON body: {title, summary, entity_ids, findings}
        """
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0 or content_length > 500_000:
            self._send_json({"error": "Invalid content length"}, 400)
            return

        try:
            body = json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        title = body.get("title", "").strip()
        summary = body.get("summary", "").strip()
        entity_ids = body.get("entity_ids", [])
        findings = body.get("findings", [])

        if not title:
            self._send_json({"error": "Missing 'title' field"}, 400)
            return

        result = file_investigation(
            title=title,
            summary=summary or "No summary provided.",
            entity_ids=entity_ids,
            findings=findings,
        )
        self._send_json(result, 201)

    def _handle_update_outcome(self, inv_id: str):
        """Update the outcome of a saved investigation.

        Expects JSON body: {outcome: "confirmed"|"dead_end"|"ongoing"|"published"}
        """
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0 or content_length > 10_000:
            self._send_json({"error": "Invalid content length"}, 400)
            return

        try:
            body = json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        outcome = body.get("outcome", "").strip()
        if not outcome:
            self._send_json({"error": "Missing 'outcome' field"}, 400)
            return

        result = update_investigation_outcome(inv_id, outcome)
        if "error" in result:
            self._send_json(result, 400)
            return
        self._send_json(result)

    def _handle_pattern_confidence(self):
        """Return historical pattern confidence statistics."""
        self._send_json(get_pattern_confidence())

    # ── Bland AI tip line endpoints ──────────────────────────────────────

    def _handle_bland_webhook(self):
        """Receive a Bland AI call completion webhook and store the tip.

        Bland sends a POST with call details (transcript, summary, caller info)
        when a call to the corruption tip line completes. We extract entity names
        from the transcript and store everything in the bland_tips table.
        """
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0 or content_length > 500_000:
            self._send_json({"error": "Invalid content length"}, 400)
            return

        try:
            body = json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        call_id = body.get("call_id", "")
        if not call_id:
            self._send_json({"error": "Missing 'call_id' field"}, 400)
            return

        transcript = body.get("concatenated_transcript", "")
        summary = body.get("summary", "")
        caller_number = body.get("from", "")
        call_length = body.get("call_length", 0.0)
        created_at = body.get("created_at", time.time())

        # Extract entity names from the transcript
        entities = _extract_entities_from_transcript(transcript) if transcript else []

        conn = _tips_db()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO bland_tips
                   (call_id, transcript, summary, caller_number, call_length, entities, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'new', ?)""",
                [call_id, transcript, summary, caller_number, call_length,
                 json.dumps(entities), created_at]
            )
            conn.commit()
        finally:
            conn.close()

        self._send_json({"status": "received", "call_id": call_id})

    def _handle_get_bland_tips(self, parsed):
        """Return all Bland AI call tips, optionally filtered by status.

        Query params:
          ?status=new|reviewed|investigating  — filter by tip status

        Returns a JSON array of tip objects ordered by created_at DESC.
        """
        params = parse_qs(parsed.query)
        status_filter = params.get("status", [None])[0]

        conn = _tips_db()
        try:
            if status_filter:
                rows = conn.execute(
                    "SELECT * FROM bland_tips WHERE status = ? ORDER BY created_at DESC",
                    [status_filter]
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM bland_tips ORDER BY created_at DESC"
                ).fetchall()

            tips = []
            for row in rows:
                tip = dict(row)
                try:
                    tip["entities"] = json.loads(tip["entities"]) if tip["entities"] else []
                except (json.JSONDecodeError, TypeError):
                    tip["entities"] = []
                tips.append(tip)

            self._send_json(tips)
        finally:
            conn.close()

    def _handle_health(self):
        """Health check endpoint — returns server status and active LLM backend.

        Useful for load balancers, Render health checks, or verifying
        the server is running before sending investigation requests.
        Reports which LLM backend is active so you can confirm TrueFoundry
        routing is working before trusting the observability dashboard.
        """
        self._send_json({
            "status": "ok",
            "service": "commons-agent",
            "llm_backend": _BACKEND,  # "gemini" or "truefoundry"
        })

    def _handle_static(self, url_path: str):
        """Serve static files from the compiled Vite build directory.

        Security note: we resolve the file path and verify it stays inside
        _STATIC_ROOT to prevent directory traversal attacks (e.g. ../etc/passwd).

        For SPA routing: if the requested path doesn't match a file, serve
        index.html so the frontend router handles it client-side.
        """
        if not _STATIC_ROOT.exists():
            # Frontend has not been built yet (dev mode without build step)
            self._send_json({"error": "Frontend not built. Run: cd homepage && npm run build"}, 503)
            return

        # Strip leading slash and resolve to a real path
        relative_path = url_path.lstrip("/")
        # Default to index.html for root requests
        if not relative_path:
            relative_path = "index.html"

        # Resolve and check for path traversal
        try:
            resolved = (_STATIC_ROOT / relative_path).resolve()
            # Ensure the resolved path is still inside our static root
            resolved.relative_to(_STATIC_ROOT.resolve())
        except (ValueError, OSError):
            # Path traversal attempt — refuse
            self._send_json({"error": "Forbidden"}, 403)
            return

        # Fall back to index.html if file doesn't exist (SPA routing)
        if not resolved.exists() or resolved.is_dir():
            resolved = _STATIC_ROOT / "index.html"

        # Read and serve the file
        try:
            content = resolved.read_bytes()
        except OSError:
            self._send_json({"error": "Not found"}, 404)
            return

        # Detect MIME type from file extension (default to octet-stream)
        mime_type, _ = mimetypes.guess_type(str(resolved))
        if mime_type is None:
            mime_type = "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        # Cache static assets (JS/CSS with hash names) aggressively, HTML not at all
        if resolved.suffix in (".js", ".css", ".woff", ".woff2", ".png", ".svg"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

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
        print(f"[commons-agent] {format % args}")


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
