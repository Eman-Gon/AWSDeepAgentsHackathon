"""
Load extracted entities and edges into Aerospike knowledge graph.

Falls back to SQLite if Aerospike is unavailable (for local dev).
"""

import json
import sqlite3
import os
from typing import Optional

from pipeline.config import (
    AEROSPIKE_HOST,
    AEROSPIKE_NAMESPACE,
    AEROSPIKE_PORT,
    DATA_DIR,
)
from pipeline.entity_extraction import EntityStore


# ---------------------------------------------------------------------------
# Aerospike loader
# ---------------------------------------------------------------------------

def connect_aerospike():
    """Connect to Aerospike and return client."""
    import aerospike
    config = {"hosts": [(AEROSPIKE_HOST, AEROSPIKE_PORT)]}
    client = aerospike.client(config).connect()
    return client


def create_secondary_indexes(client) -> None:
    """Create secondary indexes on edges for graph traversal."""
    ns = AEROSPIKE_NAMESPACE
    try:
        client.index_string_create(ns, "edges", "source_entity", "idx_edge_source")
    except Exception:
        pass  # index already exists
    try:
        client.index_string_create(ns, "edges", "target_entity", "idx_edge_target")
    except Exception:
        pass
    try:
        client.index_string_create(ns, "entities", "type", "idx_entity_type")
    except Exception:
        pass
    print("  Secondary indexes ensured.")


def load_to_aerospike(store: EntityStore) -> dict:
    """Bulk-load entities and edges into Aerospike. Returns stats."""
    client = connect_aerospike()
    ns = AEROSPIKE_NAMESPACE

    create_secondary_indexes(client)

    entity_count = 0
    for eid, entity in store.entities.items():
        key = (ns, "entities", eid)
        # Aerospike bins from entity dict (map/list types supported natively)
        bins = {
            "entity_id": entity["entity_id"],
            "type": entity["type"],
            "name": entity["name"],
            "aliases": entity["aliases"],
            "properties": json.dumps(entity["properties"]),  # store as JSON string for safety
            "sources": entity["sources"],
            "first_seen": entity["first_seen"],
            "last_updated": entity["last_updated"],
            "flagged": entity["flagged_in_investigations"],
        }
        client.put(key, bins)
        entity_count += 1

    edge_count = 0
    for edge in store.edges:
        key = (ns, "edges", edge["edge_id"])
        bins = {
            "edge_id": edge["edge_id"],
            "source_entity": edge["source_entity"],
            "target_entity": edge["target_entity"],
            "relationship": edge["relationship"],
            "properties": json.dumps(edge["properties"]),
            "source_dataset": edge["source_dataset"],
            "confidence": edge["confidence"],
        }
        client.put(key, bins)
        edge_count += 1

    client.close()
    stats = {"entities_loaded": entity_count, "edges_loaded": edge_count}
    print(f"  Aerospike load complete: {stats}")
    return stats


# ---------------------------------------------------------------------------
# SQLite fallback (for local dev without Aerospike)
# ---------------------------------------------------------------------------

SQLITE_PATH = os.path.join(DATA_DIR, "commons_graph.db")


def init_sqlite() -> sqlite3.Connection:
    """Create SQLite tables mirroring the Aerospike schema."""
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            entity_id TEXT PRIMARY KEY,
            type TEXT,
            name TEXT,
            aliases TEXT,
            properties TEXT,
            sources TEXT,
            first_seen TEXT,
            last_updated TEXT,
            flagged TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            edge_id TEXT PRIMARY KEY,
            source_entity TEXT,
            target_entity TEXT,
            relationship TEXT,
            properties TEXT,
            source_dataset TEXT,
            confidence REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_source ON edges(source_entity)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_target ON edges(target_entity)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(type)")
    conn.commit()
    return conn


def load_to_sqlite(store: EntityStore) -> dict:
    """Bulk-load entities and edges into SQLite fallback."""
    conn = init_sqlite()

    for eid, entity in store.entities.items():
        conn.execute(
            "INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?,?,?)",
            (
                entity["entity_id"],
                entity["type"],
                entity["name"],
                json.dumps(entity["aliases"]),
                json.dumps(entity["properties"]),
                json.dumps(entity["sources"]),
                entity["first_seen"],
                entity["last_updated"],
                json.dumps(entity["flagged_in_investigations"]),
            ),
        )

    for edge in store.edges:
        conn.execute(
            "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?,?)",
            (
                edge["edge_id"],
                edge["source_entity"],
                edge["target_entity"],
                edge["relationship"],
                json.dumps(edge["properties"]),
                edge["source_dataset"],
                edge["confidence"],
            ),
        )

    conn.commit()
    stats = {"entities_loaded": len(store.entities), "edges_loaded": len(store.edges)}
    print(f"  SQLite load complete ({SQLITE_PATH}): {stats}")
    conn.close()
    return stats


# ---------------------------------------------------------------------------
# Auto-select loader
# ---------------------------------------------------------------------------

def load_graph(store: EntityStore, force_sqlite: bool = False) -> dict:
    """Load into Aerospike if available, otherwise fall back to SQLite."""
    if force_sqlite:
        return load_to_sqlite(store)

    try:
        return load_to_aerospike(store)
    except Exception as e:
        print(f"  Aerospike unavailable ({e}), falling back to SQLite...")
        return load_to_sqlite(store)
