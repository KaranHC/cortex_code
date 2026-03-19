import streamlit as st

session = st.session_state.get("session")

TICKET_TRENDS = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.TICKET_TRENDS"
SLA_COMPLIANCE = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.SLA_COMPLIANCE"
AGENT_PERFORMANCE = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.AGENT_PERFORMANCE_V"
CUSTOMER_INSIGHTS = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.CUSTOMER_INSIGHTS"

st.title("Freshdesk Analytics")

st.subheader("SLA Compliance")
try:
    sla = session.sql(f"""
        SELECT
            COUNT(*) AS TOTAL_TICKETS,
            COUNT_IF(IS_OVERDUE = TRUE) AS OVERDUE_TICKETS,
            ROUND(COUNT_IF(IS_OVERDUE = FALSE) * 100.0 / NULLIF(COUNT(*), 0), 1) AS ON_TIME_PCT
        FROM {SLA_COMPLIANCE}
    """).collect()[0]
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tickets", sla["TOTAL_TICKETS"])
    col2.metric("Overdue Tickets", sla["OVERDUE_TICKETS"])
    col3.metric("On-Time %", f"{sla['ON_TIME_PCT']}%")
except Exception as e:
    st.error(f"Could not load SLA data: {e}")

st.divider()

st.subheader("Ticket Volume Trends")
try:
    trends = session.sql(f"""
        SELECT WEEK, TOTAL_TICKETS, OPEN_TICKETS, RESOLVED_TICKETS
        FROM {TICKET_TRENDS}
        ORDER BY WEEK
    """).to_pandas()
    trends = trends.set_index("WEEK")
    st.line_chart(trends)
except Exception as e:
    st.error(f"Could not load ticket trends: {e}")

st.divider()

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Top Agents by Tickets Handled")
    try:
        agents = session.sql(f"""
            SELECT AGENT_NAME, TICKETS_HANDLED, TICKETS_RESOLVED,
                   ROUND(AVG_RESOLUTION_HOURS, 1) AS AVG_RESOLUTION_HOURS
            FROM {AGENT_PERFORMANCE}
            ORDER BY TICKETS_HANDLED DESC
            LIMIT 20
        """).to_pandas()
        st.dataframe(agents, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not load agent performance: {e}")

with col_right:
    st.subheader("Top Companies by Ticket Count")
    try:
        customers = session.sql(f"""
            SELECT COMPANY_NAME, TOTAL_TICKETS, OPEN_TICKETS, TOTAL_CONTACTS
            FROM {CUSTOMER_INSIGHTS}
            ORDER BY TOTAL_TICKETS DESC
            LIMIT 20
        """).to_pandas()
        st.dataframe(customers, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not load customer insights: {e}")
