CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_SPACES (
    space_id           VARCHAR(100) PRIMARY KEY,
    title              VARCHAR(1000),
    description        VARCHAR(2000),
    visibility         VARCHAR(50),
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    urls               VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'gitbook'
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_PAGES (
    page_id            VARCHAR(100),
    space_id           VARCHAR(100),
    space_title        VARCHAR(500),
    title              VARCHAR(1000),
    description        VARCHAR(2000),
    path               VARCHAR(2000),
    content_markdown   VARCHAR,
    parent_page_id     VARCHAR(100),
    kind               VARCHAR(50),
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'gitbook'
);

CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_COLLECTIONS (
    collection_id      VARCHAR(100) PRIMARY KEY,
    space_id           VARCHAR(100),
    title              VARCHAR(1000),
    description        VARCHAR(2000),
    path               VARCHAR(2000),
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'gitbook'
);
