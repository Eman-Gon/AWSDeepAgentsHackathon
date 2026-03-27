"""
Corruption pattern detection for the Commons investigation agent.

Analyzes the knowledge graph around a target entity to identify
red flags that suggest potential conflicts of interest, bid rigging,
or other corruption indicators. Each pattern returns a severity
level and a human-readable explanation.

Patterns are based on real investigative journalism heuristics:
  - Shell company indicators (recently formed LLCs winning big contracts)
  - Pay-to-play (contractor officers donating to officials who award them contracts)
  - Address clustering (multiple contract-winning entities at the same address)
  - Contract concentration (one vendor dominating a department's spending)
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional

from agent.graph_queries import _connect, get_edges_for_entity


# ──────────────────────────────────────────────────────────────────────────
# Tool 6: detect_patterns — run all corruption checks on an entity
# ──────────────────────────────────────────────────────────────────────────

def detect_patterns(entity_id: str) -> list[dict]:
    """
    Run all corruption pattern checks against a specific entity.

    Args:
        entity_id: The entity to investigate (e.g. "company:acme_corp_12345678").

    Returns:
        List of detected pattern dicts, each containing:
          pattern_type, severity ("CRITICAL"/"HIGH"/"MEDIUM"/"LOW"),
          detail (human-readable explanation), confidence (0.0–1.0)
    """
    conn = _connect()
    try:
        # Fetch the entity
        row = conn.execute(
            "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if not row:
            return [{"pattern_type": "ERROR", "severity": "LOW",
                      "detail": f"Entity {entity_id} not found", "confidence": 0}]

        entity_type = row["type"]
        properties = json.loads(row["properties"] or "{}")
        patterns: list[dict] = []

        # Run pattern checks based on entity type
        if entity_type == "company":
            patterns.extend(_check_contract_concentration(conn, entity_id))
            patterns.extend(_check_shared_address(conn, entity_id))
            patterns.extend(_check_pay_to_play(conn, entity_id))
            patterns.extend(_check_shell_company(conn, entity_id, properties))

        elif entity_type == "person":
            patterns.extend(_check_donor_contractor_overlap(conn, entity_id))

        elif entity_type == "department":
            patterns.extend(_check_department_vendor_concentration(conn, entity_id))

        # Sort by severity (CRITICAL first)
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        patterns.sort(key=lambda p: severity_order.get(p["severity"], 4))

        return patterns
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Pattern 1: Contract concentration — one company getting too many contracts
# from a single department
# ──────────────────────────────────────────────────────────────────────────

def _check_contract_concentration(conn: sqlite3.Connection, company_id: str) -> list[dict]:
    """Flag when a company has many contracts from the same department."""
    patterns = []

    # Get all contracts this company is connected to
    contracts = conn.execute(
        "SELECT * FROM edges WHERE source_entity = ? AND relationship = 'CONTRACTED_WITH'",
        (company_id,)
    ).fetchall()

    # For each contract, find which department awarded it
    dept_counts: dict[str, list[str]] = {}  # dept_name → [contract_ids]
    for contract_edge in contracts:
        contract_id = contract_edge["target_entity"]
        # Find the department that awarded this contract
        dept_edges = conn.execute(
            "SELECT e.target_entity, en.name FROM edges e "
            "JOIN entities en ON e.target_entity = en.entity_id "
            "WHERE e.source_entity = ? AND e.relationship = 'AWARDED_BY'",
            (contract_id,)
        ).fetchall()
        for dept_edge in dept_edges:
            dept_name = dept_edge["name"]
            dept_counts.setdefault(dept_name, []).append(contract_id)

    # Flag departments where this company has 5+ contracts
    for dept, contract_ids in dept_counts.items():
        if len(contract_ids) >= 5:
            patterns.append({
                "pattern_type": "CONTRACT_CONCENTRATION",
                "severity": "HIGH" if len(contract_ids) >= 10 else "MEDIUM",
                "detail": (
                    f"Company has {len(contract_ids)} contracts from {dept}. "
                    f"High concentration may indicate preferential treatment."
                ),
                "confidence": min(0.5 + len(contract_ids) * 0.05, 0.95),
            })

    return patterns


# ──────────────────────────────────────────────────────────────────────────
# Pattern 2: Shared address — multiple contract-winning companies at same address
# ──────────────────────────────────────────────────────────────────────────

def _check_shared_address(conn: sqlite3.Connection, company_id: str) -> list[dict]:
    """Flag when multiple companies share a registered address."""
    patterns = []

    # Get this company's registered address(es)
    address_edges = conn.execute(
        "SELECT target_entity FROM edges WHERE source_entity = ? AND relationship = 'REGISTERED_AT'",
        (company_id,)
    ).fetchall()

    for addr_edge in address_edges:
        address_id = addr_edge["target_entity"]

        # Count how many OTHER companies share this address
        co_located = conn.execute(
            "SELECT e.source_entity, en.name FROM edges e "
            "JOIN entities en ON e.source_entity = en.entity_id "
            "WHERE e.target_entity = ? AND e.relationship = 'REGISTERED_AT' "
            "AND e.source_entity != ?",
            (address_id, company_id)
        ).fetchall()

        if len(co_located) >= 3:
            # Get the address name for the report
            addr_row = conn.execute(
                "SELECT name FROM entities WHERE entity_id = ?", (address_id,)
            ).fetchone()
            addr_name = addr_row["name"] if addr_row else address_id

            company_names = [r["name"] for r in co_located[:5]]
            patterns.append({
                "pattern_type": "SHARED_ADDRESS_CLUSTER",
                "severity": "HIGH" if len(co_located) >= 5 else "MEDIUM",
                "detail": (
                    f"{len(co_located) + 1} companies share address '{addr_name}': "
                    f"{', '.join(company_names)}"
                    + (f" and {len(co_located) - 5} more" if len(co_located) > 5 else "")
                    + ". Could indicate shell companies or related entities."
                ),
                "confidence": min(0.4 + len(co_located) * 0.1, 0.9),
            })

    return patterns


# ──────────────────────────────────────────────────────────────────────────
# Pattern 3: Pay-to-play — company officers donating to campaigns connected
# to officials who award them contracts
# ──────────────────────────────────────────────────────────────────────────

def _check_pay_to_play(conn: sqlite3.Connection, company_id: str) -> list[dict]:
    """Flag when a company's officers donate to campaigns linked to awarding officials."""
    patterns = []

    # Find people who are officers of this company
    officers = conn.execute(
        "SELECT source_entity FROM edges WHERE target_entity = ? AND relationship = 'OFFICER_OF'",
        (company_id,)
    ).fetchall()

    # Find campaigns these officers donated to
    officer_donations: list[dict] = []
    for officer in officers:
        person_id = officer["source_entity"]
        donations = conn.execute(
            "SELECT e.target_entity, en.name, e.properties FROM edges e "
            "JOIN entities en ON e.target_entity = en.entity_id "
            "WHERE e.source_entity = ? AND e.relationship = 'DONATED_TO'",
            (person_id,)
        ).fetchall()

        person_row = conn.execute(
            "SELECT name FROM entities WHERE entity_id = ?", (person_id,)
        ).fetchone()
        person_name = person_row["name"] if person_row else person_id

        for donation in donations:
            props = json.loads(donation["properties"] or "{}")
            officer_donations.append({
                "person": person_name,
                "person_id": person_id,
                "campaign": donation["name"],
                "amount": props.get("amount", "unknown"),
            })

    # If we found officer donations, that's a potential pay-to-play
    if officer_donations:
        total_donations = len(officer_donations)
        detail_lines = []
        for d in officer_donations[:5]:  # show top 5
            detail_lines.append(
                f"  - {d['person']} donated ${d['amount']} to {d['campaign']}"
            )

        patterns.append({
            "pattern_type": "PAY_TO_PLAY",
            "severity": "CRITICAL" if total_donations >= 3 else "HIGH",
            "detail": (
                f"Officers of this company made {total_donations} donations to political campaigns:\n"
                + "\n".join(detail_lines)
                + "\nThis may indicate pay-to-play corruption."
            ),
            "confidence": min(0.6 + total_donations * 0.1, 0.95),
        })

    return patterns


