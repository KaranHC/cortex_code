# PLAN 3: RevSearch Enhancements & Future Improvements

> Covers remaining gaps (G3, G6, G10, G11) not addressed in PLAN_2 patches.
> These are Phase 2 improvements to be implemented after MVP launch.

---

## Enhancement 1: Answer Caching (Gap G3)

**Problem**: Identical or near-identical questions re-invoke Cortex Agent (LLM credits + latency).

**Solution**: Cache answers in Snowflake with TTL-based expiration.

### 1.1 Cache Table

```sql
CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.AGENTS.ANSWER_CACHE (
    cache_key        VARCHAR(64) PRIMARY KEY,
    question_text    VARCHAR,
    question_hash    VARCHAR(64),
    answer_json      VARIANT,
    answer_strength  VARCHAR(20),
    created_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    expires_at       TIMESTAMP_NTZ,
    hit_count        NUMBER DEFAULT 0,
    last_hit_at      TIMESTAMP_NTZ
);
```

### 1.2 Cache Logic in Python (agent_client.py)

```python
import hashlib

CACHE_TTL_HOURS = 24

def get_cache_key(question):
    normalized = question.strip().lower()
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return hashlib.sha256(normalized.encode()).hexdigest()

def check_cache(session, question):
    cache_key = get_cache_key(question)
    result = session.sql(f"""
        SELECT answer_json
        FROM SNOWFLAKE_INTELLIGENCE.AGENTS.ANSWER_CACHE
        WHERE cache_key = '{cache_key}'
          AND expires_at > CURRENT_TIMESTAMP()
    """).collect()
    if result:
        session.sql(f"""
            UPDATE SNOWFLAKE_INTELLIGENCE.AGENTS.ANSWER_CACHE
            SET hit_count = hit_count + 1, last_hit_at = CURRENT_TIMESTAMP()
            WHERE cache_key = '{cache_key}'
        """).collect()
        return json.loads(result[0]["ANSWER_JSON"])
    return None

def save_to_cache(session, question, answer_data):
    cache_key = get_cache_key(question)
    session.sql(f"""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.ANSWER_CACHE
            (cache_key, question_text, question_hash, answer_json, answer_strength, expires_at)
        SELECT
            '{cache_key}',
            '{question.replace("'", "''")}',
            '{cache_key}',
            PARSE_JSON('{json.dumps(answer_data).replace("'", "''")}'),
            '{answer_data.get("answer_strength", "unknown")}',
            DATEADD('hour', {CACHE_TTL_HOURS}, CURRENT_TIMESTAMP())
    """).collect()

def ask_agent_with_cache(session, question, conversation_history=None):
    cached = check_cache(session, question)
    if cached:
        cached["from_cache"] = True
        return cached
    answer = ask_agent(session, question, conversation_history)
    if answer.get("answer_strength") in ("strong", "medium"):
        save_to_cache(session, question, answer)
    answer["from_cache"] = False
    return answer
```

### 1.3 Cache Cleanup Task

```sql
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.AGENTS.CLEAN_EXPIRED_CACHE
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 3 * * * America/Los_Angeles'
AS
    DELETE FROM SNOWFLAKE_INTELLIGENCE.AGENTS.ANSWER_CACHE
    WHERE expires_at < CURRENT_TIMESTAMP();

ALTER TASK SNOWFLAKE_INTELLIGENCE.AGENTS.CLEAN_EXPIRED_CACHE RESUME;
```

### 1.4 Cache Invalidation on Ingestion

Add to the weekly full refresh task:
```sql
TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.AGENTS.ANSWER_CACHE;
```

---

## Enhancement 2: Question Deduplication via Embeddings (Gap G6)

**Problem**: FAQ analytics counts "How do I reset my password?" and "password reset process?" as separate questions.

**Solution**: Use `snowflake-arctic-embed-l-v2.0` to embed questions and cluster similar ones.

### 2.1 Embedding-Based Similarity

