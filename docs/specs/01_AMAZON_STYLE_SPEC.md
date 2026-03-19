# Internal AI Knowledge Assistant — Amazon-Style Specification
## Project Codename: **RevSearch**

---

## 1. Problem Statement

Employees spend significant time searching across fragmented knowledge sources — Freshdesk helpdesk articles, GitBook product documentation, and Notion internal wikis — to find answers to operational, product, and policy questions. There is no unified search interface, no confidence indicator for answer quality, no routing to knowledge owners when documentation is insufficient, and no visibility into knowledge gaps across the organization.

**The cost of this fragmentation:**
- Employees waste 30-60 minutes per question navigating multiple systems
- Duplicate questions are asked repeatedly across teams with no shared FAQ
- Knowledge owners are unaware of gaps in their documentation
- New hires have no single entry point for institutional knowledge
- Critical process documentation may be outdated without anyone knowing

**What we are building:**
A Snowflake-native internal AI assistant that ingests all documentation from Freshdesk, GitBook, and Notion into Snowflake, provides intelligent search via Cortex Search Service, generates grounded answers via Cortex Agent with strict no-hallucination guardrails, assigns answer confidence levels, routes to knowledge owners when answers are incomplete, and surfaces knowledge gaps through analytics — all delivered through a Streamlit in Snowflake application.

---

## 2. Success Metrics (Measurable KPIs)

| KPI | Target (MVP) | Target (6-Month) | Measurement Method |
|-----|-------------|-------------------|-------------------|
| **Answer Accuracy** | ≥ 85% of answers rated "helpful" by users | ≥ 92% | User feedback (thumbs up/down) on each answer |
| **Strong Answer Rate** | ≥ 60% of questions receive "Strong" confidence | ≥ 75% | Automated confidence scoring from retrieval scores |
| **Hallucination Rate** | 0% fabricated information in answers | 0% | Manual audit of 100 random answers/month + automated grounding check |
| **Response Latency** | < 8 seconds end-to-end | < 5 seconds | Measured from question submission to full response render |
| **Source Attribution** | 100% of answers include ≥ 1 source document | 100% | Automated check — answers without sources are blocked |
| **Knowledge Gap Detection** | Identify top 20 undocumented topics/month | Top 50/month | Clustering of Weak/No Answer questions |
| **User Adoption** | 50+ unique users/week | 150+ unique users/week | Streamlit session tracking |
| **Document Freshness** | 90% of served documents updated within 90 days | 95% | Metadata tracking on last_updated field |
| **Ingestion Coverage** | 100% of Freshdesk KB + GitBook + Notion MVP pages | 100% + new sources | Automated ingestion pipeline monitoring |
| **Owner Routing Accuracy** | 90% correct knowledge owner assignment | 95% | Admin review of routing suggestions |

---

## 3. Key Requirements

### 3.1 Data Ingestion Pipeline

| Requirement | Detail |
|------------|--------|
| **R1: Freshdesk Ingestion** | ⏸️ **DEFERRED — GitBook-first e2e.** Extract ALL data from helpdesk.revelator.com: knowledge base articles (INGEST_HELPDESK) plus 5 operational entities — tickets, contacts, companies, agents, groups (INGEST_FRESHDESK). Load into Snowflake RAW tables. Support incremental refresh every 5 days via Snowflake Tasks. *Will be enabled after GitBook e2e is validated.* |
| **R2: GitBook Ingestion** | Extract all spaces (via org-based listing across 3 orgs, 17 spaces), pages with markdown content, and collections via GitBook API. Preserve page hierarchy and metadata. Load into Snowflake RAW tables. Support incremental refresh every 5 days. |
| **R3: Notion Ingestion** | ⏸️ **DEFERRED — GitBook-first e2e.** Extract pages, databases, and nested blocks via Notion API. Handle rich text, tables, embedded content. Load into Snowflake staging tables. Support incremental refresh every 5 days. *(Note: Notion API key not yet in .env — required before implementation.)* *Will be enabled after GitBook e2e is validated.* |
| **R4: Document Processing** | Parse all ingested content into a unified DOCUMENTS table. Extract metadata (title, team, topic, product_area, owner, last_updated). Chunk documents into optimal segments (512-1024 tokens with 10-15% overlap) for search indexing. |
| **R5: Unified Schema** | All sources converge into a single DOCUMENT_CHUNKS table that feeds Cortex Search Service. Source provenance is preserved (source_system, source_id, source_url). |
| **R6: Credential Management** | Store Freshdesk, GitBook, and Notion API keys as Snowflake Secrets. Use External Access Integrations for outbound API calls. Never store credentials in plaintext in Snowflake objects. |

