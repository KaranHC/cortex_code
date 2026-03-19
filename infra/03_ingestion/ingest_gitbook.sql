CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.INGEST_GITBOOK()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'requests')
HANDLER = 'run'
EXTERNAL_ACCESS_INTEGRATIONS = (SI_GITBOOK_ACCESS)
SECRETS = ('api_key' = SNOWFLAKE_INTELLIGENCE.INGESTION.GITBOOK_API_SECRET)
AS
$$
import requests
import json
import time
import _snowflake
from snowflake.snowpark import Session

ALLOWED_SPACE_IDS = {
    "-MEiW8xrgQlP3-v0URKN",
    "49lBWSCXQFq3YGRsWAXQ",
    "0d42YQdL3XYb3luJAPml",
    "b8fWWMibpoQPDE8c4bNU",
    "6EV0C5Tj7N6vgV31huTC",
    "-MEhYn3_AWu0YUP8Nex5",
    "iMjnl88bO52hFfU06D2S",
    "j7aR5bZPcW93Y3GaPQ6Y",
    "7rxGLsjuchCZnYivHpjd",
    "kA6L5ph2xG5uY0BHLf9p",
}

SKIP_SPACE_IDS = {
    "MrHXgW2jdKgv8Y7c0wSU",
    "DiFtdEKGyDkbKD9Tsb1b",
    "lXHq7lsBry23eg9Mvktx",
    "O8uSos1Fe25XRS2l6MhB",
    "T3F6jlXMBoPcreFBmXaD",
    "mWh49nn1fFTt7s05kEQq",
    "lbAOpV8iERyMzty9TCzw",
}

def api_get(url, headers, retries=3):
    for attempt in range(retries):
        resp = requests.get(url, headers=headers)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get('Retry-After', 30))
            time.sleep(retry_after)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise Exception(f"Rate limited after {retries} retries: {url}")

def extract_leaves(nodes):
    texts = []
    for node in nodes:
        leaves = node.get("leaves", [])
        if leaves:
            for leaf in leaves:
                texts.append(leaf.get("text", ""))
        elif "nodes" in node:
            texts.append(extract_leaves(node["nodes"]))
    return "".join(texts)

def nodes_to_text(nodes, depth=0):
    parts = []
    for node in nodes:
        node_type = node.get("type", "")
        children = node.get("nodes", [])

        if node_type in ("heading-1", "heading-2", "heading-3"):
            prefix = "#" * int(node_type[-1]) + " "
            text = extract_leaves(children)
            parts.append(f"\n{prefix}{text}\n")
        elif node_type == "paragraph":
            text = extract_leaves(children)
            if text.strip():
                parts.append(text)
        elif node_type in ("list-unordered", "list-ordered"):
            for i, item in enumerate(children):
                item_children = item.get("nodes", [])
                bullet = f"{i+1}." if node_type == "list-ordered" else "-"
                text = nodes_to_text(item_children, depth + 1)
                parts.append(f"{bullet} {text}")
        elif node_type == "list-item":
            text = nodes_to_text(children, depth)
            parts.append(text)
        elif node_type == "code":
            text = extract_leaves(children)
            parts.append(f"```\n{text}\n```")
        elif node_type in ("blockquote", "hint"):
            text = nodes_to_text(children, depth)
            parts.append(f"> {text}")
        elif node_type == "table":
            for row in children:
                cells = row.get("nodes", [])
                row_text = " | ".join(nodes_to_text(c.get("nodes", []), depth) for c in cells)
                parts.append(f"| {row_text} |")
        elif node_type == "tabs":
            for tab in children:
                tab_title = tab.get("title", tab.get("data", {}).get("title", ""))
                tab_text = nodes_to_text(tab.get("nodes", []), depth)
                parts.append(f"[Tab: {tab_title}]\n{tab_text}")
        elif node_type == "swagger":
            parts.append(f"[API Reference: {node.get('data', {}).get('url', '')}]")
        elif node_type == "images":
            for img in children:
                caption = img.get("caption", "")
                parts.append(f"[Image: {caption}]" if caption else "[Image]")
        else:
            text = extract_leaves(children)
            if text.strip():
                parts.append(text)
            elif children:
                parts.append(nodes_to_text(children, depth))

    return "\n".join(parts)

