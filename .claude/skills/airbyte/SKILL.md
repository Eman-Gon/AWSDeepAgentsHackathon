---
name: airbyte
description: PyAirbyte SDK reference for data ingestion pipelines. Use when building data connectors, ETL pipelines, reading from REST APIs or databases via Airbyte source connectors in Python, or integrating Airbyte into the Commons hackathon project.
---

# Airbyte (PyAirbyte SDK)

## Overview

PyAirbyte lets you use any of Airbyte's 500+ source connectors directly in Python — no Docker, no Airbyte server needed. Data flows from sources into local DuckDB cache (default) or pandas DataFrames.

## Quick Start

```bash
pip install airbyte
```

```python
import airbyte as ab

# Connect to a source connector by name
source = ab.get_source(
    "source-faker",           # any connector from the registry
    config={"count": 1000},   # connector-specific config
    install_if_missing=True,  # auto-install the connector package
)

# Validate the connection
source.check()

# Select which streams to read
source.select_all_streams()
# OR: source.select_streams(["users", "products"])

# Read data (cached in local DuckDB by default)
result = source.read()

# Access data as pandas DataFrame
df = result["users"].to_pandas()

# Or iterate records directly
for record in result["users"]:
    print(record)
```

## Custom REST API Sources (Declarative YAML)

For APIs without an existing connector (like SF SODA API), use `source_manifest`:

```python
import airbyte as ab

# Define a custom source using declarative YAML manifest
manifest = {
    "version": "0.1.0",
    "type": "DeclarativeSource",
    "definitions": {
        "requester": {
            "type": "HttpRequester",
            "url_base": "https://data.sfgov.org/resource/",
            "http_method": "GET",
            "request_parameters": {
                "$limit": "50000",
                "$$app_token": "{{ config['app_token'] }}"
            }
        },
        "contracts_stream": {
            "type": "DeclarativeStream",
            "name": "contracts",
            "primary_key": "contract_id",
            "retriever": {
                "type": "SimpleRetriever",
                "requester": {
                    "$ref": "#/definitions/requester",
                    "path": "cqi5-hm2d.json"
                }
            }
        }
    },
    "streams": [{"$ref": "#/definitions/contracts_stream"}]
}

source = ab.get_source(
    "source-declarative-manifest",
    config={"app_token": "YOUR_SODA_TOKEN"},
    source_manifest=manifest,
)
result = source.read()
contracts_df = result["contracts"].to_pandas()
```

## Key API Reference

| Method | Purpose |
|--------|---------|
| `ab.get_source(name, config, ...)` | Create a source connector instance |
| `source.check()` | Validate connection credentials |
| `source.get_available_streams()` | List all available streams |
| `source.select_all_streams()` | Select all streams for reading |
| `source.select_streams(["a","b"])` | Select specific streams |
| `source.read(cache=None)` | Read data into cache, returns ReadResult |
| `source.get_records("stream")` | Stream records without caching |
| `result["stream"].to_pandas()` | Convert cached stream to DataFrame |
| `result["stream"].to_arrow()` | Convert to Arrow dataset |
| `ab.new_local_cache("name")` | Create a named DuckDB cache |
| `ab.get_source(..., source_manifest=dict)` | Use declarative YAML manifest |

## Caching Options

```python
# Default: local DuckDB (auto-created in .cache/)
result = source.read()  # uses DuckDB

# Named cache for persistence across runs
cache = ab.new_local_cache("my_project")
result = source.read(cache=cache)

# Access underlying SQL engine
engine = result.get_sql_engine()
```

## Write Strategies

```python
from airbyte import WriteStrategy

# Append new records (default for incremental)
result = source.read(write_strategy=WriteStrategy.APPEND)

# Replace all data each time
result = source.read(write_strategy=WriteStrategy.REPLACE, force_full_refresh=True)

# Merge/upsert based on primary key
result = source.read(write_strategy=WriteStrategy.MERGE)
```

## Commons Project Integration

For the Commons hackathon, use PyAirbyte to ingest SF government data:

```python
# Option 1: Direct HTTP fetch (simpler, no connector needed)
import requests
contracts = requests.get(
    "https://data.sfgov.org/resource/cqi5-hm2d.json",
    params={"$limit": 50000, "$$app_token": SODA_TOKEN}
).json()

# Option 2: PyAirbyte with declarative manifest (gets caching, schema, incremental)
# See the Custom REST API Sources section above
```

See [references/pyairbyte-api.md](references/pyairbyte-api.md) for the extended API reference.

## Critical Rules

- Always call `source.check()` before `source.read()` to fail fast on bad credentials
- Use `install_if_missing=True` on `get_source()` — connectors install automatically
- For hackathon speed: prefer `get_records()` for quick data exploration, `read()` for persistent pipelines
- DuckDB cache files land in `.cache/` — gitignore this directory
- `source_manifest` accepts `True` (auto-download), `dict`, `Path`, or URL string

## Resources

See the references/ directory for detailed API docs:

- `references/pyairbyte-api.md` — Extended PyAirbyte API with all classes and methods
- `references/soda-connector.md` — Declarative manifest template for SF SODA API
