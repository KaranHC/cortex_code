# Research: Embedding Models & LLM Options
## Agent 3 Output — Comprehensive Findings

---

## Snowflake Embedding Models

### Available Models

| Model | Dimensions | Max Tokens | Best For | Status |
|-------|-----------|------------|----------|--------|
| `snowflake-arctic-embed-l-v2.0` | 1024 | 8192 | Long documents, high accuracy | Recommended |
| `snowflake-arctic-embed-m-v2.0` | 768 | 8192 | Balanced quality/speed | Available |
| `snowflake-arctic-embed-l-v2.0-8k` | 1024 | 8192 | Extra-long documents | Available |
| `snowflake-arctic-embed-m-v1.0` | 768 | 512 | Legacy, short text | Available |
| `e5-base-v2` | 768 | 512 | Legacy baseline | Available |
| `nv-embed-qa-4` | 1024 | 512 | Question-answer pairs | Available |
| `voyage-multilingual-2` | 1024 | 16000 | Multilingual content | Available |

### Cortex Search Internal Embedding

**Critical Finding**: Cortex Search Service manages embeddings internally. When you create a search service with `ON content`, it automatically:
1. Generates embeddings using the latest arctic-embed model
2. Builds a vector index
3. Builds a BM25 keyword index
4. Fuses results at query time

You do **NOT** need to manually call `EMBED_TEXT_1024()` when using Cortex Search Service. Only use manual embedding if you need:
- Custom similarity calculations
- Pre-computed embeddings for clustering
- Embedding-based question deduplication for FAQ analytics

### Manual Embedding Function

```sql
-- Generate embedding for a text string
SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_1024(
    'snowflake-arctic-embed-l-v2.0',
    'How do royalty clawbacks work?'
) AS embedding;

-- Use in a table
SELECT 
    question_text,
    SNOWFLAKE.CORTEX.EMBED_TEXT_1024(
        'snowflake-arctic-embed-l-v2.0',
        question_text
    ) AS question_embedding
FROM REVSEARCH.ANALYTICS.QUESTIONS;
```

### Cosine Similarity for Question Clustering

```sql
-- Find similar questions for FAQ deduplication
SELECT 
    q1.question_text AS question_1,
    q2.question_text AS question_2,
    VECTOR_COSINE_SIMILARITY(
        SNOWFLAKE.CORTEX.EMBED_TEXT_1024('snowflake-arctic-embed-l-v2.0', q1.question_text),
        SNOWFLAKE.CORTEX.EMBED_TEXT_1024('snowflake-arctic-embed-l-v2.0', q2.question_text)
    ) AS similarity
FROM REVSEARCH.ANALYTICS.QUESTIONS q1
CROSS JOIN REVSEARCH.ANALYTICS.QUESTIONS q2
WHERE q1.question_id < q2.question_id
  AND VECTOR_COSINE_SIMILARITY(...) > 0.85
ORDER BY similarity DESC;
```

---

## LLM Models via CORTEX.COMPLETE()

### Available Models

| Model | Context Window | Output Tokens | Cost (relative) | Quality | Speed |
|-------|---------------|---------------|-----------------|---------|-------|
| `claude-3.5-sonnet` | 200K | 8K | $$$ | Highest | Medium |
| `claude-3-haiku` | 200K | 4K | $ | Good | Very Fast |
| `llama3.3-70b` | 128K | 4K | $$ | High | Fast |
| `llama3.1-405b` | 128K | 4K | $$$$ | Very High | Slow |
| `llama3.1-70b` | 128K | 4K | $$ | High | Fast |
| `llama3.1-8b` | 128K | 4K | $ | Medium | Very Fast |
| `mistral-large2` | 128K | 4K | $$ | High | Fast |
| `mistral-7b` | 32K | 4K | $ | Medium | Very Fast |
| `mixtral-8x7b` | 32K | 4K | $$ | High | Fast |
| `reka-flash` | 100K | 4K | $$ | High | Fast |
| `snowflake-arctic` | 4K | 4K | $ | Medium | Fast |

### Direct COMPLETE() Usage (Fallback if Agent unavailable)

```sql
-- Direct LLM call with system prompt
SELECT SNOWFLAKE.CORTEX.COMPLETE(
    'claude-3.5-sonnet',
    [
        {'role': 'system', 'content': 'You are a knowledge assistant. Only answer from provided context.'},
        {'role': 'user', 'content': 'Context: [retrieved chunks here]\n\nQuestion: How do royalty clawbacks work?'}
    ],
    {
        'temperature': 0.1,
        'max_tokens': 2000
    }
) AS answer;
```

### Model Selection Recommendations

**For Cortex Agent (primary answer generation):**
- **Production**: `claude-3.5-sonnet` — Best at following structured output instructions, best reasoning
- **Cost fallback**: `llama3.3-70b` — Good quality at lower cost, use for simple questions
- **Speed fallback**: `claude-3-haiku` — Fast for simple lookups

**For Cortex AI Functions:**
- **Classification** (AI_CLASSIFY): Built-in, no model selection needed
- **Summarization** (AI_SUMMARIZE): Built-in
- **Extraction** (AI_EXTRACT): Built-in
- **Sentiment**: Built-in

**For Manual COMPLETE() calls (if needed):**
- **Confidence scoring**: Use `claude-3.5-sonnet` with temperature=0
- **Related question generation**: Use `llama3.3-70b` (good enough, cheaper)
- **Document metadata extraction**: Use `llama3.1-8b` (fast, simple task)

---

## Cost Estimation

### Per-Query Cost Breakdown

For a typical RAG query:
1. **Cortex Search query**: ~0.01-0.05 credits
2. **Cortex Agent (claude-3.5-sonnet)**: ~0.01-0.10 credits depending on context
3. **Total per query**: ~0.02-0.15 credits

At 1,000 queries/month: **20-150 credits/month** for AI compute

### Cost Optimization Strategies

1. **Use cheaper models for simple questions**: Route easy questions to `llama3.3-70b`
2. **Cache frequent questions**: Store answers for repeated questions
3. **Limit search results**: 5 results instead of 10 reduces context tokens
4. **Smaller chunks**: Smaller chunks = fewer tokens per search result
5. **Warehouse auto-suspend**: Set aggressive auto-suspend on search warehouse

---

## Embedding Model Deep Dive: snowflake-arctic-embed-l-v2.0

This is Snowflake's flagship embedding model and the recommended choice:

- **Architecture**: Based on XLM-RoBERTa with proprietary fine-tuning
- **Training**: Trained on 100B+ text pairs including enterprise documentation
- **Dimensions**: 1024 (optimal for similarity search)
- **Max tokens**: 8192 (handles long document chunks)
- **Multilingual**: Supports 100+ languages
- **MTEB benchmark**: Top performer on enterprise retrieval benchmarks
- **Matryoshka support**: Can truncate to lower dimensions (256, 512) with minimal quality loss

### Why it's best for RevSearch:
- Handles the mix of technical music industry terminology
- 8K token context handles longer document chunks
- Enterprise-focused training matches internal documentation style
- Automatically used by Cortex Search Service (no manual setup)
