# Research: Security, Governance & Operations
## Agent 9 Output — Comprehensive Findings

---

## Credential Management: .env → Snowflake Secrets

### The Problem
The `.env` file contains plaintext API keys:
```
GITBOOK_API=gb_api_eRsEQjJveQ3dQh4yD1fBZlOfMip277BJ9bgnTPlf
FRESHDESK_API=eduJofkrPjd7sDyTt1AK
```

### The Solution: Snowflake Secrets

```sql
-- Generic string secret for API keys
CREATE OR REPLACE SECRET REVSEARCH.INGESTION.FRESHDESK_API_SECRET
    TYPE = GENERIC_STRING
    SECRET_STRING = 'eduJofkrPjd7sDyTt1AK';

CREATE OR REPLACE SECRET REVSEARCH.INGESTION.GITBOOK_API_SECRET
    TYPE = GENERIC_STRING
    SECRET_STRING = 'gb_api_eRsEQjJveQ3dQh4yD1fBZlOfMip277BJ9bgnTPlf';
```

### Accessing Secrets in Stored Procedures

```python
import _snowflake

def run(session):
    api_key = _snowflake.get_generic_secret_string('api_key')
    # Use api_key in API calls
```

### Security Properties
- Secrets are encrypted at rest
- Access controlled via RBAC (GRANT USAGE ON SECRET)
- Secret values never appear in query history or logs
- Auditable via ACCESS_HISTORY views

---

## External Access Integration

### Full Setup Pattern

```sql
-- Step 1: Network Rule (allow outbound traffic)
CREATE OR REPLACE NETWORK RULE REVSEARCH.INGESTION.FRESHDESK_RULE
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = ('helpdesk.revelator.com:443');

-- Step 2: External Access Integration (bind network + secrets)
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION REVSEARCH_FRESHDESK_EAI
    ALLOWED_NETWORK_RULES = (REVSEARCH.INGESTION.FRESHDESK_RULE)
    ALLOWED_AUTHENTICATION_SECRETS = (REVSEARCH.INGESTION.FRESHDESK_API_SECRET)
    ENABLED = TRUE;

-- Step 3: Use in stored procedure
CREATE OR REPLACE PROCEDURE REVSEARCH.INGESTION.INGEST_FRESHDESK()
    RETURNS STRING
    LANGUAGE PYTHON
    RUNTIME_VERSION = '3.11'
    PACKAGES = ('snowflake-snowpark-python', 'requests')
    HANDLER = 'run'
    EXTERNAL_ACCESS_INTEGRATIONS = (REVSEARCH_FRESHDESK_EAI)
    SECRETS = ('api_key' = REVSEARCH.INGESTION.FRESHDESK_API_SECRET)
AS $$
import requests
import _snowflake

def run(session):
    key = _snowflake.get_generic_secret_string('api_key')
    resp = requests.get(
        'https://helpdesk.revelator.com/api/v2/solutions/categories',
        auth=(key, 'X')
    )
    return str(resp.status_code)
$$;
```

---

## Role-Based Access Control

### Role Design

