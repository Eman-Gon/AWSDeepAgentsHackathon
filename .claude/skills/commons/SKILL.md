---
name: commons
description: Build and develop the Commons investigative intelligence platform — an agentic system that ingests SF government public records (contracts, campaign finance, business registrations) via Airbyte, stores them in an Aerospike knowledge graph, and deploys AI agents to autonomously detect corruption patterns. Use when implementing any part of the Commons platform including data pipeline (Airbyte/SODA), knowledge graph (Aerospike), investigation agent, Auth0 trust architecture, frontend (Next.js + graph viz), or stretch integrations (Overmind, TrueFoundry, Kiro). Triggers on work related to the Deep Agents Hackathon, SF government data analysis, entity graph traversal, corruption pattern detection, or journalist investigation tools.
---

# Commons — Shared Investigation Intelligence Platform

An agentic investigation platform that ingests public records, builds a real-time entity knowledge graph, and deploys AI agents that autonomously detect corruption patterns.

**Core thesis:** Every investigation enriches the graph. After 1,000 investigations, the graph is nearly impossible to replicate.

## Architecture

```
AIRBYTE (Ingestion) → AEROSPIKE (Knowledge Graph) ↔ INVESTIGATION AGENT (LLM + Tools)
                                                      ↓
                                                   OVERMIND (Pattern Learning)
AUTH0 (Journalist Login | M2M Agent Tokens | Anonymous Tips)
FRONTEND (Search Bar | Agent Narrative | Graph Viz | Pattern Feed)
```

## Development Tracks

Building Commons involves these parallel tracks. Read the corresponding reference file before starting work on any track.

### Track 1: Data Pipeline (Airbyte + SODA API)
→ Read `references/data-sources.md` for endpoints and fields
→ Read `references/airbyte.md` for integration options

Steps:
1. Set up Airbyte (Cloud or Docker) and register SODA app token
2. Configure 3 SODA sources (contracts, campaign finance, businesses)
3. Build entity extraction transform (normalize names, deduplicate)
4. Connect output to Aerospike loader script
5. Pre-seed data by downloading JSON directly (do NOT rely solely on live ingestion for demo)

### Track 2: Knowledge Graph (Aerospike)
→ Read `references/aerospike.md` for schema, traversal, and pattern detection code

Steps:
1. Set up Aerospike (Docker or Cloud), create namespace/sets/secondary indexes
2. Implement `traverse_graph()` — BFS, N-hop traversal using secondary indexes
3. Implement `detect_patterns()` — corruption pattern checks (recently-formed LLC, donation-to-awarding-official, shared addresses)
4. Build investigation storage (create, update, outcome tracking)
5. Expose all as Python API for agent tool calls

### Track 3: Investigation Agent
→ Read `references/agent.md` for system prompt, tools, and demo flow

Steps:
1. Scaffold agent with tool-calling (pydantic-ai, langchain, or raw Claude API)
2. Define 8 tool interfaces (search_entity, traverse_connections, detect_patterns, etc.)
3. Wire tools to Aerospike API
4. Implement streaming output (WebSocket/SSE)
5. Test full investigation flow end-to-end

### Track 4: Auth0 Trust Architecture
→ Read `references/auth0.md` for all 3 auth flows

Steps:
1. Set up Auth0 tenant with roles (journalist, editor, newsroom_admin, public_reader)
2. Implement journalist login (RBAC with custom claims)
3. Implement M2M client credentials for agent (scoped: read data, write findings, NO publish)
4. Implement anonymous tip submission (one-time retrieval token, no identity stored)
5. Wire into frontend (protect routes) and agent (M2M token in headers)

### Track 5: Frontend
→ Read `references/frontend.md` for panel design and tech choices

Steps:
1. Scaffold Next.js + React app
2. Build search bar → agent narrative panel (streaming) → graph viz (vis.js)
3. **Graph visualization is the demo** — animate node discovery, color by entity type, label edges
4. Build with mock auth first, wire Auth0 last
5. Stream agent output in real-time showing tool calls

### Stretch Integrations
→ Read `references/stretch-sponsors.md` for Overmind, TrueFoundry, Kiro

Cut order (if time-crunched): TrueFoundry → Overmind → Kiro

## Tech Stack

| Layer | Technology |
|---|---|
| Agent | Python (pydantic-ai / langchain / raw Claude API) |
| Graph DB | Aerospike (`aerospike` Python client) |
| Ingestion | Airbyte + custom SODA connector |
| Auth | Auth0 (Universal Login + M2M + Actions) |
| LLM | Claude Sonnet 4 or GPT-4o |
| Frontend | Next.js + React + vis.js |
| Deployment | Vercel (frontend) + fly.io or Railway (backend) |

## Judging Alignment (20% each)

1. **Autonomy** — Agent acts on real-time data, zero human intervention post-query
2. **Idea** — Government accountability using real SF data (judges are in SF)
3. **Technical** — Multi-source pipeline → knowledge graph → multi-step agent reasoning
4. **Tool Use** — Deep Airbyte + Aerospike + Auth0 integration (not surface level)
5. **Presentation** — Live demo with dramatic graph visualization

## Critical Rules

- Pre-seed data for demo reliability (see `references/demo.md`)
- Graph viz is priority 1 for frontend
- Use Aerospike secondary indexes for graph traversal (not just key-value)
- Build real SODA connector for Airbyte (not just a generic REST connector)
- Implement 3 distinct Auth0 flows (not just a login button)
- SQLite fallback if Aerospike setup is blocked
- Demo script and task assignments in `references/demo.md` and `references/tasks.md`
