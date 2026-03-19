# Research: Snowflake Data Architecture
## Agent 6 Output — Comprehensive Findings

---

## Database & Schema Design

### Recommended Layout

```
REVSEARCH (Database)
├── RAW          — Staging tables from external APIs
├── CURATED      — Processed documents & chunks (source of truth)
├── SEARCH       — Cortex Search Service
├── AGENTS       — Cortex Agent definitions
├── ANALYTICS    — Questions, feedback, dynamic tables
├── ADMIN        — Knowledge owners, config, permissions
├── INGESTION    — Stored procedures, tasks, secrets
└── APP          — Streamlit application stage
```

### Why This Layout?
- **Separation of concerns**: Raw data separate from processed data
- **Security boundaries**: Different roles can access different schemas
- **Lifecycle management**: Raw data can be purged independently
- **Governance**: Tags and policies applied at schema level

---

## Dynamic Tables

### What Are Dynamic Tables?
Dynamic Tables are Snowflake's declarative data pipeline mechanism. Define the desired output as a SQL query, and Snowflake automatically keeps it fresh.

### Syntax

```sql
CREATE [ OR REPLACE ] DYNAMIC TABLE <name>
    TARGET_LAG = '<time>'
    WAREHOUSE = <warehouse>
AS
    <SELECT query>;
```

### TARGET_LAG Options
| Setting | Behavior | Use Case |
|---------|----------|----------|
| `'1 minute'` | Near-real-time refresh | Critical dashboards |
| `'1 hour'` | Hourly refresh | FAQ analytics (recommended) |
| `'1 day'` | Daily refresh | Historical reports |
| `DOWNSTREAM` | Refreshes only when downstream depends on it | Chained pipelines |

### Refresh Modes
- **Incremental**: Only processes changed rows (much faster, less compute)
- **Full**: Recomputes entire table
- Snowflake automatically chooses the best mode based on the query

### RevSearch Dynamic Tables

```sql
-- FAQ Summary: Group similar questions by frequency
CREATE OR REPLACE DYNAMIC TABLE REVSEARCH.ANALYTICS.FAQ_SUMMARY
    TARGET_LAG = '1 hour'
    WAREHOUSE = REVSEARCH_SEARCH_WH
AS
SELECT
    question_text,
    COUNT(*) AS ask_count,
    MODE(answer_strength) AS typical_strength,
    MIN(date_asked) AS first_asked,
    MAX(date_asked) AS last_asked,
    ROUND(AVG(response_latency_ms), 0) AS avg_latency_ms,
    ARRAY_AGG(DISTINCT user_team) AS teams_asking,
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS weak_count
FROM REVSEARCH.ANALYTICS.QUESTIONS
GROUP BY question_text;

-- Team Summary: Per-team analytics
CREATE OR REPLACE DYNAMIC TABLE REVSEARCH.ANALYTICS.TEAM_SUMMARY
    TARGET_LAG = '1 hour'
    WAREHOUSE = REVSEARCH_SEARCH_WH
AS
SELECT
    COALESCE(user_team, 'Unknown') AS team,
    COUNT(*) AS total_questions,
    COUNT_IF(answer_strength = 'strong') AS strong_answers,
    COUNT_IF(answer_strength = 'medium') AS medium_answers,
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS weak_or_none,
    ROUND(COUNT_IF(answer_strength = 'strong') * 100.0 / NULLIF(COUNT(*), 0), 1) AS strong_pct
FROM REVSEARCH.ANALYTICS.QUESTIONS
GROUP BY COALESCE(user_team, 'Unknown');

-- Knowledge Gaps: Topics needing documentation
CREATE OR REPLACE DYNAMIC TABLE REVSEARCH.ANALYTICS.KNOWLEDGE_GAPS
    TARGET_LAG = '1 hour'
    WAREHOUSE = REVSEARCH_SEARCH_WH
AS
SELECT
    question_text,
    answer_strength,
    COUNT(*) AS times_asked,
    MAX(date_asked) AS last_asked,
    ARRAY_AGG(DISTINCT user_team) AS teams_affected
FROM REVSEARCH.ANALYTICS.QUESTIONS
WHERE answer_strength IN ('weak', 'no_answer')
GROUP BY question_text, answer_strength
HAVING COUNT(*) >= 2;

-- Daily Trends
CREATE OR REPLACE DYNAMIC TABLE REVSEARCH.ANALYTICS.DAILY_TRENDS
    TARGET_LAG = '1 hour'
    WAREHOUSE = REVSEARCH_SEARCH_WH
AS
SELECT
    DATE_TRUNC('day', date_asked) AS ask_date,
    COUNT(*) AS questions,
    COUNT_IF(answer_strength = 'strong') AS strong,
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS weak_or_none,
    AVG(response_latency_ms) AS avg_latency_ms
FROM REVSEARCH.ANALYTICS.QUESTIONS
GROUP BY DATE_TRUNC('day', date_asked);
```

