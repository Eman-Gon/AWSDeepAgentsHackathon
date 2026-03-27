"""
migrate_to_turso.py — Upload the local SQLite knowledge graph to Turso cloud.

Strategy: dump to a SQL file then pipe into `turso db shell` (fastest: 30-90s).
Fallback: Turso HTTP /v2/pipeline API with batched INSERTs (5-10 min, no CLI).

Usage:
    python -m pipeline.migrate_to_turso [--db-name commons-graph] [--http]
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH       = Path(__file__).resolve().parent.parent / "data" / "commons_graph.db"
TURSO_DB_NAME = os.environ.get("TURSO_DB_NAME", "commons-graph")
TURSO_URL     = os.environ.get("TURSO_DATABASE_URL", "").rstrip("/")
TURSO_TOKEN   = os.environ.get("TURSO_AUTH_TOKEN", "")
HTTP_BATCH    = 200  # rows per HTTP request (keep low to avoid 30s timeouts)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY, type TEXT, name TEXT, aliases TEXT,
    properties TEXT, sources TEXT, first_seen TEXT, last_updated TEXT, flagged TEXT
);
CREATE TABLE IF NOT EXISTS edges (
    edge_id TEXT PRIMARY KEY, source_entity TEXT, target_entity TEXT,
    relationship TEXT, properties TEXT, source_dataset TEXT, confidence REAL
);
CREATE INDEX IF NOT EXISTS idx_edge_source ON edges(source_entity);
CREATE INDEX IF NOT EXISTS idx_edge_target ON edges(target_entity);
CREATE INDEX IF NOT EXISTS idx_edge_rel    ON edges(relationship);
CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(type);
"""


def _esc(v):
    """SQL-escape a Python value: None→NULL, numbers→literal, strings→quoted."""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


# ── Method 1: Turso CLI pipe (~30–90s for 400K rows) ─────────────────────────

def migrate_via_cli(db_name: str = TURSO_DB_NAME) -> None:
    """
    Stream the local SQLite DB into Turso via `turso db shell <db-name> < dump.sql`.

    This is the fastest path: the Turso CLI manages its own WebSocket
    connection and streams SQL natively without per-row HTTP overhead.
    Expected: ~30-90s for 186K entities + 245K edges.
    """
    print(f"Generating SQL dump for Turso DB: {db_name}")
    src = sqlite3.connect(str(DB_PATH))
    ec = src.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    ed = src.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    print(f"  Source: {ec:,} entities, {ed:,} edges")

    t0 = time.time()
    TX_BATCH = 1000  # rows per transaction — keeps each TX small enough for Turso
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
        fpath = f.name
        # Schema first (idempotent)
        f.write(SCHEMA_SQL + "\n")

        # Entities — commit every TX_BATCH rows
        batch_count = 0
        f.write("BEGIN TRANSACTION;\n")
        for i, row in enumerate(src.execute(
            "SELECT entity_id, type, name, aliases, properties, sources, "
            "first_seen, last_updated, flagged FROM entities"
        )):
            f.write(
                f"INSERT OR IGNORE INTO entities VALUES "
                f"({','.join(_esc(v) for v in row)});\n"
            )
            batch_count += 1
            if batch_count >= TX_BATCH:
                f.write("COMMIT;\nBEGIN TRANSACTION;\n")
                batch_count = 0
        f.write("COMMIT;\n")

        # Edges — same pattern
        batch_count = 0
        f.write("BEGIN TRANSACTION;\n")
        for row in src.execute(
            "SELECT edge_id, source_entity, target_entity, relationship, "
            "properties, source_dataset, confidence FROM edges"
        ):
            f.write(
                f"INSERT OR IGNORE INTO edges VALUES "
                f"({','.join(_esc(v) for v in row)});\n"
            )
            batch_count += 1
            if batch_count >= TX_BATCH:
                f.write("COMMIT;\nBEGIN TRANSACTION;\n")
                batch_count = 0
        f.write("COMMIT;\n")
    src.close()

    sz = Path(fpath).stat().st_size / 1_048_576
    print(f"  Dump: {sz:.1f} MB in {time.time()-t0:.0f}s. Uploading via CLI...")
    t1 = time.time()
    with open(fpath) as sql_f:
        result = subprocess.run(
            ["turso", "db", "shell", db_name],
            stdin=sql_f,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min safety timeout
        )
    os.unlink(fpath)

    if result.returncode != 0:
        print(f"  ✗ turso shell failed:\n{result.stderr[:2000]}")
        sys.exit(1)

    print(f"  ✓ Upload complete in {time.time()-t1:.0f}s")


