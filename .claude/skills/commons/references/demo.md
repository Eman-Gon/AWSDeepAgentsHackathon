# Demo Script & Pre-Seeding Strategy

## 3-Minute Demo Script

### [0:00–0:30] The Problem
"Every year, San Francisco awards billions in government contracts. When a journalist suspects corruption — a contractor who donated to the official who awarded their contract, or a shell company formed weeks before winning a bid — they start from scratch. They don't know that another journalist already found the same registered agent, or that the same address appears in four other investigations. We built Commons."

### [0:30–1:15] The Agent in Action
Live input: "Investigate [real vendor from SF data] and their city contracts."

Show the agent working in real-time:
- "Searching knowledge graph..." → vendor node appears on graph
- "Traversing connections..." → connected entities animate in
- "Pattern detected: This LLC was formed 47 days before receiving a $1.2M contract..."
- "Cross-referencing campaign finance..."
- "Checking prior investigations..."

### [1:15–1:45] The Knowledge Graph
Zoom out on graph visualization. Show full network.
"Every node is a person, company, address, contract, or campaign contribution. This graph grows with every investigation."

### [1:45–2:15] Learning + Confidence
Show Overmind pattern confidence. "When journalists confirm a lead or mark it as dead end, the platform learns."

### [2:15–2:45] Trust Architecture
Show Auth0 flows: journalist login, M2M agent tokens, anonymous tips. "The agent can read and write findings, but cannot publish without journalist approval."

### [2:45–3:00] Close
"Commons turns investigative journalism from a solo sprint into a compounding network."

## Pre-Seeding Strategy (CRITICAL)

Do NOT rely solely on live Airbyte ingestion for demo.

1. **Hour 1:** Download all 3 datasets as JSON (see data-sources.md for curl commands)
2. **Hour 1-2:** Write bulk loader script: parse into entity nodes + edges → load into Aerospike
3. **Hour 2:** Run exploratory queries to find most compelling real connections for demo

The Airbyte pipeline should be real and working (for judges), but demo data should be warm and pre-loaded.

## Demo Warm-Up

- Pre-warm the specific demo query
- Cache the agent's traversal results
- Have backup recorded demo video ready
