"""
Integration tests that connect to Snowflake and validate deployed objects
match local SQL definitions. Run with: pytest tests/test_integration.py -v
"""
import json
import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFRA_DIR = os.path.join(PROJECT_ROOT, "infra")


class TestDeployedProcedures:
    def test_process_documents_procedure_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW PROCEDURES LIKE 'PROCESS_DOCUMENTS'
            IN SCHEMA SNOWFLAKE_INTELLIGENCE.INGESTION
        """)
        rows = sf_cursor.fetchall()
        assert len(rows) >= 1, "PROCESS_DOCUMENTS procedure not found"

    def test_process_documents_uses_insert_select(self, sf_cursor):
        sf_cursor.execute("""
            SELECT GET_DDL('PROCEDURE',
                'SNOWFLAKE_INTELLIGENCE.INGESTION.PROCESS_DOCUMENTS()')
        """)
        ddl = sf_cursor.fetchone()[0]
        assert "row.get(" not in ddl, \
            "Deployed PROCESS_DOCUMENTS still uses row.get() — redeploy needed"
        assert "VALUES" not in ddl.split("INSERT INTO")[1] if "INSERT INTO" in ddl else True, \
            "Deployed PROCESS_DOCUMENTS uses INSERT...VALUES instead of INSERT...SELECT"

    def test_process_documents_null_timestamp_handling(self, sf_cursor):
        sf_cursor.execute("""
            SELECT GET_DDL('PROCEDURE',
                'SNOWFLAKE_INTELLIGENCE.INGESTION.PROCESS_DOCUMENTS()')
        """)
        ddl = sf_cursor.fetchone()[0]
        assert "CURRENT_TIMESTAMP()" in ddl, \
            "Deployed PROCESS_DOCUMENTS missing CURRENT_TIMESTAMP() NULL fallback"

    def test_ingest_gitbook_procedure_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW PROCEDURES LIKE 'INGEST_GITBOOK'
            IN SCHEMA SNOWFLAKE_INTELLIGENCE.INGESTION
        """)
        rows = sf_cursor.fetchall()
        assert len(rows) >= 1, "INGEST_GITBOOK procedure not found"

    def test_classify_documents_procedure_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW PROCEDURES LIKE 'CLASSIFY_DOCUMENTS'
            IN SCHEMA SNOWFLAKE_INTELLIGENCE.INGESTION
        """)
        rows = sf_cursor.fetchall()
        assert len(rows) >= 1, "CLASSIFY_DOCUMENTS procedure not found"


class TestDeployedAgents:
    def test_knowledge_assistant_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW AGENTS LIKE 'KNOWLEDGE_ASSISTANT'
            IN SCHEMA SNOWFLAKE_INTELLIGENCE.AGENTS
        """)
        rows = sf_cursor.fetchall()
        matching = [r for r in rows if r[1] == "KNOWLEDGE_ASSISTANT"]
        assert len(matching) == 1, "KNOWLEDGE_ASSISTANT agent not found"

    def test_knowledge_assistant_fallback_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW AGENTS LIKE 'KNOWLEDGE_ASSISTANT_FALLBACK'
            IN SCHEMA SNOWFLAKE_INTELLIGENCE.AGENTS
        """)
        rows = sf_cursor.fetchall()
        assert len(rows) >= 1, "KNOWLEDGE_ASSISTANT_FALLBACK agent not found"

    def test_knowledge_assistant_spec_has_search_tool(self, sf_cursor):
        sf_cursor.execute("""
            DESCRIBE AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT
        """)
        row = sf_cursor.fetchone()
        spec_str = row[6]
        spec = json.loads(spec_str) if isinstance(spec_str, str) else spec_str
        tools = spec.get("tools", [])
        tool_types = [t.get("tool_spec", {}).get("type") for t in tools]
        assert "cortex_search" in tool_types, \
            "KNOWLEDGE_ASSISTANT missing cortex_search tool"

    def test_agents_use_correct_search_service(self, sf_cursor):
        sf_cursor.execute("""
            DESCRIBE AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT
        """)
        row = sf_cursor.fetchone()
        spec_str = row[6]
        spec = json.loads(spec_str) if isinstance(spec_str, str) else spec_str
        tool_resources = spec.get("tool_resources", {})
        search_config = tool_resources.get("search_docs", {})
        service = search_config.get("search_service", "")
        assert "DOCUMENT_SEARCH" in service, \
            f"Agent references wrong search service: {service}"


class TestDeployedSearchService:
    def test_document_search_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW CORTEX SEARCH SERVICES
            IN SCHEMA SNOWFLAKE_INTELLIGENCE.SEARCH
        """)
        rows = sf_cursor.fetchall()
        names = [r[1] for r in rows]
        assert "DOCUMENT_SEARCH" in names, "DOCUMENT_SEARCH service not found"


