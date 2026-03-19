# Internal AI Knowledge Assistant — Technical Implementation Plan
## Project Codename: **RevSearch**
## Reference: See PLAN_1_AMAZON_STYLE_SPEC.md for business requirements

---

## GitBook API Exploration Results (March 2026)

> Discovered via live API exploration using GitBook API v1 (`https://api.gitbook.com/v1`).
> Auth: Bearer token, user `meira@revelator.com` (Meira Rahamim).

### Organizations

| Org | ID |
|-----|----|
| Revelator | `TtdEwjBDdVcxf2N1XKSI` |
| POCRevvy | `w6093MHpvwKToCRVBt6S` |

### API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/orgs` | List all orgs for authenticated user |
| `GET /v1/orgs/{id}/spaces` | List spaces per org (**not** `/v1/spaces`) |
| `GET /v1/spaces/{id}/content` | Full recursive page tree for a space |
| `GET /v1/spaces/{id}/content/page/{pageId}` | Page detail with structured document nodes |
| `GET /v1/orgs/{id}/collections` | Collections per org (**not** per space) |

### Content Format

Pages return **structured document nodes**, NOT markdown. Response shape:
```json
{
  "id": "...",
  "title": "...",
  "document": {
    "nodes": [
      { "type": "heading-1", "nodes": [{ "leaves": [{ "text": "..." }] }] },
      { "type": "paragraph", "nodes": [{ "leaves": [{ "text": "...", "marks": [] }] }] },
      { "type": "list-unordered", "nodes": [{ "type": "list-item", "nodes": [...] }] }
    ]
  }
}
```
Node types: `heading-1..heading-3`, `paragraph`, `list-unordered`, `list-ordered`, `list-item`, `code`, `blockquote`, `hint`, `table`, `images`, `tabs`, `swagger`.
Text extraction: `node.nodes[].leaves[].text`, formatting in `marks[]`.
**INGEST_GITBOOK must convert document nodes → plain text (no markdown endpoint exists).**

### Spaces — Worth Ingesting (10 spaces, ~306 pages)

| Space | ID | Org | Pages | Visibility |
|-------|-----|-----|-------|------------|
| Revelator Pro | `-MEiW8xrgQlP3-v0URKN` | Revelator | 138 | public |
| Revelator Labs | `49lBWSCXQFq3YGRsWAXQ` | Revelator | 37 | private |
| Revelator NFT | `0d42YQdL3XYb3luJAPml` | Revelator | 19 | private |
| Revelator NFT - closed beta | `b8fWWMibpoQPDE8c4bNU` | Revelator | 25 | private |
| Revelator Wallet | `6EV0C5Tj7N6vgV31huTC` | Revelator | 20 | public |
| Revelator Onboarding | `-MEhYn3_AWu0YUP8Nex5` | Revelator | 12 | public |
| Revelator API | `iMjnl88bO52hFfU06D2S` | Revelator | 8 | public |
| Web3 API | `j7aR5bZPcW93Y3GaPQ6Y` | Revelator | 5 | private |
| Data Pro User Guide | `7rxGLsjuchCZnYivHpjd` | POCRevvy | 31 | private |
| HS Q&A | `kA6L5ph2xG5uY0BHLf9p` | Revelator | 1 | private |

### Spaces — Skip (7 spaces, ~144 pages — test/empty/duplicate)

| Space | ID | Reason |
|-------|----|--------|
| Copy of Revelator Labs | `MrHXgW2jdKgv8Y7c0wSU` | duplicate |
| revvy-test-space-82791 | `DiFtdEKGyDkbKD9Tsb1b` | test data |
| Copy of Revelator API | `lXHq7lsBry23eg9Mvktx` | duplicate |
| POCRevvy | `O8uSos1Fe25XRS2l6MhB` | test |
| Untitled | `T3F6jlXMBoPcreFBmXaD` | empty |
| HelpDesk | `mWh49nn1fFTt7s05kEQq` | empty |
| Untitled | `lbAOpV8iERyMzty9TCzw` | empty |

### Collections

All 4 collections (across both orgs) are **empty** — no items. Endpoint is per-org (`/v1/orgs/{id}/collections`), not per-space.

---

## PHASE 1: FOUNDATION (Week 1)
### Agent Assignment: Infrastructure Agent

### 1.1 Database & Schema Setup

```sql
-- Master database
CREATE DATABASE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE;

-- Schemas by domain
CREATE SCHEMA IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW;          -- Staging tables from APIs
CREATE SCHEMA IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.CURATED;       -- Processed documents and chunks
CREATE SCHEMA IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.SEARCH;        -- Cortex Search Service
CREATE SCHEMA IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.AGENTS;        -- Cortex Agent definitions
CREATE SCHEMA IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.ANALYTICS;     -- Questions, feedback, dynamic tables
CREATE SCHEMA IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.ADMIN;         -- Knowledge owners, config
CREATE SCHEMA IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.INGESTION;     -- Stored procedures, tasks
CREATE SCHEMA IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.APP;           -- Streamlit application
```

### 1.2 Role Hierarchy

```sql
-- Application roles
CREATE ROLE IF NOT EXISTS SI_ADMIN;    -- Full access: all schemas + admin panel
CREATE ROLE IF NOT EXISTS SI_USER;     -- Read access: search + FAQ dashboard
CREATE ROLE IF NOT EXISTS SI_INGESTION; -- Service role: ingestion pipelines
CREATE ROLE IF NOT EXISTS SI_AGENT;    -- Service role: Cortex Agent execution

-- Hierarchy
GRANT ROLE SI_USER TO ROLE SI_ADMIN;
GRANT ROLE SI_INGESTION TO ROLE SI_ADMIN;
GRANT ROLE SI_AGENT TO ROLE SI_ADMIN;

-- Grant database usage
GRANT USAGE ON DATABASE SNOWFLAKE_INTELLIGENCE TO ROLE SI_USER;
GRANT USAGE ON DATABASE SNOWFLAKE_INTELLIGENCE TO ROLE SI_INGESTION;
GRANT USAGE ON DATABASE SNOWFLAKE_INTELLIGENCE TO ROLE SI_AGENT;
```

### 1.3 Core Tables DDL

```sql
-- ===========================================
-- RAW SCHEMA: Staging tables (one per source)
-- ===========================================

-- ---- FRESHDESK: Helpdesk Knowledge Base (helpdesk.revelator.com) ----
-- ⏸️ DEFERRED — GitBook-first e2e. Will be enabled after GitBook pipeline validated.

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_ARTICLES (
    article_id         NUMBER,
    title              VARCHAR(1000),
    description        VARCHAR,       -- HTML content
    description_text   VARCHAR,       -- Plain text content
    folder_id          NUMBER,
    category_id        NUMBER,
    status             NUMBER,        -- 1=draft, 2=published
    agent_id           NUMBER,
    tags               VARIANT,       -- JSON array of tags
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ---- FRESHDESK: Operational Data (6 entities) ----
-- Auth: HTTP Basic (API key as username, "X" as password)
-- Base URL: https://helpdesk.revelator.com/api/v2
-- Pagination: page & per_page (max 100), Link header for next page
-- Rate limits: X-RateLimit-Total, X-RateLimit-Remaining, Retry-After on 429

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS (
    id                 NUMBER PRIMARY KEY,
    subject            VARCHAR(1000),
    description        VARCHAR,        -- HTML content
    description_text   VARCHAR,        -- Plain text
    status             NUMBER,         -- 2=open, 3=pending, 4=resolved, 5=closed
    priority           NUMBER,         -- 1=low, 2=medium, 3=high, 4=urgent
    type               VARCHAR(100),
    source             NUMBER,         -- 1=email, 2=portal, 3=phone, 7=chat, 9=feedback, 10=outbound
    requester_id       NUMBER,
    responder_id       NUMBER,
    company_id         NUMBER,
    group_id           NUMBER,
    tags               VARIANT,
    custom_fields      VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    due_by             TIMESTAMP_NTZ,
    fr_due_by          TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_CONTACTS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    email              VARCHAR(500),
    phone              VARCHAR(100),
    mobile             VARCHAR(100),
    company_id         NUMBER,
    active             BOOLEAN,
    job_title          VARCHAR(200),
    language           VARCHAR(20),
    time_zone          VARCHAR(100),
    tags               VARIANT,
    custom_fields      VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_COMPANIES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR,
    domains            VARIANT,       -- JSON array of domain strings
    industry           VARCHAR(200),
    account_tier       VARCHAR(100),
    health_score       VARCHAR(100),
    renewal_date       TIMESTAMP_NTZ,
    custom_fields      VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AGENTS (
    id                 NUMBER PRIMARY KEY,
    contact_id         NUMBER,
    name               VARCHAR(500),
    email              VARCHAR(500),
    active             BOOLEAN,
    occasional         BOOLEAN,
    job_title          VARCHAR(200),
    language           VARCHAR(20),
    time_zone          VARCHAR(100),
    group_ids          VARIANT,       -- JSON array of group IDs
    role_ids           VARIANT,       -- JSON array of role IDs
    ticket_scope       NUMBER,        -- 1=global, 2=group, 3=restricted
    available          BOOLEAN,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_GROUPS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR,
    agent_ids          VARIANT,       -- JSON array of agent IDs
    escalate_to        NUMBER,
    unassigned_for     VARCHAR(100),
    auto_ticket_assign BOOLEAN,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ---- GITBOOK: Product Documentation ----
-- Auth: Bearer token
-- Base URL: https://api.gitbook.com/v1
-- Data selectors: most list endpoints return { items: [...] }

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_SPACES (
    space_id           VARCHAR(100) PRIMARY KEY,
    title              VARCHAR(1000),
    description        VARCHAR(2000),
    visibility         VARCHAR(50),
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    urls               VARIANT,       -- public URL info
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'gitbook'
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_PAGES (
    page_id            VARCHAR(100),
    space_id           VARCHAR(100),
    space_title        VARCHAR(500),
    title              VARCHAR(1000),
    description        VARCHAR(2000),
    path               VARCHAR(2000),  -- URL path
    content_markdown   VARCHAR,        -- Full markdown content
    parent_page_id     VARCHAR(100),
    kind               VARCHAR(50),    -- page type (document, group, link)
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'gitbook'
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_COLLECTIONS (
    collection_id      VARCHAR(100) PRIMARY KEY,
    space_id           VARCHAR(100),
    title              VARCHAR(1000),
    description        VARCHAR(2000),
    path               VARCHAR(2000),
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'gitbook'
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.NOTION_PAGES (
    page_id            VARCHAR(100),
    database_id        VARCHAR(100),
    title              VARCHAR(1000),
    content_markdown   VARCHAR,        -- Converted from blocks
    parent_type        VARCHAR(50),
    parent_id          VARCHAR(100),
    created_by         VARCHAR(200),
    last_edited_by     VARCHAR(200),
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    properties         VARIANT,        -- All Notion properties as JSON
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'notion'
);

-- ===========================================
-- CURATED SCHEMA: Unified document model
-- ===========================================

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS (
    document_id        VARCHAR(64) PRIMARY KEY,  -- SHA-256 of source_system + source_id
    source_system      VARCHAR(20) NOT NULL,      -- freshdesk | gitbook | notion
    source_id          VARCHAR(200) NOT NULL,     -- Original ID in source system
    source_url         VARCHAR(2000),             -- Link back to original
    title              VARCHAR(1000) NOT NULL,
    content            VARCHAR NOT NULL,          -- Full document content (plain text)
    content_length     NUMBER,                    -- Character count
    team               VARCHAR(200),              -- Assigned team
    topic              VARCHAR(200),              -- Primary topic
    product_area       VARCHAR(200),              -- Product area classification
    owner              VARCHAR(200),              -- Primary knowledge owner
    backup_owner       VARCHAR(200),              -- Backup knowledge owner
    tags               VARIANT,                   -- JSON array of tags
    status             VARCHAR(20) DEFAULT 'active', -- active | archived
    created_at         TIMESTAMP_NTZ,
    last_updated       TIMESTAMP_NTZ,
    ingested_at        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    metadata           VARIANT,                   -- Additional source-specific metadata
    UNIQUE (source_system, source_id)
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS (
    chunk_id           VARCHAR(64) PRIMARY KEY,   -- SHA-256 of document_id + chunk_index
    document_id        VARCHAR(64) NOT NULL REFERENCES SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS(document_id),
    chunk_index        NUMBER NOT NULL,           -- Order within document
    content            VARCHAR NOT NULL,          -- Chunk text (512-1024 tokens)
    content_length     NUMBER,
    title              VARCHAR(1000),             -- Inherited from parent document
    team               VARCHAR(200),
    topic              VARCHAR(200),
    product_area       VARCHAR(200),
    source_system      VARCHAR(20),
    source_url         VARCHAR(2000),
    owner              VARCHAR(200),
    backup_owner       VARCHAR(200),
    last_updated       TIMESTAMP_NTZ,
    status             VARCHAR(20) DEFAULT 'active',
    created_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ===========================================
-- ANALYTICS SCHEMA: Question & feedback tracking
-- ===========================================

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS (
    question_id        VARCHAR(64) PRIMARY KEY DEFAULT UUID_STRING(),
    question_text      VARCHAR(5000) NOT NULL,
    user_name          VARCHAR(200),
    user_email         VARCHAR(500),
    user_team          VARCHAR(200),
    date_asked         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    answer             VARCHAR,
    answer_strength    VARCHAR(20),    -- strong | medium | weak | no_answer
    sources_used       VARIANT,        -- JSON array of {document_id, title, chunk_id, score}
    knowledge_owner    VARIANT,        -- JSON: {primary, backup, contact}
    related_questions  VARIANT,        -- JSON array of related question strings
    response_latency_ms NUMBER,
    model_used         VARCHAR(100),
    session_id         VARCHAR(100)
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK (
    feedback_id        VARCHAR(64) PRIMARY KEY DEFAULT UUID_STRING(),
    question_id        VARCHAR(64) NOT NULL,
    feedback_type      VARCHAR(20) NOT NULL,  -- thumbs_up | thumbs_down
    feedback_text      VARCHAR(2000),          -- Optional free-text feedback
    user_name          VARCHAR(200),
    created_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ===========================================
-- ADMIN SCHEMA: Knowledge owners & config
-- ===========================================

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.ADMIN.KNOWLEDGE_OWNERS (
    owner_id           VARCHAR(64) PRIMARY KEY DEFAULT UUID_STRING(),
    name               VARCHAR(200) NOT NULL,
    team               VARCHAR(200) NOT NULL,
    expertise_topics   VARIANT NOT NULL,       -- JSON array of topic strings
    product_areas      VARIANT,                -- JSON array of product area strings
    contact_method     VARCHAR(500),           -- Slack channel or email
    backup_for         VARCHAR(200),           -- Name of person they back up
    is_active          BOOLEAN DEFAULT TRUE,
    created_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.ADMIN.SYSTEM_CONFIG (
    config_key         VARCHAR(200) PRIMARY KEY,
    config_value       VARIANT,
    description        VARCHAR(1000),
    updated_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_by         VARCHAR(200)
);
```

