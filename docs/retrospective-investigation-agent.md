# Building an AI Investigation Agent with Gemini Flash Function Calling

**Project:** Commons — Investigative Journalism Platform  
**Track:** Person 2 — Investigation Intelligence Agent  
**Stack:** Python 3.10, Google Gemini Flash (gemini-flash-latest → gemini-3-flash), SQLite graph database  
**Date:** 2025

---

## TL;DR

We built an autonomous investigation agent that traverses a knowledge graph of 186K+ entities and 245K+ edges from San Francisco government open data. The agent uses Gemini Flash's native function calling to autonomously decide which graph queries to run, detect corruption patterns, and produce structured investigation briefings. The hardest part wasn't the graph queries or the LLM integration — it was getting Gemini 3 Flash's **thought signatures** working properly with function calling.

---

## The Problem

Investigative journalists spend weeks manually cross-referencing public records to find patterns: which companies donate to politicians who then award them contracts? Which addresses house suspiciously many shell companies? We wanted to build an agent that could do this autonomously — give it a company or person name, and it produces an investigation briefing with evidence chains.

---

## Architecture

```
User Query ("Investigate Recology")
    │
    ▼
┌───────────────────────┐
│  Gemini Flash Agent   │  ← System prompt with investigation methodology
│  (agentic tool loop)  │
└───────┬───────────────┘
        │ function_call / function_response
        ▼
┌───────────────────────┐
│  Tool Dispatch Layer  │  ← 6 tools: search, traverse, details, edges, patterns, aggregate
└───────┬───────────────┘
        │ SQL queries
        ▼
┌───────────────────────┐
│  SQLite Graph DB      │  ← 186K entities, 245K edges from SF SODA API
│  (entities + edges)   │
└───────────────────────┘
```

The key insight: **let the LLM decide the investigation strategy**. Instead of hardcoding "first search, then traverse, then check patterns," we give Gemini a set of tools and a system prompt describing investigation methodology. The model autonomously decides which tools to call and in what order based on what it finds.

---

## Step 1: The Graph Query Layer

The graph lives in SQLite with two tables:

```sql
-- Every person, company, department, contract, campaign, or address
CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,  -- e.g. "company:recology_san_francisco_558a43aa"
    type TEXT,                    -- person, company, department, contract, campaign, address
    name TEXT,
    aliases TEXT,                 -- JSON array of name variants
    properties TEXT,              -- JSON blob of dataset-specific fields
    sources TEXT,                 -- JSON array of source datasets
    first_seen TEXT,
    last_updated TEXT,
    flagged TEXT                  -- JSON array of investigation flags
);

-- Relationships between entities
CREATE TABLE edges (
    edge_id TEXT PRIMARY KEY,
    source_entity TEXT,
    target_entity TEXT,
    relationship TEXT,            -- CONTRACTED_WITH, AWARDED_BY, DONATED_TO, OFFICER_OF, REGISTERED_AT
    properties TEXT,              -- JSON blob
    source_dataset TEXT,
    confidence REAL
);
```

We built 5 query functions that map 1:1 to Gemini function declarations:

### `search_entity` — Fuzzy Name Matching

The most important tool. Journalists don't know exact entity IDs — they know names like "Recology" or "YMCA." We use SQL LIKE for initial filtering, then `thefuzz` for quality ranking:

```python
def search_entity(name: str, entity_type: str = None, limit: int = 10) -> list[dict]:
    """Fuzzy search for entities by name, ranked by match quality."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # SQL LIKE for fast initial filtering (catches partial matches)
    like_pattern = f"%{name}%"
    query = "SELECT entity_id, type, name, properties, sources FROM entities WHERE name LIKE ?"
    params = [like_pattern]
    
    if entity_type:
        query += " AND type = ?"
        params.append(entity_type)
    
    query += " LIMIT 200"  # get candidates, then re-rank
    rows = cursor.execute(query, params).fetchall()
    
    # Re-rank using fuzzy string matching for quality scores
    results = []
    for row in rows:
        score = fuzz.token_sort_ratio(name.lower(), row[2].lower())
        results.append({
            "entity_id": row[0],
            "type": row[1],
            "name": row[2],
            "score": score,
            # ... properties, sources
        })
    
    # Sort by fuzzy match score descending, return top N
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
```

