# PLAN 6 Part 1: Freshdesk V2 API — Complete Data Ingestion

> Ingest ALL Freshdesk V2 data into Snowflake RAW tables: 25 entity types across
> operational, knowledge base, discussion, admin, and satisfaction domains.
> V2 Base URL: `https://newaccount1623084859360.freshdesk.com/api/v2`
> Auth: HTTP Basic (API key + "X") | Pro plan | Dual rate limits: 100/min + 40/min

---

## V2 API Discovery (March 17, 2026)

### Domain Resolution

| Domain | V1 | V2 | Notes |
|--------|----|----|-------|
| `helpdesk.revelator.com` | ✅ 30 endpoints | ❌ ALL 404 | Vanity/CNAME — V2 not supported |
| `newaccount1623084859360.freshdesk.com` | ✅ works | ✅ **31/37 GET endpoints** | Real default subdomain — V2 primary |
| `revelator.freshdesk.com` | ❌ ALL 404 | ❌ ALL 404 | Not the actual subdomain |

### Account Info (from `/api/v2/account`)

```json
{
  "account_id": 1957334,
  "account_name": "Revelator",
  "account_domain": "newaccount1623084859360.freshdesk.com",
  "tier_type": "Pro",
  "total_agents": {"full_time": 24, "occasional": 0},
  "timezone": "Jerusalem",
  "data_center": "US"
}
```

### Rate Limits (Confirmed from Response Headers)

| Bucket | Limit | Applies To |
|--------|-------|------------|
| **General** | 100/min | agents, groups, solutions, admin, discussions, surveys, email, SLA, automations |
| **Tickets + Contacts** | 40/min | `/api/v2/tickets*`, `/api/v2/contacts*` |

### API Call Budget

```
=== 100/min bucket (~97 calls, fits in ~1 minute) ===
Agents ×1, Account ×1, Roles ×1, Groups ×1, Companies ×5 pages,
Company Fields ×1, Contact Fields ×1, Ticket Fields ×1, Ticket Forms ×1,
Admin Ticket Fields ×1, Admin Groups ×1,
Solution Categories ×1, Solution Folders ×12, Solution Articles ×44,
Discussion Categories ×1, Discussion Forums ×1, Discussion Topics ×5, Discussion Comments ×8,
Surveys ×1, Satisfaction Ratings ×1, CSAT Surveys ×1,
Email Configs ×1, Email Mailboxes ×1, Business Hours ×1, SLA Policies ×1,
Automation Rules ×3

=== 40/min bucket (~3,691 calls, ~92 minutes — BOTTLENECK) ===
Tickets list ×19 pages, Ticket details ×1,811, Ticket conversations ×1,811,
Contacts ×50 pages

TOTAL: ~3,788 calls | Full refresh: ~92 min | Incremental: <3 min
```

### Plan-Blocked Features (403)

| Feature | Error | Plan Required |
|---------|-------|---------------|
| Archived Tickets | "Archive Tickets feature not supported" | Estate+ |
| Ticket Accesses | "Collaboration At Mentions not supported" | Estate+ |
| Agent Availability | "Agent Statuses not supported" | Estate+ |
| Admin Skills | 403 | Enterprise |
| Canned Responses | 404 | May need admin setup |

---

## V2 Endpoint Inventory (37 Tested, 31 Working)

