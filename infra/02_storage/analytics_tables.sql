CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS (
    question_id        VARCHAR(64) PRIMARY KEY DEFAULT UUID_STRING(),
    question_text      VARCHAR(5000) NOT NULL,
    user_name          VARCHAR(200),
    user_email         VARCHAR(500),
    user_team          VARCHAR(200),
    date_asked         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    answer             VARCHAR,
    answer_strength    VARCHAR(20),
    sources_used       VARIANT,
    knowledge_owner    VARIANT,
    related_questions  VARIANT,
    response_latency_ms NUMBER,
    model_used         VARCHAR(100),
    session_id         VARCHAR(100)
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK (
    feedback_id        VARCHAR(64) PRIMARY KEY DEFAULT UUID_STRING(),
    question_id        VARCHAR(64) NOT NULL,
    feedback_type      VARCHAR(20) NOT NULL,
    feedback_text      VARCHAR(2000),
    user_name          VARCHAR(200),
    created_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
