import json
import re
import streamlit as st
from datetime import datetime, timedelta
from utils.agent_client import ask_agent, enrich_with_knowledge_owners
from utils.db_utils import log_question, log_feedback

session = st.session_state.get("session")

if "conversation_history" not in st.session_state:
    st.session_state["conversation_history"] = []
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "pending_question" not in st.session_state:
    st.session_state["pending_question"] = None
if "last_question_id" not in st.session_state:
    st.session_state["last_question_id"] = None

st.title("Ask a Question")
st.caption("Get answers from your organization's knowledge base")

GREETING_PATTERNS = re.compile(
    r"^(hi|hello|hey|good morning|good afternoon|good evening|howdy|greetings|sup|yo)\b",
    re.IGNORECASE,
)
OFF_TOPIC_PATTERNS = re.compile(
    r"^(tell me a joke|what is the meaning of life|write me a poem|sing|"
    r"who is the president|what is the weather|play a game)",
    re.IGNORECASE,
)
INTENT_PATTERNS = [
    ("people_lookup", re.compile(r"\b(who owns|who knows|who is responsible|contact for|owner of)\b", re.IGNORECASE)),
    ("comparison", re.compile(r"\b(compare|difference between|vs\.?|versus)\b", re.IGNORECASE)),
    ("how_to", re.compile(r"\b(how to|how do i|how can i|steps to|guide for)\b", re.IGNORECASE)),
    ("factual", re.compile(r"\b(what is|what are|define|explain|describe)\b", re.IGNORECASE)),
]


def classify_intent(question):
    if GREETING_PATTERNS.match(question.strip()):
        return "greeting"
    if OFF_TOPIC_PATTERNS.match(question.strip()):
        return "off_topic"
    for intent, pattern in INTENT_PATTERNS:
        if pattern.search(question):
            return intent
    return "general"


@st.cache_data(ttl=300, show_spinner=False)
def cached_ask_agent(_session_id, question, conversation_history_key, intent):
    answer_data = ask_agent(session, question, st.session_state.get("conversation_history"), intent=intent)
    return enrich_with_knowledge_owners(session, answer_data)


def display_answer(answer_data):
    st.markdown(answer_data.get("answer", ""))

    strength = answer_data.get("answer_strength", "unknown")
    strength_colors = {
        "strong": "green",
        "moderate": "orange",
        "weak": "red",
        "no_answer": "red",
        "unknown": "gray",
    }
    color = strength_colors.get(strength, "gray")
    st.markdown(f"**Answer Confidence:** :{color}[{strength.replace('_', ' ').title()}]")

    if strength == "weak":
        st.warning("This answer has low confidence. Consider verifying with a knowledge owner below or rephrasing your question.")

    if strength == "no_answer":
        st.error("We couldn't find a reliable answer. Please reach out to the knowledge owner listed below or escalate to your team lead.")

    if answer_data.get("model_used") == "fallback":
        st.warning("This response was generated using the fallback model.")

    if answer_data.get("model_used") == "direct_search":
        st.info("This response was generated from direct document search after all agents were unavailable.")

    sources = answer_data.get("sources", [])
    if sources:
        with st.expander(f"Sources ({len(sources)})"):
            for i, source in enumerate(sources):
                if isinstance(source, dict):
                    title = source.get("title", f"Source {i + 1}")
                    url = source.get("source_url", "")
                    last_updated = source.get("last_updated", "")
                    source_system = (source.get("source_system") or "").lower()

                    if source_system == "freshdesk":
                        badge_color = "green"
                        badge_icon = "\U0001F3AB"
                    else:
                        badge_color = "blue"
                        badge_icon = "\U0001F4D6"

                    if url:
                        st.markdown(f"{badge_icon} **[{title}]({url})**")
                    else:
                        st.markdown(f"{badge_icon} **{title}**")

                    if last_updated:
                        try:
                            updated_date = datetime.fromisoformat(str(last_updated).replace("Z", "+00:00"))
                            days_old = (datetime.now(updated_date.tzinfo) - updated_date).days if updated_date.tzinfo else (datetime.now() - updated_date).days
                            if days_old > 90:
                                st.warning(f"This document was last updated {days_old} days ago and may be stale.")
                        except (ValueError, TypeError):
                            pass

                    if source_system:
                        st.markdown(f":{badge_color}[{source_system.title()}]")
                else:
                    st.markdown(f"- {source}")

    knowledge_owner = answer_data.get("knowledge_owner")
    if knowledge_owner and isinstance(knowledge_owner, dict):
        with st.container(border=True):
            st.subheader("Knowledge Owner")
            cols = st.columns(3)
            cols[0].metric("Primary", knowledge_owner.get("primary_owner", "N/A"))
            cols[1].metric("Backup", knowledge_owner.get("backup_owner", "N/A"))
            cols[2].metric("Contact", knowledge_owner.get("contact", "N/A"))
    elif strength in ("weak", "no_answer"):
        st.info("No knowledge owner found for this topic. Please escalate to your team lead.")

    related = answer_data.get("related_questions", [])
    if related:
        st.markdown("**Related Questions:**")
        for rq in related:
            if st.button(rq, key=f"rq_{rq}"):
                st.session_state["pending_question"] = rq
                st.rerun()


