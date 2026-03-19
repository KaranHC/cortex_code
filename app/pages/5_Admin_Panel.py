import streamlit as st

session = st.session_state.get("session")

DOCUMENTS_TABLE = "SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS"
KNOWLEDGE_OWNERS_TABLE = "SNOWFLAKE_INTELLIGENCE.ADMIN.KNOWLEDGE_OWNERS"
QUESTIONS_TABLE = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS"
FEEDBACK_TABLE = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK"

st.title("Admin Panel")

tab_docs, tab_owners, tab_weak, tab_system = st.tabs(["Documents", "Knowledge Owners", "Weak Answers", "System"])

with tab_docs:
    st.subheader("Document Overview")
    try:
        docs = session.sql(f"""
            SELECT TITLE, SOURCE_SYSTEM, TOPIC, PRODUCT_AREA, CONTENT_LENGTH, CREATED_AT
            FROM {DOCUMENTS_TABLE}
            ORDER BY CREATED_AT DESC
            LIMIT 50
        """).to_pandas()
        st.dataframe(docs, use_container_width=True)
    except Exception as e:
        st.error(f"Could not load documents: {e}")

with tab_owners:
    st.subheader("Add Knowledge Owner")
    with st.form("add_owner_form", clear_on_submit=True):
        owner_name = st.text_input("Name")
        owner_team = st.text_input("Team")
        try:
            available_topics = session.sql(f"""
                SELECT DISTINCT TOPIC FROM {DOCUMENTS_TABLE}
                WHERE TOPIC IS NOT NULL
                ORDER BY TOPIC
            """).to_pandas()["TOPIC"].tolist()
        except Exception:
            available_topics = []
        owner_topics = st.multiselect("Topics", options=available_topics)
        owner_contact = st.text_input("Contact (email or Slack)")
        owner_backup = st.text_input("Backup For (name)")
        owner_submitted = st.form_submit_button("Add Owner")

        if owner_submitted and owner_name and owner_topics:
            escaped_name = owner_name.replace("'", "''")
            escaped_team_o = owner_team.replace("'", "''")
            escaped_contact = owner_contact.replace("'", "''")
            escaped_backup = owner_backup.replace("'", "''")
            topics_array = ", ".join(f"'{t.replace(chr(39), chr(39)+chr(39))}'" for t in owner_topics)
            try:
                session.sql(f"""
                    INSERT INTO {KNOWLEDGE_OWNERS_TABLE}
                    (NAME, TEAM, EXPERTISE_TOPICS, CONTACT_METHOD, BACKUP_FOR, CREATED_AT)
                    SELECT
                        '{escaped_name}',
                        '{escaped_team_o}',
                        ARRAY_CONSTRUCT({topics_array}),
                        '{escaped_contact}',
                        '{escaped_backup}',
                        CURRENT_TIMESTAMP()
                """).collect()
                st.success(f"Owner '{owner_name}' added for {len(owner_topics)} topic(s).")
            except Exception as e:
                st.error(f"Failed to add owner: {e}")

    st.subheader("Current Knowledge Owners")
    try:
        owners = session.sql(f"""
            SELECT NAME, TEAM, EXPERTISE_TOPICS, CONTACT_METHOD, BACKUP_FOR, IS_ACTIVE, CREATED_AT
            FROM {KNOWLEDGE_OWNERS_TABLE}
            ORDER BY NAME
        """).to_pandas()
        st.dataframe(owners, use_container_width=True)
    except Exception as e:
        st.error(f"Could not load knowledge owners: {e}")

with tab_weak:
    st.subheader("Questions Needing Attention")
    try:
        weak_questions = session.sql(f"""
            SELECT Q.QUESTION_TEXT, Q.ANSWER_STRENGTH, Q.ANSWER, Q.DATE_ASKED
            FROM {QUESTIONS_TABLE} Q
            WHERE Q.ANSWER_STRENGTH IN ('weak', 'no_answer')
            ORDER BY Q.DATE_ASKED DESC
            LIMIT 50
        """).to_pandas()
        st.dataframe(weak_questions, use_container_width=True)
    except Exception as e:
        st.error(f"Could not load weak answers: {e}")

    st.subheader("Negative Feedback")
    try:
        neg_feedback = session.sql(f"""
            SELECT F.QUESTION_ID, Q.QUESTION_TEXT, F.USER_NAME, F.FEEDBACK_TEXT, F.CREATED_AT
            FROM {FEEDBACK_TABLE} F
            LEFT JOIN {QUESTIONS_TABLE} Q ON F.QUESTION_ID = Q.QUESTION_ID
            WHERE F.FEEDBACK_TYPE = 'negative'
            ORDER BY F.CREATED_AT DESC
            LIMIT 50
        """).to_pandas()
        st.dataframe(neg_feedback, use_container_width=True)
    except Exception as e:
        st.error(f"Could not load negative feedback: {e}")

with tab_system:
    st.subheader("Ingestion Status")
    try:
        ingestion = session.sql("""
            SELECT SOURCE_SYSTEM, STATUS, COUNT(*) AS TOTAL_DOCUMENTS,
                MIN(CREATED_AT) AS EARLIEST_DOC, MAX(LAST_UPDATED) AS LATEST_DOC
            FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
            GROUP BY SOURCE_SYSTEM, STATUS
        """).to_pandas()
        st.dataframe(ingestion, use_container_width=True)
    except Exception as e:
        st.error(f"Could not load ingestion status: {e}")

    st.subheader("Document Counts by Topic")
    try:
        by_topic = session.sql(f"""
            SELECT COALESCE(TOPIC, 'Unclassified') AS TOPIC, COUNT(*) AS DOC_COUNT
            FROM {DOCUMENTS_TABLE}
            GROUP BY TOPIC
            ORDER BY DOC_COUNT DESC
        """).to_pandas()
        st.bar_chart(by_topic.set_index("TOPIC"))
    except Exception as e:
        st.error(f"Could not load topic counts: {e}")

    st.subheader("Search Service Health")
    try:
        st.info("Cortex Search Service: SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH")
        health = session.sql("""
            SHOW CORTEX SEARCH SERVICES IN SCHEMA SNOWFLAKE_INTELLIGENCE.SEARCH
        """).to_pandas()
        st.dataframe(health, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not retrieve search service info: {e}")

    st.subheader("Ingestion Logs")
    try:
        logs = session.sql("""
            SELECT SOURCE_SYSTEM, INGESTION_TYPE, STARTED_AT, COMPLETED_AT,
                   RECORDS_INGESTED, STATUS, ERROR_MESSAGE
            FROM SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
            ORDER BY STARTED_AT DESC LIMIT 10
        """).to_pandas()
        st.dataframe(logs, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load ingestion logs: {e}")
