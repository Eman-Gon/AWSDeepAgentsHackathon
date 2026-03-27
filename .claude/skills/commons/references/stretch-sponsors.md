# Stretch Sponsor Integrations

## Overmind — Pattern Learning ($651 prize pool) ✅ IMPLEMENTED

Tyler's talk: "Continuous learning infrastructure for agents."

### Integration (Actual Implementation):
- **Auto-instrumentation**: `overmind-sdk` v0.1.35 wraps `google-genai` calls with zero code changes
- **Per-query tagging**: Each investigation is tagged with `investigation.query` for per-query tracing
- **OpenTelemetry traces**: All Gemini function calls (tool declarations, responses) are captured automatically
- **Setup**: `overmind_sdk.init(service_name="commons-investigation-agent", providers=["google"])`

### Files:
- `agent/investigator.py` — Overmind init at module load, `_overmind_tag()` in `investigate()` and `investigate_stream()`
- `.env` — `OVERMIND_API_KEY`, `OVERMIND_ENVIRONMENT` env vars

## TrueFoundry — AI Gateway ($600 prize) ✅ IMPLEMENTED

### Integration (Actual Implementation):
- **Alternative LLM backend**: `agent/truefoundry_backend.py` uses OpenAI SDK with function calling routed through TrueFoundry
- **Same 6 tools**: Tool declarations translated from Gemini format to OpenAI JSON Schema format
- **Auto-detection**: `agent/server.py` checks `TRUEFOUNDRY_BASE_URL` env var → switches backend automatically
- **Health endpoint**: Reports active backend name (`gemini-flash` or `truefoundry (url)`)
- **Retry logic**: Exponential backoff on 429 rate limits (same as Gemini backend)

### Files:
- `agent/truefoundry_backend.py` — OpenAI-compatible function calling backend (270 lines)
- `agent/server.py` — Auto-selects backend based on TRUEFOUNDRY_BASE_URL
- `.env` — `TRUEFOUNDRY_BASE_URL`, `TRUEFOUNDRY_API_KEY`, `TRUEFOUNDRY_MODEL` env vars

### Usage:
```bash
# Default: Gemini Flash backend
python -m agent.server

# TrueFoundry backend: set env vars
export TRUEFOUNDRY_BASE_URL=https://llm-gateway.truefoundry.com/api/llm
export TRUEFOUNDRY_API_KEY=your-key
export TRUEFOUNDRY_MODEL=openai-main/gpt-4o
python -m agent.server
# → "[commons-agent] LLM backend: truefoundry (https://...)"
```

## Kiro — Spec-Driven Development (Free prize)

- Use Kiro's spec mode to generate requirement/design/task files from this spec
- Document the process for writeup
- Use agent hooks for auto-updating docs
- Use steering docs for Python/JS conventions

## Priority Order (if time-crunched)

Cut in this order: TrueFoundry → Overmind → Kiro. Core demo needs: Airbyte → Aerospike → Agent → Auth0 → Frontend.