### 3.2 Search & Retrieval (Cortex Search Service)

| Requirement | Detail |
|------------|--------|
| **R7: Cortex Search Service** | Create a Cortex Search Service over DOCUMENT_CHUNKS with hybrid search (vector + keyword). Use `snowflake-arctic-embed-l-v2.0` for embeddings (best balance of quality and performance for internal docs). Configure automatic refresh to keep index in sync with source tables. |
| **R8: Search Quality** | Return top-k results (k=5) with relevance scores. Support filtering by team, topic, product_area, source_system, and document status. Exclude archived documents from search. |
| **R9: Metadata Columns** | Index columns: content (search column), title, team, topic, product_area, source_system, owner, backup_owner, last_updated, document_id, chunk_id, source_url. |

### 3.3 Intelligent Agent (Cortex Agent)

| Requirement | Detail |
|------------|--------|
| **R10: Cortex Agent** | Create a Cortex Agent with Cortex Search as its primary tool. Configure system prompt to enforce: (a) answer only from retrieved documents, (b) assign confidence level, (c) cite sources, (d) route to owners when confidence is low. |
| **R11: Answer Confidence Logic** | Agent must classify every answer: **Strong** (direct info, multiple sources, no ambiguity), **Medium** (partial info, interpretation needed), **Weak** (minimal content, needs confirmation), **No Answer** (no relevant sources — prefer this over guessing). Confidence derived from retrieval score thresholds + LLM self-assessment. |
| **R12: Structured Output** | Every response must follow the defined format: Answer → Answer Strength → Supporting Sources (doc name, section, last_updated) → Knowledge Owner (if Medium/Weak/No Answer) → Related Questions. |
| **R13: No Hallucination** | System prompt must enforce: "If the retrieved documents do not contain sufficient information to answer the question, respond with 'No Answer' and route to the knowledge owner. Never generate information not found in the provided documents." |
| **R14: LLM Selection** | Use `claude-3.5-sonnet` via CORTEX.COMPLETE() for answer generation (best structured output quality). Fallback to `llama3.3-70b` for cost optimization if needed. |
| **R15: Knowledge Owner Routing** | Maintain a KNOWLEDGE_OWNERS table mapping topics → owners. When answer strength is Medium/Weak/No Answer, query this table and include owner info in response. |

### 3.4 Streamlit Application (3 Pages)

| Requirement | Detail |
|------------|--------|
| **R16: Page 1 — Ask a Question** | Search input with real-time answer display. Show: answer text, confidence badge (color-coded: green/yellow/orange/red), expandable source cards, knowledge owner card (when applicable), related questions as clickable chips. Conversation history in session state. |
| **R17: Page 2 — FAQ Dashboard** | Display: top 20 most-asked questions, recently asked (last 7 days), questions grouped by team (bar chart), questions with Weak/No Answer (knowledge gaps table), trend line of questions over time. Powered by Dynamic Tables for real-time aggregation. |
| **R18: Page 3 — Admin Panel** | Document upload (PDF, DOCX, MD via file uploader). Metadata editor for existing documents. Knowledge owner CRUD. View/export weak/unanswered questions. Document archival toggle. Access restricted to ADMIN role. |
| **R19: Role-Based Access** | ADMIN role: full access to all pages. USER role: Page 1 (Ask) + Page 2 (FAQ). Enforced via Snowflake roles and `st.experimental_user`. |

### 3.5 Analytics & Knowledge Gap Detection

| Requirement | Detail |
|------------|--------|
| **R20: Question Logging** | Every question logged to QUESTIONS table: question_text, user_team, timestamp, answer, answer_strength, sources_used, response_latency_ms. |
| **R21: Feedback Collection** | Thumbs up/down + optional text feedback on every answer. Stored in FEEDBACK table linked to question_id. |
| **R22: FAQ Aggregation** | Dynamic Table aggregating: question clusters (similar questions grouped by embedding similarity), frequency counts, average confidence, team distribution. Refreshed every 1 hour. |
| **R23: Knowledge Gap Alerts** | Snowflake Alert that fires when: > 5 questions in a topic receive Weak/No Answer within 7 days. Notification sent to knowledge owner via email (Snowflake Notification Integration). |

---

## 4. Success Criteria

### MVP Launch Criteria (All must be met)

