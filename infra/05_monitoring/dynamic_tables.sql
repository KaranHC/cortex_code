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

CREATE OR REPLACE DYNAMIC TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.AGENT_PERFORMANCE
    TARGET_LAG = '1 hour'
    WAREHOUSE = AI_WH
AS
SELECT
    DATE_TRUNC('hour', created_at) AS hour,
    agent_used,
    COUNT(*) AS total_requests,
    COUNT_IF(answer_strength = 'strong') AS strong_count,
    COUNT_IF(answer_strength = 'medium') AS medium_count,
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS weak_or_none,
    COUNT_IF(fallback_triggered) AS fallback_count,
    AVG(total_latency_ms) AS avg_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_latency_ms) AS p95_latency_ms,
    ARRAYAGG(DISTINCT CASE WHEN error_messages IS NOT NULL THEN error_messages END) AS errors
FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.REQUEST_TRACES
GROUP BY hour, agent_used;