def run(session):
    api_key = _snowflake.get_generic_secret_string('api_key')
    base_url = "https://api.gitbook.com/v1"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    orgs_data = api_get(f"{base_url}/orgs", headers)
    orgs_list = orgs_data.get("items", [])

    spaces_list = []
    spaces = []
    skipped = []
    for org in orgs_list:
        org_id = org["id"]
        try:
            org_spaces = api_get(f"{base_url}/orgs/{org_id}/spaces", headers)
            for s in org_spaces.get("items", []):
                if s["id"] in SKIP_SPACE_IDS:
                    skipped.append(s.get("title", s["id"]))
                    continue
                if s["id"] not in ALLOWED_SPACE_IDS:
                    skipped.append(s.get("title", s["id"]))
                    continue
                spaces_list.append(s)
                spaces.append({
                    "space_id": s["id"],
                    "title": s.get("title", ""),
                    "description": s.get("description", ""),
                    "visibility": s.get("visibility", ""),
                    "created_at": s.get("createdAt"),
                    "updated_at": s.get("updatedAt"),
                    "urls": json.dumps(s.get("urls", {})),
                })
        except Exception:
            continue

    if spaces:
        session.create_dataframe(spaces).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_SPACES")

    pages = []
    for space in spaces_list:
        space_id = space["id"]
        space_title = space.get("title", "")

        try:
            content_data = api_get(f"{base_url}/spaces/{space_id}/content", headers)
            page_list = content_data.get("pages", [])
        except Exception:
            continue

        def process_pages(page_list, parent_id=None):
            for page in page_list:
                page_id = page.get("id", "")
                content_text = ""
                try:
                    page_detail = api_get(
                        f"{base_url}/spaces/{space_id}/content/page/{page_id}",
                        headers
                    )
                    doc = page_detail.get("document", {})
                    doc_nodes = doc.get("nodes", [])
                    content_text = nodes_to_text(doc_nodes) if doc_nodes else ""
                except Exception:
                    content_text = page.get("description", "")

                pages.append({
                    "page_id": page_id,
                    "space_id": space_id,
                    "space_title": space_title,
                    "title": page.get("title", ""),
                    "description": page.get("description", ""),
                    "path": page.get("path", ""),
                    "content_markdown": content_text,
                    "parent_page_id": parent_id,
                    "kind": page.get("kind", "document"),
                    "created_at": page.get("createdAt"),
                    "updated_at": page.get("updatedAt"),
                })

                if "pages" in page:
                    process_pages(page["pages"], page_id)

        process_pages(page_list)

    if pages:
        session.create_dataframe(pages).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_PAGES")

    collections = []
    for org in orgs_list:
        org_id = org["id"]
        try:
            coll_data = api_get(f"{base_url}/orgs/{org_id}/collections", headers)
            for c in coll_data.get("items", []):
                collections.append({
                    "collection_id": c["id"],
                    "space_id": c.get("spaceId", ""),
                    "title": c.get("title", ""),
                    "description": c.get("description", ""),
                    "path": c.get("path", ""),
                    "created_at": c.get("createdAt"),
                    "updated_at": c.get("updatedAt"),
                })
        except Exception:
            pass

    if collections:
        session.create_dataframe(collections).write.mode("overwrite").save_as_table(
            "SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_COLLECTIONS")

    session.sql("""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.INGESTION.INGESTION_LOG
            (source_system, ingestion_type, started_at, completed_at, records_ingested, status)
        SELECT 'gitbook', 'full', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
            """ + str(len(spaces) + len(pages) + len(collections)) + """, 'success'
    """).collect()

    return (f"Ingested GitBook: {len(spaces)} spaces, {len(pages)} pages, "
            f"{len(collections)} collections. Skipped: {skipped}")
$$;
