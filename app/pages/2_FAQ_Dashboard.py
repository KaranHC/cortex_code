import streamlit as st

session = st.session_state.get("session")

QUESTIONS_TABLE = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS"

st.title("FAQ Dashboard")

try:
    total_questions = session.sql(f"SELECT COUNT(*) AS CNT FROM {QUESTIONS_TABLE}").collect()[0]["CNT"]
except Exception:
    total_questions = 0

try:
    strong_rate_row = session.sql(f"""
        SELECT
            ROUND(COUNT_IF(ANSWER_STRENGTH = 'strong') * 100.0 / NULLIF(COUNT(*), 0), 1) AS STRONG_RATE
        FROM {QUESTIONS_TABLE}
    """).collect()[0]
    strong_rate = strong_rate_row["STRONG_RATE"] or 0
except Exception:
    strong_rate = 0

try:
    weak_count = session.sql(f"""
        SELECT COUNT(*) AS CNT FROM {QUESTIONS_TABLE}
        WHERE ANSWER_STRENGTH IN ('weak', 'no_answer')
    """).collect()[0]["CNT"]
except Exception:
    weak_count = 0

try:
    avg_latency = session.sql(f"""
        SELECT ROUND(AVG(RESPONSE_LATENCY_MS), 0) AS AVG_MS FROM {QUESTIONS_TABLE}
    """).collect()[0]["AVG_MS"] or 0
except Exception:
    avg_latency = 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Questions", total_questions)
col2.metric("Strong Answer Rate", f"{strong_rate}%")
col3.metric("Weak/No Answers", weak_count)
col4.metric("Avg Response Time", f"{avg_latency}ms")

st.divider()

st.subheader("Top 20 Most-Asked Questions")
try:
    top_questions = session.sql(f"""
        SELECT QUESTION_TEXT, COUNT(*) AS TIMES_ASKED, MAX(ANSWER_STRENGTH) AS LAST_STRENGTH
        FROM {QUESTIONS_TABLE}
        GROUP BY QUESTION_TEXT
        ORDER BY TIMES_ASKED DESC
        LIMIT 20
    """).to_pandas()
    st.dataframe(top_questions, use_container_width=True)
except Exception as e:
    st.error(f"Could not load top questions: {e}")

st.subheader("Recent 20 Questions")
try:
    recent_questions = session.sql(f"""
        SELECT QUESTION_TEXT, ANSWER_STRENGTH, MODEL_USED, RESPONSE_LATENCY_MS, DATE_ASKED
        FROM {QUESTIONS_TABLE}
        ORDER BY DATE_ASKED DESC
        LIMIT 20
    """).to_pandas()
    st.dataframe(recent_questions, use_container_width=True)
except Exception as e:
    st.error(f"Could not load recent questions: {e}")

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Questions by Team")
    try:
        by_team = session.sql(f"""
            SELECT COALESCE(USER_TEAM, 'Unknown') AS TEAM, COUNT(*) AS QUESTION_COUNT
            FROM {QUESTIONS_TABLE}
            GROUP BY USER_TEAM
            ORDER BY QUESTION_COUNT DESC
        """).to_pandas()
        st.bar_chart(by_team.set_index("TEAM"))
    except Exception as e:
        st.error(f"Could not load team data: {e}")

with col_right:
    st.subheader("Answer Strength Distribution")
    try:
        strength_dist = session.sql(f"""
            SELECT ANSWER_STRENGTH, COUNT(*) AS COUNT
            FROM {QUESTIONS_TABLE}
            GROUP BY ANSWER_STRENGTH
            ORDER BY COUNT DESC
        """).to_pandas()
        st.bar_chart(strength_dist.set_index("ANSWER_STRENGTH"))
    except Exception as e:
        st.error(f"Could not load strength distribution: {e}")

st.subheader("Knowledge Gaps")
st.caption("Questions with weak or no answers that may need attention")
try:
    gaps = session.sql(f"""
        SELECT QUESTION_TEXT, ANSWER_STRENGTH, COUNT(*) AS TIMES_ASKED, MAX(DATE_ASKED) AS LAST_ASKED
        FROM {QUESTIONS_TABLE}
        WHERE ANSWER_STRENGTH IN ('weak', 'no_answer')
        GROUP BY QUESTION_TEXT, ANSWER_STRENGTH
        ORDER BY TIMES_ASKED DESC
        LIMIT 20
    """).to_pandas()
    st.dataframe(gaps, use_container_width=True)
except Exception as e:
    st.error(f"Could not load knowledge gaps: {e}")
