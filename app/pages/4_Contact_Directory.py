import streamlit as st

session = st.session_state.get("session")

AGENT_DIRECTORY = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.AGENT_DIRECTORY"
GROUP_WORKLOAD = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.GROUP_WORKLOAD"

st.title("Contact Directory")

st.subheader("Agent Directory")
search_query = st.text_input("Search agents by name")

try:
    if search_query:
        escaped = search_query.replace("'", "''")
        agents = session.sql(f"""
            SELECT AGENT_NAME, AGENT_EMAIL, AGENT_TYPE, GROUP_NAMES, TICKET_COUNT
            FROM {AGENT_DIRECTORY}
            WHERE LOWER(AGENT_NAME) LIKE LOWER('%{escaped}%')
            ORDER BY AGENT_NAME
        """).to_pandas()
    else:
        agents = session.sql(f"""
            SELECT AGENT_NAME, AGENT_EMAIL, AGENT_TYPE, GROUP_NAMES, TICKET_COUNT
            FROM {AGENT_DIRECTORY}
            ORDER BY AGENT_NAME
        """).to_pandas()
    st.dataframe(agents, use_container_width=True, hide_index=True)
except Exception as e:
    st.error(f"Could not load agent directory: {e}")

st.divider()

st.subheader("Group Workload Summary")
try:
    groups = session.sql(f"""
        SELECT GROUP_NAME, ACTIVE_AGENTS, TOTAL_TICKETS, OPEN_TICKETS, AVG_TICKETS_PER_AGENT
        FROM {GROUP_WORKLOAD}
        ORDER BY TOTAL_TICKETS DESC
    """).to_pandas()
    st.dataframe(groups, use_container_width=True, hide_index=True)
except Exception as e:
    st.error(f"Could not load group workload: {e}")
