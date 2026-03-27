# Commons: Investigative Intelligence for Government Oversight

**An AI-powered platform for detecting corruption in government contracts and public records.** 

Commons autonomously investigates San Francisco government data (contracts, campaign finance, business registrations) to uncover pay-to-play schemes, shell company networks, and conflict-of-interest patterns. Built for journalists, investigators, and civic watchdogs.

🌐 **Live Demo**: https://commons-ovyq.onrender.com

---

## Overview

Corruption in government procurement happens at the intersection of three domains:
- **Contracts**: which companies win city work
- **Campaign Finance**: who funds politicians who award contracts
- **Business Registration**: hidden ownership of shell companies

Investigating these connections manually takes weeks. Commons does it in seconds.

### The Platform

- **Knowledge Graph**: 186K+ entities (persons, companies, city departments, contracts, campaigns) + 245K+ edges mapping their relationships
- **AI Investigation Agent**: Gemini Flash with function calling autonomously traverses the graph to find corruption patterns
- **Interactive Frontend**: Real-time visualization of entity networks, contract flows, and corruption findings
- **Anonymous Tip Submission**: Whistleblowers can submit tips without accounts
- **Saved Investigations**: Persist and publish findings for follow-up reporting

### Key Features

| Feature | What It Detects |
|---------|-----------------|
| **Pay-to-Play Detection** | Owners donate to politician → their company wins contracts from that politician |
| **Shell Company Networks** | Multiple newly-formed companies sharing addresses, winning from same departments |
| **Conflict of Interest** | City officials awarding contracts to companies their relatives own/work for |
| **Pattern Aggregation** | Which vendors get the most contracts? Which politicians receive the most donations? |
| **Prior Investigation Search** | Check if a company/person has already been investigated |
| **Anonymous Tip Intake** | One-time-retrieval tokens for secure tip submission |

---

## Architecture

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Preact + TypeScript + Vite | Interactive investigation UI + entity graph viz |
| **Backend** | Python 3.11 + Gemini Flash 2.0 | Investigation agent with function calling |
| **Database** | SQLite (local) / Turso/LibSQL (cloud) | Knowledge graph storage |
| **Auth** | Auth0 | Login + RBAC for investigator accounts |
| **Alerting** | Server-Sent Events (SSE) | Real-time investigation progress streaming |
| **Deployment** | Render | Free-tier Python web service + static hosting |
| **Optional**: TrueFoundry AI Gateway | Token cost tracking + LLM observability |
| **Optional**: Overmind SDK | Synthetic evaluation of investigation quality |

### Data Flow

```
1. SODA API (SF Open Data) 
        ↓
  Airbyte connectors extract contracts, donations, business registrations
        ↓
2. Entity Extraction + Linking
        ↓
  Python pipeline fuzzy-matches companies/persons → deduplicates → normalizes
        ↓
3. Knowledge Graph
        ↓
  SQLite with indexed tables: entities, edges, investigations
        ↓
4. Investigation Agent (Gemini Flash)
        ↓
  Function calling: search → get_details → traverse → detect_patterns → aggregate
        ↓
5. Frontend (SSE stream)
        ↓
  Real-time rendering of findings in graph, globe, narrative panels
```

### Investigation Flow

When a user starts an investigation (e.g., "Investigate Recology's SF contracts"):

1. **Agent receives query** → Frontend sends to `/api/investigate?q=...`
2. **Search phase**: `search_entity()` finds Recology in the graph (186K entities scanned via SQLite full-text search)
3. **Detail phase**: `get_entity_details()` retrieves Recology's metadata (contract count, locations, officers)
4. **Traversal phase**: `traverse_connections()` runs 2-3 hop BFS to find related entities
   - Recology → officers → their other companies
   - Recology → contract departments → those departments' other vendors
   - Recology → shared addresses → other companies at same address
5. **Pattern detection**: `detect_patterns()` runs heuristics for:
   - Conflict of interest (officers donating to politicians who awarded contracts)
   - Shell company networks (newly-formed, shared infrastructure)
   - Unusually high contract values relative to company age
6. **Aggregation**: `aggregate_query()` surfaces the BiggestPlayers (top vendors by total contract value)
7. **Synthesis**: Agent compiles findings into a structured briefing with evidence chains and confidence scores
8. **Frontend renders**: As SSE events stream in, the frontend updates entity graphs, highlights suspicious edges, and displays the narrative briefing

---

## Quick Start

### Development

