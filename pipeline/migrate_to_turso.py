"""
migrate_to_turso.py — Upload the local SQLite knowledge graph to Turso cloud.

Reads from data/commons_graph.db (local SQLite) and uploads all entities
and edges to the Turso remote database in large batches via libsql HTTP API.

Turso uses the libsql wire protocol over HTTP, so we POST directly to the
/v2/pipeline endpoint which supports batch INSERT for speed.

Usage:
    python -m pipeline.migrate_to_turso [--start-entity N] [--start-edge N]

Environment variables required:
    TURSO_DATABASE_URL  — e.g. libsql://commons-graph-xxx.turso.io
    TURSO_AUTH_TOKEN    — JWT token from `turso db tokens create <db>`
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

# Load .env from project root so TURSO_* vars are available
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import requests

# ── Configuration ─────────────────────────────────────────────────────────────

# Local SQLite source database
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "commons_graph.db"

# Turso connection (read from environment)
TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "").rstrip("/")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

# Batch size for INSERT statements — Turso handles large batches well
ENTITY_BATCH = 300   # entities per HTTP request
EDGE_BATCH = 300     # edges per HTTP request


def turso_execute_batch(statements: list[dict]) -> dict:
    """
    Send a batch of SQL statements to Turso via the /v2/pipeline HTTP endpoint.

    Each statement is a dict: {"type": "execute", "stmt": {"sql": "..."}}
    Turso executes them atomically (all succeed or all fail).

    Returns the JSON response from Turso.
    Raises requests.HTTPError on failure.
    """
    url = TURSO_URL.replace("libsql://", "https://") + "/v2/pipeline"
    headers = {
        "Authorization": f"Bearer {TURSO_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"requests": statements + [{"type": "close"}]}
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _sql_str(val) -> str:
    """Escape a Python value for inline SQL (single-quoted string or NULL)."""
    if val is None:
        return "NULL"
    # Convert dicts/lists to JSON strings for storage
    if isinstance(val, (dict, list)):
        val = json.dumps(val)
    # Escape single quotes by doubling them (standard SQL escaping)
    return "'" + str(val).replace("'", "''") + "'"


def init_schema():
    """Create the entities and edges tables in Turso if they don't exist."""
    print("Initialising schema in Turso...")
    # Mirror the exact schema from pipeline/aerospike_loader.py
    stmts = [
        {
            "type": "execute",
            "stmt": {
                "sql": """
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id    TEXT PRIMARY KEY,
                    type         TEXT,
                    name         TEXT,
                    aliases      TEXT,
                    properties   TEXT,
                    sources      TEXT,
                    first_seen   TEXT,
                    last_updated TEXT,
                    flagged      TEXT
                )"""
            },
        },
        {
            "type": "execute",
            "stmt": {
                "sql": """
                CREATE TABLE IF NOT EXISTS edges (
                    edge_id        TEXT PRIMARY KEY,
                    source_entity  TEXT,
                    target_entity  TEXT,
                    relationship   TEXT,
                    properties     TEXT,
                    source_dataset TEXT,
                    confidence     REAL
                )"""
            },
        },
        # Index for graph traversal queries (source → outbound edges)
        {
            "type": "execute",
            "stmt": {"sql": "CREATE INDEX IF NOT EXISTS idx_edge_source ON edges(source_entity)"},
        },
        # Index for reverse traversal (target → inbound edges)
        {
            "type": "execute",
            "stmt": {"sql": "CREATE INDEX IF NOT EXISTS idx_edge_target ON edges(target_entity)"},
        },
        # Index for filtering by relationship type
        {
            "type": "execute",
            "stmt": {"sql": "CREATE INDEX IF NOT EXISTS idx_edge_rel ON edges(relationship)"},
        },
        # Index for entity type lookups (e.g. "get all companies")
        {
            "type": "execute",
            "stmt": {"sql": "CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(type)"},
        },
    ]
    turso_execute_batch(stmts)
    print("  Schema ready.")


def migrate_entities(conn: sqlite3.Connection, start_offset: int = 0):
    """Upload all entities from local SQLite to Turso in batches."""

    # Count total for progress reporting
    total = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    print(f"\nMigrating entities: {total:,} total, starting at offset {start_offset:,}")

    uploaded = 0
    offset = start_offset
    t0 = time.time()

    while True:
        # Fetch next batch from local SQLite
        rows = conn.execute(
            "SELECT entity_id, type, name, aliases, properties, sources, "
            "first_seen, last_updated, flagged FROM entities LIMIT ? OFFSET ?",
            (ENTITY_BATCH, offset),
        ).fetchall()

        if not rows:
            break  # done

        # Build INSERT OR IGNORE statements (skip rows already in Turso)
        stmts = []
        for row in rows:
            sql = (
                f"INSERT OR IGNORE INTO entities "
                f"(entity_id, type, name, aliases, properties, sources, first_seen, last_updated, flagged) "
                f"VALUES ({_sql_str(row[0])}, {_sql_str(row[1])}, {_sql_str(row[2])}, "
                f"{_sql_str(row[3])}, {_sql_str(row[4])}, {_sql_str(row[5])}, "
                f"{_sql_str(row[6])}, {_sql_str(row[7])}, {_sql_str(row[8])})"
            )
            stmts.append({"type": "execute", "stmt": {"sql": sql}})

        turso_execute_batch(stmts)
        uploaded += len(rows)
        offset += len(rows)

        elapsed = time.time() - t0
        rate = uploaded / elapsed if elapsed > 0 else 0
        pct = (offset / total) * 100
        eta = (total - offset) / rate if rate > 0 else 0
        print(
            f"  {offset:>7,}/{total:,} ({pct:.1f}%)  "
            f"{rate:.0f} rows/s  ETA {eta:.0f}s",
            end="\r",
        )

    print(f"\n  ✓ Entities done: {uploaded:,} uploaded in {time.time()-t0:.0f}s")


