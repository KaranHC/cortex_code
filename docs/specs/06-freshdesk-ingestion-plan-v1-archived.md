# PLAN 6: Freshdesk Full Data Ingestion — Staff Engineer Implementation Plan

> Ingest ALL available Freshdesk data into Snowflake: operational entities, field metadata,
> ticket conversations, the complete Solutions knowledge base, and Discussions forums.
> Follows the Snowpark stored procedure pattern established by `INGEST_GITBOOK`.
> Domain: `helpdesk.revelator.com` | Auth: HTTP Basic (API key + "X") | API key: `FRESHDESK_API_KEY` in `.env`

---

## Verified API Findings (March 16, 2026)

> All findings below are from **live API testing** via `scripts/verify_freshdesk_endpoints.py`
> and `scripts/verify_freshdesk_all_endpoints.py` (70+ endpoints tested).
> Not assumptions — every endpoint, field name, wrapping pattern, and volume count was confirmed.

### V1 vs V2 API Status

| Version | Base URL | Status | Notes |
|---------|----------|--------|-------|
| **V1** | `https://helpdesk.revelator.com/*.json` | **30/70 endpoints working** | Only working API on any domain |
| **V2** | `https://helpdesk.revelator.com/api/v2/*` | **ALL 404 (0/9 tested)** | Not available on vanity domain |
| **V2** | `https://revelator.freshdesk.com/api/v2/*` | **ALL 404 (0/9 re-tested 2026-03-16)** | Not available on default subdomain either |
| V1 alt | `https://revelator.freshdesk.com/*.json` | **ALL 404** | Default subdomain serves nothing (V1 or V2) |

