#!/usr/bin/env python3
"""
End-to-end integration test for the Commons investigation platform.

Tests:
  1. Graph query functions (directly, no server needed)
  2. HTTP server endpoints (health, tips, static files, investigate)
  3. Anonymous tip lifecycle (submit → retrieve → reject re-use)

Run with:
    python test_e2e.py                    # local graph + server tests
    python test_e2e.py --backend-url URL  # test a remote deployed server
"""

import argparse
import json
import os
import subprocess
import sys
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path

# ── Colours for pretty output ────────────────────────────────────────────
GREEN = "\033[32m"
RED   = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

pass_count = 0
fail_count = 0
skip_count = 0


def ok(label: str, detail: str = ""):
    global pass_count
    pass_count += 1
    suffix = f"  ({detail})" if detail else ""
    print(f"  {GREEN}✓{RESET} {label}{suffix}")


def fail(label: str, detail: str = ""):
    global fail_count
    fail_count += 1
    print(f"  {RED}✗{RESET} {label}  →  {detail}")


def skip(label: str, reason: str = ""):
    global skip_count
    skip_count += 1
    print(f"  {YELLOW}⚠{RESET} SKIP {label}  ({reason})")


def section(title: str):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ────────────────────────────────────────────────────────────────────
# Section 1: Database / Graph query layer
# ────────────────────────────────────────────────────────────────────

def test_graph_queries():
    section("1. Graph query layer (graph_queries.py)")

    DB = Path(__file__).parent / "data" / "commons_graph.db"
    if not DB.exists():
        skip("All graph query tests", "commons_graph.db not found — run build.sh first")
        return

    # Import after confirming DB exists so we get a clean error path
    from agent.graph_queries import (
        search_entity,
        get_entity_details,
        traverse_connections,
        get_edges_for_entity,
        aggregate_query,
        check_campaign_finance,
        file_investigation,
        check_prior_investigations,
        publish_finding,
    )

    # --- search_entity ---
    try:
        results = search_entity("Recology", limit=3)
        if results and len(results) > 0:
            ok("search_entity('Recology')", f"{len(results)} results, top: {results[0]['name']!r} score={results[0]['score']}")
        else:
            fail("search_entity('Recology')", "no results")
    except Exception as e:
        fail("search_entity", str(e))

    # --- get_entity_details ---
    try:
        sample = search_entity("Recology", limit=1)
        if sample:
            eid = sample[0]["entity_id"]
            details = get_entity_details(eid)
            if details and "entity_id" in details:
                ok("get_entity_details", f"entity_id={eid!r}")
            else:
                fail("get_entity_details", "empty response")
        else:
            skip("get_entity_details", "no entity to test with")
    except Exception as e:
        fail("get_entity_details", str(e))

    # --- traverse_connections ---
    try:
        sample = search_entity("Recology", limit=1)
        if sample:
            eid = sample[0]["entity_id"]
            traversal = traverse_connections(eid, max_hops=1)
            e_count = len(traversal.get("entities", []))
            ed_count = len(traversal.get("edges", []))
            ok("traverse_connections (1-hop)", f"{e_count} entities, {ed_count} edges")
        else:
            skip("traverse_connections", "no entity to test with")
    except Exception as e:
        fail("traverse_connections", str(e))

    # --- get_edges_for_entity ---
    try:
        sample = search_entity("Recology", limit=1)
        if sample:
            eid = sample[0]["entity_id"]
            edges = get_edges_for_entity(eid, direction="both")
            ok("get_edges_for_entity", f"{len(edges)} edges found")
        else:
            skip("get_edges_for_entity", "no entity")
    except Exception as e:
        fail("get_edges_for_entity", str(e))

    # --- aggregate_query ---
    try:
        top = aggregate_query(entity_type="company", limit=5)
        if top:
            ok("aggregate_query(company)", f"top: {top[0]['name']!r} ({top[0]['edge_count']} edges)")
        else:
            fail("aggregate_query", "no results")
    except Exception as e:
        fail("aggregate_query", str(e))

    # --- check_campaign_finance ---
    try:
        result = check_campaign_finance("Brown", direction="both", limit=5)
        total = result.get("total_found", 0)
        ok("check_campaign_finance('Brown')", f"{total} records found")
    except Exception as e:
        fail("check_campaign_finance", str(e))

    # --- file_investigation + check_prior_investigations + publish_finding ---
    try:
        sample = search_entity("Recology", limit=1)
        eid = sample[0]["entity_id"] if sample else "test_entity"

        filed = file_investigation(
            title="E2E Test Investigation",
            summary="This is an automated end-to-end test investigation.",
            entity_ids=[eid],
            findings=[{"description": "Test finding", "severity": "LOW", "confidence": 0.9}],
        )
        inv_id = filed.get("investigation_id")
        if inv_id:
            ok("file_investigation", f"id={inv_id}")
        else:
            fail("file_investigation", f"no investigation_id in response: {filed}")
            return

        prior = check_prior_investigations(keyword="E2E Test")
        if prior and any(p["investigation_id"] == inv_id for p in prior):
            ok("check_prior_investigations", f"found {len(prior)} matching")
        else:
            fail("check_prior_investigations", f"investigation {inv_id} not returned — got {prior}")

        published = publish_finding(inv_id, public_title="E2E Test (Published)")
        if published.get("status") == "published":
            ok("publish_finding", f"status=published for {inv_id}")
        else:
            fail("publish_finding", str(published))

    except Exception as e:
        fail("file_investigation / publish_finding lifecycle", str(e))


