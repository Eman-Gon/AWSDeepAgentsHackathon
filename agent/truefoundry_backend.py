"""
TrueFoundry AI Gateway backend for the Commons investigation agent.

This module is a drop-in replacement for agent/investigator.py:
it exposes the same `investigate_stream()` function but routes all
LLM calls through the TrueFoundry AI Gateway instead of calling
Gemini directly.

Advantages of routing through TrueFoundry:
  - Unified observability: per-call token counts, latency, cost
  - Model fallback: if the primary model is down, TrueFoundry
    automatically retries on a backup model
  - Guardrails: input/output filtering without code changes
  - Cost attribution: tag calls by investigation query or journalist

Configuration (set in .env or Render environment):
  TRUEFOUNDRY_BASE_URL   — e.g. https://llm-gateway.truefoundry.com/api/llm
  TRUEFOUNDRY_API_KEY    — Your TrueFoundry workspace API key
  TRUEFOUNDRY_MODEL      — e.g. openai-main/gpt-4o or anthropic/claude-3-5-sonnet

TrueFoundry is OpenAI-API-compatible, so we use the standard `openai`
Python SDK with a custom `base_url` and `api_key`.  Tool calls work
identically — the only difference is the endpoint and model name.

How to activate: set the three env vars above. The server (agent/server.py)
will automatically detect TRUEFOUNDRY_BASE_URL and import investigate_stream
from this module instead of agent/investigator.py.
"""

import json
import os
import time
from typing import Generator

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI, RateLimitError

from agent.graph_queries import (
    aggregate_query,
    check_campaign_finance,
    check_prior_investigations,
    file_investigation,
    get_edges_for_entity,
    get_entity_details,
    publish_finding,
    search_entity,
    traverse_connections,
)
from agent.patterns import detect_patterns
from agent.step_emitter import emit_step, emit_final_briefing

# ── TrueFoundry gateway config ────────────────────────────────────────────
_TFY_BASE_URL = os.environ.get("TRUEFOUNDRY_BASE_URL", "")
_TFY_API_KEY  = os.environ.get("TRUEFOUNDRY_API_KEY", "")
_TFY_MODEL    = os.environ.get("TRUEFOUNDRY_MODEL", "openai-main/gpt-4o")

# TrueFoundry uses OpenAI-compatible endpoints — standard SDK, custom base_url
_client = OpenAI(base_url=_TFY_BASE_URL, api_key=_TFY_API_KEY) if _TFY_BASE_URL else None

# ── System prompt (same as Gemini backend) ────────────────────────────────
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
6. Use aggregate_query to find the biggest players

