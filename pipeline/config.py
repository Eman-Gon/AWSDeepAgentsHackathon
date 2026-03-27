"""Pipeline configuration — loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- SODA API ---
SODA_BASE_URL = "https://data.sfgov.org/resource"
SODA_APP_TOKEN = os.getenv("SODA_APP_TOKEN", "")  # optional, avoids rate limits

SODA_DATASETS = {
    "contracts": {
        "resource_id": "cqi5-hm2d",
        "description": "SF Supplier Contracts",
        "key_fields": ["contract_number"],
        "date_field": "start_date",
    },
    "campaign_finance": {
        "resource_id": "pitq-e56w",
        "description": "Campaign Finance Transactions",
        "key_fields": ["filer_id", "tran_naml", "tran_date"],
        "date_field": "tran_date",
    },
    "businesses": {
        "resource_id": "g8m3-pdis",
        "description": "Registered Businesses",
        "key_fields": ["dba_name", "ownership_name"],
        "date_field": "business_start_date",
    },
}

DEFAULT_RECORD_LIMIT = 50_000

# --- Aerospike ---
AEROSPIKE_HOST = os.getenv("AEROSPIKE_HOST", "127.0.0.1")
AEROSPIKE_PORT = int(os.getenv("AEROSPIKE_PORT", "3000"))
AEROSPIKE_NAMESPACE = os.getenv("AEROSPIKE_NAMESPACE", "commons")

# --- Paths ---
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