| # | Table | V2 Endpoint | Records | Bucket | Paginated | Incremental |
|---|-------|------------|---------|--------|-----------|-------------|
| 1 | FRESHDESK_TICKETS | `/api/v2/tickets` | 1,811 | 40/min | ✅ `page` | `updated_since` |
| 2 | FRESHDESK_TICKET_CONVERSATIONS | `/api/v2/tickets/{id}/conversations` | per-ticket | 40/min | ✅ `page` | via ticket |
| 3 | FRESHDESK_CONTACTS | `/api/v2/contacts` | 5,000+ | 40/min | ✅ `page` | `_updated_since` |
| 4 | FRESHDESK_COMPANIES | `/api/v2/companies` | 434 | 100/min | ✅ `page` | — |
| 5 | FRESHDESK_AGENTS | `/api/v2/agents` | 40 | 100/min | ✅ `page` | — |
| 6 | FRESHDESK_GROUPS | `/api/v2/groups` | 13 | 100/min | ✅ `page` | — |
| 7 | FRESHDESK_ROLES | `/api/v2/roles` | 4 | 100/min | ❌ | — |
| 8 | FRESHDESK_ACCOUNT | `/api/v2/account` | 1 | 100/min | ❌ | — |
| 9 | FRESHDESK_TICKET_FIELDS | `/api/v2/ticket_fields` | 17 | 100/min | ❌ | — |
| 10 | FRESHDESK_CONTACT_FIELDS | `/api/v2/contact_fields` | 14 | 100/min | ❌ | — |
| 11 | FRESHDESK_COMPANY_FIELDS | `/api/v2/company_fields` | 14 | 100/min | ❌ | — |
| 12 | FRESHDESK_TICKET_FORMS | `/api/v2/ticket-forms` | 2 | 100/min | ❌ | — |
| 13 | FRESHDESK_SOLUTION_CATEGORIES | `/api/v2/solutions/categories` | 12 | 100/min | ❌ | — |
| 14 | FRESHDESK_SOLUTION_FOLDERS | `/api/v2/solutions/categories/{id}/folders` | 44 | 100/min | ❌ | — |
| 15 | FRESHDESK_SOLUTION_ARTICLES | `/api/v2/solutions/folders/{id}/articles` | 179 | 100/min | ✅ `page` | — |
| 16 | FRESHDESK_DISCUSSION_CATEGORIES | `/api/v2/discussions/categories` | 1 | 100/min | ❌ | — |
| 17 | FRESHDESK_DISCUSSION_FORUMS | `/api/v2/discussions/categories/{id}/forums` | 5 | 100/min | ❌ | — |
| 18 | FRESHDESK_DISCUSSION_TOPICS | `/api/v2/discussions/forums/{id}/topics` | 8 | 100/min | ✅ `page` | — |
| 19 | FRESHDESK_DISCUSSION_COMMENTS | `/api/v2/discussions/topics/{id}/comments` | 18 | 100/min | ✅ `page` | — |
| 20 | FRESHDESK_SURVEYS | `/api/v2/surveys` | 2 | 100/min | ❌ | — |
| 21 | FRESHDESK_SATISFACTION_RATINGS | `/api/v2/surveys/satisfaction_ratings` | 6 | 100/min | ✅ `page` | — |
| 22 | FRESHDESK_EMAIL_CONFIGS | `/api/v2/email_configs` | 3 | 100/min | ❌ | — |
| 23 | FRESHDESK_EMAIL_MAILBOXES | `/api/v2/email/mailboxes` | 3 | 100/min | ❌ | — |
| 24 | FRESHDESK_BUSINESS_HOURS | `/api/v2/business_hours` | 1 | 100/min | ❌ | — |
| 25 | FRESHDESK_SLA_POLICIES | `/api/v2/sla_policies` | 1 | 100/min | ❌ | — |
| — | FRESHDESK_AUTOMATION_RULES | `/api/v2/automations/{type}/rules` | 64 | 100/min | ❌ | — |

> Automation rules stored in FRESHDESK_SLA_POLICIES or a dedicated table — 3 types (creation=1, update=3, frustration=4)
> Time Entries (0 records) and Products (0 records) — SKIP until populated.

---

## Phase 1: Foundation — Secrets, Network Rule, EAI

### 1.1 Secret (reuse existing)

```sql
-- Already exists: SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET
-- Verify: DESCRIBE SECRET SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET;
```

### 1.2 Network Rule — BOTH Domains

```sql
CREATE OR REPLACE NETWORK RULE SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_NETWORK_RULE
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = (
        'newaccount1623084859360.freshdesk.com',
        'helpdesk.revelator.com'
    );
```

### 1.3 External Access Integration

```sql
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION SI_FRESHDESK_ACCESS
    ALLOWED_NETWORK_RULES = (SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_NETWORK_RULE)
    ALLOWED_AUTHENTICATION_SECRETS = (SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET)
    ENABLED = TRUE;
```

### 1.4 Infrastructure File

Create `infra/01_foundation/security_freshdesk.sql` with above DDL.

### Deliverables
- [ ] Network rule includes `newaccount1623084859360.freshdesk.com`
- [ ] `DESCRIBE INTEGRATION SI_FRESHDESK_ACCESS` → ENABLED=TRUE

---

## Phase 2: RAW Storage Layer — 25 Tables

All tables follow conventions from existing `raw_tables.sql`:
- `raw_json VARIANT` on every table for schema evolution
- `_loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()`
- `_source_system VARCHAR DEFAULT 'freshdesk'`
- `CREATE TABLE IF NOT EXISTS` (idempotent)

### 2.1 File: `infra/02_storage/raw_freshdesk_tables.sql`