**Re-test context (March 16, 2026)**: Freshdesk Support advised that V2 only works on
the default `*.freshdesk.com` subdomain, not vanity/CNAME URLs
([KB article](https://support.freshdesk.com/en/support/solutions/articles/225438)).
We re-tested all V2 endpoints on `revelator.freshdesk.com` — still ALL 404.
Both domains resolve to the **same IP** (`172.66.0.145`), confirming they hit
the same backend. V2 is disabled **account-wide**, not a domain routing issue.
Freshdesk Support must enable V2 on their backend — see Phase 15 action items.

**Conclusion**: V1 on `helpdesk.revelator.com` is the **only** working API path.
All implementation MUST use V1 endpoints.

### Rate Limits

**Observed headers** (from V2 404 responses on vanity domain only):
```
X-RateLimit-Total: 5000
X-RateLimit-Remaining: 4996
x-fw-ratelimiting-managed: false
```

**Important nuance**: V1 200 responses do **not** return any rate limit headers.
The `5000/min` figure comes from V2 404 response headers and may reflect a V2 default,
not the actual V1 limit. `x-fw-ratelimiting-managed: false` suggests V1 is not
actively managed by Freshdesk's rate limiting system.

**Freshdesk Support states**: Account is on **Pro plan** (100 API calls/minute).
This contradicts the 5000 header, but the discrepancy doesn't matter for our use case:
~82 API calls with 0.3s politeness delay completes in ~25 seconds wall time, well within
even a 100/min budget. The `api_get()` function (§3.9) handles 429 responses with
`Retry-After` as a safety net regardless of actual limit.

| Scenario | Rate Limit | 82 calls @ 0.3s delay | Fits? |
|----------|-----------|----------------------|-------|
| Pro plan (per Support) | 100/min | ~25s wall time | ✅ Yes |
| Header value | 5,000/min | ~25s wall time | ✅ Yes |
| Worst case (Growth) | 200/min | ~25s wall time | ✅ Yes |

### Complete Endpoint Verification Results

#### WORKING V1 Endpoints (30 confirmed)

| Category | Endpoint | Status | Count | Root Key | RAG Value |
|----------|----------|--------|-------|----------|-----------|
| **Agents** | `/agents.json` | 200 | 20 | `wrapped:agent` | Medium |
| **Agents** | `/agents/filter/active.json` | 200 | 20 | `wrapped:agent` | Medium |
| **Agents** | `/agents/filter/deleted.json` | 200 | 17 | `wrapped:agent` | Low |
| **Agents** | `/agents/filter/occasional.json` | 200 | 0 | flat | Low |
| **Companies** | `/companies.json` | 200 | 50 | `wrapped:company` | Medium |
| **Contacts** | `/contacts.json` | 200 | 5 (default) | `wrapped:user` | Medium |
| **Contacts** | `/contacts.json?state=verified` | 200 | 50 | `wrapped:user` | Medium |
| **Contacts** | `/contacts.json?state=all` | 200 | 50 | `wrapped:user` | Medium |
| **Contacts** | `/contacts.json?state=deleted` | 200 | 26 | `wrapped:user` | Low |
| **Contacts** | `/contacts.json?state=unverified` | 200 | 50 | `wrapped:user` | Low |
| **Groups** | `/groups.json` | 200 | 13 | `wrapped:group` | Medium |
| **Tickets** | `/helpdesk/tickets.json` | 200 | 30 | **flat** | **High** |
| **Tickets** | `/helpdesk/tickets/{id}.json` | 200 | 1 | `wrapped:helpdesk_ticket` | **High** |
| **Ticket Filters** | `/helpdesk/tickets/filter/all_tickets?format=json` | 200 | 30 | flat | Medium |
| **Ticket Filters** | `/helpdesk/tickets/filter/new_and_my_open?format=json` | 200 | 30 | flat | Medium |
| **Ticket Filters** | `/helpdesk/tickets/filter/spam?format=json` | 200 | 15 | flat | Low |
| **Ticket Filters** | `/helpdesk/tickets/filter/deleted?format=json` | 200 | 30 | flat | Low |
| **Ticket Filters** | `/helpdesk/tickets/filter/monitored_by?format=json` | 200 | 30 | flat | Low |
| **Field Metadata** | `/ticket_fields.json` | 200 | 17 | `wrapped:ticket_field` | **High** |
| **Field Metadata** | `/admin/contact_fields.json` | 200 | 14 | `wrapped:contact_field` | **High** |
| **Field Metadata** | `/admin/company_fields.json` | 200 | 14 | `wrapped:company_field` | **High** |
| **Time Entries** | `/helpdesk/time_sheets.json` | 200 | 0 | flat | Low |
| **Time Entries** | `/helpdesk/tickets/{id}/time_sheets.json` | 200 | 0 | flat | Low |
| **Discussions** | `/discussions/categories.json` | 200 | 1 | `wrapped:forum_category` | Medium |
| **Discussions** | `/discussions/categories/{id}.json` | 200 | 1 | `wrapped:forum_category` | Medium |
| **Discussions** | `/discussions/forums.json` | 200 | 0 | flat | Low |
| **Discussions** | `/discussions/topics.json` | 200 | 0 | flat | Low |
| **CSAT** | `/helpdesk/tickets/{id}/surveys.json` | 200 | 0 | flat | Low |
| **Solutions** | `/solution/categories.json` | 200 | 12 | `wrapped:category` | **High** |
| **Solutions** | `/solution/categories/{id}.json` | 200 | 1 | `wrapped:category` | **High** |

#### NOT FOUND / Unavailable (38+ endpoints confirmed 404)

| Category | Endpoint | Status | Notes |
|----------|----------|--------|-------|
| **Roles** | `/roles.json`, `/admin/roles.json`, `/helpdesk/roles.json` | 404 | **Not available on V1** |
| **Ticket Conversations** | `/helpdesk/tickets/{id}/conversations.json` | 404 | Notes embedded in ticket detail instead |
| **Canned Responses** | `/canned_responses.json`, `/admin/canned_responses/*` | 404 | Not available (204 on `/helpdesk/` path = empty) |
| **Products** | `/products.json`, `/admin/products.json` | 404/406 | Not available |
| **Business Hours** | `/business_hours.json`, `/admin/business_hours.json` | 404 | Not available |
| **SLA Policies** | `/sla_policies.json`, `/admin/sla_policies.json` | 404 | Not available |
| **Email Configs** | `/email_configs.json`, `/admin/email_configs.json` | 404/406 | Not available |
| **Automations** | `/scenario_automations.json`, `/admin/automations.json` | 404 | Not available |
| **Satisfaction Ratings** | `/surveys/satisfaction_ratings.json`, `/surveys.json` | 404 | Global endpoint not available (per-ticket works but empty) |
| **Solution Folders** | `/solution/categories/{id}/folders.json` | 404 | Folders are embedded in category response |
| **Solutions alt** | `/solutions/categories.json` (with 's') | 404 | Must use `/solution/` (no 's') |
| **Discussion Forums** | `/discussions/categories/{id}/forums.json` | 404 | Must use `/discussions/forums.json` globally |
| **V2 (ALL)** | `/api/v2/*` (11 endpoints tested) | 404 | V2 completely disabled |

### KEY DISCOVERY: Ticket Notes Embedded in Ticket Detail

Ticket conversations/notes are **NOT** at a separate endpoint (`/conversations.json` returns 404).
Instead, notes are **embedded in the ticket detail response**:

```
GET /helpdesk/tickets/{display_id}.json
→ {"helpdesk_ticket": {..., "notes": [{"note": {...}}, ...]}}
```

**Verified note structure** (from ticket #61180 which has 1 note):
```
Note keys: [id, body, user_id, source, incoming, private, created_at,
            updated_at, deleted, body_html, attachments, support_email]
```

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `id` | number | `69459082921` | Note ID |
| `body` | string | "Currently, this is not possible..." | **Plain text content** |
| `body_html` | string | `<p>Currently...</p>` | **HTML content** |
| `private` | boolean | `true` | Private (agent-only) or public reply |
| `user_id` | number | `69046699027` | Author agent |
| `incoming` | boolean | `false` | false=outgoing reply, true=customer message |
| `source` | number | `0` | Channel source |
| `attachments` | array | `[]` | File attachments |
| `support_email` | string | email address | Sending email |
| `created_at` | datetime | `2026-03-16T18:12:34+02:00` | |
| `deleted` | boolean | `false` | |

**RAG Value**: **HIGH** — These are actual support agent responses to customer questions. Public notes are direct Q&A pairs.

### Verified Data Volumes (Updated with Comprehensive Testing)

| Entity | Actual Count | V1 Endpoint | Root Key | Ingest? |
|--------|-------------|-------------|----------|---------|
| **Agents (active)** | **20** | `/agents.json` | `agent` | YES |
| **Agents (deleted)** | **17** | `/agents/filter/deleted.json` | `agent` | YES (for ID resolution) |
| **Companies** | **50** | `/companies.json` | `company` | YES |
| **Contacts (all states)** | **50** | `/contacts.json?state=all` | `user` | YES |
| **Contacts (deleted)** | **26** | `/contacts.json?state=deleted` | `user` | YES (for ID resolution) |
| **Groups** | **13** | `/groups.json` | `group` | YES |
| **Tickets** | **30** | `/helpdesk/tickets.json` | **flat** | YES |
| **Ticket Detail + Notes** | **30** (N notes) | `/helpdesk/tickets/{id}.json` | `helpdesk_ticket` | **YES — HIGH VALUE** |
| **Ticket Fields** | **17** | `/ticket_fields.json` | `ticket_field` | YES |
| **Contact Fields** | **14** | `/admin/contact_fields.json` | `contact_field` | YES |
| **Company Fields** | **14** | `/admin/company_fields.json` | `company_field` | YES |
| **Discussion Categories** | **1** | `/discussions/categories.json` | `forum_category` | YES (if forums grow) |
| **Discussion Forums** | **0** | `/discussions/forums.json` | flat | SKIP (empty) |
| **Discussion Topics** | **0** | `/discussions/topics.json` | flat | SKIP (empty) |
| **Time Entries** | **0** | `/helpdesk/time_sheets.json` | flat | SKIP (empty) |
| **Ticket Surveys** | **0** | `/helpdesk/tickets/{id}/surveys.json` | flat | SKIP (empty) |
| **Solution Categories** | **12** | `/solution/categories.json` | `category` | YES |
| **Solution Folders** | **39** | Embedded in category response | in `category.folders[]` | YES |
| **Solution Articles** | **175** (152 published) | `/solution/folders/{id}.json` | `folder.articles[]` | **YES — HIGHEST VALUE** |

### Entity Tiers for Ingestion

**Tier 1 — Must Ingest (Core + High RAG Value)**
1. Solution Articles (175) — KB content, highest RAG value
2. Solution Categories (12) + Folders (39) — KB hierarchy
3. Tickets (30) + Ticket Notes/Conversations — Support Q&A pairs
4. Agents (20 active + 17 deleted) — ID resolution for notes
5. Contacts (50 all + 26 deleted) — Customer context
6. Companies (50) — Account context
7. Groups (13) — Routing context

**Tier 2 — Field Metadata (Schema Intelligence)**
8. Ticket Fields (17) — Custom field definitions
9. Contact Fields (14) — Custom field definitions
10. Company Fields (14) — Custom field definitions

**Tier 3 — Monitor for Growth (Currently Empty/Minimal)**
11. Discussion Categories (1) — Community forums (inactive)
12. Discussion Forums (0) — SKIP until populated
13. Discussion Topics (0) — SKIP until populated
14. Time Entries (0) — SKIP until used
15. Surveys/CSAT (0) — SKIP until used

### Verified Ticket Detail Structure

From live API response for ticket detail (`/helpdesk/tickets/61503.json`):

```
ALL keys: [id, description, requester_id, responder_id, status, urgent, source,
           spam, deleted, created_at, updated_at, trained, subject, display_id,
           owner_id, group_id, due_by, frDueBy, isescalated, priority, fr_escalated,
           to_email, email_config_id, cc_email, delta, ticket_type, description_html,
           parent_ticket_id, dirty, sl_product_id, sl_sla_policy_id,
           sl_merge_parent_ticket, sl_skill_id, st_survey_rating,
           sl_escalation_level, sl_manual_dueby, internal_group_id,
           internal_agent_id, association_type, associates_rdb, sla_state,
           nr_due_by, nr_reminded, nr_escalated, int_tc01..05, long_tc01..05,
           datetime_tc01..03, json_tc01, department_id, status_name,
           requester_status_name, priority_name, source_name, requester_name,
           responder_name, to_emails, product_id, attachments, custom_field, tags, notes]
```

Custom fields on tickets:
```
cf_slack_notified_1957334      — Slack integration
cf_slack_channel_1957334       — Slack channel
cf_enterpriseid_1957334        — Enterprise ID link
cf_what_is_your_issue_type_1957334 — Issue categorization (portal-visible)
cf_a_1957334                   — Nested field A
cf_b_1957334                   — Nested field B
cf_c_1957334                   — Nested field C
```

### Verified Ticket Field Metadata Structure

17 fields from `/ticket_fields.json`:
```
requester              type=default_requester   required=True  portal=True
subject                type=default_subject     required=True  portal=True
ticket_type            type=default_ticket_type required=False portal=False
source                 type=default_source      required=False portal=False
status                 type=default_status      required=True  portal=False
priority               type=default_priority    required=True  portal=False
group                  type=default_group       required=False portal=False
agent                  type=default_agent       required=False portal=False
internal_group         type=default_internal_group  required=False portal=False
internal_agent         type=default_internal_agent  required=False portal=False
description            type=default_description required=True  portal=True
company                type=default_company     required=True  portal=True
cf_slack_notified      type=custom_dropdown     required=False portal=False
cf_slack_channel       type=custom_dropdown     required=False portal=False
cf_enterpriseid        type=custom_number       required=False portal=False
cf_issue_type          type=custom_dropdown     required=False portal=True
cf_a (nested)          type=nested_field        required=False portal=True
```

### Verified Article Field Structure

From live API response for article `69000808409`:

```
Keys: [id, position, art_type, thumbs_up, thumbs_down, hits, created_at,
       updated_at, folder_id, title, description, user_id, status,
       desc_un_html, seo_data, modified_at, modified_by]
```

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `id` | number | `69000808409` | Primary key |
| `title` | string | "FAQ: Frequently Asked Questions" | Article title |
| `description` | string | `<p data-identifyelement="478"...` | **Full HTML content** |
| `desc_un_html` | string | "Can we access a staging demo..." | **Plain text version** |
| `status` | number | `2` | 1=draft, 2=published |
| `folder_id` | number | `69000640913` | Parent folder |
| `user_id` | number | `69006981909` | Creating agent (not `agent_id`) |
| `hits` | number | `4675` | View count |
| `thumbs_up` | number | `5` | Upvotes |
| `thumbs_down` | number | `13` | Downvotes |
| `seo_data` | object | `{meta_title, meta_description}` | SEO metadata |
| `art_type` | number | `1` | Article type |
| `position` | number | `1` | Sort order |
| `modified_at` | datetime | `2025-08-06T14:53:32+03:00` | Last modification |
| `modified_by` | number | `69055229853` | Modifier user ID |

### Verified Category/Folder Breakdown

```
Default Category          → 1 folder  →   0 articles (Drafts)
FAQ                       → 4 folders →  20 articles
Onboarding to Rev Pro     → 1 folder  →   2 articles
Creating & Updating Rel.  → 2 folders →  17 articles
Distribution              → 11 folders → 52 articles ★ Largest
Rights Mgmt & Metadata    → 3 folders →  16 articles
Analytics                 → 2 folders →   5 articles
Data Pro - BI             → 2 folders →   7 articles
Revenue/Royalties/Payouts → 8 folders →  29 articles
Getting Paid by Revelator → 2 folders →  18 articles
Branding/White Labeling   → 1 folder  →   2 articles
User Accounts             → 2 folders →   7 articles
─────────────────────────────────────────────────────
Total:   12 categories, 39 folders, 175 articles (152 published)
```

### Critical V1 API Quirks (All Verified)

1. **Roles endpoint does not exist on V1** — `/roles.json` returns 404 on all paths tested.

2. **Tickets list is FLAT** — V1 ticket listing returns flat objects `[{id, subject, ...}]`, unlike all other entities which use root-key wrapping.

3. **Ticket DETAIL is wrapped** — Single ticket at `/helpdesk/tickets/{id}.json` wraps in `{"helpdesk_ticket": {...}}` and includes `notes[]` array.

4. **Ticket conversations/notes are NOT a separate endpoint** — `/conversations.json` returns 404. Notes are embedded in ticket detail response under `notes[]` key.

5. **Solution Folders are embedded in categories** — `/solution/categories.json` returns folders **inline** in `category.folders[]`. No separate folder listing endpoint.

6. **Solution Articles are embedded in folder detail** — `/solution/folders/{id}.json` returns the folder with articles in `folder.articles[]`. No separate articles list.

7. **Contacts are wrapped as "user"** — Not "contact". `[{"user": {...}}]`

8. **Article text field is `desc_un_html`** — Not `description_text`.

9. **Canned Responses not available** — `/helpdesk/canned_responses.json` returns 204 (No Content), all other paths 404.

10. **Discussion Forums category-scoped endpoint 404** — Must use global `/discussions/forums.json`. Category-specific listing not available.

11. **Contact default page size is 5** — Must use `?state=all` to get full list, or paginate with `per_page=100`.

---

## Decision: Snowpark vs dlt (dlthub)

### dlt Freshdesk Verified Source Analysis

From **actual source code** at `dlt-hub/verified-sources/sources/freshdesk/`:

**`__init__.py`**: Defines `freshdesk_source()` which iterates over endpoint names, creating a `DltResource` per endpoint with `write_disposition="merge"` and `primary_key="id"`. Supports incremental via `updated_at`.

**`freshdesk_client.py`**: `FreshdeskClient` class with:
- `base_url = f"https://{domain}.freshdesk.com/api/v2"` — **hardcoded V2 path**
- `_request_with_rate_limit()` — respects 429 + `Retry-After`
- `paginated_response()` — page-based pagination with `per_page` and `page` params
- Incremental support: only `tickets` uses `updated_since`, `contacts` uses `_updated_since`, others fetch all

**`settings.py`**: `DEFAULT_ENDPOINTS = ["agents", "companies", "contacts", "groups", "roles", "tickets"]`

### Evaluation Matrix

| Criterion | dlt Freshdesk Source | Snowpark Stored Procedure |
|-----------|---------------------|--------------------------|
| **V1 API support** | NO — hardcoded V2 base URL (`/api/v2`). Would 404 on our domain. | YES — targets V1 endpoints directly |
| **Custom domain support** | NO — expects `{domain}.freshdesk.com` format | YES — any base URL |
| **Solutions/KB endpoints** | NO — not in DEFAULT_ENDPOINTS | YES — custom hierarchy traversal |
| **Ticket notes/conversations** | NO — no conversation extraction | YES — extracts from ticket detail |
| **Field metadata** | NO — not in DEFAULT_ENDPOINTS | YES — ticket/contact/company fields |
| **Discussion forums** | NO — not supported | YES — categories/forums/topics |
| **V1 root-key unwrapping** | NO — expects flat V2 responses | YES — per-entity unwrapping |
| **Entity coverage** | 6 (agents, companies, contacts, groups, roles, tickets) | **13 entity types + 3 solution tables** |
| **Architecture fit** | External Python runtime, `.dlt/secrets.toml` | Same pattern as `INGEST_GITBOOK` |

### Verdict: **Snowpark Stored Procedure**

dlt's Freshdesk source would fail on three levels:
1. **V2 hardcoded** — all 404 on `helpdesk.revelator.com`
2. **Domain format** — expects `{domain}.freshdesk.com`, not custom domain
3. **Missing 10+ entity types** — no Solutions, no conversations, no field metadata, no discussions

---

## Phase 0: Pre-Flight Validation ✅ COMPLETED

**Goal**: Confirm API access, measure data volumes, validate ALL V1 endpoint shapes.

### 0.1 Verification Scripts Created

- `scripts/verify_freshdesk_endpoints.py` — 457 lines: V1/V2 comparison, rate limits, data volumes, solutions traversal
- `scripts/verify_freshdesk_all_endpoints.py` — 443 lines: **70+ endpoints** tested across all resource families

### 0.2 Comprehensive Results

- **30 working endpoints** confirmed with data shapes and wrapping patterns
- **38 endpoints** confirmed 404 (documented above)
- **4 other status codes** (500, 204, 406) — edge cases documented
- Key discoveries: ticket notes embedded in detail, canned responses unavailable, discussions empty

### Deliverables
- [x] `scripts/verify_freshdesk_endpoints.py` created and run
- [x] `scripts/verify_freshdesk_all_endpoints.py` created and run
- [x] All V1 and V2 endpoints tested (70+ total)
- [x] Data volumes documented
- [x] Rate limit confirmed: 5,000/minute
- [x] V1 response shapes verified with actual field names
- [x] Ticket notes discovery — embedded in detail, high RAG value
- [x] Field metadata discovery — 17 ticket + 14 contact + 14 company fields
- [x] Discussion forum status — 1 category, 0 forums, 0 topics (inactive)

---

## Phase 1: Foundation — Secrets, Network Rules, External Access Integration

**Goal**: Snowflake security infrastructure for Freshdesk API access.

### 1.1 Snowflake Secret

```sql
CREATE OR REPLACE SECRET SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET
    TYPE = GENERIC_STRING
    SECRET_STRING = '<FRESHDESK_API_KEY>';
```

### 1.2 Network Rule

```sql
CREATE OR REPLACE NETWORK RULE SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_NETWORK_RULE
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = ('helpdesk.revelator.com');
```

### 1.3 External Access Integration

```sql
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION SI_FRESHDESK_ACCESS
    ALLOWED_NETWORK_RULES = (SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_NETWORK_RULE)
    ALLOWED_AUTHENTICATION_SECRETS = (SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET)
    ENABLED = TRUE;
```

### 1.4 Infrastructure File

Create `infra/01_foundation/security_freshdesk.sql`.

### Deliverables
- [ ] Secret, Network Rule, EAI created and tested
- [ ] `DESCRIBE INTEGRATION SI_FRESHDESK_ACCESS` returns ENABLED=TRUE

---

## Phase 2: RAW Storage Layer — Table DDL (13 Tables)

**Goal**: Create RAW tables matching **verified** V1 API response shapes for ALL entity types.

### 2.1 Create `infra/02_storage/raw_freshdesk_tables.sql`

```sql
-- ============================================================
-- Tier 1: Operational Entities
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AGENTS (
    agent_id           NUMBER PRIMARY KEY,
    user_id            NUMBER,
    signature          VARCHAR,
    signature_html     VARCHAR,
    ticket_permission  NUMBER,
    occasional         BOOLEAN,
    points             NUMBER,
    scoreboard_level_id NUMBER,
    is_deleted         BOOLEAN DEFAULT FALSE,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_COMPANIES (
    company_id         NUMBER PRIMARY KEY,
    name               VARCHAR(1000),
    cust_identifier    VARCHAR(500),
    description        VARCHAR,
    note               VARCHAR,
    domains            VARIANT,
    sla_policy_id      NUMBER,
    options            VARIANT,
    custom_field       VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_CONTACTS (
    contact_id         NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    email              VARCHAR(500),
    phone              VARCHAR(100),
    mobile             VARCHAR(100),
    account_id         NUMBER,
    customer_id        NUMBER,
    active             BOOLEAN,
    job_title          VARCHAR(500),
    language           VARCHAR(50),
    time_zone          VARCHAR(100),
    description        VARCHAR,
    address            VARCHAR(1000),
    state              VARCHAR(50),
    custom_field       VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_GROUPS (
    group_id           NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR(2000),
    escalate_to        NUMBER,
    assign_time        NUMBER,
    ticket_assign_type NUMBER,
    business_calendar_id NUMBER,
    toggle_availability BOOLEAN,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS (
    ticket_id          NUMBER,
    display_id         NUMBER,
    subject            VARCHAR(2000),
    description        VARCHAR,
    description_html   VARCHAR,
    status             NUMBER,
    status_name        VARCHAR(100),
    priority           NUMBER,
    priority_name      VARCHAR(100),
    source             NUMBER,
    source_name        VARCHAR(100),
    requester_id       NUMBER,
    requester_name     VARCHAR(500),
    responder_id       NUMBER,
    responder_name     VARCHAR(500),
    group_id           NUMBER,
    owner_id           NUMBER,
    to_email           VARCHAR(500),
    cc_email           VARIANT,
    ticket_type        VARCHAR(100),
    spam               BOOLEAN,
    deleted            BOOLEAN,
    urgent             BOOLEAN,
    isescalated        BOOLEAN,
    parent_ticket_id   NUMBER,
    product_id         NUMBER,
    tags               VARIANT,
    custom_field       VARIANT,
    attachments        VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    due_by             TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_CONVERSATIONS (
    note_id            NUMBER PRIMARY KEY,
    ticket_id          NUMBER NOT NULL,
    ticket_display_id  NUMBER,
    body               VARCHAR,
    body_html          VARCHAR,
    user_id            NUMBER,
    source             NUMBER,
    incoming           BOOLEAN,
    private            BOOLEAN,
    deleted            BOOLEAN,
    support_email      VARCHAR(500),
    attachments        VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ============================================================
-- Tier 2: Field Metadata (Schema Intelligence)
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_FIELDS (
    field_id           NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    label              VARCHAR(500),
    label_in_portal    VARCHAR(500),
    description        VARCHAR,
    field_type         VARCHAR(100),
    position           NUMBER,
    required           BOOLEAN,
    visible_in_portal  BOOLEAN,
    active             BOOLEAN,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_CONTACT_FIELDS (
    field_id           NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    label              VARCHAR(500),
    label_in_portal    VARCHAR(500),
    field_type         VARCHAR(100),
    position           NUMBER,
    required           BOOLEAN,
    visible_in_portal  BOOLEAN,
    deleted            BOOLEAN,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_COMPANY_FIELDS (
    field_id           NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    label              VARCHAR(500),
    field_type         VARCHAR(100),
    position           NUMBER,
    required           BOOLEAN,
    deleted            BOOLEAN,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ============================================================
-- Tier 1: Solutions (Knowledge Base) — V1 Hierarchical
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_CATEGORIES (
    category_id        NUMBER PRIMARY KEY,
    name               VARCHAR(1000),
    description        VARCHAR,
    is_default         BOOLEAN,
    position           NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_FOLDERS (
    folder_id          NUMBER PRIMARY KEY,
    category_id        NUMBER NOT NULL,
    name               VARCHAR(1000),
    description        VARCHAR,
    visibility         NUMBER,
    articles_count     NUMBER,
    is_default         BOOLEAN,
    position           NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_ARTICLES (
    article_id         NUMBER PRIMARY KEY,
    folder_id          NUMBER NOT NULL,
    category_id        NUMBER,
    user_id            NUMBER,
    title              VARCHAR(2000),
    description_html   VARCHAR,
    desc_un_html       VARCHAR,
    status             NUMBER,
    art_type           NUMBER,
    hits               NUMBER,
    thumbs_up          NUMBER,
    thumbs_down        NUMBER,
    position           NUMBER,
    seo_data           VARIANT,
    modified_at        TIMESTAMP_NTZ,
    modified_by        NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- ============================================================
-- Tier 3: Discussions (Community Forums) — Monitor for Growth
-- ============================================================

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_CATEGORIES (
    category_id        NUMBER PRIMARY KEY,
    name               VARCHAR(1000),
    description        VARCHAR,
    position           NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);
```

### 2.2 Convention Notes

- **13 tables total** across 3 tiers
- Every table has `raw_json VARIANT` for schema evolution safety
- `_loaded_at` and `_source_system` match existing GitBook pattern
- Field names match **verified** V1 response shapes exactly
- `FRESHDESK_TICKET_CONVERSATIONS` is a NEW table (notes extracted from ticket detail)
- `FRESHDESK_DISCUSSION_CATEGORIES` is Tier 3 (currently 1 record, monitor for growth)

### Deliverables
- [ ] `infra/02_storage/raw_freshdesk_tables.sql` created
- [ ] All 13 tables created in `SNOWFLAKE_INTELLIGENCE.RAW`
- [ ] `SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='RAW' AND TABLE_NAME LIKE 'FRESHDESK%'` returns 13 rows

---

## Phase 3: Core Ingestion Procedure — Operational Entities

**Goal**: `INGEST_FRESHDESK()` stored procedure for 10 entity types: 5 operational entities + ticket conversations (extracted from detail) + 3 field metadata + discussions.

### 3.1 Create `infra/03_ingestion/ingest_freshdesk.sql`

```
INGEST_FRESHDESK()
├── api_get(url, auth, retries=3)           — HTTP GET with retry/backoff
├── paginate(base_url, path, auth)          — Paginated fetch with per_page=100
├── unwrap_v1(items, root_key)              — Extract from V1 root-key wrapper
├── ingest_agents()                         — /agents.json (active) + /agents/filter/deleted.json → unwrap "agent"
├── ingest_companies()                      — /companies.json → unwrap "company"
├── ingest_contacts()                       — /contacts.json?state=all → unwrap "user"
├── ingest_groups()                         — /groups.json → unwrap "group"
├── ingest_tickets_with_conversations()     — /helpdesk/tickets.json → flat; then per-ticket detail for notes
├── ingest_ticket_fields()                  — /ticket_fields.json → unwrap "ticket_field"
├── ingest_contact_fields()                 — /admin/contact_fields.json → unwrap "contact_field"
├── ingest_company_fields()                 — /admin/company_fields.json → unwrap "company_field"
├── ingest_discussion_categories()          — /discussions/categories.json → unwrap "forum_category"
└── log_result()                            — Insert into INGESTION_LOG
```

### 3.2 V1 Root-Key Unwrapping (All Verified)

```python
V1_ROOT_KEYS = {
    "agents": "agent",
    "companies": "company",
    "contacts": "user",                 # NOT "contact" — verified
    "groups": "group",
    "tickets": None,                    # Tickets LIST is FLAT — verified
    "ticket_detail": "helpdesk_ticket", # Single ticket detail IS wrapped
    "ticket_fields": "ticket_field",
    "contact_fields": "contact_field",
    "company_fields": "company_field",
    "solution_categories": "category",
    "solution_folders": "folder",       # Folder detail response wrapper
    "discussion_categories": "forum_category",
}

def unwrap_v1(items, entity_type):
    root_key = V1_ROOT_KEYS.get(entity_type)
    if root_key:
        return [item.get(root_key, item) for item in items]
    return items
```

### 3.3 Ticket + Conversation Extraction (NEW)

```python
def ingest_tickets_with_conversations(base_url, auth):
    tickets = paginate(base_url, "/helpdesk/tickets.json", auth)
    # Tickets list is flat (no unwrapping)
    
    all_notes = []
    for ticket in tickets:
        display_id = ticket.get("display_id") or ticket.get("id")
        # Fetch ticket detail which includes embedded notes
        detail_url = f"{base_url}/helpdesk/tickets/{display_id}.json"
        detail = api_get(detail_url, auth)
        if detail:
            ht = detail.get("helpdesk_ticket", detail)
            notes = ht.get("notes", [])
            for note in notes:
                n = note.get("note", note)
                n["ticket_id"] = ht.get("id")
                n["ticket_display_id"] = display_id
                all_notes.append(n)
    
    # Write tickets to FRESHDESK_TICKETS
    # Write notes to FRESHDESK_TICKET_CONVERSATIONS
    return len(tickets), len(all_notes)
```

**API calls**: 1 (list) + 30 (detail per ticket) = **31 calls** for tickets + conversations.

### 3.4 Pagination

```python
def paginate(base_url, path, auth, per_page=100):
    all_items = []
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        url = f"{base_url}{path}{sep}page={page}&per_page={per_page}"
        data = api_get(url, auth)
        if not data:
            break
        all_items.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return all_items
```

### 3.5 Rate Limit Handling

```python
def api_get(url, auth, retries=3):
    for attempt in range(retries):
        resp = requests.get(url, auth=auth, timeout=30)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get('Retry-After', 30))
            time.sleep(retry_after)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise Exception(f"Failed after {retries} retries: {url}")
```

### 3.6 Write Strategy

Full refresh for all entities (total ~100 API calls against 5,000/min = trivial):

```python
session.create_dataframe(records).write.mode("overwrite").save_as_table(table_name)
```

### 3.7 Agent Ingestion — Active + Deleted

```python
def ingest_agents(base_url, auth):
    active = paginate(base_url, "/agents.json", auth)
    active = unwrap_v1(active, "agents")
    for a in active:
        a["is_deleted"] = False
    
    deleted = paginate(base_url, "/agents/filter/deleted.json", auth)
    deleted = unwrap_v1(deleted, "agents")
    for a in deleted:
        a["is_deleted"] = True
    
    all_agents = active + deleted  # 20 active + 17 deleted = 37
    # Write to FRESHDESK_AGENTS
```

### 3.8 Contact Ingestion — All States

```python
def ingest_contacts(base_url, auth):
    # Default /contacts.json only returns 5! Must use state=all
    contacts = paginate(base_url, "/contacts.json?state=all", auth)
    contacts = unwrap_v1(contacts, "contacts")
    # Total: 50 contacts (includes verified + unverified)
    # Write to FRESHDESK_CONTACTS
```

### 3.9 Rate Limiting & Resilience Best Practices

The existing `api_get()` (§3.5) handles 429 and 5xx — but needs hardening for production:

```python
import time
import requests

def api_get(url, auth, retries=3, timeout=30):
    for attempt in range(retries):
        try:
            resp = requests.get(url, auth=auth, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise Exception(f"Network error after {retries} retries: {url} — {e}")

        if resp.status_code == 429:
            retry_after = int(resp.headers.get('Retry-After', 30))
            time.sleep(retry_after)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 404:
            return None  # graceful — endpoint may be unavailable
        if resp.status_code in (401, 403):
            raise Exception(f"Auth failure ({resp.status_code}): {url} — check API key validity")
        resp.raise_for_status()

        # Track rate-limit budget for monitoring
        remaining = resp.headers.get('X-RateLimit-Remaining')
        if remaining and int(remaining) < 100:
            time.sleep(1)  # preemptive slow-down near budget exhaustion

        return resp.json()

    raise Exception(f"Failed after {retries} retries: {url}")
```

**Key improvements over base pattern:**
1. **Network errors handled**: `ConnectionError` + `Timeout` caught and retried with backoff
2. **Auth failures fail fast**: 401/403 raise immediately with clear message (not retried)
3. **404 returns None**: Graceful degradation if an endpoint disappears (V1 deprecation)
4. **Preemptive rate-limit**: Tracks `X-RateLimit-Remaining` header, slows down near exhaustion
5. **Politeness delay**: Add `time.sleep(0.3)` in `paginate()` between pages:

```python
def paginate(base_url, path, auth, per_page=100):
    all_items = []
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        url = f"{base_url}{path}{sep}page={page}&per_page={per_page}"
        data = api_get(url, auth)
        if not data:
            break
        all_items.extend(data)
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.3)  # politeness delay — prevents thundering herd
    return all_items
```

### 3.10 Error Handling & Per-Entity Isolation

A single failed entity must NOT crash the entire ingestion. Each entity is wrapped in try/except:

```python
def run(session):
    errors = []
    counts = {}

    for entity_fn in [
        ingest_agents, ingest_companies, ingest_contacts, ingest_groups,
        ingest_tickets_with_conversations, ingest_ticket_fields,
        ingest_contact_fields, ingest_company_fields, ingest_discussion_categories
    ]:
        try:
            count = entity_fn(base_url, auth, session)
            counts[entity_fn.__name__] = count
        except Exception as e:
            errors.append({"entity": entity_fn.__name__, "error": str(e)})

    status = "partial_failure" if errors else "success"
    if len(errors) == len(entity_fns):
        status = "failed"

    # Log to INGESTION_LOG with error details
    session.sql(f"""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
            (source_system, ingestion_type, started_at, completed_at,
             records_ingested, status, details)
        SELECT 'freshdesk', 'full', '{started_at}', CURRENT_TIMESTAMP(),
            {sum(counts.values())}, '{status}',
            PARSE_JSON('{json.dumps({"counts": counts, "errors": errors})}')
    """).collect()

    if status == "failed":
        raise Exception(f"All entities failed: {errors}")
    return f"{status}: {counts}, errors: {errors}"
```

**For ticket detail fetches** — skip individual failures, don't crash the loop:

```python
def ingest_tickets_with_conversations(base_url, auth, session):
    tickets = paginate(base_url, "/helpdesk/tickets.json", auth)
    all_notes = []
    failed_tickets = []

    for ticket in tickets:
        display_id = ticket.get("display_id") or ticket.get("id")
        try:
            detail = api_get(f"{base_url}/helpdesk/tickets/{display_id}.json", auth)
            if detail:
                ht = detail.get("helpdesk_ticket", detail)
                for note in ht.get("notes", []):
                    n = note.get("note", note)
                    n["ticket_id"] = ht.get("id")
                    n["ticket_display_id"] = display_id
                    all_notes.append(n)
        except Exception as e:
            failed_tickets.append({"display_id": display_id, "error": str(e)})

    if len(failed_tickets) > len(tickets) * 0.2:
        raise Exception(f">20% ticket details failed ({len(failed_tickets)}/{len(tickets)})")

    # Write tickets and notes...
    return len(tickets), len(all_notes), failed_tickets
```

**Threshold rule**: If >20% of ticket detail fetches fail, abort the entire entity (likely systemic issue). Otherwise, log failures and continue.

### 3.11 Contact Ingestion — Include Deleted Contacts

The expertise model needs 3 former agents who exist only in contacts (Yoktan, Tshego, Ahuvah).
`?state=all` may NOT include deleted contacts. Fetch both and merge:

```python
def ingest_contacts(base_url, auth, session):
    all_contacts = paginate(base_url, "/contacts.json?state=all", auth)
    all_contacts = unwrap_v1(all_contacts, "contacts")
    all_ids = {c.get("id") for c in all_contacts}

    deleted = paginate(base_url, "/contacts.json?state=deleted", auth)
    deleted = unwrap_v1(deleted, "contacts")
    for c in deleted:
        if c.get("id") not in all_ids:
            c["_is_deleted"] = True
            all_contacts.append(c)

    # Write to FRESHDESK_CONTACTS
    return len(all_contacts)
```

### Deliverables
- [ ] `infra/03_ingestion/ingest_freshdesk.sql` created
- [ ] Procedure compiles and executes successfully
- [ ] 10 entity types loaded: agents(37), companies(50+26 deleted), contacts(50), groups(13), tickets(30), ticket_conversations(N), ticket_fields(17), contact_fields(14), company_fields(14), discussion_categories(1)
- [ ] INGESTION_LOG shows freshdesk entry with status='success'
- [ ] Per-entity error isolation verified: single entity failure doesn't crash procedure
- [ ] Failed ticket details logged but don't abort run (unless >20% failure)
- [ ] Rate-limit budget tracked via `X-RateLimit-Remaining` header
- [ ] Network errors (timeout, connection) retried with exponential backoff
- [ ] 404s handled gracefully (return None, log warning)

---

## Phase 4: Solutions Ingestion — Knowledge Base Hierarchy

**Goal**: Traverse the V1 Solutions hierarchy and load categories, folders, and articles.

### 4.1 V1 Traversal Strategy (Verified)

```
Step 1: GET /solution/categories.json
        → Returns [{category: {id, name, folders: [{id, name, ...}, ...]}}]
        → Extract categories AND folders from this single call

Step 2: For each folder_id from Step 1:
        GET /solution/folders/{folder_id}.json
        → Returns {folder: {id, name, articles: [{id, title, description, ...}, ...]}}
        → Extract articles from each folder detail
```

**Total API calls**: 1 (categories) + 39 (folder details) = **40 calls**.

### 4.2 Separate Procedure: `INGEST_FRESHDESK_SOLUTIONS()`

```
INGEST_FRESHDESK_SOLUTIONS()
├── api_get(url, auth, retries=3)
├── Step 1: Fetch categories + extract embedded folders
│   └── GET /solution/categories.json
│       → Parse category.folders[] for each category
│       → Write categories to FRESHDESK_SOLUTION_CATEGORIES
│       → Write folders to FRESHDESK_SOLUTION_FOLDERS
├── Step 2: For each folder, fetch detail with articles
│   └── GET /solution/folders/{id}.json
│       → Parse folder.articles[]
│       → Enrich each article with category_id (from parent)
│       → Write articles to FRESHDESK_SOLUTION_ARTICLES
└── log_result()
```

### 4.3 Article Content Handling (Verified)

- `description`: Full HTML with Freshdesk `data-identifyelement` attributes
- `desc_un_html`: Plain text version (V1 field name — NOT `description_text`)

Store **both** in RAW. `PROCESS_DOCUMENTS` uses `description` (HTML) through `clean_html()`, fallback to `desc_un_html`.

### 4.4 Published-Only Filtering for RAG

status: 1=draft, 2=published. All go to RAW; only status=2 flow to CURATED.
175 total, **152 published**, 23 draft.

### 4.5 API Call Budget

```
1 call:   /solution/categories.json       → 12 categories + 39 folders
39 calls: /solution/folders/{id}.json     → 175 articles total
──────────────────────────────────────────
40 API calls — < 1 second of rate-limit budget
```

### Deliverables
- [ ] `infra/03_ingestion/ingest_freshdesk_solutions.sql` created
- [ ] Category count: 12, Folder count: 39, Article count: 175
- [ ] HTML content preserved in `description_html` column
- [ ] `desc_un_html` preserved for fallback

---

## Phase 5: Extend PROCESS_DOCUMENTS — Freshdesk Content Processing

**Goal**: Process Freshdesk articles AND ticket conversations into DOCUMENTS + DOCUMENT_CHUNKS for RAG.

### 5.1 Solution Articles → CURATED (Highest Priority)

```python
fd_articles = session.table("SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_ARTICLES").collect()

for row in fd_articles:
    if row["STATUS"] != 2:  # Only published
        continue
    doc_id = make_id("freshdesk", row["ARTICLE_ID"])
    content = row["DESCRIPTION_HTML"] or row["DESC_UN_HTML"] or ""
    if not content.strip() or len(content.strip()) < 50:
        continue
    title = row["TITLE"] or "Untitled"
    source_url = f"https://helpdesk.revelator.com/support/solutions/articles/{row['ARTICLE_ID']}"
    # → INSERT into DOCUMENTS (source_system='freshdesk', doc_type='kb_article')
    # → chunk_text(content, title=title) → INSERT into DOCUMENT_CHUNKS
```

### 5.2 Ticket Conversations → CURATED (High Priority — NEW)

Public ticket notes contain agent-authored support responses — excellent RAG content.

```python
fd_notes = session.table("SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_CONVERSATIONS").collect()

for row in fd_notes:
    if row["PRIVATE"]:  # Skip private internal notes
        continue
    if row["DELETED"]:
        continue
    if row["INCOMING"]:  # Skip customer-authored messages (may contain PII)
        continue          # Only ingest agent-authored responses for RAG
    body = row["BODY_HTML"] or row["BODY"] or ""
    if not body.strip() or len(body.strip()) < 50:
        continue
    
    # Get ticket subject for context
    ticket = get_ticket_by_id(row["TICKET_ID"])
    title = f"Support Response: {ticket['SUBJECT']}" if ticket else "Support Response"
    doc_id = make_id("freshdesk_conversation", row["NOTE_ID"])
    source_url = f"https://helpdesk.revelator.com/helpdesk/tickets/{row['TICKET_DISPLAY_ID']}"
    # → INSERT into DOCUMENTS (source_system='freshdesk', doc_type='ticket_conversation')
    # → chunk_text(body) → INSERT into DOCUMENT_CHUNKS
```

### 5.3 HTML Cleaning (Verified Edge Cases)

Freshdesk V1 HTML patterns handled by existing `clean_html()`:
- `data-identifyelement="478"` attributes → stripped
- `dir="ltr"` attributes → stripped
- `style="line-height: 1.38;"` → stripped
- `&nbsp;` → handled by `html.unescape()`

### 5.4 Metadata Enrichment

```python
# Article metadata
metadata = json.dumps({
    "category_id": str(row["CATEGORY_ID"]),
    "folder_id": str(row["FOLDER_ID"]),
    "user_id": str(row["USER_ID"]),
    "hits": row["HITS"],
    "thumbs_up": row["THUMBS_UP"],
    "thumbs_down": row["THUMBS_DOWN"],
    "seo_data": row["SEO_DATA"]
})

# Conversation metadata
metadata = json.dumps({
    "ticket_id": str(row["TICKET_ID"]),
    "ticket_display_id": str(row["TICKET_DISPLAY_ID"]),
    "user_id": str(row["USER_ID"]),
    "incoming": row["INCOMING"],
    "source": row["SOURCE"]
})
```

### Deliverables
- [ ] `PROCESS_DOCUMENTS()` updated for articles AND conversations
- [ ] Expected: ~152 article documents + N conversation documents
- [ ] HTML correctly converted — spot-check 5 articles + 5 conversations
- [ ] `doc_type` column distinguishes `kb_article` from `ticket_conversation`

---

## Phase 6: Extend CLASSIFY_DOCUMENTS — Freshdesk Auto-Classification

**Goal**: Ensure auto-classification covers Freshdesk articles and conversations.

### 6.1 No Code Changes Expected

`CLASSIFY_DOCUMENTS()` operates on `WHERE topic IS NULL`. New Freshdesk documents auto-classified.

### 6.2 Validate Classification Quality

- KB articles → "FAQ", "Product Documentation", "Technical Guide"
- Ticket conversations → "Support Response", "Troubleshooting"

### Deliverables
- [ ] Classification runs without errors on Freshdesk documents
- [ ] 90%+ have sensible `topic` and `product_area` values

---

## Phase 7: Incremental Loading & Write Atomicity

**Goal**: Support incremental ingestion, ensure atomic writes, and lay the foundation for
future delta-only ingestion as data volumes grow.

### 7.1 Strategy: Full Refresh (Current) with Incremental Foundation

| Entity | Volume | API Calls | Strategy | Incremental Ready? |
|--------|--------|-----------|----------|-------------------|
| Agents (active+deleted) | 37 | 2 | Full refresh | N/A (small) |
| Companies | 50 | 1 | Full refresh | N/A (small) |
| Contacts | 50+26 | 2 | Full refresh | N/A (small) |
| Groups | 13 | 1 | Full refresh | N/A (small) |
| Tickets + Conversations | 30 + N | 31 | Full refresh | **Yes** — `updated_since` wired |
| Ticket Fields | 17 | 1 | Full refresh | N/A (small) |
| Contact Fields | 14 | 1 | Full refresh | N/A (small) |
| Company Fields | 14 | 1 | Full refresh | N/A (small) |
| Discussion Categories | 1 | 1 | Full refresh | N/A (small) |
| Solution Categories | 12 | 1 | Full refresh | N/A (small) |
| Solution Folders | 39 | 0 (embedded) | Full refresh | N/A |
| Solution Articles | 175 | 39 | Full refresh | **Yes** — folder `updated_at` compare |
| **TOTAL** | **~450** | **~81** | | |

With ~81 API calls against 5,000/min limit, full refresh completes in <30 seconds. No incremental needed yet.

### 7.2 Watermark / Checkpoint Mechanism

Even with full refresh, write the high-water mark to enable future incremental:

```python
last_run = session.sql("""
    SELECT COALESCE(value, '1970-01-01T00:00:00Z')
    FROM SNOWFLAKE_INTELLIGENCE.ADMIN.SYSTEM_CONFIG
    WHERE key = 'freshdesk_last_ingested_at'
""").collect()[0][0]

# Wire into ticket fetch (defaults to epoch = full refresh):
tickets = paginate(base_url, f"/helpdesk/tickets.json?updated_since={last_run}", auth)

# After successful ingestion, update watermark:
session.sql(f"""
    MERGE INTO SNOWFLAKE_INTELLIGENCE.ADMIN.SYSTEM_CONFIG t
    USING (SELECT 'freshdesk_last_ingested_at' AS key, CURRENT_TIMESTAMP()::VARCHAR AS value) s
    ON t.key = s.key
    WHEN MATCHED THEN UPDATE SET value = s.value
    WHEN NOT MATCHED THEN INSERT (key, value) VALUES (s.key, s.value)
""").collect()
```

**Default behavior**: Pass `updated_since=1970-01-01` (= full refresh). When incremental is
enabled in the future, pass the actual watermark. Zero code change needed — just stop resetting
the watermark on each run.

### 7.3 Growth Warning — Automated Detection

```python
ticket_count = len(tickets)
if ticket_count > 1000:
    session.sql(f"""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
            (source_system, ingestion_type, started_at, completed_at, status, details)
        SELECT 'freshdesk', 'warning', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), 'warning',
            PARSE_JSON('{{"message": "Ticket volume {ticket_count} approaching incremental threshold (5000)", "recommendation": "Enable incremental via updated_since watermark"}}')
    """).collect()
```

### 7.4 Atomic Writes — Staging Table Swap

**Problem**: `mode("overwrite")` is NOT atomic across tables. If the procedure fails after
writing TICKETS but before TICKET_CONVERSATIONS, data is inconsistent until next run.

**Solution**: Write to staging tables, then swap atomically:

```python
def atomic_write(session, records, target_table, pk_column=None):
    staging = f"{target_table}__STAGING"
    df = session.create_dataframe(records)
    df.write.mode("overwrite").save_as_table(staging)

    # Atomic swap — target gets staging data, staging gets old data (for rollback)
    session.sql(f"ALTER TABLE {staging} SWAP WITH {target_table}").collect()
    session.sql(f"DROP TABLE IF EXISTS {staging}").collect()
```

For the current low-volume scenario, the simpler `mode("overwrite")` is acceptable — but
the staging-swap pattern MUST be used once we have >100 tickets or any downstream consumers
depend on data consistency within a run.

### 7.5 Source-Scoped CURATED Deletes

**Critical fix** for `PROCESS_DOCUMENTS`: Currently it does `DELETE FROM DOCUMENTS` which
wipes ALL sources (GitBook + Freshdesk). If Freshdesk ingestion fails but GitBook succeeds,
the entire CURATED layer is empty.

```python
# INSTEAD OF:
session.sql("DELETE FROM CURATED.DOCUMENT_CHUNKS").collect()
session.sql("DELETE FROM CURATED.DOCUMENTS").collect()

# USE:
session.sql("DELETE FROM CURATED.DOCUMENT_CHUNKS WHERE source_system = 'freshdesk'").collect()
session.sql("DELETE FROM CURATED.DOCUMENTS WHERE source_system = 'freshdesk'").collect()
# ... process Freshdesk content ...

session.sql("DELETE FROM CURATED.DOCUMENT_CHUNKS WHERE source_system = 'gitbook'").collect()
session.sql("DELETE FROM CURATED.DOCUMENTS WHERE source_system = 'gitbook'").collect()
# ... process GitBook content ...
```

This prevents cross-source blast radius — a Freshdesk failure leaves GitBook content intact.

### 7.6 Growth Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Ticket count | > 1,000 | Log warning to INGESTION_LOG |
| Ticket count | > 5,000 | Switch to `updated_since` incremental |
| Article count | > 1,000 | Compare folder `updated_at` to skip unchanged |
| API calls/run | > 500 | Split into entity-specific parallel procedures |
| Run duration | > 180 seconds | Increase SP timeout, consider warehouse size |

### Deliverables
- [ ] Full refresh completes in <30 seconds
- [ ] `SYSTEM_CONFIG` updated with `freshdesk_last_ingested_at` watermark after each run
- [ ] `updated_since` parameter wired into ticket fetch (defaulting to epoch)
- [ ] Growth warning logged when ticket count > 1,000
- [ ] `PROCESS_DOCUMENTS` uses source-scoped deletes (not blanket DELETE)
- [ ] Staging-swap pattern documented and ready for activation at >100 tickets

---

## Phase 8: Task Scheduling — DAG Integration

**Goal**: Wire Freshdesk ingestion into the existing Snowflake Task DAG with proper
independence between data sources.

### 8.1 Updated Task DAG — Parallel Source Ingestion

**Critical change**: GitBook and Freshdesk are independent data sources. A GitBook failure
must NOT block Freshdesk ingestion (and vice versa). Use multi-predecessor Tasks:

```
TASK_INGEST_GITBOOK (cron: 0 3 */5 * *)                    ─┐
                                                              ├── TASK_PROCESS_DOCUMENTS (AFTER both)
TASK_INGEST_FRESHDESK (cron: 0 3 */5 * *)                  ─┤      └── TASK_CLASSIFY_DOCUMENTS
    └── TASK_INGEST_FRESHDESK_SOLUTIONS (AFTER FRESHDESK)  ──┘

FULL_REFRESH (cron: 0 2 1,15 * *)
    → Ingests FIRST, truncates curated AFTER successful ingestion
    → Skips if regular run completed within 12 hours
```

### 8.2 New Task DDL

```sql
-- Freshdesk is its own root task (NOT dependent on GitBook)
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 3 */5 * * America/Los_Angeles'
AS
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK();

CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK_SOLUTIONS
    WAREHOUSE = AI_WH
    AFTER SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK
AS
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK_SOLUTIONS();

-- PROCESS_DOCUMENTS depends on BOTH sources completing (multi-predecessor)
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_PROCESS_DOCUMENTS
    WAREHOUSE = AI_WH
    AFTER SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_GITBOOK,
         SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_INGEST_FRESHDESK_SOLUTIONS
AS
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.PROCESS_DOCUMENTS();
```

### 8.3 FULL_REFRESH — Safe Truncate Pattern

**Problem with current pattern**: Truncating ALL tables BEFORE ingestion means if ingestion
fails, both RAW and CURATED are empty. The Cortex Search service has zero documents until recovery.

**Fix**: Ingest first, then swap/truncate CURATED only after success:

```sql
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.FULL_REFRESH
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 2 1,15 * * America/Los_Angeles'
    WHEN SYSTEM$GET_PREDECESSOR_RETURN_VALUE IS NULL  -- only if not already triggered by regular schedule
AS
BEGIN
    -- Step 1: Re-ingest all sources (overwrite mode handles RAW tables)
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_GITBOOK();
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK();
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK_SOLUTIONS();

    -- Step 2: Only AFTER successful ingestion, rebuild CURATED
    -- Source-scoped deletes prevent cross-source blast radius
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.PROCESS_DOCUMENTS();
    CALL SNOWFLAKE_INTELLIGENCE.INGESTION.CLASSIFY_DOCUMENTS();
END;
```

### 8.4 Overlap Prevention

The biweekly FULL_REFRESH (1st & 15th) and the every-5-day regular schedule may overlap.
Add a staleness check to skip redundant runs:

```python
# At the start of INGEST_FRESHDESK():
last_run = session.sql("""
    SELECT MAX(completed_at)
    FROM SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
    WHERE source_system = 'freshdesk' AND status IN ('success', 'partial_failure')
""").collect()[0][0]

if last_run and (datetime.utcnow() - last_run).total_seconds() < 43200:  # 12 hours
    return "Skipped — last successful run was within 12 hours"
```

### 8.5 Pre-Check in PROCESS_DOCUMENTS

Verify both sources have recent data before processing:

```python
def verify_sources(session):
    for table, source in [
        ("RAW.GITBOOK_PAGES", "gitbook"),
        ("RAW.FRESHDESK_SOLUTION_ARTICLES", "freshdesk"),
    ]:
        result = session.sql(f"""
            SELECT COUNT(*), MAX(_loaded_at)
            FROM SNOWFLAKE_INTELLIGENCE.{table}
        """).collect()[0]
        if result[0] == 0:
            raise Exception(f"ABORT: {table} is empty — {source} ingestion may have failed")
        hours_stale = (datetime.utcnow() - result[1]).total_seconds() / 3600
        if hours_stale > 144:  # 6 days
            log_warning(f"{table} data is {hours_stale:.0f}h old — may be stale")
```

### 8.6 Task Resume Order (bottom-up)

```sql
ALTER TASK TASK_CLASSIFY_DOCUMENTS RESUME;
ALTER TASK TASK_PROCESS_DOCUMENTS RESUME;
ALTER TASK TASK_INGEST_FRESHDESK_SOLUTIONS RESUME;
ALTER TASK TASK_INGEST_FRESHDESK RESUME;
ALTER TASK TASK_INGEST_GITBOOK RESUME;
ALTER TASK FULL_REFRESH RESUME;
```

### Deliverables
- [ ] Freshdesk tasks created as independent root tasks (not dependent on GitBook)
- [ ] PROCESS_DOCUMENTS depends on BOTH GitBook and Freshdesk (multi-predecessor)
- [ ] FULL_REFRESH ingests BEFORE truncating CURATED (safe pattern)
- [ ] Overlap prevention: skip if last run < 12 hours ago
- [ ] Pre-check: PROCESS_DOCUMENTS verifies both sources have data before proceeding
- [ ] Task DAG executes end-to-end without errors

---

## Phase 9: Cortex Search Service Update

**Goal**: Verify Cortex Search automatically picks up Freshdesk chunks.

### 9.1 No DDL Changes Required

`DOCUMENT_SEARCH` is defined over `CURATED.DOCUMENT_CHUNKS`. Freshdesk chunks auto-indexed.

### 9.2 Validation

```sql
SELECT COUNT(*), source_system, doc_type
FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
GROUP BY source_system, doc_type;
-- Expected: gitbook ~935, freshdesk/kb_article ~300-600, freshdesk/ticket_conversation ~N
```

### Deliverables
- [ ] Freshdesk chunks indexed
- [ ] Search returns Freshdesk results alongside GitBook
- [ ] `source_system` filter works

---

## Phase 10: Agent Prompt Update

**Goal**: Update Cortex Agent system prompt to be aware of Freshdesk data sources.

### 10.1 Update All 3 Agent Variants

```
DATA SOURCES:
1. GitBook (source_system='gitbook') — Product docs, API docs, technical guides
2. Freshdesk KB (source_system='freshdesk', doc_type='kb_article') — 175 articles across
   12 categories: FAQ, Distribution, Revenue/Royalties, Onboarding, Analytics, etc.
3. Freshdesk Conversations (source_system='freshdesk', doc_type='ticket_conversation') —
   Agent support responses to customer questions

For customer-facing support (FAQ, how-to, troubleshooting) → prioritize Freshdesk KB.
For step-by-step resolution of specific issues → check Freshdesk Conversations.
For technical/product documentation → prioritize GitBook.
Always cite source_system in attribution.
```

### 10.2 Update Streamlit Source Display

Ensure `app/pages/1_Ask_a_Question.py` renders "Freshdesk KB" and "Freshdesk Support" source cards.

### Deliverables
- [ ] All 3 agents updated
- [ ] Agent correctly cites Freshdesk sources
- [ ] Streamlit UI renders Freshdesk source cards

---

## Phase 10.5: Agent Expertise Model — "Who Can Help With This?"

**Goal**: Build a comprehensive expertise model that maps **every** Freshdesk agent (37 total:
20 active + 17 deleted) to their topic-level expertise using **9 weighted signals**, producing
L1→L2→L3 tiered escalation paths so the Cortex Agent can answer "who should I contact about X?"
with ranked contact lists.

### 10.5.1 Data Sources & Expertise Signals (9 Signals, All Verified)

Every signal below was verified via live API testing (`scripts/freshdesk_expertise_deep_dive.py`).

| # | Signal | Source Table | Join Key | Weight | Rationale |
|---|--------|-------------|----------|--------|-----------|
| 1 | **KB articles authored** | `FRESHDESK_SOLUTION_ARTICLES.user_id` | → agent `user_id` via `raw_json:user:id` | **×10** | Deepest signal — they wrote the documentation |
| 2 | **KB articles modified** | `FRESHDESK_SOLUTION_ARTICLES.modified_by` | → agent `user_id` | **×3** | Reviewed/maintained content |
| 3 | **KB article hits** (popularity) | `FRESHDESK_SOLUTION_ARTICLES.hits` | per author | **×0.01/hit** | Popular articles = proven expertise |
| 4 | **KB article ratings** | `FRESHDESK_SOLUTION_ARTICLES.thumbs_up/thumbs_down` | per author | **+2/up, -1/down** | Quality signal |
| 5 | **Ticket notes authored** (public) | `FRESHDESK_TICKET_CONVERSATIONS` WHERE `incoming=false, private=false` | → agent `user_id` | **×5** | Public support responses = customer-facing expertise |
| 6 | **Ticket notes authored** (private) | `FRESHDESK_TICKET_CONVERSATIONS` WHERE `incoming=false, private=true` | → agent `user_id` | **×2** | Internal notes = domain knowledge but less visible |
| 7 | **Ticket note substance** | `LENGTH(body)` on conversations | per author | **×0.001/char** | Longer replies = more substantive help |
| 8 | **Ticket responder assignment** | `FRESHDESK_TICKETS.responder_id` | → agent `agent_id` | **×3** | Designated resolver for this issue type |
| 9 | **Recency of activity** | `modified_at`, `created_at` on articles/notes | per (agent, topic) | **×0.2–1.0** | Recent activity weighted higher |

**Critical ID Resolution**: Articles and conversations reference `user_id`, NOT `agent_id`.
Each agent has both: e.g., Meira Rahamim has `agent_id=69000303225` and `user_id=69087956474`.
The `FRESHDESK_AGENTS` table stores both via `raw_json:user:id`. Additionally, 3 top historical
contributors exist only as contacts (not in the agent list at all) — these are resolved via
`FRESHDESK_CONTACTS` as fallback.

### 10.5.2 Scoring Model

```
EXPERTISE SCORE per (agent, topic) =

  Base Points:
    (KB articles authored × 10)
  + (KB articles modified × 3)
  + (Ticket notes public × 5)
  + (Ticket notes private × 2)
  + (Tickets assigned × 3)

  Quality Bonuses:
  + (Article hits × 0.01)
  + (Article thumbs_up × 2) - (Article thumbs_down × 1)
  + (Note body characters × 0.001)

  Multipliers:
  × Recency factor:
      ≤90 days ago:   1.0
      91–180 days:    0.8
      181–365 days:   0.6
      366–730 days:   0.4
      >730 days:      0.2
  × Status factor:
      Active agent:   1.0
      Deleted agent:  0.5   (valuable for context but deprioritized for contact)
```

### 10.5.3 Tier Definitions

| Tier | Label | Criteria | Use Case |
|------|-------|----------|----------|
| **L1** | Primary Expert | Rank #1 in topic AND score ≥ 20 | First contact — owns this domain |
| **L2** | Secondary Expert | Rank #2–3 in topic AND score ≥ 10 | Escalation or backup if L1 unavailable |
| **L3** | Contributing Expert | Score ≥ 5 | Has relevant experience, can assist |
| **--** | Minimal | Score < 5 | Not listed as contact for this topic |

### 10.5.4 Complete Agent Roster (37 Agents, All Verified)

#### Active Agents (20) — Global Activity Summary

| Agent | Email | KB Auth | KB Mod | Notes | Tickets | Topics | L1 | L2 | L3 | Total Score |
|-------|-------|---------|--------|-------|---------|--------|----|----|----|----|
| Rebecca \| Revelator | rebecca.stary@revelator.com | 31 | 1 | 0 | 0 | 6 | 2 | 1 | 3 | 424.6 |
| Golan Aharony | golan@revelator.com | 7 | 3 | 0 | 0 | 3 | 0 | 2 | 1 | 139.4 |
| Rev Marketing | marketing@revelator.com | 9 | 10 | 0 | 0 | 7 | 1 | 2 | 4 | 125.3 |
| Meira Rahamim | meira@revelator.com | 0 | 0 | 10 | 7 | 3 | 1 | 0 | 0 | 91.1 |
| Kenny \| Revelator | kenny@revelator.com | 1 | 8 | 1 | 0 | 3 | 0 | 1 | 0 | 42.3 |
| Revelator Support | marko@revelator.com | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 21.0 |
| Maya Marija Jovic | marija@revelator.com | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 1 | 5.6 |
| Matheus Telles | matheus@revelator.com | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 2.2 |
| Nicolas Guasca | nicolas.g@revelator.com | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 2.0 |
| Similise \| Revelator | similise@revelator.com | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0.0 |
| Adrián Martínez Azorín | adrian@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Challey Legg | challey@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Effy \| Yu | effy@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Jovana Borkovic | jovana@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Lena Djuricic | lena@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Marija Cekić | marija.cekic@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Milan Adamović | milan@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Naomi \| Revelator | naomi@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Revelator Inspection & YT Ops | inspection@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Revelator UGC Support | ugcsupport@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |

#### Deleted Agents (17) — Historical Contributors

| Agent | Email | KB Auth | KB Mod | Notes | Topics | L1 | L2 | L3 | Total Score |
|-------|-------|---------|--------|-------|--------|----|----|----|----|
| Yoktan \| Revelator ¹ | yoktan@revelator.com | 53 | 11 | 0 | 8 | 3 | 2 | 1 | 757.5 |
| Tshego Mogodi ¹ | tshego.mogodi@revelator.com | 27 | 11 | 7 | 12 | 0 | 3 | 4 | 187.3 |
| Rafael \| Revelator | rafael@revelator.com | 13 | 3 | 0 | 6 | 1 | 0 | 1 | 59.9 |
| Lulu \| Revelator | lulu@revelator.com | 6 | 0 | 0 | 4 | 0 | 2 | 0 | 38.5 |
| Miriam Lottner | miriam@revelator.com | 7 | 3 | 0 | 4 | 0 | 1 | 0 | 35.4 |
| Ahuvah Berger ¹ | ahuvah.berger@revelator.com | 15 | 2 | 0 | 5 | 0 | 1 | 2 | 31.6 |
| Jo Friedman | jo@revelator.com | 1 | 18 | 0 | 5 | 0 | 0 | 1 | 18.7 |
| Viraj \| Revelator | viraj@revelator.com | 2 | 0 | 0 | 1 | 0 | 0 | 1 | 10.6 |
| Maria \| Revelator | maria@revelator.com | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 6.4 |
| Alain Prasquier | alain@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Claudia \| Revelator | claudia.garcia@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Customer Service | custserv@freshdesk.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Eric Denis | eric@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Euniz L | euniz@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Malka Lehman | malka@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Meg M | meg@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |
| Nikita Shenkar | nikita@revelator.com | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |

> ¹ Not in agent list (only in contacts table). Resolved via `FRESHDESK_CONTACTS` fallback join.

### 10.5.5 Complete Tiered Expertise Map — All 14 Topics

#### Distribution (10 experts, 3 active)

| Tier | Agent | Email | Status | Score | KB | Mod | Notes | Hits | Recency |
|------|-------|-------|--------|-------|-----|-----|-------|------|---------|
| **L1** | Yoktan \| Revelator | yoktan@revelator.com | deleted | 515.4 | 29 | 5 | 0 | 52,476 | 7d |
| L2 | **Rebecca \| Revelator** | rebecca.stary@revelator.com | **active** | 151.6 | 4 | 1 | 0 | 9,251 | 144d |
| L2 | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 68.2 | 7 | 4 | 0 | 5,447 | 14d |
| L3 | **Rev Marketing** | marketing@revelator.com | **active** | 22.2 | 1 | 4 | 0 | 23 | 20d |
| L3 | Jo Friedman | jo@revelator.com | deleted | 14.8 | 1 | 2 | 0 | 1,165 | 83d |
| L3 | Viraj \| Revelator | viraj@revelator.com | deleted | 10.6 | 2 | 0 | 0 | 843 | 273d |
| L3 | **Golan Aharony** | golan@revelator.com | **active** | 9.2 | 1 | 2 | 0 | 691 | 693d |
| L3 | Ahuvah Berger | ahuvah.berger@revelator.com | deleted | 9.2 | 4 | 2 | 0 | 4,204 | 1190d |
| -- | Lulu \| Revelator | lulu@revelator.com | deleted | 2.6 | 2 | 0 | 0 | 656 | 1446d |
| -- | Rafael \| Revelator | rafael@revelator.com | deleted | 1.4 | 1 | 0 | 0 | 154 | 1061d |

> **Active escalation**: Rebecca (L2, 151.6) → Rev Marketing (L3, 22.2) → Golan (L3, 9.2)

#### Getting Paid by Revelator (4 experts, 1 active)

| Tier | Agent | Email | Status | Score | KB | Mod | Notes | Hits |
|------|-------|-------|--------|-------|-----|-----|-------|------|
| **L1** | **Rebecca \| Revelator** | rebecca.stary@revelator.com | **active** | 161.3 | 16 | 0 | 0 | 9,987 |
| L2 | Lulu \| Revelator | lulu@revelator.com | deleted | 16.0 | 1 | 0 | 0 | 3,019 |
| -- | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 3.5 | 1 | 0 | 0 | 162 |
| -- | Jo Friedman | jo@revelator.com | deleted | 1.5 | 0 | 5 | 0 | 0 |

> **Active escalation**: Rebecca (L1, 161.3) — **sole active expert**, dominant with 16 KB articles

#### Rights Management & Metadata (5 experts, 3 active)

| Tier | Agent | Email | Status | Score | KB | Mod | Notes | Hits |
|------|-------|-------|--------|-------|-----|-----|-------|------|
| **L1** | Yoktan \| Revelator | yoktan@revelator.com | deleted | 111.2 | 8 | 2 | 0 | 11,230 |
| L2 | **Golan Aharony** | golan@revelator.com | **active** | 75.3 | 3 | 1 | 0 | 5,717 |
| L2 | **Rev Marketing** | marketing@revelator.com | **active** | 13.4 | 1 | 1 | 0 | 39 |
| L3 | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 10.0 | 2 | 0 | 0 | 304 |
| L3 | **Rebecca \| Revelator** | rebecca.stary@revelator.com | **active** | 7.4 | 2 | 0 | 0 | 1,611 |

> **Active escalation**: Golan (L2, 75.3) → Rev Marketing (L2, 13.4) → Rebecca (L3, 7.4)

#### Revenue Reports, Royalty Statements & Payee Payouts (11 experts, 4 active)

| Tier | Agent | Email | Status | Score | KB | Mod | Notes | Hits |
|------|-------|-------|--------|-------|-----|-----|-------|------|
| **L1** | Rafael \| Revelator | rafael@revelator.com | deleted | 47.7 | 9 | 2 | 0 | 6,312 |
| L2 | **Kenny \| Revelator** | kenny@revelator.com | **active** | 39.2 | 1 | 7 | 0 | 816 |
| L2 | Miriam Lottner | miriam@revelator.com | deleted | 34.4 | 6 | 0 | 0 | 5,460 |
| L3 | **Rebecca \| Revelator** | rebecca.stary@revelator.com | **active** | 26.9 | 2 | 0 | 0 | 2,286 |
| L3 | **Revelator Support** | marko@revelator.com | **active** | 21.0 | 1 | 0 | 0 | 1,627 |
| L3 | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 17.3 | 3 | 0 | 0 | 1,130 |
| L3 | Yoktan \| Revelator | yoktan@revelator.com | deleted | 15.7 | 3 | 3 | 0 | 3,145 |
| L3 | **Rev Marketing** | marketing@revelator.com | **active** | 13.2 | 1 | 1 | 0 | 153 |
| -- | Lulu \| Revelator | lulu@revelator.com | deleted | 2.8 | 1 | 0 | 0 | 1,456 |
| -- | Ahuvah Berger | ahuvah.berger@revelator.com | deleted | 2.4 | 2 | 0 | 0 | 222 |
| -- | Jo Friedman | jo@revelator.com | deleted | 2.4 | 0 | 8 | 0 | 0 |

> **Active escalation**: Kenny (L2, 39.2) → Rebecca (L3, 26.9) → Revelator Support (L3, 21.0) → Rev Marketing (L3, 13.2)

#### FAQ (9 experts, 4 active)

| Tier | Agent | Email | Status | Score | KB | Mod | Notes | Hits |
|------|-------|-------|--------|-------|-----|-----|-------|------|
| **L1** | **Rebecca \| Revelator** | rebecca.stary@revelator.com | **active** | 65.5 | 5 | 0 | 0 | 3,815 |
| L2 | **Golan Aharony** | golan@revelator.com | **active** | 54.9 | 3 | 0 | 0 | 5,353 |
| L2 | Yoktan \| Revelator | yoktan@revelator.com | deleted | 24.9 | 2 | 0 | 0 | 6,102 |
| L3 | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 24.8 | 4 | 2 | 0 | 1,098 |
| L3 | **Rev Marketing** | marketing@revelator.com | **active** | 22.5 | 2 | 0 | 0 | 246 |
| L3 | Maria \| Revelator | maria@revelator.com | deleted | 6.4 | 1 | 0 | 0 | 2,693 |
| -- | Rafael \| Revelator | rafael@revelator.com | deleted | 3.5 | 1 | 0 | 0 | 1,344 |
| -- | **Nicolas Guasca** | nicolas.g@revelator.com | **active** | 2.0 | 1 | 0 | 0 | 0 |
| -- | Miriam Lottner | miriam@revelator.com | deleted | 1.0 | 1 | 0 | 0 | 0 |

> **Active escalation**: Rebecca (L1, 65.5) → Golan (L2, 54.9) → Rev Marketing (L3, 22.5)

#### General Support — Tickets (5 experts, 4 active)

| Tier | Agent | Email | Status | Score | KB | Notes (pub+priv) | Assigned | Recency |
|------|-------|-------|--------|-------|-----|-------------------|----------|---------|
| **L1** | **Meira Rahamim** | meira@revelator.com | **active** | 85.1 | 0 | 4p + 6i | 5 | 6d |
| L3 | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 9.1 | 0 | 1p + 5i | 0 | 0d |
| L3 | **Maya Marija Jovic** | marija@revelator.com | **active** | 5.6 | 0 | 1p + 0i | 0 | 3d |
| -- | **Kenny \| Revelator** | kenny@revelator.com | **active** | 3.1 | 0 | 0p + 1i | 0 | 21d |
| -- | **Matheus Telles** | matheus@revelator.com | **active** | 2.2 | 0 | 0p + 1i | 0 | 69d |

> **Active escalation**: Meira (L1, 85.1) → Maya (L3, 5.6) → Kenny (below threshold) → Matheus

#### Creating & Updating Releases (7 experts, 2 active)

| Tier | Agent | Email | Status | Score | KB | Mod | Hits |
|------|-------|-------|--------|-------|-----|-----|------|
| **L1** | Yoktan \| Revelator | yoktan@revelator.com | deleted | 71.8 | 6 | 1 | 10,262 |
| L2 | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 23.5 | 4 | 3 | 963 |
| L2 | Lulu \| Revelator | lulu@revelator.com | deleted | 17.1 | 2 | 0 | 1,613 |
| L3 | **Rev Marketing** | marketing@revelator.com | **active** | 16.6 | 1 | 2 | 63 |
| L3 | **Rebecca \| Revelator** | rebecca.stary@revelator.com | **active** | 11.9 | 2 | 0 | 1,082 |
| -- | Rafael \| Revelator | rafael@revelator.com | deleted | 1.7 | 1 | 0 | 961 |
| -- | Ahuvah Berger | ahuvah.berger@revelator.com | deleted | 1.0 | 1 | 0 | 0 |

> **Active escalation**: Rev Marketing (L3, 16.6) → Rebecca (L3, 11.9)

#### User Accounts (3 experts, 1 active)

| Tier | Agent | Email | Status | Score | KB | Mod | Hits |
|------|-------|-------|--------|-------|-----|-----|------|
| **L1** | **Rev Marketing** | marketing@revelator.com | **active** | 26.9 | 2 | 2 | 91 |
| L2 | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 23.9 | 4 | 0 | 777 |
| -- | Yoktan \| Revelator | yoktan@revelator.com | deleted | 2.2 | 1 | 0 | 952 |

> **Active escalation**: Rev Marketing (L1, 26.9) — sole active expert

#### Analytics (3 experts, 1 active)

| Tier | Agent | Email | Status | Score | KB | Hits |
|------|-------|-------|--------|-------|-----|------|
| L2 | Yoktan \| Revelator | yoktan@revelator.com | deleted | 12.5 | 3 | 2,646 |
| L2 | **Rev Marketing** | marketing@revelator.com | **active** | 10.5 | 1 | 47 |
| -- | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 2.0 | 1 | 0 |

> **Active escalation**: Rev Marketing (L2, 10.5) — only active contributor

#### Data Pro / BI (1 expert, 0 active) ⚠

| Tier | Agent | Email | Status | Score | KB | Hits |
|------|-------|-------|--------|-------|-----|------|
| L2 | Ahuvah Berger | ahuvah.berger@revelator.com | deleted | 10.4 | 7 | 2,988 |

> **⚠ NO ACTIVE EXPERTS** — All 7 Data Pro/BI articles written by former agent

#### Branding and White Labeling (2 experts, 0 active) ⚠

| Tier | Agent | Email | Status | Score | KB | Hits |
|------|-------|-------|--------|-------|-----|------|
| L3 | Ahuvah Berger | ahuvah.berger@revelator.com | deleted | 8.6 | 1 | 1,879 |
| -- | Yoktan \| Revelator | yoktan@revelator.com | deleted | 3.8 | 1 | 889 |

> **⚠ NO ACTIVE EXPERTS** — Both contributors are former agents

#### Onboarding to Revelator Pro (2 experts, 0 active) ⚠

| Tier | Agent | Email | Status | Score | KB | Hits |
|------|-------|-------|--------|-------|-----|------|
| L3 | Rafael \| Revelator | rafael@revelator.com | deleted | 5.6 | 1 | 4,269 |
| -- | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 3.9 | 1 | 304 |

> **⚠ NO ACTIVE EXPERTS** — High-traffic article (4,269 hits) but no active owner

#### Problem (ticket type) (2 experts, 1 active)

| Tier | Agent | Email | Status | Score | Notes | Assigned |
|------|-------|-------|--------|-------|-------|----------|
| -- | **Meira Rahamim** | meira@revelator.com | **active** | 3.0 | 0 | 1 |
| -- | Tshego Mogodi | tshego.mogodi@revelator.com | deleted | 1.1 | 1i | 0 |

#### Request (ticket type) (1 expert, 1 active)

| Tier | Agent | Email | Status | Score | Assigned |
|------|-------|-------|--------|-------|----------|
| -- | **Meira Rahamim** | meira@revelator.com | **active** | 3.0 | 1 |

### 10.5.6 Key Findings & Expertise Gaps

**Top 5 Active Agents by Total Expertise Score**:

| Rank | Agent | Email | Score | Strongest Area |
|------|-------|-------|-------|----------------|
| 1 | Rebecca \| Revelator | rebecca.stary@revelator.com | 424.6 | Getting Paid (L1), FAQ (L1), Distribution (L2) |
| 2 | Golan Aharony | golan@revelator.com | 139.4 | Rights Mgmt (L2), FAQ (L2), Distribution (L3) |
| 3 | Rev Marketing | marketing@revelator.com | 125.3 | User Accounts (L1), 6 more topics at L2-L3 |
| 4 | Meira Rahamim | meira@revelator.com | 91.1 | General Support (L1) — primary ticket responder |
| 5 | Kenny \| Revelator | kenny@revelator.com | 42.3 | Revenue/Royalties (L2), top active modifier |

**Top 3 Historical Contributors (deleted but critical for context)**:

| Rank | Agent | Email | Score | Note |
|------|-------|-------|-------|------|
| 1 | Yoktan \| Revelator | yoktan@revelator.com | 757.5 | All-time #1, 53 KB articles, L1 in 3 topics |
| 2 | Tshego Mogodi | tshego.mogodi@revelator.com | 187.3 | 27 KB + 7 ticket notes, active across 12 topics |
| 3 | Rafael \| Revelator | rafael@revelator.com | 59.9 | Revenue/Royalties L1, 13 KB articles |

**⚠ Expertise Gaps (topics with NO active L1/L2 experts)**:

| Topic | Gap | Recommendation |
|-------|-----|----------------|
| Data Pro / BI | 0 active experts, 7 articles by Ahuvah (deleted) | Assign active agent to own this domain |
| Branding & White Labeling | 0 active experts | Assign active agent |
| Onboarding to Revelator Pro | 0 active experts, 4,269-hit article unowned | Assign active agent — high-traffic content |
| Creating & Updating Releases | 0 active L1/L2 — best active is Rev Marketing at L3 (16.6) | Promote or assign |
| Distribution | No active L1 — Rebecca is L2 (151.6) but Yoktan (deleted) holds L1 (515.4) | Rebecca effectively inherits L1 |

### 10.5.7 CURATED View: `V_FRESHDESK_AGENT_EXPERTISE`

```sql
CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.CURATED.V_FRESHDESK_AGENT_EXPERTISE AS
WITH agent_users AS (
    SELECT
        agent_id,
        (raw_json:user:id)::NUMBER AS user_id,
        (raw_json:user:name)::VARCHAR AS agent_name,
        (raw_json:user:email)::VARCHAR AS agent_email,
        is_deleted,
        CASE WHEN is_deleted THEN 'deleted' ELSE 'active' END AS agent_status
    FROM SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AGENTS
),
kb_authored AS (
    SELECT
        art.user_id,
        sc.name AS topic,
        COUNT(*) AS articles_authored,
        SUM(art.hits) AS total_hits,
        SUM(art.thumbs_up) AS total_thumbs_up,
        SUM(art.thumbs_down) AS total_thumbs_down,
        MIN(DATEDIFF('day', COALESCE(art.modified_at, art.updated_at), CURRENT_TIMESTAMP())) AS best_recency_days
    FROM SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_ARTICLES art
    JOIN SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_CATEGORIES sc
        ON art.category_id = sc.category_id
    GROUP BY art.user_id, sc.name
),
kb_modified AS (
    SELECT
        art.modified_by AS user_id,
        sc.name AS topic,
        COUNT(*) AS articles_modified
    FROM SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_ARTICLES art
    JOIN SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_CATEGORIES sc
        ON art.category_id = sc.category_id
    WHERE art.modified_by IS NOT NULL
      AND art.modified_by != art.user_id
    GROUP BY art.modified_by, sc.name
),
ticket_notes AS (
    SELECT
        c.user_id,
        COALESCE(t.ticket_type, 'General Support') AS topic,
        COUNT(CASE WHEN c.private = FALSE THEN 1 END) AS notes_public,
        COUNT(CASE WHEN c.private = TRUE THEN 1 END) AS notes_private,
        SUM(LENGTH(COALESCE(c.body, c.body_html, ''))) AS note_chars,
        COUNT(DISTINCT c.ticket_id) AS tickets_touched,
        MIN(DATEDIFF('day', c.created_at, CURRENT_TIMESTAMP())) AS best_recency_days
    FROM SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_CONVERSATIONS c
    JOIN SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS t
        ON c.ticket_id = t.ticket_id
    WHERE c.incoming = FALSE
      AND c.deleted = FALSE
    GROUP BY c.user_id, COALESCE(t.ticket_type, 'General Support')
),
ticket_assigned AS (
    SELECT
        au.user_id,
        COALESCE(t.ticket_type, 'General Support') AS topic,
        COUNT(*) AS tickets_assigned,
        MIN(DATEDIFF('day', t.created_at, CURRENT_TIMESTAMP())) AS best_recency_days
    FROM SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS t
    JOIN agent_users au ON t.responder_id = au.agent_id
    WHERE t.responder_id IS NOT NULL
    GROUP BY au.user_id, COALESCE(t.ticket_type, 'General Support')
),
all_signals AS (
    SELECT user_id, topic FROM kb_authored
    UNION SELECT user_id, topic FROM kb_modified
    UNION SELECT user_id, topic FROM ticket_notes
    UNION SELECT user_id, topic FROM ticket_assigned
),
scored AS (
    SELECT
        au.agent_id,
        au.user_id,
        au.agent_name,
        au.agent_email,
        au.agent_status,
        s.topic,
        COALESCE(ka.articles_authored, 0) AS kb_articles_authored,
        COALESCE(km.articles_modified, 0) AS kb_articles_modified,
        COALESCE(ka.total_hits, 0) AS kb_hits,
        COALESCE(ka.total_thumbs_up, 0) AS kb_thumbs_up,
        COALESCE(ka.total_thumbs_down, 0) AS kb_thumbs_down,
        COALESCE(tn.notes_public, 0) AS ticket_notes_public,
        COALESCE(tn.notes_private, 0) AS ticket_notes_private,
        COALESCE(tn.note_chars, 0) AS ticket_note_chars,
        COALESCE(tn.tickets_touched, 0) AS tickets_responded_to,
        COALESCE(ta.tickets_assigned, 0) AS tickets_assigned,
        LEAST(
            COALESCE(ka.best_recency_days, 9999),
            COALESCE(tn.best_recency_days, 9999),
            COALESCE(ta.best_recency_days, 9999)
        ) AS best_recency_days,
        -- Raw score
        (COALESCE(ka.articles_authored, 0) * 10)
          + (COALESCE(km.articles_modified, 0) * 3)
          + (COALESCE(tn.notes_public, 0) * 5)
          + (COALESCE(tn.notes_private, 0) * 2)
          + (COALESCE(ta.tickets_assigned, 0) * 3)
          + (COALESCE(ka.total_hits, 0) * 0.01)
          + (COALESCE(ka.total_thumbs_up, 0) * 2)
          - (COALESCE(ka.total_thumbs_down, 0) * 1)
          + (COALESCE(tn.note_chars, 0) * 0.001)
        AS raw_score,
        -- Recency multiplier
        CASE
            WHEN LEAST(COALESCE(ka.best_recency_days,9999), COALESCE(tn.best_recency_days,9999), COALESCE(ta.best_recency_days,9999)) <= 90 THEN 1.0
            WHEN LEAST(COALESCE(ka.best_recency_days,9999), COALESCE(tn.best_recency_days,9999), COALESCE(ta.best_recency_days,9999)) <= 180 THEN 0.8
            WHEN LEAST(COALESCE(ka.best_recency_days,9999), COALESCE(tn.best_recency_days,9999), COALESCE(ta.best_recency_days,9999)) <= 365 THEN 0.6
            WHEN LEAST(COALESCE(ka.best_recency_days,9999), COALESCE(tn.best_recency_days,9999), COALESCE(ta.best_recency_days,9999)) <= 730 THEN 0.4
            ELSE 0.2
        END AS recency_multiplier,
        -- Status multiplier
        CASE WHEN au.agent_status = 'active' THEN 1.0 ELSE 0.5 END AS status_multiplier
    FROM all_signals s
    JOIN agent_users au ON s.user_id = au.user_id
    LEFT JOIN kb_authored ka ON s.user_id = ka.user_id AND s.topic = ka.topic
    LEFT JOIN kb_modified km ON s.user_id = km.user_id AND s.topic = km.topic
    LEFT JOIN ticket_notes tn ON s.user_id = tn.user_id AND s.topic = tn.topic
    LEFT JOIN ticket_assigned ta ON s.user_id = ta.user_id AND s.topic = ta.topic
)
SELECT
    *,
    ROUND(raw_score * recency_multiplier * status_multiplier, 1) AS expertise_score,
    ROW_NUMBER() OVER (PARTITION BY topic ORDER BY raw_score * recency_multiplier * status_multiplier DESC) AS topic_rank,
    CASE
        WHEN ROW_NUMBER() OVER (PARTITION BY topic ORDER BY raw_score * recency_multiplier * status_multiplier DESC) = 1
             AND raw_score * recency_multiplier * status_multiplier >= 20 THEN 'L1'
        WHEN ROW_NUMBER() OVER (PARTITION BY topic ORDER BY raw_score * recency_multiplier * status_multiplier DESC) <= 3
             AND raw_score * recency_multiplier * status_multiplier >= 10 THEN 'L2'
        WHEN raw_score * recency_multiplier * status_multiplier >= 5 THEN 'L3'
        ELSE '--'
    END AS expertise_tier
FROM scored
WHERE raw_score * recency_multiplier * status_multiplier >= 1
ORDER BY topic, expertise_score DESC;
```

### 10.5.8 CURATED View: `V_FRESHDESK_TOPIC_CONTACTS`

Active-first escalation paths per topic.

```sql
CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.CURATED.V_FRESHDESK_TOPIC_CONTACTS AS
SELECT
    topic AS expertise_area,
    agent_name,
    agent_email,
    agent_status,
    expertise_tier,
    expertise_score,
    kb_articles_authored,
    kb_articles_modified,
    kb_hits,
    ticket_notes_public,
    ticket_notes_private,
    tickets_assigned,
    best_recency_days,
    ROW_NUMBER() OVER (
        PARTITION BY topic
        ORDER BY
            CASE WHEN agent_status = 'active' THEN 0 ELSE 1 END,
            expertise_score DESC
    ) AS active_first_rank
FROM SNOWFLAKE_INTELLIGENCE.CURATED.V_FRESHDESK_AGENT_EXPERTISE
WHERE expertise_tier IN ('L1', 'L2', 'L3')
QUALIFY active_first_rank <= 5;
```

### 10.5.9 CURATED Table: `FRESHDESK_AGENT_DIRECTORY`

Flat agent roster for Streamlit and agent prompt context.

```sql
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.CURATED.FRESHDESK_AGENT_DIRECTORY (
    agent_id              NUMBER,
    user_id               NUMBER,
    agent_name            VARCHAR(500),
    agent_email           VARCHAR(500),
    agent_status          VARCHAR(20),
    total_kb_authored     NUMBER,
    total_kb_modified     NUMBER,
    total_kb_hits         NUMBER,
    total_ticket_notes    NUMBER,
    total_tickets_assigned NUMBER,
    topics_as_l1          NUMBER,
    topics_as_l2          NUMBER,
    topics_as_l3          NUMBER,
    top_expertise_areas   VARCHAR(2000),
    overall_score         NUMBER,
    latest_activity_days  NUMBER,
    _loaded_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

Populated after ingestion:

```python
directory = session.sql("""
    SELECT
        agent_id, user_id, agent_name, agent_email, agent_status,
        SUM(kb_articles_authored) AS total_kb_authored,
        SUM(kb_articles_modified) AS total_kb_modified,
        SUM(kb_hits) AS total_kb_hits,
        SUM(ticket_notes_public + ticket_notes_private) AS total_ticket_notes,
        SUM(tickets_assigned) AS total_tickets_assigned,
        COUNT(CASE WHEN expertise_tier = 'L1' THEN 1 END) AS topics_as_l1,
        COUNT(CASE WHEN expertise_tier = 'L2' THEN 1 END) AS topics_as_l2,
        COUNT(CASE WHEN expertise_tier = 'L3' THEN 1 END) AS topics_as_l3,
        LISTAGG(DISTINCT topic, ', ')
            WITHIN GROUP (ORDER BY expertise_score DESC) AS top_expertise_areas,
        ROUND(SUM(expertise_score), 1) AS overall_score,
        MIN(best_recency_days) AS latest_activity_days
    FROM CURATED.V_FRESHDESK_AGENT_EXPERTISE
    GROUP BY agent_id, user_id, agent_name, agent_email, agent_status
    ORDER BY overall_score DESC
""")
directory.write.mode("overwrite").save_as_table(
    "SNOWFLAKE_INTELLIGENCE.CURATED.FRESHDESK_AGENT_DIRECTORY"
)
```

### 10.5.10 Agent Prompt Integration

Add to Cortex Agent system prompt (all 3 variants):

```
4. Agent Expertise Directory — When the user asks "who should I contact about X?",
   "who knows about Y?", or "who is the expert on Z?":
   a) Query V_FRESHDESK_TOPIC_CONTACTS WHERE expertise_area ILIKE '%<topic>%'
   b) Return agents in active_first_rank order with tier labels
   c) Format: "L1 (Primary): Name <email> — L2 (Backup): Name <email>"
   d) If no active experts exist for a topic, warn: "No active experts — historical
      contact: <name> (former agent)"
   e) Always include email addresses for direct contact
   f) If topic unclear, query FRESHDESK_AGENT_DIRECTORY for agents with highest
      overall_score as general contacts
