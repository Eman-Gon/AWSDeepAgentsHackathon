# SF SODA API — Declarative Manifest for PyAirbyte

## Direct HTTP Approach (Recommended for Hackathon)

The SODA API is a simple REST JSON API. Use `requests` with pagination (10k chunks):

```python
import requests

SODA_BASE = "https://data.sfgov.org/resource"

def fetch_soda_dataset(resource_id, limit=50000):
    """Fetch from SODA with 10k pagination to avoid timeouts."""
    all_records, offset, page_size = [], 0, 10000
    while offset < limit:
        chunk = min(page_size, limit - offset)
        resp = requests.get(
            f"{SODA_BASE}/{resource_id}.json",
            params={"$limit": chunk, "$offset": offset},
            timeout=120
        )
        batch = resp.json()
        if not batch:
            break
        all_records.extend(batch)
        offset += len(batch)
    return all_records

# SF Government Contracts
contracts = fetch_soda_dataset("cqi5-hm2d", 50000)
# Fields: contract_no, contract_title, prime_contractor, project_team_supplier,
#          agreed_amt, department, contract_type, term_start_date, term_end_date

# Campaign Finance Transactions
campaign = fetch_soda_dataset("pitq-e56w", 50000)
# Fields: filer_nid, filer_name, transaction_last_name, transaction_first_name,
#          transaction_amount_1, calculated_amount, calculated_date, transaction_city

# Registered Businesses
businesses = fetch_soda_dataset("g8m3-pdis", 50000)
# Fields: dba_name, ownership_name, full_business_address, dba_start_date, city, state
```

## PyAirbyte Declarative Manifest Approach

For incremental syncs, schema enforcement, or DuckDB caching:

**Critical requirements:**
1. Manifest MUST have a `spec` section or PyAirbyte throws "Unable to find spec.yaml"
2. Every stream MUST have `InlineSchemaLoader` with `properties` or you get "KeyError: 'properties'"
3. Use `additionalProperties: true` so SODA's variable schemas pass through
4. Source name must be `source-declarative-manifest`
5. Use 10k `$limit` to avoid API timeouts (50k single-request fails)

```python
import airbyte as ab

manifest = {
    "version": "6.44.0",
    "type": "DeclarativeSource",
    "check": {
        "type": "CheckStream",
        "stream_names": ["contracts"]
    },
    "definitions": {
        "base_requester": {
            "type": "HttpRequester",
            "url_base": "https://data.sfgov.org",
            "http_method": "GET",
            "request_parameters": {
                "$limit": "10000"
            }
        },
        "contracts_stream": {
            "type": "DeclarativeStream",
            "name": "contracts",
            "retriever": {
                "type": "SimpleRetriever",
                "requester": {
                    "$ref": "#/definitions/base_requester",
                    "path": "/resource/cqi5-hm2d.json"
                },
                "record_selector": {
                    "type": "RecordSelector",
                    "extractor": {"type": "DpathExtractor", "field_path": []}
                }
            },
            "schema_loader": {
                "type": "InlineSchemaLoader",
                "schema": {
                    "type": "object",
                    "additionalProperties": true,
                    "properties": {
                        "contract_no": {"type": ["string", "null"]},
                        "prime_contractor": {"type": ["string", "null"]},
                        "agreed_amt": {"type": ["string", "null"]},
                        "department": {"type": ["string", "null"]}
                    }
                }
            }
        },
        "campaign_finance_stream": {
            "type": "DeclarativeStream",
            "name": "campaign_finance",
            "retriever": {
                "type": "SimpleRetriever",
                "requester": {
                    "$ref": "#/definitions/base_requester",
                    "path": "/resource/pitq-e56w.json"
                },
                "record_selector": {
                    "type": "RecordSelector",
                    "extractor": {"type": "DpathExtractor", "field_path": []}
                }
            },
            "schema_loader": {
                "type": "InlineSchemaLoader",
                "schema": {
                    "type": "object",
                    "additionalProperties": true,
                    "properties": {
                        "filer_nid": {"type": ["string", "null"]},
                        "filer_name": {"type": ["string", "null"]},
                        "transaction_last_name": {"type": ["string", "null"]},
                        "transaction_amount_1": {"type": ["string", "null"]}
                    }
                }
            }
        },
        "businesses_stream": {
            "type": "DeclarativeStream",
            "name": "businesses",
            "retriever": {
                "type": "SimpleRetriever",
                "requester": {
                    "$ref": "#/definitions/base_requester",
                    "path": "/resource/g8m3-pdis.json"
                },
                "record_selector": {
                    "type": "RecordSelector",
                    "extractor": {"type": "DpathExtractor", "field_path": []}
                }
            },
            "schema_loader": {
                "type": "InlineSchemaLoader",
                "schema": {
                    "type": "object",
                    "additionalProperties": true,
                    "properties": {
                        "dba_name": {"type": ["string", "null"]},
                        "ownership_name": {"type": ["string", "null"]},
                        "full_business_address": {"type": ["string", "null"]}
                    }
                }
            }
        }
    },
    "streams": [
        {"$ref": "#/definitions/contracts_stream"},
        {"$ref": "#/definitions/campaign_finance_stream"},
        {"$ref": "#/definitions/businesses_stream"}
    ],
    "spec": {
        "type": "Spec",
        "connection_specification": {
            "type": "object",
            "properties": {
                "app_token": {"type": "string", "title": "SODA App Token", "default": ""}
            }
        }
    }
}

source = ab.get_source(
    "source-declarative-manifest",
    config={"__injected_declarative_manifest": manifest},
)
source.select_all_streams()
result = source.read()  # Caches to DuckDB locally

contracts_df = result["contracts"].to_pandas()
campaign_df = result["campaign_finance"].to_pandas()
businesses_df = result["businesses"].to_pandas()
```

## SODA API Dataset IDs

| Dataset | ID | Key Fields |
|---------|-----|------------|
| Contracts | `cqi5-hm2d` | contract_no, prime_contractor, agreed_amt, department |
| Campaign Finance | `pitq-e56w` | filer_nid, filer_name, transaction_last_name, transaction_amount_1 |
| Businesses | `g8m3-pdis` | dba_name, ownership_name, full_business_address |

## Key SODA Query Parameters

| Parameter | Example | Purpose |
|-----------|---------|---------|
| `$limit` | `10000` | Max records per page (use 10k, not 50k) |
| `$offset` | `10000` | Pagination offset |
| `$where` | `agreed_amt > 100000` | SoQL filter |
| `$select` | `prime_contractor, agreed_amt` | Column selection |
| `$order` | `agreed_amt DESC` | Sort order |
| `$$app_token` | `abc123` | API rate limit token (optional) |
