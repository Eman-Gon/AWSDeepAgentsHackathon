"""
migrate_to_turso.py — Upload the local SQLite knowledge graph to Turso cloud.

Reads from data/commons_graph.db (local SQLite) and uploads all entities
and edges to the Turso remote database using the libsql_experimental SDK.

The libsql_experimental package creates an embedded replica locally and
syncs it to the remote Turso database via WebSocket. This is much faster
and more reliable than the raw HTTP /v2/pipeline endpoint.

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

import libsql_experimental as libsql

# ── Configuration ─────────────────────────────────────────────────────────────

# Local SQLite source database
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "commons_graph.db"

# Turso connection (read from environment)
TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "").rstrip("/")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

# Batch size for executemany — sync after each batch
ENTITY_BATCH = 500   # entities per sync call
EDGE_BATCH = 500     # edges per sync call

# Local replica file (libsql_experimental uses an embedded local SQLite cache)
REPLICA_PATH = "/tmp/commons_turso_replica.db"


def open_turso() -> libsql.Connection:
    """
    Open a connection to the Turso remote database via libsql_experimental.

    libsql_experimental creates a local SQLite file (REPLICA_PATH) that
    acts as an embedded replica: reads come from the local replica,
    writes go to local first, then conn.sync() pushes to remote Turso.
    """
    conn = libsql.connect(REPLICA_PATH, sync_url=TURSO_URL, auth_token=TURSO_TOKEN)
    conn.sync()   # pull latest state from remote before writing
    return conn


def init_schema(conn):
    """Create the entities and edges tables in Turso if they don't exist."""
    print("Initialising schema in Turso...")
    # Mirror the exact schema from pipeline/aerospike_loader.py
    conn.executescript("""
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
        );
        CREATE TABLE IF NOT EXISTS edges (
            edge_id        TEXT PRIMARY KEY,
            source_entity  TEXT,
            target_entity  TEXT,
            relationship   TEXT,
            properties     TEXT,
            source_dataset TEXT,
            confidence     REAL
        );
        CREATE INDEX IF NOT EXISTS idx_edge_source ON edges(source_entity);
        CREATE INDEX IF NOT EXISTS idx_edge_target ON edges(target_entity);
        CREATE INDEX IF NOT EXISTS idx_edge_rel ON edges(relationship);
        CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(type);
    """)
    conn.commit()
    conn.sync()   # push schema to remote
    print("  Schema ready.")


def migrate_entities(src: sqlite3.Connection, dst: libsql.Connection, start_offset: int = 0):
    """Upload all entities from local SQLite to Turso in batches using executemany."""

    total = src.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    print(f"\nMigrating entities: {total:,} total, starting at offset {start_offset:,}")

    uploaded = 0
    offset = start_offset
    t0 = time.time()

    while True:
        # Fetch next batch from local SQLite source
        rows = src.execute(
            "SELECT entity_id, type, name, aliases, properties, sources, "
            "first_seen, last_updated, flagged FROM entities LIMIT ? OFFSET ?",
            (ENTITY_BATCH, offset),
        ).fetchall()

        if not rows:
            break   # done

        # Insert into local libsql replica
        # INSERT OR IGNORE skips rows already present (safe to re-run)
        dst.executemany(
            "INSERT OR IGNORE INTO entities "
            "(entity_id, type, name, aliases, properties, sources, first_seen, last_updated, flagged) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]) for r in rows],
        )
        dst.commit()
        # Sync local replica to remote Turso
        dst.sync()

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


def migrate_edges(src: sqlite3.Connection, dst: libsql.Connection, start_offset: int = 0):
    """Upload all edges from local SQLite to Turso in batches."""

    total = src.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    print(f"\nMigrating edges: {total:,} total, starting at offset {start_offset:,}")

    uploaded = 0
    offset = start_offset
    t0 = time.time()

    while True:
        rows = src.execute(
            "SELECT edge_id, source_entity, target_entity, relationship, "
            "properties, source_dataset, confidence FROM edges LIMIT ? OFFSET ?",
            (EDGE_BATCH, offset),
        ).fetchall()

        if not rows:
            break

        dst.executemany(
            "INSERT OR IGNORE INTO edges "
            "(edge_id, source_entity, target_entity, relationship, "
            "properties, source_dataset, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows],
        )
        dst.commit()
        dst.sync()

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
    print(f"Replica:    {REPLICA_PATH}")

    # Open local source database (read-only)
    src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    # Open Turso destination via libsql_experimental embedded replica
    print("\nConnecting to Turso...")
    dst = open_turso()
    print("  Connected.")

    # Create schema in Turso if needed (always safe — IF NOT EXISTS)
    if not args.edges_only:
        init_schema(dst)

    if not args.edges_only:
        migrate_entities(src, dst, start_offset=args.start_entity)

    if not args.entities_only:
        migrate_edges(src, dst, start_offset=args.start_edge)

    src.close()

    # Report final counts in Turso via a fresh sync
    print("\nVerifying Turso counts...")
    dst.sync()
    entity_count = dst.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    edge_count = dst.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    print(f"  Turso entities: {entity_count:,}")
    print(f"  Turso edges:    {edge_count:,}")
    print("\n✓ Migration complete!")


if __name__ == "__main__":
    main()
