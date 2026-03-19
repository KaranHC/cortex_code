CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.ADMIN.KNOWLEDGE_OWNERS (
    owner_id           VARCHAR(64) PRIMARY KEY DEFAULT UUID_STRING(),
    name               VARCHAR(200) NOT NULL,
    team               VARCHAR(200) NOT NULL,
    expertise_topics   VARIANT NOT NULL,
    product_areas      VARIANT,
    contact_method     VARCHAR(500),
    backup_for         VARCHAR(200),
    is_active          BOOLEAN DEFAULT TRUE,
    created_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.ADMIN.SYSTEM_CONFIG (
    config_key         VARCHAR(200) PRIMARY KEY,
    config_value       VARIANT,
    description        VARCHAR(1000),
    updated_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_by         VARCHAR(200)
);
