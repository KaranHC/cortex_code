# PLAN 6 Part 2: Freshdesk V2 — Agent Enablement & Snowflake Intelligence

> Using V2 ingested data (Part 1) to power Cortex Agents, Cortex Search, Snowflake Intelligence,
> and the expertise model. Depends on Part 1 completion (25 RAW tables populated).

---

## Prerequisites (from Part 1)

| Requirement | Verification |
|-------------|-------------|
| 25 RAW tables populated | `SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='RAW' AND TABLE_NAME LIKE 'FRESHDESK%'` → 25 |
| Tickets: 1,811+ | `SELECT COUNT(*) FROM RAW.FRESHDESK_TICKETS` |
| Articles: 179+ | `SELECT COUNT(*) FROM RAW.FRESHDESK_SOLUTION_ARTICLES` |
| Conversations loaded | `SELECT COUNT(*) FROM RAW.FRESHDESK_TICKET_CONVERSATIONS` > 0 |
| Discussions loaded | `SELECT COUNT(*) FROM RAW.FRESHDESK_DISCUSSION_TOPICS` > 0 |
| CSAT loaded | `SELECT COUNT(*) FROM RAW.FRESHDESK_SATISFACTION_RATINGS` > 0 |

---

## Phase 1: PROCESS_DOCUMENTS — Freshdesk V2 Content → CURATED

### 1.1 Solution Articles → CURATED.DOCUMENTS + DOCUMENT_CHUNKS

V2 articles have `description` (HTML) and `description_text` (plain text). Both stored in RAW; use `description` through `clean_html()` with `description_text` as fallback.

```python
def process_freshdesk_articles(session):
    articles = session.sql("""
        SELECT id, title, description, description_text, folder_id, category_id,
               agent_id, status, hits, thumbs_up, thumbs_down, tags, created_at, updated_at
        FROM RAW.FRESHDESK_SOLUTION_ARTICLES
        WHERE status = 2
    """).collect()

    docs = []
    for row in articles:
        content = clean_html(row["DESCRIPTION"]) or row["DESCRIPTION_TEXT"] or ""
        if len(content.strip()) < 50:
            continue
        doc_id = make_id("freshdesk", str(row["ID"]))
        docs.append({
            "document_id": doc_id,
            "source_system": "freshdesk",
            "source_id": str(row["ID"]),
            "source_url": f"https://newaccount1623084859360.freshdesk.com/a/solutions/articles/{row['ID']}",
            "title": row["TITLE"] or "Untitled",
            "content": content[:100000],
            "content_length": len(content),
            "status": "active",
            "created_at": row["CREATED_AT"],
            "last_updated": row["UPDATED_AT"],
            "metadata": json.dumps({
                "doc_type": "kb_article", "folder_id": str(row["FOLDER_ID"]),
                "category_id": str(row["CATEGORY_ID"]), "hits": row["HITS"],
                "thumbs_up": row["THUMBS_UP"], "thumbs_down": row["THUMBS_DOWN"],
            }),
        })
    return docs
```

### 1.2 Ticket Conversations → CURATED (Public Agent Responses Only)

Only public, outgoing, non-deleted conversations → RAG content. Private notes and customer messages excluded.

```python
def process_freshdesk_conversations(session):
    convos = session.sql("""
        SELECT c.id, c.ticket_id, c.body, c.body_text, c.user_id,
               c.incoming, c.private, c.created_at, c.updated_at,
               t.subject AS ticket_subject
        FROM RAW.FRESHDESK_TICKET_CONVERSATIONS c
        JOIN RAW.FRESHDESK_TICKETS t ON c.ticket_id = t.id
        WHERE c.incoming = FALSE AND c.private = FALSE
    """).collect()

    docs = []
    for row in convos:
        body = clean_html(row["BODY"]) or row["BODY_TEXT"] or ""
        if len(body.strip()) < 50:
            continue
        doc_id = make_id("freshdesk_conversation", str(row["ID"]))
        docs.append({
            "document_id": doc_id,
            "source_system": "freshdesk",
            "source_id": f"conv_{row['ID']}",
            "source_url": f"https://newaccount1623084859360.freshdesk.com/a/tickets/{row['TICKET_ID']}",
            "title": f"Support Response: {row['TICKET_SUBJECT']}" if row["TICKET_SUBJECT"] else "Support Response",
            "content": body[:100000],
            "content_length": len(body),
            "status": "active",
            "created_at": row["CREATED_AT"],
            "last_updated": row["UPDATED_AT"],
            "metadata": json.dumps({
                "doc_type": "ticket_conversation",
                "ticket_id": str(row["TICKET_ID"]),
                "user_id": str(row["USER_ID"]),
            }),
        })
    return docs
```

