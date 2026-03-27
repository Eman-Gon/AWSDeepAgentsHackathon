"""
Entity extraction and normalization transform.

Sits between SODA raw data and Aerospike loader:
  raw records → entities (persons, companies, addresses) + edges (relationships)
"""

import hashlib
import re
from datetime import datetime
from typing import Optional

from thefuzz import fuzz


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

def normalize_name(name: Optional[str]) -> str:
    """Normalize a name for deduplication: strip punctuation, uppercase, collapse whitespace."""
    if not name:
        return ""
    name = name.upper().strip()
    name = re.sub(r"[.,\-'\"()]", " ", name)  # remove punctuation
    name = re.sub(r"\b(LLC|INC|CORP|CO|LTD|L\.L\.C\.?|INCORPORATED)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def make_entity_id(entity_type: str, name: str) -> str:
    """Generate a stable entity ID from type + normalized name."""
    normalized = normalize_name(name)
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    # Add a short hash to handle collisions on very long names
    short_hash = hashlib.md5(normalized.encode()).hexdigest()[:8]
    return f"{entity_type}:{slug}_{short_hash}"


def names_match(a: str, b: str, threshold: int = 85) -> bool:
    """Check if two names are a fuzzy match."""
    return fuzz.token_sort_ratio(normalize_name(a), normalize_name(b)) >= threshold


# ---------------------------------------------------------------------------
# Entity + edge containers
# ---------------------------------------------------------------------------

class EntityStore:
    """Accumulates deduplicated entities and edges from multiple data sources."""

    def __init__(self):
        self.entities: dict[str, dict] = {}  # entity_id → entity dict
        self.edges: list[dict] = []

    def upsert_entity(
        self,
        entity_type: str,
        name: str,
        properties: Optional[dict] = None,
        source: str = "unknown",
    ) -> str:
        """Add or update an entity. Returns entity_id."""
        eid = make_entity_id(entity_type, name)
        now = datetime.utcnow().isoformat()

        if eid in self.entities:
            ent = self.entities[eid]
            if name not in ent["aliases"]:
                ent["aliases"].append(name)
            if source not in ent["sources"]:
                ent["sources"].append(source)
            ent["properties"].update(properties or {})
            ent["last_updated"] = now
        else:
            self.entities[eid] = {
                "entity_id": eid,
                "type": entity_type,
                "name": name,
                "aliases": [name],
                "properties": properties or {},
                "sources": [source],
                "first_seen": now,
                "last_updated": now,
                "flagged_in_investigations": [],
            }
        return eid

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        properties: Optional[dict] = None,
        source_dataset: str = "unknown",
        confidence: float = 1.0,
    ) -> str:
        """Add a directed edge between two entities."""
        edge_id = f"edge:{source_id}:{relationship.lower()}:{target_id}"
        self.edges.append({
            "edge_id": edge_id,
            "source_entity": source_id,
            "target_entity": target_id,
            "relationship": relationship,
            "properties": properties or {},
            "source_dataset": source_dataset,
            "confidence": confidence,
        })
        return edge_id

    @property
    def stats(self) -> dict:
        types = {}
        for e in self.entities.values():
            types[e["type"]] = types.get(e["type"], 0) + 1
        rels = {}
        for e in self.edges:
            rels[e["relationship"]] = rels.get(e["relationship"], 0) + 1
        return {"entities": types, "edges": rels, "total_entities": len(self.entities), "total_edges": len(self.edges)}


# ---------------------------------------------------------------------------
# Dataset-specific extractors
# ---------------------------------------------------------------------------

