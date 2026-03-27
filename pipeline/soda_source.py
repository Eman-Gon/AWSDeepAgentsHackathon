"""
SODA API source using PyAirbyte declarative manifest.

Provides two ingestion paths:
  1. PyAirbyte (declarative manifest) — caching, schema, incremental sync
  2. Direct HTTP fallback — simpler, no Airbyte dependency
"""

import json
import os
from typing import Optional

import requests

from pipeline.config import (
    DATA_DIR,
    DEFAULT_RECORD_LIMIT,
    SODA_APP_TOKEN,
    SODA_BASE_URL,
    SODA_DATASETS,
)

# ---------------------------------------------------------------------------
# PyAirbyte declarative manifest
# ---------------------------------------------------------------------------

SODA_MANIFEST = {
    "version": "0.1.0",
    "type": "DeclarativeSource",
    "spec": {
        "type": "Spec",
        "documentation_url": "https://dev.socrata.com/foundry/data.sfgov.org/",
        "connection_specification": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "app_token": {
                    "type": "string",
                    "title": "SODA App Token",
                    "description": "Optional app token for higher rate limits",
                    "default": "",
                }
            },
            "required": [],
        },
    },
    "check": {"type": "CheckStream", "stream_names": ["contracts"]},
    "definitions": {
        "base_requester": {
            "type": "HttpRequester",
            "url_base": f"{SODA_BASE_URL}/",
            "http_method": "GET",
            "request_parameters": {
                "$limit": str(DEFAULT_RECORD_LIMIT),
                "$$app_token": "{{ config.get('app_token', '') }}",
            },
        },
        "contracts_stream": {
            "type": "DeclarativeStream",
            "name": "contracts",
            "retriever": {
                "type": "SimpleRetriever",
                "requester": {
                    "$ref": "#/definitions/base_requester",
                    "path": f"{SODA_DATASETS['contracts']['resource_id']}.json",
                },
                "record_selector": {
                    "type": "RecordSelector",
                    "extractor": {"type": "DpathExtractor", "field_path": []},
                },
            },
            "schema_loader": {
                "type": "InlineSchemaLoader",
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "contract_no": {"type": ["string", "null"]},
                        "prime_contractor": {"type": ["string", "null"]},
                        "project_team_supplier": {"type": ["string", "null"]},
                        "agreed_amt": {"type": ["string", "null"]},
                        "term_start_date": {"type": ["string", "null"]},
                        "term_end_date": {"type": ["string", "null"]},
                        "department": {"type": ["string", "null"]},
                        "contract_title": {"type": ["string", "null"]},
                        "contract_type": {"type": ["string", "null"]},
                        "purchasing_authority": {"type": ["string", "null"]},
                        "scope_of_work": {"type": ["string", "null"]},
                    },
                },
            },
        },
        "campaign_finance_stream": {
            "type": "DeclarativeStream",
            "name": "campaign_finance",
            "retriever": {
                "type": "SimpleRetriever",
                "requester": {
                    "$ref": "#/definitions/base_requester",
                    "path": f"{SODA_DATASETS['campaign_finance']['resource_id']}.json",
                },
                "record_selector": {
                    "type": "RecordSelector",
                    "extractor": {"type": "DpathExtractor", "field_path": []},
                },
            },
            "schema_loader": {
                "type": "InlineSchemaLoader",
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "filer_nid": {"type": ["string", "null"]},
                        "filer_name": {"type": ["string", "null"]},
                        "transaction_last_name": {"type": ["string", "null"]},
                        "transaction_first_name": {"type": ["string", "null"]},
                        "transaction_amount_1": {"type": ["string", "null"]},
                        "calculated_amount": {"type": ["string", "null"]},
                        "transaction_date": {"type": ["string", "null"]},
                        "calculated_date": {"type": ["string", "null"]},
                        "transaction_employer": {"type": ["string", "null"]},
                        "transaction_occupation": {"type": ["string", "null"]},
                        "entity_code": {"type": ["string", "null"]},
                        "transaction_city": {"type": ["string", "null"]},
                    },
                },
            },
        },
        "businesses_stream": {
            "type": "DeclarativeStream",
            "name": "businesses",
            "retriever": {
                "type": "SimpleRetriever",
                "requester": {
                    "$ref": "#/definitions/base_requester",
                    "path": f"{SODA_DATASETS['businesses']['resource_id']}.json",
                },
                "record_selector": {
                    "type": "RecordSelector",
                    "extractor": {"type": "DpathExtractor", "field_path": []},
                },
            },
            "schema_loader": {
                "type": "InlineSchemaLoader",
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "dba_name": {"type": ["string", "null"]},
                        "ownership_name": {"type": ["string", "null"]},
                        "business_start_date": {"type": ["string", "null"]},
                        "location": {"type": ["string", "null"]},
                        "business_corridor": {"type": ["string", "null"]},
                        "naic_code": {"type": ["string", "null"]},
                    },
                },
            },
        },
    },
    "streams": [
        {"$ref": "#/definitions/contracts_stream"},
        {"$ref": "#/definitions/campaign_finance_stream"},
        {"$ref": "#/definitions/businesses_stream"},
    ],
}


