# Bridging an LLM Agent to a Real-Time Frontend with SSE Streaming

**Project:** Commons — Investigative Journalism Platform  
**Track:** Frontend-Backend Integration  
**Stack:** Python 3.10 HTTP server, Preact + TypeScript frontend, Server-Sent Events (SSE), Gemini Flash function calling  
**Date:** 2025

---

## TL;DR

We had a working Python investigation agent and a working Preact frontend that used mock data. The challenge: make the real agent's tool calls stream into the frontend in real time, so journalists watch the investigation unfold — nodes appearing on a graph, connections being drawn, corruption patterns surfacing — as the LLM works. We solved it with a Python generator that yields structured events, an SSE HTTP server, and a fetch-based stream reader. The trickiest part was the **data shape translation** between raw SQLite query results and the frontend's visualization types.

---

## The Problem

The frontend team had built an impressive dashboard: a 3D globe, a vis-network graph, a narrative timeline, and a findings panel. It all ran on hardcoded mock data — a carefully curated array of `AgentStep` objects that told a compelling story about Recology's corruption connections.

The agent team (me) had built a Gemini Flash agent that autonomously traverses a 186K-entity knowledge graph. It produced great text briefings but had no concept of "steps" or "graph nodes" — it just called tools and got JSON blobs back.

The gap: **the frontend needed structured visualization data (`GraphNode[]`, `GraphEdge[]`, `PatternAlert[]`) delivered incrementally, while the agent produced unstructured tool results delivered all at once.**

---

## Architecture

```
┌─────────────────────────┐
│  Preact Frontend        │  Consumes SSE stream, renders graph/globe/narrative
│  (Vite dev server:5173) │
└────────┬────────────────┘
         │ GET /api/investigate?q=Recology
         │ (proxied via Vite in dev)
         ▼
┌─────────────────────────┐
│  Python SSE Server      │  HTTP server, streams AgentStep events
│  (port 8000)            │
└────────┬────────────────┘
         │ yields AgentStep dicts
         ▼
┌─────────────────────────┐
│  investigate_stream()   │  Generator variant of investigate()
│  + step_emitter.py      │  Converts raw tool results → frontend types
└────────┬────────────────┘
         │ function_call / function_response
         ▼
┌─────────────────────────┐
│  Gemini Flash Agent     │  Autonomous tool-calling loop
│  + Graph Query Layer    │  6 tools over SQLite (186K entities)
└─────────────────────────┘
```

---

## Step 1: Understanding the Frontend's Data Contract

Before writing any code, I needed to understand exactly what the frontend expected. The key TypeScript interfaces:

```typescript
// Every event the frontend processes
interface AgentStep {
  tool: string;       // "search_entity", "traverse_connections", etc.
  message: string;    // Human-readable narrative text
  nodes?: GraphNode[];  // Entities to add to the graph
  edges?: GraphEdge[];  // Connections to draw
  patterns?: PatternAlert[];  // Corruption findings
  delay: number;      // Animation delay (ms)
}

// A node on the vis-network graph and 3D globe
interface GraphNode {
  id: string;        // e.g. "company:recology_558a43aa"
  label: string;     // Display name
  group: 'person' | 'company' | 'contract' | 'campaign' | 'address';
  color?: { background: string; border: string };
  size?: number;
}

// A connection line between two nodes
interface GraphEdge {
  from: string;      // Source node ID
  to: string;        // Target node ID
  label: string;     // Relationship type
}

// A corruption pattern card in the findings panel
interface PatternAlert {
  type: string;          // e.g. "CONTRACT_CONCENTRATION"
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM';
  detail: string;        // Human-readable explanation
  confidence: number;    // 0.0 - 1.0
}
```

The mock data showed the expected flow: search results → traversal with nodes/edges → pattern detection with alerts. Each step progressively builds up the visual investigation.

**Key insight:** The frontend doesn't care about raw database records. It needs pre-processed visualization data with colors, sizes, and labels already applied. The translation layer can't be a thin wrapper — it needs to understand both the database schema and the visualization requirements.

