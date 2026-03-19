"""
Static validation tests for infra SQL files and app configuration.
These run without a Snowflake connection — pure file/content checks.
"""
import os
import re
import glob
import yaml
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFRA_DIR = os.path.join(PROJECT_ROOT, "infra")
APP_DIR = os.path.join(PROJECT_ROOT, "app")

EXPECTED_FOLDERS = [
    "01_foundation",
    "02_storage",
    "03_ingestion",
    "04_intelligence",
    "05_monitoring",
]

EXPECTED_FILES = {
    "01_foundation": ["schemas.sql", "roles.sql", "security.sql", "permissions.sql"],
    "02_storage": ["raw_tables.sql", "curated_tables.sql", "analytics_tables.sql",
                    "admin_tables.sql", "ingestion_tables.sql"],
    "03_ingestion": ["ingest_gitbook.sql", "process_documents.sql",
                      "classify_documents.sql", "tasks.sql"],
    "04_intelligence": ["cortex_search.sql", "cortex_agents.sql"],
    "05_monitoring": ["dynamic_tables.sql", "alerts.sql"],
}


class TestInfraStructure:
    def test_no_phase_directories_remain(self):
        phase_dirs = glob.glob(os.path.join(INFRA_DIR, "phase*"))
        assert phase_dirs == [], f"Leftover phase directories found: {phase_dirs}"

    def test_expected_folders_exist(self):
        for folder in EXPECTED_FOLDERS:
            path = os.path.join(INFRA_DIR, folder)
            assert os.path.isdir(path), f"Missing folder: {folder}"

    def test_expected_files_exist(self):
        for folder, files in EXPECTED_FILES.items():
            for f in files:
                path = os.path.join(INFRA_DIR, folder, f)
                assert os.path.isfile(path), f"Missing file: {folder}/{f}"

    def test_no_unexpected_folders(self):
        actual = [d for d in os.listdir(INFRA_DIR)
                  if os.path.isdir(os.path.join(INFRA_DIR, d)) and not d.startswith(".")]
        for d in actual:
            assert d in EXPECTED_FOLDERS, f"Unexpected folder: {d}"

    def test_total_sql_file_count(self):
        sql_files = glob.glob(os.path.join(INFRA_DIR, "**", "*.sql"), recursive=True)
        assert len(sql_files) == 17, f"Expected 17 SQL files, found {len(sql_files)}"


class TestProcessDocumentsSQL:
    @pytest.fixture(autouse=True)
    def load_file(self):
        path = os.path.join(INFRA_DIR, "03_ingestion", "process_documents.sql")
        with open(path) as f:
            self.content = f.read()

    def test_no_row_get_pattern(self):
        assert "row.get(" not in self.content, \
            "process_documents.sql still uses row.get() — must use row['KEY'] with fallback"

    def test_uses_direct_key_access_with_fallback(self):
        assert 'row["PATH"] if row["PATH"]' in self.content, \
            "Missing safe field access pattern for PATH"
        assert 'row["SPACE_TITLE"] if row["SPACE_TITLE"]' in self.content, \
            "Missing safe field access pattern for SPACE_TITLE"

    def test_null_timestamp_handling(self):
        assert 'row["CREATED_AT"] if row["CREATED_AT"] else None' in self.content, \
            "Missing NULL handling for CREATED_AT"
        assert 'row["UPDATED_AT"] if row["UPDATED_AT"] else None' in self.content, \
            "Missing NULL handling for UPDATED_AT"

    def test_uses_insert_select_not_insert_values(self):
        lines = self.content.split("\n")
        insert_lines = [i for i, l in enumerate(lines) if "INSERT INTO" in l]
        for idx in insert_lines:
            subsequent = "\n".join(lines[idx:idx+10])
            assert "VALUES" not in subsequent, \
                f"INSERT near line {idx+1} uses VALUES instead of SELECT"
            assert "SELECT" in subsequent or "select" in subsequent, \
                f"INSERT near line {idx+1} missing SELECT clause"

    def test_conditional_timestamp_expressions(self):
        assert "created_expr" in self.content, "Missing created_expr conditional"
        assert "updated_expr" in self.content, "Missing updated_expr conditional"
        assert 'CURRENT_TIMESTAMP()' in self.content, \
            "Missing CURRENT_TIMESTAMP() fallback for NULL timestamps"


