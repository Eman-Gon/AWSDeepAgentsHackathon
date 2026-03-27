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
"""

import json
import os
import sqlite3
from typing import Optional

from thefuzz import fuzz

# ── Path to the pre-seeded SQLite graph database ──────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "commons_graph.db")


def _connect() -> sqlite3.Connection:
    """Open a read-only SQLite connection to the graph DB."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row          # dict-like access to columns
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
        # Build query — use LIKE for a coarse first pass, then re-rank by fuzz score
        query = "SELECT * FROM entities WHERE name LIKE ?"
        params: list = [f"%{name}%"]

        if entity_type:
            query += " AND type = ?"
            params.append(entity_type)

        query += " LIMIT 500"  # fetch a broad pool for fuzzy ranking

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