```sql
CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTION_CLUSTERS (
    cluster_id       NUMBER AUTOINCREMENT,
    canonical_question VARCHAR,
    question_count   NUMBER,
    questions        VARIANT,
    cluster_embedding VECTOR(FLOAT, 1024),
    last_updated     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.ANALYTICS.CLUSTER_QUESTIONS()
    RETURNS VARCHAR
    LANGUAGE PYTHON
    RUNTIME_VERSION = '3.11'
    PACKAGES = ('snowflake-snowpark-python')
    HANDLER = 'run'
AS
$$
def run(session):
    new_questions = session.sql("""
        SELECT DISTINCT question_text,
               SNOWFLAKE.CORTEX.EMBED_TEXT_1024('snowflake-arctic-embed-l-v2.0', question_text) AS embedding
        FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
        WHERE question_text NOT IN (
            SELECT q.VALUE::VARCHAR
            FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTION_CLUSTERS,
                 LATERAL FLATTEN(input => questions) q
        )
    """).collect()

    for row in new_questions:
        q_text = row["QUESTION_TEXT"]
        q_emb = row["EMBEDDING"]

        similar = session.sql(f"""
            SELECT cluster_id, canonical_question,
                   VECTOR_COSINE_SIMILARITY(cluster_embedding, '{q_emb}'::VECTOR(FLOAT, 1024)) AS similarity
            FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTION_CLUSTERS
            WHERE VECTOR_COSINE_SIMILARITY(cluster_embedding, '{q_emb}'::VECTOR(FLOAT, 1024)) > 0.85
            ORDER BY similarity DESC
            LIMIT 1
        """).collect()

        if similar:
            cluster_id = similar[0]["CLUSTER_ID"]
            session.sql(f"""
                UPDATE SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTION_CLUSTERS
                SET questions = ARRAY_APPEND(questions, '{q_text.replace("'", "''")}'),
                    question_count = question_count + 1,
                    last_updated = CURRENT_TIMESTAMP()
                WHERE cluster_id = {cluster_id}
            """).collect()
        else:
            session.sql(f"""
                INSERT INTO SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTION_CLUSTERS
                    (canonical_question, question_count, questions, cluster_embedding)
                SELECT
                    '{q_text.replace("'", "''")}',
                    1,
                    ARRAY_CONSTRUCT('{q_text.replace("'", "''")}'),
                    '{q_emb}'::VECTOR(FLOAT, 1024)
            """).collect()

    return f"Processed {len(new_questions)} new questions"
$$;

CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.ANALYTICS.TASK_CLUSTER_QUESTIONS
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 4 * * * America/Los_Angeles'
AS
    CALL SNOWFLAKE_INTELLIGENCE.ANALYTICS.CLUSTER_QUESTIONS();

ALTER TASK SNOWFLAKE_INTELLIGENCE.ANALYTICS.TASK_CLUSTER_QUESTIONS RESUME;
```

---

## Enhancement 3: PDF/Document Upload with CORTEX.PARSE_DOCUMENT (Gap G10)

**Problem**: Some internal docs exist only as PDFs or uploaded files, not in Freshdesk/GitBook/Notion.

**Solution**: Allow admins to upload PDFs via the Streamlit Admin Panel, parse with `CORTEX.PARSE_DOCUMENT`, chunk, and index.

### 3.1 Stage for Uploaded Files

```sql
CREATE OR REPLACE STAGE SNOWFLAKE_INTELLIGENCE.ADMIN.UPLOADED_DOCS
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

### 3.2 Admin Upload UI (add to Page 3: Admin Panel)

```python
st.subheader("Upload Documents")
uploaded_file = st.file_uploader("Upload PDF or text file", type=["pdf", "txt", "md"])

if uploaded_file and st.button("Process Upload"):
    with st.spinner("Uploading and processing..."):
        stage_path = f"@SNOWFLAKE_INTELLIGENCE.ADMIN.UPLOADED_DOCS/{uploaded_file.name}"
        session.file.put_stream(uploaded_file, stage_path, auto_compress=False)

        if uploaded_file.name.endswith(".pdf"):
            parsed = session.sql(f"""
                SELECT SNOWFLAKE.CORTEX.PARSE_DOCUMENT(
                    '{stage_path}',
                    {{'mode': 'LAYOUT'}}
                ) AS parsed_content
            """).collect()
            content = parsed[0]["PARSED_CONTENT"]["content"]
        else:
            content = uploaded_file.read().decode("utf-8")

        doc_title = st.text_input("Document title", value=uploaded_file.name)
        doc_team = st.selectbox("Team", ["Support", "Engineering", "Product", "Finance", "Operations"])
        doc_topic = st.text_input("Topic/Category")
        doc_owner = st.text_input("Knowledge Owner")

        from hashlib import sha256
        doc_id = sha256(f"manual_{uploaded_file.name}".encode()).hexdigest()

        session.sql(f"""
            INSERT INTO SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
                (document_id, source_system, source_id, title, content, content_length,
                 team, topic, status, owner, last_updated)
            VALUES (
                '{doc_id}', 'manual', '{uploaded_file.name}',
                '{doc_title.replace("'", "''")}',
                '{content[:50000].replace("'", "''")}',
                {len(content)},
                '{doc_team}', '{doc_topic}', 'active',
                '{doc_owner.replace("'", "''")}',
                CURRENT_TIMESTAMP()
            )
        """).collect()

        chunks = chunk_text(content, title=doc_title)
        for i, chunk in enumerate(chunks):
            chunk_id = sha256(f"{doc_id}_{i}".encode()).hexdigest()
            session.sql(f"""
                INSERT INTO SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
                    (chunk_id, document_id, chunk_index, content, title, team, topic,
                     source_system, owner, source_url, last_updated)
                VALUES (
                    '{chunk_id}', '{doc_id}', {i},
                    '{chunk.replace("'", "''")}',
                    '{doc_title.replace("'", "''")}',
                    '{doc_team}', '{doc_topic}', 'manual',
                    '{doc_owner.replace("'", "''")}',
                    NULL, CURRENT_TIMESTAMP()
                )
            """).collect()

        st.success(f"Uploaded and indexed '{doc_title}' — {len(chunks)} chunks created.")
