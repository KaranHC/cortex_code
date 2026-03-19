import os
import pytest
import snowflake.connector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFRA_DIR = os.path.join(PROJECT_ROOT, "infra")
APP_DIR = os.path.join(PROJECT_ROOT, "app")


@pytest.fixture(scope="session")
def sf_connection():
    conn = snowflake.connector.connect(
        connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or "VVA53450"
    )
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def sf_cursor(sf_connection):
    cur = sf_connection.cursor()
    yield cur
    cur.close()