**Prerequisites**: Python 3.11+, Node.js 20+, GEMINI_API_KEY

```bash
# Clone and enter the project
git clone https://github.com/Eman-Gon/AWSDeepAgentsHackathon.git
cd AWSDeepAgentsHackathon

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd homepage && npm install && cd ..

# Build the SQLite knowledge graph from SODA API
python -m pipeline.run_pipeline --local --sqlite

# Start the Python backend (port 8000)
python -m agent.server

# In another terminal, start the Vite dev server (port 5173)
cd homepage && npm run dev

# App available at http://localhost:5173
```

### Deployment (Render)

The repo includes a `render.yaml` blueprint that deploys both frontend and backend as a single web service.

**One-time setup**:
1. Go to https://dashboard.render.com
2. Create a new Blueprint project pointing to this GitHub repo
3. Set these environment variables:
   - `GEMINI_API_KEY` — your Google Gemini API key
   - `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_REDIRECT_URI` — for login (or set `VITE_AUTH_DEV_BYPASS=true` to skip auth)

4. Click Deploy — the build script (`build.sh`) handles everything:
   - Installs Python + Node deps
   - Builds the Vite frontend
   - Fetches data from SODA API and seeds the SQLite graph
   - Starts the combined server on `$PORT` (provided by Render)

---

## API Reference

### Investigation Endpoints

**Stream investigation results in real-time**:
```bash
curl "http://localhost:8000/api/investigate?q=Investigate+Recology" \
  -H "Accept: text/event-stream"
```

Returns SSE stream of AgentStep JSON objects:
```json
{"id": "1", "type": "search", "details": "Found entity 'Recology Inc'..."}
{"id": "2", "type": "traverse", "details": "Explored 42 connections..."}
{"id": "3", "type": "findings", "details": "5 potential pay-to-play indicators..."}
```

### Investigation Storage

**List all saved investigations**:
```bash
curl http://localhost:8000/api/investigations
```

**Save an investigation**:
```bash
curl -X POST http://localhost:8000/api/investigations \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "recology", "findings": "...", "verdict": "suspicious"}'
```

**Publish a finding** (mark as ready for journalist):
```bash
curl -X PATCH http://localhost:8000/api/investigations/recology \
  -H "Content-Type: application/json" \
  -d '{"published": true}'
```

### Anonymous Tips

**Submit a tip** (returns one-time retrieval token):
```bash
curl -X POST http://localhost:8000/api/tips \
  -H "Content-Type: application/json" \
  -d '{"entity_name": "Shell Corp Inc", "allegation": "...", "evidence_url": "..."}'
```

Response:
```json
{"token": "abc123def456..."}
```

**Retrieve a tip** (token is burned after retrieval):
```bash
curl http://localhost:8000/api/tips/abc123def456...
```

### Health & Metadata

```bash
curl http://localhost:8000/api/health
# → {"status": "healthy"}

curl http://localhost:8000/api/tips
# (GET /api/tips returns "Method Not Allowed" — only POST and token-specific GETs work)
```

---

## Agent Function Definitions

The investigation agent has access to these tools (via Gemini function calling):

### Core Graph Queries

| Function | Purpose | Example |
|----------|---------|---------|
| `search_entity(name, entity_type)` | Fuzzy search for entities in the graph | `search_entity("Recology", "company")` |
| `get_entity_details(entity_id)` | Retrieve full metadata for an entity | `get_entity_details("recology")` |
| `get_edges_for_entity(entity_id, relationship_type)` | Get all edges of a specific type | `get_edges_for_entity("recology", "CONTRACTED_WITH")` |
| `traverse_connections(entity_id, hops, direction)` | BFS traversal (forward/backward/bidirectional) | `traverse_connections("recology", hops=2, "bidirectional")` |
| `aggregate_query(relationship_type, limit, sort_by)` | Find top entities by metric | `aggregate_query("CONTRACTED_WITH", limit=10, sort_by="total_value")` |

### Campaign Finance & Investigations

| Function | Purpose |
|----------|---------|
| `check_campaign_finance(entity_name)` | Find donations from/to entity |
| `file_investigation(entity_id, findings_summary)` | Persist investigation to DB |
| `check_prior_investigations(entity_id_or_keyword)` | Search saved investigations |
| `publish_finding(investigation_id)` | Mark investigation as published for journalist follow-up |

### Pattern Detection

| Function | Purpose |
|----------|---------|
| `detect_patterns(entity_id)` | Run heuristics for corruption red flags |
| `collect_airbyte_evidence(entity_id)` | Fetch additional context from Airbyte enrichment API (if available) |