```sql
-- ============================================================
-- Tier 1: Core Operational (40/min bucket)
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS (
    id                 NUMBER PRIMARY KEY,
    subject            VARCHAR(2000),
    description        VARCHAR,
    description_text   VARCHAR,
    status             NUMBER,
    priority           NUMBER,
    source             NUMBER,
    type               VARCHAR(100),
    requester_id       NUMBER,
    responder_id       NUMBER,
    company_id         NUMBER,
    group_id           NUMBER,
    product_id         NUMBER,
    email_config_id    NUMBER,
    to_emails          VARIANT,
    cc_emails          VARIANT,
    fwd_emails         VARIANT,
    reply_cc_emails    VARIANT,
    fr_escalated       BOOLEAN,
    spam               BOOLEAN,
    is_escalated       BOOLEAN,
    tags               VARIANT,
    custom_fields      VARIANT,
    attachments        VARIANT,
    due_by             TIMESTAMP_NTZ,
    fr_due_by          TIMESTAMP_NTZ,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_CONVERSATIONS (
    id                 NUMBER PRIMARY KEY,
    ticket_id          NUMBER NOT NULL,
    body               VARCHAR,
    body_text          VARCHAR,
    user_id            NUMBER,
    source             NUMBER,
    category           NUMBER,
    incoming           BOOLEAN,
    private            BOOLEAN,
    to_emails          VARIANT,
    from_email         VARCHAR(500),
    cc_emails          VARIANT,
    bcc_emails         VARIANT,
    support_email      VARCHAR(500),
    attachments        VARIANT,
    last_edited_at     TIMESTAMP_NTZ,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_CONTACTS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    email              VARCHAR(500),
    phone              VARCHAR(100),
    mobile             VARCHAR(100),
    company_id         NUMBER,
    active             BOOLEAN,
    job_title          VARCHAR(500),
    language           VARCHAR(50),
    time_zone          VARCHAR(100),
    description        VARCHAR,
    address            VARCHAR(1000),
    tags               VARIANT,
    custom_fields      VARIANT,
    other_emails       VARIANT,
    other_companies    VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ============================================================
-- Tier 1: Core Operational (100/min bucket)
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_COMPANIES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(1000),
    description        VARCHAR,
    note               VARCHAR,
    domains            VARIANT,
    health_score       VARCHAR(100),
    account_tier       VARCHAR(100),
    renewal_date       TIMESTAMP_NTZ,
    industry           VARCHAR(200),
    custom_fields      VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AGENTS (
    id                 NUMBER PRIMARY KEY,
    contact            VARIANT,
    type               VARCHAR(50),
    occasional         BOOLEAN,
    signature          VARCHAR,
    ticket_scope       NUMBER,
    group_ids          VARIANT,
    role_ids           VARIANT,
    available          BOOLEAN,
    available_since    TIMESTAMP_NTZ,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_GROUPS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR(2000),
    escalate_to        NUMBER,
    unassigned_for     VARCHAR(100),
    business_hour_id   NUMBER,
    group_type         VARCHAR(100),
    auto_ticket_assign NUMBER,
    agent_ids          VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_ROLES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR,
    default_role       BOOLEAN,
    agent_type         NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_ACCOUNT (
    account_id         NUMBER PRIMARY KEY,
    account_name       VARCHAR(500),
    account_domain     VARCHAR(500),
    tier_type          VARCHAR(100),
    timezone           VARCHAR(100),
    data_center        VARCHAR(50),
    total_agents       VARIANT,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ============================================================
-- Tier 2: Field Metadata + Forms
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_FIELDS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    label              VARCHAR(500),
    label_for_customers VARCHAR(500),
    description        VARCHAR,
    type               VARCHAR(100),
    position           NUMBER,
    required_for_closure BOOLEAN,
    required_for_agents BOOLEAN,
    required_for_customers BOOLEAN,
    customers_can_edit BOOLEAN,
    choices            VARIANT,
    nested_fields      VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_CONTACT_FIELDS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    label              VARCHAR(500),
    type               VARCHAR(100),
    position           NUMBER,
    required_for_agents BOOLEAN,
    customers_can_edit BOOLEAN,
    editable_in_signup BOOLEAN,
    choices            VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_COMPANY_FIELDS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    label              VARCHAR(500),
    type               VARCHAR(100),
    position           NUMBER,
    required_for_agents BOOLEAN,
    choices            VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_FORMS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    title              VARCHAR(500),
    description        VARCHAR,
    default_form       BOOLEAN,
    portals            VARIANT,
    fields             VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ============================================================
-- Tier 1: Solutions (Knowledge Base)
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_CATEGORIES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(1000),
    description        VARCHAR,
    visible_in_portals VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_FOLDERS (
    id                 NUMBER PRIMARY KEY,
    category_id        NUMBER NOT NULL,
    name               VARCHAR(1000),
    description        VARCHAR,
    visibility         NUMBER,
    articles_count     NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_ARTICLES (
    id                 NUMBER PRIMARY KEY,
    folder_id          NUMBER NOT NULL,
    category_id        NUMBER,
    agent_id           NUMBER,
    title              VARCHAR(2000),
    description        VARCHAR,
    description_text   VARCHAR,
    status             NUMBER,
    type               NUMBER,
    hits               NUMBER,
    thumbs_up          NUMBER,
    thumbs_down        NUMBER,
    seo_data           VARIANT,
    tags               VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ============================================================
-- Tier 2: Discussions (NOW ACTIVE — V2 revealed data)
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_CATEGORIES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(1000),
    description        VARCHAR,
    position           NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_FORUMS (
    id                 NUMBER PRIMARY KEY,
    category_id        NUMBER NOT NULL,
    name               VARCHAR(1000),
    description        VARCHAR,
    forum_type         NUMBER,
    forum_visibility   NUMBER,
    topics_count       NUMBER,
    position           NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_TOPICS (
    id                 NUMBER PRIMARY KEY,
    forum_id           NUMBER NOT NULL,
    title              VARCHAR(2000),
    user_id            NUMBER,
    locked             BOOLEAN,
    sticky             BOOLEAN,
    hits               NUMBER,
    replies            NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_COMMENTS (
    id                 NUMBER PRIMARY KEY,
    topic_id           NUMBER NOT NULL,
    user_id            NUMBER,
    body               VARCHAR,
    body_text          VARCHAR,
    answer             BOOLEAN,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ============================================================
-- Tier 2: Customer Satisfaction
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SURVEYS (
    id                 NUMBER PRIMARY KEY,
    title              VARCHAR(500),
    active             BOOLEAN,
    questions          VARIANT,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SATISFACTION_RATINGS (
    id                 NUMBER PRIMARY KEY,
    survey_id          NUMBER,
    user_id            NUMBER,
    agent_id           NUMBER,
    ticket_id          NUMBER,
    group_id           NUMBER,
    feedback           VARCHAR,
    ratings            VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ============================================================
-- Tier 3: Admin / Config
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_EMAIL_CONFIGS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    to_email           VARCHAR(500),
    reply_email        VARCHAR(500),
    group_id           NUMBER,
    primary_role       BOOLEAN,
    active             BOOLEAN,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_EMAIL_MAILBOXES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    support_email      VARCHAR(500),
    product_id         NUMBER,
    group_id           NUMBER,
    active             BOOLEAN,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_BUSINESS_HOURS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR,
    is_default         BOOLEAN,
    time_zone          VARCHAR(100),
    business_hours     VARIANT,
    list_of_holidays   VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SLA_POLICIES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR,
    is_default         BOOLEAN,
    active             BOOLEAN,
    position           NUMBER,
    applicable_to      VARIANT,
    sla_target         VARIANT,
    escalation         VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AUTOMATION_RULES (
    id                 NUMBER PRIMARY KEY,
    automation_type_id NUMBER NOT NULL,
    name               VARCHAR(500),
    active             BOOLEAN,
    position           NUMBER,
    conditions         VARIANT,
    actions            VARIANT,
    performer          VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);
```