class TestCortexAgentsSQL:
    @pytest.fixture(autouse=True)
    def load_file(self):
        path = os.path.join(INFRA_DIR, "04_intelligence", "cortex_agents.sql")
        with open(path) as f:
            self.content = f.read()

    def test_no_create_cortex_agent_syntax(self):
        assert "CREATE CORTEX AGENT" not in self.content.upper(), \
            "cortex_agents.sql uses wrong 'CREATE CORTEX AGENT' syntax"

    def test_uses_create_agent_from_specification(self):
        assert "CREATE OR REPLACE AGENT" in self.content, \
            "Missing 'CREATE OR REPLACE AGENT' statement"
        assert "FROM SPECIFICATION $$" in self.content, \
            "Missing 'FROM SPECIFICATION $$' block"

    def test_has_all_agents(self):
        assert "KNOWLEDGE_ASSISTANT_FALLBACK" in self.content
        assert "KNOWLEDGE_ASSISTANT_FALLBACK_2" in self.content
        assert self.content.count("CREATE OR REPLACE AGENT") == 3, \
            "Expected exactly 3 agent definitions"

    def test_spec_has_required_fields(self):
        assert "models:" in self.content
        assert "orchestration:" in self.content
        assert "instructions:" in self.content
        assert "tools:" in self.content
        assert "tool_resources:" in self.content
        assert "cortex_search" in self.content

    def test_correct_models(self):
        assert "claude-sonnet-4-6" in self.content, "Primary agent should use claude-sonnet-4-6"
        assert "claude-haiku-4-5" in self.content, "Fallback agent should use claude-haiku-4-5"
        assert "openai-gpt-5.2" in self.content, "Fallback 2 agent should use openai-gpt-5.2"

    def test_no_disallowed_models(self):
        assert "llama3.3-70b" not in self.content, "llama3.3-70b is not allowed for agent requests"
        assert "claude-3.5-sonnet" not in self.content, "claude-3.5-sonnet uses wrong format (should be claude-3-5-sonnet)"

    def test_references_correct_search_service(self):
        assert "SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH" in self.content


class TestDynamicTablesSQL:
    @pytest.fixture(autouse=True)
    def load_file(self):
        path = os.path.join(INFRA_DIR, "05_monitoring", "dynamic_tables.sql")
        with open(path) as f:
            self.content = f.read()

    def test_no_cortex_cost_tracking(self):
        assert "CORTEX_COST_TRACKING" not in self.content, \
            "dynamic_tables.sql still contains broken CORTEX_COST_TRACKING"

    def test_has_exactly_three_dynamic_tables(self):
        count = self.content.count("CREATE OR REPLACE DYNAMIC TABLE")
        assert count == 3, f"Expected 3 dynamic tables, found {count}"

    def test_expected_dynamic_tables_present(self):
        assert "FAQ_SUMMARY" in self.content
        assert "TEAM_SUMMARY" in self.content
        assert "KNOWLEDGE_GAPS" in self.content

    def test_no_metering_daily_history_reference(self):
        assert "METERING_DAILY_HISTORY" not in self.content, \
            "Should not reference METERING_DAILY_HISTORY (removed with CORTEX_COST_TRACKING)"