def extract_from_contracts(records: list[dict], store: EntityStore) -> None:
    """Extract entities and edges from SF Supplier Contracts.

    Actual SODA field names (cqi5-hm2d):
      prime_contractor, project_team_supplier, contract_no, contract_title,
      agreed_amt, department, contract_type, purchasing_authority,
      term_start_date, term_end_date, scope_of_work
    """
    for rec in records:
        # Try multiple possible vendor field names
        vendor = (rec.get("prime_contractor")
                  or rec.get("project_team_supplier")
                  or rec.get("supplier_name")
                  or rec.get("vendor_name"))
        dept = rec.get("department")
        contract_num = rec.get("contract_no") or rec.get("contract_number", "unknown")

        if not vendor:
            continue

        # Entities
        vendor_id = store.upsert_entity(
            "company", vendor,
            properties={
                "contract_amount": rec.get("agreed_amt"),
                "contract_type": rec.get("contract_type"),
                "purchasing_authority": rec.get("purchasing_authority"),
            },
            source="contracts",
        )

        contract_id = store.upsert_entity(
            "contract", f"Contract {contract_num}",
            properties={
                "amount": rec.get("agreed_amt"),
                "title": rec.get("contract_title"),
                "department": dept,
                "start_date": rec.get("term_start_date"),
                "end_date": rec.get("term_end_date"),
                "scope": rec.get("scope_of_work"),
                "contract_type": rec.get("contract_type"),
            },
            source="contracts",
        )

        # Edges
        store.add_edge(vendor_id, contract_id, "CONTRACTED_WITH",
                       properties={"amount": rec.get("agreed_amt")},
                       source_dataset="contracts")

        if dept:
            dept_id = store.upsert_entity("department", dept, source="contracts")
            store.add_edge(contract_id, dept_id, "AWARDED_BY",
                           properties={"department": dept},
                           source_dataset="contracts")


def extract_from_campaign_finance(records: list[dict], store: EntityStore) -> None:
    """Extract entities and edges from Campaign Finance Transactions.

    Actual SODA field names (pitq-e56w):
      transaction_last_name, transaction_first_name, filer_name,
      transaction_amount_1 / calculated_amount, transaction_date / calculated_date,
      transaction_employer, transaction_occupation, transaction_city,
      filer_nid, entity_code, form_type
    """
    for rec in records:
        # Build contributor name from first + last, or fall back to last only
        last_name = rec.get("transaction_last_name") or rec.get("tran_naml")
        first_name = rec.get("transaction_first_name") or rec.get("tran_namf", "")
        if last_name and first_name:
            contributor = f"{first_name} {last_name}".strip()
        elif last_name:
            contributor = last_name
        else:
            contributor = None

        committee = rec.get("filer_name") or rec.get("filer_naml")
        amount = (rec.get("transaction_amount_1")
                  or rec.get("calculated_amount")
                  or rec.get("tran_amt1"))

        if not contributor or not committee:
            continue

        # Entities
        person_id = store.upsert_entity(
            "person", contributor,
            properties={
                "employer": rec.get("transaction_employer") or rec.get("tran_emp"),
                "occupation": rec.get("transaction_occupation") or rec.get("tran_occ"),
                "city": rec.get("transaction_city") or rec.get("tran_city"),
            },
            source="campaign_finance",
        )

        campaign_id = store.upsert_entity(
            "campaign", committee,
            properties={"filer_id": rec.get("filer_nid") or rec.get("filer_id")},
            source="campaign_finance",
        )

        # Edge
        store.add_edge(person_id, campaign_id, "DONATED_TO",
                       properties={
                           "amount": amount,
                           "date": rec.get("transaction_date") or rec.get("calculated_date"),
                       },
                       source_dataset="campaign_finance")


def extract_from_businesses(records: list[dict], store: EntityStore) -> None:
    """Extract entities and edges from Registered Businesses."""
    for rec in records:
        biz_name = rec.get("dba_name")
        owner = rec.get("ownership_name")
        address = rec.get("full_business_address")

        if not biz_name:
            continue

        # Entities
        biz_id = store.upsert_entity(
            "company", biz_name,
            properties={
                "business_start_date": rec.get("business_start_date"),
                "naic_code": rec.get("naic_code_description"),
            },
            source="businesses",
        )

        if owner:
            owner_id = store.upsert_entity("person", owner, source="businesses")
            store.add_edge(owner_id, biz_id, "OFFICER_OF", source_dataset="businesses")

        if address:
            addr_id = store.upsert_entity(
                "address", address,
                properties={"location": rec.get("location")},
                source="businesses",
            )
            store.add_edge(biz_id, addr_id, "REGISTERED_AT", source_dataset="businesses")


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------

EXTRACTORS = {
    "contracts": extract_from_contracts,
    "campaign_finance": extract_from_campaign_finance,
    "businesses": extract_from_businesses,
}


def extract_all(datasets: dict[str, list[dict]]) -> EntityStore:
    """Run entity extraction across all datasets. Returns populated EntityStore."""
    store = EntityStore()
    for name, records in datasets.items():
        extractor = EXTRACTORS.get(name)
        if extractor:
            print(f"  Extracting from {name} ({len(records):,} records)...")
            extractor(records, store)
    print(f"  Extraction complete: {store.stats}")
    return store