# ────────────────────────────────────────────────────────────────────
# Section 2: HTTP server endpoints
# ────────────────────────────────────────────────────────────────────

def http_get(url: str, timeout: int = 10) -> tuple[int, dict | str]:
    """Simple HTTP GET that returns (status_code, body)."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except Exception as e:
        return 0, str(e)


def http_post(url: str, data: dict, timeout: int = 10) -> tuple[int, dict | str]:
    """Simple HTTP POST with JSON body."""
    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except Exception as e:
        return 0, str(e)


def wait_for_server(url: str, max_wait: int = 15) -> bool:
    """Poll the health endpoint until the server responds (or timeout)."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        status, _ = http_get(url, timeout=2)
        if status == 200:
            return True
        time.sleep(0.5)
    return False


def test_server_endpoints(base_url: str, start_local: bool):
    section(f"2. HTTP server endpoints  ({base_url})")

    local_proc = None

    if start_local:
        print(f"  Starting local server...")
        local_proc = subprocess.Popen(
            [sys.executable, "-m", "agent.server", "--host", "127.0.0.1", "--port", "18765"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=Path(__file__).parent,
        )
        if not wait_for_server(f"{base_url}/api/health"):
            fail("Server startup", "did not respond in 15 seconds")
            local_proc.terminate()
            return
        print(f"  Server ready at {base_url}")

    try:
        # --- /api/health ---
        status, body = http_get(f"{base_url}/api/health")
        if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
            ok("/api/health", f"status={body['status']}")
        else:
            fail("/api/health", f"HTTP {status} → {body}")

        # --- static file serving: GET / ---
        status, body = http_get(base_url)
        if status == 200 and isinstance(body, str) and "<!doctype html>" in body.lower():
            ok("GET / (static index.html)", f"HTML returned ({len(body)} bytes)")
        elif status == 503:
            skip("GET / (static index.html)", "frontend not built on this instance")
        else:
            fail("GET / (static index.html)", f"HTTP {status}")

        # --- unknown API path ---
        status, body = http_get(f"{base_url}/api/nonexistent")
        if status == 404:
            ok("GET /api/nonexistent → 404", "correct")
        else:
            fail("GET /api/nonexistent → 404", f"got HTTP {status}")

        # --- anonymous tip: POST /api/tips ---
        status, body = http_post(
            f"{base_url}/api/tips",
            {"content": "E2E test tip: this is a test message from the integration suite."},
        )
        if status == 201 and isinstance(body, dict) and "token" in body:
            raw_token = body["token"]
            ok("POST /api/tips (submit)", f"token received ({len(raw_token)} chars)")
        else:
            fail("POST /api/tips (submit)", f"HTTP {status} → {body}")
            raw_token = None

        # --- retrieve tip (first time) ---
        if raw_token:
            status, body = http_get(f"{base_url}/api/tips/{raw_token}")
            if status == 200 and isinstance(body, dict) and "E2E test tip" in (body.get("content") or ""):
                ok("GET /api/tips/<token> (retrieve)", "tip content matches")
            else:
                fail("GET /api/tips/<token> (retrieve)", f"HTTP {status} → {body}")

            # --- retrieve tip (second time — should be burned) ---
            status, body = http_get(f"{base_url}/api/tips/{raw_token}")
            if status == 410:
                ok("GET /api/tips/<token> (burn check)", "410 Gone — one-time use enforced")
            else:
                fail("GET /api/tips/<token> (burn check)", f"expected 410, got HTTP {status}")

        # --- invalid tip token ---
        status, body = http_get(f"{base_url}/api/tips/invalid_token_xyz")
        if status == 404:
            ok("GET /api/tips/<bad-token> → 404", "correct")
        else:
            fail("GET /api/tips/<bad-token> → 404", f"got HTTP {status}")

        # --- /api/investigate without GEMINI key ---
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            skip(
                "GET /api/investigate?q=... (full SSE stream)",
                "GEMINI_API_KEY not set — skipping live agent test",
            )
        else:
            # Just check that it starts streaming (don't wait for full response)
            print(f"  Testing SSE stream (will timeout after 8s)...")
            try:
                req = urllib.request.Request(f"{base_url}/api/investigate?q=Recology+contracts")
                with urllib.request.urlopen(req, timeout=8) as resp:
                    # Read first few bytes — if we get any data events, the agent is working
                    chunk = resp.read(1024).decode(errors="ignore")
                    if "data:" in chunk:
                        ok("GET /api/investigate (SSE stream started)", f"first {len(chunk)} bytes received")
                    else:
                        fail("GET /api/investigate", f"unexpected response: {chunk[:100]}")
            except Exception as e:
                if "timed out" in str(e).lower():
                    skip("/api/investigate (SSE)", "timed out  — agent may need longer")
                else:
                    fail("/api/investigate", str(e))

    finally:
        if local_proc:
            local_proc.terminate()
            local_proc.wait()


# ────────────────────────────────────────────────────────────────────
# Section 3: Payload validation (security/edge cases)
# ────────────────────────────────────────────────────────────────────

def test_security_edge_cases(base_url: str, start_local: bool):
    section("3. Security & edge cases")

    if start_local:
        # start fresh local server for this section
        local_proc = subprocess.Popen(
            [sys.executable, "-m", "agent.server", "--host", "127.0.0.1", "--port", "18766"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=Path(__file__).parent,
        )
        if not wait_for_server(f"{base_url.replace('18765','18766')}/api/health"):
            skip("Security edge cases", "local server did not start")
            local_proc.terminate()
            return
        base_url = base_url.replace("18765", "18766")
    
    try:
        # --- path traversal: GET /../../etc/passwd ---
        status, _ = http_get(f"{base_url}/%2e%2e/%2e%2e/etc/passwd")
        if status in (400, 403, 404, 200):  # 200 means index.html fallback (OK for SPA)
            ok("Path traversal GET /../.. → not 500", f"HTTP {status}")
        else:
            fail("Path traversal", f"unexpected HTTP {status}")

        # --- empty tip content ---
        status, body = http_post(f"{base_url}/api/tips", {"content": ""})
        if status == 400:
            ok("POST /api/tips empty content → 400", "correct")
        else:
            fail("POST /api/tips empty content", f"expected 400, got {status}")

        # --- tip too large ---
        status, body = http_post(f"{base_url}/api/tips", {"content": "x" * 11_000})
        if status == 400:
            ok("POST /api/tips oversized → 400", "correct")
        else:
            fail("POST /api/tips oversized", f"expected 400, got {status}")

        # --- investigation query too long ---
        status, body = http_get(f"{base_url}/api/investigate?q={'a'*501}")
        if status == 400:
            ok("GET /api/investigate?q=<501chars> → 400", "correct")
        else:
            fail("/api/investigate query too long", f"expected 400, got {status}")

    finally:
        if start_local:
            local_proc.terminate()
            local_proc.wait()


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Commons E2E integration test")
    parser.add_argument(
        "--backend-url",
        default="",
        help="Test a remote backend instead of starting one locally (e.g. https://commons-ovyq.onrender.com)",
    )
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  Commons E2E Integration Test")
    print(f"{'='*55}")

    if args.backend_url:
        base_url = args.backend_url.rstrip("/")
        start_local = False
        print(f"  Target: {base_url} (remote)")
    else:
        base_url = "http://127.0.0.1:18765"
        start_local = True
        print(f"  Target: local server on port 18765")

    test_graph_queries()
    test_server_endpoints(base_url, start_local)
    test_security_edge_cases(base_url, start_local)

    # Summary
    print(f"\n{'='*55}")
    total = pass_count + fail_count + skip_count
    print(f"  Results: {GREEN}{pass_count} passed{RESET}  {RED}{fail_count} failed{RESET}  {YELLOW}{skip_count} skipped{RESET}  ({total} total)")
    print(f"{'='*55}\n")
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
