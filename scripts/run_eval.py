import json
import os
import sys
import time
from datetime import datetime

import snowflake.connector


AGENTS = {
    "primary": "SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT",
    "fallback": "SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT_FALLBACK",
    "fallback_2": "SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT_FALLBACK_2",
}

JUDGE_PROMPT = """You are an evaluation judge. Compare the agent's answer to the expected answer and score it.

Question: {question}
Expected Answer: {expected_answer}
Agent Answer: {agent_answer}

Score the answer on a 0-2 scale:
- 2 = CORRECT: Agent answer contains the key information from the expected answer, even if worded differently. Minor extra details are fine.
- 1 = PARTIAL: Agent answer captures some but not all key points, or is partially correct.
- 0 = INCORRECT: Agent answer is wrong, missing key information, or says it cannot find information when it exists.

Special cases:
- If the expected answer says the question is "out of scope" and the agent correctly identifies it as out of scope (no_answer or similar), score 2.
- If the agent returns valid JSON with answer_strength "no_answer" for an in-scope question that should have an answer, score 0.

Respond with ONLY a JSON object:
{{"score": <0|1|2>, "reason": "<brief explanation>"}}"""


def get_connection():
    conn_name = os.getenv("SNOWFLAKE_CONNECTION_NAME") or "VVA53450"
    return snowflake.connector.connect(connection_name=conn_name)


def fetch_eval_questions(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT question_id, question, expected_answer, category, product_area, difficulty
        FROM SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_DATASET
        ORDER BY question_id
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def call_agent(conn, agent_fqn, question):
    cur = conn.cursor()
    request_body = json.dumps({
        "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}]
    })
    safe_body = request_body.replace("'", "''")
    safe_agent = agent_fqn.replace("'", "''")
    start = time.time()
    try:
        cur.execute(f"""
            SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                '{safe_agent}',
                '{safe_body}'
            )
        """)
        row = cur.fetchone()
        elapsed_ms = int((time.time() - start) * 1000)
        raw = json.loads(row[0]) if isinstance(row[0], str) else row[0]

        text_content = ""
        for part in raw.get("content", []):
            if isinstance(part, dict) and part.get("type") == "text":
                text_content = part.get("text", "")
                break

        try:
            parsed = json.loads(text_content)
            answer = parsed.get("answer", text_content)
            strength = parsed.get("answer_strength", "unknown")
        except (json.JSONDecodeError, TypeError):
            answer = text_content or str(raw)
            strength = "unknown"

        return {"answer": answer, "answer_strength": strength, "latency_ms": elapsed_ms, "error": None}
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {"answer": "", "answer_strength": "error", "latency_ms": elapsed_ms, "error": str(e)}
    finally:
        cur.close()


def judge_answer(conn, question, expected_answer, agent_answer):
    cur = conn.cursor()
    prompt = JUDGE_PROMPT.format(
        question=question,
        expected_answer=expected_answer,
        agent_answer=agent_answer
    )
    safe_prompt = prompt.replace("'", "''")
    try:
        cur.execute(f"""
            SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-sonnet-4-6', '{safe_prompt}')
        """)
        row = cur.fetchone()
        result = row[0] if row else "{}"
        if isinstance(result, str):
            result = json.loads(result)
        return result
    except Exception as e:
        return {"score": -1, "reason": f"Judge error: {str(e)}"}
    finally:
        cur.close()


def run_evaluation(agent_key=None):
    conn = get_connection()
    questions = fetch_eval_questions(conn)
    agents_to_test = {agent_key: AGENTS[agent_key]} if agent_key else AGENTS

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    for akey, afqn in agents_to_test.items():
        print(f"\n{'='*60}")
        print(f"Evaluating: {akey} ({afqn})")
        print(f"{'='*60}")

        agent_results = []
        for i, q in enumerate(questions):
            qid = q["QUESTION_ID"]
            question = q["QUESTION"]
            expected = q["EXPECTED_ANSWER"]
            category = q["CATEGORY"]

            print(f"  [{i+1}/{len(questions)}] Q{qid}: {question[:60]}...", end=" ", flush=True)

            resp = call_agent(conn, afqn, question)

            if resp["error"]:
                print(f"ERROR ({resp['latency_ms']}ms)")
                judgment = {"score": 0, "reason": f"Agent error: {resp['error']}"}
            else:
                judgment = judge_answer(conn, question, expected, resp["answer"])
                score = judgment.get("score", -1)
                label = {2: "CORRECT", 1: "PARTIAL", 0: "INCORRECT"}.get(score, "ERROR")
                print(f"{label} ({resp['latency_ms']}ms)")

            agent_results.append({
                "question_id": qid,
                "question": question,
                "expected_answer": expected,
                "category": category,
                "agent_answer": resp["answer"],
                "answer_strength": resp["answer_strength"],
                "latency_ms": resp["latency_ms"],
                "error": resp["error"],
                "score": judgment.get("score", -1),
                "judge_reason": judgment.get("reason", ""),
            })

        total = len(agent_results)
        correct = sum(1 for r in agent_results if r["score"] == 2)
        partial = sum(1 for r in agent_results if r["score"] == 1)
        incorrect = sum(1 for r in agent_results if r["score"] == 0)
        errors = sum(1 for r in agent_results if r["score"] == -1)
        avg_latency = sum(r["latency_ms"] for r in agent_results) / total if total else 0

        summary = {
            "agent": akey,
            "agent_fqn": afqn,
            "total_questions": total,
            "correct": correct,
            "partial": partial,
            "incorrect": incorrect,
            "errors": errors,
            "accuracy_pct": round((correct * 2 + partial) / (total * 2) * 100, 1) if total else 0,
            "avg_latency_ms": round(avg_latency),
        }

        print(f"\n  Summary for {akey}:")
        print(f"    Correct: {correct}/{total} | Partial: {partial}/{total} | Incorrect: {incorrect}/{total} | Errors: {errors}/{total}")
        print(f"    Accuracy: {summary['accuracy_pct']}% | Avg Latency: {summary['avg_latency_ms']}ms")

        by_category = {}
        for r in agent_results:
            cat = r["category"]
            if cat not in by_category:
                by_category[cat] = {"total": 0, "correct": 0, "partial": 0, "incorrect": 0}
            by_category[cat]["total"] += 1
            if r["score"] == 2:
                by_category[cat]["correct"] += 1
            elif r["score"] == 1:
                by_category[cat]["partial"] += 1
            else:
                by_category[cat]["incorrect"] += 1

        print(f"    By category:")
        for cat, stats in sorted(by_category.items()):
            print(f"      {cat}: {stats['correct']}/{stats['total']} correct, {stats['partial']}/{stats['total']} partial")

        results.append({
            "summary": summary,
            "details": agent_results,
            "by_category": by_category,
        })

    output_path = f"/Users/chethan/work/rev/ragsearch/scripts/eval_results_{timestamp}.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_path}")

    conn.close()
    return results


if __name__ == "__main__":
    agent_key = sys.argv[1] if len(sys.argv) > 1 else None
    if agent_key and agent_key not in AGENTS:
        print(f"Unknown agent key: {agent_key}. Choose from: {list(AGENTS.keys())}")
        sys.exit(1)
    run_evaluation(agent_key)