### 1.4 Credential Management (Secrets & External Access)

```sql
-- =============================================
-- SECRETS: Store API keys securely in Snowflake
-- =============================================

CREATE OR REPLACE SECRET SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET
    TYPE = GENERIC_STRING
    SECRET_STRING = '<from .env: FRESHDESK_API>';

CREATE OR REPLACE SECRET SNOWFLAKE_INTELLIGENCE.INGESTION.GITBOOK_API_SECRET
    TYPE = GENERIC_STRING
    SECRET_STRING = '<from .env: GITBOOK_API>';

CREATE OR REPLACE SECRET SNOWFLAKE_INTELLIGENCE.INGESTION.NOTION_API_SECRET
    TYPE = GENERIC_STRING
    SECRET_STRING = '<from .env: NOTION_API - TO BE PROVIDED>';

-- =============================================
-- NETWORK RULES: Allow outbound API calls
-- =============================================

CREATE OR REPLACE NETWORK RULE SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_NETWORK_RULE
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = ('helpdesk.revelator.com');

CREATE OR REPLACE NETWORK RULE SNOWFLAKE_INTELLIGENCE.INGESTION.GITBOOK_NETWORK_RULE
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = ('api.gitbook.com');

CREATE OR REPLACE NETWORK RULE SNOWFLAKE_INTELLIGENCE.INGESTION.NOTION_NETWORK_RULE
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = ('api.notion.com');

-- =============================================
-- EXTERNAL ACCESS INTEGRATIONS
-- =============================================

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION SI_FRESHDESK_ACCESS
    ALLOWED_NETWORK_RULES = (SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_NETWORK_RULE)
    ALLOWED_AUTHENTICATION_SECRETS = (SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET)
    ENABLED = TRUE;

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION SI_GITBOOK_ACCESS
    ALLOWED_NETWORK_RULES = (SNOWFLAKE_INTELLIGENCE.INGESTION.GITBOOK_NETWORK_RULE)
    ALLOWED_AUTHENTICATION_SECRETS = (SNOWFLAKE_INTELLIGENCE.INGESTION.GITBOOK_API_SECRET)
    ENABLED = TRUE;

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION SI_NOTION_ACCESS
    ALLOWED_NETWORK_RULES = (SNOWFLAKE_INTELLIGENCE.INGESTION.NOTION_NETWORK_RULE)
    ALLOWED_AUTHENTICATION_SECRETS = (SNOWFLAKE_INTELLIGENCE.INGESTION.NOTION_API_SECRET)
    ENABLED = TRUE;
```

### 1.5 Warehouse Setup

```sql
-- Using existing warehouses (no new warehouses needed):
--   AI_WH (XS)        → Ingestion tasks, Cortex Search Service, Cortex Agent, Dynamic Tables, Alerts
--   STREAMLIT_WH (XS) → Streamlit in Snowflake application (query warehouse)
```

---

## PHASE 2: DATA INGESTION (Week 2)
### Agent Assignment: Ingestion Agent

### 2.1 Freshdesk Helpdesk Knowledge Base Ingestion (INGEST_HELPDESK)

Ingests solution articles from helpdesk.revelator.com (knowledge base content for RAG search).

```sql
CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_HELPDESK()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'requests')
HANDLER = 'run'
EXTERNAL_ACCESS_INTEGRATIONS = (SI_FRESHDESK_ACCESS)
SECRETS = ('api_key' = SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET)
AS
$$
import requests
import json
import re
import time
import _snowflake
from html import unescape
from snowflake.snowpark import Session

FRESHDESK_DOMAIN = "helpdesk.revelator.com"

def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def api_get(url, auth, headers, retries=3):
    for attempt in range(retries):
        resp = requests.get(url, auth=auth, headers=headers)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get('Retry-After', 30))
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp.json()
    raise Exception(f"Rate limited after {retries} retries: {url}")

def run(session):
    api_key = _snowflake.get_generic_secret_string('api_key')
    base_url = f"https://{FRESHDESK_DOMAIN}"
    headers = {"Content-Type": "application/json"}
    auth = (api_key, "X")

    # V1 API: /solution/categories.json → /solution/categories/{id}/folders.json → .../articles.json
    categories_raw = api_get(f"{base_url}/solution/categories.json", auth, headers)

    articles = []
    for cat_wrapper in categories_raw:
        category = cat_wrapper.get("category", cat_wrapper)
        cat_id = category["id"]
        folders_raw = api_get(
            f"{base_url}/solution/categories/{cat_id}/folders.json",
            auth, headers
        )
        for folder_wrapper in folders_raw:
            folder = folder_wrapper.get("folder", folder_wrapper)
            folder_id = folder["id"]
            articles_raw = api_get(
                f"{base_url}/solution/categories/{cat_id}/folders/{folder_id}/articles.json",
                auth, headers
            )
            for art_wrapper in articles_raw:
                article = art_wrapper.get("article", art_wrapper)
                articles.append({
                    "article_id": article["id"],
                    "title": article.get("title", ""),
                    "description": article.get("description", ""),
                    "description_text": clean_html(article.get("description", "")),
                    "folder_id": folder_id,
                    "category_id": cat_id,
                    "status": article.get("status", 1),
                    "agent_id": article.get("agent_id"),
                    "tags": json.dumps(article.get("tags", [])),
                    "created_at": article.get("created_at"),
                    "updated_at": article.get("updated_at"),
                })

    if articles:
        df = session.create_dataframe(articles)
        df.write.mode("overwrite").save_as_table("SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_ARTICLES")

    session.sql("""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
            (source_system, ingestion_type, started_at, completed_at, records_ingested, status)
        SELECT 'freshdesk_kb', 'full', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), """ + str(len(articles)) + """, 'success'
    """).collect()

    return f"Ingested {len(articles)} helpdesk knowledge base articles"
$$;
```

### 2.2 Freshdesk Operational Data Ingestion (INGEST_FRESHDESK)

> ⏸️ **DEFERRED — GitBook-first e2e.** This proc will be enabled after GitBook pipeline is validated end-to-end.

Ingests 5 operational entities via Freshdesk V1 API: tickets, contacts, companies, agents, groups.
Note: Roles endpoint not available in V1 API — FRESHDESK_ROLES table removed.

