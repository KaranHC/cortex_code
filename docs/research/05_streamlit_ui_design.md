# Research: Streamlit in Snowflake UI
## Agent 5 Output — Comprehensive Findings

---

## Streamlit in Snowflake (SiS) Overview

Streamlit in Snowflake allows building and deploying interactive data apps directly within the Snowflake platform. Apps run inside Snowflake's security perimeter and inherit RBAC.

### Key Capabilities
- **Multi-page apps**: Using `pages/` directory structure
- **Chat interface**: `st.chat_input()`, `st.chat_message()` for conversational UI
- **File upload**: `st.file_uploader()` for admin document uploads
- **Session state**: `st.session_state` for conversation history
- **User context**: `st.experimental_user` for role-based access
- **Direct DB access**: `get_active_session()` for Snowpark queries
- **Cortex integration**: Call Cortex Agent and Search from within the app

### Limitations
- No custom CSS injection (limited styling)
- No external API calls from frontend (use stored procedures)
- File uploads limited in size
- No background jobs from Streamlit (use Tasks instead)
- packages must be from Snowflake's Anaconda channel

---

## Creating a SiS Application

### SQL Method

```sql
CREATE OR REPLACE STREAMLIT REVSEARCH.APP.KNOWLEDGE_ASSISTANT
    ROOT_LOCATION = '@REVSEARCH.APP.STREAMLIT_STAGE'
    MAIN_FILE = 'main.py'
    QUERY_WAREHOUSE = REVSEARCH_APP_WH
    COMMENT = 'Internal Knowledge Assistant - RevSearch';
```

### Stage Setup

```sql
CREATE OR REPLACE STAGE REVSEARCH.APP.STREAMLIT_STAGE
    DIRECTORY = (ENABLE = TRUE)
    COMMENT = 'Streamlit application files';

-- Upload files
PUT file:///path/to/main.py @REVSEARCH.APP.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT file:///path/to/pages/1_Ask.py @REVSEARCH.APP.STREAMLIT_STAGE/pages/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT file:///path/to/environment.yml @REVSEARCH.APP.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

### environment.yml

```yaml
name: revsearch
channels:
  - snowflake
dependencies:
  - snowflake-snowpark-python
  - snowflake-core
  - streamlit
  - pandas
```

---

## Multi-Page App Structure

```
@REVSEARCH.APP.STREAMLIT_STAGE/
├── main.py                    # Entry point (Page 1: Ask)
├── pages/
│   ├── 2_FAQ_Dashboard.py     # Page 2
│   └── 3_Admin_Panel.py       # Page 3
└── environment.yml
```

SiS auto-discovers pages in `pages/` directory and creates sidebar navigation.

---

## Chat Interface Implementation

### Core Pattern

```python
import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.core import Root
import json

session = get_active_session()

