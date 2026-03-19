import json
import time
import uuid
import logging

from utils.search_client import search_documents

PRIMARY_AGENT = "SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT"
FALLBACK_AGENT = "SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT_FALLBACK"
FALLBACK_AGENT_2 = "SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT_FALLBACK_2"
KNOWLEDGE_OWNERS_TABLE = "SNOWFLAKE_INTELLIGENCE.ADMIN.KNOWLEDGE_OWNERS"
REQUEST_TRACES_TABLE = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.REQUEST_TRACES"

STRONG_STRENGTHS = {"strong", "medium", "moderate"}
WEAK_STRENGTHS = {"weak"}
NO_ANSWER_STRENGTHS = {"no_answer"}

_REFUSAL_PATTERNS = [
    "i don't have", "i do not have", "i couldn't find", "i could not find",
    "no information", "no relevant", "outside my knowledge", "beyond my scope",
    "not available in", "cannot answer", "can't answer", "i'm unable to",
    "i am unable to", "don't have access", "no data available",
    "i'm not able to", "i am not able to", "outside the scope",
    "not within my", "i cannot provide", "i can't provide",
]

logger = logging.getLogger(__name__)


def _extract_sources_from_raw(raw_response):
    sources = []
    for part in raw_response.get("content", []):
        if not isinstance(part, dict):
            continue
        if part.get("type") == "tool_result":
            tr = part.get("tool_result", {})
            for content_item in tr.get("content", []):
                if isinstance(content_item, dict) and "json" in content_item:
                    for sr in content_item["json"].get("search_results", []):
                        sources.append({
                            "title": sr.get("doc_title", ""),
                            "source_url": sr.get("source_url", ""),
                            "source_system": sr.get("source_system", ""),
                        })
    return sources


def _infer_answer_strength(text, sources):
    text_lower = text.lower().strip()
    if not text_lower or len(text_lower) < 20:
        return "no_answer"
    for pat in _REFUSAL_PATTERNS:
        if pat in text_lower:
            return "no_answer" if len(sources) == 0 else "weak"
    if len(sources) >= 3 and len(text) > 200:
        return "strong"
    if len(sources) >= 1:
        return "medium"
    if len(text) > 100:
        return "weak"
    return "no_answer"


def _call_agent(session, agent_fqn, question, conversation_history=None):
    messages = []
    if conversation_history:
        for msg in conversation_history:
            role = msg["role"]
            text = msg["content"]
            messages.append({
                "role": role,
                "content": [{"type": "text", "text": text}]
            })
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": question}]
    })

    request_body = json.dumps({"messages": messages})
    safe_body = request_body.replace("'", "''")
    safe_agent = agent_fqn.replace("'", "''")

    result = session.sql(f"""
        SELECT TRY_PARSE_JSON(
            SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                '{safe_agent}',
                '{safe_body}'
            )
        ) AS resp
    """).collect()

    resp = result[0]["RESP"]
    if isinstance(resp, str):
        resp = json.loads(resp)

    if resp.get("code") or resp.get("error_code"):
        raise Exception(resp.get("message", "Agent returned an error"))

    return resp


def _parse_agent_response(raw_response, model_used):
    try:
        content_parts = raw_response.get("content", [])
        text_parts = []
        for part in content_parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        text_content = "\n".join(text_parts)

        if not text_content:
            text_content = str(raw_response)

        sources = _extract_sources_from_raw(raw_response)

        try:
            parsed = json.loads(text_content) if isinstance(text_content, str) else text_content
            if isinstance(parsed, dict):
                return {
                    "answer": parsed.get("answer", text_content),
                    "answer_strength": parsed.get("answer_strength", _infer_answer_strength(text_content, sources)),
                    "sources": parsed.get("sources", sources) or sources,
                    "knowledge_owner": parsed.get("knowledge_owner"),
                    "related_questions": parsed.get("related_questions", []),
                    "model_used": model_used,
                }
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "answer": text_content,
            "answer_strength": _infer_answer_strength(text_content, sources),
            "sources": sources,
            "knowledge_owner": None,
            "related_questions": [],
            "model_used": model_used,
        }
    except Exception:
        return {
            "answer": str(raw_response),
            "answer_strength": "unknown",
            "sources": [],
            "knowledge_owner": None,
            "related_questions": [],
            "model_used": model_used,
        }