```

### 10.5.11 Streamlit Contact Directory Page

New page `app/pages/4_Contact_Directory.py`:
- **Escalation view**: Select topic → shows L1→L2→L3 path with active-first ordering
- **Agent roster view**: Full table of all agents with scores, sortable by any column
- **Gap alert**: Highlights topics with ⚠ NO ACTIVE EXPERTS in red
- **Search**: Filter by name/email/topic
- **Export**: CSV download of directory

### Deliverables
- [ ] `V_FRESHDESK_AGENT_EXPERTISE` view created — returns 74 (agent, topic) pairs with 9 signals
- [ ] `V_FRESHDESK_TOPIC_CONTACTS` view returns active-first escalation paths per topic
- [ ] `FRESHDESK_AGENT_DIRECTORY` table populated — 20 active + 17 deleted agents
- [ ] All 14 topics have verified L1/L2/L3 assignments matching deep-dive analysis
- [ ] 3 contact-only former agents (Yoktan, Tshego, Ahuvah) resolved via fallback join
- [ ] Agent prompt updated with expertise query instructions
- [ ] Streamlit contact directory page renders with escalation paths + gap alerts
- [ ] Test: "Who should I contact about distribution?" → Rebecca (L2) → Rev Marketing (L3) → Golan (L3)
- [ ] Test: "Who handles revenue/royalties?" → Kenny (L2) → Rebecca (L3) → Revelator Support (L3)
- [ ] Test: "Who knows about Data Pro/BI?" → ⚠ No active experts, historical: Ahuvah Berger

---

## Phase 11: Testing & Validation

**Goal**: Comprehensive test coverage — unit tests for core functions, range-based integration
tests, referential integrity checks, and automated E2E evaluation.

### 11.1 Update Static Validation Tests

```python
"03_ingestion": [
    "ingest_gitbook.sql",
    "ingest_freshdesk.sql",
    "ingest_freshdesk_solutions.sql",
    "process_documents.sql",
    "classify_documents.sql",
    "tasks.sql"
],
```

### 11.2 Unit Tests for Core Functions

Extract and test `unwrap_v1()`, `paginate()` (mocked HTTP), `clean_html()` in isolation:

```python
# tests/test_freshdesk_core.py
import pytest