def ingest_via_airbyte(streams: Optional[list[str]] = None) -> dict:
    """Ingest SF data via PyAirbyte with declarative manifest. Returns dict of DataFrames."""
    import airbyte as ab

    source = ab.get_source(
        "source-declarative-manifest",
        config={"app_token": SODA_APP_TOKEN},
        source_manifest=SODA_MANIFEST,
    )
    source.check()

    if streams:
        source.select_streams(streams)
    else:
        source.select_all_streams()

    result = source.read()
    return {name: result[name].to_pandas() for name in (streams or SODA_DATASETS.keys())}


# ---------------------------------------------------------------------------
# Direct HTTP fallback (no Airbyte dependency)
# ---------------------------------------------------------------------------


def fetch_soda_dataset(
    resource_id: str,
    limit: int = DEFAULT_RECORD_LIMIT,
    where: Optional[str] = None,
    offset: int = 0,
) -> list[dict]:
    """Fetch a single dataset from SODA API via HTTP."""
    params: dict = {"$limit": limit, "$offset": offset}
    if SODA_APP_TOKEN:
        params["$$app_token"] = SODA_APP_TOKEN
    if where:
        params["$where"] = where

    resp = requests.get(f"{SODA_BASE_URL}/{resource_id}.json", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_all_datasets(limit: int = DEFAULT_RECORD_LIMIT) -> dict[str, list[dict]]:
    """Fetch all 3 SODA datasets via direct HTTP. Returns {name: [records]}."""
    results = {}
    for name, meta in SODA_DATASETS.items():
        print(f"  Fetching {meta['description']} ({meta['resource_id']})...")
        results[name] = fetch_soda_dataset(meta["resource_id"], limit=limit)
        print(f"    → {len(results[name]):,} records")
    return results


def save_raw_json(datasets: dict[str, list[dict]]) -> dict[str, str]:
    """Save raw datasets as JSON files in data/ for pre-seeding."""
    paths = {}
    for name, records in datasets.items():
        path = os.path.join(DATA_DIR, f"{name}.json")
        with open(path, "w") as f:
            json.dump(records, f)
        paths[name] = path
        print(f"  Saved {len(records):,} records → {path}")
    return paths


def load_raw_json() -> dict[str, list[dict]]:
    """Load pre-seeded JSON files from data/ directory."""
    datasets = {}
    for name in SODA_DATASETS:
        path = os.path.join(DATA_DIR, f"{name}.json")
        if os.path.exists(path):
            with open(path) as f:
                datasets[name] = json.load(f)
            print(f"  Loaded {len(datasets[name]):,} records from {path}")
    return datasets