Be efficient: gather evidence in 3-5 rounds of tool calls, then STOP and write
your structured investigation briefing. Cite entity names, amounts, and dates.
Flag confidence levels. Do not overstate — note innocent explanations too."""

# ── Tool definitions in OpenAI JSON Schema format ─────────────────────────
# These map 1:1 to the Gemini tool declarations in investigator.py.
# OpenAI function calling uses "type": "function" + "function": {name, description, parameters}.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_entity",
            "description": (
                "Search the knowledge graph for entities matching a name (fuzzy match). "
                "Returns up to 10 results. Use this first to find the entity_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name to search for"},
                    "entity_type": {
                        "type": "string",
                        "description": "Optional filter: person, company, department, contract, campaign, address",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_details",
            "description": "Get full details for an entity by its exact entity_id. Returns aliases, properties, sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Exact entity_id from search_entity"},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "traverse_connections",
            "description": (
                "BFS traversal from a starting entity through the knowledge graph. "
                "Discovers connected entities within N hops."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Starting entity_id"},
                    "max_hops": {"type": "integer", "description": "Hops to traverse (1-3, default 2)"},
                    "relationship_filter": {
                        "type": "string",
                        "description": "Only follow edges of this type (e.g. DONATED_TO, CONTRACTED_WITH)",
                    },
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_edges_for_entity",
            "description": "Get all edges connected to an entity. Filter by relationship type and direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity to query edges for"},
                    "relationship": {"type": "string", "description": "Filter by relationship type"},
                    "direction": {
                        "type": "string",
                        "description": "outbound, inbound, or both (default both)",
                    },
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_patterns",
            "description": (
                "Run all corruption pattern checks on an entity. "
                "Returns red flags with severity (CRITICAL/HIGH/MEDIUM/LOW) and confidence scores."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity to check for corruption patterns"},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_query",
            "description": "Find entities with the most connections of a given type (top contractors, donors, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string", "description": "Filter by entity type"},
                    "relationship": {"type": "string", "description": "Filter by edge relationship"},
                    "min_edge_count": {"type": "integer", "description": "Minimum edges to include"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_campaign_finance",
            "description": (
                "Search campaign finance records for an entity. "
                "Returns DONATED_TO edges — who they donated to and who donated to them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {"type": "string", "description": "Name of donor or recipient"},
                    "direction": {
                        "type": "string",
                        "description": "'donor', 'recipient', or 'both' (default)",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
                "required": ["entity_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_prior_investigations",
            "description": "Search past investigations for overlapping entities or keywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Find investigations involving this entity_id"},
                    "keyword": {"type": "string", "description": "Search by keyword in title or summary"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_investigation",
            "description": "Save the current investigation and findings to the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short descriptive title"},
                    "summary": {"type": "string", "description": "Full narrative summary"},
                    "entity_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity_ids central to this investigation",
                    },
                    "findings": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Finding dicts with keys: description, severity, confidence, evidence",
                    },
                },
                "required": ["title", "summary", "entity_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "publish_finding",
            "description": "Mark a filed investigation as published.",
            "parameters": {
                "type": "object",
                "properties": {
                    "investigation_id": {"type": "string", "description": "The id from file_investigation"},
                    "public_title": {"type": "string", "description": "Optional refined public title"},
                    "public_summary": {"type": "string", "description": "Optional refined public summary"},
                },
                "required": ["investigation_id"],
            },
        },
    },
]

# ── Dispatch table (same as investigator.py) ──────────────────────────────
TOOL_DISPATCH = {
    "search_entity":           search_entity,
    "get_entity_details":      get_entity_details,
    "traverse_connections":    traverse_connections,
    "get_edges_for_entity":    get_edges_for_entity,
    "detect_patterns":         detect_patterns,
    "aggregate_query":         aggregate_query,
    "check_campaign_finance":  check_campaign_finance,
    "check_prior_investigations": check_prior_investigations,
    "file_investigation":      file_investigation,
    "publish_finding":         publish_finding,
}


def _call_tool(name: str, args: dict) -> str:
    """Execute a tool function and return JSON-serialized result."""
    func = TOOL_DISPATCH.get(name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return json.dumps(func(**args), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _chat_with_retry(messages: list, max_retries: int = 3, verbose: bool = False):
    """Call TrueFoundry gateway with exponential backoff on 429 errors."""
    for attempt in range(max_retries + 1):
        try:
            return _client.chat.completions.create(
                model=_TFY_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
        except RateLimitError:
            if attempt < max_retries:
                wait = 5 * (2 ** attempt)  # 5s, 10s, 20s
                if verbose:
                    print(f"  ⏳ TrueFoundry rate limit, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


def investigate_stream(
    query: str, verbose: bool = False, max_turns: int = 15
) -> Generator[dict, None, None]:
    """
    Streaming investigation using TrueFoundry AI Gateway.

    Yields AgentStep dicts (same interface as investigator.py's investigate_stream).
    Activated automatically by server.py when TRUEFOUNDRY_BASE_URL is set.
    """
    if not _client:
        raise RuntimeError(
            "TrueFoundry backend selected but TRUEFOUNDRY_BASE_URL is not set. "
            "Check your environment variables."
        )

    # OpenAI chat history — starts with system prompt + user query
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    for turn in range(max_turns):
        # Call the TrueFoundry gateway (with retry on rate limits)
        response = _chat_with_retry(messages, max_retries=3, verbose=verbose)
        choice = response.choices[0]
        msg = choice.message

        # If no tool calls, the model is done — emit its text as the final briefing
        if not msg.tool_calls:
            final_text = msg.content or "Investigation complete."
            yield emit_final_briefing(final_text)
            return

        # Append the assistant's response (with tool calls) to history
        messages.append(msg)

        # Execute each tool call and collect results
        tool_results = []
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            if verbose:
                print(f"  🔧 [TFY] {tool_name}({json.dumps(tool_args)[:120]})")

            result_json = _call_tool(tool_name, tool_args)

            if verbose:
                print(f"     → {result_json[:200]}")

            # Emit AgentStep for the frontend (same format as Gemini backend)
            yield emit_step(tool_name, tool_args, result_json)

            # Collect tool result for the next message
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_json,
            })

        # Append tool results to the conversation
        messages.extend(tool_results)

        # Nudge the model to wrap up when approaching the turn limit
        if turn >= max_turns - 2:
            messages.append({
                "role": "user",
                "content": (
                    "You are running low on tool call budget. "
                    "Please synthesize your findings into a final briefing NOW. "
                    "Do NOT call any more tools—just write your summary."
                ),
            })

    # Max turns reached — ask for final summary without tools
    messages.append({"role": "user", "content": "Summarize all findings into a briefing."})
    try:
        response = _client.chat.completions.create(
            model=_TFY_MODEL,
            messages=messages,
            temperature=0.2,
        )
        final_text = response.choices[0].message.content or "Investigation complete."
        yield emit_final_briefing(final_text)
    except Exception as e:
        yield emit_final_briefing(f"Investigation analysis complete (summary generation failed: {e}).")