**Why `token_sort_ratio`?** Government records are messy. "RECOLOGY SAN FRANCISCO" should match "Recology San Francisco" — `token_sort_ratio` normalizes case and word order for robust matching.

### `traverse_connections` — Multi-Hop BFS

The workhorse for discovering hidden networks. Given a starting entity, it does breadth-first traversal through the graph:

```python
def traverse_connections(entity_id: str, max_hops: int = 2, relationship_filter: str = None):
    """BFS traversal from a starting entity, discovering connected entities within N hops."""
    visited_entities = set()
    visited_edges = set()
    queue = deque([(entity_id, 0)])  # (entity_id, depth)
    
    while queue:
        current_id, depth = queue.popleft()
        if current_id in visited_entities or depth > max_hops:
            continue
        visited_entities.add(current_id)
        
        # Find all edges where this entity is source OR target (bidirectional)
        edges = cursor.execute(
            "SELECT * FROM edges WHERE source_entity = ? OR target_entity = ?",
            (current_id, current_id)
        ).fetchall()
        
        for edge in edges:
            # ... filter by relationship type if specified
            neighbor = edge.target if edge.source == current_id else edge.source
            if neighbor not in visited_entities:
                queue.append((neighbor, depth + 1))
    
    return {"entities": [...], "edges": [...], "summary": {...}}
```

**Key safety cap:** We limit to 200 entities and 500 edges to prevent the LLM context from exploding on highly-connected nodes like "City Administrator" (which connects to thousands of contracts).

### Other Tools

- **`get_entity_details`** — Full record lookup by entity_id
- **`get_edges_for_entity`** — Filtered edge query (e.g., "show me only DONATED_TO edges for Recology")
- **`aggregate_query`** — GROUP BY/COUNT for "who has the most contracts?" type questions

---

## Step 2: Corruption Pattern Detection

Six pattern checkers run against any entity and return severity-ranked findings:

```python
def detect_patterns(entity_id: str) -> list[dict]:
    """Run all corruption pattern checks on an entity."""
    patterns = []
    patterns.extend(_check_contract_concentration(entity_id, conn))
    patterns.extend(_check_shared_address(entity_id, conn))
    patterns.extend(_check_pay_to_play(entity_id, conn))
    patterns.extend(_check_shell_company(entity_id, conn))
    patterns.extend(_check_donor_contractor_overlap(entity_id, conn))
    patterns.extend(_check_department_vendor_concentration(entity_id, conn))
    
    # Sort by severity: CRITICAL > HIGH > MEDIUM > LOW
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    patterns.sort(key=lambda p: severity_order.get(p["severity"], 99))
    return patterns
```

The most interesting pattern is **contract concentration** — flagging when a single company has an outsized number of contracts from one department:

```python
def _check_contract_concentration(entity_id, conn):
    """Flag company if it has 5+ contracts from the same department."""
    # Find all contracts this company has
    contracts = conn.execute("""
        SELECT e2.source_entity, e2.target_entity, e3.name as dept_name
        FROM edges e1
        JOIN edges e2 ON e1.target_entity = e2.source_entity  
        JOIN entities e3 ON e2.target_entity = e3.entity_id
        WHERE e1.source_entity = ? 
        AND e1.relationship = 'CONTRACTED_WITH'
        AND e2.relationship = 'AWARDED_BY'
    """, (entity_id,)).fetchall()
    
    # Group by department and flag concentrations
    dept_counts = Counter(row[2] for row in contracts)
    for dept, count in dept_counts.items():
        if count >= 5:
            severity = "HIGH" if count >= 10 else "MEDIUM"
            patterns.append({
                "pattern_type": "CONTRACT_CONCENTRATION",
                "severity": severity,
                "detail": f"Company has {count} contracts from {dept}...",
                "confidence": min(0.9, 0.5 + count * 0.04),
            })
```

When we tested this against the YMCA of SF, it flagged:
- **HIGH**: 26 contracts from HSA Human Services Agency
- **HIGH**: 84 contracts from MYR Mayor
- **HIGH**: 64 contracts from CHF Children/Youth/Families

---

## Step 3: The Gemini Agent Loop — Where Things Got Interesting

The agent loop is conceptually simple: send the user's query to Gemini, check if it returns function calls, execute them, send results back, repeat until the model produces a text response.