class TestEnvironmentYml:
    @pytest.fixture(autouse=True)
    def load_file(self):
        path = os.path.join(APP_DIR, "environment.yml")
        with open(path) as f:
            self.content = f.read()
        self.parsed = yaml.safe_load(self.content)

    def test_valid_yaml(self):
        assert self.parsed is not None

    def test_has_required_keys(self):
        assert "name" in self.parsed
        assert "channels" in self.parsed
        assert "dependencies" in self.parsed

    def test_channel_is_snowflake(self):
        assert "snowflake" in self.parsed["channels"]

    def test_no_version_specifiers_in_deps(self):
        for dep in self.parsed["dependencies"]:
            assert ">=" not in str(dep), \
                f"Invalid version specifier '>=' in dependency: {dep}"
            assert "<=" not in str(dep), \
                f"Invalid version specifier '<=' in dependency: {dep}"
            assert "==" not in str(dep), \
                f"Invalid version specifier '==' in dependency: {dep}"

    def test_no_bare_snowflake_dependency(self):
        deps = self.parsed["dependencies"]
        for dep in deps:
            assert dep != "snowflake", \
                "'snowflake' is not a valid conda package — use 'snowflake-snowpark-python' or 'snowflake.core'"

    def test_has_required_dependencies(self):
        deps = self.parsed["dependencies"]
        assert "snowflake-snowpark-python" in deps
        assert "streamlit" in deps

    def test_no_snowflake_core_dependency(self):
        deps = self.parsed["dependencies"]
        assert "snowflake.core" not in deps, \
            "snowflake.core should not be in environment.yml — app uses pure SQL APIs"

    def test_anaconda_naming_compliance(self):
        allowed_pattern = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
        for dep in self.parsed["dependencies"]:
            dep_str = str(dep)
            assert allowed_pattern.match(dep_str), \
                f"Dependency '{dep_str}' violates Anaconda naming rules (lowercase, numbers, .-_ only)"


class TestAppImports:
    def test_no_snowflake_core_imports_anywhere(self):
        for root, _, files in os.walk(APP_DIR):
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    with open(path) as fh:
                        content = fh.read()
                    assert "snowflake.core" not in content, \
                        f"{path} imports snowflake.core — app must use pure SQL APIs"

    def test_agent_client_uses_sql_api(self):
        path = os.path.join(APP_DIR, "utils", "agent_client.py")
        with open(path) as f:
            content = f.read()
        assert "DATA_AGENT_RUN" in content, \
            "agent_client.py must use SNOWFLAKE.CORTEX.DATA_AGENT_RUN SQL function"
        assert "from snowflake.core" not in content, \
            "agent_client.py must not import from snowflake.core"

    def test_search_client_uses_sql_api(self):
        path = os.path.join(APP_DIR, "utils", "search_client.py")
        with open(path) as f:
            content = f.read()
        assert "SEARCH_PREVIEW" in content, \
            "search_client.py must use SNOWFLAKE.CORTEX.SEARCH_PREVIEW SQL function"
        assert "from snowflake.core" not in content, \
            "search_client.py must not import from snowflake.core"

    def test_agent_client_has_fallback(self):
        path = os.path.join(APP_DIR, "utils", "agent_client.py")
        with open(path) as f:
            content = f.read()
        assert "FALLBACK" in content, \
            "agent_client.py must have fallback agent support"
        assert "PRIMARY_AGENT" in content
        assert "FALLBACK_AGENT" in content
        assert "FALLBACK_AGENT_2" in content

    def test_no_wildcard_imports(self):
        for root, _, files in os.walk(APP_DIR):
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    with open(path) as fh:
                        content = fh.read()
                    assert "from * import" not in content and "import *" not in content, \
                        f"Wildcard import found in {path}"


class TestAllSQLFilesBasicValidity:
    def get_all_sql_files(self):
        return glob.glob(os.path.join(INFRA_DIR, "**", "*.sql"), recursive=True)

    def test_all_sql_files_non_empty(self):
        for path in self.get_all_sql_files():
            size = os.path.getsize(path)
            assert size > 0, f"Empty SQL file: {path}"

    def test_all_sql_files_have_create_statement(self):
        for path in self.get_all_sql_files():
            with open(path) as f:
                content = f.read().upper()
            has_create = "CREATE" in content
            has_use = "USE" in content
            has_alter = "ALTER" in content
            assert has_create or has_use or has_alter, \
                f"SQL file has no CREATE/USE/ALTER: {path}"

    def test_no_sql_files_reference_nonexistent_schemas(self):
        valid_schemas = {"RAW", "CURATED", "SEARCH", "AGENTS", "ANALYTICS",
                         "ADMIN", "INGESTION", "APP"}
        for path in self.get_all_sql_files():
            with open(path) as f:
                content = f.read()
            refs = re.findall(r'SNOWFLAKE_INTELLIGENCE\.(\w+)\.', content)
            for ref in refs:
                assert ref.upper() in valid_schemas, \
                    f"Reference to unknown schema '{ref}' in {path}"