```sql
-- Application roles
CREATE ROLE IF NOT EXISTS REVSEARCH_ADMIN;
CREATE ROLE IF NOT EXISTS REVSEARCH_USER;
CREATE ROLE IF NOT EXISTS REVSEARCH_SERVICE;

-- Hierarchy
GRANT ROLE REVSEARCH_USER TO ROLE REVSEARCH_ADMIN;
GRANT ROLE REVSEARCH_SERVICE TO ROLE REVSEARCH_ADMIN;
GRANT ROLE REVSEARCH_ADMIN TO ROLE SYSADMIN;

-- Database level
GRANT USAGE ON DATABASE REVSEARCH TO ROLE REVSEARCH_USER;
GRANT USAGE ON DATABASE REVSEARCH TO ROLE REVSEARCH_SERVICE;

-- Schema-level permissions (USER)
GRANT USAGE ON SCHEMA REVSEARCH.CURATED TO ROLE REVSEARCH_USER;
GRANT USAGE ON SCHEMA REVSEARCH.SEARCH TO ROLE REVSEARCH_USER;
GRANT USAGE ON SCHEMA REVSEARCH.ANALYTICS TO ROLE REVSEARCH_USER;
GRANT USAGE ON SCHEMA REVSEARCH.ADMIN TO ROLE REVSEARCH_USER;

GRANT SELECT ON ALL TABLES IN SCHEMA REVSEARCH.CURATED TO ROLE REVSEARCH_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA REVSEARCH.ANALYTICS TO ROLE REVSEARCH_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA REVSEARCH.ADMIN TO ROLE REVSEARCH_USER;

-- Users can submit questions and feedback
GRANT INSERT ON TABLE REVSEARCH.ANALYTICS.QUESTIONS TO ROLE REVSEARCH_USER;
GRANT INSERT ON TABLE REVSEARCH.ANALYTICS.FEEDBACK TO ROLE REVSEARCH_USER;

-- Schema-level permissions (ADMIN)
GRANT ALL ON ALL SCHEMAS IN DATABASE REVSEARCH TO ROLE REVSEARCH_ADMIN;
GRANT ALL ON ALL TABLES IN DATABASE REVSEARCH TO ROLE REVSEARCH_ADMIN;

-- Schema-level permissions (SERVICE)
GRANT ALL ON SCHEMA REVSEARCH.RAW TO ROLE REVSEARCH_SERVICE;
GRANT ALL ON SCHEMA REVSEARCH.CURATED TO ROLE REVSEARCH_SERVICE;
GRANT ALL ON SCHEMA REVSEARCH.INGESTION TO ROLE REVSEARCH_SERVICE;
```

---

## Row Access Policy (Document-Level Security)

```sql
-- For future: restrict document access by team
CREATE OR REPLACE ROW ACCESS POLICY REVSEARCH.ADMIN.DOCUMENT_ACCESS
AS (team VARCHAR) RETURNS BOOLEAN ->
    CURRENT_ROLE() = 'REVSEARCH_ADMIN'
    OR team IS NULL  -- public documents
    OR team IN (
        SELECT team_name FROM REVSEARCH.ADMIN.USER_TEAM_MAPPING
        WHERE user_name = CURRENT_USER()
    );

-- Apply to documents table
ALTER TABLE REVSEARCH.CURATED.DOCUMENTS
    ADD ROW ACCESS POLICY REVSEARCH.ADMIN.DOCUMENT_ACCESS ON (team);
```

---

## Monitoring & Alerting

### Task Failure Alert

```sql
CREATE OR REPLACE NOTIFICATION INTEGRATION REVSEARCH_EMAIL
    TYPE = EMAIL
    ENABLED = TRUE
    ALLOWED_RECIPIENTS = ('admin@revelator.com');

CREATE OR REPLACE ALERT REVSEARCH.INGESTION.TASK_FAILURE_ALERT
    WAREHOUSE = REVSEARCH_SEARCH_WH
    SCHEDULE = '30 MINUTE'
    IF (EXISTS (
        SELECT 1
        FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
            SCHEDULED_TIME_RANGE_START => DATEADD('hour', -1, CURRENT_TIMESTAMP())
        ))
        WHERE state = 'FAILED'
          AND DATABASE_NAME = 'REVSEARCH'
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'REVSEARCH_EMAIL',
            'admin@revelator.com',
            'RevSearch Alert: Ingestion Task Failed',
            'Check TASK_HISTORY for details.'
        );

ALTER ALERT REVSEARCH.INGESTION.TASK_FAILURE_ALERT RESUME;
```

### Knowledge Gap Alert

```sql
CREATE OR REPLACE ALERT REVSEARCH.ANALYTICS.KNOWLEDGE_GAP_ALERT
    WAREHOUSE = REVSEARCH_SEARCH_WH
    SCHEDULE = 'USING CRON 0 9 * * 1 America/Los_Angeles'  -- Monday 9 AM
    IF (EXISTS (
        SELECT 1
        FROM REVSEARCH.ANALYTICS.QUESTIONS
        WHERE answer_strength IN ('weak', 'no_answer')
          AND date_asked >= DATEADD('day', -7, CURRENT_TIMESTAMP())
        GROUP BY question_text
        HAVING COUNT(*) >= 3
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'REVSEARCH_EMAIL',
            'admin@revelator.com',
            'RevSearch: Knowledge Gaps This Week',
            'Multiple questions had weak/no answers. Review FAQ Dashboard.'
        );
```

