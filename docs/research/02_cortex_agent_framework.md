# Research: Cortex Agent Framework
## Agent 2 Output — Comprehensive Findings

---

## What is Cortex Agent?

Cortex Agent is Snowflake's managed intelligent agent framework that orchestrates tool use (like Cortex Search, SQL execution) with LLM reasoning to answer complex questions. It is the recommended way to build RAG applications on Snowflake.

Key capabilities:
- **Tool orchestration**: Automatically decides when and how to use attached tools (search services, SQL tools)
- **Multi-tool support**: Can use multiple Cortex Search services and other tools in a single query
- **System prompt**: Configurable instructions that control agent behavior
- **Conversation support**: Multi-turn conversation with context preservation
- **Structured output**: Can return JSON-formatted responses
- **Snowflake-native**: Inherits RBAC, runs inside Snowflake

---

## Creating a Cortex Agent

### SQL Syntax

```sql
CREATE [ OR REPLACE ] CORTEX AGENT [ IF NOT EXISTS ] <name>
  MODEL = '<model_name>'
  TOOLS = ( <tool_1>, <tool_2>, ... )
  [ SYSTEM_PROMPT = '<instructions>' ]
  [ COMMENT = '<comment>' ];
```

### Parameters

| Parameter | Description | Required |
|-----------|-------------|----------|
| `MODEL` | LLM model for reasoning. Options: 'claude-3.5-sonnet', 'llama3.3-70b', 'mistral-large2', etc. | Yes |
| `TOOLS` | List of tools: Cortex Search services, Cortex Analyst semantic views, SQL exec tools | Yes |
| `SYSTEM_PROMPT` | Instructions controlling agent behavior, output format, guardrails | No (strongly recommended) |
| `COMMENT` | Description | No |

### Tool Types

1. **Cortex Search Service**: For document/knowledge retrieval
2. **Cortex Analyst (Semantic Views)**: For structured data queries via text-to-SQL
3. **Python Tool Functions**: Custom tools defined as Python UDFs

---

## Python SDK Usage

### Basic Query

```python
from snowflake.core import Root

root = Root(session)
agent = (
    root.databases["REVSEARCH"]
    .schemas["AGENTS"]
    .cortex_agents["KNOWLEDGE_ASSISTANT"]
)

response = agent.complete(
    messages=[
        {"role": "user", "content": "How do royalty clawbacks work?"}
    ]
)

print(response.message.content)
```

### Multi-Turn Conversation

```python
conversation = []

# Turn 1
conversation.append({"role": "user", "content": "How do royalty clawbacks work?"})
response = agent.complete(messages=conversation)
conversation.append({"role": "assistant", "content": response.message.content})

# Turn 2 (follow-up)
conversation.append({"role": "user", "content": "What triggers a clawback?"})
response = agent.complete(messages=conversation)
```

### REST API

```python
import requests

url = f"https://{account}.snowflakecomputing.com/api/v2/cortex/agent:run"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
payload = {
    "agent_name": "REVSEARCH.AGENTS.KNOWLEDGE_ASSISTANT",
    "messages": [
        {"role": "user", "content": "How do royalty clawbacks work?"}
    ],
    "tools": [],  # Uses tools defined on the agent
    "model": "claude-3.5-sonnet"
}

response = requests.post(url, headers=headers, json=payload)
```

---

## System Prompt Engineering for RAG

### The Critical System Prompt

The system prompt is the most important configuration for answer quality. Key elements:

```
You are an internal knowledge assistant. Your ONLY purpose is to answer employee 
questions using retrieved internal documents.

STRICT RULES:
1. ONLY use information from the retrieved documents. NEVER add your own knowledge.
2. If documents don't contain the answer, say "I could not find sufficient 
   documentation to answer this question" - NEVER guess.
3. ALWAYS cite specific document titles and sections.
4. Assign answer_strength based on retrieval quality.
5. Output valid JSON matching the required schema.

CONFIDENCE ASSESSMENT:
- strong: Direct quotes/info from 2+ documents, clear answer
- medium: Partial info from 1-2 documents, interpretation needed
- weak: Tangential info only, low confidence
- no_answer: No relevant documents found
```