### 1.3 Discussion Topics + Comments → CURATED (V2 NEW — was empty on V1)

```python
def process_freshdesk_discussions(session):
    topics = session.sql("""
        SELECT t.id, t.title, t.forum_id, t.user_id, t.hits, t.created_at, t.updated_at,
               f.name AS forum_name
        FROM RAW.FRESHDESK_DISCUSSION_TOPICS t
        JOIN RAW.FRESHDESK_DISCUSSION_FORUMS f ON t.forum_id = f.id
    """).collect()

    comments = session.sql("""
        SELECT c.id, c.topic_id, c.body, c.body_text, c.user_id, c.answer,
               c.created_at, c.updated_at, t.title AS topic_title
        FROM RAW.FRESHDESK_DISCUSSION_COMMENTS c
        JOIN RAW.FRESHDESK_DISCUSSION_TOPICS t ON c.topic_id = t.id
    """).collect()

    docs = []
    for row in comments:
        body = row["BODY_TEXT"] or clean_html(row["BODY"]) or ""
        if len(body.strip()) < 30:
            continue
        doc_id = make_id("freshdesk_discussion", str(row["ID"]))
        docs.append({
            "document_id": doc_id,
            "source_system": "freshdesk",
            "source_id": f"disc_{row['ID']}",
            "title": f"Discussion: {row['TOPIC_TITLE']}" if row["TOPIC_TITLE"] else "Discussion Comment",
            "content": body[:100000],
            "content_length": len(body),
            "status": "active",
            "created_at": row["CREATED_AT"],
            "last_updated": row["UPDATED_AT"],
            "metadata": json.dumps({
                "doc_type": "discussion_comment",
                "topic_id": str(row["TOPIC_ID"]),
                "is_answer": row["ANSWER"],
            }),
        })
    return docs
```

### 1.4 Source-Scoped Writes (Critical)

```python
session.sql("DELETE FROM CURATED.DOCUMENT_CHUNKS WHERE source_system = 'freshdesk'").collect()
session.sql("DELETE FROM CURATED.DOCUMENTS WHERE source_system = 'freshdesk'").collect()

all_docs = process_freshdesk_articles(session) + process_freshdesk_conversations(session) + process_freshdesk_discussions(session)

if all_docs:
    session.create_dataframe(all_docs).write.mode("append").save_as_table("CURATED.DOCUMENTS")
    chunks = []
    for doc in all_docs:
        for i, chunk_text in enumerate(chunk_content(doc["content"])):
            chunks.append({
                "chunk_id": make_id(doc["document_id"], str(i)),
                "document_id": doc["document_id"],
                "chunk_index": i,
                "content": chunk_text,
                "content_length": len(chunk_text),
                "title": doc["title"],
                "source_system": "freshdesk",
                "source_url": doc["source_url"],
                "last_updated": doc["last_updated"],
                "status": "active",
            })
    if chunks:
        session.create_dataframe(chunks).write.mode("append").save_as_table("CURATED.DOCUMENT_CHUNKS")
```