---

## Entity Types & Relationships

### Entities

- **person**: Individual (business owner, city official, donor)
- **company**: Vendor, contractor, shell company
- **department**: City department (e.g., "Department of Public Works")
- **contract**: Specific city procurement
- **campaign**: Campaign finance record
- **address**: Physical location

### Relationship Types

| Type | Direction | Meaning |
|------|-----------|---------|
| `CONTRACTED_WITH` | company → department | Company was awarded contracts by this city department |
| `AWARDED_BY` | contract → department | Contract was awarded by this department |
| `DONATED_TO` | person/company → recipient | Made campaign contribution |
| `OFFICER_OF` | person → company | Officer/director/owner of company |
| `REGISTERED_AT` | company → address | Business registered at this address |
| `WORKS_FOR` | person → department | Employee of city agency |

---

## Configuration

### Environment Variables

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `GEMINI_API_KEY` | ✅ Yes | Google Gemini API key for the investigation agent |
| `GOOGLE_API_KEY` | ✅ (alt) | Alternative to GEMINI_API_KEY |
| `TURSO_DATABASE_URL` | Optional | LibSQL cloud database (defaults to local SQLite) |
| `TURSO_AUTH_TOKEN` | Optional | Auth token for LibSQL |
| `VITE_AUTH0_DOMAIN` | Optional | Auth0 tenant for login |
| `VITE_AUTH0_CLIENT_ID` | Optional | Auth0 SPA app ID |
| `VITE_AUTH0_REDIRECT_URI` | Optional | Auth0 callback URL |
| `VITE_AUTH0_AUDIENCE` | Optional | Auth0 API identifier |
| `VITE_AUTH_DEV_BYPASS` | Optional | Set to `true` to skip Auth0 entirely (dev only) |
| `TRUEFOUNDRY_BASE_URL` | Optional | TrueFoundry AI Gateway URL for LLM routing |
| `TRUEFOUNDRY_API_KEY` | Optional | TrueFoundry API key |
| `OVERMIND_API_KEY` | Optional | Overmind tracing for evaluation + optimization |
| `SODA_APP_TOKEN` | Optional | SODA API concurrency token (unauthenticated requests work too) |

### File Structure

```
agent/
  investigator.py        # Gemini agent with function calling
  server.py             # SSE HTTP server
  graph_queries.py      # All graph functions + investigation DB
  patterns.py           # Corruption detection heuristics
  step_emitter.py       # SSE event formatting
  airbyte_enrichment.py # Optional Airbyte context
  truefoundry_backend.py # Optional TrueFoundry routing

homepage/
  src/
    components/         # Reusable UI panels:
      GraphPanel.ts     #   - Interactive entity graph (force-directed)
      GlobePanel.ts     #   - Globe visualization of contract locations
      NarrativePanel.ts #   - Rich-text investigation briefing
      FindingsPanel.ts  #   - Structured findings with severity
      EntitiesPanel.ts  #   - Entity search/filter
      SearchPanel.ts    #   - Investigation query input
      TipsPanel.ts      #   - Tip submission form
  api/
    investigate.js      # Proxies to backend /api/investigate
    publish.js          # Proxies to backend /api/*/publish
    tips.js             # Proxies to backend /api/tips

pipeline/
  run_pipeline.py       # Main ETL orchestrator
  soda_source.py        # SODA API connectors
  entity_extraction.py  # Entity matching + deduplication
  aerospike_loader.py   # (Optional) Graph load to Aerospike

data/
  contracts.json        # Pre-seeded SF contracts (150MB+, gitignored)
  campaign_finance.json # Pre-seeded SF donations
  businesses.json       # Pre-seeded SF business registrations

test_e2e.py            # End-to-end API test suite
render.yaml            # Render Blueprint (deployment config)
build.sh               # Build script for Render
```

---

## Testing

**Run the full E2E test suite** (20 tests covering graph queries, API endpoints, and agent flow):

```bash
# Against local server (http://localhost:8000)
python test_e2e.py

# Against live Render deployment
GEMINI_API_KEY=your-key python test_e2e.py --backend-url https://commons-ovyq.onrender.com
```

