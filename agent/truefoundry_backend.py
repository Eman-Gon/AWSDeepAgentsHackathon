"""
TrueFoundry AI Gateway backend for the investigation agent.

Routes LLM calls through TrueFoundry's OpenAI-compatible gateway,
giving us cost tracking, observability, rate limiting, and model
fallbacks for free. Uses the standard OpenAI SDK with function
calling — only base_url and api_key change.

When TRUEFOUNDRY_BASE_URL is set in the environment, the SSE server
automatically uses this backend instead of the default Gemini one.

TrueFoundry model IDs use {provider}-{account}/{model} format:
  - openai-main/gpt-4o
  - anthropic-main/claude-sonnet-4-5
"""

import json
import os
import time
from typing import Any, Generator

from openai import OpenAI

# Import shared components from the main investigator module
from agent.investigator import SYSTEM_PROMPT, TOOL_DISPATCH, _call_tool
from agent.step_emitter import emit_step, emit_final_briefing

# ── TrueFoundry client setup ─────────────────────────────────────────────
# Reads gateway URL and API key from environment variables.
# Falls back to direct OpenAI if TRUEFOUNDRY_BASE_URL is not set.
_TF_BASE_URL = os.environ.get("TRUEFOUNDRY_BASE_URL", "")
_TF_API_KEY = os.environ.get("TRUEFOUNDRY_API_KEY", "")
_TF_MODEL = os.environ.get("TRUEFOUNDRY_MODEL", "openai-main/gpt-4o")


# ── OpenAI-format tool definitions ───────────────────────────────────────
# Same 6 tools as the Gemini backend, translated to OpenAI's JSON Schema
# format. TrueFoundry proxies these to whatever model is configured.

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_entity",
            "description": (
                "Search the knowledge graph for entities matching a name (fuzzy match). "
                "Returns up to 10 results sorted by match quality. Use this first to find "
                "the entity_id for a person, company, or department."
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
            "description": (
                "Get full details for a specific entity by its exact entity_id. "
                "Returns aliases, properties, sources, and investigation flags."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Exact entity_id"},
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
                "Discovers connected entities within N hops. Returns entities, edges, and a summary."
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
            "description": (
                "Get all edges connected to a specific entity. "
                "Can filter by relationship type and direction (outbound/inbound/both)."
            ),
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
                "Returns detected red flags with severity (CRITICAL/HIGH/MEDIUM/LOW), "
                "descriptions, and confidence scores."
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
            "description": (
                "Find entities with the most connections of a given type. "
                "Useful for finding biggest contractors, most prolific donors, departments with most contracts."
            ),
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
]


def _create_client() -> OpenAI:
    """Create an OpenAI client pointed at TrueFoundry's gateway.
    
    If TRUEFOUNDRY_BASE_URL is set, routes through the gateway.
    Otherwise falls back to direct OpenAI API.
    """
    if _TF_BASE_URL:
        return OpenAI(base_url=_TF_BASE_URL, api_key=_TF_API_KEY)
    # Fallback to direct OpenAI (needs OPENAI_API_KEY in env)
    return OpenAI()


def investigate_stream(
    query: str, verbose: bool = False, max_turns: int = 15
) -> Generator[dict, None, None]:
    """
    Streaming investigation using OpenAI-compatible function calling
    through TrueFoundry AI Gateway.

    Yields AgentStep dicts (same format as the Gemini backend) so the
    SSE server and frontend work identically regardless of which
    LLM backend is active.

    Args:
        query: Natural language investigation prompt
        verbose: If True, print tool calls to stdout
        max_turns: Max LLM ↔ tool call rounds

    Yields:
        AgentStep dicts: {tool, message, nodes, edges, patterns, delay}
    """
    client = _create_client()

    # Build the initial conversation with system prompt + user query
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    for turn in range(max_turns):
        # Call the LLM with tools available (retry on rate limits)
        for attempt in range(4):
            try:
                response = client.chat.completions.create(
                    model=_TF_MODEL,
                    messages=messages,
                    tools=OPENAI_TOOLS,
                    temperature=0.2,
                )
                break
            except Exception as e:
                if "429" in str(e) and attempt < 3:
                    wait = 5 * (2 ** attempt)
                    if verbose:
                        print(f"  ⏳ Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

        choice = response.choices[0]
        message = choice.message

        # If the model produced tool calls, execute them
        if message.tool_calls:
            # Add the assistant's message (with tool calls) to history
            messages.append(message)

            # Execute each tool call and yield an AgentStep
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                if verbose:
                    print(f"  🔧 {tool_name}({json.dumps(tool_args, default=str)[:120]})")

                # Execute the tool (same dispatch table as Gemini backend)
                result_json = _call_tool(tool_name, tool_args)

                if verbose:
                    preview = result_json[:200] + "..." if len(result_json) > 200 else result_json
                    print(f"     → {preview}")

                # Yield an AgentStep for the frontend
                step = emit_step(tool_name, tool_args, result_json)
                yield step

                # Send tool result back to the model
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_json,
                })

        else:
            # No tool calls — model is done, yield final briefing
            final_text = message.content or "Investigation complete."
            yield emit_final_briefing(final_text)
            return

        # Nudge the model to wrap up when approaching max turns
        if turn >= max_turns - 2:
            messages.append({
                "role": "user",
                "content": (
                    "You are running low on tool call budget. "
                    "Please synthesize your findings into a final briefing NOW. "
                    "Do NOT call any more tools—just write your summary."
                ),
            })

    # Hit max turns — ask for final summary without tools
    messages.append({
        "role": "user",
        "content": "Summarize all findings from the investigation above into a briefing.",
    })
    try:
        response = client.chat.completions.create(
            model=_TF_MODEL,
            messages=messages,
            temperature=0.2,
        )
        final_text = response.choices[0].message.content or "Investigation complete."
        yield emit_final_briefing(final_text)
    except Exception:
        yield emit_final_briefing("Investigation reached maximum tool calls. Please refine your query.")
