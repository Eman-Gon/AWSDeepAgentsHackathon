# Airbyte — Data Ingestion Pipeline

## Integration Strategy

Two options, ordered by speed:

### Option A: Airbyte Agent Connectors (faster, ~45 min)

```python
# pip install airbyte-agent-connectors
# Configure three SODA sources as agent tools
# Agent calls them during investigation flow
```

- Install the airbyte-agent-connectors Python package
- Expose SODA API as agent-callable tools
- Agent triggers data pulls as part of investigation

### Option B: Full Custom SODA Connector (deeper, ~2 hrs)

Build using Airbyte CDK (Connector Development Kit):

1. **Custom SODA API Source Connector** that speaks the Socrata/SODA protocol:
   - Accepts a SODA endpoint URL + optional app token
   - Supports SoQL filtering ($where, $limit, $offset)
   - Handles pagination (SODA pages at 50,000 records)
   - Outputs structured entity records (not raw JSON blobs)
   - Implements incremental sync using date fields

2. **Three source instances using the same connector:**
   - SF Supplier Contracts (cqi5-hm2d)
   - Campaign Finance Transactions (pitq-e56w)
   - Registered Businesses (g8m3-pdis)

## Entity Extraction Transform

Between Airbyte output and Aerospike input:

1. Extract unique persons, companies, addresses from raw records
2. Normalize names (fuzzy matching: "ACME LLC" = "Acme, LLC" = "ACME L.L.C.")
3. Deduplicate entities across sources
4. Output: entity nodes + relationship edges ready for graph ingestion

## Why This Matters for Judges

- Most teams use a pre-built connector — we build a reusable SODA connector
- SODA is used by NYC, Chicago, LA, Seattle — connector could ship to Airbyte's catalog
- Pedro (Airbyte sponsor) specifically wants "projects that integrate data from multiple sources"

## Fallback

If Airbyte setup is blocked, use direct SODA API calls. The pipeline layer is important but not the only path to data.
