-- Tier 1: Core Operational (40/min bucket)
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS (
    id                 NUMBER PRIMARY KEY,
    subject            VARCHAR(2000),
    description        VARCHAR,
    description_text   VARCHAR,
    status             NUMBER,
    priority           NUMBER,
    source             NUMBER,
    type               VARCHAR(100),
    requester_id       NUMBER,
    responder_id       NUMBER,
    company_id         NUMBER,
    group_id           NUMBER,
    product_id         NUMBER,
    email_config_id    NUMBER,
    to_emails          VARIANT,
    cc_emails          VARIANT,
    fwd_emails         VARIANT,
    reply_cc_emails    VARIANT,
    fr_escalated       BOOLEAN,
    spam               BOOLEAN,
    is_escalated       BOOLEAN,
    tags               VARIANT,
    custom_fields      VARIANT,
    attachments        VARIANT,
    due_by             TIMESTAMP_NTZ,
    fr_due_by          TIMESTAMP_NTZ,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_CONVERSATIONS (
    id                 NUMBER PRIMARY KEY,
    ticket_id          NUMBER NOT NULL,
    body               VARCHAR,
    body_text          VARCHAR,
    user_id            NUMBER,
    source             NUMBER,
    category           NUMBER,
    incoming           BOOLEAN,
    private            BOOLEAN,
    to_emails          VARIANT,
    from_email         VARCHAR(500),
    cc_emails          VARIANT,
    bcc_emails         VARIANT,
    support_email      VARCHAR(500),
    attachments        VARIANT,
    last_edited_at     TIMESTAMP_NTZ,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_CONTACTS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    email              VARCHAR(500),
    phone              VARCHAR(100),
    mobile             VARCHAR(100),
    company_id         NUMBER,
    active             BOOLEAN,
    job_title          VARCHAR(500),
    language           VARCHAR(50),
    time_zone          VARCHAR(100),
    description        VARCHAR,
    address            VARCHAR(1000),
    tags               VARIANT,
    custom_fields      VARIANT,
    other_emails       VARIANT,
    other_companies    VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- Tier 1: Core Operational (100/min bucket)
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_COMPANIES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(1000),
    description        VARCHAR,
    note               VARCHAR,
    domains            VARIANT,
    health_score       VARCHAR(100),
    account_tier       VARCHAR(100),
    renewal_date       TIMESTAMP_NTZ,
    industry           VARCHAR(200),
    custom_fields      VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AGENTS (
    id                 NUMBER PRIMARY KEY,
    contact            VARIANT,
    type               VARCHAR(50),
    occasional         BOOLEAN,
    signature          VARCHAR,
    ticket_scope       NUMBER,
    group_ids          VARIANT,
    role_ids           VARIANT,
    available          BOOLEAN,
    available_since    TIMESTAMP_NTZ,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_GROUPS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR(2000),
    escalate_to        NUMBER,
    unassigned_for     VARCHAR(100),
    business_hour_id   NUMBER,
    group_type         VARCHAR(100),
    auto_ticket_assign NUMBER,
    agent_ids          VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_ROLES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR,
    default_role       BOOLEAN,
    agent_type         NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_ACCOUNT (
    account_id         NUMBER PRIMARY KEY,
    account_name       VARCHAR(500),
    account_domain     VARCHAR(500),
    tier_type          VARCHAR(100),
    timezone           VARCHAR(100),
    data_center        VARCHAR(50),
    total_agents       VARIANT,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- Tier 2: Field Metadata + Forms
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_FIELDS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    label              VARCHAR(500),
    label_for_customers VARCHAR(500),
    description        VARCHAR,
    type               VARCHAR(100),
    position           NUMBER,
    required_for_closure BOOLEAN,
    required_for_agents BOOLEAN,
    required_for_customers BOOLEAN,
    customers_can_edit BOOLEAN,
    choices            VARIANT,
    nested_fields      VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_CONTACT_FIELDS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    label              VARCHAR(500),
    type               VARCHAR(100),
    position           NUMBER,
    required_for_agents BOOLEAN,
    customers_can_edit BOOLEAN,
    editable_in_signup BOOLEAN,
    choices            VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_COMPANY_FIELDS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    label              VARCHAR(500),
    type               VARCHAR(100),
    position           NUMBER,
    required_for_agents BOOLEAN,
    choices            VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_FORMS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    title              VARCHAR(500),
    description        VARCHAR,
    default_form       BOOLEAN,
    portals            VARIANT,
    fields             VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- Tier 1: Solutions (Knowledge Base)
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_CATEGORIES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(1000),
    description        VARCHAR,
    visible_in_portals VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_FOLDERS (
    id                 NUMBER PRIMARY KEY,
    category_id        NUMBER NOT NULL,
    name               VARCHAR(1000),
    description        VARCHAR,
    visibility         NUMBER,
    articles_count     NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_ARTICLES (
    id                 NUMBER PRIMARY KEY,
    folder_id          NUMBER NOT NULL,
    category_id        NUMBER,
    agent_id           NUMBER,
    title              VARCHAR(2000),
    description        VARCHAR,
    description_text   VARCHAR,
    status             NUMBER,
    type               NUMBER,
    hits               NUMBER,
    thumbs_up          NUMBER,
    thumbs_down        NUMBER,
    seo_data           VARIANT,
    tags               VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- Tier 2: Discussions
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_CATEGORIES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(1000),
    description        VARCHAR,
    position           NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_FORUMS (
    id                 NUMBER PRIMARY KEY,
    category_id        NUMBER NOT NULL,
    name               VARCHAR(1000),
    description        VARCHAR,
    forum_type         NUMBER,
    forum_visibility   NUMBER,
    topics_count       NUMBER,
    position           NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_TOPICS (
    id                 NUMBER PRIMARY KEY,
    forum_id           NUMBER NOT NULL,
    title              VARCHAR(2000),
    user_id            NUMBER,
    locked             BOOLEAN,
    sticky             BOOLEAN,
    hits               NUMBER,
    replies            NUMBER,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_COMMENTS (
    id                 NUMBER PRIMARY KEY,
    topic_id           NUMBER NOT NULL,
    user_id            NUMBER,
    body               VARCHAR,
    body_text          VARCHAR,
    answer             BOOLEAN,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- Tier 2: Customer Satisfaction
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SURVEYS (
    id                 NUMBER PRIMARY KEY,
    title              VARCHAR(500),
    active             BOOLEAN,
    questions          VARIANT,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SATISFACTION_RATINGS (
    id                 NUMBER PRIMARY KEY,
    survey_id          NUMBER,
    user_id            NUMBER,
    agent_id           NUMBER,
    ticket_id          NUMBER,
    group_id           NUMBER,
    feedback           VARCHAR,
    ratings            VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

-- Tier 3: Admin / Config
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_EMAIL_CONFIGS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    to_email           VARCHAR(500),
    reply_email        VARCHAR(500),
    group_id           NUMBER,
    primary_role       BOOLEAN,
    active             BOOLEAN,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_EMAIL_MAILBOXES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    support_email      VARCHAR(500),
    product_id         NUMBER,
    group_id           NUMBER,
    active             BOOLEAN,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_BUSINESS_HOURS (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR,
    is_default         BOOLEAN,
    time_zone          VARCHAR(100),
    business_hours     VARIANT,
    list_of_holidays   VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SLA_POLICIES (
    id                 NUMBER PRIMARY KEY,
    name               VARCHAR(500),
    description        VARCHAR,
    is_default         BOOLEAN,
    active             BOOLEAN,
    position           NUMBER,
    applicable_to      VARIANT,
    sla_target         VARIANT,
    escalation         VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);

CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AUTOMATION_RULES (
    id                 NUMBER PRIMARY KEY,
    automation_type_id NUMBER NOT NULL,
    name               VARCHAR(500),
    active             BOOLEAN,
    position           NUMBER,
    conditions         VARIANT,
    actions            VARIANT,
    performer          VARIANT,
    created_at         TIMESTAMP_NTZ,
    updated_at         TIMESTAMP_NTZ,
    raw_json           VARIANT,
    _loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _source_system     VARCHAR DEFAULT 'freshdesk'
);
