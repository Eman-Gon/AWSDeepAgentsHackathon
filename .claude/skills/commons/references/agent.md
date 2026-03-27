# Investigation Agent Design

## System Prompt

```
You are an investigative intelligence agent for the Commons platform.
Your job is to investigate entities (people, companies, government agencies)
by traversing a knowledge graph of public records, campaign finance data,
and business registrations.

When given an investigation query:
1. Identify the primary entity and resolve it in the knowledge graph
2. Perform a multi-hop graph traversal (up to 3 hops) to find connected entities
3. Run pattern detection checks for known corruption indicators
4. Check if any prior investigations have flagged overlapping entities
5. Check Overmind for historical pattern confidence scores
6. Synthesize findings into a structured investigation briefing
7. Recommend next steps and flag the highest-priority leads

Always cite your data sources. Never speculate beyond what the data shows.
Flag confidence levels for each finding.
```

## Agent Tools

| Tool | Description | Backend |
|---|---|---|
| `search_entity` | Find entity in graph by name (fuzzy match) | Aerospike query |
| `traverse_connections` | BFS traversal, returns connected entities within N hops | Aerospike multi-hop |
| `detect_patterns` | Run corruption pattern checks on entity | Aerospike + pattern logic |
| `check_campaign_finance` | Query campaign donations for person/company | Airbyte/SODA direct |
| `check_prior_investigations` | Search past investigations for overlapping entities | Aerospike investigations set |
| `get_pattern_confidence` | Get historical confidence on a detected pattern | Overmind API |
| `file_investigation` | Save findings to private workspace | Aerospike + Auth0 scoped |
| `publish_finding` | Publish to public graph (requires journalist role) | Aerospike + Auth0 RBAC |

## Demo Investigation Flow

```
User Input: "Investigate [Vendor X]'s city contracts"

Step 1: search_entity("Vendor X")
  → Found: entity:company:vendor_x (3 contracts totaling $2.1M)

Step 2: traverse_connections(entity:company:vendor_x, hops=2)
  → Hop 1: Person A (officer), Address B (registered), Department C (awarded by)
  → Hop 2: Campaign D (Person A donated to), Company E (same address)

Step 3: detect_patterns(entity:company:vendor_x)
  → CRITICAL: Company formed 47 days before first contract award
  → HIGH: Person A donated $4,800 to Campaign D; Campaign D connected to Supervisor
  → MEDIUM: Company E at same address received $800K from different department

Step 4: check_prior_investigations()
  → Investigation #23 (6 months ago) flagged same registered address

Step 5: get_pattern_confidence(pattern_combo)
  → "This pattern combination leads to confirmed conflicts 75% of the time"

Output: Structured investigation briefing with findings, confidence, next steps
```

## Tech Options

- Python with pydantic-ai, langchain, or raw Claude API tool-calling
- LLM: Claude Sonnet 4 or GPT-4o
- Streaming output via WebSocket or SSE to frontend
