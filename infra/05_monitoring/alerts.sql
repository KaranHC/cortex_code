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
            'SI_EMAIL_NOTIFICATIONS',
            'admin@revelator.com',
            'RevSearch: Knowledge Gaps Detected',
            'Multiple questions received weak or no answers this week. Review the FAQ Dashboard for details.'
        );

ALTER ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.KNOWLEDGE_GAP_ALERT RESUME;

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
            'SI_EMAIL_NOTIFICATIONS',
            'admin@revelator.com',
            'RevSearch: Daily Cortex Credit Threshold Exceeded',
            'RevSearch used more than 10 Cortex credits yesterday. Review usage in the Admin Panel.'
        );

ALTER ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.CORTEX_COST_ALERT RESUME;

CREATE OR REPLACE ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUALITY_REGRESSION_ALERT
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 10 * * * America/Los_Angeles'
    IF (EXISTS (
        SELECT 1
        FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.REQUEST_TRACES
        WHERE created_at >= DATEADD('hour', -24, CURRENT_TIMESTAMP())
        GROUP BY ALL
        HAVING COUNT_IF(answer_strength IN ('weak', 'no_answer')) * 100.0 / COUNT(*) > 30
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'SI_EMAIL_NOTIFICATIONS',
            'admin@revelator.com',
            'RevSearch: Quality Regression — >30% weak/no_answer in last 24h',
            'More than 30% of queries in the last 24 hours received weak or no answers.'
        );

ALTER ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUALITY_REGRESSION_ALERT RESUME;
