# SF SODA API — Declarative Manifest for PyAirbyte

## Direct HTTP Approach (Recommended for Hackathon)

The SODA API is a simple REST JSON API. For hackathon speed, use `requests` directly:

```python
import requests

SODA_BASE = "https://data.sfgov.org/resource"
SODA_TOKEN = "YOUR_APP_TOKEN"  # optional but avoids rate limits

# SF Government Contracts
contracts = requests.get(
    f"{SODA_BASE}/cqi5-hm2d.json",
    params={"$limit": 50000, "$$app_token": SODA_TOKEN}
).json()

# Campaign Finance
campaign = requests.get(
    f"{SODA_BASE}/pitq-e56w.json",
    params={"$limit": 50000, "$$app_token": SODA_TOKEN}
).json()

# Registered Businesses
businesses = requests.get(
    f"{SODA_BASE}/g8m3-pdis.json",
    params={"$limit": 50000, "$$app_token": SODA_TOKEN}
).json()
```

## PyAirbyte Declarative Manifest Approach

If you need incremental syncs, schema enforcement, or caching:

```python
import airbyte as ab

manifest = {
    "version": "0.1.0",
    "type": "DeclarativeSource",
    "check": {
        "type": "CheckStream",
        "stream_names": ["contracts"]
    },
    "definitions": {
        "base_requester": {
            "type": "HttpRequester",
            "url_base": "https://data.sfgov.org/resource/",
            "http_method": "GET",
            "request_parameters": {
                "$limit": "50000",
                "$$app_token": "{{ config.get('app_token', '') }}"
            }
        },
        "contracts_stream": {
            "type": "DeclarativeStream",
            "name": "contracts",
            "retriever": {
                "type": "SimpleRetriever",
                "requester": {
                    "$ref": "#/definitions/base_requester",
                    "path": "cqi5-hm2d.json"
                },
                "record_selector": {
                    "type": "RecordSelector",
                    "extractor": {
                        "type": "DpathExtractor",
                        "field_path": []
                    }
                }
            },
            "schema_loader": {
                "type": "InlineSchemaLoader",
                "schema": {
                    "$schema": "http://json-schema.org/schema#",
                    "type": "object",
                    "properties": {
                        "contract_number": {"type": ["string", "null"]},
                        "contract_type": {"type": ["string", "null"]},
                        "vendor_name": {"type": ["string", "null"]},
                        "department": {"type": ["string", "null"]},
                        "contract_amount": {"type": ["string", "null"]},
                        "start_date": {"type": ["string", "null"]},
                        "end_date": {"type": ["string", "null"]}
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
                    "path": "pitq-e56w.json"
                },
                "record_selector": {
                    "type": "RecordSelector",
                    "extractor": {
                        "type": "DpathExtractor",
                        "field_path": []
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
                    "path": "g8m3-pdis.json"
                },
                "record_selector": {
                    "type": "RecordSelector",
                    "extractor": {
                        "type": "DpathExtractor",
                        "field_path": []
                    }
                }
            }
        }
    },
    "streams": [
        {"$ref": "#/definitions/contracts_stream"},
        {"$ref": "#/definitions/campaign_finance_stream"},
        {"$ref": "#/definitions/businesses_stream"}
    ]
}

source = ab.get_source(
    "source-declarative-manifest",
    config={"app_token": "YOUR_SODA_TOKEN"},
    source_manifest=manifest,
)

source.select_all_streams()
result = source.read()

contracts_df = result["contracts"].to_pandas()
campaign_df = result["campaign_finance"].to_pandas()
businesses_df = result["businesses"].to_pandas()
```

## SODA API Dataset IDs

| Dataset | ID | Description |
|---------|-----|-------------|
| Contracts | `cqi5-hm2d` | City vendor contracts, amounts, departments |
| Campaign Finance | `pitq-e56w` | Political contributions and expenditures |
| Businesses | `g8m3-pdis` | Registered business locations and owners |

## Key SODA Query Parameters

| Parameter | Example | Purpose |
|-----------|---------|---------|
| `$limit` | `50000` | Max records per request |
| `$offset` | `50000` | Pagination offset |
| `$where` | `contract_amount > 100000` | SoQL filter |
| `$select` | `vendor_name, contract_amount` | Column selection |
| `$order` | `contract_amount DESC` | Sort order |
| `$$app_token` | `abc123` | API rate limit token |