### Deliverables
- [ ] `infra/02_storage/raw_freshdesk_tables.sql` created — 25 tables
- [ ] All tables created in `SNOWFLAKE_INTELLIGENCE.RAW`
- [ ] `SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='RAW' AND TABLE_NAME LIKE 'FRESHDESK%'` → 25

---

## Phase 3: Core Ingestion — `INGEST_FRESHDESK()`

### 3.1 V2 API Differences from V1

| Aspect | V1 | V2 |
|--------|----|----|
| Response format | Root-key wrapped (`{"agent": {...}}`) | Flat JSON (no wrapping) |
| Pagination | `page` + `per_page` params | `page` + `per_page`, `Link` header for next |
| Conversations | Embedded in ticket detail (`notes[]`) | Dedicated `/tickets/{id}/conversations` |
| Ticket list | `/helpdesk/tickets.json` (30 default) | `/api/v2/tickets` (100/page) |
| Incremental | Limited | `updated_since` on tickets, `_updated_since` on contacts |

### 3.2 Procedure Architecture

```
INGEST_FRESHDESK()
├── v2_get(url, auth)                     — GET with retry, 429 backoff, dual-bucket awareness
├── v2_paginate(url, auth, bucket)        — Paginate via page param, respect bucket limit
├── ingest_tickets_and_conversations()    — 40/min bucket: list + detail + conversations
├── ingest_contacts()                     — 40/min bucket: paginate with _updated_since
├── ingest_companies()                    — 100/min bucket
├── ingest_agents()                       — 100/min bucket
├── ingest_groups()                       — 100/min bucket
├── ingest_roles()                        — 100/min bucket (NEW in V2)
├── ingest_account()                      — 100/min bucket (NEW in V2)
├── ingest_ticket_fields()                — 100/min bucket
├── ingest_contact_fields()               — 100/min bucket
├── ingest_company_fields()               — 100/min bucket
├── ingest_ticket_forms()                 — 100/min bucket (NEW in V2)
└── log_result()
```

### 3.3 V2 HTTP Client with Dual-Bucket Rate Limiting

```python
import time, requests, _snowflake, json
from datetime import datetime, timezone

BASE_URL = "https://newaccount1623084859360.freshdesk.com/api/v2"
BUCKET_40 = {"remaining": 40, "reset_at": 0}
BUCKET_100 = {"remaining": 100, "reset_at": 0}

def v2_get(path, auth, bucket=BUCKET_100, retries=3, timeout=30):
    now = time.time()
    if bucket["remaining"] <= 2 and now < bucket["reset_at"]:
        time.sleep(bucket["reset_at"] - now + 1)
    for attempt in range(retries):
        try:
            resp = requests.get(f"{BASE_URL}{path}", auth=auth, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        remaining = resp.headers.get('X-RateLimit-Remaining')
        if remaining:
            bucket["remaining"] = int(remaining)
        if resp.status_code == 429:
            wait = int(resp.headers.get('Retry-After', 60))
            bucket["reset_at"] = time.time() + wait
            time.sleep(wait)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code in (401, 403):
            raise Exception(f"Auth/permission error ({resp.status_code}): {path}")
        resp.raise_for_status()
        return resp.json()
    raise Exception(f"Failed after {retries} retries: {path}")

def v2_paginate(path, auth, bucket=BUCKET_100, per_page=100):
    all_items, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        data = v2_get(f"{path}{sep}page={page}&per_page={per_page}", auth, bucket)
        if not data:
            break
        all_items.extend(data)
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.5)
    return all_items

def normalize_ts(ts_str):
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return ts_str

def dedup(records, pk='id'):
    seen = {}
    for r in records:
        key = r.get(pk)
        if key is not None:
            if key not in seen or (r.get('updated_at', '') > seen[key].get('updated_at', '')):
                seen[key] = r
        else:
            seen[id(r)] = r
    return list(seen.values())
```