st.title("Knowledge Assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
if prompt := st.chat_input("Ask a question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching..."):
            root = Root(session)
            agent = root.databases["REVSEARCH"].schemas["AGENTS"].cortex_agents["KNOWLEDGE_ASSISTANT"]
            response = agent.complete(
                messages=[{"role": "user", "content": prompt}]
            )
            answer = response.message.content
            st.markdown(answer)
    
    st.session_state.messages.append({"role": "assistant", "content": answer})
```

---

## Structured Response Display

### Answer Strength Badges

```python
def show_strength_badge(strength):
    colors = {
        "strong": "🟢",
        "medium": "🟡", 
        "weak": "🟠",
        "no_answer": "🔴"
    }
    labels = {
        "strong": "Strong — Well-documented answer",
        "medium": "Medium — Partial documentation",
        "weak": "Weak — Limited documentation",
        "no_answer": "No Answer — Documentation insufficient"
    }
    icon = colors.get(strength, "⚪")
    label = labels.get(strength, "Unknown")
    st.markdown(f"### {icon} Answer Strength: {strength.upper()}")
    st.caption(label)
```

### Source Cards

```python
def show_sources(sources):
    with st.expander(f"📄 Supporting Sources ({len(sources)})", expanded=True):
        for i, src in enumerate(sources):
            col1, col2 = st.columns([4, 1])
            with col1:
                title = src.get("title", "Untitled")
                url = src.get("source_url", "")
                if url:
                    st.markdown(f"**[{title}]({url})**")
                else:
                    st.markdown(f"**{title}**")
                system = src.get("source_system", "unknown")
                updated = src.get("last_updated", "unknown")
                st.caption(f"Source: {system} | Last updated: {updated}")
            with col2:
                st.caption(src.get("relevance_note", ""))
            if i < len(sources) - 1:
                st.divider()
```

### Knowledge Owner Card

```python
def show_knowledge_owner(ko):
    if not ko.get("needed"):
        return
    st.warning("📋 Documentation may be incomplete. Reach out to the knowledge owner:")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Primary Owner", ko.get("primary_owner", "Unknown"))
    with col2:
        st.metric("Backup Owner", ko.get("backup_owner", "Unknown"))
    with col3:
        contact = ko.get("contact", "Unknown")
        st.metric("Contact", contact)
    if ko.get("reason"):
        st.info(f"Reason: {ko['reason']}")
```

### Related Questions as Clickable Chips

```python
def show_related_questions(questions):
    if not questions:
        return
    st.markdown("**💡 Related Questions:**")
    cols = st.columns(len(questions))
    for i, q in enumerate(questions):
        with cols[i]:
            if st.button(q, key=f"rq_{i}"):
                st.session_state.pending_question = q
                st.rerun()
```

---

## Role-Based Access Control

```python
import streamlit as st

current_user = st.experimental_user

def check_admin():
    """Check if current user has admin role."""
    session = get_active_session()
    result = session.sql("""
        SELECT COUNT(*) AS is_admin 
        FROM INFORMATION_SCHEMA.APPLICABLE_ROLES
        WHERE ROLE_NAME = 'REVSEARCH_ADMIN'
    """).collect()
    return result[0]["IS_ADMIN"] > 0

# In Admin Panel page:
if not check_admin():
    st.error("Access denied. Admin role required.")
    st.stop()
```

---

## File Upload for Admin

```python
uploaded_file = st.file_uploader("Upload document", type=["txt", "md", "pdf"])
if uploaded_file:
    content = uploaded_file.read().decode("utf-8")
    # Process and insert into DOCUMENTS table
    st.success(f"Uploaded: {uploaded_file.name} ({len(content)} characters)")
```

Note: PDF parsing requires additional handling. For MVP, support TXT and MD files. Add PDF support later via `CORTEX.PARSE_DOCUMENT()`.

---

## Dashboard Widgets

### KPI Metrics Row

```python
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Questions", "1,234", delta="+56 this week")
with col2:
    st.metric("Strong Answer Rate", "72%", delta="+3%")
with col3:
    st.metric("Knowledge Gaps", "18", delta="-4")
with col4:
    st.metric("Avg Response Time", "4.2s", delta="-0.8s")
```

### Charts

```python
import pandas as pd

# Bar chart
st.bar_chart(df.set_index("team")["question_count"])

# Line chart
st.line_chart(df.set_index("date")["daily_questions"])

# Altair for more control (available in SiS)
import altair as alt
chart = alt.Chart(df).mark_bar().encode(
    x='team',
    y='questions',
    color='answer_strength'
)
st.altair_chart(chart, use_container_width=True)
```

---

## Session State Best Practices

1. **Initialize once**: Check `if "key" not in st.session_state` before setting
2. **Conversation history**: Store as list of dicts in `st.session_state.messages`
3. **Clear history**: Provide a "New Conversation" button that resets state
4. **Limit history size**: Keep last 10 turns to avoid memory issues
5. **Cache queries**: Use `@st.cache_data(ttl=300)` for dashboard queries

```python
@st.cache_data(ttl=300)
def get_top_questions():
    return session.sql("SELECT * FROM REVSEARCH.ANALYTICS.FAQ_SUMMARY ORDER BY ask_count DESC LIMIT 20").to_pandas()
```

---

## Performance Tips

1. **Cache expensive queries**: Use `@st.cache_data` with TTL
2. **Lazy loading**: Don't query all data on page load
3. **XSMALL warehouse**: Sufficient for Streamlit app (queries are lightweight)
4. **Minimize reruns**: Use `st.form()` for multi-input submissions
5. **Pagination**: Use LIMIT/OFFSET for large result sets
