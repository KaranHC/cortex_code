import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="RevSearch", layout="wide")

session = get_active_session()

ask_page = st.Page("pages/1_Ask_a_Question.py", title="Ask a Question", icon="\U0001F50D")
faq_page = st.Page("pages/2_FAQ_Dashboard.py", title="FAQ Dashboard", icon="\U0001F4CA")
freshdesk_page = st.Page("pages/3_Freshdesk_Analytics.py", title="Freshdesk Analytics", icon="\U0001F3AB")
contacts_page = st.Page("pages/4_Contact_Directory.py", title="Contact Directory", icon="\U0001F4C7")
admin_page = st.Page("pages/5_Admin_Panel.py", title="Admin Panel", icon="\U00002699")

pg = st.navigation([ask_page, faq_page, freshdesk_page, contacts_page, admin_page])

if "session" not in st.session_state:
    st.session_state["session"] = session

pg.run()
