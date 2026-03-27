# Aerospike Graph Schema for Commons

## Namespace & Sets

```
Namespace: commons (configured in pipeline/config.py; falls back to SQLite at data/commons_graph.db)

Sets:
├── entities   — Graph nodes (persons, companies, departments, contracts, campaigns, addresses)
├── edges      — Directed relationships between entities
└── investigations — Saved investigation sessions (Person 2 track)
```

## Entity Record Schema

```python
# Key: ("commons", "entities", entity_id)
# entity_id format: "{type}:{slug}_{md5hash8}" e.g. "person:jane_doe_a1b2c3d4"
{
    "entity_id": str,      # Same as the key — e.g. "person:jane_doe_a1b2c3d4"
    "type": str,           # "person" | "company" | "department" | "contract" | "campaign" | "address"
    "name": str,           # Display name: "Jane Doe"
    "aliases": list,       # All name variants seen: ["Jane Doe", "JANE DOE"]
    "properties": dict,    # Flexible metadata (contract_title, agreed_amt, address, etc.)
    "sources": list,       # Which datasets contributed: ["contracts", "campaign_finance"]
    "first_seen": str,     # ISO timestamp of first upsert
    "last_updated": str,   # ISO timestamp of most recent upsert
    "flagged_in_investigations": list,  # Investigation IDs that flagged this entity
}
```

## Edge Record Schema

```python
# Key: ("commons", "edges", edge_id)
# edge_id format: "edge:{source_id}:{relationship_lower}:{target_id}"
{
    "edge_id": str,            # Same as the key
    "source_entity": str,      # entity_id of source node
    "target_entity": str,      # entity_id of target node
    "relationship": str,       # Relationship type (see below)
    "properties": dict,        # Flexible metadata (amount, contract_no, etc.)
    "source_dataset": str,     # "contracts" | "campaign_finance" | "businesses"
    "confidence": float,       # 0.0 to 1.0 (1.0 = exact name match)
}
```

## Relationship Types

| Relationship | Source → Target | Count (~50k seed) | Example |
|-------------|----------------|-------------------|---------|
| `CONTRACTED_WITH` | company → contract | ~47,769 | AcmeCorp contracted with Contract#12345 |
| `AWARDED_BY` | contract → department | ~47,714 | Contract#12345 awarded by DPW |
| `DONATED_TO` | person → campaign | ~49,796 | Jane Doe donated to Committee XYZ |
| `OFFICER_OF` | person → company | ~50,000 | Jane Doe officer of AcmeCorp |
| `REGISTERED_AT` | company → address | ~50,000 | AcmeCorp registered at 123 Main St |

## Investigation Record Schema (Person 2 track)

```python
# Key: ("commons", "investigations", investigation_id)
{
    "title": str,          # "DPW Contract Concentration Analysis"
    "created_at": str,     # ISO timestamp
    "updated_at": str,     # ISO timestamp
    "status": str,         # "active" | "completed" | "archived"
    "seed_entities": list, # Starting entity_ids
    "findings": list,      # List of finding dicts
    "narrative": str,      # Generated investigation narrative
    "user_id": str         # Auth0 user ID (if authenticated)
}
```

## Required Secondary Indexes

Create these at application startup:

```python
import aerospike

def create_indexes(client):
    """Create all secondary indexes needed for graph queries."""
    ns = "commons"
    indexes = [
        # Entity indexes
        ("entities", "type", "idx_entity_type", "string"),
        ("entities", "name", "idx_entity_name", "string"),
        # Edge indexes (critical for graph traversal)
        ("edges", "source_entity", "idx_edge_source", "string"),
        ("edges", "target_entity", "idx_edge_target", "string"),
        ("edges", "relationship", "idx_edge_relation", "string"),
    ]

    for set_name, bin_name, idx_name, idx_type in indexes:
        try:
            client.index_string_create(ns, set_name, bin_name, idx_name)
            print(f"Created index: {idx_name}")
        except aerospike.exception.IndexFoundError:
            pass  # Already exists
```

## Sample Data Seeding

Use the pipeline instead of manual seeding:

```bash
# Download 50k records per dataset from SODA, save to data/
python -m pipeline.run_pipeline --seed --limit 50000

# Process pre-seeded data and load into SQLite (Aerospike fallback)
python -m pipeline.run_pipeline --local --sqlite

# Or process via PyAirbyte and load into SQLite
python -m pipeline.run_pipeline --airbyte --sqlite
```

Output stats from a 50k seed run:
- 186,504 entities (58k persons, 53k companies, 43k addresses, 32k contracts, 294 campaigns, 56 departments)
- 245,279 edges across 5 relationship types
