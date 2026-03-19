# Research: Analytics, Evaluation & Continuous Improvement
## Agent 10 Output — Comprehensive Findings

---

## FAQ Analytics Module

### Question Logging Pipeline

Every question submitted through the Streamlit app is logged to `REVSEARCH.ANALYTICS.QUESTIONS`:

```python
# In Streamlit app, after getting agent response
import json
import time

session.sql("""
    INSERT INTO REVSEARCH.ANALYTICS.QUESTIONS
    (question_id, question_text, user_name, user_team, answer, answer_strength,
     sources_used, knowledge_owner, related_questions, response_latency_ms, model_used)
    VALUES (
        :1, :2, CURRENT_USER(), :3, :4, :5, 
        PARSE_JSON(:6), PARSE_JSON(:7), PARSE_JSON(:8), :9, :10
    )
""", [
    question_id, question_text, user_team, answer_text, answer_strength,
    json.dumps(sources), json.dumps(knowledge_owner), json.dumps(related),
    response_latency_ms, "claude-3.5-sonnet"
]).collect()
```

---

## Dynamic Tables for Real-Time Aggregation

### FAQ Summary (Group Similar Questions)

```sql
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
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS weak_count,
    ROUND(
        COUNT_IF(f.feedback_type = 'thumbs_up') * 100.0 / 
        NULLIF(COUNT_IF(f.feedback_type IS NOT NULL), 0), 
        1
    ) AS satisfaction_pct
FROM REVSEARCH.ANALYTICS.QUESTIONS q
LEFT JOIN REVSEARCH.ANALYTICS.FEEDBACK f ON q.question_id = f.question_id
GROUP BY question_text;
```

### Team Analytics

```sql
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
    ROUND(COUNT_IF(answer_strength = 'strong') * 100.0 / NULLIF(COUNT(*), 0), 1) AS strong_pct,
    ROUND(AVG(response_latency_ms), 0) AS avg_latency_ms,
    MAX(date_asked) AS last_question
FROM REVSEARCH.ANALYTICS.QUESTIONS
GROUP BY COALESCE(user_team, 'Unknown');
```

### Knowledge Gaps Detection

```sql
CREATE OR REPLACE DYNAMIC TABLE REVSEARCH.ANALYTICS.KNOWLEDGE_GAPS
    TARGET_LAG = '1 hour'
    WAREHOUSE = REVSEARCH_SEARCH_WH
AS
SELECT
    question_text,
    answer_strength,
    COUNT(*) AS times_asked,
    MAX(date_asked) AS last_asked,
    ARRAY_AGG(DISTINCT user_team) AS teams_affected,
    MAX(knowledge_owner:primary_owner::VARCHAR) AS suggested_owner
FROM REVSEARCH.ANALYTICS.QUESTIONS
WHERE answer_strength IN ('weak', 'no_answer')
GROUP BY question_text, answer_strength
HAVING COUNT(*) >= 2
ORDER BY times_asked DESC;
```

### Daily Trends

```sql
CREATE OR REPLACE DYNAMIC TABLE REVSEARCH.ANALYTICS.DAILY_TRENDS
    TARGET_LAG = '1 hour'
    WAREHOUSE = REVSEARCH_SEARCH_WH
AS
SELECT
    DATE_TRUNC('day', date_asked) AS ask_date,
    COUNT(*) AS total_questions,
    COUNT_IF(answer_strength = 'strong') AS strong,
    COUNT_IF(answer_strength = 'medium') AS medium,
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS weak_or_none,
    ROUND(AVG(response_latency_ms), 0) AS avg_latency_ms,
    COUNT(DISTINCT user_name) AS unique_users
FROM REVSEARCH.ANALYTICS.QUESTIONS
GROUP BY DATE_TRUNC('day', date_asked);
```

### Topic Distribution

```sql
CREATE OR REPLACE DYNAMIC TABLE REVSEARCH.ANALYTICS.TOPIC_DISTRIBUTION
    TARGET_LAG = '1 hour'
    WAREHOUSE = REVSEARCH_SEARCH_WH
AS
SELECT
    SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        question_text,
        ['Royalties', 'Distribution', 'Billing', 'Onboarding', 'DSP', 
         'Content Management', 'Technical Support', 'Account Management', 'General']
    ):label::VARCHAR AS predicted_topic,
    COUNT(*) AS question_count,
    COUNT_IF(answer_strength = 'strong') AS strong_count,
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS gap_count
FROM REVSEARCH.ANALYTICS.QUESTIONS
GROUP BY predicted_topic;
```

---

## Question Clustering with Embeddings

