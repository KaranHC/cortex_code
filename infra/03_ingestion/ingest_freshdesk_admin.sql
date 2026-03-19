CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK_ADMIN()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'requests')
HANDLER = 'run'
EXTERNAL_ACCESS_INTEGRATIONS = (SI_FRESHDESK_ACCESS)
SECRETS = ('api_key' = SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET)
AS
$$
import requests
import json
import time
import _snowflake
from datetime import datetime, timezone
from snowflake.snowpark import Session

BASE_URL = "https://newaccount1623084859360.freshdesk.com/api/v2"
BUCKET_100 = {"remaining": 100, "reset_at": 0}

def v2_get(path, auth, bucket=None, retries=3, timeout=30):
    if bucket is None:
        bucket = BUCKET_100
    now = time.time()
    if bucket["remaining"] <= 2 and now < bucket["reset_at"]:
        time.sleep(bucket["reset_at"] - now + 1)
    for attempt in range(retries):
        try:
            resp = requests.get(f"{BASE_URL}{path}", auth=auth, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        remaining = resp.headers.get('X-RateLimit-Remaining')
        if remaining:
            bucket["remaining"] = int(remaining)
        if resp.status_code == 429:
            wait = int(resp.headers.get('Retry-After', 60))
            bucket["reset_at"] = time.time() + wait
            time.sleep(wait)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code in (401, 403):
            raise Exception(f"Auth/permission error ({resp.status_code}): {path}")
        resp.raise_for_status()
        return resp.json()
    raise Exception(f"Failed after {retries} retries: {path}")

def v2_paginate(path, auth, bucket=None, per_page=100):
    if bucket is None:
        bucket = BUCKET_100
    all_items, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        data = v2_get(f"{path}{sep}page={page}&per_page={per_page}", auth, bucket)
        if not data:
            break
        if isinstance(data, list):
            all_items.extend(data)
            if len(data) < per_page:
                break
        else:
            break
        page += 1
        time.sleep(0.5)
    return all_items

def normalize_ts(ts_str):
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return ts_str

def run(session):
    api_key = _snowflake.get_generic_secret_string('api_key')
    auth = (api_key, "X")
    counts = {}
    errors = []

    # --- Surveys ---
    try:
        data = v2_get("/surveys", auth)
        rows = []
        for r in (data or []):
            rows.append({
                "id": r.get("id"),
                "title": r.get("title"),
                "active": r.get("active"),
                "questions": json.dumps(r.get("questions")),
                "raw_json": json.dumps(r),
            })
        if rows:
            session.create_dataframe(rows).write.mode("overwrite").save_as_table(
                "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SURVEYS")
        counts["surveys"] = len(rows)
    except Exception as e:
        errors.append(f"surveys: {e}")

    # --- Satisfaction Ratings ---
    try:
        data = v2_paginate("/surveys/satisfaction_ratings", auth)
        rows = []
        for r in (data or []):
            rows.append({
                "id": r.get("id"),
                "survey_id": r.get("survey_id"),
                "user_id": r.get("user_id"),
                "agent_id": r.get("agent_id"),
                "ticket_id": r.get("ticket_id"),
                "group_id": r.get("group_id"),
                "feedback": r.get("feedback"),
                "ratings": json.dumps(r.get("ratings")),
                "created_at": normalize_ts(r.get("created_at")),
                "updated_at": normalize_ts(r.get("updated_at")),
                "raw_json": json.dumps(r),
            })
        if rows:
            session.create_dataframe(rows).write.mode("overwrite").save_as_table(
                "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SATISFACTION_RATINGS")
        counts["satisfaction_ratings"] = len(rows)
    except Exception as e:
        errors.append(f"satisfaction_ratings: {e}")

    # --- Email Configs ---
    try:
        data = v2_get("/email_configs", auth)
        rows = []
        for r in (data or []):
            rows.append({
                "id": r.get("id"),
                "name": r.get("name"),
                "to_email": r.get("to_email"),
                "reply_email": r.get("reply_email"),
                "group_id": r.get("group_id"),
                "primary_role": r.get("primary_role"),
                "active": r.get("active"),
                "raw_json": json.dumps(r),
            })
        if rows:
            session.create_dataframe(rows).write.mode("overwrite").save_as_table(
                "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_EMAIL_CONFIGS")
        counts["email_configs"] = len(rows)
    except Exception as e:
        errors.append(f"email_configs: {e}")

    # --- Email Mailboxes ---
    try:
        data = v2_get("/email/mailboxes", auth)
        rows = []
        for r in (data or []):
            rows.append({
                "id": r.get("id"),
                "name": r.get("name"),
                "support_email": r.get("support_email"),
                "product_id": r.get("product_id"),
                "group_id": r.get("group_id"),
                "active": r.get("active"),
                "raw_json": json.dumps(r),
            })
        if rows:
            session.create_dataframe(rows).write.mode("overwrite").save_as_table(
                "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_EMAIL_MAILBOXES")
        counts["email_mailboxes"] = len(rows)
    except Exception as e:
        errors.append(f"email_mailboxes: {e}")

    # --- Business Hours ---
    try:
        data = v2_get("/business_hours", auth)
        rows = []
        for r in (data or []):
            rows.append({
                "id": r.get("id"),
                "name": r.get("name"),
                "description": r.get("description"),
                "is_default": r.get("is_default"),
                "time_zone": r.get("time_zone"),
                "business_hours": json.dumps(r.get("business_hours")),
                "list_of_holidays": json.dumps(r.get("list_of_holidays")),
                "created_at": normalize_ts(r.get("created_at")),
                "updated_at": normalize_ts(r.get("updated_at")),
                "raw_json": json.dumps(r),
            })
        if rows:
            session.create_dataframe(rows).write.mode("overwrite").save_as_table(
                "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_BUSINESS_HOURS")
        counts["business_hours"] = len(rows)
    except Exception as e:
        errors.append(f"business_hours: {e}")

    # --- SLA Policies ---
    try:
        data = v2_get("/sla_policies", auth)
        rows = []
        for r in (data or []):
            rows.append({
                "id": r.get("id"),
                "name": r.get("name"),
                "description": r.get("description"),
                "is_default": r.get("is_default"),
                "active": r.get("active"),
                "position": r.get("position"),
                "applicable_to": json.dumps(r.get("applicable_to")),
                "sla_target": json.dumps(r.get("sla_target")),
                "escalation": json.dumps(r.get("escalation")),
                "created_at": normalize_ts(r.get("created_at")),
                "updated_at": normalize_ts(r.get("updated_at")),
                "raw_json": json.dumps(r),
            })
        if rows:
            session.create_dataframe(rows).write.mode("overwrite").save_as_table(
                "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SLA_POLICIES")
        counts["sla_policies"] = len(rows)
    except Exception as e:
        errors.append(f"sla_policies: {e}")

    # --- Automation Rules (3 types combined) ---
    try:
        automation_types = [1, 3, 4]
        rows = []
        for type_id in automation_types:
            data = v2_get(f"/automations/{type_id}/rules", auth)
            if data is None:
                continue
            rules = data.get("rules", data) if isinstance(data, dict) else data
            if not isinstance(rules, list):
                rules = [rules]
            for r in rules:
                rows.append({
                    "id": r.get("id"),
                    "automation_type_id": type_id,
                    "name": r.get("name"),
                    "active": r.get("active"),
                    "position": r.get("position"),
                    "conditions": json.dumps(r.get("conditions")),
                    "actions": json.dumps(r.get("actions")),
                    "performer": json.dumps(r.get("performer")),
                    "created_at": normalize_ts(r.get("created_at")),
                    "updated_at": normalize_ts(r.get("updated_at")),
                    "raw_json": json.dumps(r),
                })
        if rows:
            session.create_dataframe(rows).write.mode("overwrite").save_as_table(
                "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_AUTOMATION_RULES")
        counts["automation_rules"] = len(rows)
    except Exception as e:
        errors.append(f"automation_rules: {e}")

    total = sum(counts.values())
    status = "partial_success" if errors else "success"

    try:
        session.sql(f"""
            INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
                (source_system, ingestion_type, started_at, completed_at, records_ingested, status)
            SELECT 'freshdesk_admin', 'full', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
                {total}, '{status}'
        """).collect()
    except Exception:
        pass

    parts = [f"{k}={v}" for k, v in counts.items()]
    result = f"Ingested Freshdesk Admin: {', '.join(parts)} (total={total})"
    if errors:
        result += f" | Errors: {'; '.join(errors)}"
    return result
$$;