```sql
CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'requests')
HANDLER = 'run'
EXTERNAL_ACCESS_INTEGRATIONS = (SI_FRESHDESK_ACCESS)
SECRETS = ('api_key' = SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET)
AS
$$
import requests
import json
import re
import time
import _snowflake
from html import unescape
from snowflake.snowpark import Session

FRESHDESK_DOMAIN = "helpdesk.revelator.com"

def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def api_get_paginated(base_url, endpoint, auth, headers, per_page=100, max_pages=500, wrapper_key=None):
    """Fetch paginated V1 API results. wrapper_key unwraps V1 nested objects like {"user": {...}}."""
    all_items = []
    page = 1
    while page <= max_pages:
        url = f"{base_url}/{endpoint}?per_page={per_page}&page={page}"
        resp = requests.get(url, auth=auth, headers=headers)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get('Retry-After', 30))
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        if wrapper_key:
            data = [item.get(wrapper_key, item) for item in data]
        all_items.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return all_items

def run(session):
    api_key = _snowflake.get_generic_secret_string('api_key')
    base_url = f"https://{FRESHDESK_DOMAIN}"
    headers = {"Content-Type": "application/json"}
    auth = (api_key, "X")

    counts = {}

    # --- TICKETS (V1: /helpdesk/tickets.json, flat structure) ---
    tickets_raw = api_get_paginated(base_url, "helpdesk/tickets.json", auth, headers)
    tickets = []
    for t in tickets_raw:
        tickets.append({
            "id": t["id"],
            "subject": t.get("subject", ""),
            "description": t.get("description", ""),
            "description_text": clean_html(t.get("description", "")),
            "status": t.get("status"),
            "priority": t.get("priority"),
            "type": t.get("ticket_type"),
            "source": t.get("source"),
            "requester_id": t.get("requester_id"),
            "responder_id": t.get("responder_id"),
            "company_id": t.get("department_id"),
            "group_id": t.get("group_id"),
            "tags": json.dumps(t.get("tags", [])),
            "custom_fields": json.dumps(t.get("custom_field", {})),
            "created_at": t.get("created_at"),
            "updated_at": t.get("updated_at"),
            "due_by": t.get("due_by"),
            "fr_due_by": t.get("frDueBy"),
        })
    if tickets:
        session.create_dataframe(tickets).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS")
    counts["tickets"] = len(tickets)

    # --- CONTACTS (V1: /contacts.json, wrapped in {"user": {...}}) ---
    contacts_raw = api_get_paginated(base_url, "contacts.json", auth, headers, wrapper_key="user")
    contacts = []
    for c in contacts_raw:
        contacts.append({
            "id": c["id"],
            "name": c.get("name", ""),
            "email": c.get("email", ""),
            "phone": c.get("phone"),
            "mobile": c.get("mobile"),
            "company_id": c.get("customer_id"),
            "active": c.get("active", True),
            "job_title": c.get("job_title"),
            "language": c.get("language"),
            "time_zone": c.get("time_zone"),
            "tags": json.dumps(c.get("tags", [])),
            "custom_fields": json.dumps(c.get("custom_field", {})),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
        })
    if contacts:
        session.create_dataframe(contacts).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_CONTACTS")
    counts["contacts"] = len(contacts)

    # --- COMPANIES (V1: /companies.json, wrapped in {"company": {...}}) ---
    companies_raw = api_get_paginated(base_url, "companies.json", auth, headers, wrapper_key="company")
    companies = []
    for co in companies_raw:
        companies.append({
            "id": co["id"],
            "name": co.get("name", ""),
            "description": co.get("description", ""),
            "domains": json.dumps(co.get("domains", [])),
            "industry": co.get("industry"),
            "account_tier": co.get("account_tier"),
            "health_score": co.get("health_score"),
            "renewal_date": co.get("renewal_date"),
            "custom_fields": json.dumps(co.get("custom_fields", {})),
            "created_at": co.get("created_at"),
            "updated_at": co.get("updated_at"),
        })
    if companies:
        session.create_dataframe(companies).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_COMPANIES")
    counts["companies"] = len(companies)

    # --- AGENTS (V1: /agents.json, wrapped in {"agent": {...}}) ---
    agents_raw = api_get_paginated(base_url, "agents.json", auth, headers, wrapper_key="agent")
    agents = []
    for a in agents_raw:
        agents.append({
            "id": a["id"],
            "user_id": a.get("user_id"),
            "name": a.get("user", {}).get("name", "") if isinstance(a.get("user"), dict) else "",
            "email": a.get("user", {}).get("email", "") if isinstance(a.get("user"), dict) else "",
            "active": a.get("user", {}).get("active", True) if isinstance(a.get("user"), dict) else True,
            "occasional": a.get("occasional", False),
            "ticket_permission": a.get("ticket_permission"),
            "signature": a.get("signature", ""),
            "group_ids": json.dumps(a.get("group_ids", [])),
            "role_ids": json.dumps(a.get("role_ids", [])),
            "available": a.get("available", True),
            "created_at": a.get("created_at"),
            "updated_at": a.get("updated_at"),
        })
    if agents:
        session.create_dataframe(agents).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AGENTS")
    counts["agents"] = len(agents)

    # --- GROUPS (V1: /groups.json, wrapped in {"group": {...}}) ---
    groups_raw = api_get_paginated(base_url, "groups.json", auth, headers, wrapper_key="group")
    groups = []
    for g in groups_raw:
        groups.append({
            "id": g["id"],
            "name": g.get("name", ""),
            "description": g.get("description", ""),
            "agent_ids": json.dumps(g.get("agents", [])),
            "escalate_to": g.get("escalate_to"),
            "group_type": g.get("group_type"),
            "auto_ticket_assign": g.get("ticket_assign_type", 0),
            "created_at": g.get("created_at"),
            "updated_at": g.get("updated_at"),
        })
    if groups:
        session.create_dataframe(groups).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_GROUPS")
    counts["groups"] = len(groups)

    session.sql("""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
            (source_system, ingestion_type, started_at, completed_at, records_ingested, status)
        SELECT 'freshdesk_ops', 'full', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
            """ + str(sum(counts.values())) + """, 'success'
    """).collect()

    return f"Ingested Freshdesk: {counts}"
$$;
```

### 2.3 GitBook Ingestion Stored Procedure (INGEST_GITBOOK)

Ingests spaces, pages (with content), and collections from GitBook API v1.
- **Space allow-list**: Only ingests the 10 spaces identified as worth ingesting (~306 pages).
- **Document node→text**: Converts structured document nodes to plain text (no markdown endpoint exists).
- **Collections**: Fetched per-org (not per-space). Currently all empty.