### Purpose
Group semantically similar questions to:
- Identify the "real" FAQ (canonical form of repeated questions)
- Detect trends in what employees are asking
- Find patterns in knowledge gaps

### Implementation

```sql
-- Pre-compute embeddings for clustering (batch job)
CREATE OR REPLACE TABLE REVSEARCH.ANALYTICS.QUESTION_EMBEDDINGS AS
SELECT
    question_id,
    question_text,
    date_asked,
    answer_strength,
    SNOWFLAKE.CORTEX.EMBED_TEXT_1024(
        'snowflake-arctic-embed-l-v2.0',
        question_text
    ) AS embedding
FROM REVSEARCH.ANALYTICS.QUESTIONS;

-- Find similar question pairs
SELECT 
    q1.question_text AS q1_text,
    q2.question_text AS q2_text,
    VECTOR_COSINE_SIMILARITY(q1.embedding, q2.embedding) AS similarity
FROM REVSEARCH.ANALYTICS.QUESTION_EMBEDDINGS q1
JOIN REVSEARCH.ANALYTICS.QUESTION_EMBEDDINGS q2
    ON q1.question_id < q2.question_id
WHERE VECTOR_COSINE_SIMILARITY(q1.embedding, q2.embedding) > 0.85
ORDER BY similarity DESC
LIMIT 100;
```

---

## User Feedback Analysis

### Feedback Collection

```python
# In Streamlit, after displaying answer
col1, col2 = st.columns(2)
with col1:
    if st.button("👍 Helpful", key=f"up_{question_id}"):
        session.sql("""
            INSERT INTO REVSEARCH.ANALYTICS.FEEDBACK 
            (question_id, feedback_type, user_name)
            VALUES (:1, 'thumbs_up', CURRENT_USER())
        """, [question_id]).collect()
        st.success("Thanks!")

with col2:
    if st.button("👎 Not Helpful", key=f"down_{question_id}"):
        feedback_text = st.text_input("What was wrong?", key=f"fb_{question_id}")
        session.sql("""
            INSERT INTO REVSEARCH.ANALYTICS.FEEDBACK 
            (question_id, feedback_type, feedback_text, user_name)
            VALUES (:1, 'thumbs_down', :2, CURRENT_USER())
        """, [question_id, feedback_text]).collect()
        st.info("We'll use this to improve.")
```

### Feedback Analytics

```sql
-- Overall satisfaction rate
SELECT
    ROUND(
        COUNT_IF(feedback_type = 'thumbs_up') * 100.0 / 
        NULLIF(COUNT(*), 0), 
        1
    ) AS satisfaction_rate,
    COUNT_IF(feedback_type = 'thumbs_up') AS positive,
    COUNT_IF(feedback_type = 'thumbs_down') AS negative,
    COUNT(*) AS total_feedback
FROM REVSEARCH.ANALYTICS.FEEDBACK;

-- Satisfaction by answer strength
SELECT
    q.answer_strength,
    ROUND(
        COUNT_IF(f.feedback_type = 'thumbs_up') * 100.0 / 
        NULLIF(COUNT(*), 0), 
        1
    ) AS satisfaction_rate,
    COUNT(*) AS feedback_count
FROM REVSEARCH.ANALYTICS.FEEDBACK f
JOIN REVSEARCH.ANALYTICS.QUESTIONS q ON f.question_id = q.question_id
GROUP BY q.answer_strength;

-- Most disliked answers (for improvement)
SELECT
    q.question_text,
    q.answer_strength,
    q.answer,
    f.feedback_text,
    f.created_at
FROM REVSEARCH.ANALYTICS.FEEDBACK f
JOIN REVSEARCH.ANALYTICS.QUESTIONS q ON f.question_id = q.question_id
WHERE f.feedback_type = 'thumbs_down'
ORDER BY f.created_at DESC
LIMIT 20;
```

---

## Knowledge Gap Detection

### Weekly Knowledge Gap Report

```sql
-- Questions that need documentation
SELECT
    question_text,
    times_asked,
    teams_affected,
    suggested_owner,
    last_asked,
    DATEDIFF('day', last_asked, CURRENT_TIMESTAMP()) AS days_since_last
FROM REVSEARCH.ANALYTICS.KNOWLEDGE_GAPS
ORDER BY times_asked DESC
LIMIT 20;
```

### Auto-Detect Trending Topics