```

---

## Enhancement 4: Smart Section-Based Chunking (Gap G11)

**Problem**: Fixed-size chunking can split mid-sentence or mid-section, losing context.

**Solution**: Prefer section/heading boundaries when chunking, falling back to fixed-size with sentence-boundary overlap.

### 4.1 Improved Chunking Function

```python
import re

def smart_chunk_text(text, title=None, max_chunk_size=1500, min_chunk_size=200, overlap=200):
    if not text or len(text.strip()) < 50:
        return []

    sections = re.split(r'\n(?=#{1,4}\s|[A-Z][A-Za-z\s]{5,}:|\d+\.\s)', text)

    chunks = []
    current_chunk = ""

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(current_chunk) + len(section) <= max_chunk_size:
            current_chunk += "\n\n" + section if current_chunk else section
        else:
            if current_chunk and len(current_chunk) >= min_chunk_size:
                chunks.append(current_chunk)
            if len(section) > max_chunk_size:
                sub_chunks = chunk_text(section, chunk_size=max_chunk_size, overlap=overlap)
                chunks.extend(sub_chunks)
                current_chunk = ""
            else:
                if current_chunk and len(current_chunk) < min_chunk_size:
                    current_chunk += "\n\n" + section
                else:
                    current_chunk = section

    if current_chunk and len(current_chunk) >= min_chunk_size:
        chunks.append(current_chunk)
    elif current_chunk and chunks:
        chunks[-1] += "\n\n" + current_chunk

    if title and chunks:
        chunks[0] = f"Title: {title}\n\n{chunks[0]}"

    return chunks
```

### 4.2 Source-Specific Chunking Strategy

| Source | Strategy | Rationale |
|--------|----------|-----------|
| **Freshdesk** | `chunk_text()` (fixed-size) | ⏸️ DEFERRED — GitBook-first e2e. FAQ articles are short, HTML-cleaned, flat structure |
| **GitBook** | `smart_chunk_text()` | Product docs have clear heading hierarchy |
| **Notion** | `smart_chunk_text()` | ⏸️ DEFERRED — GitBook-first e2e. Wiki pages often have section headers |
| **Manual PDF** | `smart_chunk_text()` | Parsed PDFs have layout-based sections |

---

## Implementation Priority

| Enhancement | Priority | Effort | Impact | When |
|-------------|----------|--------|--------|------|
| G3: Answer Caching | HIGH | 1 day | Reduces LLM costs by 30-50%, improves latency | Week 7 |
| G6: Question Dedup | MEDIUM | 2 days | Better FAQ analytics, knowledge gap accuracy | Week 7 |
| G10: PDF Upload | MEDIUM | 1 day | Enables manual document ingestion | Week 8 |
| G11: Smart Chunking | LOW | 1 day | Marginal retrieval quality improvement | Week 8 |

---

## Cross-Reference to PLAN_1 and PLAN_2

| Gap | PLAN_1 Section | PLAN_2 Phase | Status |
|-----|---------------|-------------|--------|
| G1: HTML Cleaning | R4 (Data Quality) | Phase 2 (Ingestion) | **DONE in PLAN_2** |
| G2: Title in Chunks | R5 (Retrieval Quality) | Phase 2 (Ingestion) | **DONE in PLAN_2** |
| G3: Answer Caching | R18 (Performance) | Phase 4 (Agent) | **PLAN_3 Enh. 1** |
| G4: Agent Fallback | R19 (Reliability) | Phase 4 (Agent) | **DONE in PLAN_2** |
| G5: Staleness Warnings | R8 (Transparency) | Phase 5 (Streamlit) | **DONE in PLAN_2** |
| G6: Question Dedup | R11 (Analytics) | Phase 6 (Analytics) | **PLAN_3 Enh. 2** |
| G7: Weekly Refresh | R3 (Data Freshness) | Phase 2 (Ingestion) | **DONE in PLAN_2** |
| G8: Email Alerts | R20 (Monitoring) | Phase 6 (Analytics) | **DONE in PLAN_2** |
| G9: Production Prompt | R6 (Answer Quality) | Phase 4 (Agent) | **DONE in PLAN_2** |
| G10: PDF Upload | R15 (Admin Tools) | Phase 5 (Streamlit) | **PLAN_3 Enh. 3** |
| G11: Smart Chunking | R5 (Retrieval Quality) | Phase 2 (Ingestion) | **PLAN_3 Enh. 4** |
| G12: Cost Monitoring | R21 (Cost Control) | Phase 6 (Analytics) | **DONE in PLAN_2** |

---

## Summary

All 12 gaps identified during research are now covered:
- **8 gaps (G1, G2, G4, G5, G7, G8, G9, G12)** patched directly into PLAN_2
- **4 gaps (G3, G6, G10, G11)** documented in PLAN_3 as post-MVP enhancements

The system is production-ready after PLAN_2 implementation. PLAN_3 enhancements are recommended for Weeks 7-8 to optimize cost, analytics accuracy, and admin capabilities.