- [ ] **SC1:** All Freshdesk KB articles and GitBook pages successfully ingested into Snowflake (100% coverage verified by count comparison)
- [ ] **SC2:** Cortex Search Service returns relevant results for 20 pre-defined test questions (manual validation by product team)
- [ ] **SC3:** Cortex Agent produces structured answers with confidence levels for all test questions, with 0 hallucinated facts
- [ ] **SC4:** Streamlit app Page 1 (Ask) loads in < 3 seconds and returns answers in < 8 seconds
- [ ] **SC5:** Streamlit app Page 2 (FAQ Dashboard) displays accurate aggregated metrics
- [ ] **SC6:** Streamlit app Page 3 (Admin) allows document upload and metadata editing
- [ ] **SC7:** Knowledge owner routing correctly identifies owners for 90%+ of Medium/Weak/No Answer responses
- [ ] **SC8:** Ingestion pipeline runs on schedule (every 5 days) with monitoring and alerting
- [ ] **SC9:** All API credentials stored as Snowflake Secrets (zero plaintext credentials)
- [ ] **SC10:** User feedback mechanism operational and logging to FEEDBACK table

### Post-Launch Success (30-Day)

- [ ] 50+ weekly active users
- [ ] ≥ 85% positive feedback rate
- [ ] Top 10 knowledge gaps identified and escalated to owners
- [ ] Zero hallucination incidents reported
- [ ] All ingestion pipelines running without manual intervention

---

## 5. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                      │
│  │ Freshdesk│    │ GitBook  │    │  Notion  │                      │
│  │   API    │    │   API    │    │   API    │                      │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘                      │
│       │               │               │                             │
│       ▼               ▼               ▼                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │          SNOWFLAKE INGESTION LAYER                          │   │
│  │  External Access Integration + Secrets + Snowflake Tasks    │   │
│  │  Python Stored Procedures (per source)                      │   │
│  │  Schedule: Every 5 days | Incremental loads                │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                             │                                       │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              SNOWFLAKE DATA LAYER                           │   │
│  │                                                             │   │
│  │  DB: SNOWFLAKE_INTELLIGENCE                                              │   │
│  │  ├── SCHEMA: RAW        (staging tables per source)         │   │
│  │  ├── SCHEMA: CURATED    (DOCUMENTS, DOCUMENT_CHUNKS)        │   │
│  │  ├── SCHEMA: SEARCH     (Cortex Search Service)             │   │
│  │  ├── SCHEMA: AGENTS     (Cortex Agent definition)           │   │
│  │  ├── SCHEMA: ANALYTICS  (QUESTIONS, FEEDBACK, Dynamic Tbls) │   │
│  │  └── SCHEMA: ADMIN      (KNOWLEDGE_OWNERS, CONFIG)          │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                             │                                       │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              SNOWFLAKE AI LAYER                             │   │
│  │                                                             │   │
│  │  Cortex Search Service ──► Hybrid Search (Vector + BM25)    │   │
│  │         │                   Embedding: arctic-embed-l-v2.0  │   │
│  │         ▼                                                   │   │
│  │  Cortex Agent ──► Tool: Cortex Search                       │   │
│  │         │          LLM: claude-3.5-sonnet                   │   │
│  │         │          Structured Output + Confidence Scoring   │   │
│  │         ▼                                                   │   │
│  │  Cortex AI Functions (CLASSIFY, EXTRACT, SUMMARIZE)         │   │
│  │         │  Auto-classify documents by topic                 │   │
│  │         │  Auto-extract metadata                            │   │
│  │         │  Generate document summaries                      │   │
│  └─────────┼───────────────────────────────────────────────────┘   │
│             │                                                       │
│             ▼                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │         STREAMLIT IN SNOWFLAKE APPLICATION                  │   │
│  │                                                             │   │
│  │  Page 1: Ask a Question (Chat Interface)                    │   │
│  │  Page 2: FAQ Dashboard (Analytics & Knowledge Gaps)         │   │
│  │  Page 3: Admin Panel (Documents, Owners, Config)            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │         MONITORING & ALERTING                               │   │
│  │                                                             │   │
│  │  Snowflake Alerts: Ingestion failures, Knowledge gaps       │   │
│  │  Dynamic Tables: Real-time FAQ aggregation                  │   │
│  │  Streams + Tasks: CDC for new documents                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Cloud Platform** | Snowflake (100% native) | No external AI services needed. All compute, storage, search, LLM, and app hosting within Snowflake. Simplifies security, governance, and cost management. |
| **Embedding Model** | `snowflake-arctic-embed-l-v2.0` | Best-in-class retrieval accuracy for enterprise docs. 1024 dimensions. Natively supported by Cortex Search Service (managed automatically). |
| **LLM for Generation** | `claude-3.5-sonnet` via CORTEX.COMPLETE() | Superior structured output, instruction following, and citation capabilities. Best for generating formatted answers with confidence assessment. |
| **Search Service** | Cortex Search Service | Managed hybrid search (vector + BM25 keyword). Auto-refresh, auto-embedding, filtering. No infrastructure to manage. |
| **Agent Framework** | Cortex Agent | Native Snowflake agent with tool integration (Cortex Search as tool). Supports system prompts, structured output, multi-turn conversation. |
| **Ingestion Method** | Python Stored Procedures + External Access Integration | Direct API calls from Snowflake. No external orchestrator needed. Scheduled via Snowflake Tasks. |
| **Application Layer** | Streamlit in Snowflake | Native hosting, no deployment infra, inherits Snowflake RBAC, built-in session management. |
| **Analytics** | Dynamic Tables | Declarative, auto-refreshing materialized aggregations. No ETL orchestration needed for FAQ analytics. |
| **Scheduling** | Snowflake Tasks | Native cron-like scheduling for ingestion pipelines. Built-in monitoring and retry. |
| **Credential Storage** | Snowflake Secrets + External Access Integration | Secure, auditable credential management. No plaintext keys in code or config. |

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Notion API key not available** | Medium | Low — ⏸️ DEFERRED | Notion deferred. GitBook-first e2e. Will add Notion after GitBook pipeline validated. |
| **Low answer quality on first launch** | Medium | High — erodes user trust | Extensive prompt engineering + test suite of 50 questions. Prefer "No Answer" over bad answers. |
| **Cortex Search relevance issues** | Low | High | Tune chunk size, overlap, and filtering. Monitor retrieval scores. |
| **High Cortex AI costs** | Medium | Medium | Use `llama3.3-70b` for cost-sensitive operations. Monitor credit consumption daily. |
| **Document staleness** | Medium | Medium | Track last_updated. Alert owners when docs > 90 days old. Show freshness in UI. |
| **Low user adoption** | Medium | High | Integrate into existing workflows (Slack future). Promote via team leads. Track adoption metrics. |