def migrate_edges(conn: sqlite3.Connection, start_offset: int = 0):
    """Upload all edges from local SQLite to Turso in batches."""

    total = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    print(f"\nMigrating edges: {total:,} total, starting at offset {start_offset:,}")

    uploaded = 0
    offset = start_offset
    t0 = time.time()

    while True:
        rows = conn.execute(
            "SELECT edge_id, source_entity, target_entity, relationship, "
            "properties, source_dataset, confidence FROM edges LIMIT ? OFFSET ?",
            (EDGE_BATCH, offset),
        ).fetchall()

        if not rows:
            break

        stmts = []
        for row in rows:
            sql = (
                f"INSERT OR IGNORE INTO edges "
                f"(edge_id, source_entity, target_entity, relationship, "
                f"properties, source_dataset, confidence) "
                f"VALUES ({_sql_str(row[0])}, {_sql_str(row[1])}, {_sql_str(row[2])}, "
                f"{_sql_str(row[3])}, {_sql_str(row[4])}, {_sql_str(row[5])}, "
                f"{_sql_str(row[6])})"
            )
            stmts.append({"type": "execute", "stmt": {"sql": sql}})

        turso_execute_batch(stmts)
        uploaded += len(rows)
        offset += len(rows)

        elapsed = time.time() - t0
        rate = uploaded / elapsed if elapsed > 0 else 0
        pct = (offset / total) * 100
        eta = (total - offset) / rate if rate > 0 else 0
        print(
            f"  {offset:>7,}/{total:,} ({pct:.1f}%)  "
            f"{rate:.0f} rows/s  ETA {eta:.0f}s",
            end="\r",
        )

    print(f"\n  ✓ Edges done: {uploaded:,} uploaded in {time.time()-t0:.0f}s")


def main():
    parser = argparse.ArgumentParser(description="Migrate local SQLite graph to Turso")
    parser.add_argument("--start-entity", type=int, default=0,
                        help="Skip this many entities (resume from offset)")
    parser.add_argument("--start-edge", type=int, default=0,
                        help="Skip this many edges (resume from offset)")
    parser.add_argument("--entities-only", action="store_true",
                        help="Only migrate entities (skip edges)")
    parser.add_argument("--edges-only", action="store_true",
                        help="Only migrate edges (skip entities)")
    args = parser.parse_args()

    # Validate environment
    if not TURSO_URL:
        print("ERROR: TURSO_DATABASE_URL not set in environment", file=sys.stderr)
        sys.exit(1)
    if not TURSO_TOKEN:
        print("ERROR: TURSO_AUTH_TOKEN not set in environment", file=sys.stderr)
        sys.exit(1)
    if not DB_PATH.exists():
        print(f"ERROR: Local SQLite DB not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Source DB:  {DB_PATH} ({DB_PATH.stat().st_size / 1e6:.1f} MB)")
    print(f"Target URL: {TURSO_URL}")

    # Open local source database (read-only)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    # Create schema in Turso if needed
    if not args.edges_only:
        init_schema()

    if not args.edges_only:
        migrate_entities(conn, start_offset=args.start_entity)

    if not args.entities_only:
        migrate_edges(conn, start_offset=args.start_edge)

    conn.close()

    # Report final counts in Turso
    print("\nVerifying Turso counts...")
    result = turso_execute_batch([
        {"type": "execute", "stmt": {"sql": "SELECT COUNT(*) FROM entities"}},
        {"type": "execute", "stmt": {"sql": "SELECT COUNT(*) FROM edges"}},
    ])
    results = result.get("results", [])
    if len(results) >= 2:
        try:
            entity_count = results[0]["response"]["result"]["rows"][0][0]["value"]
            edge_count = results[1]["response"]["result"]["rows"][0][0]["value"]
            print(f"  Turso entities: {entity_count:,}")
            print(f"  Turso edges:    {edge_count:,}")
        except (KeyError, IndexError):
            pass

    print("\n✓ Migration complete!")


if __name__ == "__main__":
    main()
