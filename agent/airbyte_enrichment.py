"""
Optional Airbyte-powered evidence enrichment for Commons investigations.

This module uses Airbyte's GitHub agent connector in open-source mode to pull
small slices of fresh external context into an investigation run. The
integration is intentionally lightweight:
  - disabled by default unless AIRBYTE_ENABLE_GITHUB_ENRICHMENT=true
  - safe to import even when the Airbyte GitHub package is not installed
  - returns a structured status payload for the frontend timeline

Official Airbyte docs used for this integration approach:
  - Agent Engine overview: https://docs.airbyte.com/ai-agents
  - GitHub auth/config: https://docs.airbyte.com/ai-agents/connectors/github/AUTH
  - GitHub connector reference: https://docs.airbyte.com/ai-agents/connectors/github/REFERENCE
"""

from __future__ import annotations

import asyncio
import os
from typing import Any


def airbyte_enrichment_enabled() -> bool:
    return os.environ.get("AIRBYTE_ENABLE_GITHUB_ENRICHMENT", "").lower() == "true"


def collect_airbyte_evidence(entity_name: str, query: str) -> dict[str, Any] | None:
    """Return optional evidence from Airbyte's GitHub connector.

    The function is deliberately defensive so the investigation flow keeps
    working even when Airbyte is not configured or the connector package has
    not been installed yet.
    """
    if not airbyte_enrichment_enabled():
      return None

    token = os.environ.get("GITHUB_ACCESS_TOKEN", "").strip()
    if not token:
        return {
            "status": "disabled",
            "provider": "airbyte-github",
            "message": "Airbyte GitHub enrichment is enabled, but GITHUB_ACCESS_TOKEN is missing.",
            "sources": [],
        }

    try:
        return asyncio.run(_collect_github_context(entity_name, query, token))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_collect_github_context(entity_name, query, token))
        finally:
            loop.close()
    except Exception as exc:
        return {
            "status": "error",
            "provider": "airbyte-github",
            "message": f"Airbyte GitHub enrichment failed: {exc}",
            "sources": [],
        }


async def _collect_github_context(entity_name: str, query: str, token: str) -> dict[str, Any]:
    try:
        from airbyte_agent_github import GithubConnector
        from airbyte_agent_github.models import GithubPersonalAccessTokenAuthConfig
    except ImportError:
        return {
            "status": "unavailable",
            "provider": "airbyte-github",
            "message": (
                "Airbyte GitHub connector package is not installed. "
                "Install airbyte-agent-github to enable live evidence enrichment."
            ),
            "sources": [],
        }

    connector = GithubConnector(
        auth_config=GithubPersonalAccessTokenAuthConfig(token=token)
    )

    repo_scope = os.environ.get("AIRBYTE_GITHUB_REPOSITORIES", "").strip()
    search_scope = f" repo:{repo_scope}" if repo_scope else ""
    search_phrase = entity_name.strip() or query.strip()
    github_query = f"\"{search_phrase}\"{search_scope}"

    issues_result = await connector.issues.api_search(query=github_query, limit=3)
    prs_result = await connector.pull_requests.api_search(query=github_query, limit=2)

    issue_items = _extract_items(issues_result)
    pr_items = _extract_items(prs_result)
    sources = [
        _to_source_item(item, "issue") for item in issue_items[:3]
    ] + [
        _to_source_item(item, "pull_request") for item in pr_items[:2]
    ]
    sources = [item for item in sources if item]

    if sources:
        message = (
            f"Airbyte GitHub enrichment found {len(sources)} external references for "
            f"“{search_phrase}”."
        )
        status = "connected"
    else:
        message = (
            f"Airbyte GitHub enrichment searched for “{search_phrase}”, but found no "
            "matching issues or pull requests."
        )
        status = "connected"

    return {
        "status": status,
        "provider": "airbyte-github",
        "message": message,
        "sources": sources,
        "meta": {
            "search_query": github_query,
            "repository_scope": repo_scope or "global",
        },
    }


def _extract_items(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []

    if hasattr(result, "model_dump"):
        result = result.model_dump()

    if isinstance(result, dict):
        for key in ("items", "results", "nodes", "data"):
            value = result.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]

    return []


def _to_source_item(item: dict[str, Any], kind: str) -> dict[str, Any] | None:
    title = item.get("title") or item.get("name")
    url = item.get("url") or item.get("html_url")
    repo = _extract_repo_name(item)

    if not title:
        return None

    detail_parts = []
    if repo:
        detail_parts.append(repo)
    if item.get("state"):
        detail_parts.append(str(item["state"]))

    return {
        "label": str(title),
        "system": "Airbyte GitHub",
        "kind": kind,
        "url": str(url) if url else "",
        "detail": " · ".join(detail_parts),
    }


def _extract_repo_name(item: dict[str, Any]) -> str:
    repository = item.get("repository")
    if isinstance(repository, dict):
        owner = repository.get("owner")
        owner_name = owner.get("login") if isinstance(owner, dict) else None
        repo_name = repository.get("name")
        if owner_name and repo_name:
            return f"{owner_name}/{repo_name}"
        if repo_name:
            return str(repo_name)

    repo_url = item.get("repository_url")
    if isinstance(repo_url, str) and "repos/" in repo_url:
        return repo_url.split("repos/", 1)[1]

    return ""
