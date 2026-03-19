CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.CLASSIFY_DOCUMENTS()
RETURNS STRING
LANGUAGE SQL
AS
BEGIN
    UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
    SET topic = SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        SUBSTR(content, 1, 4000),
        ARRAY_CONSTRUCT('Product Documentation', 'Support Process', 'Onboarding', 'Billing Policy',
         'Operational Procedure', 'Ownership Directory', 'Technical Guide', 'FAQ',
         'Release Notes', 'Training Material')
    )['label']::VARCHAR
    WHERE topic IS NULL;

    UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
    SET product_area = SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        SUBSTR(content, 1, 4000),
        ARRAY_CONSTRUCT('Royalties', 'DSP', 'Distribution', 'Billing', 'Onboarding',
         'Analytics', 'Rights Management', 'Content Delivery', 'Account Management', 'General')
    )['label']::VARCHAR
    WHERE product_area IS NULL;

    UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS c
    SET c.topic = d.topic,
        c.product_area = d.product_area,
        c.team = d.team,
        c.owner = d.owner,
        c.backup_owner = d.backup_owner
    FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS d
    WHERE c.document_id = d.document_id;

    RETURN 'Classification complete';
END;
