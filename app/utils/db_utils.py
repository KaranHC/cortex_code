import json
import uuid

QUESTIONS_TABLE = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS"
FEEDBACK_TABLE = "SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK"
KNOWLEDGE_OWNERS_TABLE = "SNOWFLAKE_INTELLIGENCE.ADMIN.KNOWLEDGE_OWNERS"


def log_question(session, question, answer_data, elapsed_ms):
    question_id = str(uuid.uuid4())
    escaped_question = question.replace("'", "''")
    escaped_answer = answer_data.get("answer", "").replace("'", "''")
    strength = answer_data.get("answer_strength", "unknown").replace("'", "''")
    model_used = answer_data.get("model_used", "unknown").replace("'", "''")
    sources_json = json.dumps(answer_data.get("sources", [])).replace("'", "''")
    ko_json = json.dumps(answer_data.get("knowledge_owner") or {}).replace("'", "''")
    rq_json = json.dumps(answer_data.get("related_questions", [])).replace("'", "''")
    trace_id = str(answer_data.get("trace_id", "")).replace("'", "''")

    sql = f"""
        INSERT INTO {QUESTIONS_TABLE}
        (QUESTION_ID, QUESTION_TEXT, ANSWER, ANSWER_STRENGTH, MODEL_USED, RESPONSE_LATENCY_MS,
         SOURCES_USED, KNOWLEDGE_OWNER, RELATED_QUESTIONS, TRACE_ID, DATE_ASKED)
        SELECT
            '{question_id}',
            '{escaped_question}',
            '{escaped_answer}',
            '{strength}',
            '{model_used}',
            {elapsed_ms},
            PARSE_JSON('{sources_json}'),
            PARSE_JSON('{ko_json}'),
            PARSE_JSON('{rq_json}'),
            '{trace_id}',
            CURRENT_TIMESTAMP()
    """
    session.sql(sql).collect()
    return question_id


def log_feedback(session, question_id, feedback_type, user_name, feedback_text=None):
    escaped_user = user_name.replace("'", "''")
    escaped_text = feedback_text.replace("'", "''") if feedback_text else ""
    text_value = f"'{escaped_text}'" if feedback_text else "NULL"
    escaped_qid = str(question_id).replace("'", "''")

    sql = f"""
        INSERT INTO {FEEDBACK_TABLE}
        (QUESTION_ID, FEEDBACK_TYPE, USER_NAME, FEEDBACK_TEXT, CREATED_AT)
        SELECT
            '{escaped_qid}',
            '{feedback_type}',
            '{escaped_user}',
            {text_value},
            CURRENT_TIMESTAMP()
    """
    session.sql(sql).collect()


def get_knowledge_owners(session, topics=None):
    if topics:
        topic_list = ", ".join(f"'{t.replace(chr(39), chr(39)+chr(39))}'" for t in topics)
        sql = f"""
            SELECT * FROM {KNOWLEDGE_OWNERS_TABLE}
            WHERE ARRAY_CONTAINS('{topic_list}'::VARIANT, EXPERTISE_TOPICS)
        """
    else:
        sql = f"SELECT * FROM {KNOWLEDGE_OWNERS_TABLE}"

    return session.sql(sql).collect()
