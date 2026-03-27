"""
Step emitter: converts raw agent tool call results into AgentStep dicts
that match the frontend's AgentStep TypeScript interface.

Each AgentStep contains:
  - tool: the tool name (e.g. "search_entity")
  - message: a human-readable narrative string
  - nodes: optional list of GraphNode dicts for the graph/globe visualizations
  - edges: optional list of GraphEdge dicts for connections
  - patterns: optional list of PatternAlert dicts for findings panel
  - delay: animation delay in ms (used by frontend to pace the narrative)

The frontend expects:
  GraphNode: {id, label, group, color?, font?, shape?, size?}
  GraphEdge: {from, to, label, id?}
  PatternAlert: {type, severity, detail, confidence}
"""

import json
from typing import Any

# ── Node color and size constants matching frontend config/constants.ts ──
# These must stay in sync with the frontend's NODE_COLORS and NODE_SIZES
NODE_COLORS = {
    "person":   {"background": "#3B82F6", "border": "#2563EB"},
    "company":  {"background": "#22C55E", "border": "#16A34A"},
    "contract": {"background": "#EAB308", "border": "#CA8A04"},
    "campaign": {"background": "#EF4444", "border": "#DC2626"},
    "address":  {"background": "#6B7280", "border": "#4B5563"},
    "department": {"background": "#8B5CF6", "border": "#7C3AED"},
}

NODE_SIZES = {
    "person": 25,
    "company": 25,
    "contract": 18,
    "campaign": 18,
    "address": 18,
    "department": 22,
}

# Default font style for all graph nodes
NODE_FONT = {"color": "#fff", "size": 14, "face": "Inter, system-ui, sans-serif"}


def _make_node(entity_id: str, name: str, entity_type: str) -> dict:
    """Create a GraphNode dict from an entity record.
    
    Maps entity type to the frontend's 'group' field and applies
    the matching color and size from the constants.
    """
    # Map entity types to frontend group names (address, department → closest match)
    group = entity_type if entity_type in NODE_COLORS else "address"
    return {
        "id": entity_id,
        "label": name[:40],  # truncate long names for readability in the graph
        "group": group,
        "color": NODE_COLORS.get(group, NODE_COLORS["address"]),
        "font": NODE_FONT,
        "shape": "dot",
        "size": NODE_SIZES.get(group, 18),
    }


def _make_edge(source: str, target: str, relationship: str) -> dict:
    """Create a GraphEdge dict from an edge record.
    
    The frontend expects {from, to, label} where 'from' and 'to' are
    entity_id strings that match node ids already added to the graph.
    """
    return {
        "from": source,
        "to": target,
        "label": relationship,
    }


def emit_search_results(tool_args: dict, result: Any) -> dict:
    """Convert search_entity results into an AgentStep.
    
    Shows the search query in the narrative and adds found entities
    as graph nodes so they appear on the visualization immediately.
    """
    name = tool_args.get("name", "unknown")
    
    # Parse result if it's a JSON string (from _call_tool)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = []
    
    # Build narrative message describing what was found
    if isinstance(result, list) and len(result) > 0:
        top = result[0]
        count = len(result)
        message = f'Searching for "{name}"... Found {count} match(es). Top result: {top.get("name", "?")} ({top.get("type", "?")})'
        
        # Convert each search result entity into a GraphNode
        nodes = [
            _make_node(r["entity_id"], r["name"], r["type"])
            for r in result[:5]  # limit to top 5 for visual clarity
            if "entity_id" in r and "name" in r and "type" in r
        ]
    else:
        message = f'Searching for "{name}"... No matches found.'
        nodes = []
    
    return {
        "tool": "search_entity",
        "message": message,
        "nodes": nodes,
        "edges": [],
        "patterns": [],
        "delay": 800,
    }