```python
def investigate(query: str, verbose: bool = False, max_turns: int = 15) -> str:
    client = genai.Client(api_key=_API_KEY)
    
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=query)])
    ]
    
    for turn in range(max_turns):
        response = _generate_with_retry(client, contents)
        candidate = response.candidates[0]
        
        function_calls = [p for p in candidate.content.parts if p.function_call]
        
        if not function_calls:
            # Model is done — return its text response
            return "\n".join(p.text for p in candidate.content.parts if p.text)
        
        # Preserve the full model response (critical for thought signatures!)
        contents.append(candidate.content)
        
        # Execute each function call
        function_responses = []
        for part in function_calls:
            result = _call_tool(part.function_call.name, dict(part.function_call.args))
            function_responses.append(
                types.Part.from_function_response(
                    name=part.function_call.name,
                    response={"result": result},
                )
            )
        
        # Send results back as a "user" turn
        contents.append(types.Content(role="user", parts=function_responses))
```

### The Thought Signature Bug — Our Biggest Challenge

When we first ran this with `gemini-flash-latest`, the initial tool call succeeded but the **second** `generate_content` call failed with:

```
400 INVALID_ARGUMENT: Function call is missing a thought_signature in functionCall parts.
```

**What happened:** `gemini-flash-latest` resolves to Gemini 3 Flash (not 2.0 or 2.5). Gemini 3 models are "thinking" models that include encrypted `thoughtSignature` fields in their function call responses. These signatures represent the model's internal reasoning chain and **must** be preserved when sending conversation history back.

The fix was embarrassingly simple: **upgrade the SDK**.

```bash
python3 -m pip install --upgrade google-genai  # → 1.68.0
```

The official SDK (version 1.68.0+) handles thought signatures automatically when you append `candidate.content` directly to the conversation history — which we were already doing. Our older SDK version (pre-1.68) was stripping the signature during serialization.

**Lesson learned:** When using Gemini 3 Flash for function calling:
1. Always use `google-genai >= 1.68.0`
2. Always append `candidate.content` directly (never reconstruct the response manually)
3. The SDK serializes `thoughtSignature` fields transparently — you never see them in Python code

### Rate Limiting — The Second Surprise

After fixing the thought signature issue, we immediately hit a second problem: **429 RESOURCE_EXHAUSTED** errors. Gemini 3 Flash has a 2M token/minute quota, and our investigation queries burn through it fast.

Why? The agent was making 15-30+ tool calls per investigation, and each turn sends the **entire conversation history** back to the model. By turn 10, the context includes the original query + 10 model responses + 10 tool results — easily exceeding 100K tokens per request.

We added retry logic with exponential backoff:

```python
def _generate_with_retry(client, contents, max_retries=3, verbose=False):
    for attempt in range(max_retries + 1):
        try:
            return client.models.generate_content(
                model=_MODEL, contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[TOOL_DECLARATIONS],
                    temperature=0.2,
                ),
            )
        except ClientError as e:
            if e.code == 429 and attempt < max_retries:
                # Parse retry delay from error message
                match = re.search(r"retry in ([\d.]+)s", str(e), re.IGNORECASE)
                wait = float(match.group(1)) + 1 if match else 5 * (2 ** attempt)
                if verbose:
                    print(f"  ⏳ Rate limited, waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                raise
```

### The "Never Stops Talking" Problem

The third issue: the model would keep calling tools indefinitely, never producing a final text summary. It would exhaustively check every relationship type for every entity, burning through the turn budget.

We fixed this with two mechanisms:

1. **System prompt instruction:** "Be efficient with tool calls. Gather what you need in 3-5 rounds, then STOP and produce your text briefing."

2. **Turn budget nudge:** When approaching max_turns, we inject a firm user message:

```python
if turn >= max_turns - 2:
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(
            text="You are running low on tool call budget. "
            "Please synthesize your findings into a final briefing NOW. "
            "Do NOT call any more tools—just write your summary."
        )],
    ))
```

3. **Fallback summary:** If we still hit max_turns, we ask the model one final time (without tools) to summarize everything it gathered.

---

## The Result

Here's what a successful investigation looks like:

```
$ python3 -m agent.cli --verbose "Search for Recology and briefly summarize"

⏳ Investigating: Search for Recology and briefly summarize

  🔧 search_entity({"name": "Recology"})
     → [{"entity_id": "person:recology_66c7f2c5", "name": "Recology", "score": 100}, ...]
  🔧 get_entity_details({"entity_id": "company:recology_san_francisco_558a43aa"})
     → {"name": "RECOLOGY SAN FRANCISCO", "properties": {"contract_amount": "1000000"...}}
  🔧 traverse_connections({"entity_id": "company:recology_san_francisco_558a43aa"})
     → {"entities": [...], "edges": [...]}
  🔧 detect_patterns({"entity_id": "company:recology_san_francisco_558a43aa"})
     → [{"pattern_type": "CONTRACT_CONCENTRATION", "severity": "MEDIUM"...}]
  🔧 get_edges_for_entity({"entity_id": "person:recology_66c7f2c5", "relationship": "DONATED_TO"})
     → [{"target_entity": "campaign:daniel_lurie_for_mayor_2024"...}]
  ... (17 tool calls total)

### Investigation Briefing: Recology Network

#### 1. Massive Contract Concentration (Severity: MEDIUM/HIGH)
Recology subsidiaries hold over $220 million in active contracts, awarded predominantly 
by the City Administrator...

#### 2. Active Political Participation (Severity: LOW/MEDIUM)
Donations to Daniel Lurie for Mayor 2024, Aaron Peskin for Mayor 2024, and 
Yes on G (Affordable Housing)...

#### 3. Multi-Entity Corporate Structure (Severity: LOW)
Operates through 4+ distinct entities: Recology San Francisco, Sunset Scavenger, 
Golden Gate, Peninsula Services...
```

The agent autonomously:
1. Found all Recology entities via fuzzy search
2. Discovered their $220M+ in city contracts  
3. Found political donations to mayoral campaigns
4. Detected contract concentration patterns
5. Produced a structured briefing with evidence chains and journalist recommendations

---

## What I Got Right

1. **Letting the LLM drive investigation strategy** — No hardcoded flow. The model decides whether to search, traverse, or check patterns based on what it finds. This makes it adaptable to any entity type.

2. **Fuzzy matching with `thefuzz`** — Government records are wildly inconsistent ("RECOLOGY SAN FRANCISCO" vs "Recology San Francisco"). Fuzzy matching was essential.

3. **Safety caps on traversals** — Limiting BFS to 200 entities/500 edges prevents context window explosions on hub nodes.

4. **Appending `candidate.content` directly** — This one decision saved hours. If we'd manually reconstructed the model's response, we'd have lost thought signatures and debugging would have been a nightmare.

## What I Got Wrong

1. **Model name instability** — We started with `gemini-2.5-flash-preview-05-20` (404), then `gemini-flash-latest` (thought signature error with old SDK). The Gemini model naming is a minefield. `gemini-flash-latest` currently resolves to `gemini-3-flash`, which has different requirements than 2.5 or 2.0.

2. **Underestimating token consumption** — Each tool result can be 1-5KB of JSON. After 10 turns with the full conversation history being sent each time, we were burning through the 2M token/minute quota. Should have truncated tool results more aggressively.

3. **No turn budget from the start** — The model's investigative thoroughness is both a feature and a bug. It will check every relationship type for every entity unless told to stop.

## What I'd Do Differently

1. **Truncate tool results** — Instead of sending full JSON, summarize large results before adding them to the conversation context
2. **Streaming responses** — For the final briefing, stream the output so users see results immediately
3. **Parallel tool execution** — When the model requests multiple tool calls in one turn, we already execute them sequentially. Could parallelize with `asyncio`
4. **Context window management** — Implement a sliding window that drops older tool results to keep the context under control

---

## Key Takeaways for Developers

1. **Gemini 3 Flash ≠ Gemini 2.0 Flash** — The `gemini-flash-latest` endpoint now points to Gemini 3 Flash, which is a thinking model with mandatory thought signatures. Use SDK >= 1.68.0.

2. **The agentic loop pattern is simple** — The core loop is ~30 lines of Python. The complexity is in the tools and the system prompt.

3. **System prompts matter more than you think** — The difference between "investigate thoroughly" and "investigate efficiently in 3-5 tool call rounds" was the difference between a working agent and one that runs forever.

4. **Graph databases in SQLite work fine for hackathons** — You don't need Neo4j or ArangoDB. Two tables (entities + edges) with proper indexing handles 186K entities in milliseconds.

5. **Rate limiting is a real concern for agentic workflows** — Unlike chatbots that make one API call per user message, agents can make 15-30+ calls per query. Budget accordingly.