```sql
CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_GITBOOK()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'requests')
HANDLER = 'run'
EXTERNAL_ACCESS_INTEGRATIONS = (SI_GITBOOK_ACCESS)
SECRETS = ('api_key' = SNOWFLAKE_INTELLIGENCE.INGESTION.GITBOOK_API_SECRET)
AS
$$
import requests
import json
import time
import _snowflake
from snowflake.snowpark import Session

ALLOWED_SPACE_IDS = {
    "-MEiW8xrgQlP3-v0URKN",  # Revelator Pro (138 pages)
    "49lBWSCXQFq3YGRsWAXQ",  # Revelator Labs (37 pages)
    "0d42YQdL3XYb3luJAPml",  # Revelator NFT (19 pages)
    "b8fWWMibpoQPDE8c4bNU",  # Revelator NFT - closed beta (25 pages)
    "6EV0C5Tj7N6vgV31huTC",  # Revelator Wallet (20 pages)
    "-MEhYn3_AWu0YUP8Nex5",  # Revelator Onboarding (12 pages)
    "iMjnl88bO52hFfU06D2S",  # Revelator API (8 pages)
    "j7aR5bZPcW93Y3GaPQ6Y",  # Web3 API (5 pages)
    "7rxGLsjuchCZnYivHpjd",  # Data Pro User Guide (31 pages)
    "kA6L5ph2xG5uY0BHLf9p",  # HS Q&A (1 page)
}

SKIP_SPACE_IDS = {
    "MrHXgW2jdKgv8Y7c0wSU",  # Copy of Revelator Labs (duplicate)
    "DiFtdEKGyDkbKD9Tsb1b",  # revvy-test-space-82791 (test data)
    "lXHq7lsBry23eg9Mvktx",  # Copy of Revelator API (duplicate)
    "O8uSos1Fe25XRS2l6MhB",  # POCRevvy (test)
    "T3F6jlXMBoPcreFBmXaD",  # Untitled (empty)
    "mWh49nn1fFTt7s05kEQq",  # HelpDesk (empty)
    "lbAOpV8iERyMzty9TCzw",  # Untitled (empty)
}

def api_get(url, headers, retries=3):
    for attempt in range(retries):
        resp = requests.get(url, headers=headers)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get('Retry-After', 30))
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp.json()
    raise Exception(f"Rate limited after {retries} retries: {url}")

def nodes_to_text(nodes, depth=0):
    """Convert GitBook document nodes to plain text.

    GitBook pages return structured document nodes (not markdown).
    Each node has a type and nested nodes/leaves containing text.
    """
    parts = []
    for node in nodes:
        node_type = node.get("type", "")
        children = node.get("nodes", [])

        if node_type in ("heading-1", "heading-2", "heading-3"):
            prefix = "#" * int(node_type[-1]) + " "
            text = extract_leaves(children)
            parts.append(f"\n{prefix}{text}\n")

        elif node_type == "paragraph":
            text = extract_leaves(children)
            if text.strip():
                parts.append(text)

        elif node_type in ("list-unordered", "list-ordered"):
            for i, item in enumerate(children):
                item_children = item.get("nodes", [])
                bullet = f"{i+1}." if node_type == "list-ordered" else "-"
                text = nodes_to_text(item_children, depth + 1)
                parts.append(f"{bullet} {text}")

        elif node_type == "list-item":
            text = nodes_to_text(children, depth)
            parts.append(text)

        elif node_type == "code":
            text = extract_leaves(children)
            parts.append(f"```\n{text}\n```")

        elif node_type in ("blockquote", "hint"):
            text = nodes_to_text(children, depth)
            parts.append(f"> {text}")

        elif node_type == "table":
            for row in children:
                cells = row.get("nodes", [])
                row_text = " | ".join(nodes_to_text(c.get("nodes", []), depth) for c in cells)
                parts.append(f"| {row_text} |")

        elif node_type == "tabs":
            for tab in children:
                tab_title = tab.get("title", "")
                tab_text = nodes_to_text(tab.get("nodes", []), depth)
                parts.append(f"[Tab: {tab_title}]\n{tab_text}")

        elif node_type == "swagger":
            parts.append(f"[API Reference: {node.get('data', {}).get('url', '')}]")

        elif node_type == "images":
            for img in children:
                caption = img.get("caption", "")
                parts.append(f"[Image: {caption}]" if caption else "[Image]")

        else:
            text = extract_leaves(children)
            if text.strip():
                parts.append(text)
            elif children:
                parts.append(nodes_to_text(children, depth))

    return "\n".join(parts)

def extract_leaves(nodes):
    """Extract text from leaf nodes."""
    texts = []
    for node in nodes:
        leaves = node.get("leaves", [])
        if leaves:
            for leaf in leaves:
                texts.append(leaf.get("text", ""))
        elif "nodes" in node:
            texts.append(extract_leaves(node["nodes"]))
    return "".join(texts)

def run(session):
    api_key = _snowflake.get_generic_secret_string('api_key')
    base_url = "https://api.gitbook.com/v1"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # --- SPACES (via organizations, filtered by allow-list) ---
    orgs_data = api_get(f"{base_url}/orgs", headers)
    orgs_list = orgs_data.get("items", [])

    spaces_list = []
    spaces = []
    skipped = []
    for org in orgs_list:
        org_id = org["id"]
        try:
            org_spaces = api_get(f"{base_url}/orgs/{org_id}/spaces", headers)
            for s in org_spaces.get("items", []):
                if s["id"] in SKIP_SPACE_IDS:
                    skipped.append(s.get("title", s["id"]))
                    continue
                if s["id"] not in ALLOWED_SPACE_IDS:
                    skipped.append(s.get("title", s["id"]))
                    continue
                spaces_list.append(s)
                spaces.append({
                    "space_id": s["id"],
                    "title": s.get("title", ""),
                    "description": s.get("description", ""),
                    "visibility": s.get("visibility", ""),
                    "created_at": s.get("createdAt"),
                    "updated_at": s.get("updatedAt"),
                    "urls": json.dumps(s.get("urls", {})),
                })
        except Exception:
            continue

    if spaces:
        session.create_dataframe(spaces).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_SPACES")

    # --- PAGES (per allowed space, recursive with document node→text) ---
    pages = []
    for space in spaces_list:
        space_id = space["id"]
        space_title = space.get("title", "")

        try:
            content_data = api_get(f"{base_url}/spaces/{space_id}/content", headers)
            page_list = content_data.get("pages", [])
        except Exception:
            continue

        def process_pages(page_list, parent_id=None):
            for page in page_list:
                page_id = page.get("id", "")
                content_text = ""
                try:
                    page_detail = api_get(
                        f"{base_url}/spaces/{space_id}/content/page/{page_id}",
                        headers
                    )
                    doc = page_detail.get("document", {})
                    doc_nodes = doc.get("nodes", [])
                    content_text = nodes_to_text(doc_nodes) if doc_nodes else ""
                except Exception:
                    content_text = page.get("description", "")

                pages.append({
                    "page_id": page_id,
                    "space_id": space_id,
                    "space_title": space_title,
                    "title": page.get("title", ""),
                    "description": page.get("description", ""),
                    "path": page.get("path", ""),
                    "content_markdown": content_text,
                    "parent_page_id": parent_id,
                    "kind": page.get("kind", "document"),
                    "created_at": page.get("createdAt"),
                    "updated_at": page.get("updatedAt"),
                })

                if "pages" in page:
                    process_pages(page["pages"], page_id)

        process_pages(page_list)

    if pages:
        session.create_dataframe(pages).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_PAGES")

    # --- COLLECTIONS (per org, not per space) ---
    collections = []
    for org in orgs_list:
        org_id = org["id"]
        try:
            coll_data = api_get(f"{base_url}/orgs/{org_id}/collections", headers)
            for c in coll_data.get("items", []):
                collections.append({
                    "collection_id": c["id"],
                    "org_id": org_id,
                    "title": c.get("title", ""),
                    "description": c.get("description", ""),
                    "path": c.get("path", ""),
                    "created_at": c.get("createdAt"),
                    "updated_at": c.get("updatedAt"),
                })
        except Exception:
            pass

    if collections:
        session.create_dataframe(collections).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_COLLECTIONS")

    session.sql("""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
            (source_system, ingestion_type, started_at, completed_at, records_ingested, status)
        SELECT 'gitbook', 'full', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
            """ + str(len(spaces) + len(pages) + len(collections)) + """, 'success'
    """).collect()

    return (f"Ingested GitBook: {len(spaces)} spaces, {len(pages)} pages, "
            f"{len(collections)} collections. Skipped: {skipped}")
$$;
```

### 2.4 Notion Ingestion Stored Procedure

```sql
CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_NOTION()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'requests')
HANDLER = 'run'
EXTERNAL_ACCESS_INTEGRATIONS = (SI_NOTION_ACCESS)
SECRETS = ('api_key' = SNOWFLAKE_INTELLIGENCE.INGESTION.NOTION_API_SECRET)
AS
$$
import requests
import json
import _snowflake
from snowflake.snowpark import Session

def run(session):
    api_key = _snowflake.get_generic_secret_string('api_key')
    base_url = "https://api.notion.com/v1"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    def get_block_children(block_id):
        """Recursively get all block children and convert to markdown."""
        blocks = []
        url = f"{base_url}/blocks/{block_id}/children"
        has_more = True
        start_cursor = None

        while has_more:
            params = {"page_size": 100}
            if start_cursor:
                params["start_cursor"] = start_cursor
            resp = requests.get(url, headers=headers, params=params).json()
            blocks.extend(resp.get("results", []))
            has_more = resp.get("has_more", False)
            start_cursor = resp.get("next_cursor")

        return blocks_to_markdown(blocks)

    def blocks_to_markdown(blocks):
        """Convert Notion blocks to markdown text."""
        md_parts = []
        for block in blocks:
            block_type = block.get("type", "")
            block_data = block.get(block_type, {})

            if block_type in ["paragraph", "bulleted_list_item", "numbered_list_item",
                              "heading_1", "heading_2", "heading_3"]:
                rich_texts = block_data.get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_texts])

                if block_type == "heading_1":
                    text = f"# {text}"
                elif block_type == "heading_2":
                    text = f"## {text}"
                elif block_type == "heading_3":
                    text = f"### {text}"
                elif block_type == "bulleted_list_item":
                    text = f"- {text}"
                elif block_type == "numbered_list_item":
                    text = f"1. {text}"

                md_parts.append(text)

            elif block_type == "code":
                rich_texts = block_data.get("rich_text", [])
                code = "".join([rt.get("plain_text", "") for rt in rich_texts])
                lang = block_data.get("language", "")
                md_parts.append(f"```{lang}\n{code}\n```")

            elif block_type == "table":
                pass  # Simplified: skip complex table parsing

            if block.get("has_children", False):
                child_md = get_block_children(block["id"])
                md_parts.append(child_md)

        return "\n\n".join(md_parts)

    def get_page_title(page):
        """Extract title from Notion page properties."""
        props = page.get("properties", {})
        for prop_name, prop_data in props.items():
            if prop_data.get("type") == "title":
                title_parts = prop_data.get("title", [])
                return "".join([t.get("plain_text", "") for t in title_parts])
        return "Untitled"

    # Search all pages accessible to the integration
    all_pages = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {"filter": {"value": "page", "property": "object"}, "page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        resp = requests.post(f"{base_url}/search", headers=headers, json=payload).json()
        all_pages.extend(resp.get("results", []))
        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")

    pages = []
    for page in all_pages:
        page_id = page["id"]
        title = get_page_title(page)
        content_md = get_block_children(page_id)

        parent = page.get("parent", {})
        parent_type = parent.get("type", "")
        parent_id = parent.get(parent_type, "")

        pages.append({
            "page_id": page_id,
            "database_id": parent_id if parent_type == "database_id" else None,
            "title": title,
            "content_markdown": content_md,
            "parent_type": parent_type,
            "parent_id": str(parent_id),
            "created_by": page.get("created_by", {}).get("id", ""),
            "last_edited_by": page.get("last_edited_by", {}).get("id", ""),
            "created_at": page.get("created_time"),
            "updated_at": page.get("last_edited_time"),
            "properties": json.dumps(page.get("properties", {})),
        })

    if pages:
        df = session.create_dataframe(pages)
        df.write.mode("overwrite").save_as_table("SNOWFLAKE_INTELLIGENCE.RAW.NOTION_PAGES")

    return f"Ingested {len(pages)} Notion pages"
$$;
```

### 2.4 Document Unification & Chunking Procedure

