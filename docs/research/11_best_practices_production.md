# Research: Cortex Agent + Cortex Search Best Practices
## Agent 11 (Bonus) Output — Gap Analysis & Production Quality Guide

---

## Critical Best Practices for Maximum Answer Quality

### 1. Data Preparation is King

**Problem**: Poor data quality → poor search results → poor answers.

**Best Practices**:
- **Strip HTML completely**: Freshdesk returns HTML — convert to clean text
- **Normalize whitespace**: Multiple spaces, tabs, trailing newlines — clean them
- **Remove boilerplate**: Headers, footers, navigation menus, cookie notices
- **Handle encoding**: UTF-8 normalize, fix smart quotes, handle special characters
- **Deduplicate**: Same article may exist in multiple sources — deduplicate by content hash
- **Minimum quality threshold**: Skip chunks < 50 characters or pure metadata

```python
import re
from html import unescape

def clean_text(text):
    """Clean raw text for indexing."""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = unescape(text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove URLs (optional — keep if they're informative)
    # text = re.sub(r'https?://\S+', '', text)
    return text
```

### 2. Chunk Design for Maximum Retrieval Quality

**Key Insight**: The chunk that gets retrieved must contain ENOUGH context to answer the question, but not so much that it dilutes relevance.

**Optimal Strategy for Revelator's content**:
- **Freshdesk articles**: Most are short (< 2000 chars) → index whole article as one chunk + chunk only if > 2000 chars
- **GitBook pages**: Usually well-structured with headers → split by H2/H3 sections
- **Notion pages**: Variable → use smart chunking (section-based with fallback to fixed)

**Title injection**: ALWAYS prepend the document title to each chunk:
```python
chunk_text = f"Title: {title}\n\n{chunk_content}"
```
This dramatically improves retrieval because the title provides context.

### 3. Cortex Search Configuration Optimization

**Attribute Selection**:
- Index ALL metadata columns you want to filter or display in results
- Don't index computed/derived columns (wastes storage)
- Cast timestamps to VARCHAR before indexing

**Filter Strategy**:
- ALWAYS filter `status = 'active'` in the source query AND at query time
- Add `source_system` filter when user explicitly asks about one source
- Add `topic` / `product_area` filters when question is clearly about one domain

**Result Count**:
- **5 results**: Best for most questions (focused, low noise)
- **8-10 results**: For complex questions spanning multiple topics
- **3 results**: For simple factual lookups

### 4. System Prompt Engineering (Most Critical)

**The system prompt determines 80% of answer quality.**

**Production system prompt for RevSearch**:

```
You are RevSearch, the internal knowledge assistant for Revelator employees.
You answer questions about music distribution, royalties, DSPs, billing, 
onboarding, and company processes.

## CORE RULES

1. ONLY use information from the search results provided to you.
2. NEVER add information from your own training data.
3. If the search results do not contain sufficient information to answer
   the question completely, set answer_strength to "weak" or "no_answer".
4. NEVER guess, speculate, or fill in gaps.
5. When you're unsure, explicitly say what you don't know.

## ANSWER QUALITY

For every answer:
- Quote or closely paraphrase the source documents
- Use inline citations: [Source: Document Title]
- If combining information from multiple documents, note this explicitly
- If documents contain conflicting information, present both and flag the conflict
- If information seems outdated (mentioned in context as old), warn the user

## CONFIDENCE ASSESSMENT

Assign answer_strength based on these STRICT criteria:

"strong":
- The answer is directly stated in 2+ retrieved documents
- No interpretation or inference required
- You could quote the answer verbatim from the sources
- Example: "The refund policy states refunds are processed within 30 days" [Source: Billing Policy]

"medium":
- The answer is partially covered in 1-2 documents
- Some interpretation or inference was needed
- The answer addresses the question but may miss nuances
- Route to knowledge owner for verification

"weak":
- Retrieved documents are only tangentially related
- Significant inference was needed
- You are not confident the answer is complete or accurate
- ALWAYS route to knowledge owner

"no_answer":
- No relevant documents were found
- Retrieved documents don't address the question at all
- You cannot construct a meaningful answer
- ALWAYS route to knowledge owner
- Say: "I could not find documentation addressing this question."

## OUTPUT FORMAT

ALWAYS respond with valid JSON:
{
  "answer": "Your answer with [Source: Title] citations",
  "answer_strength": "strong|medium|weak|no_answer",
  "sources": [
    {
      "title": "Exact document title",
      "source_system": "freshdesk|gitbook|notion|manual",
      "source_url": "URL if available",
      "last_updated": "Date string",
      "relevance_note": "One sentence why this source is relevant"
    }
  ],
  "knowledge_owner": {
    "needed": true/false,
    "primary_owner": "Owner name from document metadata",
    "backup_owner": "Backup name",
    "contact": "Slack/email from metadata",
    "reason": "Why the user should contact the owner"
  },
  "related_questions": [
    "A specific, useful follow-up question",
    "Another related question",
    "A third question from a different angle"
  ]
}

Do NOT include any text before or after the JSON object.
```

### 5. Handling Edge Cases

**No Results**: When Cortex Search returns nothing relevant:
```json
{
  "answer": "I could not find any documentation addressing your question about [topic]. This may be an undocumented area.",
  "answer_strength": "no_answer",
  "sources": [],
  "knowledge_owner": {
    "needed": true,
    "reason": "No documentation found — knowledge owner may need to create documentation for this topic."
  }
}
```

**Ambiguous Question**: When the question could mean multiple things:
- Answer the most likely interpretation
- Mention alternatives: "If you meant [X] instead, please rephrase"

**Very Long Question**: The agent should extract the core question and search for that