---

## 8. Milestones & Timeline

| Milestone | Duration | Deliverable |
|-----------|----------|-------------|
| **M1: Foundation** | Week 1 | Database, schemas, tables, roles, secrets, external access integrations created |
| **M2: Ingestion** | Week 2 | Freshdesk + GitBook pipelines running on schedule. Documents in DOCUMENT_CHUNKS. |
| **M3: Search** | Week 3 | Cortex Search Service created and validated with test queries |
| **M4: Agent** | Week 3-4 | Cortex Agent configured with confidence scoring and structured output |
| **M5: Streamlit MVP** | Week 4-5 | All 3 pages functional: Ask, FAQ Dashboard, Admin |
| **M6: Analytics** | Week 5 | Dynamic Tables, question logging, feedback, knowledge gap detection |
| **M7: Testing** | Week 6 | 50-question test suite passed. Performance validated. Security audit. |
| **M8: Launch** | Week 6 | Internal launch to pilot group (50 users) |

---

## 9. Out of Scope (MVP)

- Slack integration
- Permission-based document access (all docs visible to all users in MVP)
- Automatic FAQ generation
- Multi-language support
- Document version diffing
- AI-suggested documentation improvements
- External (non-employee) access

---

## 10. Dependencies

| Dependency | Owner | Status |
|-----------|-------|--------|
| Freshdesk API key | Available | ✅ In .env |
| GitBook API key | Available | ✅ In .env |
| Notion API key | Needed | ❌ Not in .env — must obtain |
| Snowflake account with Cortex enabled | Infra team | To verify |
| Cortex Search Service access | Snowflake account admin | To verify |
| Cortex Agent access (preview/GA) | Snowflake account admin | To verify |
| Streamlit in Snowflake enabled | Snowflake account admin | To verify |
| Knowledge owner directory | Product Ops (Milan) | To be provided |
| Test question set (50 questions) | Product + Support teams | To be created |

---

## 11. Revelator-Specific Context

### GitBook Knowledge Base (Primary Source — Active)

Two orgs: **Revelator** (`TtdEwjBDdVcxf2N1XKSI`) and **POCRevvy** (`w6093MHpvwKToCRVBt6S`).

**10 spaces worth ingesting (~306 pages):**