# ──────────────────────────────────────────────────────────────────────────
# Pattern 4: Shell company indicators — recently formed entity winning contracts
# ──────────────────────────────────────────────────────────────────────────

def _check_shell_company(
    conn: sqlite3.Connection, company_id: str, properties: dict
) -> list[dict]:
    """Flag companies that look like shell entities."""
    patterns = []

    # Check if company was recently formed (has dba_start_date)
    start_date_str = properties.get("dba_start_date", "")
    if start_date_str:
        try:
            # Parse the date (SODA dates can be various formats)
            start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))

            # Check if this company has contracts
            contract_count = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE source_entity = ? AND relationship = 'CONTRACTED_WITH'",
                (company_id,)
            ).fetchone()[0]

            if contract_count > 0:
                # How old was the company when it got contracts?
                now = datetime.now(start_date.tzinfo) if start_date.tzinfo else datetime.now()
                age_days = (now - start_date).days

                if age_days < 365:
                    patterns.append({
                        "pattern_type": "SHELL_COMPANY_INDICATOR",
                        "severity": "HIGH" if age_days < 180 else "MEDIUM",
                        "detail": (
                            f"Company formed {age_days} days ago but already has "
                            f"{contract_count} city contract(s). "
                            f"Recently formed entities winning contracts is a red flag."
                        ),
                        "confidence": max(0.9 - age_days * 0.002, 0.5),
                    })
        except (ValueError, TypeError):
            pass  # can't parse date, skip this check

    return patterns