---

## Snowflake Tasks

### Task Tree for Ingestion

```
TASK_INGEST_ALL (root, scheduled CRON)
  └── TASK_INGEST_GITBOOK (AFTER root)
       └── TASK_INGEST_NOTION (AFTER gitbook)
            └── TASK_PROCESS_DOCUMENTS (AFTER notion)
                 └── TASK_CLASSIFY_DOCUMENTS (AFTER process)
```

### Task Scheduling Syntax

```sql
-- Cron-based scheduling
SCHEDULE = 'USING CRON 0 */6 * * * America/Los_Angeles'
-- Meaning: Every 6 hours at minute 0

-- Weekly full refresh (Sundays at 2 AM)
SCHEDULE = 'USING CRON 0 2 * * 0 America/Los_Angeles'

-- Every 30 minutes
SCHEDULE = '30 MINUTE'
```

### Task Monitoring

```sql
-- Check last 10 task runs
SELECT name, state, scheduled_time, completed_time, 
       DATEDIFF('second', scheduled_time, completed_time) AS duration_seconds,
       error_code, error_message
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    TASK_NAME => 'TASK_INGEST_ALL',
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
))
ORDER BY scheduled_time DESC
LIMIT 10;
```

### Task Error Alerting

```sql
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
            'revsearch_notifications',
            'admin@revelator.com',
            'RevSearch: Ingestion Task Failed',
            'One or more ingestion tasks failed in the last hour. Check TASK_HISTORY.'
        );
```

---

## Streams (Change Data Capture)

### Use Case: Track new documents for real-time indexing

```sql
CREATE OR REPLACE STREAM REVSEARCH.CURATED.DOCUMENT_CHUNKS_STREAM
    ON TABLE REVSEARCH.CURATED.DOCUMENT_CHUNKS
    SHOW_INITIAL_ROWS = FALSE
    APPEND_ONLY = TRUE;

-- Task to process new chunks (e.g., update stats)
CREATE OR REPLACE TASK REVSEARCH.ANALYTICS.PROCESS_NEW_CHUNKS
    WAREHOUSE = REVSEARCH_SEARCH_WH
    SCHEDULE = '5 MINUTE'
    WHEN SYSTEM$STREAM_HAS_DATA('REVSEARCH.CURATED.DOCUMENT_CHUNKS_STREAM')
AS
    INSERT INTO REVSEARCH.ANALYTICS.INGESTION_LOG
    SELECT source_system, COUNT(*) AS new_chunks, CURRENT_TIMESTAMP() AS processed_at
    FROM REVSEARCH.CURATED.DOCUMENT_CHUNKS_STREAM
    GROUP BY source_system;
```

---

## Snowflake Alerts

### Alert Syntax

```sql
CREATE [ OR REPLACE ] ALERT <name>
    WAREHOUSE = <warehouse>
    SCHEDULE = '<schedule>'
    IF ( EXISTS ( <condition_query> ) )
    THEN
        <action>;
```