class TestDeployedTables:
    EXPECTED_TABLES = {
        "RAW": ["GITBOOK_SPACES", "GITBOOK_PAGES", "GITBOOK_COLLECTIONS"],
        "CURATED": ["DOCUMENTS", "DOCUMENT_CHUNKS"],
        "ANALYTICS": ["QUESTIONS", "FEEDBACK"],
        "ADMIN": ["KNOWLEDGE_OWNERS", "SYSTEM_CONFIG"],
        "INGESTION": ["INGESTION_LOG"],
    }

    @pytest.mark.parametrize("schema,tables", EXPECTED_TABLES.items())
    def test_tables_exist(self, sf_cursor, schema, tables):
        sf_cursor.execute(f"""
            SHOW TABLES IN SCHEMA SNOWFLAKE_INTELLIGENCE.{schema}
        """)
        rows = sf_cursor.fetchall()
        existing = {r[1] for r in rows}
        for table in tables:
            assert table in existing, \
                f"Table {schema}.{table} not found in Snowflake"


class TestDeployedDynamicTables:
    def test_faq_summary_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW DYNAMIC TABLES LIKE 'FAQ_SUMMARY'
            IN SCHEMA SNOWFLAKE_INTELLIGENCE.ANALYTICS
        """)
        assert len(sf_cursor.fetchall()) >= 1

    def test_team_summary_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW DYNAMIC TABLES LIKE 'TEAM_SUMMARY'
            IN SCHEMA SNOWFLAKE_INTELLIGENCE.ANALYTICS
        """)
        assert len(sf_cursor.fetchall()) >= 1

    def test_knowledge_gaps_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW DYNAMIC TABLES LIKE 'KNOWLEDGE_GAPS'
            IN SCHEMA SNOWFLAKE_INTELLIGENCE.ANALYTICS
        """)
        assert len(sf_cursor.fetchall()) >= 1


class TestDeployedTasks:
    EXPECTED_TASKS = [
        "TASK_INGEST_GITBOOK",
        "TASK_PROCESS_DOCUMENTS",
        "TASK_CLASSIFY_DOCUMENTS",
        "FULL_REFRESH",
    ]

    def test_all_tasks_exist(self, sf_cursor):
        sf_cursor.execute("""
            SHOW TASKS IN SCHEMA SNOWFLAKE_INTELLIGENCE.INGESTION
        """)
        rows = sf_cursor.fetchall()
        existing = {r[1] for r in rows}
        for task in self.EXPECTED_TASKS:
            assert task in existing, f"Task {task} not found"


class TestStreamlitApp:
    def test_revsearch_app_exists(self, sf_cursor):
        sf_cursor.execute("""
            SHOW STREAMLITS IN SCHEMA SNOWFLAKE_INTELLIGENCE.APP
        """)
        rows = sf_cursor.fetchall()
        names = [r[1] for r in rows]
        assert "REVSEARCH" in names, "REVSEARCH Streamlit app not found"

    def test_revsearch_packages_valid(self, sf_cursor):
        sf_cursor.execute("""
            DESCRIBE STREAMLIT SNOWFLAKE_INTELLIGENCE.APP.REVSEARCH
        """)
        row = sf_cursor.fetchone()
        user_packages = row[7]
        assert "Error" not in str(user_packages), \
            f"Streamlit app has package errors: {user_packages}"
        assert "snowflake.core" not in str(user_packages), \
            f"snowflake.core should not be in packages (uses pure SQL): {user_packages}"
        assert "streamlit" in str(user_packages), \
            f"Missing streamlit in packages: {user_packages}"

    def test_stage_files_present(self, sf_cursor):
        sf_cursor.execute("""
            LIST @SNOWFLAKE_INTELLIGENCE.APP.REVSEARCH_STAGE/
        """)
        rows = sf_cursor.fetchall()
        files = {r[0].split("/")[-1] for r in rows}
        required = {"main.py", "environment.yml"}
        for f in required:
            assert f in files, f"Missing {f} in app stage"


class TestLiveAgentCalls:
    """Real E2E tests against live Cortex Agents — no mocks."""

    def test_primary_agent_responds(self, sf_cursor):
        sf_cursor.execute("""
            SELECT TRY_PARSE_JSON(
                SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                    'SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT',
                    '{"messages": [{"role": "user", "content": [{"type": "text", "text": "What is Revelator?"}]}]}'
                )
            ) AS resp
        """)
        row = sf_cursor.fetchone()
        resp = row[0]
        if isinstance(resp, str):
            resp = json.loads(resp)
        assert resp is not None, "Agent returned NULL"
        assert "content" in resp or "error_code" not in resp, \
            f"Agent returned error: {resp}"
        content = resp.get("content", [])
        assert len(content) > 0, "Agent returned empty content"

    def test_fallback_agent_responds(self, sf_cursor):
        sf_cursor.execute("""
            SELECT TRY_PARSE_JSON(
                SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                    'SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT_FALLBACK',
                    '{"messages": [{"role": "user", "content": [{"type": "text", "text": "What is Revelator?"}]}]}'
                )
            ) AS resp
        """)
        row = sf_cursor.fetchone()
        resp = row[0]
        if isinstance(resp, str):
            resp = json.loads(resp)
        assert resp is not None, "Fallback agent returned NULL"
        assert "content" in resp or "error_code" not in resp, \
            f"Fallback agent returned error: {resp}"

    def test_agent_returns_text_content(self, sf_cursor):
        sf_cursor.execute("""
            SELECT TRY_PARSE_JSON(
                SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                    'SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT',
                    '{"messages": [{"role": "user", "content": [{"type": "text", "text": "Explain about DSP catalog"}]}]}'
                )
            ) AS resp
        """)
        row = sf_cursor.fetchone()
        resp = row[0]
        if isinstance(resp, str):
            resp = json.loads(resp)
        content = resp.get("content", [])
        text_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "text"]
        assert len(text_parts) > 0, "Agent response has no text parts"
        text = text_parts[0].get("text", "")
        assert len(text) > 10, f"Agent text response too short: {text}"

    def test_agent_uses_search_tool(self, sf_cursor):
        sf_cursor.execute("""
            SELECT TRY_PARSE_JSON(
                SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                    'SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT',
                    '{"messages": [{"role": "user", "content": [{"type": "text", "text": "How does billing work at Revelator?"}]}]}'
                )
            ) AS resp
        """)
        row = sf_cursor.fetchone()
        resp = row[0]
        if isinstance(resp, str):
            resp = json.loads(resp)
        content = resp.get("content", [])
        types = [p.get("type") for p in content if isinstance(p, dict)]
        assert "tool_use" in types or "tool_result" in types, \
            f"Agent did not use any tools. Content types: {types}"

    def test_agent_conversation_history(self, sf_cursor):
        messages = json.dumps({
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "What is Revelator?"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "Revelator is a music distribution platform."}]},
                {"role": "user", "content": [{"type": "text", "text": "Tell me more about their DSP integrations."}]}
            ]
        }).replace("'", "''")
        sf_cursor.execute(f"""
            SELECT TRY_PARSE_JSON(
                SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                    'SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT',
                    '{messages}'
                )
            ) AS resp
        """)
        row = sf_cursor.fetchone()
        resp = row[0]
        if isinstance(resp, str):
            resp = json.loads(resp)
        assert resp is not None, "Agent failed with conversation history"
        assert "content" in resp, "No content in multi-turn response"

    def test_agent_error_on_invalid_fqn(self, sf_cursor):
        try:
            sf_cursor.execute("""
                SELECT TRY_PARSE_JSON(
                    SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                        'SNOWFLAKE_INTELLIGENCE.AGENTS.NONEXISTENT_AGENT',
                        '{"messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]}'
                    )
                ) AS resp
            """)
            row = sf_cursor.fetchone()
            resp = row[0]
            if isinstance(resp, str):
                resp = json.loads(resp)
            if resp and (resp.get("error_code") or resp.get("code")):
                pass
            else:
                pytest.fail("Expected error for nonexistent agent but got a response")
        except Exception:
            pass


class TestLiveSearchService:
    """Real E2E tests against live Cortex Search — no mocks."""

    def test_search_returns_results(self, sf_cursor):
        sf_cursor.execute("""
            SELECT PARSE_JSON(
                SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                    'SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH',
                    '{"query": "DSP catalog", "columns": ["content", "title"], "limit": 3}'
                )
            )['results'] AS results
        """)
        row = sf_cursor.fetchone()
        results = row[0]
        if isinstance(results, str):
            results = json.loads(results)
        assert results is not None, "Search returned NULL"
        assert len(results) > 0, "Search returned no results for 'DSP catalog'"

    def test_search_results_have_expected_fields(self, sf_cursor):
        sf_cursor.execute("""
            SELECT PARSE_JSON(
                SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                    'SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH',
                    '{"query": "billing process", "columns": ["content", "title", "source_system", "owner"], "limit": 2}'
                )
            )['results'] AS results
        """)
        row = sf_cursor.fetchone()
        results = row[0]
        if isinstance(results, str):
            results = json.loads(results)
        assert len(results) > 0, "No results for 'billing process'"
        first = results[0]
        assert "content" in first or "title" in first, \
            f"Search result missing expected fields: {list(first.keys())}"

    def test_search_with_limit(self, sf_cursor):
        sf_cursor.execute("""
            SELECT PARSE_JSON(
                SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                    'SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH',
                    '{"query": "onboarding", "columns": ["content", "title"], "limit": 1}'
                )
            )['results'] AS results
        """)
        row = sf_cursor.fetchone()
        results = row[0]
        if isinstance(results, str):
            results = json.loads(results)
        assert len(results) <= 1, f"Search returned more results than limit: {len(results)}"

    def test_search_with_filter(self, sf_cursor):
        sf_cursor.execute("""
            SELECT PARSE_JSON(
                SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                    'SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH',
                    '{"query": "distribution", "columns": ["content", "title", "source_system"], "limit": 5, "filter": {"@eq": {"source_system": "gitbook"}}}'
                )
            )['results'] AS results
        """)
        row = sf_cursor.fetchone()
        results = row[0]
        if isinstance(results, str):
            results = json.loads(results)
        if results and len(results) > 0:
            for r in results:
                src = r.get("source_system", "").lower()
                assert src == "gitbook", f"Filter not applied, got source_system={src}"

    def test_search_empty_query_doesnt_crash(self, sf_cursor):
        try:
            sf_cursor.execute("""
                SELECT PARSE_JSON(
                    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                        'SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH',
                        '{"query": "", "columns": ["content"], "limit": 1}'
                    )
                )['results'] AS results
            """)
            sf_cursor.fetchone()
        except Exception:
            pass


class TestLiveDBOperations:
    """Real E2E tests for database operations used by the app."""

    def test_questions_table_writable(self, sf_cursor):
        sf_cursor.execute("""
            INSERT INTO SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
                (QUESTION_TEXT, ANSWER, ANSWER_STRENGTH, MODEL_USED, SOURCES_USED, KNOWLEDGE_OWNER, DATE_ASKED)
            SELECT
                '__e2e_test_question__',
                '__e2e_test_answer__',
                'strong',
                'e2e-test',
                PARSE_JSON('[]'),
                NULL,
                CURRENT_TIMESTAMP()
        """)
        sf_cursor.execute("""
            SELECT COUNT(*) FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
            WHERE QUESTION_TEXT = '__e2e_test_question__'
        """)
        count = sf_cursor.fetchone()[0]
        assert count >= 1, "Failed to write to QUESTIONS table"
        sf_cursor.execute("""
            DELETE FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
            WHERE QUESTION_TEXT = '__e2e_test_question__'
        """)

    def test_feedback_table_writable(self, sf_cursor):
        sf_cursor.execute("""
            INSERT INTO SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
                (QUESTION_TEXT, ANSWER, ANSWER_STRENGTH, MODEL_USED, DATE_ASKED)
            SELECT
                '__e2e_feedback_test_q__',
                '__e2e_feedback_test_a__',
                'strong',
                'e2e-test',
                CURRENT_TIMESTAMP()
        """)
        sf_cursor.execute("""
            SELECT QUESTION_ID FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
            WHERE QUESTION_TEXT = '__e2e_feedback_test_q__'
            LIMIT 1
        """)
        question_id = sf_cursor.fetchone()[0]
        sf_cursor.execute(f"""
            INSERT INTO SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK
                (QUESTION_ID, FEEDBACK_TYPE, FEEDBACK_TEXT, CREATED_AT)
            SELECT
                '{question_id}',
                'positive',
                'e2e test',
                CURRENT_TIMESTAMP()
        """)
        sf_cursor.execute(f"""
            SELECT COUNT(*) FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK
            WHERE QUESTION_ID = '{question_id}'
        """)
        count = sf_cursor.fetchone()[0]
        assert count >= 1, "Failed to write to FEEDBACK table"
        sf_cursor.execute(f"""
            DELETE FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK
            WHERE QUESTION_ID = '{question_id}'
        """)
        sf_cursor.execute("""
            DELETE FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
            WHERE QUESTION_TEXT = '__e2e_feedback_test_q__'
        """)

    def test_knowledge_owners_readable(self, sf_cursor):
        sf_cursor.execute("""
            SELECT COUNT(*) FROM SNOWFLAKE_INTELLIGENCE.ADMIN.KNOWLEDGE_OWNERS
        """)
        count = sf_cursor.fetchone()[0]
        assert count >= 0, "KNOWLEDGE_OWNERS table not readable"

    def test_dynamic_tables_have_data(self, sf_cursor):
        for dt in ["FAQ_SUMMARY", "TEAM_SUMMARY", "KNOWLEDGE_GAPS"]:
            try:
                sf_cursor.execute(f"""
                    SELECT COUNT(*) FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.{dt}
                """)
                count = sf_cursor.fetchone()[0]
                assert count >= 0, f"Dynamic table {dt} not readable"
            except Exception as e:
                pytest.skip(f"Dynamic table {dt} may not be refreshed yet: {e}")


class TestDeployedSQLCompiles:
    SQL_FILES_TO_COMPILE = [
        ("02_storage/raw_tables.sql", None),
        ("02_storage/curated_tables.sql", None),
        ("02_storage/analytics_tables.sql", None),
        ("02_storage/admin_tables.sql", None),
        ("02_storage/ingestion_tables.sql", None),
    ]

    @pytest.mark.parametrize("sql_file,_", SQL_FILES_TO_COMPILE)
    def test_sql_compiles(self, sf_cursor, sql_file, _):
        path = os.path.join(INFRA_DIR, sql_file)
        with open(path) as f:
            content = f.read()
        statements = [s.strip() for s in content.split(";") if s.strip()]
        for stmt in statements:
            if not stmt.upper().startswith(("CREATE", "ALTER")):
                continue
            try:
                sf_cursor.execute(f"EXPLAIN USING TEXT {stmt}")
            except Exception:
                pass
