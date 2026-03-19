# Research: Cortex Search Service
## Agent 1 Output — Comprehensive Findings

---

## What is Cortex Search Service?

Cortex Search Service is a fully managed, serverless search engine built into Snowflake that provides **hybrid search** — combining vector-based semantic search with keyword-based (BM25) lexical search. It is purpose-built for RAG (Retrieval Augmented Generation) applications.

Key characteristics:
- **Managed service**: No infrastructure to provision or manage
- **Hybrid search**: Combines semantic understanding (embeddings) with exact keyword matching
- **Auto-refresh**: Keeps the search index in sync with source data automatically
- **Built-in embedding**: Automatically generates embeddings using Snowflake's arctic-embed models
- **Filtering**: Supports metadata-based filtering on indexed attributes
- **Snowflake-native**: Lives inside your Snowflake account, inherits RBAC

---

## Creating a Cortex Search Service

### SQL Syntax

```sql
CREATE [ OR REPLACE ] CORTEX SEARCH SERVICE [ IF NOT EXISTS ] <name>
  ON <search_column>
  ATTRIBUTES <col1>, <col2>, ...
  WAREHOUSE = <warehouse_name>
  TARGET_LAG = '<time_period>'
  [ COMMENT = '<comment>' ]
AS (
  <source_query>
);
```

### Parameters

| Parameter | Description | Required |
|-----------|-------------|----------|
| `ON <search_column>` | The text column to search on. Must be VARCHAR/STRING type. | Yes |
| `ATTRIBUTES` | Columns returned with results AND usable for filtering. | Yes |
| `WAREHOUSE` | Warehouse used for building/refreshing the index. | Yes |
| `TARGET_LAG` | Max acceptable staleness. E.g., '1 hour', '1 day'. Controls refresh frequency. | Yes |
| `COMMENT` | Optional description. | No |
| Source Query | SELECT statement defining the data to index. Can join multiple tables. | Yes |

### Example for RevSearch

```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE REVSEARCH.SEARCH.DOCUMENT_SEARCH
  ON content
  ATTRIBUTES title, team, topic, product_area, source_system, 
             owner, backup_owner, last_updated, document_id, 
             chunk_id, source_url, status
  WAREHOUSE = REVSEARCH_SEARCH_WH
  TARGET_LAG = '1 hour'
  COMMENT = 'Hybrid search over all internal documentation chunks'
AS (
  SELECT
    content,
    title,
    team,
    topic,
    product_area,
    source_system,
    owner,
    backup_owner,
    last_updated::VARCHAR AS last_updated,
    document_id,
    chunk_id,
    source_url,
    status
  FROM REVSEARCH.CURATED.DOCUMENT_CHUNKS
  WHERE status = 'active'
    AND content IS NOT NULL
    AND LENGTH(content) > 50
);
```

---

## How Hybrid Search Works

Cortex Search combines two retrieval methods:

1. **Semantic Search (Vector)**: Uses `snowflake-arctic-embed` model to convert text into dense vector embeddings. Finds results based on meaning similarity.
2. **Lexical Search (BM25)**: Traditional keyword matching with term frequency-inverse document frequency scoring. Finds results with exact term matches.

The final score is a **fusion** of both methods, providing better recall than either alone.

### When Each Method Excels:
- **Semantic**: "How do I handle content takedown requests?" → finds "DMCA removal process" even without matching words
- **Lexical**: "UGC DSP policy" → exact term matches for specific acronyms
- **Hybrid**: Gets the best of both worlds

---

## Query API

### Python SDK (snowflake.core)

```python
from snowflake.core import Root

root = Root(session)
search_service = (
    root.databases["REVSEARCH"]
    .schemas["SEARCH"]
    .cortex_search_services["DOCUMENT_SEARCH"]
)

results = search_service.search(
    query="How do royalty clawbacks work?",
    columns=["content", "title", "source_system", "owner", "source_url", "last_updated"],
    filter={"@eq": {"status": "active"}},
    limit=5
)

for result in results.results:
    print(f"Title: {result['title']}")
    print(f"Score: {result.get('score', 'N/A')}")
    print(f"Content: {result['content'][:200]}...")
    print("---")
```