def emit_entity_details(tool_args: dict, result: Any) -> dict:
    """Convert get_entity_details results into an AgentStep.
    
    Shows key properties of the entity in the narrative text.
    No new nodes/edges since the entity should already be on the graph.
    """
    entity_id = tool_args.get("entity_id", "unknown")
    
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {}
    
    if isinstance(result, dict) and "name" in result:
        name = result["name"]
        etype = result.get("type", "entity")
        # Extract notable properties for the narrative
        props = result.get("properties", {})
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except json.JSONDecodeError:
                props = {}
        
        details = []
        if props.get("contract_amount"):
            details.append(f"contract value: ${props['contract_amount']}")
        if props.get("tran_amt"):
            details.append(f"donation: ${props['tran_amt']}")
        
        detail_str = " | ".join(details) if details else "Full record retrieved"
        message = f"Retrieved details for {name} ({etype}). {detail_str}"
    else:
        message = f"Could not find details for {entity_id}"
    
    return {
        "tool": "get_entity_details",
        "message": message,
        "nodes": [],
        "edges": [],
        "patterns": [],
        "delay": 600,
    }


def emit_traversal(tool_args: dict, result: Any) -> dict:
    """Convert traverse_connections results into an AgentStep.
    
    This is the most visually impactful step — it adds potentially many
    new nodes and edges to the graph, revealing the entity's network.
    """
    entity_id = tool_args.get("entity_id", "unknown")
    max_hops = tool_args.get("max_hops", 2)
    
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {}
    
    nodes = []
    edges = []
    
    if isinstance(result, dict):
        # Extract entities from traversal result
        entities = result.get("entities", [])
        raw_edges = result.get("edges", [])
        summary = result.get("summary", "")
        
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
                    edge.get("source_entity", edge.get("source", "")),
                    edge.get("target_entity", edge.get("target", "")),
                    edge.get("relationship", "CONNECTED"),
                ))
        
        # summary is a string like "Traversed 15 entities over 2 hops..."
        # Use entity/edge list lengths for the counts
        entity_count = len(entities)
        edge_count = len(raw_edges)
        message = (
            f"Traversing connections from {entity_id} ({max_hops} hops)... "
            f"Found {entity_count} entities and {edge_count} connections."
        )
    else:
        message = f"Traversing connections from {entity_id}... No results."
    
    return {
        "tool": "traverse_connections",
        "message": message,
        "nodes": nodes,
        "edges": edges,
        "patterns": [],
        "delay": 1200,
    }


def emit_edges(tool_args: dict, result: Any) -> dict:
    """Convert get_edges_for_entity results into an AgentStep.
    
    Shows specific edges (e.g., all DONATED_TO relationships) and
    adds the connected entities as nodes.
    """
    entity_id = tool_args.get("entity_id", "unknown")
    relationship = tool_args.get("relationship", "all")
    
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = []
    
    edges = []
    nodes = []
    seen_nodes = set()
    
    if isinstance(result, list):
        for edge in result[:20]:
            if isinstance(edge, dict):
                edges.append(_make_edge(
                    edge.get("source_entity", ""),
                    edge.get("target_entity", ""),
                    edge.get("relationship", "CONNECTED"),
                ))
                # Add the "other" entity as a node if we haven't seen it
                for key in ["source_entity", "target_entity"]:
                    other_id = edge.get(key, "")
                    if other_id and other_id != entity_id and other_id not in seen_nodes:
                        seen_nodes.add(other_id)
                        # Infer type from entity_id prefix (e.g. "person:john" → "person")
                        etype = other_id.split(":")[0] if ":" in other_id else "address"
                        # Use the entity_id as label since we don't have the name
                        # The prefix:suffix format gives a reasonable short label
                        label = other_id.split(":", 1)[1] if ":" in other_id else other_id
                        nodes.append(_make_node(other_id, label[:40], etype))
        
        message = f"Found {len(result)} {relationship} edges for {entity_id}."
    else:
        message = f"Querying edges for {entity_id}... No results."
    
    return {
        "tool": "get_edges_for_entity",
        "message": message,
        "nodes": nodes[:15],
        "edges": edges[:20],
        "patterns": [],
        "delay": 800,
    }


