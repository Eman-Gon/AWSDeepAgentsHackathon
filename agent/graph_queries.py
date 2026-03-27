"""
Graph query layer for the Commons investigation agent.

Provides Python functions that query the SQLite knowledge graph.
Each function maps 1:1 to a Gemini function-calling tool so the
LLM can autonomously explore the graph during an investigation.

SQLite schema (populated by pipeline/aerospike_loader.py):
  entities: entity_id TEXT PK, type, name, aliases (JSON), properties (JSON),
            sources (JSON), first_seen, last_updated, flagged (JSON)
  edges:    edge_id TEXT PK, source_entity, target_entity, relationship,
            properties (JSON), source_dataset, confidence REAL

Investigations schema (commons_investigations.db — write-enabled):
  investigations: id TEXT PK, title, summary, entity_ids (JSON), findings (JSON),
                  status TEXT, created_at REAL, published_at REAL
"""

import json
import os
import sqlite3
import time
import uuid
from typing import Optional

from thefuzz import fuzz

# ── Path to the pre-seeded SQLite graph database (read-only) ──────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "commons_graph.db")

# ── Path to the writable investigations database ──────────────────────────
# Separate from the main graph so we can open it read-write
INV_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "commons_investigations.db")

# ── Turso cloud database config (production / Render) ─────────────────────
# When TURSO_DATABASE_URL + TURSO_AUTH_TOKEN are set, queries use the Turso
# HTTP API directly (no local replica sync — instant cold start).
_TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "")
_TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")


class _TursoHTTPConn:
    """
    Minimal sqlite3.Connection-compatible wrapper for the Turso HTTP API.

    Uses the Turso /v2/pipeline REST endpoint so we never need to
    sync a local replica. Queries go directly to the cloud database,
    which keeps cold-start time near zero on Render.
    """

    def __init__(self, url: str, token: str) -> None:
        import requests  # type: ignore

        # Convert libsql:// URL to HTTPS for the REST endpoint
        self.base = url.replace("libsql://", "https://")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._requests = requests
        # row_factory attribute for compatibility with sqlite3-style code
        self.row_factory = None

    def execute(self, sql: str, params: tuple = ()):
        """Execute a single SQL statement and return a cursor-like object."""
        # Build the Turso-flavoured bound parameter list
        args = [
            {"type": "text", "value": str(v)} if not isinstance(v, (int, float))
            else {"type": "integer" if isinstance(v, int) else "float", "value": v}
            for v in params
        ]
        payload = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": args}}
            ]
        }
        for attempt in range(3):
            try:
                r = self._requests.post(
                    f"{self.base}/v2/pipeline",
                    json=payload,
                    headers=self.headers,
                    timeout=60,  # Turso full-table LIKE scans can take 10-30s
                )
                r.raise_for_status()
                data = r.json()
                result = data["results"][0]["response"]["result"]
                cols = [c["name"] for c in result["cols"]]

                # Convert Turso row format → sqlite3.Row-compatible namedtuples
                rows = []
                for raw_row in result["rows"]:
                    vals = [cell.get("value") for cell in raw_row]
                    rows.append(_TursoRow(cols, vals))
                return _TursoFakeCursor(rows)
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(0.5)

    def close(self):
        pass  # Nothing to close for HTTP


class _TursoRow:
    """sqlite3.Row-compatible row that supports both index and key access."""

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._vals[self._cols.index(key)]

    def keys(self):
        return self._cols

    def __iter__(self):
        return iter(self._vals)


class _TursoFakeCursor:
    """Cursor-like wrapper returned by _TursoHTTPConn.execute()."""

    def __init__(self, rows):
        self._rows = rows
        self._idx = 0

    def fetchall(self):
        return self._rows

    def fetchone(self):
        if self._rows:
            return self._rows[0]
        return None

    def __iter__(self):
        return iter(self._rows)