### Cortex Credit Monitoring

```sql
-- Monitor AI credit usage
SELECT 
    DATE_TRUNC('day', start_time) AS usage_date,
    service_type,
    SUM(credits_used) AS total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY
WHERE service_type LIKE '%CORTEX%'
  AND start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY 1 DESC;
```

---

## Audit Logging

### Track All Queries to the Search Service

```sql
-- All questions are already logged to ANALYTICS.QUESTIONS table
-- Additionally, monitor access history:
SELECT 
    query_start_time,
    user_name,
    direct_objects_accessed,
    base_objects_accessed
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
WHERE ARRAY_CONTAINS('REVSEARCH'::VARIANT, 
    TRANSFORM(base_objects_accessed, obj -> obj:objectDomain::VARCHAR))
ORDER BY query_start_time DESC
LIMIT 100;
```

---

## Performance Optimization

### Warehouse Sizing

| Warehouse | Size | Purpose | Auto-Suspend |
|-----------|------|---------|--------------|
| REVSEARCH_INGESTION_WH | SMALL | API calls + data processing | 120s |
| REVSEARCH_SEARCH_WH | SMALL | Cortex Search + Agent queries | 60s |
| REVSEARCH_APP_WH | XSMALL | Streamlit app queries | 60s |

### Caching Strategies

```sql
-- Result cache: Snowflake automatically caches identical queries for 24 hours
-- For Streamlit, use @st.cache_data with TTL:
```

```python
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_faq_summary():
    return session.sql("SELECT * FROM REVSEARCH.ANALYTICS.FAQ_SUMMARY").to_pandas()
```

### Answer Caching (Future Enhancement)

```sql
-- Cache frequent question answers
CREATE OR REPLACE TABLE REVSEARCH.ANALYTICS.ANSWER_CACHE (
    question_hash VARCHAR(64) PRIMARY KEY,
    question_text VARCHAR(5000),
    cached_answer VARCHAR,
    answer_strength VARCHAR(20),
    sources VARIANT,
    cached_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    hit_count NUMBER DEFAULT 0,
    ttl_hours NUMBER DEFAULT 24
);

-- Check cache before calling agent
SELECT cached_answer, answer_strength, sources
FROM REVSEARCH.ANALYTICS.ANSWER_CACHE
WHERE question_hash = SHA2(LOWER(TRIM(:question)))
  AND cached_at > DATEADD('hour', -ttl_hours, CURRENT_TIMESTAMP());
```

---

## Document Lifecycle Management

### Status Flow
```
draft → active → archived
         │
         └── stale (>90 days without update → alert owner)
```

### Staleness Detection

```sql
CREATE OR REPLACE ALERT REVSEARCH.ADMIN.DOCUMENT_STALENESS_ALERT
    WAREHOUSE = REVSEARCH_SEARCH_WH
    SCHEDULE = 'USING CRON 0 10 1 * * America/Los_Angeles'  -- 1st of each month
    IF (EXISTS (
        SELECT 1
        FROM REVSEARCH.CURATED.DOCUMENTS
        WHERE status = 'active'
          AND last_updated < DATEADD('day', -90, CURRENT_TIMESTAMP())
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'REVSEARCH_EMAIL',
            'admin@revelator.com',
            'RevSearch: Stale Documents Detected',
            'Some active documents haven not been updated in 90+ days.'
        );
```

---

## Data Classification

```sql
-- Auto-tag sensitive documents
UPDATE REVSEARCH.CURATED.DOCUMENTS
SET metadata = OBJECT_INSERT(
    COALESCE(metadata, OBJECT_CONSTRUCT()),
    'sensitivity',
    CASE
        WHEN content ILIKE '%salary%' OR content ILIKE '%compensation%' THEN 'confidential'
        WHEN content ILIKE '%internal only%' THEN 'internal'
        ELSE 'public'
    END
)
WHERE metadata:sensitivity IS NULL;
```