```sql
CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.PROCESS_DOCUMENTS()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
AS
$$
import hashlib
import json
import re
from html import unescape
from snowflake.snowpark import Session
from snowflake.snowpark.functions import col, lit, current_timestamp

CHUNK_SIZE = 1500        # ~375-500 tokens per chunk
CHUNK_OVERLAP = 200      # ~50 token overlap

def clean_html(text):
    """[GAP G1] Strip HTML tags and normalize text from Freshdesk content."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def chunk_text(text, title=None, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks. [GAP G2] Prepends title to first chunk."""
    if not text or len(text.strip()) < 50:
        return []
    
    if len(text) <= chunk_size:
        chunk = f"Title: {title}\n\n{text}" if title else text
        return [chunk]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        if end < len(text):
            for sep in ['\n\n', '\n', '. ', '? ', '! ']:
                last_break = chunk.rfind(sep)
                if last_break > chunk_size * 0.5:
                    chunk = chunk[:last_break + len(sep)]
                    end = start + last_break + len(sep)
                    break

        if start == 0 and title:
            chunk = f"Title: {title}\n\n{chunk.strip()}"
        else:
            chunks_text = chunk.strip()
            chunk = chunks_text

        chunks.append(chunk.strip())
        start = end - overlap

    return chunks

def make_id(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]

def run(session):
    total_docs = 0
    total_chunks = 0

    # Process Freshdesk articles
    try:
        fd = session.table("SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_ARTICLES").collect()
        for row in fd:
            doc_id = make_id("freshdesk", row["ARTICLE_ID"])
            content = clean_html(row["DESCRIPTION_TEXT"] or row["DESCRIPTION"] or "")
            if not content.strip():
                continue

            doc = {
                "DOCUMENT_ID": doc_id,
                "SOURCE_SYSTEM": "freshdesk",
                "SOURCE_ID": str(row["ARTICLE_ID"]),
                "SOURCE_URL": f"https://helpdesk.revelator.com/support/solutions/articles/{row['ARTICLE_ID']}",
                "TITLE": row["TITLE"] or "Untitled",
                "CONTENT": content,
                "CONTENT_LENGTH": len(content),
                "TEAM": None,
                "TOPIC": None,
                "PRODUCT_AREA": None,
                "OWNER": None,
                "BACKUP_OWNER": None,
                "TAGS": json.dumps([]),
                "STATUS": "active" if row["STATUS"] == 2 else "draft",
                "CREATED_AT": row["CREATED_AT"],
                "LAST_UPDATED": row["UPDATED_AT"],
                "METADATA": json.dumps({"folder_id": row["FOLDER_ID"], "category_id": row["CATEGORY_ID"]}),
            }

            session.create_dataframe([doc]).write.mode("append").save_as_table("SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS")
            total_docs += 1

            # Chunk the document — [GAP G2] title injected into first chunk
            chunks_text = chunk_text(content, title=doc["TITLE"])
            for i, chunk in enumerate(chunks_text):
                chunk_row = {
                    "CHUNK_ID": make_id(doc_id, i),
                    "DOCUMENT_ID": doc_id,
                    "CHUNK_INDEX": i,
                    "CONTENT": chunk,
                    "CONTENT_LENGTH": len(chunk),
                    "TITLE": doc["TITLE"],
                    "TEAM": doc["TEAM"],
                    "TOPIC": doc["TOPIC"],
                    "PRODUCT_AREA": doc["PRODUCT_AREA"],
                    "SOURCE_SYSTEM": "freshdesk",
                    "SOURCE_URL": doc["SOURCE_URL"],
                    "OWNER": doc["OWNER"],
                    "BACKUP_OWNER": doc["BACKUP_OWNER"],
                    "LAST_UPDATED": doc["LAST_UPDATED"],
                    "STATUS": doc["STATUS"],
                }
                session.create_dataframe([chunk_row]).write.mode("append").save_as_table("SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS")
                total_chunks += 1
    except Exception as e:
        pass  # Table may not exist yet

    # Process GitBook pages (same pattern)
    try:
        gb = session.table("SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_PAGES").collect()
        for row in gb:
            doc_id = make_id("gitbook", row["PAGE_ID"])
            content = row["CONTENT_MARKDOWN"] or ""
            if not content.strip():
                continue

            doc = {
                "DOCUMENT_ID": doc_id,
                "SOURCE_SYSTEM": "gitbook",
                "SOURCE_ID": str(row["PAGE_ID"]),
                "SOURCE_URL": row.get("PATH", ""),
                "TITLE": row["TITLE"] or "Untitled",
                "CONTENT": content,
                "CONTENT_LENGTH": len(content),
                "TEAM": None,
                "TOPIC": None,
                "PRODUCT_AREA": None,
                "OWNER": None,
                "BACKUP_OWNER": None,
                "TAGS": json.dumps([]),
                "STATUS": "active",
                "CREATED_AT": row["CREATED_AT"],
                "LAST_UPDATED": row["UPDATED_AT"],
                "METADATA": json.dumps({"space_id": row["SPACE_ID"], "space_title": row["SPACE_TITLE"]}),
            }

            session.create_dataframe([doc]).write.mode("append").save_as_table("SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS")
            total_docs += 1

            chunks_text = chunk_text(content)
            for i, chunk in enumerate(chunks_text):
                chunk_row = {
                    "CHUNK_ID": make_id(doc_id, i),
                    "DOCUMENT_ID": doc_id,
                    "CHUNK_INDEX": i,
                    "CONTENT": chunk,
                    "CONTENT_LENGTH": len(chunk),
                    "TITLE": doc["TITLE"],
                    "TEAM": doc["TEAM"],
                    "TOPIC": doc["TOPIC"],
                    "PRODUCT_AREA": doc["PRODUCT_AREA"],
                    "SOURCE_SYSTEM": "gitbook",
                    "SOURCE_URL": doc["SOURCE_URL"],
                    "OWNER": doc["OWNER"],
                    "BACKUP_OWNER": doc["BACKUP_OWNER"],
                    "LAST_UPDATED": doc["LAST_UPDATED"],
                    "STATUS": doc["STATUS"],
                }
                session.create_dataframe([chunk_row]).write.mode("append").save_as_table("SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS")
                total_chunks += 1
    except Exception as e:
        pass

    # Process Notion pages (same pattern)
    try:
        nt = session.table("SNOWFLAKE_INTELLIGENCE.RAW.NOTION_PAGES").collect()
        for row in nt:
            doc_id = make_id("notion", row["PAGE_ID"])
            content = row["CONTENT_MARKDOWN"] or ""
            if not content.strip():
                continue

            doc = {
                "DOCUMENT_ID": doc_id,
                "SOURCE_SYSTEM": "notion",
                "SOURCE_ID": str(row["PAGE_ID"]),
                "SOURCE_URL": f"https://notion.so/{row['PAGE_ID'].replace('-', '')}",
                "TITLE": row["TITLE"] or "Untitled",
                "CONTENT": content,
                "CONTENT_LENGTH": len(content),
                "TEAM": None,
                "TOPIC": None,
                "PRODUCT_AREA": None,
                "OWNER": None,
                "BACKUP_OWNER": None,
                "TAGS": json.dumps([]),
                "STATUS": "active",
                "CREATED_AT": row["CREATED_AT"],
                "LAST_UPDATED": row["UPDATED_AT"],
                "METADATA": json.dumps({"database_id": row["DATABASE_ID"]}),
            }

            session.create_dataframe([doc]).write.mode("append").save_as_table("SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS")
            total_docs += 1

            chunks_text = chunk_text(content)
            for i, chunk in enumerate(chunks_text):
                chunk_row = {
                    "CHUNK_ID": make_id(doc_id, i),
                    "DOCUMENT_ID": doc_id,
                    "CHUNK_INDEX": i,
                    "CONTENT": chunk,
                    "CONTENT_LENGTH": len(chunk),
                    "TITLE": doc["TITLE"],
                    "TEAM": doc["TEAM"],
                    "TOPIC": doc["TOPIC"],
                    "PRODUCT_AREA": doc["PRODUCT_AREA"],
                    "SOURCE_SYSTEM": "notion",
                    "SOURCE_URL": doc["SOURCE_URL"],
                    "OWNER": doc["OWNER"],
                    "BACKUP_OWNER": doc["BACKUP_OWNER"],
                    "LAST_UPDATED": doc["LAST_UPDATED"],
                    "STATUS": doc["STATUS"],
                }
                session.create_dataframe([chunk_row]).write.mode("append").save_as_table("SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS")
                total_chunks += 1
    except Exception as e:
        pass

    return f"Processed {total_docs} documents into {total_chunks} chunks"
$$;
```

### 2.5 Auto-Classification with Cortex AI Functions

```sql
-- After initial ingestion, auto-classify documents by topic and product area
CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.CLASSIFY_DOCUMENTS()
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    -- Auto-classify topic
    UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
    SET topic = SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        SUBSTR(content, 1, 4000),
        ['Product Documentation', 'Support Process', 'Onboarding', 'Billing Policy',
         'Operational Procedure', 'Ownership Directory', 'Technical Guide', 'FAQ',
         'Release Notes', 'Training Material']
    ):label::VARCHAR
    WHERE topic IS NULL;

    -- Auto-classify product area
    UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
    SET product_area = SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        SUBSTR(content, 1, 4000),
        ['Royalties', 'DSP', 'Distribution', 'Billing', 'Onboarding',
         'Analytics', 'Rights Management', 'Content Delivery', 'Account Management', 'General']
    ):label::VARCHAR
    WHERE product_area IS NULL;

    -- Propagate classifications to chunks
    UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS c
    SET c.topic = d.topic,
        c.product_area = d.product_area,
        c.team = d.team,
        c.owner = d.owner,
        c.backup_owner = d.backup_owner
    FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS d
    WHERE c.document_id = d.document_id;

    RETURN 'Classification complete';
END;
$$;
```

### 2.6 Ingestion Scheduling

```sql
-- =============================================
-- INGESTION TASK TREE: Runs every 5 days at 3 AM
-- ⏸️ GitBook-first e2e: Only GitBook → PROCESS → CLASSIFY active.
-- Freshdesk (HELPDESK, FRESHDESK) and Notion tasks DEFERRED.
-- =============================================

-- Root scheduled task — GitBook only for now
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_GITBOOK
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 3 */5 * * America/Los_Angeles'
    COMMENT = 'Ingest GitBook spaces, pages, and collections every 5 days'
AS
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_GITBOOK();

-- PROCESS runs after GitBook completes
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_PROCESS_DOCUMENTS
    WAREHOUSE = AI_WH
    AFTER SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_GITBOOK
    COMMENT = 'Process all ingested documents into unified chunks'
AS
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.PROCESS_DOCUMENTS();

CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_CLASSIFY_DOCUMENTS
    WAREHOUSE = AI_WH
    AFTER SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_PROCESS_DOCUMENTS
AS
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.CLASSIFY_DOCUMENTS();

-- Enable the task tree (children first, root last)
ALTER TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_CLASSIFY_DOCUMENTS RESUME;
ALTER TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_PROCESS_DOCUMENTS RESUME;
ALTER TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_GITBOOK RESUME;

-- ⏸️ DEFERRED TASKS — Will be added back when Freshdesk/Notion are enabled:
-- CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_HELPDESK ...
-- CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK ...
-- CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_NOTION ...
-- When re-enabled, use parallel DAG: HELPDESK (root) → (FRESHDESK | GITBOOK | NOTION) → PROCESS → CLASSIFY

-- =============================================
-- FULL REFRESH: Runs on 1st and 15th of month at 2 AM
-- Truncates all raw/curated tables and re-ingests everything
-- =============================================

CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.FULL_REFRESH
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 2 1,15 * * America/Los_Angeles'
    COMMENT = 'Bi-monthly full re-ingestion — GitBook only (Freshdesk/Notion deferred)'
AS
BEGIN
    -- ⏸️ DEFERRED — Freshdesk tables (uncomment when re-enabled):
    -- TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_ARTICLES;
    -- TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS;
    -- TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_CONTACTS;
    -- TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_COMPANIES;
    -- TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AGENTS;
    -- TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_GROUPS;
    TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_SPACES;
    TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_PAGES;
    TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_COLLECTIONS;
    -- ⏸️ DEFERRED: TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.RAW.NOTION_PAGES;
    -- ⏸️ DEFERRED: CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_HELPDESK();
    -- ⏸️ DEFERRED: CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK();
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_GITBOOK();
    -- ⏸️ DEFERRED: CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_NOTION();
    TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS;
    TRUNCATE TABLE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS;
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.PROCESS_DOCUMENTS();
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.CLASSIFY_DOCUMENTS();
END;

ALTER TASK SNOWFLAKE_INTELLIGENCE.INGESTION.FULL_REFRESH RESUME;

-- =============================================
-- [GAP G8] NOTIFICATION INTEGRATION for alerts
-- =============================================

CREATE OR REPLACE NOTIFICATION INTEGRATION SI_EMAIL_NOTIFICATIONS
    TYPE = EMAIL
    ENABLED = TRUE
    ALLOWED_RECIPIENTS = ('admin@revelator.com');

-- =============================================
-- [GAP G7] INGESTION TRACKING TABLE
-- Tracks last successful incremental ingestion
-- =============================================

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG (
    source_system    VARCHAR(20),
    ingestion_type   VARCHAR(20),  -- full | incremental
    started_at       TIMESTAMP_NTZ,
    completed_at     TIMESTAMP_NTZ,
    records_ingested NUMBER,
    status           VARCHAR(20),  -- success | failed
    error_message    VARCHAR
);
```