### 3.4 Ticket + Conversation Ingestion (40/min Bucket — Bottleneck)

```python
def ingest_tickets_and_conversations(auth, session, updated_since=None):
    path = "/tickets"
    if updated_since:
        path += f"?updated_since={updated_since}"
    tickets_raw = v2_paginate(path, auth, BUCKET_40)
    tickets_raw = dedup(tickets_raw)

    conversations = []
    failed = []
    for t in tickets_raw:
        tid = t["id"]
        try:
            convos = v2_paginate(f"/tickets/{tid}/conversations", auth, BUCKET_40, per_page=100)
            for c in convos:
                c["ticket_id"] = tid
                conversations.append(c)
        except Exception as e:
            failed.append({"ticket_id": tid, "error": str(e)})

    if len(failed) > len(tickets_raw) * 0.2:
        raise Exception(f">20% conversation fetches failed ({len(failed)}/{len(tickets_raw)})")

    tickets = [{
        "id": t["id"], "subject": t.get("subject"),
        "description": t.get("description"), "description_text": t.get("description_text"),
        "status": t.get("status"), "priority": t.get("priority"),
        "source": t.get("source"), "type": t.get("type"),
        "requester_id": t.get("requester_id"), "responder_id": t.get("responder_id"),
        "company_id": t.get("company_id"), "group_id": t.get("group_id"),
        "product_id": t.get("product_id"), "email_config_id": t.get("email_config_id"),
        "to_emails": json.dumps(t.get("to_emails", [])),
        "cc_emails": json.dumps(t.get("cc_emails", [])),
        "fwd_emails": json.dumps(t.get("fwd_emails", [])),
        "reply_cc_emails": json.dumps(t.get("reply_cc_emails", [])),
        "fr_escalated": t.get("fr_escalated"), "spam": t.get("spam"),
        "is_escalated": t.get("is_escalated"),
        "tags": json.dumps(t.get("tags", [])),
        "custom_fields": json.dumps(t.get("custom_fields", {})),
        "attachments": json.dumps(t.get("attachments", [])),
        "due_by": normalize_ts(t.get("due_by")),
        "fr_due_by": normalize_ts(t.get("fr_due_by")),
        "created_at": normalize_ts(t.get("created_at")),
        "updated_at": normalize_ts(t.get("updated_at")),
        "raw_json": json.dumps(t),
    } for t in tickets_raw]

    convos_out = [{
        "id": c["id"], "ticket_id": c["ticket_id"],
        "body": c.get("body"), "body_text": c.get("body_text"),
        "user_id": c.get("user_id"), "source": c.get("source"),
        "category": c.get("category"),
        "incoming": c.get("incoming"), "private": c.get("private"),
        "to_emails": json.dumps(c.get("to_emails", [])),
        "from_email": c.get("from_email"),
        "cc_emails": json.dumps(c.get("cc_emails", [])),
        "bcc_emails": json.dumps(c.get("bcc_emails", [])),
        "support_email": c.get("support_email"),
        "attachments": json.dumps(c.get("attachments", [])),
        "last_edited_at": normalize_ts(c.get("last_edited_at")),
        "created_at": normalize_ts(c.get("created_at")),
        "updated_at": normalize_ts(c.get("updated_at")),
        "raw_json": json.dumps(c),
    } for c in conversations]

    if tickets:
        session.create_dataframe(tickets).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS")
    if convos_out:
        session.create_dataframe(convos_out).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_CONVERSATIONS")
    return len(tickets), len(convos_out), failed
```

### 3.5 Main Runner with Per-Entity Isolation

