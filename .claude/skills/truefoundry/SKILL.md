---
name: truefoundry
description: TrueFoundry AI Gateway reference for LLM routing, cost tracking, and observability. Use when routing LLM requests through TrueFoundry, adding guardrails, tracking token costs, or integrating TrueFoundry AI Gateway into the Commons hackathon project.
---

# TrueFoundry AI Gateway

## Overview

TrueFoundry AI Gateway is an OpenAI-compatible proxy that routes LLM requests to any model provider (OpenAI, Anthropic, etc.) while adding centralized access control, cost tracking, rate limiting, guardrails, and observability. It uses the standard OpenAI SDK — just change the `base_url` and `api_key`.

## Quick Start

### 1. Sign Up & Get Credentials

1. Go to [TrueFoundry](https://www.truefoundry.com/) and create an account
2. Add a provider account (OpenAI, Anthropic, etc.) with your API key
3. Add models to the provider account
4. Copy your **Gateway Base URL** and **API Key** from the playground

### 2. Python (OpenAI SDK)

```bash
pip install openai
```

```python
from openai import OpenAI

# Point the standard OpenAI client at TrueFoundry's gateway
client = OpenAI(
    base_url="https://<YOUR_TF_DOMAIN>/api/llm",  # TrueFoundry gateway URL
    api_key="<YOUR_TF_API_KEY>",                    # TrueFoundry API key
)

# Use exactly like OpenAI — model ID is provider-main/model-name
response = client.chat.completions.create(
    model="openai-main/gpt-4o",  # TrueFoundry model ID
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain machine learning in one sentence."}
    ],
    temperature=0.7,
    max_tokens=200
)

print(response.choices[0].message.content)
```

### 3. With Instructor (Structured Output)

```bash
pip install instructor openai pydantic
```

```python
import instructor
from openai import OpenAI
from pydantic import BaseModel

# Configure OpenAI client to use TrueFoundry Gateway
client = OpenAI(
    base_url="https://<YOUR_TF_DOMAIN>/api/llm",
    api_key="<YOUR_TF_API_KEY>",
)

# Patch the client with Instructor for structured output
instructor_client = instructor.from_openai(client)

class Entity(BaseModel):
    name: str
    type: str  # "person", "company", "department"
    role: str

class EntityExtraction(BaseModel):
    entities: list[Entity]
    relationships: list[str]

# Extract structured data from text
result = instructor_client.chat.completions.create(
    model="openai-main/gpt-4o",
    response_model=EntityExtraction,
    messages=[{
        "role": "user",
        "content": "Extract entities: Jane Doe, lobbyist for Acme Corp, secured a $2M contract with SF Department of Public Works."
    }]
)

for entity in result.entities:
    print(f"{entity.name} ({entity.type}): {entity.role}")
```

## Model ID Format

TrueFoundry uses `{provider}-{account}/{model}` format:

| Model ID | Provider | Model |
|----------|----------|-------|
| `openai-main/gpt-4o` | OpenAI | GPT-4o |
| `openai-main/gpt-4o-mini` | OpenAI | GPT-4o Mini |
| `anthropic-main/claude-sonnet-4-5` | Anthropic | Claude Sonnet 4.5 |
| `anthropic-main/claude-haiku-3-5` | Anthropic | Claude Haiku 3.5 |

## Gateway Features

| Feature | Description |
|---------|-------------|
| **Model Routing** | Route requests to any provider through one API |
| **Cost Tracking** | Token counts, costs per request in metrics dashboard |
| **Rate Limiting** | Per-user/per-app rate limits |
| **Guardrails** | Input/output content filtering |
| **Observability** | Latency, TTFT, inter-token latency, error rates |
| **Access Control** | One API key per user, provider keys stay server-side |
| **Fallbacks** | Auto-fallback to backup models on errors |

## Environment Variable Setup

```env
# .env
TRUEFOUNDRY_BASE_URL=https://your-domain.truefoundry.cloud/api/llm
TRUEFOUNDRY_API_KEY=tfy-...
TRUEFOUNDRY_MODEL=openai-main/gpt-4o
```

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["TRUEFOUNDRY_BASE_URL"],
    api_key=os.environ["TRUEFOUNDRY_API_KEY"],
)
```

## Commons Project Integration

For the investigation agent, route all LLM calls through TrueFoundry:

```python
from openai import OpenAI
import os

def get_llm_client():
    """Get an LLM client routed through TrueFoundry for cost tracking."""
    return OpenAI(
        base_url=os.environ.get("TRUEFOUNDRY_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.environ.get("TRUEFOUNDRY_API_KEY", os.environ.get("OPENAI_API_KEY")),
    )

def investigate(client, query, context):
    """Run an investigation query through the LLM."""
    return client.chat.completions.create(
        model=os.environ.get("TRUEFOUNDRY_MODEL", "gpt-4o"),
        messages=[
            {"role": "system", "content": "You are an investigative journalist agent analyzing SF government data."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuery: {query}"}
        ],
        temperature=0.3,
    )
```

## Critical Rules

- TrueFoundry is a **drop-in replacement** for OpenAI — only `base_url` and `api_key` change
- Model IDs use `provider-account/model` format, not native model names
- All standard OpenAI SDK features work: streaming, function calling, JSON mode
- The gateway URL path is `/api/llm` (not `/v1` like OpenAI)
- Store TrueFoundry API key in env vars, never in code
- Check the metrics dashboard for cost tracking after testing

## Resources

- `references/gateway-config.md` — Advanced gateway configuration and routing