def test_unwrap_v1_agents():
    raw = [{"agent": {"id": 1, "name": "Alice"}}, {"agent": {"id": 2, "name": "Bob"}}]
    result = unwrap_v1(raw, "agents")
    assert result == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

def test_unwrap_v1_tickets_flat():
    raw = [{"id": 1, "subject": "Help"}]
    result = unwrap_v1(raw, "tickets")
    assert result == raw  # tickets are flat, no unwrapping

def test_unwrap_v1_missing_key_fallback():
    raw = [{"wrong_key": {"id": 1}}, {"agent": {"id": 2}}]
    result = unwrap_v1(raw, "agents")
    assert result[0] == {"wrong_key": {"id": 1}}  # falls back to raw item
    assert result[1] == {"id": 2}

def test_clean_html_freshdesk_attributes():
    html = '<p data-identifyelement="478">Hello <strong>world</strong></p>'
    result = clean_html(html)
    assert "data-identifyelement" not in result
    assert "**world**" in result

def test_clean_html_table_to_markdown():
    html = '<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>'
    result = clean_html(html)
    assert "| A | B |" in result
    assert "| 1 | 2 |" in result
```

### 11.3 Integration Tests — Range-Based Assertions

Hardcoded counts break when data changes. Use minimum thresholds:

```python
def test_freshdesk_raw_tables_populated(self, sf_cursor):
    minimum_counts = {
        "FRESHDESK_AGENTS": 30,            # at least 30 (currently 37)
        "FRESHDESK_COMPANIES": 40,          # at least 40 (currently 50)
        "FRESHDESK_CONTACTS": 40,           # at least 40 (currently 50+)
        "FRESHDESK_GROUPS": 10,             # at least 10 (currently 13)
        "FRESHDESK_TICKETS": 10,            # at least 10 (currently 30)
        "FRESHDESK_TICKET_CONVERSATIONS": 1,# at least 1
        "FRESHDESK_TICKET_FIELDS": 10,      # at least 10 (currently 17)
        "FRESHDESK_CONTACT_FIELDS": 10,     # at least 10 (currently 14)
        "FRESHDESK_COMPANY_FIELDS": 10,     # at least 10 (currently 14)
        "FRESHDESK_DISCUSSION_CATEGORIES": 1,
        "FRESHDESK_SOLUTION_CATEGORIES": 5, # at least 5 (currently 12)
        "FRESHDESK_SOLUTION_FOLDERS": 20,   # at least 20 (currently 39)
        "FRESHDESK_SOLUTION_ARTICLES": 100, # at least 100 (currently 175)
    }
    for table, min_count in minimum_counts.items():
        result = sf_cursor.execute(f"SELECT COUNT(*) FROM RAW.{table}").fetchone()
        assert result[0] >= min_count, f"{table}: expected >= {min_count}, got {result[0]}"