### Deliverables
- [ ] PROCESS_DOCUMENTS updated with V2 Freshdesk content
- [ ] ~152 KB articles + N conversations + 18 discussion comments → CURATED
- [ ] Source-scoped deletes (Freshdesk failure doesn't wipe GitBook)
- [ ] Batch `create_dataframe` writes (no SQL interpolation)
- [ ] Private conversations excluded from CURATED

---

## Phase 2: CLASSIFY_DOCUMENTS

No code changes — existing `CLASSIFY_DOCUMENTS()` operates on `WHERE topic IS NULL` and auto-classifies new Freshdesk documents.

### Validation

- KB articles → "FAQ", "Product Documentation", "Technical Guide"
- Conversations → "Support Response", "Troubleshooting"
- Discussion comments → "Community Discussion"

### Deliverables
- [ ] Classification runs on Freshdesk documents without errors
- [ ] 90%+ have sensible `topic` and `product_area`

---

## Phase 3: Cortex Search Service

### 3.1 No DDL Changes

`DOCUMENT_SEARCH` is defined over `CURATED.DOCUMENT_CHUNKS`. Freshdesk chunks auto-indexed on next refresh.

### 3.2 Validation

```sql
SELECT source_system, COUNT(*) AS chunks, COUNT(DISTINCT document_id) AS docs
FROM CURATED.DOCUMENT_CHUNKS
GROUP BY source_system;
-- Expected: freshdesk ~500-1000+ chunks alongside gitbook ~935
```

### Deliverables
- [ ] Freshdesk chunks indexed in DOCUMENT_SEARCH
- [ ] Search returns Freshdesk results alongside GitBook
- [ ] `source_system` attribute filter works

---

## Phase 4: Agent Prompt Update

### 4.1 Update All 3 Agent Variants

Add to system prompt:

```
DATA SOURCES:
1. GitBook (source_system='gitbook') — Product docs, API docs, technical guides
2. Freshdesk KB (source_system='freshdesk', doc_type='kb_article') — 179 articles across
   12 categories: FAQ, Distribution, Revenue/Royalties, Onboarding, Analytics, etc.
3. Freshdesk Conversations (source_system='freshdesk', doc_type='ticket_conversation') —
   Agent support responses to customer questions (public replies only)
4. Freshdesk Discussions (source_system='freshdesk', doc_type='discussion_comment') —
   Community forum discussions (5 forums, 8 topics, 18 comments)

For customer-facing FAQ → prioritize Freshdesk KB.
For step-by-step resolution → check Freshdesk Conversations.
For community insights → check Freshdesk Discussions.
For technical/product docs → prioritize GitBook.
Always cite source_system in attribution.
```

### Deliverables
- [ ] All 3 agents updated with Freshdesk data source descriptions
- [ ] Agent correctly cites Freshdesk sources

---

## Phase 5: Agent Expertise Model (V2 Enhanced)

### 5.1 V2 Enhancements Over V1 Plan

| Signal | V1 Data | V2 Data |
|--------|---------|---------|
| Ticket volume | 30 tickets | **1,811 tickets** — much richer signal |
| Conversations | Embedded in ticket (limited) | **Dedicated endpoint** — full conversation threads |
| Agents | 20 active + 17 deleted | **40 total** — more complete |
| CSAT Ratings | Empty (0) | **6 ratings** — agent satisfaction signal (NEW) |
| Discussions | Empty (0 forums) | **5 forums, 8 topics, 18 comments** — community expertise (NEW) |
| Roles | Not available (V1 404) | **4 roles** — role-based expertise context (NEW) |

### 5.2 Scoring Model (Same as V1 plan, more data)

9-signal scoring model (unchanged from existing Phase 10.5):
- KB articles authored (×10), modified (×3)
- Ticket notes public (×5), private (×2)
- Tickets assigned (×3)
- Article hits (×0.01), ratings (+2/-1)
- Note substance (×0.001/char)
- Recency factor (1.0→0.2 decay)

**NEW V2 Signals** (additive):
- **CSAT ratings per agent**: Agents with positive CSAT get +5 per positive rating
- **Discussion answers**: Agents whose comments are marked `answer=true` get +8 per answer
- **Role context**: Agent roles stored for context ("Admin", "Supervisor", etc.)

### 5.3 Views

```sql
CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.CURATED.V_FRESHDESK_AGENT_EXPERTISE AS
-- Same CTE-based scoring model from existing plan §10.5.7
-- Updated to use V2 table schemas (id not agent_id, contact VARIANT not user_id)
-- Added CSAT signal CTE and discussion answer CTE
...;

CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.CURATED.V_FRESHDESK_TOPIC_CONTACTS AS
-- Active-first escalation paths per topic
...;
```

### 5.4 Agent Directory Table

```sql
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.CURATED.FRESHDESK_AGENT_DIRECTORY (
    agent_id              NUMBER,
    agent_name            VARCHAR(500),
    agent_email           VARCHAR(500),
    agent_status          VARCHAR(20),
    agent_role            VARCHAR(200),
    total_kb_authored     NUMBER,
    total_ticket_notes    NUMBER,
    total_csat_positive   NUMBER,
    total_discussion_answers NUMBER,
    topics_as_l1          NUMBER,
    topics_as_l2          NUMBER,
    topics_as_l3          NUMBER,
    top_expertise_areas   VARCHAR(2000),
    overall_score         NUMBER,
    latest_activity_days  NUMBER,
    _loaded_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

### Deliverables
- [ ] V_FRESHDESK_AGENT_EXPERTISE view with V2 schema
- [ ] V_FRESHDESK_TOPIC_CONTACTS view with active-first escalation
- [ ] FRESHDESK_AGENT_DIRECTORY populated
- [ ] CSAT and discussion signals incorporated
- [ ] Agent prompt includes expertise query instructions

---

## Phase 6: Snowflake Intelligence Enablement

### 6.1 V2 Data Powers New SI Capabilities

| V2 Entity | Intelligence Use Case |
|-----------|----------------------|
| **CSAT Ratings** (6) | "What's our average customer satisfaction?" "Which agents have best CSAT?" |
| **SLA Policies** (1) | "What are our SLA targets?" "Are we meeting SLA?" |
| **Automation Rules** (64) | "What automations do we have?" "How many ticket creation rules?" |
| **Business Hours** (1) | "What are our support hours?" "What timezone?" |
| **Ticket Forms** (2) | "What ticket forms exist?" "What fields are on each form?" |
| **Discussion Topics** (8) | "What are customers discussing?" "Most popular forum topics?" |
| **Email Configs** (3) | "What support emails exist?" "Which groups handle which email?" |
| **1,811 Tickets** (was 30) | Trend analysis, SLA compliance, category distribution |

### 6.2 Analytical Views for SI

```sql
CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.ANALYTICS.V_FRESHDESK_TICKET_TRENDS AS
SELECT
    DATE_TRUNC('month', created_at) AS month,
    status, priority, type, group_id,
    COUNT(*) AS ticket_count,
    AVG(DATEDIFF('hour', created_at, updated_at)) AS avg_resolution_hours
FROM RAW.FRESHDESK_TICKETS
GROUP BY 1, 2, 3, 4, 5;

CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.ANALYTICS.V_FRESHDESK_AGENT_PERFORMANCE AS
SELECT
    t.responder_id AS agent_id,
    a.contact:name::VARCHAR AS agent_name,
    COUNT(DISTINCT t.id) AS tickets_handled,
    AVG(DATEDIFF('hour', t.created_at, t.updated_at)) AS avg_handle_hours,
    COUNT(DISTINCT sr.id) AS csat_responses,
    AVG(sr.ratings:default_question::NUMBER) AS avg_csat_score
FROM RAW.FRESHDESK_TICKETS t
LEFT JOIN RAW.FRESHDESK_AGENTS a ON t.responder_id = a.id
LEFT JOIN RAW.FRESHDESK_SATISFACTION_RATINGS sr ON sr.ticket_id = t.id
WHERE t.responder_id IS NOT NULL
GROUP BY 1, 2;

CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.ANALYTICS.V_FRESHDESK_SLA_COMPLIANCE AS
SELECT
    t.id AS ticket_id, t.subject, t.priority,
    t.created_at, t.due_by, t.fr_due_by, t.updated_at,
    IFF(t.due_by IS NOT NULL AND t.updated_at <= t.due_by, TRUE, FALSE) AS resolution_sla_met,
    IFF(t.fr_due_by IS NOT NULL, TRUE, NULL) AS has_first_response_sla,
    sp.name AS sla_policy_name
FROM RAW.FRESHDESK_TICKETS t
LEFT JOIN RAW.FRESHDESK_SLA_POLICIES sp ON sp.is_default = TRUE;
```

### 6.3 Agent Prompt for SI Queries

Add to agent system prompt:

```
ANALYTICAL CAPABILITIES (V2 data):
- Ticket trends: query V_FRESHDESK_TICKET_TRENDS for monthly volumes, resolution times
- Agent performance: query V_FRESHDESK_AGENT_PERFORMANCE for individual metrics + CSAT
- SLA compliance: query V_FRESHDESK_SLA_COMPLIANCE for SLA adherence
- Automation inventory: query RAW.FRESHDESK_AUTOMATION_RULES for rule catalog
- Support hours: query RAW.FRESHDESK_BUSINESS_HOURS for schedule
```

### Deliverables
- [ ] 3 analytical views created
- [ ] Agent prompt includes analytical capabilities
- [ ] SI can answer CSAT, SLA, trend, performance questions

---

## Phase 7: Evaluation

### 7.1 Expanded Eval Dataset (V2-powered)

| # | Question | Expected Source | Doc Type |
|---|----------|----------------|----------|
| 1 | How do I distribute music on TikTok? | freshdesk | kb_article |
| 2 | What DSPs does Revelator support? | freshdesk | kb_article |
| 3 | How do I pay payees with PayPal? | freshdesk | kb_article |
| 4 | What are our SLA targets? | freshdesk | sla_policy |
| 5 | What's our average CSAT score? | freshdesk | satisfaction_rating |
| 6 | How many automation rules do we have? | freshdesk | automation_rule |
| 7 | What are our support hours? | freshdesk | business_hours |
| 8 | Who should I contact about distribution? | freshdesk | expertise |
| 9 | What are customers discussing in forums? | freshdesk | discussion |
| 10 | Which ticket forms are available? | freshdesk | ticket_form |

### 7.2 Acceptance Criteria

- Freshdesk KB questions: ≥85% accuracy
- Freshdesk analytical questions: ≥80% accuracy
- No regression on GitBook (delta < 5%)
- Expertise queries return correct L1→L2→L3 paths

### Deliverables
- [ ] 10 new eval questions added
- [ ] All accuracy targets met
- [ ] No GitBook regression

---

## Phase 8: Streamlit UI

### 8.1 Source Display Updates

Ensure `app/pages/1_Ask_a_Question.py` renders:
- "Freshdesk KB" source cards (kb_article)
- "Freshdesk Support" source cards (ticket_conversation)
- "Freshdesk Discussion" source cards (discussion_comment)

### 8.2 Contact Directory Page

New `app/pages/4_Contact_Directory.py`:
- Escalation view: topic → L1→L2→L3 path
- Agent roster: sortable table with scores
- Gap alerts: topics with ⚠ NO ACTIVE EXPERTS in red
- CSAT badges: agents with positive CSAT highlighted

### 8.3 Analytics Dashboard

New `app/pages/5_Freshdesk_Analytics.py`:
- Ticket volume trend (monthly)
- Resolution time by priority
- CSAT distribution
- SLA compliance rate
- Agent leaderboard

### Deliverables
- [ ] Freshdesk source cards in Ask a Question
- [ ] Contact Directory page with escalation paths
- [ ] Analytics dashboard with V2 metrics

---

## Implementation Order

```
Phase 1: PROCESS_DOCUMENTS update (articles + convos + discussions)  ← ~6h
Phase 2: CLASSIFY_DOCUMENTS validation                              ← ~1h
Phase 3: Cortex Search validation                                   ← ~1h
Phase 4: Agent prompt update (3 variants)                           ← ~1.5h
Phase 5: Expertise model (views + directory + CSAT signal)          ← ~4h
Phase 6: SI enablement (analytical views + agent prompt)            ← ~3h
Phase 7: Evaluation (10 new questions)                              ← ~3h
Phase 8: Streamlit UI (3 pages)                                     ← ~4h
────────────────────────────────────────────────────────
TOTAL: ~23.5h
```

---

## Combined Effort (Part 1 + Part 2)

| Component | Effort |
|-----------|--------|
| Part 1: V2 Ingestion (11 phases) | ~32h |
| Part 2: Intelligence + Agents (8 phases) | ~23.5h |
| **Total** | **~55.5h** |

---

## V1 → V2 Migration Checklist

- [x] V2 confirmed working on `newaccount1623084859360.freshdesk.com`
- [x] All V2 endpoints tested (37 GET, 31 working, 4 plan-blocked, 2 empty)
- [x] Dual rate limits confirmed (100/min + 40/min)
- [x] Full entity inventory with record counts
- [ ] Network rule updated with V2 domain
- [ ] 25 RAW tables created (Part 1 Phase 2)
- [ ] 4 ingestion procedures created (Part 1 Phases 3-6)
- [ ] PROCESS_DOCUMENTS handles V2 schemas (Part 2 Phase 1)
- [ ] All 3 agents aware of V2 data sources (Part 2 Phase 4)
- [ ] Expertise model uses V2 volumes (Part 2 Phase 5)
- [ ] SI analytical views deployed (Part 2 Phase 6)
- [ ] Old V1 plan archived
