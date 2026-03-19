CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_FRESHDESK_SOLUTIONS()
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
from datetime import datetime

BASE_URL = "https://newaccount1623084859360.freshdesk.com/api/v2"

def v2_get(url, auth, retries=3):
    for attempt in range(retries):
        resp = requests.get(url, auth=auth)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 30))
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
        time.sleep(0.5)
    return results

def normalize_ts(val):
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def dedup(records, key="id"):
    seen = set()
    out = []
    for r in records:
        k = r.get(key)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out

def run(session):
    api_key = _snowflake.get_generic_secret_string("api_key")
    auth = (api_key, "X")
    errors = []

    categories_raw = v2_get(f"{BASE_URL}/solutions/categories", auth)
    if not categories_raw:
        raise Exception("Failed to fetch any categories")

    category_records = []
    for c in categories_raw:
        category_records.append({
            "ID": c["id"],
            "NAME": c.get("name", ""),
            "DESCRIPTION": c.get("description", ""),
            "VISIBLE_IN_PORTALS": json.dumps(c.get("visible_in_portals", [])),
            "CREATED_AT": normalize_ts(c.get("created_at")),
            "UPDATED_AT": normalize_ts(c.get("updated_at")),
            "RAW_JSON": json.dumps(c),
        })
    category_records = dedup(category_records, "ID")

    folder_records = []
    cat_folder_map = {}
    for cat in categories_raw:
        cat_id = cat["id"]
        try:
            folders_raw = v2_get(f"{BASE_URL}/solutions/categories/{cat_id}/folders", auth)
            time.sleep(0.5)
        except Exception as e:
            errors.append(f"folders for category {cat_id}: {e}")
            continue
        for f in (folders_raw or []):
            cat_folder_map[f["id"]] = cat_id
            folder_records.append({
                "ID": f["id"],
                "CATEGORY_ID": cat_id,
                "NAME": f.get("name", ""),
                "DESCRIPTION": f.get("description", ""),
                "VISIBILITY": f.get("visibility"),
                "ARTICLES_COUNT": f.get("articles_count"),
                "CREATED_AT": normalize_ts(f.get("created_at")),
                "UPDATED_AT": normalize_ts(f.get("updated_at")),
                "RAW_JSON": json.dumps(f),
            })
    folder_records = dedup(folder_records, "ID")

    if not folder_records and errors:
        raise Exception(f"All category-folder fetches failed: {errors}")

    article_records = []
    for folder in folder_records:
        folder_id = folder["ID"]
        category_id = cat_folder_map.get(folder_id)
        try:
            articles_raw = v2_paginate(f"{BASE_URL}/solutions/folders/{folder_id}/articles", auth)
        except Exception as e:
            errors.append(f"articles for folder {folder_id}: {e}")
            continue
        for a in (articles_raw or []):
            article_records.append({
                "ID": a["id"],
                "FOLDER_ID": folder_id,
                "CATEGORY_ID": category_id,
                "AGENT_ID": a.get("agent_id"),
                "TITLE": a.get("title", ""),
                "DESCRIPTION": a.get("description", ""),
                "DESCRIPTION_TEXT": a.get("description_text", ""),
                "STATUS": a.get("status"),
                "TYPE": a.get("type"),
                "HITS": a.get("hits"),
                "THUMBS_UP": a.get("thumbs_up"),
                "THUMBS_DOWN": a.get("thumbs_down"),
                "SEO_DATA": json.dumps(a.get("seo_data", {})),
                "TAGS": json.dumps(a.get("tags", [])),
                "CREATED_AT": normalize_ts(a.get("created_at")),
                "UPDATED_AT": normalize_ts(a.get("updated_at")),
                "RAW_JSON": json.dumps(a),
            })
    article_records = dedup(article_records, "ID")

    if category_records:
        session.create_dataframe(category_records).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_CATEGORIES")

    if folder_records:
        session.create_dataframe(folder_records).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_FOLDERS")

    if article_records:
        session.create_dataframe(article_records).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_ARTICLES")

    total = len(category_records) + len(folder_records) + len(article_records)
    session.sql("""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
            (source_system, ingestion_type, started_at, completed_at, records_ingested, status)
        SELECT 'freshdesk_solutions', 'full', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
            """ + str(total) + """, 'success'
    """).collect()

    result = (f"Ingested Freshdesk Solutions: {len(category_records)} categories, "
              f"{len(folder_records)} folders, {len(article_records)} articles")
    if errors:
        result += f". Partial errors: {errors}"
    return result
$$;