```

### 11.4 Referential Integrity Checks

```sql
-- All ticket_conversations reference a valid ticket
SELECT COUNT(*) FROM RAW.FRESHDESK_TICKET_CONVERSATIONS tc
LEFT JOIN RAW.FRESHDESK_TICKETS t ON tc.ticket_id = t.ticket_id
WHERE t.ticket_id IS NULL;
-- Expected: 0

-- All articles reference a valid category
SELECT COUNT(*) FROM RAW.FRESHDESK_SOLUTION_ARTICLES a
LEFT JOIN RAW.FRESHDESK_SOLUTION_CATEGORIES c ON a.category_id = c.category_id
WHERE c.category_id IS NULL;
-- Expected: 0

-- All articles reference a valid folder
SELECT COUNT(*) FROM RAW.FRESHDESK_SOLUTION_ARTICLES a
LEFT JOIN RAW.FRESHDESK_SOLUTION_FOLDERS f ON a.folder_id = f.folder_id
WHERE f.folder_id IS NULL;
-- Expected: 0

-- CURATED documents all have at least 1 chunk
SELECT d.document_id FROM CURATED.DOCUMENTS d
LEFT JOIN CURATED.DOCUMENT_CHUNKS c ON d.document_id = c.document_id
WHERE d.source_system = 'freshdesk'
GROUP BY d.document_id
HAVING COUNT(c.chunk_id) = 0;
-- Expected: 0 rows

