# Research: Snowflake Quickstarts & Blog Analysis
## Agent 8 Output — Comprehensive Findings

---

## Quickstart 1: Asking Questions to Your Documents with Cortex Search

**Source**: Snowflake Quickstart Guide

### Architecture Pattern
1. Load documents into a Snowflake table
2. Chunk documents into smaller pieces
3. Create Cortex Search Service on chunks
4. Build Streamlit app for Q&A

### Key Code Patterns

**Creating Search Service**:
```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE my_search_service
    ON text_chunk
    ATTRIBUTES title, source
    WAREHOUSE = my_wh
    TARGET_LAG = '1 hour'
AS (
    SELECT text_chunk, title, source
    FROM document_chunks
);
```

**Querying from Python**:
```python
from snowflake.core import Root

root = Root(session)
svc = root.databases["DB"].schemas["SCHEMA"].cortex_search_services["SVC"]
results = svc.search(query="my question", columns=["text_chunk", "title"], limit=5)
```

### Lessons Learned
- Start with simple chunking (fixed size with overlap)
- 5 results is usually enough for RAG
- Include document title as an attribute for source attribution
- Use `TARGET_LAG = '1 hour'` for most use cases

---

## Quickstart 2: Build RAG-Based LLM Assistant with Streamlit + Cortex

**Source**: Snowflake Quickstart Guide

### Architecture Pattern
1. PDF documents uploaded to a Snowflake stage
2. Python UDF parses PDFs using `pypdf`
3. Text chunked with overlap
4. Cortex Search indexes chunks
5. Streamlit app uses Cortex Search + CORTEX.COMPLETE for RAG

### Key Code Patterns

**PDF Parsing**:
```python
from pypdf import PdfReader
import io

def parse_pdf(file_bytes):
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text
```

**RAG with CORTEX.COMPLETE**:
```python
def get_answer(question, context_chunks):
    context = "\n\n".join(context_chunks)
    prompt = f"""You are a helpful assistant. Answer the question based ONLY on the 
    provided context. If the context doesn't contain the answer, say so.
    
    Context:
    {context}
    
    Question: {question}
    
    Answer:"""
    
    result = session.sql(f"""
        SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-3.5-sonnet', '{prompt}')
    """).collect()
    return result[0][0]
```

### Lessons Learned
- Cortex Search + CORTEX.COMPLETE is the basic RAG pattern
- Cortex Agent replaces the manual COMPLETE call (recommended for new projects)
- Always include "based ONLY on the provided context" in prompts
- PDF parsing needs to handle edge cases (images, tables, multi-column layouts)

---

## Quickstart 3: Cortex Search Overview

### Key Insights

1. **Hybrid search is automatic**: No configuration needed — Cortex Search always uses both vector and keyword search
2. **Embedding is managed**: Don't need to call EMBED_TEXT yourself
3. **Filtering is powerful**: Can filter on any ATTRIBUTE column at query time
4. **Refresh is automatic**: TARGET_LAG controls freshness
5. **Source query flexibility**: The AS clause can be a complex query joining multiple tables

### Performance Recommendations
- Keep chunk size reasonable (500-2000 characters)
- Index only the columns you need as attributes
- Use filters to narrow search scope
- Start with `limit=5`, increase if needed

---

## Quickstart 4: Product Review Analysis App

### Relevant Patterns for RevSearch

**Sentiment Analysis on Feedback**:
```sql
SELECT 
    question_text,
    feedback_text,
    SNOWFLAKE.CORTEX.SENTIMENT(feedback_text) AS sentiment_score
FROM REVSEARCH.ANALYTICS.FEEDBACK
WHERE feedback_text IS NOT NULL;
```

**Topic Classification**:
```sql
SELECT 
    question_text,
    SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        question_text,
        ['Royalties', 'Distribution', 'Billing', 'Onboarding', 'Technical', 'General']
    ):label::VARCHAR AS topic
FROM REVSEARCH.ANALYTICS.QUESTIONS;
```

---

## Blog: Cortex Search — Build AI Apps

### Key Takeaways

1. **Cortex Search is the foundation for RAG on Snowflake**
2. **Hybrid search outperforms pure vector or pure keyword** for enterprise use cases
3. **No embedding pipeline needed** — Cortex Search handles everything
4. **Scale tested** to millions of documents
5. **Enterprise features**: RBAC, audit logging, data governance all inherited

### Recommended Architecture from Blog
- Use Cortex Search for retrieval
- Use Cortex Agent for orchestration (replaces manual RAG pipeline)
- Use Streamlit in Snowflake for UI
- Use Dynamic Tables for analytics

---

## Blog: Cortex Agent — AI Apps

### Key Takeaways

1. **Cortex Agent is the recommended way to build AI assistants** on Snowflake
2. **Tool-based architecture**: Attach search services, SQL tools, custom tools
3. **System prompt controls behavior**: Quality of answers depends heavily on prompt engineering
4. **Multi-tool support**: Agent can search multiple search services and combine results
5. **Conversation support**: Built-in multi-turn context management

### Production Recommendations from Blog
- Start with one search service, add more as needed
- Invest time in system prompt engineering
- Monitor answer quality via user feedback
- Use structured output for consistent UX
- Test with a diverse set of questions before launch

---

## Consolidated Best Practices from All Quickstarts

### Data Preparation
1. Clean text: Strip HTML, normalize whitespace, fix encoding
2. Chunk appropriately: 1000-1500 chars with 10-15% overlap
3. Preserve metadata: Title, source, date, owner in every chunk
4. Deduplicate: Remove identical chunks from overlapping sources
5. Filter quality: Exclude chunks < 50 characters

### Search Configuration
1. Hybrid search (automatic with Cortex Search)
2. Filter by status = 'active' always
3. Return 5 results (sweet spot for RAG quality vs noise)
4. Include metadata columns as attributes for filtering and source citation
5. Set TARGET_LAG based on freshness needs (1 hour recommended)

### Answer Generation
1. Use Cortex Agent (not manual COMPLETE) for production
2. System prompt must enforce grounding (no hallucination)
3. Require source citations in every answer
4. Temperature = 0 for factual accuracy
5. Structured JSON output for consistent UX

### Application
1. Multi-page Streamlit app
2. Chat interface with session state
3. Feedback collection on every answer
4. Dashboard for analytics and knowledge gaps
5. Admin panel for document and owner management

### Operations
1. Scheduled ingestion via Snowflake Tasks
2. Dynamic Tables for real-time analytics
3. Alerts for pipeline failures and knowledge gaps
4. Credit monitoring for Cortex usage
5. Regular evaluation of answer quality (manual audit + user feedback)
