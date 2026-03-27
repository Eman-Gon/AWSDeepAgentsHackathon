# Task Assignments & Timeline

## Build Window: 11:00 AM – 4:30 PM PT (5.5 hrs)

### Person 1: Data Pipeline + Airbyte

| Time | Task | Deliverable |
|---|---|---|
| 11:00–11:30 | Set up Airbyte (Cloud or Docker). Register SODA app token. | Airbyte instance running |
| 11:30–12:30 | SODA source config for 3 datasets. Entity extraction transform. | Data flowing → normalized entities |
| 12:30–1:30 | Connect Airbyte output → Aerospike loader. Bulk load pre-fetched data. | Graph seeded with real SF data |
| 1:30–2:30 | Add incremental sync. Test end-to-end pipeline. | Live pipeline working |
| 2:30–3:30 | Find best real data connections for demo. | Demo-ready data identified |
| 3:30–4:00 | Polish, submission | |

### Person 2: Knowledge Graph + Aerospike

| Time | Task | Deliverable |
|---|---|---|
| 11:00–11:45 | Aerospike setup. Create namespace, sets, secondary indexes. | Aerospike running with schema |
| 11:45–1:00 | Graph traversal (BFS, N-hop) + pattern detection. Python API. | traverse_graph() + detect_patterns() |
| 1:00–1:30 | Load sample data. Test traversal on real entities. | Graph queryable |
| 1:30–2:30 | Investigation storage. Connect to agent tools. Optimize. | All Aerospike endpoints ready |
| 2:30–3:30 | Performance optimization. Sub-second traversal. | Demo queries fast |
| 3:30–4:00 | Polish, submission | |

### Person 3: Agent + Overmind + Frontend

| Time | Task | Deliverable |
|---|---|---|
| 11:00–11:45 | Scaffold agent with tool-calling. Define tool interfaces. | Agent skeleton |
| 11:45–1:00 | Frontend: search bar + streaming narrative + graph viz. | Basic UI rendering |
| 1:00–1:30 | Integrate Overmind. | Overmind connected |
| 1:30–2:30 | Wire agent tools to Aerospike API. Test full flow. | Agent completes investigation |
| 2:30–3:30 | Polish graph viz + agent narrative. | Demo-ready frontend |
| 3:30–4:00 | Demo dry run. Record backup video. | |

### Person 4 (if available): Auth0 + DevOps + Demo

| Time | Task | Deliverable |
|---|---|---|
| 11:00–12:00 | Auth0 tenant: journalist login, M2M, anonymous tips. | Auth0 configured |
| 12:00–1:00 | Wire Auth0 into frontend + agent. | Auth integrated |
| 1:00–2:00 | Kiro setup: import spec, generate artifacts. | Kiro artifacts in repo |
| 2:00–3:00 | TrueFoundry AI Gateway. | Observability dashboard |
| 3:00–4:00 | Demo recording. DevPost. GitHub README. shipables.dev. | All submissions |

## Risk Mitigations

| Risk | Mitigation |
|---|---|
| Aerospike setup slow | SQLite fallback with same API |
| Airbyte issues | Direct SODA API calls |
| No compelling real data | One realistic synthetic entity, be transparent |
| Agent too slow for demo | Pre-warm demo query, cache traversal results |
| Auth0 blocks frontend | Mock auth first, wire Auth0 last |
| Time crunch | Cut TrueFoundry → Overmind first |

## Submission Checklist

- [ ] DevPost project page with description, screenshots, demo video
- [ ] 3-minute demo video uploaded
- [ ] Public GitHub repo with README
- [ ] Published to shipables.dev
- [ ] Kiro writeup (if targeting Kiro prize)
- [ ] All sponsor integrations documented in README
