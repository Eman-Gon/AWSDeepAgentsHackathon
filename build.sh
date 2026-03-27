#!/usr/bin/env bash
# build.sh — Render build script for Commons.
#
# This script runs during Render's build phase. It:
#   1. Installs Python dependencies (for the investigation backend)
#   2. Rebuilds the SQLite knowledge graph from pre-seeded JSON data
#   3. Installs Node.js dependencies and builds the Vite frontend
#
# Render provides Node.js (via NODE_VERSION env var) and Python
# (via PYTHON_VERSION env var) automatically.

set -e  # exit immediately on any error

echo "=== [1/3] Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== [2/3] Building SQLite knowledge graph ==="
# The JSON data files are too large for git (~150MB), so we fetch fresh
# data from the SF SODA API during build. The pipeline fetches, extracts
# entities, and loads them into SQLite.
# --sqlite: force SQLite output (no Aerospike needed in prod)
# --limit 10000: fetch up to 10k records per dataset (keeps build fast)
python -m pipeline.run_pipeline --sqlite --limit 10000

echo "=== [3/3] Building frontend ==="
cd homepage
npm install
npm run build
cd ..

echo "=== Build complete ==="
echo "  Frontend: homepage/dist/"
echo "  Database: data/commons_graph.db"
