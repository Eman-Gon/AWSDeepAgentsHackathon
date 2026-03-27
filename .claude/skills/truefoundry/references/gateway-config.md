# TrueFoundry AI Gateway Configuration

## Gateway Architecture

```
Your App → TrueFoundry Gateway → Provider APIs
              ↓                    (OpenAI, Anthropic, etc.)
         Dashboard
         (metrics, logs, costs)
```

## Setup Steps

1. **Sign up** at truefoundry.com
2. **Add Provider Account**: Connect OpenAI/Anthropic with their API keys
3. **Add Models**: Select which models to expose through the gateway
4. **Get Gateway URL**: Copy from the playground page
5. **Get API Key**: Generate from the playground page

## Advanced Routing Configuration

### Model Fallbacks

Configure fallback models in the TrueFoundry dashboard so if the primary model fails, requests automatically route to a backup:

- Primary: `openai-main/gpt-4o`
- Fallback: `anthropic-main/claude-sonnet-4-5`

### Load Balancing

Route requests across multiple provider accounts for the same model to distribute costs and avoid rate limits.

## Integration Patterns

### Pattern 1: Direct OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://<DOMAIN>/api/llm",
    api_key="<TF_KEY>"
)
response = client.chat.completions.create(
    model="openai-main/gpt-4o",
    messages=[{"role": "user", "content": "Hello"}]
)
```

### Pattern 2: LangChain

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="openai-main/gpt-4o",
    base_url="https://<DOMAIN>/api/llm",
    api_key="<TF_KEY>"
)
response = llm.invoke("Hello")
```

### Pattern 3: Streaming

```python
stream = client.chat.completions.create(
    model="openai-main/gpt-4o",
    messages=[{"role": "user", "content": "Explain corruption patterns"}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Pattern 4: Function Calling

```python
tools = [{
    "type": "function",
    "function": {
        "name": "search_graph",
        "description": "Search the entity graph for connections",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string"},
                "max_depth": {"type": "integer", "default": 3}
            },
            "required": ["entity_name"]
        }
    }
}]

response = client.chat.completions.create(
    model="openai-main/gpt-4o",
    messages=[{"role": "user", "content": "Find connections for Jane Doe"}],
    tools=tools,
    tool_choice="auto"
)
```

## Metrics Dashboard

After routing traffic through TrueFoundry, the dashboard shows:

| Metric | Description |
|--------|-------------|
| Latency | End-to-end request latency |
| TTFT | Time to first token (streaming) |
| ITL | Inter-token latency |
| Token Count | Input + output tokens per request |
| Cost | Dollar cost per request |
| Error Rate | Failed requests by error code |
| Throughput | Requests per second |

## Environment Configuration

```env
# Production
TRUEFOUNDRY_BASE_URL=https://your-org.truefoundry.cloud/api/llm
TRUEFOUNDRY_API_KEY=tfy-prod-key

# Fallback to direct OpenAI if TrueFoundry is not configured
OPENAI_API_KEY=sk-...
```

```python
import os
from openai import OpenAI

def create_client():
    """Create LLM client with TrueFoundry fallback to direct OpenAI."""
    if os.environ.get("TRUEFOUNDRY_BASE_URL"):
        return OpenAI(
            base_url=os.environ["TRUEFOUNDRY_BASE_URL"],
            api_key=os.environ["TRUEFOUNDRY_API_KEY"]
        )
    return OpenAI()  # Falls back to OPENAI_API_KEY
```