# ──────────────────────────────────────────────────────────────────────────
# Pattern 5: Donor-contractor overlap — person donates AND their company contracts
# ──────────────────────────────────────────────────────────────────────────

def _check_donor_contractor_overlap(conn: sqlite3.Connection, person_id: str) -> list[dict]:
    """Flag when a person both donates to campaigns and is an officer of a contractor."""
    patterns = []

    # Check if person donated to any campaigns
    donations = conn.execute(
        "SELECT e.target_entity, en.name, e.properties FROM edges e "
        "JOIN entities en ON e.target_entity = en.entity_id "
        "WHERE e.source_entity = ? AND e.relationship = 'DONATED_TO'",
        (person_id,)
    ).fetchall()

    # Check if person is an officer of any company
    companies = conn.execute(
        "SELECT e.target_entity, en.name FROM edges e "
        "JOIN entities en ON e.target_entity = en.entity_id "
        "WHERE e.source_entity = ? AND e.relationship = 'OFFICER_OF'",
        (person_id,)
    ).fetchall()

    if donations and companies:
        # Check if any of those companies also have city contracts
        for company in companies:
            contract_count = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE source_entity = ? AND relationship = 'CONTRACTED_WITH'",
                (company["target_entity"],)
            ).fetchone()[0]

            if contract_count > 0:
                campaign_names = [d["name"] for d in donations[:3]]
                patterns.append({
                    "pattern_type": "DONOR_CONTRACTOR_OVERLAP",
                    "severity": "CRITICAL",
                    "detail": (
                        f"Person is an officer of {company['name']} ({contract_count} city contracts) "
                        f"AND donated to campaigns: {', '.join(campaign_names)}. "
                        f"Direct conflict of interest."
                    ),
                    "confidence": 0.85,
                })

    return patterns


# ──────────────────────────────────────────────────────────────────────────
# Pattern 6: Department vendor concentration — one department relying on few vendors
# ──────────────────────────────────────────────────────────────────────────

def _check_department_vendor_concentration(conn: sqlite3.Connection, dept_id: str) -> list[dict]:
    """Flag when a department awards most contracts to a small number of vendors."""
    patterns = []

    # Get all contracts awarded by this department
    contracts = conn.execute(
        "SELECT source_entity FROM edges WHERE target_entity = ? AND relationship = 'AWARDED_BY'",
        (dept_id,)
    ).fetchall()

    if not contracts:
        return patterns

    # For each contract, find the company
    vendor_counts: dict[str, int] = {}
    for contract_row in contracts:
        contract_id = contract_row["source_entity"]
        companies = conn.execute(
            "SELECT e.target_entity, en.name FROM edges e "
            "JOIN entities en ON e.source_entity = en.entity_id "
            "WHERE e.target_entity = ? AND e.relationship = 'CONTRACTED_WITH'",
            (contract_id,)
        ).fetchall()
        # Actually the edge direction is company → contract, so:
        companies = conn.execute(
            "SELECT e.source_entity, en.name FROM edges e "
            "JOIN entities en ON e.source_entity = en.entity_id "
            "WHERE e.target_entity = ? AND e.relationship = 'CONTRACTED_WITH'",
            (contract_id,)
        ).fetchall()
        for comp in companies:
            vendor_counts[comp["name"]] = vendor_counts.get(comp["name"], 0) + 1

    total_contracts = len(contracts)
    if total_contracts < 10:
        return patterns

    # Check if top vendor has disproportionate share
    sorted_vendors = sorted(vendor_counts.items(), key=lambda x: x[1], reverse=True)
    top_vendor_name, top_count = sorted_vendors[0]
    top_pct = top_count / total_contracts * 100

    if top_pct > 20:
        patterns.append({
            "pattern_type": "DEPARTMENT_VENDOR_CONCENTRATION",
            "severity": "HIGH" if top_pct > 40 else "MEDIUM",
            "detail": (
                f"Top vendor '{top_vendor_name}' holds {top_count}/{total_contracts} "
                f"contracts ({top_pct:.0f}%). Top 3: "
                + ", ".join(f"{n} ({c})" for n, c in sorted_vendors[:3])
            ),
            "confidence": min(0.5 + top_pct / 100, 0.9),
        })

    return patterns
