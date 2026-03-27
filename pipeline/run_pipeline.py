#!/usr/bin/env python3
"""
Commons data pipeline orchestrator.

Usage:
  python -m pipeline.run_pipeline                  # full pipeline (fetch → extract → load)
  python -m pipeline.run_pipeline --seed           # download data to data/ for pre-seeding
  python -m pipeline.run_pipeline --local          # load from pre-seeded JSON, skip fetch
  python -m pipeline.run_pipeline --sqlite         # force SQLite instead of Aerospike
  python -m pipeline.run_pipeline --airbyte        # use PyAirbyte instead of direct HTTP
"""

import argparse
import sys
import time


def main():
    parser = argparse.ArgumentParser(description="Commons data ingestion pipeline")
    parser.add_argument("--seed", action="store_true", help="Download raw data to data/ and exit")
    parser.add_argument("--local", action="store_true", help="Load from pre-seeded JSON files in data/")
    parser.add_argument("--sqlite", action="store_true", help="Force SQLite fallback (no Aerospike)")
    parser.add_argument("--airbyte", action="store_true", help="Use PyAirbyte instead of direct HTTP")
    parser.add_argument("--limit", type=int, default=50000, help="Max records per dataset")
    args = parser.parse_args()

    from pipeline.soda_source import (
        fetch_all_datasets,
        ingest_via_airbyte,
        load_raw_json,
        save_raw_json,
    )
    from pipeline.entity_extraction import extract_all
    from pipeline.aerospike_loader import load_graph

    start = time.time()

    # Step 1: Ingest data
    print("\n=== Step 1: Data Ingestion ===")
    if args.local:
        print("Loading from pre-seeded JSON files...")
        datasets = load_raw_json()
        if not datasets:
            print("ERROR: No pre-seeded data found in data/. Run with --seed first.")
            sys.exit(1)
    elif args.airbyte:
        print("Ingesting via PyAirbyte declarative manifest...")
        dfs = ingest_via_airbyte()
        # Convert DataFrames to list[dict] for entity extraction
        datasets = {name: df.to_dict("records") for name, df in dfs.items()}
    else:
        print("Fetching from SODA API (direct HTTP)...")
        datasets = fetch_all_datasets(limit=args.limit)

    # Optionally save raw data for future pre-seeding
    if args.seed:
        print("\n=== Saving raw data for pre-seeding ===")
        save_raw_json(datasets)
        elapsed = time.time() - start
        print(f"\nDone in {elapsed:.1f}s. Data saved to data/. Run with --local to use it.")
        return

    # Step 2: Entity extraction
    print("\n=== Step 2: Entity Extraction ===")
    store = extract_all(datasets)

    # Step 3: Graph loading
    print("\n=== Step 3: Graph Loading ===")
    stats = load_graph(store, force_sqlite=args.sqlite)

    elapsed = time.time() - start
    print(f"\n=== Pipeline complete in {elapsed:.1f}s ===")
    print(f"  Entities: {store.stats}")
    print(f"  Loaded: {stats}")


if __name__ == "__main__":
    main()
