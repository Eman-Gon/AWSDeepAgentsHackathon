"""
Investigation agent powered by Gemini Flash with function calling.

The agent receives a natural-language investigation query (e.g. "Investigate
Recology's city contracts"), then autonomously:
  1. Searches the knowledge graph for relevant entities
  2. Traverses connections to discover related parties
  3. Runs corruption pattern detection
  4. Synthesizes findings into a structured briefing

Uses Gemini's native function-calling to let the LLM decide which
graph tools to invoke and in what order—no hardcoded investigation flow.
"""

import json
import os
import re
import time
from typing import Any, Generator

# Overmind SDK — auto-instruments google-genai for observability.
# Traces every LLM call (latency, tokens, cost) to the Overmind dashboard.
# Must be initialized BEFORE importing the genai client.
try:
    from overmind_sdk import init as _overmind_init, get_tracer as _overmind_tracer, set_tag as _overmind_tag

    _overmind_init(
        service_name="commons-investigation-agent",
        environment=os.environ.get("OVERMIND_ENVIRONMENT", "development"),
        providers=["google"],  # instrument google-genai calls
    )
    _OVERMIND_ENABLED = True
except Exception:
    _OVERMIND_ENABLED = False

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from agent.graph_queries import (
    aggregate_query,
    get_edges_for_entity,
    get_entity_details,
    search_entity,
    traverse_connections,
)
from agent.patterns import detect_patterns
from agent.step_emitter import emit_step, emit_final_briefing

# ── Gemini client setup ───────────────────────────────────────────────────
# Requires GEMINI_API_KEY (or GOOGLE_API_KEY) in environment
_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
_MODEL = "gemini-flash-latest"

# ── System prompt that tells the LLM how to investigate ──────────────────
SYSTEM_PROMPT = """You are an investigative intelligence agent for the Commons platform.
Your job is to investigate entities (people, companies, government agencies)
by traversing a knowledge graph built from SF government public records:
  - 186K+ entities: persons, companies, departments, contracts, campaigns, addresses
  - 245K+ edges: CONTRACTED_WITH, AWARDED_BY, DONATED_TO, OFFICER_OF, REGISTERED_AT

When given an investigation query:
1. Search for the target entity using search_entity (fuzzy name matching)
2. Get full details with get_entity_details
3. Explore connections with traverse_connections (multi-hop BFS)
4. Check specific relationship types with get_edges_for_entity
5. Run detect_patterns to check for corruption red flags
6. Use aggregate_query to find the biggest players (most contracts, donations, etc.)

Investigation approach:
- Start broad (2-hop traversal), then narrow down on suspicious connections
- Always check for pay-to-play patterns (donations + contracts from same entity network)
- Look for shared addresses between multiple entities that win contracts
- Check if recently-formed companies are winning large contracts
- Cross-reference donors with contractors

IMPORTANT: Be efficient with tool calls. Gather what you need in 3-5 rounds of
tool calls, then STOP and produce your text briefing. Do NOT keep calling tools
endlessly. When you have enough evidence, write your summary.

Output format:
- Provide a structured investigation briefing with:
  - Key findings (numbered, with severity)
  - Evidence chain (which data sources and entities support each finding)
  - Confidence level for each finding
  - Recommended next steps for a journalist
- Be specific: cite entity names, dollar amounts, dates where available
- Flag genuine concerns but don't overstate—note when patterns could have innocent explanations"""


# ── Tool declarations for Gemini function calling ─────────────────────────
# These map 1:1 to the Python functions in graph_queries.py and patterns.py.
# Gemini will call them by name and we dispatch to the real implementations.

TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="search_entity",
            description=(
                "Search the knowledge graph for entities matching a name (fuzzy match). "
                "Returns up to 10 results sorted by match quality. Use this first to find "
                "the entity_id for a person, company, or department."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "name": types.Schema(type="STRING", description="Name to search for"),
                    "entity_type": types.Schema(
                        type="STRING",
                        description="Optional filter: person, company, department, contract, campaign, address",
                    ),
                    "limit": types.Schema(type="INTEGER", description="Max results (default 10)"),
                },
                required=["name"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_entity_details",
            description=(
                "Get full details for a specific entity by its exact entity_id. "
                "Returns aliases, properties, sources, and investigation flags."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "entity_id": types.Schema(type="STRING", description="Exact entity_id"),
                },
                required=["entity_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="traverse_connections",
            description=(
                "BFS traversal from a starting entity through the knowledge graph. "
                "Discovers connected entities within N hops. Returns entities, edges, and a summary."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "entity_id": types.Schema(type="STRING", description="Starting entity_id"),
                    "max_hops": types.Schema(type="INTEGER", description="Hops to traverse (1-3, default 2)"),
                    "relationship_filter": types.Schema(
                        type="STRING",
                        description="Only follow edges of this type (e.g. DONATED_TO, CONTRACTED_WITH)",
                    ),
                },
                required=["entity_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_edges_for_entity",
            description=(
                "Get all edges connected to a specific entity. "
                "Can filter by relationship type and direction (outbound/inbound/both)."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "entity_id": types.Schema(type="STRING", description="Entity to query edges for"),
                    "relationship": types.Schema(type="STRING", description="Filter by relationship type"),
                    "direction": types.Schema(
                        type="STRING", description="outbound, inbound, or both (default both)"
                    ),
                },
                required=["entity_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="detect_patterns",
            description=(
                "Run all corruption pattern checks on an entity. "
                "Returns detected red flags with severity (CRITICAL/HIGH/MEDIUM/LOW), "
                "descriptions, and confidence scores."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "entity_id": types.Schema(type="STRING", description="Entity to check for corruption patterns"),
                },
                required=["entity_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="aggregate_query",
            description=(
                "Find entities with the most connections of a given type. "
                "Useful for finding biggest contractors, most prolific donors, departments with most contracts."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "entity_type": types.Schema(type="STRING", description="Filter by entity type"),
                    "relationship": types.Schema(type="STRING", description="Filter by edge relationship"),
                    "min_edge_count": types.Schema(type="INTEGER", description="Minimum edges to include"),
                    "limit": types.Schema(type="INTEGER", description="Max results (default 20)"),
                },
            ),
        ),
    ]
)


# ── Dispatch table: maps function names to Python callables ──────────────
TOOL_DISPATCH: dict[str, Any] = {
    "search_entity": search_entity,
    "get_entity_details": get_entity_details,
    "traverse_connections": traverse_connections,
    "get_edges_for_entity": get_edges_for_entity,
    "detect_patterns": detect_patterns,
    "aggregate_query": aggregate_query,
}


def _call_tool(name: str, args: dict) -> str:
    """Execute a tool function and return JSON-serialized result."""
    func = TOOL_DISPATCH.get(name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = func(**args)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Main agent loop ──────────────────────────────────────────────────────

def _generate_with_retry(
    client: genai.Client,
    contents: list[types.Content],
    max_retries: int = 3,
    verbose: bool = False,
):
    """Call Gemini's generate_content with retry on 429 rate-limit errors.
    
    Parses the retryDelay from the error response if available, otherwise
    uses exponential backoff starting at 5 seconds.
    """
    for attempt in range(max_retries + 1):
        try:
            return client.models.generate_content(
                model=_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[TOOL_DECLARATIONS],
                    temperature=0.2,
                ),
            )
        except ClientError as e:
            if e.code == 429 and attempt < max_retries:
                # Parse retry delay from error message if present
                wait = 5 * (2 ** attempt)  # default exponential backoff
                match = re.search(r"retry in ([\d.]+)s", str(e), re.IGNORECASE)
                if match:
                    wait = float(match.group(1)) + 1  # add 1s buffer
                if verbose:
                    print(f"  ⏳ Rate limited, waiting {wait:.0f}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise


def investigate(query: str, verbose: bool = False, max_turns: int = 15) -> str:
    """
    Run an investigation using Gemini Flash with function calling.

    Args:
        query: Natural language investigation prompt
               (e.g. "Investigate Recology's city contracts")
        verbose: If True, print each tool call as it happens
        max_turns: Max number of LLM ↔ tool call rounds (default 15)

    Returns:
        The agent's final investigation briefing as a string.
    """
    # Tag this investigation in Overmind for per-query observability
    if _OVERMIND_ENABLED:
        _overmind_tag("investigation.query", query[:200])

    # Create the Gemini client
    client = genai.Client(api_key=_API_KEY)

    # Start conversation with the user's investigation query
    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)],
        )
    ]

    # Agentic loop: send to LLM → get tool calls → execute → repeat
    for turn in range(max_turns):
        # Call Gemini with tools available (with retry for rate limits)
        response = _generate_with_retry(
            client, contents, max_retries=3, verbose=verbose,
        )

        # Check if the model wants to call tools
        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Collect any function calls from the response
        function_calls = [p for p in parts if p.function_call]

        if not function_calls:
            # No more tool calls — the model is done, return its text response
            text_parts = [p.text for p in parts if p.text]
            return "\n".join(text_parts)

        # Add the model's response (with function calls) to the conversation
        contents.append(candidate.content)

        # Execute each function call and collect results
        function_responses = []
        for part in function_calls:
            fc = part.function_call
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            if verbose:
                print(f"  🔧 {tool_name}({json.dumps(tool_args, default=str)[:120]})")

            # Execute the tool
            result_json = _call_tool(tool_name, tool_args)

            if verbose:
                # Show a truncated preview of the result
                preview = result_json[:200] + "..." if len(result_json) > 200 else result_json
                print(f"     → {preview}")

            function_responses.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result_json},
                )
            )

        # Send tool results back to the model
        contents.append(
            types.Content(
                role="user",
                parts=function_responses,
            )
        )

        # Nudge the model to wrap up when approaching max turns
        if turn >= max_turns - 2:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(
                        text="You are running low on tool call budget. "
                        "Please synthesize your findings into a final briefing NOW. "
                        "Do NOT call any more tools—just write your summary."
                    )],
                )
            )

    # If we hit max turns, ask the model one final time without tools for a summary
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(
                text="Summarize all findings from the investigation above into a briefing."
            )],
        )
    )
    try:
        response = _generate_with_retry(client, contents, max_retries=3, verbose=verbose)
        candidate = response.candidates[0]
        text_parts = [p.text for p in candidate.content.parts if p.text]
        if text_parts:
            return "\n".join(text_parts)
    except Exception:
        pass
    return "Investigation reached maximum tool call rounds. Please refine your query."