```python
def run(session):
    api_key = _snowflake.get_generic_secret_string('api_key')
    auth = (api_key, "X")
    started = datetime.utcnow()
    errors, counts = [], {}

    last_run = session.sql("""
        SELECT COALESCE(config_value::VARCHAR, '1970-01-01T00:00:00Z')
        FROM SNOWFLAKE_INTELLIGENCE.ADMIN.SYSTEM_CONFIG
        WHERE config_key = 'freshdesk_last_ingested_at'
    """).collect()
    updated_since = last_run[0][0] if last_run else None

    entity_fns = [
        ("tickets_conversations", lambda: ingest_tickets_and_conversations(auth, session, updated_since)),
        ("contacts", lambda: ingest_contacts(auth, session)),
        ("companies", lambda: ingest_simple(auth, session, "/companies", "FRESHDESK_COMPANIES")),
        ("agents", lambda: ingest_simple(auth, session, "/agents", "FRESHDESK_AGENTS")),
        ("groups", lambda: ingest_simple(auth, session, "/groups", "FRESHDESK_GROUPS")),
        ("roles", lambda: ingest_simple(auth, session, "/roles", "FRESHDESK_ROLES", paginate=False)),
        ("account", lambda: ingest_account(auth, session)),
        ("ticket_fields", lambda: ingest_simple(auth, session, "/ticket_fields", "FRESHDESK_TICKET_FIELDS", paginate=False)),
        ("contact_fields", lambda: ingest_simple(auth, session, "/contact_fields", "FRESHDESK_CONTACT_FIELDS", paginate=False)),
        ("company_fields", lambda: ingest_simple(auth, session, "/company_fields", "FRESHDESK_COMPANY_FIELDS", paginate=False)),
        ("ticket_forms", lambda: ingest_simple(auth, session, "/ticket-forms", "FRESHDESK_TICKET_FORMS", paginate=False)),
    ]

    for name, fn in entity_fns:
        try:
            result = fn()
            counts[name] = result if isinstance(result, int) else str(result)
        except Exception as e:
            errors.append({"entity": name, "error": str(e)})

    status = "failed" if len(errors) == len(entity_fns) else "partial_failure" if errors else "success"
    duration = (datetime.utcnow() - started).total_seconds()

    session.sql(f"""
        MERGE INTO SNOWFLAKE_INTELLIGENCE.ADMIN.SYSTEM_CONFIG t
        USING (SELECT 'freshdesk_last_ingested_at' AS config_key,
               TO_VARIANT(CURRENT_TIMESTAMP()::VARCHAR) AS config_value) s
        ON t.config_key = s.config_key
        WHEN MATCHED THEN UPDATE SET config_value = s.config_value, updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (config_key, config_value, updated_at) VALUES (s.config_key, s.config_value, CURRENT_TIMESTAMP())
    """).collect()

    if status == "failed":
        raise Exception(f"All entities failed: {errors}")
    return f"{status}: {json.dumps(counts)}, errors: {len(errors)}, duration: {duration:.0f}s"
```

### Deliverables
- [ ] `infra/03_ingestion/ingest_freshdesk.sql` created
- [ ] V2 API used throughout — no root-key unwrapping
- [ ] Dual-bucket rate limiting (40/min for tickets/contacts, 100/min for rest)
- [ ] Per-entity error isolation — single failure doesn't crash run
- [ ] Deduplication on all paginated fetches
- [ ] Timestamps normalized to UTC
- [ ] `updated_since` watermark for incremental ticket ingestion

---

## Phase 4: Solutions Ingestion — `INGEST_FRESHDESK_SOLUTIONS()`

V2 hierarchy: `/solutions/categories` → `/solutions/categories/{id}/folders` → `/solutions/folders/{id}/articles`

API calls: 1 (categories) + 12 (folders per cat) + 44 (articles per folder) = **57 calls** (100/min bucket — fits in ~1 min)

### Deliverables
- [ ] `infra/03_ingestion/ingest_freshdesk_solutions.sql` created
- [ ] 12 categories, 44 folders, 179 articles ingested
- [ ] `description` (HTML) and `description_text` (plain text) both stored

---

## Phase 5: Discussions Ingestion — `INGEST_FRESHDESK_DISCUSSIONS()`

V2 hierarchy: `/discussions/categories` → `/discussions/categories/{id}/forums` → `/discussions/forums/{id}/topics` → `/discussions/topics/{id}/comments`

API calls: 1 + 1 + 5 + 8 = **15 calls** (100/min bucket)

### Deliverables
- [ ] `infra/03_ingestion/ingest_freshdesk_discussions.sql` created
- [ ] 1 category, 5 forums, 8 topics, 18 comments ingested

---

## Phase 6: Admin Entities — `INGEST_FRESHDESK_ADMIN()`

Single procedure for low-volume admin entities:

| Entity | Endpoint | Records | Paginated |
|--------|----------|---------|-----------|
| Surveys | `/surveys` | 2 | No |
| Satisfaction Ratings | `/surveys/satisfaction_ratings` | 6 | Yes |
| Email Configs | `/email_configs` | 3 | No |
| Email Mailboxes | `/email/mailboxes` | 3 | No |
| Business Hours | `/business_hours` | 1 | No |
| SLA Policies | `/sla_policies` | 1 | No |
| Automation Rules | `/automations/1/rules` + `/3/rules` + `/4/rules` | 64 | No |

API calls: **10 calls** (100/min bucket)

### Deliverables
- [ ] `infra/03_ingestion/ingest_freshdesk_admin.sql` created
- [ ] 7 entity types ingested to 7 RAW tables

---

## Phase 7: Incremental Loading

### 7.1 Strategy

| Entity | Volume | Full Refresh | Incremental | Strategy |
|--------|--------|-------------|-------------|----------|
| Tickets | 1,811 | 1,811 detail + 1,811 convo = 3,622 calls | `updated_since` → ~10-50 calls | **Incremental critical** |
| Contacts | 5,000+ | 50 pages | `_updated_since` → ~1-5 pages | **Incremental beneficial** |
| All others | <500 total | <100 calls | N/A | Full refresh (small) |

### 7.2 Watermark in SYSTEM_CONFIG

```sql
-- Read watermark at start of run
SELECT config_value::VARCHAR FROM ADMIN.SYSTEM_CONFIG
WHERE config_key = 'freshdesk_last_ingested_at';

-- Write watermark after successful run
MERGE INTO ADMIN.SYSTEM_CONFIG ...
```