# ── Method 2: Turso HTTP API (fallback, ~5–10 min for 400K rows) ─────────────

def migrate_via_http() -> None:
    """
    Upload via the Turso /v2/pipeline HTTP endpoint in small batches.
    Slower than CLI but works anywhere without the CLI installed.
    Uses INSERT OR IGNORE so it's safe to re-run after interruptions.
    """
    import requests  # type: ignore

    if not TURSO_URL or not TURSO_TOKEN:
        print("ERROR: TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set")
        sys.exit(1)

    hdrs = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}

    def run_batch(stmts: list[str]) -> None:
        payload = {
            "requests": [
                {"type": "execute", "stmt": {"sql": s}} for s in stmts if s.strip()
            ]
        }
        if not payload["requests"]:
            return
        for attempt in range(3):
            try:
                r = requests.post(
                    f"{TURSO_URL}/v2/pipeline", json=payload, headers=hdrs, timeout=30
                )
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                return
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    print("Using HTTP API fallback (turso CLI not found)")
    run_batch(SCHEMA_SQL.split(";"))

    src = sqlite3.connect(str(DB_PATH))
    for tbl, query in [
        (
            "entities",
            "SELECT entity_id, type, name, aliases, properties, sources, "
            "first_seen, last_updated, flagged FROM entities",
        ),
        (
            "edges",
            "SELECT edge_id, source_entity, target_entity, relationship, "
            "properties, source_dataset, confidence FROM edges",
        ),
    ]:
        total = src.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"Uploading {total:,} {tbl}...")
        t0, uploaded, batch = time.time(), 0, []
        for row in src.execute(query):
            batch.append(
                f"INSERT OR IGNORE INTO {tbl} VALUES "
                f"({','.join(_esc(v) for v in row)})"
            )
            if len(batch) >= HTTP_BATCH:
                run_batch(batch)
                uploaded += len(batch)
                batch = []
                pct = uploaded / total * 100
                rate = uploaded / max(1, time.time() - t0)
                print(f"  {uploaded:>7,}/{total:,} ({pct:.0f}%)  {rate:.0f}/s", end="\r")
        if batch:
            run_batch(batch)
            uploaded += len(batch)
        print(f"\n  ✓ {tbl}: {uploaded:,} in {time.time()-t0:.0f}s")
    src.close()


# ── Verification ──────────────────────────────────────────────────────────────

def verify(db_name: str = TURSO_DB_NAME) -> None:
    """Count rows in Turso to confirm the migration succeeded."""
    if not shutil.which("turso"):
        print("(CLI not found — skipping verification)")
        return
    print("\nVerifying row counts in Turso:")
    for tbl in ("entities", "edges"):
        r = subprocess.run(
            ["turso", "db", "shell", db_name, f"SELECT COUNT(*) FROM {tbl};"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            count = r.stdout.strip().splitlines()[-1]
            print(f"  {tbl}: {count}")
        else:
            print(f"  {tbl}: verification failed — {r.stderr[:200]}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate local SQLite knowledge graph to Turso cloud"
    )
    parser.add_argument("--db-name", default=TURSO_DB_NAME, help="Turso database name")
    parser.add_argument(
        "--http", action="store_true", help="Force HTTP mode (skip CLI even if available)"
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="Only verify row counts (no upload)"
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found. Run: python -m pipeline.run_pipeline")
        sys.exit(1)

    if args.verify_only:
        verify(args.db_name)
        sys.exit(0)

    t_start = time.time()
    if args.http or not shutil.which("turso"):
        migrate_via_http()
    else:
        migrate_via_cli(args.db_name)

    verify(args.db_name)
    print(f"\n✓ Total time: {time.time()-t_start:.0f}s")