def investigate_stream(
    query: str, verbose: bool = False, max_turns: int = 15
) -> Generator[dict, None, None]:
    """
    Streaming variant of investigate() that yields AgentStep dicts.

    Instead of returning a single text briefing, this generator yields
    one AgentStep dict per tool call (matching the frontend's AgentStep
    TypeScript interface), followed by a final briefing step.

    Each yielded dict has: {tool, message, nodes, edges, patterns, delay}

    This powers the SSE endpoint so the frontend can progressively
    render graph nodes, edges, narrative steps, and pattern alerts
    as the agent works through its investigation.

    Args:
        query: Natural language investigation prompt
        verbose: If True, print tool calls to stdout for debugging
        max_turns: Max LLM ↔ tool call rounds (default 15)

    Yields:
        AgentStep dicts, one per tool call + one final briefing
    """
    # Tag this investigation in Overmind for per-query observability
    if _OVERMIND_ENABLED:
        _overmind_tag("investigation.query", query[:200])

    # Create the Gemini client
    client = genai.Client(api_key=_API_KEY)

    # Start conversation with the user's investigation query
    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)],
        )
    ]

    # Agentic loop: send to LLM → get tool calls → emit steps → repeat
    for turn in range(max_turns):
        # Call Gemini with tools available (with retry for rate limits)
        response = _generate_with_retry(
            client, contents, max_retries=3, verbose=verbose,
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Collect function calls from the response
        function_calls = [p for p in parts if p.function_call]

        if not function_calls:
            # No more tool calls — model is done, yield its text as final step
            text_parts = [p.text for p in parts if p.text]
            final_text = "\n".join(text_parts) if text_parts else "Investigation complete."
            yield emit_final_briefing(final_text)
            return

        # Add the model's response to the conversation history
        contents.append(candidate.content)

        # Execute each function call, emit a step, and collect results
        function_responses = []
        for part in function_calls:
            fc = part.function_call
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            if verbose:
                print(f"  🔧 {tool_name}({json.dumps(tool_args, default=str)[:120]})")

            # Execute the tool and get raw result
            result_json = _call_tool(tool_name, tool_args)

            if verbose:
                preview = result_json[:200] + "..." if len(result_json) > 200 else result_json
                print(f"     → {preview}")

            # Emit an AgentStep for this tool call (sent to frontend via SSE)
            step = emit_step(tool_name, tool_args, result_json)
            yield step

            # Collect the function response for the conversation
            function_responses.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result_json},
                )
            )

        # Send tool results back to the model
        contents.append(
            types.Content(
                role="user",
                parts=function_responses,
            )
        )

        # Nudge the model to wrap up when approaching max turns
        if turn >= max_turns - 2:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(
                        text="You are running low on tool call budget. "
                        "Please synthesize your findings into a final briefing NOW. "
                        "Do NOT call any more tools—just write your summary."
                    )],
                )
            )

    # Hit max turns — ask for a final summary without tools
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(
                text="Summarize all findings from the investigation above into a briefing."
            )],
        )
    )
    try:
        response = _generate_with_retry(client, contents, max_retries=3, verbose=verbose)
        candidate = response.candidates[0]
        text_parts = [p.text for p in candidate.content.parts if p.text]
        if text_parts:
            yield emit_final_briefing("\n".join(text_parts))
            return
    except Exception:
        pass
    yield emit_final_briefing("Investigation reached maximum tool calls. Please refine your query.")
