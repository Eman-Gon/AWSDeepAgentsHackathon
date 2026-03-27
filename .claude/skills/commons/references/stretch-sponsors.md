# Stretch Sponsor Integrations

## Overmind — Pattern Learning ($651 prize pool)

Tyler's talk: "Continuous learning infrastructure for agents."

### Integration:
1. **Investigation Outcome Tracking** — journalist marks outcomes ("confirmed," "dead end"), stored as training signal
2. **Pattern Confidence Scoring** — Overmind learns pattern-outcome correlations (e.g., "RECENTLY_FORMED_LLC_CONTRACT + donation = 75% confirmed")
3. **Agent Prompt Optimization** — Overmind iterates on system prompt and tool definitions via synthetic evaluation

### Implementation:
```bash
overmind setup  # Index agent code
# Generate synthetic investigation scenarios
# Iterate on agent performance
# Show improvement in demo
```

## TrueFoundry — AI Gateway ($600 prize)

- Route all LLM calls through TrueFoundry AI Gateway
- Single API endpoint for Claude/GPT-4 with automatic fallback
- Observability dashboard: token costs per investigation step, latency per tool call
- ~30 min integration

## Kiro — Spec-Driven Development (Free prize)

- Use Kiro's spec mode to generate requirement/design/task files from this spec
- Document the process for writeup
- Use agent hooks for auto-updating docs
- Use steering docs for Python/JS conventions

## Priority Order (if time-crunched)

Cut in this order: TrueFoundry → Overmind → Kiro. Core demo needs: Airbyte → Aerospike → Agent → Auth0 → Frontend.