def _connect() -> sqlite3.Connection:
    """Open a connection to the graph DB.

    Priority:
    1. Turso cloud HTTP API — when TURSO_DATABASE_URL + TURSO_AUTH_TOKEN are set
    2. Local SQLite file — development fallback
    """
    if _TURSO_URL and _TURSO_TOKEN:
        # Use HTTP API: no local replica sync, instant cold start
        return _TursoHTTPConn(_TURSO_URL, _TURSO_TOKEN)  # type: ignore
    # Local development fallback: open the pre-seeded SQLite file read-only
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row          # dict-like access to columns
    return conn


def _connect_investigations() -> sqlite3.Connection:
    """Open a read-write SQLite connection to the investigations DB.

    Creates the investigations table if it doesn't exist yet.
    This is a separate database so the main graph stays read-only.
    """
    os.makedirs(os.path.dirname(INV_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(INV_DB_PATH)
    conn.row_factory = sqlite3.Row
    # Create investigations table on first use
    conn.execute("""
        CREATE TABLE IF NOT EXISTS investigations (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            summary     TEXT NOT NULL,
            entity_ids  TEXT NOT NULL DEFAULT '[]',  -- JSON array of entity_ids
            findings    TEXT NOT NULL DEFAULT '[]',  -- JSON array of finding dicts
            status      TEXT NOT NULL DEFAULT 'draft',  -- draft | published
            outcome     TEXT NOT NULL DEFAULT 'ongoing',  -- ongoing | confirmed | dead_end | published
            created_at  REAL NOT NULL,
            published_at REAL
        )
    """)
    # Add outcome column if upgrading from older schema
    try:
        conn.execute("ALTER TABLE investigations ADD COLUMN outcome TEXT NOT NULL DEFAULT 'ongoing'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    return conn


# ──────────────────────────────────────────────────────────────────────────
# Tool 1: search_entity — fuzzy name lookup
# ──────────────────────────────────────────────────────────────────────────

def search_entity(name: str, entity_type: Optional[str] = None, limit: int = 10) -> list[dict]:
    """
    Search the knowledge graph for entities matching a name (fuzzy).

    Args:
        name: The name to search for (e.g. "Recology", "Willie Brown").
        entity_type: Optional filter — "person", "company", "department",
                     "contract", "campaign", or "address".
        limit: Max results to return (default 10).

    Returns:
        List of matching entities sorted by fuzzy match score, each with:
          entity_id, type, name, score, properties, sources
    """
    conn = _connect()
    try:
        # For Turso HTTP connections: use FTS5 virtual table for fast name lookup.
        # For local SQLite: use LIKE which is fast on an in-process DB.
        is_turso = isinstance(conn, _TursoHTTPConn)

        if is_turso:
            # FTS5 MATCH uses tokenized full-text search — much faster than LIKE on remote DB.
            # Append '*' for prefix matching so "Recol" matches "Recology", etc.
            fts_term = name.replace('"', '""')  # escape quotes in FTS5 MATCH syntax
            if entity_type:
                query = (
                    "SELECT e.entity_id, e.type, e.name, e.aliases, e.properties, "
                    "e.sources, e.first_seen, e.last_updated, e.flagged "
                    "FROM entities e "
                    "JOIN entities_fts fts ON fts.entity_id = e.entity_id "
                    "WHERE fts.name MATCH ? AND e.type = ? LIMIT 100"
                )
                params: list = [f'"{fts_term}"*', entity_type]
            else:
                query = (
                    "SELECT e.entity_id, e.type, e.name, e.aliases, e.properties, "
                    "e.sources, e.first_seen, e.last_updated, e.flagged "
                    "FROM entities e "
                    "JOIN entities_fts fts ON fts.entity_id = e.entity_id "
                    "WHERE fts.name MATCH ? LIMIT 100"
                )
                params = [f'"{fts_term}"*']
        else:
            # Local SQLite LIKE — instant on in-process DB
            query = "SELECT * FROM entities WHERE name LIKE ?"
            params = [f"%{name}%"]

            if entity_type:
                query += " AND type = ?"
                params.append(entity_type)

            query += " LIMIT 100"

        rows = conn.execute(query, params).fetchall()

        # Score each row by fuzzy token-sort ratio against the search term
        scored = []
        for row in rows:
            score = fuzz.token_sort_ratio(name.upper(), row["name"].upper())
            scored.append({
                "entity_id": row["entity_id"],
                "type": row["type"],
                "name": row["name"],
                "score": score,
                "properties": json.loads(row["properties"] or "{}"),
                "sources": json.loads(row["sources"] or "[]"),
            })

        # Sort descending by match quality, take top N
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Tool 2: traverse_connections — BFS multi-hop graph walk
# ──────────────────────────────────────────────────────────────────────────

def traverse_connections(
    entity_id: str,
    max_hops: int = 2,
    relationship_filter: Optional[str] = None,
) -> dict:
    """
    BFS traversal from a starting entity through the knowledge graph.

    Args:
        entity_id: The entity_id to start from (e.g. "company:recology_abc123").
        max_hops: How many hops to traverse (1-3, default 2).
        relationship_filter: Only follow edges of this type (e.g. "DONATED_TO").

    Returns:
        Dict with:
          entities: list of discovered entity dicts (with depth)
          edges: list of traversed edge dicts
          summary: text summary of what was found
    """
    conn = _connect()
    try:
        max_hops = min(max_hops, 3)  # cap at 3 hops to avoid explosion
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(entity_id, 0)]
        found_entities: list[dict] = []
        found_edges: list[dict] = []

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_hops:
                continue
            visited.add(current_id)

            # Fetch the entity record
            row = conn.execute(
                "SELECT * FROM entities WHERE entity_id = ?", (current_id,)
            ).fetchone()
            if row:
                found_entities.append({
                    "entity_id": row["entity_id"],
                    "type": row["type"],
                    "name": row["name"],
                    "depth": depth,
                    "properties": json.loads(row["properties"] or "{}"),
                })

            if depth >= max_hops:
                continue  # don't expand further from max-depth nodes

            # Find outbound edges (this entity is source)
            edge_query = "SELECT * FROM edges WHERE source_entity = ?"
            edge_params: list = [current_id]
            if relationship_filter:
                edge_query += " AND relationship = ?"
                edge_params.append(relationship_filter)

            for edge in conn.execute(edge_query, edge_params).fetchall():
                found_edges.append(_edge_to_dict(edge))
                queue.append((edge["target_entity"], depth + 1))

            # Find inbound edges (this entity is target)
            edge_query2 = "SELECT * FROM edges WHERE target_entity = ?"
            edge_params2: list = [current_id]
            if relationship_filter:
                edge_query2 += " AND relationship = ?"
                edge_params2.append(relationship_filter)

            for edge in conn.execute(edge_query2, edge_params2).fetchall():
                found_edges.append(_edge_to_dict(edge))
                queue.append((edge["source_entity"], depth + 1))

        # Build a short summary string
        type_counts: dict[str, int] = {}
        for e in found_entities:
            type_counts[e["type"]] = type_counts.get(e["type"], 0) + 1
        rel_counts: dict[str, int] = {}
        for e in found_edges:
            rel_counts[e["relationship"]] = rel_counts.get(e["relationship"], 0) + 1

        summary = (
            f"Traversed {len(found_entities)} entities over {max_hops} hops: "
            + ", ".join(f"{v} {k}(s)" for k, v in type_counts.items())
            + ". Edges: "
            + ", ".join(f"{v} {k}" for k, v in rel_counts.items())
        )

        return {
            "entities": found_entities[:200],   # cap to avoid huge payloads
            "edges": found_edges[:500],
            "summary": summary,
        }
    finally:
        conn.close()


def _edge_to_dict(edge: sqlite3.Row) -> dict:
    """Convert a SQLite Row for an edge into a plain dict."""
    return {
        "edge_id": edge["edge_id"],
        "source_entity": edge["source_entity"],
        "target_entity": edge["target_entity"],
        "relationship": edge["relationship"],
        "properties": json.loads(edge["properties"] or "{}"),
        "source_dataset": edge["source_dataset"],
        "confidence": edge["confidence"],
    }


# ──────────────────────────────────────────────────────────────────────────
# Tool 3: get_entity_details — full record for a known entity_id
# ──────────────────────────────────────────────────────────────────────────

def get_entity_details(entity_id: str) -> Optional[dict]:
    """
    Get full details for a specific entity by its ID.

    Args:
        entity_id: Exact entity_id (e.g. "company:recology_abc123").

    Returns:
        Full entity dict with all properties, aliases, sources, etc.
        None if entity not found.
    """
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "entity_id": row["entity_id"],
            "type": row["type"],
            "name": row["name"],
            "aliases": json.loads(row["aliases"] or "[]"),
            "properties": json.loads(row["properties"] or "{}"),
            "sources": json.loads(row["sources"] or "[]"),
            "first_seen": row["first_seen"],
            "last_updated": row["last_updated"],
            "flagged_in_investigations": json.loads(row["flagged"] or "[]"),
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Tool 4: get_edges_for_entity — all edges to/from a specific entity
# ──────────────────────────────────────────────────────────────────────────

def get_edges_for_entity(
    entity_id: str,
    relationship: Optional[str] = None,
    direction: str = "both",
) -> list[dict]:
    """
    Get all edges connected to a specific entity.

    Args:
        entity_id: The entity to query edges for.
        relationship: Optional filter (e.g. "CONTRACTED_WITH").
        direction: "outbound", "inbound", or "both" (default).

    Returns:
        List of edge dicts with source_entity, target_entity, relationship, etc.
    """
    conn = _connect()
    try:
        edges = []

        if direction in ("outbound", "both"):
            q = "SELECT * FROM edges WHERE source_entity = ?"
            p: list = [entity_id]
            if relationship:
                q += " AND relationship = ?"
                p.append(relationship)
            edges.extend(_edge_to_dict(r) for r in conn.execute(q, p).fetchall())

        if direction in ("inbound", "both"):
            q = "SELECT * FROM edges WHERE target_entity = ?"
            p = [entity_id]
            if relationship:
                q += " AND relationship = ?"
                p.append(relationship)
            edges.extend(_edge_to_dict(r) for r in conn.execute(q, p).fetchall())

        return edges
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Tool 5: aggregate_query — count/sum queries for investigative analysis
# ──────────────────────────────────────────────────────────────────────────

def aggregate_query(
    entity_type: Optional[str] = None,
    relationship: Optional[str] = None,
    min_edge_count: int = 1,
    limit: int = 20,
) -> list[dict]:
    """
    Find entities with the most connections of a given type.
    Useful for finding the biggest contractors, most prolific donors, etc.

    Args:
        entity_type: Filter entities by type (e.g. "company", "person").
        relationship: Filter edges by relationship (e.g. "CONTRACTED_WITH").
        min_edge_count: Minimum number of edges to include in results.
        limit: Max results.

    Returns:
        List of dicts with entity info and edge_count, sorted descending.
    """
    conn = _connect()
    try:
        # Count edges per entity (as source)
        q = """
            SELECT e.source_entity as entity_id, en.name, en.type,
                   COUNT(*) as edge_count
            FROM edges e
            JOIN entities en ON e.source_entity = en.entity_id
            WHERE 1=1
        """
        params: list = []

        if entity_type:
            q += " AND en.type = ?"
            params.append(entity_type)
        if relationship:
            q += " AND e.relationship = ?"
            params.append(relationship)

        q += " GROUP BY e.source_entity HAVING edge_count >= ? ORDER BY edge_count DESC LIMIT ?"
        params.extend([min_edge_count, limit])

        rows = conn.execute(q, params).fetchall()
        return [
            {
                "entity_id": r["entity_id"],
                "name": r["name"],
                "type": r["type"],
                "edge_count": r["edge_count"],
            }
            for r in rows
        ]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Tool 6: check_campaign_finance — look up donations by entity name
# ──────────────────────────────────────────────────────────────────────────

def check_campaign_finance(
    entity_name: str,
    direction: str = "both",
    limit: int = 20,
) -> dict:
    """
    Search the knowledge graph for campaign finance records linked to an entity.

    Finds donor→candidate relationships (DONATED_TO edges) where either
    the source or target entity name matches the search term.

    Args:
        entity_name: Name of donor or recipient to look up (fuzzy matched).
        direction: "donor" (entity is donor), "recipient" (entity received money),
                   or "both" (default — search either side).
        limit: Max results.

    Returns:
        Dict with total_found, top_donations (list), and summary text.
    """
    conn = _connect()
    try:
        # Find matching entity IDs (by name fuzzy match)
        name_rows = conn.execute(
            "SELECT entity_id, name FROM entities WHERE name LIKE ? LIMIT 200",
            [f"%{entity_name}%"]
        ).fetchall()

        # Score to get best matches
        scored = sorted(
            name_rows,
            key=lambda r: fuzz.token_sort_ratio(entity_name.upper(), r["name"].upper()),
            reverse=True,
        )[:20]  # take top 20 candidate IDs to query edges for

        if not scored:
            return {"total_found": 0, "top_donations": [], "summary": "No matching entities found."}

        entity_ids = [r["entity_id"] for r in scored]
        placeholders = ",".join("?" * len(entity_ids))

        donations = []

        if direction in ("donor", "both"):
            # Entity is the donor (source of DONATED_TO edge)
            rows = conn.execute(
                f"SELECT e.*, en_t.name as target_name FROM edges e "
                f"JOIN entities en_t ON e.target_entity = en_t.entity_id "
                f"WHERE e.source_entity IN ({placeholders}) AND e.relationship = 'DONATED_TO' "
                f"LIMIT ?",
                entity_ids + [limit]
            ).fetchall()
            for r in rows:
                props = json.loads(r["properties"] or "{}")
                donations.append({
                    "direction": "donor",
                    "donor_id": r["source_entity"],
                    "recipient": r["target_name"],
                    "amount": props.get("amount") or props.get("amount_str", "unknown"),
                    "date": props.get("date") or props.get("transaction_date", "unknown"),
                    "dataset": r["source_dataset"],
                })

        if direction in ("recipient", "both"):
            # Entity is the recipient (target of DONATED_TO edge)
            rows = conn.execute(
                f"SELECT e.*, en_s.name as source_name FROM edges e "
                f"JOIN entities en_s ON e.source_entity = en_s.entity_id "
                f"WHERE e.target_entity IN ({placeholders}) AND e.relationship = 'DONATED_TO' "
                f"LIMIT ?",
                entity_ids + [limit]
            ).fetchall()
            for r in rows:
                props = json.loads(r["properties"] or "{}")
                donations.append({
                    "direction": "recipient",
                    "donor": r["source_name"],
                    "recipient_id": r["target_entity"],
                    "amount": props.get("amount") or props.get("amount_str", "unknown"),
                    "date": props.get("date") or props.get("transaction_date", "unknown"),
                    "dataset": r["source_dataset"],
                })

        total = len(donations)
        summary = (
            f"Found {total} campaign finance records matching '{entity_name}'. "
            + (f"Top donation: {donations[0]['amount']}" if donations else "No donations found.")
        )
        return {"total_found": total, "top_donations": donations[:limit], "summary": summary}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Tool 7: file_investigation — save an investigation to the DB
# ──────────────────────────────────────────────────────────────────────────

def file_investigation(
    title: str,
    summary: str,
    entity_ids: list,
    findings: Optional[list] = None,
) -> dict:
    """
    Save an investigation and its findings to the investigations database.

    Use this to persist a completed investigation so it can be retrieved
    later with check_prior_investigations or published with publish_finding.

    Args:
        title: Short descriptive title (e.g. "Recology SF Contract Patterns").
        summary: Full narrative summary of the investigation.
        entity_ids: List of entity_ids that are central to this investigation.
        findings: Optional list of finding dicts with keys: description, severity,
                  confidence, evidence. (Defaults to empty list.)

    Returns:
        Dict with investigation_id and status ("filed").
    """
    investigation_id = f"inv_{uuid.uuid4().hex[:12]}"
    conn = _connect_investigations()
    try:
        conn.execute(
            """INSERT INTO investigations (id, title, summary, entity_ids, findings, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'draft', ?)""",
            [
                investigation_id,
                title,
                summary,
                json.dumps(entity_ids or []),
                json.dumps(findings or []),
                time.time(),
            ]
        )
        conn.commit()
        return {
            "investigation_id": investigation_id,
            "status": "filed",
            "title": title,
            "message": f"Investigation '{title}' saved with ID {investigation_id}.",
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Tool 8: check_prior_investigations — query previously filed investigations
# ──────────────────────────────────────────────────────────────────────────

def check_prior_investigations(
    entity_id: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search for previously filed investigations in the database.

    Useful to avoid duplicating work and to find related prior investigations
    that may contain useful context about the current target.

    Args:
        entity_id: Find investigations that include this specific entity_id.
        keyword: Find investigations whose title or summary contains this text.
        limit: Max results (default 10).

    Returns:
        List of investigation dicts with id, title, summary, status, created_at.
    """
    conn = _connect_investigations()
    try:
        rows = conn.execute(
            "SELECT id, title, summary, entity_ids, status, created_at, published_at "
            "FROM investigations ORDER BY created_at DESC LIMIT 200"
        ).fetchall()

        results = []
        for row in rows:
            # Filter by entity_id if provided
            if entity_id:
                ids = json.loads(row["entity_ids"] or "[]")
                if entity_id not in ids:
                    continue
            # Filter by keyword if provided
            if keyword:
                kw = keyword.lower()
                if kw not in row["title"].lower() and kw not in row["summary"].lower():
                    continue
            results.append({
                "investigation_id": row["id"],
                "title": row["title"],
                "summary": row["summary"][:300] + "..." if len(row["summary"]) > 300 else row["summary"],
                "status": row["status"],
                "created_at": row["created_at"],
                "published_at": row["published_at"],
            })
            if len(results) >= limit:
                break

        return results
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Tool 9: publish_finding — mark a filed investigation as published
# ──────────────────────────────────────────────────────────────────────────

def publish_finding(
    investigation_id: str,
    public_title: Optional[str] = None,
    public_summary: Optional[str] = None,
) -> dict:
    """
    Publish a filed investigation to the public record.

    Changes the investigation status from 'draft' to 'published' and
    optionally updates the title/summary for public presentation.
    A journalist with editor role must authorize the actual HTTP publish
    via the /api/publish endpoint; this tool marks intent in the DB.

    Args:
        investigation_id: The investigation_id returned by file_investigation.
        public_title: Optional refined title for public display.
        public_summary: Optional refined summary for public display.

    Returns:
        Dict with status ('published' or 'not_found') and the investigation details.
    """
    conn = _connect_investigations()
    try:
        row = conn.execute(
            "SELECT * FROM investigations WHERE id = ?", [investigation_id]
        ).fetchone()

        if not row:
            return {"status": "not_found", "message": f"Investigation {investigation_id} not found."}

        update_fields: list = []
        update_vals: list = []

        update_fields.append("status = 'published'")
        update_fields.append("published_at = ?")
        update_vals.append(time.time())

        if public_title:
            update_fields.append("title = ?")
            update_vals.append(public_title)
        if public_summary:
            update_fields.append("summary = ?")
            update_vals.append(public_summary)

        update_vals.append(investigation_id)
        conn.execute(
            f"UPDATE investigations SET {', '.join(update_fields)} WHERE id = ?",
            update_vals
        )
        conn.commit()

        return {
            "status": "published",
            "investigation_id": investigation_id,
            "title": public_title or row["title"],
            "message": f"Investigation '{public_title or row['title']}' is now published.",
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# REST helpers: list, get, update outcome, pattern confidence
# ──────────────────────────────────────────────────────────────────────────

def list_investigations(limit: int = 50) -> list[dict]:
    """Return all investigations ordered by most recent first."""
    conn = _connect_investigations()
    try:
        rows = conn.execute(
            "SELECT id, title, summary, entity_ids, findings, status, outcome, created_at, published_at "
            "FROM investigations ORDER BY created_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "summary": r["summary"][:200] + ("..." if len(r["summary"]) > 200 else ""),
                "entity_ids": json.loads(r["entity_ids"] or "[]"),
                "findings_count": len(json.loads(r["findings"] or "[]")),
                "status": r["status"],
                "outcome": r["outcome"] or "ongoing",
                "created_at": r["created_at"],
                "published_at": r["published_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_investigation(investigation_id: str) -> Optional[dict]:
    """Get full investigation record by ID."""
    conn = _connect_investigations()
    try:
        row = conn.execute(
            "SELECT * FROM investigations WHERE id = ?", [investigation_id]
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "summary": row["summary"],
            "entity_ids": json.loads(row["entity_ids"] or "[]"),
            "findings": json.loads(row["findings"] or "[]"),
            "status": row["status"],
            "outcome": row["outcome"] or "ongoing",
            "created_at": row["created_at"],
            "published_at": row["published_at"],
        }
    finally:
        conn.close()


def update_investigation_outcome(investigation_id: str, outcome: str) -> dict:
    """Update the outcome status of an investigation.

    Valid outcomes: ongoing, confirmed, dead_end, published
    """
    valid = {"ongoing", "confirmed", "dead_end", "published"}
    if outcome not in valid:
        return {"error": f"Invalid outcome. Must be one of: {', '.join(sorted(valid))}"}

    conn = _connect_investigations()
    try:
        row = conn.execute(
            "SELECT id FROM investigations WHERE id = ?", [investigation_id]
        ).fetchone()
        if not row:
            return {"error": "Investigation not found"}

        conn.execute(
            "UPDATE investigations SET outcome = ? WHERE id = ?",
            [outcome, investigation_id],
        )
        conn.commit()
        return {"id": investigation_id, "outcome": outcome, "status": "updated"}
    finally:
        conn.close()


def get_pattern_confidence() -> dict:
    """Calculate pattern confidence from historical investigation outcomes.

    Returns how often each detected pattern type led to a confirmed
    investigation, based on all prior investigation outcomes.
    """
    conn = _connect_investigations()
    try:
        rows = conn.execute(
            "SELECT findings, outcome FROM investigations WHERE outcome != 'ongoing'"
        ).fetchall()

        pattern_counts: dict[str, int] = {}
        pattern_confirmed: dict[str, int] = {}

        for row in rows:
            findings = json.loads(row["findings"] or "[]")
            outcome = row["outcome"]
            for f in findings:
                ptype = f.get("type") or f.get("pattern_type", "unknown")
                pattern_counts[ptype] = pattern_counts.get(ptype, 0) + 1
                if outcome == "confirmed":
                    pattern_confirmed[ptype] = pattern_confirmed.get(ptype, 0) + 1

        confidence = {}
        for ptype, total in pattern_counts.items():
            confirmed = pattern_confirmed.get(ptype, 0)
            confidence[ptype] = {
                "total_occurrences": total,
                "confirmed": confirmed,
                "confidence_rate": round(confirmed / total, 2) if total > 0 else 0,
            }

        total_investigations = len(rows)
        total_confirmed = sum(1 for r in rows if r["outcome"] == "confirmed")

        return {
            "patterns": confidence,
            "total_investigations_with_outcomes": total_investigations,
            "total_confirmed": total_confirmed,
            "overall_confirmation_rate": round(total_confirmed / total_investigations, 2) if total_investigations > 0 else 0,
        }
    finally:
        conn.close()