### 7.3 Growth Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Tickets | > 5,000 | Mandatory incremental (updated_since) |
| Contacts | > 10,000 | Mandatory incremental (_updated_since) |
| Full refresh time | > 120 min | Alert + review |
| API calls/run | > 5,000 | Split procedures |

### Deliverables
- [ ] `updated_since` wired into ticket fetch
- [ ] Watermark stored in SYSTEM_CONFIG after each run
- [ ] Growth warnings at thresholds

---

## Phase 8: Task Scheduling

### 8.1 Task DAG

```
TASK_INGEST_FRESHDESK (cron: 0 3 * * 1 — weekly Monday 3AM) ─────────────┐
    ├── TASK_INGEST_FRESHDESK_SOLUTIONS (AFTER INGEST_FRESHDESK)          │
    ├── TASK_INGEST_FRESHDESK_DISCUSSIONS (AFTER INGEST_FRESHDESK)        ├── TASK_PROCESS_DOCUMENTS
    └── TASK_INGEST_FRESHDESK_ADMIN (AFTER INGEST_FRESHDESK)             │   (AFTER all sources)
                                                                          │
TASK_INGEST_GITBOOK (cron: 0 3 */5 * *) ─────────────────────────────────┘
```

### 8.2 Task DDL

```sql
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 3 * * 1 America/Los_Angeles'
AS CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK();

CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK_SOLUTIONS
    WAREHOUSE = AI_WH
    AFTER SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK
AS CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK_SOLUTIONS();

CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK_DISCUSSIONS
    WAREHOUSE = AI_WH
    AFTER SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK
AS CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK_DISCUSSIONS();

CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK_ADMIN
    WAREHOUSE = AI_WH
    AFTER SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK
AS CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK_ADMIN();
```

### 8.3 Warehouse Time Budget

Full refresh: ~92 min (40/min bottleneck) → AI_WH (XS) running for ~95 min.
Incremental: <5 min → minimal compute cost.
Schedule weekly to balance freshness vs cost.

### Deliverables
- [ ] 4 Freshdesk tasks created
- [ ] Independent from GitBook tasks
- [ ] PROCESS_DOCUMENTS depends on both sources (multi-predecessor)

---

## Phase 9: Testing

### 9.1 Integration Test Minimums (V2 Volumes)

```python
MINIMUM_COUNTS = {
    "FRESHDESK_TICKETS": 1500,
    "FRESHDESK_TICKET_CONVERSATIONS": 100,
    "FRESHDESK_CONTACTS": 4000,
    "FRESHDESK_COMPANIES": 400,
    "FRESHDESK_AGENTS": 30,
    "FRESHDESK_GROUPS": 10,
    "FRESHDESK_ROLES": 3,
    "FRESHDESK_ACCOUNT": 1,
    "FRESHDESK_TICKET_FIELDS": 15,
    "FRESHDESK_CONTACT_FIELDS": 10,
    "FRESHDESK_COMPANY_FIELDS": 10,
    "FRESHDESK_TICKET_FORMS": 1,
    "FRESHDESK_SOLUTION_CATEGORIES": 10,
    "FRESHDESK_SOLUTION_FOLDERS": 30,
    "FRESHDESK_SOLUTION_ARTICLES": 150,
    "FRESHDESK_DISCUSSION_CATEGORIES": 1,
    "FRESHDESK_DISCUSSION_FORUMS": 3,
    "FRESHDESK_DISCUSSION_TOPICS": 5,
    "FRESHDESK_DISCUSSION_COMMENTS": 10,
    "FRESHDESK_SURVEYS": 1,
    "FRESHDESK_SATISFACTION_RATINGS": 3,
    "FRESHDESK_EMAIL_CONFIGS": 2,
    "FRESHDESK_BUSINESS_HOURS": 1,
    "FRESHDESK_SLA_POLICIES": 1,
    "FRESHDESK_AUTOMATION_RULES": 50,
}
```

### 9.2 Referential Integrity

```sql
SELECT 'orphan_conversations' AS check_name, COUNT(*) AS violations
FROM RAW.FRESHDESK_TICKET_CONVERSATIONS c
LEFT JOIN RAW.FRESHDESK_TICKETS t ON c.ticket_id = t.id WHERE t.id IS NULL
UNION ALL
SELECT 'orphan_articles', COUNT(*)
FROM RAW.FRESHDESK_SOLUTION_ARTICLES a
LEFT JOIN RAW.FRESHDESK_SOLUTION_FOLDERS f ON a.folder_id = f.id WHERE f.id IS NULL
UNION ALL
SELECT 'orphan_comments', COUNT(*)
FROM RAW.FRESHDESK_DISCUSSION_COMMENTS c
LEFT JOIN RAW.FRESHDESK_DISCUSSION_TOPICS t ON c.topic_id = t.id WHERE t.id IS NULL;
```

### Deliverables
- [ ] All 25 tables pass minimum count checks
- [ ] Referential integrity: 0 orphans
- [ ] No duplicate PKs across any table
- [ ] All `_loaded_at` within expected window

---

## Phase 10: Monitoring & Alerting

### 10.1 Health View

