CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'requests')
HANDLER = 'run'
EXTERNAL_ACCESS_INTEGRATIONS = (SI_FRESHDESK_ACCESS)
SECRETS = ('api_key' = SNOWFLAKE_INTELLIGENCE.INGESTION.FRESHDESK_API_SECRET)
EXECUTE AS CALLER
AS
$$
import requests
import json
import time
import _snowflake
from datetime import datetime, timezone

BASE_URL = "https://newaccount1623084859360.freshdesk.com/api/v2"

BUCKET_40 = "40/min"
BUCKET_100 = "100/min"

rate_state = {
    BUCKET_40: {"remaining": 40, "reset_at": 0.0},
    BUCKET_100: {"remaining": 100, "reset_at": 0.0},
}


def _wait_if_needed(bucket):
    st = rate_state[bucket]
    if st["remaining"] <= 2:
        wait = max(0, st["reset_at"] - time.time()) + 1
        if wait > 0:
            time.sleep(wait)
        st["remaining"] = 40 if bucket == BUCKET_40 else 100


def _update_rate(bucket, headers):
    st = rate_state[bucket]
    if "x-ratelimit-remaining" in headers:
        st["remaining"] = int(headers["x-ratelimit-remaining"])
    if "retry-after" in headers:
        st["reset_at"] = time.time() + int(headers["retry-after"])
    elif "x-ratelimit-total" in headers:
        st["reset_at"] = time.time() + 60


def v2_get(path, auth, bucket, retries=3):
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        _wait_if_needed(bucket)
        try:
            resp = requests.get(url, auth=auth, timeout=30)
        except requests.exceptions.ConnectionError:
            time.sleep(2 ** attempt)
            continue
        _update_rate(bucket, resp.headers)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            rate_state[bucket]["remaining"] = 0
            rate_state[bucket]["reset_at"] = time.time() + retry_after
            time.sleep(retry_after + 1)
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code in (401, 403):
            raise Exception(f"Auth error {resp.status_code}: {url}")
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise Exception(f"Failed after {retries} retries: {url}")


def v2_paginate(path, auth, bucket, per_page=100, extra_params=None):
    all_records = []
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        paginated = f"{path}{sep}page={page}&per_page={per_page}"
        if extra_params:
            for k, v in extra_params.items():
                paginated += f"&{k}={v}"
        data = v2_get(paginated, auth, bucket)
        if data is None or not isinstance(data, list) or len(data) == 0:
            break
        all_records.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return all_records


def normalize_ts(ts_str):
    if ts_str is None:
        return None
    if isinstance(ts_str, str):
        ts_str = ts_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(ts_str)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ts_str
    return str(ts_str)


def dedup(records, pk="id"):
    seen = {}
    for r in records:
        key = r.get(pk)
        if key is None:
            continue
        existing = seen.get(key)
        if existing is None:
            seen[key] = r
        else:
            new_ts = r.get("updated_at") or ""
            old_ts = existing.get("updated_at") or ""
            if new_ts >= old_ts:
                seen[key] = r
    return list(seen.values())


def jsonify(val):
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return val


def flatten_record(record, field_map, ts_fields=None):
    row = {}
    for src, dest in field_map.items():
        val = record.get(src)
        if ts_fields and src in ts_fields:
            val = normalize_ts(val)
        elif isinstance(val, (dict, list)):
            val = jsonify(val)
        row[dest] = val
    return row


def write_table(session, records, table_name, mode="overwrite"):
    if not records:
        return 0
    session.create_dataframe(records).write.mode(mode).save_as_table(
        f"SNOWFLAKE_INTELLIGENCE.RAW.{table_name}"
    )
    return len(records)


def ingest_simple(auth, session, path, table_name, bucket, paginate, pk, field_map, ts_fields=None):
    if paginate:
        raw = v2_paginate(path, auth, bucket)
    else:
        raw = v2_get(path, auth, bucket)
        if raw is None:
            return 0
        if not isinstance(raw, list):
            raw = [raw]
    raw = dedup(raw, pk)
    records = [flatten_record(r, field_map, ts_fields) for r in raw]
    return write_table(session, records, table_name)