| Space | Pages | Topics |
|-------|-------|--------|
| Revelator Pro | 138 | Core platform docs — distribution, royalties, reporting, DSPs |
| Revelator Labs | 37 | Internal product lab documentation |
| Data Pro User Guide | 31 | Analytics and data platform guide |
| Revelator NFT - closed beta | 25 | NFT/Web3 closed beta docs |
| Revelator Wallet | 20 | Wallet and payment documentation |
| Revelator NFT | 19 | NFT product documentation |
| Revelator Onboarding | 12 | Account setup, getting started |
| Revelator API | 8 | API reference and integration guides |
| Web3 API | 5 | Web3/blockchain API documentation |
| HS Q&A | 1 | Help & support Q&A |

**7 spaces skipped** (test/empty/duplicate): Copy of Revelator Labs, revvy-test-space-82791, Copy of Revelator API, POCRevvy, 2× Untitled, HelpDesk.

### Freshdesk Helpdesk (⏸️ DEFERRED)

`helpdesk.revelator.com` — V1 API only (V2 returns 404). Contains FAQ, onboarding, release management, DSP support, UGC content policies. Will be added in a later phase.

### Notion (⏸️ DEFERRED)

API key not yet available. Will be added in a later phase.

This context informs:
- Topic classification categories (Royalties, DSP, Distribution, Billing, Onboarding, NFT, Web3, API, etc.)
- Knowledge owner mapping (Product Ops, Support, Engineering teams)
- Test question design (real employee questions about these topics)

---

## 12. Confirmed Infrastructure Status

| Component | Status |
|-----------|--------|
| Cortex Search Service | ✅ Enabled and tested |
| Cortex Agent | ✅ Enabled and tested |
| Streamlit in Snowflake | ✅ Enabled and tested (container pod) |
| Freshdesk API key | ✅ Available in .env |
| GitBook API key | ✅ Available in .env |
| Notion API key | ❌ Not yet available |
| Freshdesk domain | `helpdesk.revelator.com` |

---

## 13. Data Refresh Strategy

| Schedule | Type | Scope | Purpose |
|----------|------|-------|---------|
| **Every 5 days** | Incremental | New/updated articles only | Keep search index fresh with latest changes |
| **Bi-monthly (1st & 15th, 2 AM)** | Full refresh | All sources, complete re-ingestion | Catch any missed updates, rebuild clean state |
| **On-demand** | Manual trigger | Admin-uploaded documents | Immediate availability of manually added content |

The bi-monthly full refresh ensures data integrity by:
1. Re-pulling all pages from GitBook API (10 spaces, ~306 pages)
2. Rebuilding the unified DOCUMENTS and DOCUMENT_CHUNKS tables
3. Re-running auto-classification on all documents
4. Cortex Search Service auto-refreshes within TARGET_LAG (1 hour)
5. *(Freshdesk/Notion will be added to refresh when un-deferred)*

---

## 14. Gap Analysis — Items Added Post-Research

These items were identified through the 10-agent research phase and were NOT in the original requirements:

| Gap ID | Description | Priority | Added To |
|--------|-------------|----------|----------|
| G1 | **HTML stripping for Freshdesk** — Freshdesk returns HTML content; must clean before indexing | Critical | PLAN_2 Phase 2 |
| G2 | **Title injection in chunks** — Prepend document title to each chunk for better retrieval | Critical | PLAN_2 Phase 2 |
| G3 | **Answer caching** — Cache frequent question answers to reduce latency and cost | Medium | PLAN_3 |
| G4 | **Fallback when Agent fails** — Direct Cortex Search + COMPLETE as backup | High | PLAN_2 Phase 4 |
| G5 | **Document staleness warnings** — Show "last updated X days ago" warning for old docs | High | PLAN_2 Phase 5 |
| G6 | **Question deduplication** — Cluster similar questions using embeddings for FAQ | Medium | PLAN_3 |
| G7 | **Incremental ingestion** — Track last_ingested_at for efficient incremental loads | High | PLAN_2 Phase 2 |
| G8 | **Notification integration** — Email setup for alerts (task failures, knowledge gaps) | High | PLAN_2 Phase 1 |
| G9 | **Improved system prompt** — Revelator-specific context, stricter grounding rules | Critical | PLAN_2 Phase 4 |
| G10 | **PDF upload support** — Use CORTEX.PARSE_DOCUMENT for admin PDF uploads | Medium | PLAN_3 |
| G11 | **Smart chunking** — Section-based chunking for structured docs (H2/H3 split) | Medium | PLAN_3 |
| G12 | **Cost monitoring** — Track Cortex credit consumption with alerts | Medium | PLAN_2 Phase 6 |