```sql
CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.ADMIN.V_FRESHDESK_INGESTION_HEALTH AS
WITH stats AS (
    SELECT 'FRESHDESK_TICKETS' AS tbl, COUNT(*) AS cnt, MAX(_loaded_at) AS last_load FROM RAW.FRESHDESK_TICKETS
    UNION ALL SELECT 'FRESHDESK_CONTACTS', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_CONTACTS
    UNION ALL SELECT 'FRESHDESK_SOLUTION_ARTICLES', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_SOLUTION_ARTICLES
    -- ... all 25 tables
)
SELECT tbl, cnt, last_load,
    DATEDIFF('hour', last_load, CURRENT_TIMESTAMP()) AS hours_stale,
    IFF(DATEDIFF('hour', last_load, CURRENT_TIMESTAMP()) > 192, 'STALE', 'OK') AS status
FROM stats;
```

### 10.2 Failure Alert

```sql
CREATE OR REPLACE ALERT SNOWFLAKE_INTELLIGENCE.INGESTION.ALERT_FRESHDESK_FAILURE
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 8 * * * America/Los_Angeles'
    IF (EXISTS (
        SELECT 1 FROM INGESTION.INGESTION_LOG
        WHERE source_system LIKE 'freshdesk%' AND status = 'failed'
          AND completed_at > DATEADD('day', -1, CURRENT_TIMESTAMP())
    ))
    THEN CALL SYSTEM$SEND_EMAIL('SI_EMAIL_NOTIFICATIONS', 'admin@revelator.com',
        'Freshdesk V2 Ingestion Failed', 'Check INGESTION_LOG. Triage: verify API key, check rate limits, run verify script.');
```

### Deliverables
- [ ] Health view created
- [ ] Failure + staleness alerts created

---

## Phase 11: Security & Compliance

### 11.1 PII Masking on Contacts

```sql
ALTER TABLE RAW.FRESHDESK_CONTACTS MODIFY COLUMN email
    SET MASKING POLICY SNOWFLAKE_INTELLIGENCE.ADMIN.MASK_PII_STRING;
ALTER TABLE RAW.FRESHDESK_CONTACTS MODIFY COLUMN phone
    SET MASKING POLICY SNOWFLAKE_INTELLIGENCE.ADMIN.MASK_PII_STRING;
ALTER TABLE RAW.FRESHDESK_CONTACTS MODIFY COLUMN mobile
    SET MASKING POLICY SNOWFLAKE_INTELLIGENCE.ADMIN.MASK_PII_STRING;
```

### 11.2 Row Access on Private Conversations

```sql
ALTER TABLE RAW.FRESHDESK_TICKET_CONVERSATIONS ADD ROW ACCESS POLICY
    SNOWFLAKE_INTELLIGENCE.ADMIN.RAP_PRIVATE_NOTES ON (private);
```

### 11.3 HTML Sanitization

All HTML content (`description`, `body`) sanitized before writing to CURATED (Part 2):
- Strip `<script>`, `<iframe>`, `<object>`, `<embed>`
- Remove `javascript:`, `vbscript:` URIs
- Remove `on*` event handlers

### 11.4 API Key Rotation

1. Generate new key in Freshdesk Admin → Profile
2. `ALTER SECRET FRESHDESK_API_SECRET SET SECRET_STRING = '<new>'`
3. Verify with test call
4. Revoke old key
5. Schedule: quarterly

### Deliverables
- [ ] PII masking applied
- [ ] Row access policy on private conversations
- [ ] Key rotation runbook documented

---

## Implementation Order

```
Phase 1:  Foundation (Secret, Network Rule, EAI)           ← ~1h
Phase 2:  RAW Tables DDL (25 tables)                       ← ~2h (parallel with Phase 1)
Phase 3:  INGEST_FRESHDESK() — core + tickets + contacts   ← ~8h (bottleneck: 40/min bucket handling)
Phase 4:  INGEST_FRESHDESK_SOLUTIONS()                     ← ~3h
Phase 5:  INGEST_FRESHDESK_DISCUSSIONS()                   ← ~2h
Phase 6:  INGEST_FRESHDESK_ADMIN()                         ← ~2h
Phase 7:  Incremental loading + watermarks                 ← ~2h (with Phase 3)
Phase 8:  Task scheduling                                  ← ~2h
Phase 9:  Testing                                          ← ~5h
Phase 10: Monitoring + alerting                            ← ~2h
Phase 11: Security + compliance                            ← ~3h
────────────────────────────────────────────────────────
TOTAL: ~32h
```

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| 40/min ticket bucket causes timeout | High | Incremental via `updated_since`; SP timeout = 120 min |
| V2 disabled on subdomain | High | V1 fallback on `helpdesk.revelator.com`; both in network rule |
| API key expired | High | Alert on failure; quarterly rotation |
| Rate limit headers missing | Low | Conservative 0.5s delay between requests |
| Pagination race (duplicates) | Low | `dedup()` before write |
| PII in conversations | High | Row access policy; only public convos to CURATED (Part 2) |
| Discussion data grows | Low | Already ingesting; pagination handles growth |
| Ticket volume doubles | Medium | Incremental reduces to <100 calls; monitor via threshold |