### Prompt Engineering Best Practices

1. **Be explicit about what NOT to do**: "NEVER generate information not found in documents"
2. **Define the output schema**: Paste the exact JSON structure expected
3. **Give examples**: Include 1-2 example question→response pairs
4. **Set the persona**: "You are a knowledge assistant for Revelator employees"
5. **Define edge cases**: What to do when no results, ambiguous results, multiple topics
6. **Include confidence criteria**: Specific rules for each strength level

---

## Structured Output

### Forcing JSON Output

Add to system prompt:
```
ALWAYS respond with valid JSON matching this exact schema:
{
  "answer": "string - the answer text",
  "answer_strength": "strong|medium|weak|no_answer",
  "sources": [{"title": "string", "source_url": "string", "last_updated": "string"}],
  "knowledge_owner": {"needed": boolean, "primary_owner": "string", "contact": "string"},
  "related_questions": ["string", "string", "string"]
}
Do not include any text outside the JSON object.
```

### Parsing in Python

```python
import json

response = agent.complete(messages=[{"role": "user", "content": question}])

try:
    answer_data = json.loads(response.message.content)
except json.JSONDecodeError:
    # Fallback: try to extract JSON from mixed content
    import re
    json_match = re.search(r'\{.*\}', response.message.content, re.DOTALL)
    if json_match:
        answer_data = json.loads(json_match.group())
    else:
        answer_data = {
            "answer": response.message.content,
            "answer_strength": "medium",
            "sources": [],
            "knowledge_owner": {"needed": True},
            "related_questions": []
        }
```

---

## Agent + Cortex Search Integration

When a Cortex Search service is attached as a tool, the agent:

1. Receives the user question
2. Decides if it needs to search (almost always yes for knowledge questions)
3. May **reformulate** the query for better search results
4. Sends the search query to Cortex Search
5. Receives search results (chunks with metadata)
6. Synthesizes an answer from the retrieved chunks
7. Formats the response per system prompt instructions

### Key Behavior Notes:
- The agent sees the **full content** of each search result, not just titles
- The agent can make **multiple search calls** if the first doesn't return sufficient results
- The agent has access to all **attribute columns** from the search results
- The agent can **filter** search results if the system prompt instructs it to

---

## Model Comparison for Cortex Agent

| Model | Quality | Speed | Cost | Best For |
|-------|---------|-------|------|----------|
| claude-3.5-sonnet | Highest | Medium | Higher | Structured output, complex reasoning, production |
| llama3.3-70b | High | Fast | Lower | Cost-sensitive, high-volume queries |
| mistral-large2 | High | Fast | Medium | Good balance of quality and cost |
| llama3.1-405b | Very High | Slow | Higher | Complex multi-document synthesis |

**Recommendation for RevSearch**: Start with `claude-3.5-sonnet` for best structured output quality. Add `llama3.3-70b` as a cost fallback for simple questions.

---

## Production Best Practices

1. **Error handling**: Wrap agent calls in try/catch. Handle timeouts, malformed JSON, empty responses.
2. **Response validation**: Validate JSON schema before displaying. Fall back gracefully.
3. **Timeout management**: Set reasonable timeouts (30s for complex questions).
4. **Conversation length**: Limit conversation history to last 5-10 turns to avoid context overflow.
5. **Cost monitoring**: Track credit usage per query. Set alerts for unusual spikes.
6. **A/B testing**: Test different system prompts and measure answer quality.
7. **Logging**: Log every question, response, latency, and confidence for analytics.
8. **Guardrails**: Add topic restrictions to system prompt if needed.
9. **Fallback**: If agent fails, fall back to direct Cortex Search results display.
10. **Refresh monitoring**: Ensure Cortex Search TARGET_LAG is being met.

---

## Limits

- **Context window**: Depends on model (claude-3.5-sonnet: 200K tokens)
- **Rate limits**: Account-level limits apply
- **Tool limit**: Multiple tools supported per agent
- **Response size**: Model-dependent (typically 4K-8K output tokens)
- **Conversation turns**: No hard limit, but keep context manageable