```sql
-- Topics trending upward this week vs last week
WITH this_week AS (
    SELECT
        SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
            question_text,
            ['Royalties', 'Distribution', 'Billing', 'Onboarding', 'DSP', 'General']
        ):label::VARCHAR AS topic,
        COUNT(*) AS cnt
    FROM REVSEARCH.ANALYTICS.QUESTIONS
    WHERE date_asked >= DATEADD('day', -7, CURRENT_TIMESTAMP())
    GROUP BY topic
),
last_week AS (
    SELECT
        SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
            question_text,
            ['Royalties', 'Distribution', 'Billing', 'Onboarding', 'DSP', 'General']
        ):label::VARCHAR AS topic,
        COUNT(*) AS cnt
    FROM REVSEARCH.ANALYTICS.QUESTIONS
    WHERE date_asked BETWEEN DATEADD('day', -14, CURRENT_TIMESTAMP()) 
                        AND DATEADD('day', -7, CURRENT_TIMESTAMP())
    GROUP BY topic
)
SELECT
    tw.topic,
    tw.cnt AS this_week,
    COALESCE(lw.cnt, 0) AS last_week,
    tw.cnt - COALESCE(lw.cnt, 0) AS change,
    ROUND((tw.cnt - COALESCE(lw.cnt, 0)) * 100.0 / NULLIF(COALESCE(lw.cnt, 0), 0), 1) AS pct_change
FROM this_week tw
LEFT JOIN last_week lw ON tw.topic = lw.topic
ORDER BY change DESC;
```

---

## Dashboard KPIs

### Executive Summary Metrics

| KPI | SQL | Widget |
|-----|-----|--------|
| Total Questions | `COUNT(*) FROM QUESTIONS` | `st.metric` |
| Strong Answer Rate | `COUNT_IF(strength='strong')/COUNT(*)` | `st.metric` with delta |
| Knowledge Gaps | `COUNT(*) FROM KNOWLEDGE_GAPS` | `st.metric` |
| Avg Response Time | `AVG(response_latency_ms)/1000` | `st.metric` |
| User Satisfaction | `COUNT_IF(thumbs_up)/COUNT(feedback)` | `st.metric` |
| Unique Users/Week | `COUNT(DISTINCT user) WHERE last 7 days` | `st.metric` |
| Docs Served | `COUNT(DISTINCT document_id) FROM sources_used` | `st.metric` |
| Stale Docs | `COUNT(*) WHERE last_updated < -90 days` | `st.metric` with warning |

### Chart Implementations

```python
# Questions over time (line chart)
trends = session.sql("SELECT * FROM REVSEARCH.ANALYTICS.DAILY_TRENDS ORDER BY ask_date").to_pandas()
st.line_chart(trends.set_index("ASK_DATE")[["TOTAL_QUESTIONS", "STRONG", "WEAK_OR_NONE"]])

# Answer strength distribution (bar chart)
strength = session.sql("""
    SELECT answer_strength, COUNT(*) AS cnt 
    FROM REVSEARCH.ANALYTICS.QUESTIONS 
    GROUP BY answer_strength
""").to_pandas()
st.bar_chart(strength.set_index("ANSWER_STRENGTH"))

# Team comparison (horizontal bar)
teams = session.sql("SELECT * FROM REVSEARCH.ANALYTICS.TEAM_SUMMARY ORDER BY total_questions DESC").to_pandas()
st.bar_chart(teams.set_index("TEAM")["TOTAL_QUESTIONS"])
```

---

## Continuous Improvement Loop

### Monthly Review Process
1. **Pull top 20 negative feedback answers** → Review for prompt improvements
2. **Identify top 10 knowledge gaps** → Assign to knowledge owners
3. **Check document staleness** → Flag documents > 90 days old
4. **Compare answer quality metrics** → Month-over-month trends
5. **Review credit consumption** → Optimize model usage

### Automated Improvement Triggers

```sql
-- Alert when satisfaction drops below 80%
CREATE OR REPLACE ALERT REVSEARCH.ANALYTICS.SATISFACTION_ALERT
    WAREHOUSE = REVSEARCH_SEARCH_WH
    SCHEDULE = 'USING CRON 0 10 * * 1 America/Los_Angeles'
    IF (EXISTS (
        SELECT 1
        FROM REVSEARCH.ANALYTICS.FEEDBACK
        WHERE created_at >= DATEADD('day', -7, CURRENT_TIMESTAMP())
        HAVING COUNT_IF(feedback_type = 'thumbs_up') * 100.0 / NULLIF(COUNT(*), 0) < 80
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'REVSEARCH_EMAIL',
            'admin@revelator.com',
            'RevSearch: Satisfaction Below 80%',
            'User satisfaction has dropped below 80% this week. Review negative feedback.'
        );
```