def emit_patterns(tool_args: dict, result: Any) -> dict:
    """Convert detect_patterns results into an AgentStep.
    
    This step populates the findings panel with PatternAlert cards.
    Each pattern has severity and confidence for visual prioritization.
    """
    entity_id = tool_args.get("entity_id", "unknown")
    
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = []
    
    patterns = []
    if isinstance(result, list):
        for p in result:
            if isinstance(p, dict):
                # Map severity to frontend's expected values
                severity = p.get("severity", "MEDIUM").upper()
                if severity not in ("CRITICAL", "HIGH", "MEDIUM"):
                    severity = "MEDIUM"
                
                patterns.append({
                    "type": p.get("pattern_type", "UNKNOWN_PATTERN"),
                    "severity": severity,
                    "detail": p.get("detail", "Pattern detected"),
                    "confidence": p.get("confidence", 0.5),
                })
        
        serious = sum(1 for p in patterns if p["severity"] in ("CRITICAL", "HIGH"))
        message = (
            f"Pattern analysis for {entity_id}: {len(patterns)} pattern(s) detected"
            + (f", {serious} high/critical severity." if serious else ".")
        )
    else:
        message = f"No patterns detected for {entity_id}."
    
    return {
        "tool": "detect_patterns",
        "message": message,
        "nodes": [],
        "edges": [],
        "patterns": patterns,
        "delay": 1000,
    }


def emit_aggregate(tool_args: dict, result: Any) -> dict:
    """Convert aggregate_query results into an AgentStep.
    
    Shows top entities by connection count and adds them as graph nodes.
    """
    entity_type = tool_args.get("entity_type", "all")
    relationship = tool_args.get("relationship", "all")
    
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = []
    
    nodes = []
    if isinstance(result, list):
        for r in result[:10]:
            if isinstance(r, dict) and "entity_id" in r:
                nodes.append(_make_node(
                    r["entity_id"],
                    r.get("name", r["entity_id"]),
                    r.get("type", entity_type or "company"),
                ))
        
        message = (
            f"Top {len(result)} {entity_type or 'entities'} by {relationship or 'connections'}: "
            + ", ".join(f'{r.get("name", "?")} ({r.get("edge_count", "?")})' for r in result[:5])
        )
    else:
        message = "Aggregate query returned no results."
    
    return {
        "tool": "aggregate_query",
        "message": message,
        "nodes": nodes,
        "edges": [],
        "patterns": [],
        "delay": 800,
    }


def emit_final_briefing(text: str) -> dict:
    """Create a final step with the LLM's synthesized investigation briefing.
    
    This is the last AgentStep, containing the model's narrative summary
    without any new graph data.
    """
    return {
        "tool": "briefing",
        "message": text,
        "nodes": [],
        "edges": [],
        "patterns": [],
        "delay": 0,
    }


# ── Dispatch table: maps tool names to their emitter functions ───────────
STEP_EMITTERS = {
    "search_entity": emit_search_results,
    "get_entity_details": emit_entity_details,
    "traverse_connections": emit_traversal,
    "get_edges_for_entity": emit_edges,
    "detect_patterns": emit_patterns,
    "aggregate_query": emit_aggregate,
}


def emit_step(tool_name: str, tool_args: dict, result: Any) -> dict:
    """Main entry point: convert a tool call + result into an AgentStep dict.
    
    Looks up the appropriate emitter function by tool name and delegates
    the conversion. Falls back to a generic step if the tool is unknown.
    """
    emitter = STEP_EMITTERS.get(tool_name)
    if emitter:
        return emitter(tool_args, result)
    
    # Fallback for unknown tools
    return {
        "tool": tool_name,
        "message": f"Called {tool_name} with {tool_args}",
        "nodes": [],
        "edges": [],
        "patterns": [],
        "delay": 500,
    }