-- Freshness check: _loaded_at within expected window
SELECT table_name, MAX(_loaded_at), DATEDIFF('hour', MAX(_loaded_at), CURRENT_TIMESTAMP()) AS hours_stale
FROM (
    SELECT 'AGENTS' AS table_name, _loaded_at FROM RAW.FRESHDESK_AGENTS
    UNION ALL SELECT 'ARTICLES', _loaded_at FROM RAW.FRESHDESK_SOLUTION_ARTICLES
)
GROUP BY table_name
HAVING hours_stale > 144;  -- 6 days
-- Expected: 0 rows
```

### 11.5 Data Quality Checks

```sql
SELECT COUNT(*) FROM RAW.FRESHDESK_SOLUTION_ARTICLES WHERE status = 2 AND title IS NULL;
-- Expected: 0

SELECT COUNT(*) FROM CURATED.DOCUMENTS
WHERE source_system = 'freshdesk' AND (content IS NULL OR LENGTH(content) < 50);
-- Expected: 0

SELECT document_id, COUNT(*) as cc FROM CURATED.DOCUMENT_CHUNKS
WHERE source_system = 'freshdesk' GROUP BY 1 HAVING cc > 20 OR cc = 0;
-- Expected: 0 rows

SELECT COUNT(*) FROM RAW.FRESHDESK_TICKET_CONVERSATIONS WHERE body IS NULL AND body_html IS NULL;
-- Expected: 0