### Notification Integration Setup

```sql
-- Create email notification integration
CREATE OR REPLACE NOTIFICATION INTEGRATION REVSEARCH_EMAIL_NOTIFICATIONS
    TYPE = EMAIL
    ENABLED = TRUE
    ALLOWED_RECIPIENTS = ('admin@revelator.com', 'milan@revelator.com');

-- Use in alert
CALL SYSTEM$SEND_EMAIL(
    'REVSEARCH_EMAIL_NOTIFICATIONS',
    'admin@revelator.com',
    'Subject line',
    'Message body'
);
```

---

## Tags for Governance

```sql
-- Create tags for document classification
CREATE OR REPLACE TAG REVSEARCH.ADMIN.DOCUMENT_SENSITIVITY
    ALLOWED_VALUES = 'public', 'internal', 'confidential';

CREATE OR REPLACE TAG REVSEARCH.ADMIN.DATA_DOMAIN
    ALLOWED_VALUES = 'product', 'support', 'billing', 'operations', 'legal';

-- Apply to tables
ALTER TABLE REVSEARCH.CURATED.DOCUMENTS SET TAG 
    REVSEARCH.ADMIN.DATA_DOMAIN = 'product';
```

---

## Role Hierarchy Design

```sql
-- Role hierarchy
SYSADMIN
└── REVSEARCH_ADMIN
    ├── REVSEARCH_USER
    ├── REVSEARCH_INGESTION (service account)
    └── REVSEARCH_AGENT (service account)

-- Permissions
GRANT SELECT ON ALL TABLES IN SCHEMA REVSEARCH.CURATED TO ROLE REVSEARCH_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA REVSEARCH.ANALYTICS TO ROLE REVSEARCH_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA REVSEARCH.ADMIN TO ROLE REVSEARCH_USER;

GRANT ALL ON SCHEMA REVSEARCH.RAW TO ROLE REVSEARCH_INGESTION;
GRANT ALL ON SCHEMA REVSEARCH.CURATED TO ROLE REVSEARCH_INGESTION;
GRANT ALL ON SCHEMA REVSEARCH.INGESTION TO ROLE REVSEARCH_INGESTION;

GRANT INSERT ON TABLE REVSEARCH.ANALYTICS.QUESTIONS TO ROLE REVSEARCH_USER;
GRANT INSERT ON TABLE REVSEARCH.ANALYTICS.FEEDBACK TO ROLE REVSEARCH_USER;
```

---

## VARIANT for JSON Storage

```sql
-- Use VARIANT for flexible metadata
sources_used VARIANT,  -- [{"document_id": "abc", "title": "...", "score": 0.89}]
knowledge_owner VARIANT,  -- {"primary": "Milan", "backup": "Nico", "contact": "#ops"}
expertise_topics VARIANT,  -- ["Royalties", "DSP", "Distribution"]
tags VARIANT  -- ["billing", "enterprise", "onboarding"]

-- Query JSON fields
SELECT 
    question_text,
    sources_used[0]:title::VARCHAR AS top_source,
    knowledge_owner:primary::VARCHAR AS primary_owner
FROM REVSEARCH.ANALYTICS.QUESTIONS;

-- Array operations
SELECT * FROM REVSEARCH.ADMIN.KNOWLEDGE_OWNERS
WHERE ARRAY_CONTAINS('Royalties'::VARIANT, expertise_topics);
```

---

## Data Retention

```sql
-- 90-day time travel for recovery
ALTER TABLE REVSEARCH.CURATED.DOCUMENTS SET DATA_RETENTION_TIME_IN_DAYS = 90;
ALTER TABLE REVSEARCH.ANALYTICS.QUESTIONS SET DATA_RETENTION_TIME_IN_DAYS = 365;

-- Archive old documents instead of deleting
UPDATE REVSEARCH.CURATED.DOCUMENTS 
SET status = 'archived' 
WHERE last_updated < DATEADD('year', -1, CURRENT_TIMESTAMP());
```
