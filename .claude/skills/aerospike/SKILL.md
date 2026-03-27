---
name: aerospike
description: Aerospike Python client reference for high-performance key-value and graph operations. Use when building entity graphs, storing investigation data in Aerospike, creating secondary indexes, running graph traversals, or integrating Aerospike into the Commons hackathon project.
---

# Aerospike (Python Client)

## Overview

Aerospike is a high-performance NoSQL database. For Commons, it stores the entity graph (people, companies, departments) and edges (connections between them) for corruption pattern detection. Sub-millisecond reads make it ideal for real-time graph traversal during agent investigations.

## Docker Setup

```bash
# Start Aerospike Community Edition (free, supports up to 8 nodes)
docker run -d --name aerospike \
  -p 3000:3000 -p 3001:3001 -p 3002:3002 -p 3003:3003 \
  aerospike

# Verify it's running
docker ps | grep aerospike

# Interactive AQL shell (SQL-like queries)
docker run -ti aerospike/aerospike-tools:latest aql \
  -h $(docker inspect -f '{{.NetworkSettings.IPAddress}}' aerospike)
```

## Python Client Setup

```bash
pip install aerospike
```

```python
import aerospike
from aerospike import predicates

# Connect to local Aerospike instance
config = {'hosts': [('127.0.0.1', 3000)]}
client = aerospike.client(config).connect()
```

## CRUD Operations

```python
# Namespace and set define the "table"
ns = "test"

# --- PUT (insert/update) ---
key = (ns, "entities", "person_jane_doe")
bins = {
    "name": "Jane Doe",
    "type": "person",
    "role": "contractor",
    "department": "Public Works",
    "risk_score": 0.0
}
client.put(key, bins)

# --- GET ---
(key, metadata, record) = client.get((ns, "entities", "person_jane_doe"))
print(record["name"])  # "Jane Doe"

# --- EXISTS (check without fetching) ---
(key, metadata) = client.exists((ns, "entities", "person_jane_doe"))

# --- REMOVE ---
client.remove((ns, "entities", "person_jane_doe"))

# --- BATCH GET (multiple keys at once) ---
keys = [(ns, "entities", f"person_{i}") for i in range(10)]
records = client.get_many(keys)
```

## Secondary Indexes & Queries

```python
# CREATE INDEXES (do once at app startup, idempotent with try/except)
try:
    client.index_string_create(ns, "entities", "type", "idx_entity_type")
except aerospike.exception.IndexFoundError:
    pass  # index already exists

try:
    client.index_string_create(ns, "entities", "name", "idx_entity_name")
except aerospike.exception.IndexFoundError:
    pass

try:
    client.index_integer_create(ns, "edges", "weight", "idx_edge_weight")
except aerospike.exception.IndexFoundError:
    pass

# QUERY by secondary index
query = client.query(ns, "entities")
query.where(predicates.equals("type", "person"))

# Option 1: collect all results
results = []
def collect(record):
    (key, meta, bins) = record
    results.append(bins)

query.foreach(collect)

# Option 2: use results() for a list directly
results = query.results()  # returns list of (key, meta, bins) tuples

# RANGE QUERY on integer index
query = client.query(ns, "edges")
query.where(predicates.between("weight", 5, 100))
results = query.results()
```

## Graph Data Model for Commons

```python
# --- ENTITY NODE ---
def store_entity(client, entity_id, name, entity_type, metadata=None):
    """Store a person, company, or department as a graph node."""
    key = ("test", "entities", entity_id)
    bins = {
        "name": name,
        "type": entity_type,     # "person", "company", "department"
        "risk_score": 0.0,
        "metadata": metadata or {}
    }
    client.put(key, bins)

# --- EDGE (relationship) ---
def store_edge(client, source_id, target_id, relation, weight=1, evidence=None):
    """Store a directed edge between two entities."""
    edge_id = f"{source_id}__{relation}__{target_id}"
    key = ("test", "edges", edge_id)
    bins = {
        "source": source_id,
        "target": target_id,
        "relation": relation,    # "contracts_with", "donates_to", "owns", "works_at"
        "weight": weight,
        "evidence": evidence or []
    }
    client.put(key, bins)

# --- GRAPH TRAVERSAL (BFS) ---
def traverse_graph(client, start_id, max_depth=3):
    """BFS traversal from a starting entity, returns all connected nodes."""
    visited = set()
    queue = [(start_id, 0)]
    subgraph = {"nodes": [], "edges": []}

    while queue:
        current_id, depth = queue.pop(0)
        if current_id in visited or depth > max_depth:
            continue
        visited.add(current_id)

        # Get the node
        try:
            _, _, node = client.get(("test", "entities", current_id))
            subgraph["nodes"].append(node)
        except aerospike.exception.RecordNotFound:
            continue

        # Find edges from this node
        query = client.query("test", "edges")
        query.where(predicates.equals("source", current_id))
        edges = query.results()

        for _, _, edge in edges:
            subgraph["edges"].append(edge)
            if edge["target"] not in visited:
                queue.append((edge["target"], depth + 1))

    return subgraph

# --- CORRUPTION PATTERN DETECTION ---
def detect_patterns(client):
    """Find suspicious patterns in the entity graph."""
    patterns = []

    # Pattern 1: Entity with many high-value contracts
    query = client.query("test", "edges")
    query.where(predicates.equals("relation", "contracts_with"))
    all_contracts = query.results()

    # Group by target (vendor)
    vendor_contracts = {}
    for _, _, edge in all_contracts:
        vendor = edge["target"]
        vendor_contracts.setdefault(vendor, []).append(edge)

    for vendor, contracts in vendor_contracts.items():
        if len(contracts) >= 5:
            patterns.append({
                "type": "concentration",
                "entity": vendor,
                "detail": f"{len(contracts)} contracts from same vendor"
            })

    return patterns
```

## Key Python Client Methods

| Method | Purpose |
|--------|---------|
| `client.put(key, bins)` | Insert or update a record |
| `client.get(key)` | Retrieve a record → (key, meta, bins) |
| `client.exists(key)` | Check existence → (key, meta) |
| `client.remove(key)` | Delete a record |
| `client.get_many(keys)` | Batch read |
| `client.query(ns, set)` | Create a query object |
| `query.where(pred)` | Add a predicate filter |
| `query.results()` | Execute and return list |
| `query.foreach(callback)` | Execute with streaming callback |
| `client.index_string_create(ns, set, bin, name)` | Create string index |
| `client.index_integer_create(ns, set, bin, name)` | Create integer index |
| `client.scan(ns, set)` | Full set scan (no filter) |
| `client.close()` | Disconnect |

## Critical Rules

- Always wrap index creation in `try/except IndexFoundError` — indexes are persistent
- Keys are tuples: `(namespace, set, primary_key_string)`
- Bins (columns) are a flat dict — nested dicts serialize as maps
- Default namespace is `"test"` in Community Edition Docker
- Community Edition is free but limited to 8 nodes and 5 TiB
- Use `scan()` for full-set operations, `query()` with `where()` for indexed lookups
- Aerospike stores data in RAM + file by default in Docker (data-in-memory mode)
- For graph edges, create secondary indexes on `source`, `target`, and `relation` bins

## Resources

- `references/graph-schema.md` — Entity graph schema for Commons
- `references/docker-config.md` — Docker setup and configuration options
