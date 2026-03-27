# Data Sources — SF Government Open Data (SODA API)

All sources use Socrata Open Data API (SODA). No auth required for reads. Optional app token for higher rate limits.
Register at `https://data.sfgov.org` for an app token.

## Source 1: SF Supplier Contracts

- **Endpoint:** `https://data.sfgov.org/resource/cqi5-hm2d.json`
- **Fields:** contract_no, contract_title, prime_contractor, project_team_supplier, agreed_amt, consumed_amt, pmt_amt, remaining_amt, department, department_code, contract_type, purchasing_authority, scope_of_work, term_start_date, term_end_date, project_team_lbe_status
- **Query example:** `?$limit=5000&$where=agreed_amt > 100000`
- **What it reveals:** Who gets city money, how much, from which department, contract type

## Source 2: Campaign Finance Transactions

- **Endpoint:** `https://data.sfgov.org/resource/pitq-e56w.json`
- **Fields:** filer_nid, filer_name (committee), transaction_last_name, transaction_first_name, transaction_amount_1, calculated_amount, transaction_date, calculated_date, transaction_city, transaction_employer, transaction_occupation, entity_code, form_type, filing_type
- **Query example:** `?$limit=10000&$where=calculated_amount > 1000`
- **What it reveals:** Who donated to which political campaigns, how much, and what they do for a living

## Source 3: Registered Businesses

- **Endpoint:** `https://data.sfgov.org/resource/g8m3-pdis.json`
- **Fields:** dba_name, ownership_name, full_business_address, dba_start_date, dba_end_date, city, state, business_zip, certificate_number, ttxid, parking_tax, transient_occupancy_tax
- **What it reveals:** When a business was formed, who owns it, where it's registered

## SODA API Basics

- JSON response format, SoQL filtering
- Pagination: use `$limit` + `$offset` (paginate in 10k chunks for reliability)
- Filtering via `$where`, `$limit`, `$offset`, `$order`
- Incremental sync via date field filtering (e.g., `$where=calculated_date > '2024-01-01'`)
- 50k single-request downloads timeout — use pagination

## Pre-Seeding Commands

Use the pipeline to download and save all data:

```bash
python -m pipeline.run_pipeline --seed --limit 50000
```

Or curl with pagination (10k per page):
```bash
for i in 0 10000 20000 30000 40000; do
  curl "https://data.sfgov.org/resource/cqi5-hm2d.json?\$limit=10000&\$offset=$i" >> data/contracts.json
done
```