---

## PHASE 3: CORTEX SEARCH SERVICE (Week 3)
### Agent Assignment: Search Agent

### 3.1 Create Cortex Search Service

```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH
    ON content
    ATTRIBUTES title, team, topic, product_area, source_system, owner, backup_owner,
               last_updated, document_id, chunk_id, source_url, status
    WAREHOUSE = AI_WH
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
    FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
    WHERE status = 'active'
      AND content IS NOT NULL
      AND LENGTH(content) > 50
);
```

### 3.2 Validate Search Service

```sql
-- Test search query via SQL
SELECT SNOWFLAKE.CORTEX.SEARCH(
    'SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH',
    '{
        "query": "How do royalty clawbacks work?",
        "columns": ["content", "title", "source_system", "owner", "source_url", "last_updated"],
        "limit": 5
    }'
) AS search_results;
```

### 3.3 Python Search Client (for Streamlit)

```python
# search_client.py - Used inside Streamlit app
from snowflake.core import Root

def search_documents(session, query, filters=None, limit=5):
    """Search documents using Cortex Search Service."""
    root = Root(session)
    search_service = (
        root.databases["SNOWFLAKE_INTELLIGENCE"]
        .schemas["SEARCH"]
        .cortex_search_services["DOCUMENT_SEARCH"]
    )

    search_params = {
        "query": query,
        "columns": [
            "content", "title", "source_system", "owner",
            "backup_owner", "source_url", "last_updated",
            "document_id", "chunk_id", "topic", "product_area"
        ],
        "limit": limit,
    }

    if filters:
        filter_conditions = {}
        if filters.get("team"):
            filter_conditions["@eq"] = {"team": filters["team"]}
        if filters.get("source_system"):
            filter_conditions["@eq"] = {"source_system": filters["source_system"]}
        if filter_conditions:
            search_params["filter"] = filter_conditions

    results = search_service.search(**search_params)
    return results.results
```

---

## PHASE 4: CORTEX AGENT (Week 3-4)
### Agent Assignment: AI Agent Builder

### 4.1 Create Cortex Agent

```sql
CREATE OR REPLACE CORTEX AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT
    MODEL = 'claude-3.5-sonnet'
    TOOLS = (
        SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH   -- Cortex Search as tool
    )
    SYSTEM_PROMPT = '
You are RevSearch, the internal knowledge assistant for Revelator employees.
You answer questions about music distribution, royalties, DSPs, billing,
onboarding, and company processes.

## CORE RULES

1. ONLY use information from the search results provided to you.
2. NEVER add information from your own training data.
3. If the search results do not contain sufficient information to answer
   the question completely, set answer_strength to "weak" or "no_answer".
4. NEVER guess, speculate, or fill in gaps.
5. When you are unsure, explicitly say what you do not know.

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
- Retrieved documents do not address the question at all
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
'
    COMMENT = 'Internal knowledge assistant with confidence scoring and owner routing';
```

**[GAP G4] Fallback Agent** — uses cheaper llama3.3-70b with the same prompt:

```sql
CREATE OR REPLACE CORTEX AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT_FALLBACK
    MODEL = 'llama3.3-70b'
    TOOLS = (
        SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH
    )
    SYSTEM_PROMPT = (SELECT SYSTEM$GET_CORTEX_AGENT_SYSTEM_PROMPT('SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT'))
    COMMENT = '[GAP G4] Fallback agent using llama3.3-70b when primary claude model is unavailable';
```

### 4.2 Python Agent Client (for Streamlit)

```python
# agent_client.py - Used inside Streamlit app
import json
import time
from snowflake.core import Root

def ask_agent(session, question, conversation_history=None):
    """Send a question to the Cortex Agent and get structured response.
    [GAP G4] Falls back to llama3.3-70b if primary agent fails."""
    start_time = time.time()

    root = Root(session)
    agent = (
        root.databases["SNOWFLAKE_INTELLIGENCE"]
        .schemas["AGENTS"]
        .cortex_agents["KNOWLEDGE_ASSISTANT"]
    )

    messages = []
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": question})

    try:
        response = agent.complete(messages=messages)
        model_used = "claude-3.5-sonnet"
    except Exception as primary_err:
        try:
            fallback_agent = (
                root.databases["SNOWFLAKE_INTELLIGENCE"]
                .schemas["AGENTS"]
                .cortex_agents["KNOWLEDGE_ASSISTANT_FALLBACK"]
            )
            response = fallback_agent.complete(messages=messages)
            model_used = "llama3.3-70b (fallback)"
        except Exception as fallback_err:
            return {
                "answer": "I'm temporarily unable to process your question. Please try again in a moment.",
                "answer_strength": "no_answer",
                "sources": [],
                "knowledge_owner": {"needed": True, "reason": f"Agent error: {str(primary_err)[:200]}"},
                "related_questions": [],
                "response_latency_ms": int((time.time() - start_time) * 1000),
                "model_used": "none",
                "error": True,
            }

    elapsed_ms = int((time.time() - start_time) * 1000)

    try:
        answer_data = json.loads(response.message.content)
    except json.JSONDecodeError:
        answer_data = {
            "answer": response.message.content,
            "answer_strength": "medium",
            "sources": [],
            "knowledge_owner": {"needed": False},
            "related_questions": [],
        }

    answer_data["response_latency_ms"] = elapsed_ms
    answer_data["model_used"] = model_used
    return answer_data


def enrich_with_knowledge_owners(session, answer_data):
    """Look up knowledge owners from the ADMIN table based on topic."""
    if not answer_data.get("knowledge_owner", {}).get("needed", False):
        return answer_data

    topics = []
    for source in answer_data.get("sources", []):
        if source.get("topic"):
            topics.append(source["topic"])

    if not topics:
        return answer_data

    topic_list = ",".join([f"'{t}'" for t in topics])
    owners = session.sql(f"""
        SELECT name, team, contact_method, expertise_topics
        FROM SNOWFLAKE_INTELLIGENCE.ADMIN.KNOWLEDGE_OWNERS
        WHERE is_active = TRUE
          AND ARRAY_OVERLAP(expertise_topics, ARRAY_CONSTRUCT({topic_list}))
        LIMIT 2
    """).collect()

    if owners:
        answer_data["knowledge_owner"]["primary_owner"] = owners[0]["NAME"]
        answer_data["knowledge_owner"]["contact"] = owners[0]["CONTACT_METHOD"]
        if len(owners) > 1:
            answer_data["knowledge_owner"]["backup_owner"] = owners[1]["NAME"]

    return answer_data
```

---

## PHASE 5: STREAMLIT APPLICATION (Week 4-5)
### Agent Assignment: UI Agent

### 5.1 Application Structure

```
SNOWFLAKE_INTELLIGENCE.APP/
├── main.py                  # Entry point with page navigation
├── pages/
│   ├── 1_Ask_a_Question.py  # Page 1: Chat interface
│   ├── 2_FAQ_Dashboard.py   # Page 2: Analytics dashboard
│   └── 3_Admin_Panel.py     # Page 3: Admin interface
├── utils/
│   ├── search_client.py     # Cortex Search wrapper
│   ├── agent_client.py      # Cortex Agent wrapper
│   └── db_utils.py          # Database helper functions
└── environment.yml          # Dependencies
```

### 5.2 Page 1: Ask a Question (main page)

