CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK_DISCUSSIONS()
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
from snowflake.snowpark import Session
from datetime import datetime

BASE_URL = "https://newaccount1623084859360.freshdesk.com/api/v2"

def normalize_ts(val):
    if not val:
        return None
    if isinstance(val, str):
        return val.replace("T", " ").replace("Z", "")
    return str(val)

def v2_get(url, auth, retries=3):
    for attempt in range(retries):
        resp = requests.get(url, auth=auth)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            time.sleep(retry_after)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise Exception(f"Failed after {retries} retries: {url}")

def v2_paginate(url, auth, per_page=100):
    results = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        page_url = f"{url}{sep}page={page}&per_page={per_page}"
        data = v2_get(page_url, auth)
        if not data:
            break
        results.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return results

def run(session):
    api_key = _snowflake.get_generic_secret_string('api_key')
    auth = (api_key, "X")

    categories_raw = v2_get(f"{BASE_URL}/discussions/categories", auth)
    categories = []
    for c in categories_raw:
        categories.append({
            "id": c["id"],
            "name": c.get("name", ""),
            "description": c.get("description", ""),
            "position": c.get("position"),
            "created_at": normalize_ts(c.get("created_at")),
            "updated_at": normalize_ts(c.get("updated_at")),
            "raw_json": json.dumps(c),
        })

    forums = []
    for cat in categories:
        cat_id = cat["id"]
        try:
            forums_raw = v2_get(f"{BASE_URL}/discussions/categories/{cat_id}/forums", auth)
            for f in forums_raw:
                forums.append({
                    "id": f["id"],
                    "category_id": cat_id,
                    "name": f.get("name", ""),
                    "description": f.get("description", ""),
                    "forum_type": f.get("forum_type"),
                    "forum_visibility": f.get("forum_visibility"),
                    "topics_count": f.get("topics_count", 0),
                    "position": f.get("position"),
                    "created_at": normalize_ts(f.get("created_at")),
                    "updated_at": normalize_ts(f.get("updated_at")),
                    "raw_json": json.dumps(f),
                })
        except Exception:
            continue

    topics = []
    for forum in forums:
        forum_id = forum["id"]
        try:
            topics_raw = v2_paginate(f"{BASE_URL}/discussions/forums/{forum_id}/topics", auth)
            for t in topics_raw:
                topics.append({
                    "id": t["id"],
                    "forum_id": forum_id,
                    "title": t.get("title", ""),
                    "user_id": t.get("user_id"),
                    "locked": t.get("locked", False),
                    "sticky": t.get("sticky", False),
                    "hits": t.get("hits", 0),
                    "replies": t.get("replies", 0),
                    "created_at": normalize_ts(t.get("created_at")),
                    "updated_at": normalize_ts(t.get("updated_at")),
                    "raw_json": json.dumps(t),
                })
        except Exception:
            continue

    comments = []
    for topic in topics:
        topic_id = topic["id"]
        try:
            comments_raw = v2_paginate(f"{BASE_URL}/discussions/topics/{topic_id}/comments", auth)
            for cm in comments_raw:
                comments.append({
                    "id": cm["id"],
                    "topic_id": topic_id,
                    "user_id": cm.get("user_id"),
                    "body": cm.get("body", ""),
                    "body_text": cm.get("body_text", ""),
                    "answer": cm.get("answer", False),
                    "created_at": normalize_ts(cm.get("created_at")),
                    "updated_at": normalize_ts(cm.get("updated_at")),
                    "raw_json": json.dumps(cm),
                })
        except Exception:
            continue

    if categories:
        session.create_dataframe(categories).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_CATEGORIES")
    if forums:
        session.create_dataframe(forums).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_FORUMS")
    if topics:
        session.create_dataframe(topics).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_TOPICS")
    if comments:
        session.create_dataframe(comments).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_COMMENTS")

    total = len(categories) + len(forums) + len(topics) + len(comments)
    session.sql("""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
            (source_system, ingestion_type, started_at, completed_at, records_ingested, status)
        SELECT 'freshdesk_discussions', 'full', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
            """ + str(total) + """, 'success'
    """).collect()

    return (f"Ingested Freshdesk Discussions: {len(categories)} categories, "
            f"{len(forums)} forums, {len(topics)} topics, {len(comments)} comments")
$$;