-- Duplicate PK check across all tables
SELECT 'AGENTS' AS tbl, agent_id, COUNT(*) FROM RAW.FRESHDESK_AGENTS GROUP BY 2 HAVING COUNT(*) > 1
UNION ALL
SELECT 'TICKETS', ticket_id, COUNT(*) FROM RAW.FRESHDESK_TICKETS GROUP BY 2 HAVING COUNT(*) > 1
UNION ALL
SELECT 'ARTICLES', article_id, COUNT(*) FROM RAW.FRESHDESK_SOLUTION_ARTICLES GROUP BY 2 HAVING COUNT(*) > 1;
-- Expected: 0 rows
```

### 11.6 End-to-End Smoke Test (Automated)

Add to `scripts/run_eval.py` for automated regression testing:

```python
FRESHDESK_EVAL_CASES = [
    {
        "question": "How do I distribute music on TikTok?",
        "expected_source": "freshdesk",
        "expected_doc_type": "kb_article",
    },
    {
        "question": "How do I pay payees with PayPal?",
        "expected_source": "freshdesk",
        "expected_doc_type": "kb_article",
    },
    {
        "question": "Who should I contact about distribution?",
        "expected_contacts": ["Rebecca", "Rev Marketing"],
        "expected_source": "freshdesk_expertise",
    },
]
```

### Deliverables
- [ ] Unit tests for `unwrap_v1()`, `clean_html()` pass (pytest)
- [ ] Integration tests pass with range-based thresholds (13 tables)
- [ ] Referential integrity: 0 orphaned conversations/articles/chunks
- [ ] Data quality checks pass (0 violations, 0 duplicates)
- [ ] Automated E2E eval cases added to `scripts/run_eval.py`
- [ ] E2E smoke test passes — Freshdesk sources cited in agent responses

---

## Phase 12: Monitoring & Alerting

**Goal**: Production monitoring with staleness detection, performance metrics, and
rate-limit tracking.

### 12.1 INGESTION_LOG Schema Extension

Add columns to support richer monitoring (backwards-compatible):

```sql
ALTER TABLE SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG ADD COLUMN IF NOT EXISTS
    details VARIANT;          -- {counts: {}, errors: [], api_calls: N, duration_seconds: N}
ALTER TABLE SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG ADD COLUMN IF NOT EXISTS
    duration_seconds NUMBER;
ALTER TABLE SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG ADD COLUMN IF NOT EXISTS
    api_calls_made NUMBER;
```

### 12.2 Alert — Failure Detection

```sql
CREATE OR REPLACE ALERT SNOWFLAKE_INTELLIGENCE.INGESTION.ALERT_FRESHDESK_FAILURE
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 8 * * * America/Los_Angeles'
    IF (EXISTS (
        SELECT 1 FROM SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
        WHERE source_system = 'freshdesk' AND status = 'failed'
          AND completed_at > DATEADD('day', -1, CURRENT_TIMESTAMP())
    ))
    THEN CALL SYSTEM$SEND_EMAIL(
        'SI_EMAIL_NOTIFICATIONS', 'admin@revelator.com',
        'Freshdesk Ingestion Failed',
        'Check INGESTION_LOG for details. Triage: (1) Verify API key, (2) Run verify_freshdesk_endpoints.py, (3) Check X-RateLimit-Remaining in details column.');
```

### 12.3 Alert — Staleness Detection (NEW)

Detect when ingestion hasn't run at all (silent failure — task suspended, cron didn't fire):

```sql
CREATE OR REPLACE ALERT SNOWFLAKE_INTELLIGENCE.INGESTION.ALERT_FRESHDESK_STALE
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 9 * * * America/Los_Angeles'
    IF (NOT EXISTS (
        SELECT 1 FROM SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
        WHERE source_system = 'freshdesk'
          AND status IN ('success', 'partial_failure')
          AND completed_at > DATEADD('day', -6, CURRENT_TIMESTAMP())
    ))
    THEN CALL SYSTEM$SEND_EMAIL(
        'SI_EMAIL_NOTIFICATIONS', 'admin@revelator.com',
        'Freshdesk Ingestion Stale — No Successful Run in 6 Days',
        'The Freshdesk pipeline has not completed successfully in 6+ days. Check: (1) TASK_INGEST_FRESHDESK status, (2) Is the task suspended?, (3) Warehouse availability.');
```

### 12.4 Volume & Health Monitoring (Improved)

Use actual `_loaded_at` from data (not `INFORMATION_SCHEMA.last_altered` which reflects DDL):

```sql
CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.ADMIN.V_FRESHDESK_INGESTION_HEALTH AS
WITH table_stats AS (
    SELECT 'FRESHDESK_AGENTS' AS table_name, COUNT(*) AS row_count, MAX(_loaded_at) AS last_data_write FROM RAW.FRESHDESK_AGENTS
    UNION ALL SELECT 'FRESHDESK_COMPANIES', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_COMPANIES
    UNION ALL SELECT 'FRESHDESK_CONTACTS', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_CONTACTS
    UNION ALL SELECT 'FRESHDESK_GROUPS', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_GROUPS
    UNION ALL SELECT 'FRESHDESK_TICKETS', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_TICKETS
    UNION ALL SELECT 'FRESHDESK_TICKET_CONVERSATIONS', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_TICKET_CONVERSATIONS
    UNION ALL SELECT 'FRESHDESK_SOLUTION_ARTICLES', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_SOLUTION_ARTICLES
    UNION ALL SELECT 'FRESHDESK_SOLUTION_CATEGORIES', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_SOLUTION_CATEGORIES
    UNION ALL SELECT 'FRESHDESK_SOLUTION_FOLDERS', COUNT(*), MAX(_loaded_at) FROM RAW.FRESHDESK_SOLUTION_FOLDERS
),
expected_ranges AS (
    SELECT * FROM VALUES
        ('FRESHDESK_AGENTS', 30, 100),
        ('FRESHDESK_COMPANIES', 40, 200),
        ('FRESHDESK_CONTACTS', 40, 500),
        ('FRESHDESK_TICKETS', 10, 10000),
        ('FRESHDESK_SOLUTION_ARTICLES', 100, 1000)
    AS t(table_name, min_expected, max_expected)
)
SELECT
    ts.table_name,
    ts.row_count,
    ts.last_data_write,
    DATEDIFF('hour', ts.last_data_write, CURRENT_TIMESTAMP()) AS hours_since_update,
    CASE
        WHEN DATEDIFF('hour', ts.last_data_write, CURRENT_TIMESTAMP()) > 144 THEN 'STALE'
        WHEN er.min_expected IS NOT NULL AND ts.row_count < er.min_expected THEN 'LOW_COUNT'
        ELSE 'OK'
    END AS health_status
FROM table_stats ts
LEFT JOIN expected_ranges er ON ts.table_name = er.table_name;
```

### 12.5 Performance Trend Monitoring

Track ingestion duration and API calls over time:

```sql
CREATE OR REPLACE VIEW SNOWFLAKE_INTELLIGENCE.ADMIN.V_FRESHDESK_INGESTION_TRENDS AS
SELECT
    DATE_TRUNC('day', completed_at) AS run_date,
    status,
    records_ingested,
    duration_seconds,
    api_calls_made,
    details:errors::VARCHAR AS errors,
    CASE
        WHEN duration_seconds > 180 THEN 'SLOW'
        WHEN status = 'partial_failure' THEN 'DEGRADED'
        ELSE 'OK'
    END AS run_health
FROM SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
WHERE source_system = 'freshdesk'
ORDER BY completed_at DESC
LIMIT 30;
```

### 12.6 Operational Runbook

When an alert fires, follow this triage sequence:

1. **Check INGESTION_LOG**: `SELECT * FROM INGESTION_LOG WHERE source_system='freshdesk' ORDER BY completed_at DESC LIMIT 5`
2. **Check error details**: `SELECT details FROM INGESTION_LOG WHERE status='failed' ORDER BY completed_at DESC LIMIT 1`
3. **Verify API health**: Run `scripts/verify_freshdesk_endpoints.py` — confirms API key + endpoint availability
4. **Check rate limits**: Look at `details:rate_limit_remaining` in last successful log entry
5. **Check Task status**: `SHOW TASKS LIKE 'TASK_INGEST_FRESHDESK%' IN SCHEMA INGESTION` — is it suspended?
6. **Check warehouse**: `SHOW WAREHOUSES LIKE 'AI_WH'` — is it available?
7. **Manual re-run**: `CALL INGESTION.INGEST_FRESHDESK()` — test in isolation
8. **Escalation**: If API key invalid → rotate key (see Security section in Phase 1)

### Deliverables
- [ ] Failure alert created and enabled
- [ ] Staleness alert created (no successful run in 6 days)
- [ ] Health view uses actual `_loaded_at` with expected-count ranges
- [ ] Performance trend view tracks duration/API calls over time
- [ ] INGESTION_LOG extended with `details`, `duration_seconds`, `api_calls_made`
- [ ] Operational runbook documented with 8-step triage

---

## Phase 13: Evaluation & Regression

**Goal**: Expand eval dataset with Freshdesk-grounded questions.

### 13.1 New Eval Questions (10)

| Question | Expected Source | Doc Type |
|----------|----------------|----------|
| How do I distribute music on TikTok? | freshdesk | kb_article |
| What DSPs does Revelator support? | freshdesk | kb_article |
| Why is my music muted in a TikTok video? | freshdesk | kb_article |
| How do I link my YouTube MCN? | freshdesk | kb_article |
| How do I set up my Revelator Pro account? | freshdesk | kb_article |
| What happens to chart history when transferring distribution? | freshdesk | kb_article |
| Does Revelator process Mechanical Royalties? | freshdesk | kb_article |
| How do I pay payees with PayPal Payouts? | freshdesk | kb_article |
| What custom ticket fields are available? | freshdesk | field_metadata |
| How do I contact support about billing? | freshdesk | ticket_conversation |

### 13.2 Acceptance Criteria

- Freshdesk questions: ≥85% accuracy
- No regression on GitBook questions (delta < 5%)

### Deliverables
- [ ] Eval dataset expanded with 10 Freshdesk questions
- [ ] No regression on GitBook questions
- [ ] Freshdesk questions achieve ≥85% accuracy

---

## Phase 14: Discussion Forums Growth Monitoring

**Goal**: Set up monitoring for when community forums become active.

Currently: 1 discussion category, 0 forums, 0 topics.

### 14.1 Periodic Check

```python
# In INGEST_FRESHDESK():
forums = api_get(f"{base}/discussions/forums.json", auth)
topics = api_get(f"{base}/discussions/topics.json", auth)
if len(forums) > 0 or len(topics) > 0:
    log_info("Discussions now active! Forums: {len(forums)}, Topics: {len(topics)}")
```

When discussions become active, create:
- `FRESHDESK_DISCUSSION_FORUMS` table
- `FRESHDESK_DISCUSSION_TOPICS` table
- `FRESHDESK_DISCUSSION_POSTS` table
- Add topic/post content to PROCESS_DOCUMENTS pipeline

### Deliverables
- [ ] Growth check implemented in INGEST_FRESHDESK
- [ ] Forum/topic tables documented but not created until needed

---

## Phase 15: V2 API Migration Path (Future — Documentation Only)

If V2 becomes available on `helpdesk.revelator.com`:

1. Test: `GET https://helpdesk.revelator.com/api/v2/agents?per_page=1` — check for 200
2. V2 benefits: No root-key wrapping, `Link` header pagination, `updated_since` support, Roles endpoint, Canned Responses, Products, Business Hours, SLA Policies
3. V2 Solutions: `/api/v2/solutions/categories`, `/api/v2/solutions/folders/{id}/articles`
4. V2 Conversations: `/api/v2/tickets/{id}/conversations` (dedicated endpoint vs embedded)
5. Migration: Create `INGEST_FRESHDESK_V2()`, run in parallel with V1, compare counts, switch over

**V2 would unlock these currently unavailable endpoints:**
- Roles, Canned Responses (HIGH RAG value — pre-approved answer templates)
- Products, Business Hours, SLA Policies
- Satisfaction Ratings (global listing)
- Dedicated Conversations endpoint
- Account info

No action needed until V2 is confirmed available. Email to support@freshdesk.com drafted (see user communications).

---

## Phase 16: Data Quality, Security & Compliance Hardening

**Goal**: Address PII handling, data retention, timezone normalization, SQL injection risk,
access control, and deduplication. Based on staff-engineer deep review findings.

### 16.1 PII & Access Control — Contacts Table

`FRESHDESK_CONTACTS` contains PII: `email`, `phone`, `mobile`, `address`, `job_title`.
`FRESHDESK_TICKET_CONVERSATIONS` contains private internal notes.

**Column-level masking policy** for PII columns:

