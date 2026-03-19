CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG (
    source_system    VARCHAR(20),
    ingestion_type   VARCHAR(20),
    started_at       TIMESTAMP_NTZ,
    completed_at     TIMESTAMP_NTZ,
    records_ingested NUMBER,
    status           VARCHAR(20),
    error_message    VARCHAR
);