def handle_feedback(question_id, feedback_type):
    if question_id:
        try:
            user_name = session.sql("SELECT CURRENT_USER()").collect()[0][0]
        except Exception:
            user_name = "unknown"
        log_feedback(session, question_id, feedback_type, user_name)
        st.toast(f"{'Positive' if feedback_type == 'positive' else 'Negative'} feedback recorded. Thank you!")


for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and isinstance(msg.get("data"), dict):
            display_answer(msg["data"])
        else:
            st.markdown(msg["content"])

question = st.chat_input("Ask a question about your organization's knowledge...")

if st.session_state.get("pending_question"):
    question = st.session_state["pending_question"]
    st.session_state["pending_question"] = None

if question:
    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    intent = classify_intent(question)

    if intent == "greeting":
        answer_data = {
            "answer": "Hello! I'm your organization's knowledge assistant. Ask me anything about your company's processes, tools, or documentation.",
            "answer_strength": "strong",
            "sources": [],
            "knowledge_owner": None,
            "related_questions": [],
            "model_used": "intent_router",
            "response_latency_ms": 0,
        }
        with st.chat_message("assistant"):
            display_answer(answer_data)
            st.session_state["messages"].append({
                "role": "assistant",
                "content": answer_data["answer"],
                "data": answer_data,
            })
    elif intent == "off_topic":
        answer_data = {
            "answer": "I'm designed to help with questions about your organization's knowledge base. I can't help with that topic, but feel free to ask me about company processes, tools, or documentation!",
            "answer_strength": "no_answer",
            "sources": [],
            "knowledge_owner": None,
            "related_questions": [],
            "model_used": "intent_router",
            "response_latency_ms": 0,
        }
        with st.chat_message("assistant"):
            display_answer(answer_data)
            st.session_state["messages"].append({
                "role": "assistant",
                "content": answer_data["answer"],
                "data": answer_data,
            })
    else:
        with st.chat_message("assistant"):
            with st.spinner("Searching knowledge base..."):
                conversation_key = json.dumps(st.session_state["conversation_history"]) if st.session_state["conversation_history"] else ""
                answer_data = cached_ask_agent(id(session), question, conversation_key, intent)

                elapsed_ms = answer_data.get("response_latency_ms", 0)
                question_id = log_question(session, question, answer_data, elapsed_ms)
                st.session_state["last_question_id"] = question_id

                display_answer(answer_data)

                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": answer_data.get("answer", ""),
                    "data": answer_data,
                })
                st.session_state["conversation_history"].append({"role": "user", "content": question})
                st.session_state["conversation_history"].append({"role": "assistant", "content": answer_data.get("answer", "")})

if st.session_state.get("last_question_id"):
    col1, col2, _ = st.columns([1, 1, 8])
    with col1:
        if st.button("\U0001F44D", key="thumbs_up"):
            handle_feedback(st.session_state["last_question_id"], "positive")
    with col2:
        if st.button("\U0001F44E", key="thumbs_down"):
            handle_feedback(st.session_state["last_question_id"], "negative")