---

## Step 2: The Step Emitter — Translation Layer

This was the most important piece. Each of the 6 tools returns completely different data shapes:

- `search_entity` → list of `{entity_id, type, name, score, properties}`
- `traverse_connections` → `{entities: [...], edges: [...], summary: "string"}`
- `detect_patterns` → list of `{pattern_type, severity, detail, confidence}`
- `get_entity_details` → single entity dict
- `get_edges_for_entity` → list of edge dicts
- `aggregate_query` → list of entities with edge counts

Each needs a dedicated emitter function that:
1. Parses the JSON result (tools return JSON strings)
2. Extracts entities and converts them to `GraphNode` dicts with colors/sizes
3. Extracts relationships and converts them to `GraphEdge` dicts
4. Extracts patterns and maps severity levels
5. Generates a human-readable narrative message
6. Sets an appropriate animation delay

Here's the core pattern — the `emit_traversal` function handles the most complex case:

```python
def emit_traversal(tool_args: dict, result: Any) -> dict:
    """Convert traverse_connections results into an AgentStep."""
    entity_id = tool_args.get("entity_id", "unknown")
    max_hops = tool_args.get("max_hops", 2)
    
    if isinstance(result, str):
        result = json.loads(result)
    
    nodes = []
    edges = []
    
    if isinstance(result, dict):
        entities = result.get("entities", [])
        raw_edges = result.get("edges", [])
        
        # Convert entities to GraphNodes (limit to 20 for visual clarity)
        for ent in entities[:20]:
            if isinstance(ent, dict) and "entity_id" in ent:
                nodes.append(_make_node(
                    ent["entity_id"],
                    ent.get("name", ent["entity_id"]),
                    ent.get("type", "address"),
                ))
        
        # Convert edges to GraphEdges (limit to 30)
        for edge in raw_edges[:30]:
            if isinstance(edge, dict):
                edges.append(_make_edge(
                    edge.get("source_entity", ""),
                    edge.get("target_entity", ""),
                    edge.get("relationship", "CONNECTED"),
                ))
    
    return {
        "tool": "traverse_connections",
        "message": f"Found {len(entities)} entities and {len(raw_edges)} connections.",
        "nodes": nodes,
        "edges": edges,
        "patterns": [],
        "delay": 1200,
    }
```

The `_make_node` helper applies the same colors and sizes that the frontend uses. These constants must stay synchronized:

```python
NODE_COLORS = {
    "person":   {"background": "#3B82F6", "border": "#2563EB"},
    "company":  {"background": "#22C55E", "border": "#16A34A"},
    "contract": {"background": "#EAB308", "border": "#CA8A04"},
    "campaign": {"background": "#EF4444", "border": "#DC2626"},
    "address":  {"background": "#6B7280", "border": "#4B5563"},
}
```

### Bug: The summary field was a string, not a dict

The first test exposed a subtle bug. `traverse_connections` returns:
```python
{
    "entities": [...],
    "edges": [...],
    "summary": "Traversed 15 entities over 2 hops: 3 company(s), 5 person(s)..."
}
```

I initially wrote `summary.get("entity_count", ...)` assuming `summary` was a dict. It's actually a human-readable string. Error: `'str' object has no attribute 'get'`. Fixed by using `len(entities)` directly instead.

**Lesson:** When you're building a translation layer between two systems, never assume the shape of intermediate data. Always verify with actual test runs.

---

## Step 3: The Generator Pattern — `investigate_stream()`

The original `investigate()` function ran the full agent loop and returned a single text string. I needed a streaming variant that yields `AgentStep` events as each tool call completes.

Python generators are perfect for this:

```python
def investigate_stream(query, verbose=False, max_turns=15):
    """Yields AgentStep dicts, one per tool call."""
    client = genai.Client(api_key=_API_KEY)
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=query)])]

    for turn in range(max_turns):
        response = _generate_with_retry(client, contents)
        candidate = response.candidates[0]
        function_calls = [p for p in candidate.content.parts if p.function_call]

        if not function_calls:
            # Model is done — yield its text as the final briefing step
            text_parts = [p.text for p in candidate.content.parts if p.text]
            yield emit_final_briefing("\n".join(text_parts))
            return

        contents.append(candidate.content)
        
        function_responses = []
        for part in function_calls:
            fc = part.function_call
            result_json = _call_tool(fc.name, dict(fc.args))
            
            # THIS IS THE KEY LINE: emit a structured event for each tool call
            yield emit_step(fc.name, dict(fc.args), result_json)
            
            function_responses.append(
                types.Part.from_function_response(
                    name=fc.name, response={"result": result_json}
                )
            )
        
        contents.append(types.Content(role="user", parts=function_responses))
```

The beauty: the existing `investigate()` function stays untouched. The streaming variant shares all the same logic (retry, turn budgets, nudging) but yields events instead of accumulating text.

**Design decision:** I chose to emit one event per tool call, not one per LLM turn. A single LLM response can contain multiple function calls (Gemini supports parallel tool calling). Emitting per-tool-call gives the frontend finer-grained progress updates.

---

## Step 4: The SSE Server — No Framework Needed

For a hackathon, I chose Python's built-in `http.server` over Flask/FastAPI. No dependencies to install, no async complexity, just a simple threaded HTTP handler:

```python
class InvestigationHandler(BaseHTTPRequestHandler):
    def _handle_investigate(self, parsed):
        params = parse_qs(parsed.query)
        query = params.get("q", [None])[0]
        
        # SSE response headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        
        # Stream each AgentStep as an SSE event
        for step in investigate_stream(query, verbose=True):
            event_data = json.dumps(step, default=str)
            self.wfile.write(f"data: {event_data}\n\n".encode())
            self.wfile.flush()  # Flush immediately!
        
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
```

**Critical detail:** The `self.wfile.flush()` after each event is essential. Without it, Python buffers the output and the frontend gets nothing until the investigation is complete — defeating the entire purpose of streaming.

SSE events have a simple format: `data: <payload>\n\n`. The double newline separates events. The `[DONE]` sentinel tells the client the stream is over.

CORS is handled manually since we're not using a framework:

```python
ALLOWED_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:5174",
    "http://127.0.0.1:5173",
]

def _cors_origin(request_origin):
    if request_origin and request_origin in ALLOWED_ORIGINS:
        return request_origin  # Echo back the matching origin
    return ALLOWED_ORIGINS[0]  # Fallback (won't match, blocks the request)
```

---

## Step 5: The Frontend SSE Client

The frontend initially used `DEMO_INVESTIGATION` — a hardcoded array of mock steps. I needed to replace it with a real SSE client, but with a **fallback** to mock data when the backend is unavailable (for demos/presentations).

I chose `fetch` + `ReadableStream` over `EventSource` because:
- `EventSource` doesn't support custom headers (we'll need Authorization later)
- `EventSource` auto-reconnects, which we don't want (investigations shouldn't restart)
- `ReadableStream` gives us an `AbortSignal` for cancellation

```typescript
export async function streamInvestigation(
  query: string,
  onStep: (step: AgentStep) => void,
  signal?: AbortSignal,
): Promise<void> {
  const url = `/api/investigate?q=${encodeURIComponent(query)}`;
  const response = await fetch(url, {
    headers: { Accept: 'text/event-stream' },
    signal,
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data: ')) continue;
      const payload = line.slice(6);
      if (payload === '[DONE]') return;
      onStep(JSON.parse(payload) as AgentStep);
    }
  }
}
```

The `buffer` pattern handles chunked transfer: TCP doesn't guarantee line-aligned delivery, so we accumulate bytes until we see a complete `\n\n`-delimited event.

The App.ts integration added a clean fallback pattern:

```typescript
try {
  await streamInvestigation(query, (step) => {
    // Process each step in real-time
    this.narrativePanel.addStep(step, stepIndex++);
    if (step.nodes?.length) this.graphPanel.addNodes(step.nodes);
    if (step.edges?.length) this.graphPanel.addEdges(step.edges);
    // ... patterns, pills, etc.
  }, this.abortController.signal);
} catch (err) {
  // Backend unavailable → fall back to demo data
  console.warn('Backend unavailable, using demo data:', err);
  await this.investigateWithMockData();
}
```