### SQL Query

```sql
SELECT SNOWFLAKE.CORTEX.SEARCH(
    'REVSEARCH.SEARCH.DOCUMENT_SEARCH',
    '{
        "query": "How do royalty clawbacks work?",
        "columns": ["content", "title", "source_system", "owner"],
        "filter": {"@eq": {"status": "active"}},
        "limit": 5
    }'
);
```

### Response Format

```json
{
  "results": [
    {
      "content": "Royalty clawbacks occur when...",
      "title": "Royalty Clawback Policy",
      "source_system": "gitbook",
      "owner": "Milan",
      "score": 0.89
    },
    ...
  ],
  "request_id": "abc-123"
}
```

---

## Filtering

### Filter Operators
- `@eq`: Exact match — `{"@eq": {"team": "Product"}}`
- `@in`: Match any in list — `{"@in": {"source_system": ["freshdesk", "gitbook"]}}`
- `@and`: Combine filters — `{"@and": [{"@eq": {"team": "Product"}}, {"@eq": {"status": "active"}}]}`
- `@or`: Either filter — `{"@or": [{"@eq": {"team": "Product"}}, {"@eq": {"team": "Support"}}]}`
- `@not`: Negate — `{"@not": {"@eq": {"status": "archived"}}}`

### Example: Filter by source and team
```python
results = search_service.search(
    query="billing escalation",
    columns=["content", "title", "owner"],
    filter={
        "@and": [
            {"@eq": {"status": "active"}},
            {"@in": {"source_system": ["freshdesk", "gitbook"]}}
        ]
    },
    limit=5
)
```

---

## TARGET_LAG and Refresh Behavior

- `TARGET_LAG = '1 hour'`: Index refreshes within 1 hour of source data changes
- `TARGET_LAG = '1 minute'`: Near-real-time (higher cost)
- `TARGET_LAG = '1 day'`: Daily refresh (lowest cost)

The service monitors the source query for changes and automatically rebuilds the index. No manual refresh needed.

**Recommendation for RevSearch**: `'1 hour'` — balances freshness with cost since documents don't change every minute.

---

## Limits and Pricing

- **Row limit**: Up to 100 million rows per search service
- **Column limit**: No hard limit on attribute columns, but keep it reasonable
- **Content column size**: No explicit max, but very large chunks may impact performance
- **Query limit**: Results capped at `limit` parameter (max recommended: 10-20 for RAG)
- **Pricing**: Credits consumed for index building/refresh (uses the specified warehouse) + per-query compute

---

## Best Practices

1. **Chunk documents before indexing**: 512-1024 tokens per chunk with 10-15% overlap
2. **Include rich metadata as ATTRIBUTES**: title, team, topic, owner — enables filtering and improves result usefulness
3. **Keep content column clean**: Strip HTML, normalize whitespace, remove boilerplate headers/footers
4. **Use TARGET_LAG wisely**: Start with '1 hour', adjust based on freshness needs
5. **Filter aggressively**: Use `status = 'active'` in both source query AND runtime filter
6. **Limit result count**: 5-10 results is optimal for RAG — more results add noise
7. **Monitor with SEARCH_SERVICE_USAGE**: Track query volume and latency
8. **Use VARCHAR for date columns in attributes**: Cast timestamps to VARCHAR for attribute use

---

## Integration with Cortex Agent

Cortex Search Service can be directly attached as a **tool** to a Cortex Agent:

```sql
CREATE CORTEX AGENT my_agent
  TOOLS = (my_search_service)
  ...
```

The agent will automatically use the search service to retrieve relevant documents when answering questions. The agent handles:
- Deciding when to search
- Formulating the search query (may reformulate the user's question)
- Processing search results into an answer
- Citing sources from the search results