```python
# Streamlit in Snowflake — Page 1: Ask a Question
import streamlit as st
import json
import time
from snowflake.snowpark.context import get_active_session
from snowflake.core import Root

session = get_active_session()

st.set_page_config(page_title="RevSearch - Knowledge Assistant", page_icon="🔍", layout="wide")

st.title("Internal Knowledge Assistant")
st.caption("Ask questions about company processes, products, and policies")

# Session state for conversation history
if "messages" not in st.session_state:
    st.session_state.messages = []
if "history" not in st.session_state:
    st.session_state.history = []

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            display_answer(msg["data"])
        else:
            st.write(msg["content"])

# Helper function to display structured answer
def display_answer(data):
    st.markdown(data.get("answer", "No answer available."))

    # Answer strength badge
    strength = data.get("answer_strength", "unknown")
    strength_colors = {
        "strong": "green", "medium": "orange",
        "weak": "red", "no_answer": "red"
    }
    color = strength_colors.get(strength, "gray")
    st.markdown(f"**Answer Strength:** :{color}[{strength.upper()}]")

    # Sources
    sources = data.get("sources", [])
    if sources:
        with st.expander(f"Supporting Sources ({len(sources)})", expanded=True):
            for s in sources:
                col1, col2 = st.columns([3, 1])
                with col1:
                    if s.get("source_url"):
                        st.markdown(f"**[{s['title']}]({s['source_url']})**")
                    else:
                        st.markdown(f"**{s['title']}**")
                    st.caption(f"Source: {s.get('source_system', 'unknown')} | "
                              f"Updated: {s.get('last_updated', 'unknown')}")
                with col2:
                    if s.get("relevance_note"):
                        st.caption(s["relevance_note"])

    # [GAP G5] Document staleness warnings
    from datetime import datetime, timedelta
    stale_sources = []
    for s in data.get("sources", []):
        try:
            updated = s.get("last_updated", "")
            if updated:
                updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                age_days = (datetime.now(updated_dt.tzinfo) - updated_dt).days
                if age_days > 90:
                    stale_sources.append((s.get("title", "Unknown"), age_days))
        except (ValueError, TypeError):
            pass
    if stale_sources:
        stale_list = ", ".join([f"**{t}** ({d} days old)" for t, d in stale_sources])
        st.warning(f"Some sources may be outdated: {stale_list}. "
                   "Consider verifying with the knowledge owner.")

    # [GAP G4] Model fallback indicator
    model_used = data.get("model_used", "")
    if "fallback" in model_used.lower():
        st.info(f"Note: This answer was generated using the fallback model ({model_used}). "
                "Quality may differ slightly from the primary model.")

    # Knowledge owner routing
    ko = data.get("knowledge_owner", {})
    if ko.get("needed"):
        st.warning("Documentation may be incomplete. Contact the knowledge owner:")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Primary Owner", ko.get("primary_owner", "Unknown"))
        with col2:
            st.metric("Backup Owner", ko.get("backup_owner", "Unknown"))
        with col3:
            st.metric("Contact", ko.get("contact", "Unknown"))

    # Related questions
    related = data.get("related_questions", [])
    if related:
        st.markdown("**Related Questions:**")
        for q in related:
            if st.button(q, key=f"related_{q}"):
                st.session_state.pending_question = q
                st.rerun()

# Chat input
question = st.chat_input("Ask a question about company processes, products, or policies...")

# Handle pending question from related questions
if "pending_question" in st.session_state:
    question = st.session_state.pop("pending_question")

if question:
    # Display user message
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    # Get answer from Cortex Agent
    with st.chat_message("assistant"):
        with st.spinner("Searching internal documentation..."):
            start_time = time.time()

            root = Root(session)
            # Call Cortex Agent
            response = root.databases["SNOWFLAKE_INTELLIGENCE"].schemas["AGENTS"].cortex_agents["KNOWLEDGE_ASSISTANT"].complete(
                messages=[{"role": "user", "content": question}]
            )
            elapsed_ms = int((time.time() - start_time) * 1000)

            try:
                answer_data = json.loads(response.message.content)
            except (json.JSONDecodeError, AttributeError):
                answer_data = {
                    "answer": str(response),
                    "answer_strength": "medium",
                    "sources": [],
                    "knowledge_owner": {"needed": False},
                    "related_questions": [],
                }

            answer_data["response_latency_ms"] = elapsed_ms
            display_answer(answer_data)

    st.session_state.messages.append({"role": "assistant", "data": answer_data})

    # Log question to analytics
    session.sql(f"""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
        (question_text, user_name, answer, answer_strength, sources_used,
         knowledge_owner, related_questions, response_latency_ms)
        VALUES (
            '{question.replace("'", "''")}',
            CURRENT_USER(),
            '{answer_data.get("answer", "").replace("'", "''")[:5000]}',
            '{answer_data.get("answer_strength", "unknown")}',
            PARSE_JSON('{json.dumps(answer_data.get("sources", [])).replace("'", "''")}'),
            PARSE_JSON('{json.dumps(answer_data.get("knowledge_owner", {})).replace("'", "''")}'),
            PARSE_JSON('{json.dumps(answer_data.get("related_questions", [])).replace("'", "''")}'),
            {elapsed_ms}
        )
    """).collect()

    # Feedback buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👍 Helpful"):
            session.sql(f"""
                INSERT INTO SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK (question_id, feedback_type, user_name)
                SELECT question_id, 'thumbs_up', CURRENT_USER()
                FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
                ORDER BY date_asked DESC LIMIT 1
            """).collect()
            st.success("Thanks for the feedback!")
    with col2:
        if st.button("👎 Not Helpful"):
            session.sql(f"""
                INSERT INTO SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK (question_id, feedback_type, user_name)
                SELECT question_id, 'thumbs_down', CURRENT_USER()
                FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
                ORDER BY date_asked DESC LIMIT 1
            """).collect()
            st.info("Thanks — we'll use this to improve.")
```

### 5.3 Page 2: FAQ Dashboard

```python
# Streamlit in Snowflake — Page 2: FAQ Dashboard
import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

session = get_active_session()

st.title("FAQ Dashboard")
st.caption("Analytics on questions, knowledge gaps, and usage patterns")

# Key metrics
col1, col2, col3, col4 = st.columns(4)

total_q = session.sql("SELECT COUNT(*) AS cnt FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS").collect()[0]["CNT"]
strong_pct = session.sql("""
    SELECT ROUND(COUNT_IF(answer_strength = 'strong') * 100.0 / NULLIF(COUNT(*), 0), 1) AS pct
    FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
""").collect()[0]["PCT"] or 0
weak_cnt = session.sql("""
    SELECT COUNT(*) AS cnt FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
    WHERE answer_strength IN ('weak', 'no_answer')
""").collect()[0]["CNT"]
avg_latency = session.sql("""
    SELECT ROUND(AVG(response_latency_ms) / 1000, 1) AS avg_s
    FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
""").collect()[0]["AVG_S"] or 0

with col1:
    st.metric("Total Questions", total_q)
with col2:
    st.metric("Strong Answer Rate", f"{strong_pct}%")
with col3:
    st.metric("Weak/No Answers", weak_cnt)
with col4:
    st.metric("Avg Response Time", f"{avg_latency}s")

st.divider()

# Top asked questions
st.subheader("Most Asked Questions")
top_questions = session.sql("""
    SELECT question_text, COUNT(*) AS ask_count,
           MODE(answer_strength) AS typical_strength
    FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
    GROUP BY question_text
    ORDER BY ask_count DESC
    LIMIT 20
""").to_pandas()
st.dataframe(top_questions, use_container_width=True)

# Recent questions
st.subheader("Recently Asked")
recent = session.sql("""
    SELECT question_text, answer_strength, date_asked, user_name
    FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
    ORDER BY date_asked DESC
    LIMIT 20
""").to_pandas()
st.dataframe(recent, use_container_width=True)

# Questions by team
st.subheader("Questions by Team")
by_team = session.sql("""
    SELECT COALESCE(user_team, 'Unknown') AS team, COUNT(*) AS questions
    FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
    GROUP BY team
    ORDER BY questions DESC
""").to_pandas()
st.bar_chart(by_team.set_index("TEAM"))

# Knowledge gaps
st.subheader("Knowledge Gaps (Weak / No Answer)")
gaps = session.sql("""
    SELECT question_text, answer_strength, date_asked,
           sources_used, knowledge_owner
    FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
    WHERE answer_strength IN ('weak', 'no_answer')
    ORDER BY date_asked DESC
    LIMIT 50
""").to_pandas()
st.dataframe(gaps, use_container_width=True)

# Answer strength distribution
st.subheader("Answer Strength Distribution")
strength_dist = session.sql("""
    SELECT answer_strength, COUNT(*) AS cnt
    FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
    GROUP BY answer_strength
""").to_pandas()
st.bar_chart(strength_dist.set_index("ANSWER_STRENGTH"))
```

### 5.4 Page 3: Admin Panel

```python
# Streamlit in Snowflake — Page 3: Admin Panel
import streamlit as st
import json
from snowflake.snowpark.context import get_active_session

session = get_active_session()

st.title("Admin Panel")
st.caption("Manage documents, knowledge owners, and system configuration")

tab1, tab2, tab3, tab4 = st.tabs(["Documents", "Knowledge Owners", "Weak Answers", "System"])

# Tab 1: Document Management
with tab1:
    st.subheader("Upload New Document")
    with st.form("upload_doc"):
        title = st.text_input("Document Title")
        content = st.text_area("Document Content (paste text)", height=300)
        col1, col2 = st.columns(2)
        with col1:
            team = st.selectbox("Team", ["Product", "Support", "Engineering", "Operations", "Billing"])
            topic = st.selectbox("Topic", ["Product Documentation", "Support Process", "Onboarding",
                                           "Billing Policy", "Operational Procedure", "Technical Guide"])
        with col2:
            product_area = st.selectbox("Product Area", ["Royalties", "DSP", "Distribution",
                                                         "Billing", "Analytics", "General"])
            owner = st.text_input("Primary Owner")

        submitted = st.form_submit_button("Upload Document")
        if submitted and title and content:
            import hashlib
            doc_id = hashlib.sha256(f"manual|{title}".encode()).hexdigest()[:16]
            session.sql(f"""
                INSERT INTO SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
                (document_id, source_system, source_id, title, content, content_length,
                 team, topic, product_area, owner, status, last_updated)
                VALUES ('{doc_id}', 'manual', '{doc_id}', '{title.replace("'", "''")}',
                        '{content.replace("'", "''")}', {len(content)},
                        '{team}', '{topic}', '{product_area}', '{owner.replace("'", "''")}',
                        'active', CURRENT_TIMESTAMP())
            """).collect()
            st.success(f"Document '{title}' uploaded successfully!")

    st.subheader("Existing Documents")
    docs = session.sql("""
        SELECT document_id, title, source_system, team, topic, status, last_updated
        FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
        ORDER BY last_updated DESC
        LIMIT 100
    """).to_pandas()
    st.dataframe(docs, use_container_width=True)

# Tab 2: Knowledge Owner Management
with tab2:
    st.subheader("Add Knowledge Owner")
    with st.form("add_owner"):
        name = st.text_input("Name")
        team = st.text_input("Team")
        topics = st.multiselect("Expertise Topics",
            ["Product Documentation", "Support Process", "Onboarding", "Billing Policy",
             "Operational Procedure", "Royalties", "DSP", "Distribution", "Analytics"])
        contact = st.text_input("Contact (Slack channel or email)")

        submitted = st.form_submit_button("Add Owner")
        if submitted and name and team:
            topics_json = json.dumps(topics)
            session.sql(f"""
                INSERT INTO SNOWFLAKE_INTELLIGENCE.ADMIN.KNOWLEDGE_OWNERS
                (name, team, expertise_topics, contact_method)
                VALUES ('{name.replace("'", "''")}', '{team.replace("'", "''")}',
                        PARSE_JSON('{topics_json}'), '{contact.replace("'", "''")}')
            """).collect()
            st.success(f"Owner '{name}' added!")

    st.subheader("Current Knowledge Owners")
    owners = session.sql("""
        SELECT name, team, expertise_topics, contact_method, is_active
        FROM SNOWFLAKE_INTELLIGENCE.ADMIN.KNOWLEDGE_OWNERS
        ORDER BY team, name
    """).to_pandas()
    st.dataframe(owners, use_container_width=True)

# Tab 3: Weak/Unanswered Questions Review
with tab3:
    st.subheader("Questions Needing Attention")
    weak = session.sql("""
        SELECT q.question_text, q.answer_strength, q.date_asked,
               q.answer, q.knowledge_owner
        FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS q
        WHERE q.answer_strength IN ('weak', 'no_answer')
        ORDER BY q.date_asked DESC
        LIMIT 50
    """).to_pandas()
    st.dataframe(weak, use_container_width=True)

    st.subheader("Negative Feedback")
    neg = session.sql("""
        SELECT q.question_text, q.answer, f.feedback_text, f.created_at
        FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK f
        JOIN SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS q ON f.question_id = q.question_id
        WHERE f.feedback_type = 'thumbs_down'
        ORDER BY f.created_at DESC
        LIMIT 30
    """).to_pandas()
    st.dataframe(neg, use_container_width=True)

# Tab 4: System Configuration
with tab4:
    st.subheader("Ingestion Status")
    st.code("""
-- Check last ingestion run
SELECT name, state, scheduled_time, completed_time, error_code, error_message
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    TASK_NAME => 'TASK_INGEST_GITBOOK',
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
))
ORDER BY scheduled_time DESC
LIMIT 10;
    """)

    st.subheader("Document Counts by Source")
    counts = session.sql("""
        SELECT source_system, COUNT(*) AS doc_count,
               COUNT(DISTINCT document_id) AS unique_docs
        FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
        GROUP BY source_system
    """).to_pandas()
    st.dataframe(counts, use_container_width=True)

    st.subheader("Search Service Health")
    st.info("Check Cortex Search Service status in Snowsight > AI & ML > Search Services")
```