TICKET_FIELDS_MAP = {
    "id": "ID",
    "subject": "SUBJECT",
    "description": "DESCRIPTION",
    "description_text": "DESCRIPTION_TEXT",
    "status": "STATUS",
    "priority": "PRIORITY",
    "source": "SOURCE",
    "type": "TYPE",
    "requester_id": "REQUESTER_ID",
    "responder_id": "RESPONDER_ID",
    "company_id": "COMPANY_ID",
    "group_id": "GROUP_ID",
    "product_id": "PRODUCT_ID",
    "email_config_id": "EMAIL_CONFIG_ID",
    "to_emails": "TO_EMAILS",
    "cc_emails": "CC_EMAILS",
    "fwd_emails": "FWD_EMAILS",
    "reply_cc_emails": "REPLY_CC_EMAILS",
    "fr_escalated": "FR_ESCALATED",
    "spam": "SPAM",
    "is_escalated": "IS_ESCALATED",
    "tags": "TAGS",
    "custom_fields": "CUSTOM_FIELDS",
    "attachments": "ATTACHMENTS",
    "due_by": "DUE_BY",
    "fr_due_by": "FR_DUE_BY",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
TICKET_TS = {"created_at", "updated_at", "due_by", "fr_due_by"}

CONVERSATION_FIELDS_MAP = {
    "id": "ID",
    "ticket_id": "TICKET_ID",
    "user_id": "USER_ID",
    "body": "BODY",
    "body_text": "BODY_TEXT",
    "incoming": "INCOMING",
    "private": "PRIVATE",
    "source": "SOURCE",
    "category": "CATEGORY",
    "support_email": "SUPPORT_EMAIL",
    "to_emails": "TO_EMAILS",
    "from_email": "FROM_EMAIL",
    "cc_emails": "CC_EMAILS",
    "bcc_emails": "BCC_EMAILS",
    "attachments": "ATTACHMENTS",
    "last_edited_at": "LAST_EDITED_AT",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
CONVERSATION_TS = {"created_at", "updated_at", "last_edited_at"}

CONTACT_FIELDS_MAP = {
    "id": "ID",
    "name": "NAME",
    "email": "EMAIL",
    "phone": "PHONE",
    "mobile": "MOBILE",
    "company_id": "COMPANY_ID",
    "active": "ACTIVE",
    "job_title": "JOB_TITLE",
    "language": "LANGUAGE",
    "time_zone": "TIME_ZONE",
    "description": "DESCRIPTION",
    "address": "ADDRESS",
    "tags": "TAGS",
    "custom_fields": "CUSTOM_FIELDS",
    "other_emails": "OTHER_EMAILS",
    "other_companies": "OTHER_COMPANIES",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
CONTACT_TS = {"created_at", "updated_at"}

COMPANY_FIELDS_MAP = {
    "id": "ID",
    "name": "NAME",
    "description": "DESCRIPTION",
    "domains": "DOMAINS",
    "note": "NOTE",
    "health_score": "HEALTH_SCORE",
    "account_tier": "ACCOUNT_TIER",
    "renewal_date": "RENEWAL_DATE",
    "industry": "INDUSTRY",
    "custom_fields": "CUSTOM_FIELDS",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
COMPANY_TS = {"created_at", "updated_at", "renewal_date"}

AGENT_FIELDS_MAP = {
    "id": "ID",
    "contact": "CONTACT",
    "type": "TYPE",
    "occasional": "OCCASIONAL",
    "signature": "SIGNATURE",
    "ticket_scope": "TICKET_SCOPE",
    "group_ids": "GROUP_IDS",
    "role_ids": "ROLE_IDS",
    "available": "AVAILABLE",
    "available_since": "AVAILABLE_SINCE",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
AGENT_TS = {"created_at", "updated_at", "available_since"}

GROUP_FIELDS_MAP = {
    "id": "ID",
    "name": "NAME",
    "description": "DESCRIPTION",
    "business_hour_id": "BUSINESS_HOUR_ID",
    "escalate_to": "ESCALATE_TO",
    "unassigned_for": "UNASSIGNED_FOR",
    "agent_ids": "AGENT_IDS",
    "auto_ticket_assign": "AUTO_TICKET_ASSIGN",
    "group_type": "GROUP_TYPE",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
GROUP_TS = {"created_at", "updated_at"}

ROLE_FIELDS_MAP = {
    "id": "ID",
    "name": "NAME",
    "description": "DESCRIPTION",
    "default": "DEFAULT_ROLE",
    "agent_type": "AGENT_TYPE",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
ROLE_TS = {"created_at", "updated_at"}

TICKET_FIELD_FIELDS_MAP = {
    "id": "ID",
    "name": "NAME",
    "label": "LABEL",
    "description": "DESCRIPTION",
    "type": "TYPE",
    "default": "IS_DEFAULT",
    "customers_can_edit": "CUSTOMERS_CAN_EDIT",
    "required_for_closure": "REQUIRED_FOR_CLOSURE",
    "required_for_agents": "REQUIRED_FOR_AGENTS",
    "required_for_customers": "REQUIRED_FOR_CUSTOMERS",
    "position": "POSITION",
    "choices": "CHOICES",
    "nested_fields": "NESTED_FIELDS",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
TICKET_FIELD_TS = {"created_at", "updated_at"}

CONTACT_FIELD_FIELDS_MAP = {
    "id": "ID",
    "name": "NAME",
    "label": "LABEL",
    "type": "TYPE",
    "default": "IS_DEFAULT",
    "customers_can_edit": "CUSTOMERS_CAN_EDIT",
    "position": "POSITION",
    "choices": "CHOICES",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
CONTACT_FIELD_TS = {"created_at", "updated_at"}

COMPANY_FIELD_FIELDS_MAP = {
    "id": "ID",
    "name": "NAME",
    "label": "LABEL",
    "type": "TYPE",
    "default": "IS_DEFAULT",
    "position": "POSITION",
    "choices": "CHOICES",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
COMPANY_FIELD_TS = {"created_at", "updated_at"}

TICKET_FORM_FIELDS_MAP = {
    "id": "ID",
    "name": "NAME",
    "title": "TITLE",
    "default": "IS_DEFAULT",
    "fields": "FIELDS",
    "created_at": "CREATED_AT",
    "updated_at": "UPDATED_AT",
}
TICKET_FORM_TS = {"created_at", "updated_at"}

ACCOUNT_FIELDS_MAP = {
    "account_id": "ACCOUNT_ID",
    "account_name": "ACCOUNT_NAME",
    "account_domain": "ACCOUNT_DOMAIN",
    "tier_type": "TIER_TYPE",
    "timezone": "TIMEZONE",
    "data_center": "DATA_CENTER",
    "total_agents": "TOTAL_AGENTS",
}


def run(session):
    session.sql("USE DATABASE SNOWFLAKE_INTELLIGENCE").collect()
    session.sql("USE SCHEMA RAW").collect()
    start_time = time.time()
    api_key = _snowflake.get_generic_secret_string("api_key")
    auth = (api_key, "X")
    counts = {}
    errors = []

    last_ingested_at = None
    try:
        rows = session.sql(
            "SELECT CONFIG_VALUE::STRING FROM SNOWFLAKE_INTELLIGENCE.ADMIN.SYSTEM_CONFIG "
            "WHERE CONFIG_KEY = 'freshdesk_last_ingested_at'"
        ).collect()
        if rows and rows[0][0]:
            last_ingested_at = rows[0][0].strip('"')
    except Exception:
        pass

    # --- Tickets (40/min bucket) ---
    all_tickets = []
    try:
        extra = {}
        if last_ingested_at:
            extra["updated_since"] = last_ingested_at
        all_tickets = v2_paginate("/tickets", auth, BUCKET_40, extra_params=extra)
        all_tickets = dedup(all_tickets, "id")
        records = [flatten_record(t, TICKET_FIELDS_MAP, TICKET_TS) for t in all_tickets]
        counts["tickets"] = write_table(session, records, "FRESHDESK_TICKETS")
    except Exception as e:
        errors.append(f"tickets: {e}")

    # --- Ticket Conversations (40/min bucket, per-ticket) ---
    try:
        all_convos = []
        convo_errors = 0
        for t in all_tickets:
            tid = t.get("id")
            if tid is None:
                continue
            try:
                convos = v2_paginate(f"/tickets/{tid}/conversations", auth, BUCKET_40)
                for c in convos:
                    c["ticket_id"] = tid
                all_convos.extend(convos)
            except Exception:
                convo_errors += 1
        if all_tickets and convo_errors / max(len(all_tickets), 1) > 0.20:
            raise Exception(
                f"Conversation fetch failure rate {convo_errors}/{len(all_tickets)} exceeds 20%"
            )
        all_convos = dedup(all_convos, "id")
        records = [flatten_record(c, CONVERSATION_FIELDS_MAP, CONVERSATION_TS) for c in all_convos]
        counts["ticket_conversations"] = write_table(session, records, "FRESHDESK_TICKET_CONVERSATIONS")
    except Exception as e:
        errors.append(f"ticket_conversations: {e}")

    # --- Contacts (40/min bucket) ---
    try:
        extra = {}
        if last_ingested_at:
            extra["_updated_since"] = last_ingested_at
        raw = v2_paginate("/contacts", auth, BUCKET_40, extra_params=extra)
        raw = dedup(raw, "id")
        records = [flatten_record(r, CONTACT_FIELDS_MAP, CONTACT_TS) for r in raw]
        counts["contacts"] = write_table(session, records, "FRESHDESK_CONTACTS")
    except Exception as e:
        errors.append(f"contacts: {e}")

    # --- Companies (100/min bucket) ---
    try:
        counts["companies"] = ingest_simple(
            auth, session, "/companies", "FRESHDESK_COMPANIES",
            BUCKET_100, True, "id", COMPANY_FIELDS_MAP, COMPANY_TS
        )
    except Exception as e:
        errors.append(f"companies: {e}")

    # --- Agents (100/min bucket) ---
    try:
        counts["agents"] = ingest_simple(
            auth, session, "/agents", "FRESHDESK_AGENTS",
            BUCKET_100, True, "id", AGENT_FIELDS_MAP, AGENT_TS
        )
    except Exception as e:
        errors.append(f"agents: {e}")

    # --- Groups (100/min bucket) ---
    try:
        counts["groups"] = ingest_simple(
            auth, session, "/groups", "FRESHDESK_GROUPS",
            BUCKET_100, True, "id", GROUP_FIELDS_MAP, GROUP_TS
        )
    except Exception as e:
        errors.append(f"groups: {e}")

    # --- Roles (100/min, NOT paginated) ---
    try:
        counts["roles"] = ingest_simple(
            auth, session, "/roles", "FRESHDESK_ROLES",
            BUCKET_100, False, "id", ROLE_FIELDS_MAP, ROLE_TS
        )
    except Exception as e:
        errors.append(f"roles: {e}")

    # --- Account (100/min, single object) ---
    try:
        raw = v2_get("/account", auth, BUCKET_100)
        if raw:
            records = [flatten_record(raw, ACCOUNT_FIELDS_MAP)]
            counts["account"] = write_table(session, records, "FRESHDESK_ACCOUNT")
    except Exception as e:
        errors.append(f"account: {e}")

    # --- Ticket Fields (100/min, NOT paginated) ---
    try:
        counts["ticket_fields"] = ingest_simple(
            auth, session, "/ticket_fields", "FRESHDESK_TICKET_FIELDS",
            BUCKET_100, False, "id", TICKET_FIELD_FIELDS_MAP, TICKET_FIELD_TS
        )
    except Exception as e:
        errors.append(f"ticket_fields: {e}")

    # --- Contact Fields (100/min, NOT paginated) ---
    try:
        counts["contact_fields"] = ingest_simple(
            auth, session, "/contact_fields", "FRESHDESK_CONTACT_FIELDS",
            BUCKET_100, False, "id", CONTACT_FIELD_FIELDS_MAP, CONTACT_FIELD_TS
        )
    except Exception as e:
        errors.append(f"contact_fields: {e}")

    # --- Company Fields (100/min, NOT paginated) ---
    try:
        counts["company_fields"] = ingest_simple(
            auth, session, "/company_fields", "FRESHDESK_COMPANY_FIELDS",
            BUCKET_100, False, "id", COMPANY_FIELD_FIELDS_MAP, COMPANY_FIELD_TS
        )
    except Exception as e:
        errors.append(f"company_fields: {e}")

    # --- Ticket Forms (100/min, NOT paginated, hyphenated path) ---
    try:
        counts["ticket_forms"] = ingest_simple(
            auth, session, "/ticket-forms", "FRESHDESK_TICKET_FORMS",
            BUCKET_100, False, "id", TICKET_FORM_FIELDS_MAP, TICKET_FORM_TS
        )
    except Exception as e:
        errors.append(f"ticket_forms: {e}")

    duration = round(time.time() - start_time, 1)
    total_records = sum(counts.values())
    status = "success" if not errors else "partial_success"

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        session.sql(f"""
            MERGE INTO SNOWFLAKE_INTELLIGENCE.ADMIN.SYSTEM_CONFIG t
            USING (SELECT 'freshdesk_last_ingested_at' AS CONFIG_KEY) s
            ON t.CONFIG_KEY = s.CONFIG_KEY
            WHEN MATCHED THEN UPDATE SET
                CONFIG_VALUE = PARSE_JSON('{json.dumps(run_ts)}'),
                UPDATED_AT = CURRENT_TIMESTAMP(),
                UPDATED_BY = 'INGEST_FRESHDESK'
            WHEN NOT MATCHED THEN INSERT (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY)
                VALUES ('freshdesk_last_ingested_at', PARSE_JSON('{json.dumps(run_ts)}'),
                        'Last successful Freshdesk ingestion timestamp',
                        CURRENT_TIMESTAMP(), 'INGEST_FRESHDESK')
        """).collect()
    except Exception as e:
        errors.append(f"watermark_update: {e}")

    try:
        err_msg = "; ".join(errors).replace("'", "''") if errors else None
        err_sql = f"'{err_msg}'" if err_msg else "NULL"
        ing_type = "incremental" if last_ingested_at else "full"
        session.sql(f"""
            INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
                (SOURCE_SYSTEM, INGESTION_TYPE, STARTED_AT, COMPLETED_AT,
                 RECORDS_INGESTED, STATUS, ERROR_MESSAGE)
            SELECT 'freshdesk',
                   '{ing_type}',
                   DATEADD(SECOND, -{int(duration)}, CURRENT_TIMESTAMP()),
                   CURRENT_TIMESTAMP(),
                   {total_records},
                   '{status}',
                   {err_sql}
        """).collect()
    except Exception:
        pass

    return f"{status}: {json.dumps(counts)}, errors: {len(errors)}, duration: {duration}s"
$$;