---

## Step 6: The Vite Proxy — One Line to Connect Everything

During development, the frontend runs on `localhost:5173` (Vite) and the backend on `localhost:8000` (Python). Cross-origin requests would be blocked by CORS. The simplest solution: a Vite dev proxy.

```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
    },
  },
},
```

Now `fetch('/api/investigate?q=Recology')` from the browser hits Vite's proxy, which forwards to the Python server. No CORS issues, no URL configuration, no environment variables.

In production (Vercel), the `/api` routes are handled by the Vercel serverless functions, which will proxy to wherever the Python backend is deployed.

---

## What Went Wrong

### 1. The `summary` field type mismatch

As mentioned above, I assumed `traverse_connections` returned `{summary: {entity_count: N}}` but it actually returned `{summary: "Traversed 15 entities..."}`. Caught on first test.

### 2. Entity names missing from edge results

The `get_edges_for_entity` tool returns `{source_entity, target_entity, relationship}` but no entity names. My emitter tried to use `edge.get("target_name")` which returned `None`. Fixed by extracting a readable label from the entity ID itself (`"company:recology_558a43aa"` → `"recology_558a43aa"`).

### 3. Node limits matter for visualization

A 2-hop traversal can return 200+ entities. Dumping all of them into vis-network creates an unreadable graph. I added limits: 20 nodes and 30 edges per step. The frontend's hierarchical layout handles small batches well but chokes on large ones.

---

## What Went Right

### 1. The generator pattern was perfect

Python generators (`yield`) mapped naturally to SSE events. No async frameworks, no queue management, no threading. The generator pauses between yields, the HTTP handler flushes each event, and the client processes them incrementally. Simple, correct, debuggable.

### 2. Mock data fallback preserved the demo

By catching the `streamInvestigation` error and falling back to `DEMO_INVESTIGATION`, the frontend works in three modes:
- **Full stack:** Real agent with SSE streaming
- **Frontend only:** Mock data with animated delays
- **Hybrid:** Start with real data, fall back on error

### 3. Zero framework dependencies for the backend

The Python HTTP server is 180 lines with zero dependencies beyond the standard library (plus our existing `google-genai` SDK). In a hackathon, every dependency is a risk — install times, version conflicts, import errors.

---

## Running It

To run the full stack locally:

```bash
# Terminal 1: Start the Python backend
export GEMINI_API_KEY=<your-key>
python -m agent.server --port 8000

# Terminal 2: Start the frontend
cd homepage && npm install && npm run dev
```

Open `http://localhost:5173`, sign in via Auth0, and type "Recology SF" in the search bar. You'll see the graph build up in real-time as Gemini decides which tools to call.

---

## Numbers

| Metric | Value |
|--------|-------|
| New Python files | 2 (server.py, step_emitter.py) |
| New TypeScript files | 1 (investigation-stream.ts) |
| Modified files | 3 (investigator.py, App.ts, vite.config.ts) |
| Total new lines | ~900 |
| Backend dependencies added | 0 |
| Time from "let's integrate" to working SSE stream | One session |
| Events per investigation | 10-25 (depends on LLM's tool call decisions) |

---

## Key Takeaways

1. **Generators are the natural abstraction for SSE.** If your data producer is a loop that yields items, SSE is just `json.dumps(item) + "\n\n"`.

2. **Translation layers need type checking, not type assumptions.** When bridging two systems, every field access should handle the case where the value isn't what you expected.

3. **Start with mock data, then make it real.** The frontend's mock data served as a comprehensive integration test. If the real backend produces the same shape, it works.

4. **The Vite proxy is the unsung hero of full-stack dev.** One config line eliminates CORS complexity during development.

5. **Fallbacks preserve demos.** In a hackathon, the demo must work even if one component is down. The mock data fallback means the frontend always has something to show.
