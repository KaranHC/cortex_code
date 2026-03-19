USE DATABASE SNOWFLAKE_INTELLIGENCE;
USE SCHEMA ANALYTICS;

CREATE TABLE IF NOT EXISTS EVAL_QUESTIONS (
    QUESTION_ID NUMBER AUTOINCREMENT,
    QUESTION VARCHAR,
    EXPECTED_SOURCE VARCHAR,
    CATEGORY VARCHAR,
    CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

INSERT INTO EVAL_QUESTIONS (QUESTION, EXPECTED_SOURCE, CATEGORY)
VALUES
    ('What are the most common ticket resolution patterns and average resolution times across all Freshdesk tickets?', 'freshdesk', 'ticket_resolution'),
    ('Which support agents have the highest ticket resolution rates and fastest response times?', 'freshdesk', 'agent_performance'),
    ('What percentage of tickets are resolved within SLA deadlines, and which ticket priorities have the most SLA violations?', 'freshdesk', 'sla_compliance'),
    ('What are the most frequently used tags and categories across the 1828 support tickets?', 'freshdesk', 'ticket_topics'),
    ('What customer support workflows and escalation processes are documented in the Freshdesk knowledge base?', 'freshdesk', 'support_processes'),
    ('What topics do the 179 solution articles cover, and which articles are most referenced in ticket resolutions?', 'freshdesk', 'solution_articles'),
    ('What are the main discussion topics across the 8 forum categories, and how active is community engagement?', 'freshdesk', 'discussion_topics'),
    ('How do support resolution metrics from Freshdesk tickets compare with documentation coverage in GitBook?', 'freshdesk', 'cross_source_comparison'),
    ('Which of the 434 companies generate the most support tickets, and what are the common contact patterns among the 43049 contacts?', 'freshdesk', 'company_contact_info'),
    ('How are the 40 support agents organized into groups, and what is the team structure for handling different ticket types?', 'freshdesk', 'team_structure');