def _direct_search_fallback(session, question, trace_id):
    try:
        results = search_documents(session, question, limit=3)
        if not results:
            return {
                "answer": "I wasn't able to find a relevant answer. Please contact your knowledge owner or escalate to your team lead.",
                "answer_strength": "no_answer",
                "sources": [],
                "knowledge_owner": None,
                "related_questions": [],
                "model_used": "direct_search",
                "trace_id": trace_id,
            }

        sources = []
        snippets = []
        for r in results:
            if isinstance(r, dict):
                sources.append({
                    "title": r.get("title", "Untitled"),
                    "source_url": r.get("source_url", ""),
                    "source_system": r.get("source_system", ""),
                    "last_updated": r.get("last_updated", ""),
                    "topic": r.get("topic", ""),
                })
                snippets.append(r.get("content", "")[:500])

        answer_text = "Here are the most relevant documents I found:\n\n" + "\n\n---\n\n".join(
            f"**{s['title']}**\n{snippet}" for s, snippet in zip(sources, snippets)
        )

        return {
            "answer": answer_text,
            "answer_strength": "weak",
            "sources": sources,
            "knowledge_owner": None,
            "related_questions": [],
            "model_used": "direct_search",
            "trace_id": trace_id,
        }
    except Exception as e:
        logger.error("Direct search fallback failed: %s (trace_id=%s)", e, trace_id)
        return {
            "answer": "I wasn't able to find a relevant answer. Please contact your knowledge owner or escalate to your team lead.",
            "answer_strength": "no_answer",
            "sources": [],
            "knowledge_owner": None,
            "related_questions": [],
            "model_used": "error",
            "trace_id": trace_id,
        }


def _log_trace(session, trace_data):
    try:
        safe = {k: json.dumps(v).replace("'", "''") if isinstance(v, (list, dict)) else str(v).replace("'", "''") for k, v in trace_data.items()}
        session.sql(f"""
            INSERT INTO {REQUEST_TRACES_TABLE}
            (TRACE_ID, QUESTION_TEXT, INTENT, AGENT_USED, FALLBACK_TRIGGERED,
             FALLBACK_CHAIN, AGENT_LATENCY_MS, TOTAL_LATENCY_MS, CHUNKS_RETRIEVED,
             ANSWER_STRENGTH, ERROR_MESSAGES)
            SELECT
                '{safe.get("trace_id", "")}',
                '{safe.get("question_text", "")}',
                '{safe.get("intent", "")}',
                '{safe.get("agent_used", "")}',
                {safe.get("fallback_triggered", "FALSE")},
                PARSE_JSON('{safe.get("fallback_chain", "[]")}'),
                {safe.get("agent_latency_ms", "0")},
                {safe.get("total_latency_ms", "0")},
                {safe.get("chunks_retrieved", "0")},
                '{safe.get("answer_strength", "unknown")}',
                PARSE_JSON('{safe.get("error_messages", "[]")}')
        """).collect()
    except Exception as e:
        logger.error("Failed to log trace %s: %s", trace_data.get("trace_id"), e)


