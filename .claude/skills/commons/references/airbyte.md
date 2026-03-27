# Airbyte — Data Ingestion Pipeline

## Integration Strategy

We use **PyAirbyte with a declarative manifest** to define a custom SODA API source that ingests all three SF datasets. This avoids building a full CDK connector while still giving us a reusable Airbyte source definition.

### Implementation (pipeline/soda_source.py)

```python
import airbyte as ab

# Declarative manifest defines REST API source inline
SODA_MANIFEST = {
    "version": "6.44.0",
    "type": "DeclarativeSource",
    "definitions": {
        "streams": {
            "contracts": {
                "type": "DeclarativeStream",
                "name": "contracts",
                "retriever": {
                    "type": "SimpleRetriever",
                    "requester": {
                        "type": "HttpRequester",
                        "url_base": "https://data.sfgov.org",
                        "path": "/resource/cqi5-hm2d.json",
                        "http_method": "GET",
                        "request_parameters": {"$limit": "10000"},
                    },
                    "record_selector": {"type": "RecordSelector", "extractor": {"type": "DpathExtractor", "field_path": []}},
                },
                "schema_loader": {
                    "type": "InlineSchemaLoader",
                    "schema": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {"contract_no": {"type": "string"}, "prime_contractor": {"type": "string"}}
                    }
                }
            },
            # ... campaign_finance and businesses streams follow same pattern
        }
    },
    "spec": {
        "type": "Spec",
        "connection_specification": {
            "type": "object",
            "properties": {"app_token": {"type": "string", "title": "SODA App Token", "default": ""}}
        }
    }
}

# Ingest via PyAirbyte
source = ab.get_source("source-declarative-manifest", config={"__injected_declarative_manifest": SODA_MANIFEST})
source.select_all_streams()
result = source.read()  # Caches to DuckDB locally
contracts_df = result["contracts"].to_pandas()
```

### Key Requirements for Declarative Manifests

1. **`spec` section is mandatory** — without it, PyAirbyte throws "Unable to find spec.yaml"
2. **`InlineSchemaLoader` with `properties`** — without it, you get "KeyError: 'properties'"
3. **`additionalProperties: true`** — lets SODA's variable schemas pass through
4. **Source name must be `source-declarative-manifest`** — this is the PyAirbyte engine for custom manifests

### Fallback: Direct SODA API

If Airbyte is blocked, use direct HTTP with pagination (also in soda_source.py):

```python
def fetch_soda_dataset(resource_id, limit=50000):
    """Fetch from SODA API with 10k pagination chunks."""
    all_records = []
    offset = 0
    page_size = 10000
    while offset < limit:
        chunk = min(page_size, limit - offset)
        url = f"https://data.sfgov.org/resource/{resource_id}.json?$limit={chunk}&$offset={offset}"
        resp = requests.get(url, timeout=120)
        batch = resp.json()
        if not batch:
            break
        all_records.extend(batch)
        offset += len(batch)
    return all_records
```

## Entity Extraction Transform

Between Airbyte/SODA output and graph loading (pipeline/entity_extraction.py):

1. Extract unique persons, companies, addresses, contracts, campaigns, departments
2. Normalize names via `thefuzz` fuzzy matching ("ACME LLC" = "Acme, LLC")
3. Deduplicate entities across all sources using stable MD5-based IDs
4. Output: 186K+ entity nodes + 245K+ relationship edges

## Why This Matters for Judges

- Declarative manifest approach is reusable for any Socrata/SODA API dataset
- SODA is used by NYC, Chicago, LA, Seattle — pattern could ship to Airbyte catalog
- Pedro (Airbyte sponsor) wants "projects that integrate data from multiple sources"
- We ingest 3 distinct datasets and cross-reference entities across them