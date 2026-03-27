# Aerospike Graph Schema for Commons

## Namespace & Sets

```
Namespace: test (default in Community Edition Docker)

Sets:
├── entities   — Graph nodes (people, companies, departments)
├── edges      — Directed relationships between entities
└── investigations — Saved investigation sessions
```

## Entity Record Schema

```python
# Key: ("test", "entities", entity_id)
# entity_id format: "{type}_{normalized_name}" e.g. "person_jane_doe"
{
    "name": str,           # Display name: "Jane Doe"
    "type": str,           # "person" | "company" | "department"
    "risk_score": float,   # 0.0 to 1.0, updated by pattern detection
    "metadata": dict,      # Flexible metadata bag
    # Type-specific fields:
    # person: role, title, employer
    # company: business_type, registration_id, address
    # department: budget, head
}
```

## Edge Record Schema

```python
# Key: ("test", "edges", edge_id)
# edge_id format: "{source}__{relation}__{target}"
{
    "source": str,         # entity_id of source node
    "target": str,         # entity_id of target node
    "relation": str,       # relationship type (see below)
    "weight": int,         # relationship strength (contract count, donation amount, etc.)
    "evidence": list,      # list of evidence dicts: [{"source": "contracts", "record_id": "..."}]
    "first_seen": str,     # ISO date when first detected
    "last_seen": str       # ISO date when last confirmed
}
```

## Relation Types

| Relation | Source → Target | Example |
|----------|----------------|---------|
| `contracts_with` | department → company | DPW contracts with AcmeCorp |
| `donates_to` | person/company → person | AcmeCorp donates to Mayor Smith |
| `owns` | person → company | Jane Doe owns AcmeCorp |
| `works_at` | person → department | Bob works at DPW |
| `employed_by` | person → company | Jane employed by AcmeCorp |
| `related_to` | person → person | Family/business relationship |
| `subcontracts_to` | company → company | AcmeCorp subs to SmallCo |

## Investigation Record Schema

```python
# Key: ("test", "investigations", investigation_id)
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
    """Create all secondary indexes needed for graph operations."""
    ns = "test"
    indexes = [
        # Entity indexes
        ("entities", "type", "idx_entity_type", "string"),
        ("entities", "name", "idx_entity_name", "string"),
        # Edge indexes (critical for graph traversal)
        ("edges", "source", "idx_edge_source", "string"),
        ("edges", "target", "idx_edge_target", "string"),
        ("edges", "relation", "idx_edge_relation", "string"),
        ("edges", "weight", "idx_edge_weight", "integer"),
    ]

    for set_name, bin_name, idx_name, idx_type in indexes:
        try:
            if idx_type == "string":
                client.index_string_create(ns, set_name, bin_name, idx_name)
            else:
                client.index_integer_create(ns, set_name, bin_name, idx_name)
            print(f"Created index: {idx_name}")
        except aerospike.exception.IndexFoundError:
            pass  # Already exists
```

## Sample Data Seeding

```python
def seed_sample_data(client):
    """Seed the graph with sample SF government data for demo."""
    ns = "test"

    # Entities
    entities = [
        ("person_john_smith", {"name": "John Smith", "type": "person", "role": "Commissioner"}),
        ("person_jane_doe", {"name": "Jane Doe", "type": "person", "role": "Lobbyist"}),
        ("company_acme_consulting", {"name": "Acme Consulting", "type": "company", "business_type": "Consulting"}),
        ("company_baybridge_llc", {"name": "BayBridge LLC", "type": "company", "business_type": "Construction"}),
        ("dept_public_works", {"name": "Department of Public Works", "type": "department", "budget": 500000000}),
        ("dept_planning", {"name": "Planning Department", "type": "department", "budget": 200000000}),
    ]

    for entity_id, bins in entities:
        bins["risk_score"] = 0.0
        client.put((ns, "entities", entity_id), bins)

    # Edges
    edges = [
        ("dept_public_works", "company_acme_consulting", "contracts_with", 15),
        ("dept_public_works", "company_baybridge_llc", "contracts_with", 3),
        ("dept_planning", "company_acme_consulting", "contracts_with", 8),
        ("company_acme_consulting", "person_john_smith", "donates_to", 50000),
        ("person_jane_doe", "company_acme_consulting", "owns", 1),
        ("person_jane_doe", "person_john_smith", "related_to", 1),
    ]

    for source, target, relation, weight in edges:
        edge_id = f"{source}__{relation}__{target}"
        client.put((ns, "edges", edge_id), {
            "source": source,
            "target": target,
            "relation": relation,
            "weight": weight,
            "evidence": [{"source": "seed_data"}]
        })

    print(f"Seeded {len(entities)} entities and {len(edges)} edges")
```
