# Data Sources — SF Government Open Data (SODA API)

All sources use Socrata Open Data API (SODA). No auth required for reads. Optional app token for higher rate limits.
Register at `https://data.sfgov.org` for an app token.

## Source 1: SF Supplier Contracts

- **Endpoint:** `https://data.sfgov.org/resource/cqi5-hm2d.json`
- **Fields:** supplier_name, contract_number, contract_title, department, contract_award_amount, date, sole_source, type_of_goods_and_services
- **Query example:** `?$limit=5000&$where=contract_award_amount > 100000`
- **What it reveals:** Who gets city money, how much, from which department, whether sole-source (no competitive bid)

## Source 2: Campaign Finance Transactions

- **Endpoint:** `https://data.sfgov.org/resource/pitq-e56w.json`
- **Fields:** filer_id, filer_naml (committee name), tran_naml (contributor name), tran_amt1 (amount), tran_date, tran_city, tran_emp (employer), tran_occ (occupation)
- **Query example:** `?$limit=10000&$where=tran_amt1 > 1000`
- **What it reveals:** Who donated to which political campaigns, how much, and what they do for a living

## Source 3: Registered Businesses

- **Endpoint:** `https://data.sfgov.org/resource/g8m3-pdis.json`
- **Fields:** dba_name, ownership_name, full_business_address, business_start_date, naic_code_description, location
- **What it reveals:** When a business was formed, who owns it, where it's registered

## Source 4 (Stretch): SF Ethics Commission — Form 126f2

- **Endpoint:** Check DataSF for exact resource ID
- **What it reveals:** Notifications when city contractors submit proposals — direct link between contractors and city contracts

## SODA API Basics

- JSON response format, SoQL filtering
- Pagination at 50,000 records per page (use `$offset`)
- Filtering via `$where`, `$limit`, `$offset`, `$order`
- Incremental sync via date field filtering (e.g., `$where=date > '2024-01-01'`)

## Pre-Seeding Commands

Download all 3 datasets as JSON for local development:

```bash
curl "https://data.sfgov.org/resource/cqi5-hm2d.json?\$limit=50000" > data/contracts.json
curl "https://data.sfgov.org/resource/pitq-e56w.json?\$limit=50000" > data/campaign_finance.json
curl "https://data.sfgov.org/resource/g8m3-pdis.json?\$limit=50000" > data/businesses.json
```
