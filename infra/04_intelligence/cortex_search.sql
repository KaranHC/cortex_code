CREATE OR REPLACE CORTEX SEARCH SERVICE SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH
    ON content
    ATTRIBUTES title, team, topic, product_area, source_system, owner, backup_owner,
               last_updated, document_id, chunk_id, source_url, status, freshness_score
    WAREHOUSE = AI_WH
    TARGET_LAG = '1 hour'
AS (
    SELECT content, title, team, topic, product_area, source_system, owner, backup_owner,
           last_updated, document_id, chunk_id, source_url, status, freshness_score
    FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
    WHERE status = 'active' AND content IS NOT NULL AND LENGTH(content) > 50
);
