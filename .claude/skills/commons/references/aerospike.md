# Aerospike — Knowledge Graph Schema & Queries

## Data Model

Namespace: `commons`

### Set: entities

```
Key: entity_id (e.g., "person:john_doe_sf" or "company:acme_llc")
Bins:
  - type: string ("person" | "company" | "department" | "contract" | "campaign" | "address")
  - name: string (canonical name)
  - aliases: list (all name variants seen across sources)
  - properties: map (source-specific fields — amount, date, department, etc.)
  - sources: list (which data sources contributed to this entity)
  - first_seen: timestamp (ISO string)
  - last_updated: timestamp (ISO string)
  - flagged_in_investigations: list (investigation IDs)
```

### Set: edges

```
Key: edge_id (e.g., "edge:person_123:donated_to:campaign_456")
Bins:
  - source_entity: string (entity_id)
  - target_entity: string (entity_id)
  - relationship: string ("CONTRACTED_WITH" | "AWARDED_BY" | "DONATED_TO" | "OFFICER_OF" | "REGISTERED_AT")
  - properties: map (amount, date, context)
  - source_dataset: string (which Airbyte source)
  - confidence: float (1.0 for exact match, lower for fuzzy)
```

### Set: investigations

```
Key: investigation_id
Bins:
  - journalist_id: string (Auth0 user ID)
  - query: string (original investigation prompt)
  - entities_found: list (entity_ids)
  - patterns_detected: list (pattern descriptions)
  - outcome: string ("confirmed" | "dead_end" | "ongoing" | null)
  - created_at: timestamp
```

## Secondary Indexes

Create secondary indexes on `edges.source_entity` and `edges.target_entity` for graph traversal.

## Graph Traversal (BFS, N-hop)

```python
def traverse_graph(client, start_entity_id, max_hops=3):
    """BFS traversal from a starting entity through the knowledge graph."""
    visited = set()
    queue = [(start_entity_id, 0)]
    results = []

    while queue:
        entity_id, depth = queue.pop(0)
        if entity_id in visited or depth > max_hops:
            continue
        visited.add(entity_id)

        # Get entity details
        entity = client.get(("commons", "entities", entity_id))
        results.append({"entity": entity, "depth": depth})

        # Get all edges FROM this entity
        query = client.query("commons", "edges")
        query.where(Equals("source_entity", entity_id))
        outbound = query.results()

        # Get all edges TO this entity
        query2 = client.query("commons", "edges")
        query2.where(Equals("target_entity", entity_id))
        inbound = query2.results()

        for edge in outbound + inbound:
            next_id = edge["target_entity"] if edge["source_entity"] == entity_id else edge["source_entity"]
            queue.append((next_id, depth + 1))

    return results
```

## Pattern Detection

```python
def detect_corruption_patterns(client, entity_id):
    """Check for known corruption red flags around an entity."""
    patterns = []

    entity = client.get(("commons", "entities", entity_id))

    # Pattern 1: Recently-formed LLC winning contracts
    if entity["type"] == "company":
        formed_date = entity["properties"].get("business_start_date")
        contracts = get_edges(client, entity_id, "CONTRACTED_WITH")
        for contract in contracts:
            contract_date = contract["properties"].get("award_date")
            if formed_date and contract_date:
                days_between = (contract_date - formed_date).days
                if days_between < 90:
                    patterns.append({
                        "type": "RECENTLY_FORMED_LLC_CONTRACT",
                        "severity": "HIGH",
                        "detail": f"Company formed {days_between} days before receiving contract",
                        "confidence": 0.85
                    })

    # Pattern 2: Contractor donating to official who awarded contract
    officers = get_edges(client, entity_id, "OFFICER_OF")
    for officer in officers:
        person_id = officer["source_entity"]
        donations = get_edges(client, person_id, "DONATED_TO")
        contracts = get_edges(client, entity_id, "AWARDED_BY")
        for donation in donations:
            for contract in contracts:
                if entities_share_department(donation["target_entity"], contract["properties"].get("department")):
                    patterns.append({
                        "type": "CONTRACTOR_DONATED_TO_AWARDING_OFFICIAL",
                        "severity": "CRITICAL",
                        "detail": "Officer donated to campaign connected to awarding department",
                        "confidence": 0.90
                    })

    # Pattern 3: Shared registered agent across multiple contract-winning LLCs
    address = get_edges(client, entity_id, "REGISTERED_AT")
    if address:
        co_located = get_edges(client, address[0]["target_entity"], "REGISTERED_AT", reverse=True)
        if len(co_located) > 2:
            patterns.append({
                "type": "SHARED_ADDRESS_MULTIPLE_CONTRACTORS",
                "severity": "MEDIUM",
                "detail": f"{len(co_located)} entities share registered address",
                "confidence": 0.70
            })

    return patterns
```

## Key Design Points

- Use Aerospike secondary indexes for sub-ms graph lookups (not just key-value)
- Entity deduplication via fuzzy name matching and alias lists
- Confidence scores on edges reflect match quality (1.0 exact, lower for fuzzy)
- Investigation outcomes feed back into pattern learning