Test coverage:
- ✅ Health check + static file serving
- ✅ Entity search (exact + fuzzy matching)
- ✅ Graph traversal (BFS with depth limits)
- ✅ Campaign finance lookups
- ✅ Pattern detection heuristics
- ✅ Investigation storage + retrieval
- ✅ Finding publication
- ✅ Anonymous tip submission (token generation + burning)
- ✅ SSE streaming (integration test)
- ✅ CORS preflight handling

---

## Development Workflow

### Adding a New Graph Tool

1. Implement the function in [`agent/graph_queries.py`](agent/graph_queries.py):
   ```python
   def my_new_query(param1: str, param2: int) -> list[dict]:
       """Tool description for Gemini."""
       # Implementation
       return results
   ```

2. Add a tool declaration in [`agent/investigator.py`](agent/investigator.py) `TOOL_DECLARATIONS` list:
   ```python
   {
       "name": "my_new_query",
       "description": "What this tool does",
       "parameters": {
           "type": "object",
           "properties": {
               "param1": {"type": "string"},
               "param2": {"type": "integer"}
           },
           "required": ["param1", "param2"]
       }
   }
   ```

3. Add dispatch in `TOOL_DISPATCH` dict:
   ```python
   "my_new_query": lambda args: graph_queries.my_new_query(
       args["param1"], 
       args["param2"]
   )
   ```

4. Test with the agent:
   ```bash
   python -m agent.server --port 8000
   curl "http://localhost:8000/api/investigate?q=Use+my_new_query+on+..."
   ```

### Updating the Frontend

- Edit components in `homepage/src/components/`
- Vite hot-reloads on save during dev
- Build for production: `cd homepage && npm run build` → outputs to `homepage/dist/`

### Deploying to Render

Push to GitHub → Render auto-deploys from the Blueprint config. To force redeploy:
```bash
cd .render
render deploy --service-id srv-...
```

Or go to https://dashboard.render.com and click "Manual Deploy".

---

## Limitations & Future Work

### Current Limitations

- **SQLite only**: Knowledge graph is ~500MB SQLite file in memory. For 10M+ entities, use Turso/LibSQL or Aerospike
- **SODA API throttling**: Rate-limited during pipeline run (~100 requests/min). Can take 2-3 hours to build full graph from scratch
- **Basic auth**: No fine-grained RBAC yet. Auth0 present but not enforced. All investigations visible to all users
- **No full-text search**: Entity search uses simple substring matching + fuzzy name comparison (no ElasticSearch)
- **No persistent tips DB**: Tips are stored in memory + one-time tokens are SHA-256 hashes (not synced across server instances)

### Roadmap

- **Graph database**: Migrate from SQLite to **Aerospike** (key-value graph) for 10M+ entity scale
- **Real-time sync**: Stream data from SODA API incrementally instead of full nightly pipeline
- **RBAC + audit log**: Track who investigated what entity, add reviewer workflows
- **Journalist dashboard**: Published findings feed, tip status tracking, collaboration features
- **Overmind integration**: Automatically evaluate quality of findings + refine agent prompts
- **Browser extension**: One-click investigation of any SF vendor from city contracts web portal
- **Mobile app**: React Native version for field investigators

---

## Credits & Acknowledgments

Commons was built at the AWS Deep Agents Hackathon using:
- **Google Gemini Flash 2.0** for the investigation agent with function calling
- **SODA API** for SF government open data
- **Preact** for the lightweight UI framework
- **Render** for free-tier Python hosting
- **Auth0** for authentication
- **Airbyte** for data connectors (optional enrichment)
- **Overmind SDK** for LLM observability (optional)

---

## License

MIT License — See LICENSE file

---

## Contact

**Have questions, issues, or want to contribute?**
- File an issue on GitHub
- Email: investigative-intelligence@commons.app (placeholder)

**For journalism partnerships or data inquiries:**
- Visit: https://commons.app (coming soon)

---

## Appendix: Glossary

- **Pay-to-play**: When a donation to a politician is followed by that politician's department awarding contracts to the donor's company
- **Shell company**: A newly-formed company with minimal operations, often used to obscure ownership
- **Entity linking**: Process of matching multiple names (e.g., "Recology Inc", "Recology", "Recology, Inc.") to a single canonical entity in the graph
- **SODA API**: Socrata Open Data API — standard platform used by 100+ city/county/state governments in the US
- **Function calling**: LLM capability where the model decides which functions to call and in what order (vs. hardcoded flows)
- **SSE (Server-Sent Events)**: HTTP protocol for pushing real-time updates to browsers (simpler than WebSockets)
- **Aerospike**: High-performance key-value database optimized for real-time analytics on billions of records