**Follow-Up Questions**: Use conversation history to maintain context, but re-search for each turn (don't rely solely on previous context)

### 6. Error Handling & Fallback

```python
def ask_with_fallback(session, question):
    """Ask agent with fallback to direct search."""
    try:
        # Primary: Cortex Agent
        response = agent.complete(messages=[{"role": "user", "content": question}])
        return parse_response(response)
    except Exception as agent_error:
        try:
            # Fallback: Direct Cortex Search + COMPLETE
            results = search_service.search(query=question, columns=["content", "title"], limit=5)
            context = "\n\n".join([r["content"] for r in results.results])
            
            answer = session.sql(f"""
                SELECT SNOWFLAKE.CORTEX.COMPLETE(
                    'llama3.3-70b',
                    'Answer based on this context only: {context}\n\nQuestion: {question}'
                )
            """).collect()[0][0]
            
            return {
                "answer": answer,
                "answer_strength": "medium",
                "sources": [{"title": r["title"]} for r in results.results],
                "knowledge_owner": {"needed": True, "reason": "Fallback mode — verify answer"},
                "related_questions": []
            }
        except:
            return {
                "answer": "I'm experiencing technical difficulties. Please try again or contact support.",
                "answer_strength": "no_answer",
                "sources": [],
                "knowledge_owner": {"needed": True, "reason": "System error"},
                "related_questions": []
            }
```

### 7. Answer Caching for Performance

```sql
-- Check cache before calling agent
CREATE OR REPLACE FUNCTION REVSEARCH.SEARCH.CHECK_ANSWER_CACHE(question_text VARCHAR)
RETURNS VARIANT
LANGUAGE SQL
AS
$$
    SELECT OBJECT_CONSTRUCT(
        'answer', cached_answer,
        'answer_strength', answer_strength,
        'sources', sources,
        'cached', TRUE
    )
    FROM REVSEARCH.ANALYTICS.ANSWER_CACHE
    WHERE question_hash = SHA2(LOWER(TRIM(question_text)))
      AND cached_at > DATEADD('hour', -ttl_hours, CURRENT_TIMESTAMP())
    LIMIT 1
$$;
```

### 8. Content Freshness in Answers

**Always show document dates prominently.**

When a document is > 90 days old, append a warning:
```
⚠️ Note: The source document "[Title]" was last updated [X days ago]. 
This information may be outdated. Please verify with the knowledge owner.
```

### 9. Weekly Re-ingestion Task Design

```sql
-- Run weekly: Full refresh from all sources
-- Run 6-hourly: Incremental (new/updated only)

CREATE OR REPLACE PROCEDURE REVSEARCH.INGESTION.INGEST_ALL_SOURCES(mode VARCHAR)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    IF (mode = 'full') THEN
        -- Truncate and reload
        TRUNCATE TABLE REVSEARCH.RAW.FRESHDESK_ARTICLES;
        TRUNCATE TABLE REVSEARCH.RAW.GITBOOK_PAGES;
        TRUNCATE TABLE REVSEARCH.RAW.NOTION_PAGES;
        CALL REVSEARCH.INGESTION.INGEST_FRESHDESK();
        CALL REVSEARCH.INGESTION.INGEST_GITBOOK();
        CALL REVSEARCH.INGESTION.INGEST_NOTION();
        -- Rebuild curated layer
        TRUNCATE TABLE REVSEARCH.CURATED.DOCUMENTS;
        TRUNCATE TABLE REVSEARCH.CURATED.DOCUMENT_CHUNKS;
        CALL REVSEARCH.INGESTION.PROCESS_DOCUMENTS();
        CALL REVSEARCH.INGESTION.CLASSIFY_DOCUMENTS();
        RETURN 'Full refresh complete';
    ELSE
        -- Incremental: only new/updated since last run
        CALL REVSEARCH.INGESTION.INGEST_FRESHDESK_INCREMENTAL();
        CALL REVSEARCH.INGESTION.INGEST_GITBOOK_INCREMENTAL();
        CALL REVSEARCH.INGESTION.INGEST_NOTION_INCREMENTAL();
        CALL REVSEARCH.INGESTION.PROCESS_NEW_DOCUMENTS();
        RETURN 'Incremental refresh complete';
    END IF;
END;
$$;

-- Weekly full refresh: Sunday 2 AM
CREATE OR REPLACE TASK REVSEARCH.INGESTION.WEEKLY_FULL_REFRESH
    WAREHOUSE = REVSEARCH_INGESTION_WH
    SCHEDULE = 'USING CRON 0 2 * * 0 America/Los_Angeles'
AS
    CALL REVSEARCH.INGESTION.INGEST_ALL_SOURCES('full');

-- 6-hourly incremental
CREATE OR REPLACE TASK REVSEARCH.INGESTION.INCREMENTAL_INGEST
    WAREHOUSE = REVSEARCH_INGESTION_WH
    SCHEDULE = 'USING CRON 0 */6 * * * America/Los_Angeles'
AS
    CALL REVSEARCH.INGESTION.INGEST_ALL_SOURCES('incremental');
```

### 10. Monitoring Checklist

| Check | Frequency | Alert If |
|-------|-----------|----------|
| Task execution status | Every 30 min | Any FAILED state |
| Document count | Daily | Count drops by > 10% |
| Search service health | Hourly | TARGET_LAG exceeded |
| Answer satisfaction | Weekly | Below 80% |
| Knowledge gaps | Weekly | > 5 new gaps |
| Credit consumption | Daily | > 2x average |
| Stale documents | Monthly | > 10 docs older than 90 days |
| User adoption | Weekly | Below target threshold |