```sql
CREATE OR REPLACE MASKING POLICY SNOWFLAKE_INTELLIGENCE.ADMIN.MASK_PII_STRING AS
    (val STRING) RETURNS STRING ->
    CASE
        WHEN IS_ROLE_IN_SESSION('SYSADMIN') OR IS_ROLE_IN_SESSION('SI_INGESTION_ROLE') THEN val
        ELSE '***MASKED***'
    END;

ALTER TABLE RAW.FRESHDESK_CONTACTS MODIFY COLUMN email
    SET MASKING POLICY SNOWFLAKE_INTELLIGENCE.ADMIN.MASK_PII_STRING;
ALTER TABLE RAW.FRESHDESK_CONTACTS MODIFY COLUMN phone
    SET MASKING POLICY SNOWFLAKE_INTELLIGENCE.ADMIN.MASK_PII_STRING;
ALTER TABLE RAW.FRESHDESK_CONTACTS MODIFY COLUMN mobile
    SET MASKING POLICY SNOWFLAKE_INTELLIGENCE.ADMIN.MASK_PII_STRING;
```

**Row-access policy** for private notes:

```sql
CREATE OR REPLACE ROW ACCESS POLICY SNOWFLAKE_INTELLIGENCE.ADMIN.RAP_PRIVATE_NOTES AS
    (private BOOLEAN) RETURNS BOOLEAN ->
    CASE
        WHEN private = FALSE THEN TRUE
        WHEN IS_ROLE_IN_SESSION('SYSADMIN') OR IS_ROLE_IN_SESSION('SI_INGESTION_ROLE') THEN TRUE
        ELSE FALSE
    END;

ALTER TABLE RAW.FRESHDESK_TICKET_CONVERSATIONS ADD ROW ACCESS POLICY
    SNOWFLAKE_INTELLIGENCE.ADMIN.RAP_PRIVATE_NOTES ON (private);
```

### 16.2 Timezone Normalization

Freshdesk V1 returns timestamps with timezone offsets (e.g., `2026-03-16T18:12:34+02:00`),
but all table columns are `TIMESTAMP_NTZ`. Explicitly convert to UTC in ingestion:

```python
from datetime import datetime, timezone

def normalize_ts(ts_str):
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return ts_str

# Apply to all timestamp fields before writing:
for record in records:
    for ts_field in ['created_at', 'updated_at', 'modified_at']:
        if ts_field in record:
            record[ts_field] = normalize_ts(record[ts_field])
```

Document: **All timestamps in RAW tables are UTC** (converted during ingestion).

### 16.3 SQL Injection Prevention

The existing `process_documents.sql` uses f-string SQL with content interpolation.
A maliciously crafted article title or body could break the INSERT.

**Fix**: Use parameterized writes via `create_dataframe` instead of string interpolation:

```python
# INSTEAD OF:
session.sql(f"""
    INSERT INTO CURATED.DOCUMENTS (document_id, title, content, ...)
    SELECT '{doc_id}', '{safe(title)}', '{safe(content[:100000])}', ...
""").collect()

# USE:
doc_rows = []
for row in fd_articles:
    doc_rows.append({
        "document_id": doc_id,
        "title": title,
        "content": content[:100000],
        # ... other columns
    })

# Batch write — no SQL interpolation, no injection risk
if doc_rows:
    session.create_dataframe(doc_rows).write.mode("append").save_as_table(
        "SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS"
    )
```

This also fixes the O(n) INSERT performance issue (Phase 7.3 from Codex review) — batch
writes are ~100x faster than individual INSERT statements.

### 16.4 Deduplication Guard

Pagination race conditions can produce duplicates (record updated mid-pagination appears
on two pages). Add a dedup step before writing:

```python
def dedup_records(records, pk_field):
    seen = {}
    for r in records:
        pk = r.get(pk_field)
        if pk is not None:
            existing = seen.get(pk)
            if existing is None or (r.get('updated_at', '') > existing.get('updated_at', '')):
                seen[pk] = r
        else:
            seen[id(r)] = r  # no PK, keep all
    return list(seen.values())

# Usage:
agents = dedup_records(all_agents, "id")
tickets = dedup_records(all_tickets, "id")
articles = dedup_records(all_articles, "id")
```

### 16.5 HTML Sanitization Hardening

Freshdesk article HTML could contain XSS vectors. Extend `clean_html()` beyond `<script>` stripping:

```python
def sanitize_html(html):
    html = re.sub(r'<(script|iframe|object|embed|applet)[^>]*>[\s\S]*?</\1>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'\bon\w+\s*=\s*["\'][^"\']*["\']', '', html)  # onerror, onclick, etc.
    html = re.sub(r'javascript\s*:', '', html, flags=re.IGNORECASE)
    html = re.sub(r'vbscript\s*:', '', html, flags=re.IGNORECASE)
    return html

# Call before clean_html() in PROCESS_DOCUMENTS:
content = sanitize_html(raw_html)
content = clean_html(content)
```

### 16.6 Data Retention Policy

Customer data (contacts) should not be retained indefinitely. Add a retention mechanism:

```sql
-- Retention metadata column
ALTER TABLE RAW.FRESHDESK_CONTACTS ADD COLUMN IF NOT EXISTS
    _retention_expires_at TIMESTAMP_NTZ DEFAULT DATEADD('day', 730, CURRENT_TIMESTAMP());

-- Cleanup task (runs monthly)
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.INGESTION.TASK_DATA_RETENTION
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 4 1 * * America/Los_Angeles'
AS
BEGIN
    DELETE FROM RAW.FRESHDESK_CONTACTS
    WHERE _retention_expires_at < CURRENT_TIMESTAMP();
END;
```

**GDPR deletion request process**:
1. Receive request with customer email
2. `DELETE FROM RAW.FRESHDESK_CONTACTS WHERE email = '<email>'`
3. `DELETE FROM RAW.FRESHDESK_TICKET_CONVERSATIONS WHERE user_id IN (SELECT contact_id FROM ... WHERE email = '<email>')`
4. Re-run PROCESS_DOCUMENTS to remove from CURATED layer
5. Log deletion in INGESTION_LOG with `ingestion_type='gdpr_deletion'`

### 16.7 API Key Rotation Runbook

1. Generate new API key in Freshdesk Admin → Profile Settings
2. `ALTER SECRET SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET SET SECRET_STRING = '<new_key>'`
3. Run `scripts/verify_freshdesk_endpoints.py` to confirm connectivity
4. Revoke old key in Freshdesk Admin
5. Log rotation in SYSTEM_CONFIG: `INSERT INTO ADMIN.SYSTEM_CONFIG (key, value) VALUES ('freshdesk_api_key_rotated_at', CURRENT_TIMESTAMP()::VARCHAR)`
6. **Schedule**: Rotate quarterly (add calendar reminder)

### Deliverables
- [ ] PII masking policy applied to FRESHDESK_CONTACTS (email, phone, mobile)
- [ ] Row-access policy on private ticket conversations
- [ ] All timestamps normalized to UTC during ingestion
- [ ] PROCESS_DOCUMENTS uses `create_dataframe` batch writes (no SQL interpolation)
- [ ] Deduplication guard on all paginated fetches
- [ ] HTML sanitization strips XSS vectors (javascript:, on* handlers, iframe/object/embed)
- [ ] Data retention policy with 730-day default and GDPR deletion process
- [ ] API key rotation runbook documented

---

## Implementation Order & Dependencies

```
Phase 0:  Pre-Flight Validation           ✅ COMPLETED
Phase 1:  Foundation (Secrets, EAI)
Phase 2:  RAW Tables DDL (13 tables)      ← parallel with Phase 1
Phase 3:  INGEST_FRESHDESK()              ← depends on 1, 2 (9 entities + resilience + error isolation)
Phase 4:  INGEST_FRESHDESK_SOLUTIONS()    ← depends on 1, 2 (3 solution tables)
Phase 5:  PROCESS_DOCUMENTS update        ← depends on 3, 4 (batch writes, source-scoped deletes)
Phase 6:  CLASSIFY_DOCUMENTS validation   ← depends on 5
Phase 7:  Incremental + Write Atomicity   ← with 3/4 (watermark, atomic writes, growth warnings)
Phase 8:  Task Scheduling                 ← depends on 3, 4, 5 (parallel DAG, safe FULL_REFRESH)
Phase 9:  Cortex Search validation        ← depends on 5
Phase 10: Agent Prompt update             ← depends on 9
Phase 10.5: Agent Expertise Model         ← depends on 3, 4, 5 (needs RAW data + CURATED views)
Phase 11: Testing (unit + integration)    ← depends on all above
Phase 12: Monitoring + Alerting           ← depends on 3, 4 (staleness + trends)
Phase 13: Evaluation                      ← depends on 10, 11
Phase 14: Discussion Growth Monitoring    ← with Phase 3
Phase 15: V2 Migration Path              ← documentation only
Phase 16: Security & Compliance           ← depends on 2, 3, 5 (PII masking, GDPR, sanitization)
```

### Estimated Effort

| Phase | Effort | Risk |
|-------|--------|------|
| 0: Pre-Flight | ✅ Done | — |
| 1: Foundation | 1 hour | Low |
| 2: RAW Tables (13) | 1.5 hours | Low |
| 3: Operational Ingestion (10 entities + resilience) | 6 hours | Low — V1 shapes verified, added error isolation + rate-limit handling |
| 4: Solutions Ingestion | 3 hours | Low — hierarchy traversal verified |
| 5: Process Documents (batch writes + source-scoped) | 6 hours | Medium — HTML cleaning + batch write refactor + privacy filtering |
| 6: Classification | 1 hour | Low |
| 7: Incremental + Atomicity | 1.5 hours | Low — watermark + growth warnings + staging-swap docs |
| 8: Task Scheduling (parallel DAG) | 2 hours | Medium — multi-predecessor + safe FULL_REFRESH + overlap prevention |
| 9: Cortex Search | 1 hour | Low — auto-indexes |
| 10: Agent Prompt | 1.5 hours | Low |
| 10.5: Agent Expertise Model | 4 hours | Medium — 9-signal scoring model, 3 views, Streamlit page, prompt integration |
| 11: Testing (unit + integration + quality) | 6 hours | Medium — unit tests, referential integrity, automated E2E evals |
| 12: Monitoring (staleness + trends + runbook) | 3 hours | Low — staleness alert, health view, performance trends, runbook |
| 13: Evaluation | 3 hours | Medium |
| 14: Discussion Monitoring | 0.5 hours | Low |
| 15: V2 Migration | 0.5 hours | Low — docs only |
| 16: Security & Compliance | 3 hours | Medium — PII masking, GDPR, sanitization, tz normalization, key rotation |
| **Total** | **~45 hours** | |

### Total API Calls per Full Refresh

```
Agents (active):           1 call
Agents (deleted):          1 call
Companies:                 1 call
Contacts (all):            1 call
Contacts (deleted):        1 call  ← NEW: ensures deleted contacts for expertise model
Groups:                    1 call
Tickets (list):            1 call
Tickets (30 details):     30 calls
Ticket fields:             1 call
Contact fields:            1 call
Company fields:            1 call
Discussion categories:     1 call
Solution categories:       1 call
Solution folders (39):    39 calls
────────────────────────────────
TOTAL:                    ~82 API calls
Rate limit:             5,000/minute
Budget usage:             1.6%
Wall time (0.3s sleep):   ~25 seconds
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| V1 API deprecated | Low | High | `raw_json` preserves all data; V2 path documented (Phase 15); email sent to Freshdesk support |
| Rate limiting | Very Low | Low | 5,000/min limit vs ~82 calls needed; `api_get()` respects `Retry-After` + preemptive slowdown (§3.9) |
| Freshdesk HTML edge cases / XSS | Medium | Medium | `sanitize_html()` strips XSS vectors (§16.5); `clean_html()` handles display; `desc_un_html` as fallback |
| API key expired/revoked | Low | High | `verify_freshdesk_all_endpoints.py` pre-validates; alert on ingestion failure; rotation runbook (§16.7) |
| Ticket volume growth | Low | Low | Currently 30; `updated_since` watermark wired (§7.2); growth warning at 1,000 (§7.3); incremental at 5,000 |
| Empty conversations on most tickets | Medium | Low | Conversation extraction is additive; skip empty gracefully |
| Folder detail 404 (empty folders) | Low | Low | `api_get()` returns None for 404 (§3.9); skip folders with 0 articles; log warning |
| Discussion forums become active | Low | Medium | Growth monitoring in Phase 14; tables ready to create |
| Private notes leaking to RAG | Medium | High | Filter `private=true` in PROCESS_DOCUMENTS; row-access policy (§16.1); only public conversations to CURATED |
| Canned responses become available (V2) | Low | Medium | Would be HIGH RAG value; re-test V2 periodically |
| Articles contain PII from tickets | Very Low | High | Solutions KB is curated content; filter to published only |
| Custom domain DNS/TLS change | Low | High | `helpdesk.revelator.com` SSL cert change could break network rule; health check in monitoring view |
| Freshdesk plan downgrade | Low | Medium | Rate limit drops from 5,000 to 200-1,000/min; still fine for 82 calls; `X-RateLimit-Remaining` tracked (§3.9) |
| **Network/timeout errors** | Low | Medium | `ConnectionError` + `Timeout` retried with backoff (§3.9); auth failures (401/403) fail fast |
| **Single entity crashes entire run** | Medium | High | Per-entity try/except isolation (§3.10); partial_failure status; >20% threshold for ticket details |
| **CURATED blanket delete on failure** | High | Critical | Source-scoped deletes (§7.5); Freshdesk failure leaves GitBook intact and vice versa |
| **GitBook failure blocks Freshdesk** | Medium | High | Parallel root tasks (§8.1); multi-predecessor PROCESS_DOCUMENTS; independent schedules |
| **FULL_REFRESH truncates before ingest** | Low | Critical | Ingest-first pattern (§8.3); CURATED rebuilt only after successful RAW ingestion |
| **Ingestion silently stops** | Low | High | Staleness alert (§12.3) fires if no successful run in 6 days |
| **PII exposure in RAW tables** | Medium | High | Column masking on contacts PII (§16.1); row-access on private notes; RAW restricted to ingestion role |
| **SQL injection via content** | Low | High | Batch `create_dataframe` writes replace f-string interpolation (§16.3) |
| **Timezone inconsistency** | Medium | Low | All timestamps normalized to UTC during ingestion (§16.2) |
| **Duplicate records from pagination** | Low | Low | `dedup_records()` guard before writing (§16.4) |
| **Deleted contacts missing for expertise model** | Medium | Medium | Contacts fetched with `state=all` + `state=deleted` merge (§3.11) |
| **GDPR deletion request** | Low | Medium | Documented process: delete from RAW + re-process CURATED (§16.6) |

---

## Appendix A: Complete V1 Root Key Mapping

| Entity | Endpoint | Root Key | Wrapping Pattern |
|--------|----------|----------|------------------|
| Agents | `/agents.json` | `agent` | `[{"agent": {...}}, ...]` |
| Companies | `/companies.json` | `company` | `[{"company": {...}}, ...]` |
| Contacts | `/contacts.json` | `user` | `[{"user": {...}}, ...]` |
| Groups | `/groups.json` | `group` | `[{"group": {...}}, ...]` |
| Tickets (list) | `/helpdesk/tickets.json` | **none** | `[{id, subject, ...}, ...]` (flat) |
| Ticket (detail) | `/helpdesk/tickets/{id}.json` | `helpdesk_ticket` | `{"helpdesk_ticket": {..., "notes": [...]}}` |
| Ticket Fields | `/ticket_fields.json` | `ticket_field` | `[{"ticket_field": {...}}, ...]` |
| Contact Fields | `/admin/contact_fields.json` | `contact_field` | `[{"contact_field": {...}}, ...]` |
| Company Fields | `/admin/company_fields.json` | `company_field` | `[{"company_field": {...}}, ...]` |
| Solution Categories | `/solution/categories.json` | `category` | `[{"category": {..., "folders": [...]}}, ...]` |
| Solution Folder Detail | `/solution/folders/{id}.json` | `folder` | `{"folder": {..., "articles": [...]}}` |
| Discussion Categories | `/discussions/categories.json` | `forum_category` | `[{"forum_category": {...}}, ...]` |

## Appendix B: Unavailable Endpoints (Confirmed 404 on V1)

Roles, Canned Responses, Products, Business Hours, SLA Policies, Email Configs, Automations, Satisfaction Ratings (global), Ticket Conversations (separate endpoint — use embedded notes), Solution Folders (separate listing — use embedded in category), ALL V2 endpoints.