def ask_agent(session, question, conversation_history=None, intent="unknown"):
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    fallback_chain = []
    error_messages = []

    agents = [
        ("primary", PRIMARY_AGENT),
        ("fallback", FALLBACK_AGENT),
        ("fallback_2", FALLBACK_AGENT_2),
    ]

    for model_used, agent_fqn in agents:
        agent_start = time.time()
        try:
            raw_response = _call_agent(session, agent_fqn, question, conversation_history)
            agent_latency_ms = int((time.time() - agent_start) * 1000)
            result = _parse_agent_response(raw_response, model_used)
            strength = result.get("answer_strength", "unknown")

            if strength in STRONG_STRENGTHS:
                result["response_latency_ms"] = int((time.time() - start_time) * 1000)
                result["trace_id"] = trace_id
                _log_trace(session, {
                    "trace_id": trace_id,
                    "question_text": question[:5000],
                    "intent": intent,
                    "agent_used": model_used,
                    "fallback_triggered": str(len(fallback_chain) > 0).upper(),
                    "fallback_chain": fallback_chain,
                    "agent_latency_ms": agent_latency_ms,
                    "total_latency_ms": result["response_latency_ms"],
                    "chunks_retrieved": len(result.get("sources", [])),
                    "answer_strength": strength,
                    "error_messages": error_messages,
                })
                return result

            if strength in WEAK_STRENGTHS:
                logger.warning("Agent %s returned weak answer (trace_id=%s), trying next", model_used, trace_id)
                fallback_chain.append({"agent": model_used, "strength": strength, "latency_ms": agent_latency_ms})
                continue

            if strength in NO_ANSWER_STRENGTHS:
                logger.warning("Agent %s returned no_answer (trace_id=%s), trying next", model_used, trace_id)
                fallback_chain.append({"agent": model_used, "strength": strength, "latency_ms": agent_latency_ms})
                continue

            result["response_latency_ms"] = int((time.time() - start_time) * 1000)
            result["trace_id"] = trace_id
            _log_trace(session, {
                "trace_id": trace_id,
                "question_text": question[:5000],
                "intent": intent,
                "agent_used": model_used,
                "fallback_triggered": str(len(fallback_chain) > 0).upper(),
                "fallback_chain": fallback_chain,
                "agent_latency_ms": agent_latency_ms,
                "total_latency_ms": result["response_latency_ms"],
                "chunks_retrieved": len(result.get("sources", [])),
                "answer_strength": strength,
                "error_messages": error_messages,
            })
            return result

        except Exception as e:
            agent_latency_ms = int((time.time() - agent_start) * 1000)
            logger.error("Agent %s failed: %s (trace_id=%s)", model_used, e, trace_id)
            error_messages.append({"agent": model_used, "error": str(e)})
            fallback_chain.append({"agent": model_used, "strength": "error", "latency_ms": agent_latency_ms})
            continue

    result = _direct_search_fallback(session, question, trace_id)
    result["response_latency_ms"] = int((time.time() - start_time) * 1000)
    _log_trace(session, {
        "trace_id": trace_id,
        "question_text": question[:5000],
        "intent": intent,
        "agent_used": result.get("model_used", "direct_search"),
        "fallback_triggered": "TRUE",
        "fallback_chain": fallback_chain,
        "agent_latency_ms": 0,
        "total_latency_ms": result["response_latency_ms"],
        "chunks_retrieved": len(result.get("sources", [])),
        "answer_strength": result.get("answer_strength", "no_answer"),
        "error_messages": error_messages,
    })
    return result


def enrich_with_knowledge_owners(session, answer_data):
    sources = answer_data.get("sources", [])
    if not sources:
        return answer_data

    topics = set()
    for source in sources:
        if isinstance(source, dict) and source.get("topic"):
            topics.add(source["topic"])

    if not topics:
        return answer_data

    topic_list = ", ".join(f"'{t.replace(chr(39), chr(39)+chr(39))}'" for t in topics)
    query = f"""
        SELECT NAME, TEAM, EXPERTISE_TOPICS, CONTACT_METHOD, BACKUP_FOR
        FROM {KNOWLEDGE_OWNERS_TABLE}
        WHERE IS_ACTIVE = TRUE
        LIMIT 5
    """

    try:
        rows = session.sql(query).collect()
        if rows:
            owner_row = rows[0]
            answer_data["knowledge_owner"] = {
                "primary_owner": owner_row["NAME"],
                "backup_owner": owner_row["BACKUP_FOR"] or "N/A",
                "contact": owner_row["CONTACT_METHOD"] or "N/A",
                "team": owner_row["TEAM"],
            }
    except Exception:
        pass

    return answer_data
