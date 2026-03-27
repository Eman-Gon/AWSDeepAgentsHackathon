# Frontend Specification

## Design: Three Panels

1. **Search Bar** — "Investigate [entity name]"
2. **Agent Narrative** — Streaming text as agent works (show tool calls in real-time)
3. **Graph Visualization** — Force-directed graph that builds in real-time as agent discovers connections

## Graph Visualization (Priority 1)

The graph visualization IS the demo. Prioritize over everything else.

- Library: vis.js or d3-force
- Nodes colored by type:
  - Person = blue
  - Company = green
  - Contract = gold
  - Campaign = red
  - Address = gray
- Edges labeled with relationship type
- Animate node discovery as agent traverses connections
- Force-directed layout for organic graph appearance

## Agent Narrative Panel

- Streaming text output as agent processes
- Show tool calls: "Searching knowledge graph... Found 7 connected entities... Running pattern detection..."
- Highlight pattern detections with severity colors (CRITICAL=red, HIGH=orange, MEDIUM=yellow)

## Tech Stack

- React + Next.js
- WebSocket or SSE for streaming agent output
- vis.js for graph visualization

## Auth Integration

- Auth0 Universal Login protects routes
- Role-based UI: public_reader sees less than journalist sees less than newsroom_admin
- Build frontend first with mock auth, wire Auth0 last (risk mitigation)