---

## PHASE 6: ANALYTICS & DYNAMIC TABLES (Week 5)
### Agent Assignment: Analytics Agent

### 6.1 Dynamic Tables for Real-Time Aggregation

```sql
-- FAQ aggregation: clusters similar questions
CREATE OR REPLACE DYNAMIC TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.FAQ_SUMMARY
    TARGET_LAG = '1 hour'
    WAREHOUSE = AI_WH
AS
SELECT
    question_text,
    COUNT(*) AS ask_count,
    MODE(answer_strength) AS typical_strength,
    MIN(date_asked) AS first_asked,
    MAX(date_asked) AS last_asked,
    AVG(response_latency_ms) AS avg_latency_ms,
    ARRAY_AGG(DISTINCT user_team) AS teams_asking,
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS weak_count
FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
GROUP BY question_text;

-- Team-level analytics
CREATE OR REPLACE DYNAMIC TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.TEAM_SUMMARY
    TARGET_LAG = '1 hour'
    WAREHOUSE = AI_WH
AS
SELECT
    COALESCE(user_team, 'Unknown') AS team,
    COUNT(*) AS total_questions,
    COUNT_IF(answer_strength = 'strong') AS strong_answers,
    COUNT_IF(answer_strength = 'medium') AS medium_answers,
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS weak_or_none,
    ROUND(COUNT_IF(answer_strength = 'strong') * 100.0 / NULLIF(COUNT(*), 0), 1) AS strong_pct,
    AVG(response_latency_ms) AS avg_latency_ms
FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
GROUP BY team;

-- Knowledge gap detection
CREATE OR REPLACE DYNAMIC TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.KNOWLEDGE_GAPS
    TARGET_LAG = '1 hour'
    WAREHOUSE = AI_WH
AS
SELECT
    question_text,
    answer_strength,
    COUNT(*) AS times_asked,
    MAX(date_asked) AS last_asked,
    ARRAY_AGG(DISTINCT user_team) AS teams_affected
FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
WHERE answer_strength IN ('weak', 'no_answer')
GROUP BY question_text, answer_strength
HAVING COUNT(*) >= 2
ORDER BY times_asked DESC;
```

### 6.2 Alerting for Knowledge Gaps

```sql
CREATE OR REPLACE ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.KNOWLEDGE_GAP_ALERT
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 9 * * MON America/Los_Angeles'
    IF (EXISTS (
        SELECT 1
        FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
        WHERE answer_strength IN ('weak', 'no_answer')
          AND date_asked >= DATEADD('day', -7, CURRENT_TIMESTAMP())
        GROUP BY question_text
        HAVING COUNT(*) >= 3
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'revsearch_notifications',
            'admin@company.com',
            'RevSearch: Knowledge Gaps Detected',
            'Multiple questions received weak or no answers this week. Review the FAQ Dashboard for details.'
        );

ALTER ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.KNOWLEDGE_GAP_ALERT RESUME;
```

### 6.3 [GAP G12] Cortex Credit Cost Monitoring

```sql
CREATE OR REPLACE DYNAMIC TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.CORTEX_COST_TRACKING
    TARGET_LAG = '1 hour'
    WAREHOUSE = AI_WH
AS
SELECT
    DATE_TRUNC('day', start_time) AS usage_date,
    service_type,
    SUM(credits_used) AS daily_credits,
    COUNT(*) AS request_count,
    SUM(credits_used) / NULLIF(COUNT(*), 0) AS avg_credit_per_request
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY
WHERE service_type IN ('AI_SERVICES', 'SEARCH_OPTIMIZATION')
  AND start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY usage_date, service_type;

CREATE OR REPLACE ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.CORTEX_COST_ALERT
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 8 * * * America/Los_Angeles'
    IF (EXISTS (
        SELECT 1
        FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.CORTEX_COST_TRACKING
        WHERE usage_date = CURRENT_DATE() - 1
          AND daily_credits > 10
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'revsearch_notifications',
            'admin@revelator.com',
            'RevSearch: Daily Cortex Credit Threshold Exceeded',
            'RevSearch used more than 10 Cortex credits yesterday. Review usage in the Admin Panel.'
        );

ALTER ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.CORTEX_COST_ALERT RESUME;
```

---

## PHASE 7: TESTING & VALIDATION (Week 6)
### Agent Assignment: QA Agent

### 7.1 Test Suite: 20 Validation Questions

| # | Test Question | Expected Behavior |
|---|-------------|-------------------|
| 1 | "How do royalty clawbacks work?" | Strong/Medium answer from product docs |
| 2 | "Who owns DSP migration issues?" | Answer + knowledge owner routing |
| 3 | "How do we onboard enterprise clients?" | Strong answer from onboarding docs |
| 4 | "Where is the billing escalation process?" | Answer from billing policy docs |
| 5 | "What is the refund policy for annual plans?" | Test document retrieval accuracy |
| 6 | "How do I set up a new distribution partner?" | Multi-doc synthesis test |
| 7 | "What are the SLA requirements for support?" | Test SLA documentation coverage |
| 8 | "Who is the backup for Milan on product ops?" | Test knowledge owner lookup |
| 9 | "What changed in the latest product release?" | Test freshness and release notes |
| 10 | "How do I handle a DMCA takedown request?" | Test legal/compliance docs |
| 11 | "Completely unrelated topic: quantum physics" | Expected: No Answer |
| 12 | "Tell me about something not in any document" | Expected: No Answer (no hallucination) |
| 13 | "What is the internal process for X?" (vague) | Expected: Weak/Medium + routing |
| 14 | Same question asked 3 times | Test FAQ aggregation |
| 15 | "How do royalty clawbacks work?" (repeat of #1) | Test consistency |
| 16 | Filter test: "Freshdesk articles about billing" | Test source filtering |
| 17 | Long complex question (100+ words) | Test handling of verbose input |
| 18 | Question with typos: "How do roylty clawbaks wrk?" | Test fuzzy matching |
| 19 | Follow-up question in same session | Test conversation context |
| 20 | Admin: upload doc then search for it | Test end-to-end ingestion → search |

### 7.2 Validation Checklist

- [ ] All 3 ingestion pipelines run successfully
- [ ] DOCUMENT_CHUNKS table populated with correct data
- [ ] Cortex Search Service returns results for all test queries
- [ ] Cortex Agent returns structured JSON responses
- [ ] Answer strength classification is reasonable
- [ ] Knowledge owner routing works for Medium/Weak/No Answer
- [ ] Streamlit Page 1: question → answer flow works end-to-end
- [ ] Streamlit Page 2: dashboard shows real metrics
- [ ] Streamlit Page 3: admin can upload docs and manage owners
- [ ] Feedback buttons log to FEEDBACK table
- [ ] Dynamic Tables refresh correctly
- [ ] No hallucinated content in any test answer
- [ ] Response time < 8 seconds for all test queries
- [ ] API credentials stored only as Snowflake Secrets

---

## AGENT ASSIGNMENTS SUMMARY

| Agent # | Name | Responsibility | Phase | Deliverables |
|---------|------|---------------|-------|-------------|
| 1 | **Infrastructure Agent** | Database, schemas, roles, secrets, warehouses | Phase 1 (Week 1) | All DDL executed, roles granted, secrets created |
| 2 | **Freshdesk Ingestion Agent** | Freshdesk API → Snowflake pipeline | Phase 2 (Week 2) | Stored procedure + task, data validated |
| 3 | **GitBook Ingestion Agent** | GitBook API → Snowflake pipeline | Phase 2 (Week 2) | Stored procedure + task, data validated |
| 4 | **Notion Ingestion Agent** | Notion API → Snowflake pipeline | Phase 2 (Week 2) | Stored procedure + task, data validated |
| 5 | **Document Processing Agent** | Unification, chunking, classification | Phase 2 (Week 2) | DOCUMENTS + DOCUMENT_CHUNKS populated |
| 6 | **Search Agent** | Cortex Search Service setup & tuning | Phase 3 (Week 3) | Search service created, validated with test queries |
| 7 | **AI Agent Builder** | Cortex Agent config, prompt engineering | Phase 4 (Week 3-4) | Agent returning structured answers with confidence |
| 8 | **UI Agent** | Streamlit app (3 pages) | Phase 5 (Week 4-5) | All pages functional in Snowflake |
| 9 | **Analytics Agent** | Dynamic Tables, alerting, dashboards | Phase 6 (Week 5) | FAQ analytics, knowledge gap detection operational |
| 10 | **QA Agent** | Testing, validation, security audit | Phase 7 (Week 6) | 20-question test suite passed, all checklists green |

---

## COST ESTIMATION

| Component | Estimated Monthly Cost | Notes |
|-----------|----------------------|-------|
| Cortex Search Service | $50-200 | Based on document volume (~10K chunks) |
| Cortex Agent (LLM calls) | $100-500 | ~1000 questions/month at ~$0.10-0.50/question |
| Ingestion Warehouse (SMALL) | $50-100 | 4 runs/day, ~5 min each |
| Search Warehouse (SMALL) | $100-200 | On-demand for queries |
| App Warehouse (XSMALL) | $50-100 | Streamlit session hosting |
| Dynamic Tables | $20-50 | Hourly refresh of aggregations |
| Storage | $10-20 | Document data + analytics |
| **Total Estimated** | **$380-1,170/month** | Scales with usage |

---

## PREREQUISITES CHECKLIST

- [x] Freshdesk API key available (.env)
- [x] GitBook API key available (.env)
- [ ] Notion API key — **ACTION REQUIRED: Obtain and add to .env**
- [ ] Snowflake account with Cortex features enabled — **VERIFY**
- [ ] Cortex Search Service available in account region — **VERIFY**
- [ ] Cortex Agent available (check preview/GA status) — **VERIFY**
- [ ] Streamlit in Snowflake enabled — **VERIFY**
- [ ] ACCOUNTADMIN or equivalent role for initial setup — **VERIFY**
- [ ] Freshdesk domain URL (replace `<your-domain>` in network rules) — **ACTION REQUIRED**
- [ ] Knowledge owner directory from Milan/Product Ops — **ACTION REQUIRED**
- [ ] Test question set from Product + Support teams — **ACTION REQUIRED**
