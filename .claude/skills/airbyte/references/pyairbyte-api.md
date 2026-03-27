# PyAirbyte Extended API Reference

## Installation

```bash
pip install airbyte
```

## Module Structure

```
airbyte (import as ab)
├── sources      — Source connector management
├── caches       — SQL cache backends (DuckDB, Postgres, BigQuery, Snowflake)
├── datasets     — CachedDataset, LazyDataset
├── destinations — Destination connector management
├── documents    — LLM document format conversion
├── secrets      — Secret management (env, dotenv, prompt)
├── records      — StreamRecord handling
├── results      — ReadResult, WriteResult
└── cloud        — Airbyte Cloud integration
```

## get_source() — Full Signature

```python
ab.get_source(
    name: str,                          # connector name, e.g. "source-faker"
    config: dict | None = None,         # connector config
    streams: str | list[str] | None = None,  # pre-select streams ("*" for all)
    version: str | None = None,         # pin connector version
    source_manifest: bool | dict | Path | str | None = None,  # declarative YAML
    install_if_missing: bool = True,    # auto-install from PyPI
    docker_image: bool | str | None = None,  # run via Docker
    pip_url: str | None = None,         # custom pip URL
    local_executable: Path | str | None = None,  # pre-installed binary
) -> Source
```

### source_manifest options:
- `True` — auto-download YAML spec from registry
- `dict` — inline Python dictionary manifest
- `Path` — local file path to YAML
- `str` — URL to download YAML from

## Source Methods

```python
source.check()                    # validate connection, raises on failure
source.get_available_streams()    # returns list[str] of stream names
source.select_all_streams()       # select everything
source.select_streams(["a","b"])  # select specific streams
source.get_selected_streams()     # returns currently selected list
source.set_config(config, validate=True)  # update config
source.get_stream_json_schema("stream")  # JSON Schema for a stream
source.config_spec                # full config spec as dict
source.docs_url                   # URL to connector docs
```

## source.read() — Full Signature

```python
source.read(
    cache: CacheBase | None = None,     # None = default DuckDB
    streams: str | list[str] | None = None,  # override stream selection
    write_strategy: WriteStrategy = WriteStrategy.AUTO,
    force_full_refresh: bool = False,   # ignore incremental state
    skip_validation: bool = False,      # skip JSON schema validation
) -> ReadResult
```

## source.get_records() — Streaming Without Cache

```python
# Returns LazyDataset — iterate without writing to cache
records = source.get_records(
    stream="users",
    limit=100,              # max records (None = all)
    normalize_field_names=False,  # lowercase field names
    prune_undeclared_fields=True, # remove extra fields
)

for record in records:
    print(record)  # dict-like StreamRecord
```

## ReadResult

```python
result = source.read()

result.processed_records     # total records read (int)
result.streams              # Mapping[str, CachedDataset]
result.cache                # the CacheBase used
result.get_sql_engine()     # SQLAlchemy Engine

# Access by stream name
dataset = result["users"]   # CachedDataset
```

## CachedDataset

```python
dataset = result["users"]

dataset.to_pandas()         # -> pd.DataFrame
dataset.to_arrow()          # -> pa.Dataset
dataset.to_sql_table()      # -> sqlalchemy.Table

# Iterate records
for record in dataset:
    print(record)
```

## Cache Types

```python
# Default DuckDB (auto-created)
cache = ab.get_default_cache()

# Named DuckDB
cache = ab.new_local_cache("my_cache")

# Postgres
from airbyte.caches import PostgresCache
cache = PostgresCache(
    host="localhost", port=5432,
    username="user", password="pass",
    database="mydb", schema_name="public"
)

# BigQuery
from airbyte.caches import BigQueryCache
cache = BigQueryCache(
    project_name="my-project",
    dataset_name="my_dataset",
    credentials_path="/path/to/creds.json"
)
```

## Secrets Management

```python
# Auto-checks: env vars, .env file, then prompts user
secret = ab.get_secret("MY_API_KEY")

# Specify sources explicitly
from airbyte import SecretSourceEnum
secret = ab.get_secret(
    "MY_KEY",
    sources=[SecretSourceEnum.ENV, SecretSourceEnum.DOTENV],
    allow_prompt=False
)
```

## StreamRecord

- Dict subclass, case-insensitive key access
- Includes Airbyte metadata: `_airbyte_raw_id`, `_airbyte_extracted_at`, `_airbyte_meta`
- `record["Name"]` and `record["name"]` return the same value

## WriteStrategy Enum

| Value | Behavior |
|-------|----------|
| `AUTO` | Connector decides (default) |
| `APPEND` | Add new records |
| `REPLACE` | Drop and recreate |
| `MERGE` | Upsert by primary key |

## Error Types

- `PyAirbyteSecretNotFoundError` — secret not in any configured source
- `PyAirbyteInputError` — invalid config or arguments
- Connection errors from `source.check()` — bad credentials or network
