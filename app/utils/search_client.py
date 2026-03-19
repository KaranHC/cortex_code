import json

SEARCH_SERVICE = "SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH"
SEARCH_COLUMNS = [
    "content",
    "title",
    "source_system",
    "owner",
    "backup_owner",
    "source_url",
    "last_updated",
    "document_id",
    "chunk_id",
    "topic",
    "product_area",
]


def search_documents(session, query, filters=None, limit=5):
    search_params = {
        "query": query,
        "columns": SEARCH_COLUMNS,
        "limit": limit,
    }

    if filters:
        filter_dict = {}
        if filters.get("team"):
            filter_dict["@eq"] = {"owner": filters["team"]}
        if filters.get("source_system"):
            if "@and" not in filter_dict:
                if filter_dict:
                    existing = dict(filter_dict)
                    filter_dict = {"@and": [existing, {"@eq": {"source_system": filters["source_system"]}}]}
                else:
                    filter_dict["@eq"] = {"source_system": filters["source_system"]}
            else:
                filter_dict["@and"].append({"@eq": {"source_system": filters["source_system"]}})
        if filter_dict:
            search_params["filter"] = filter_dict

    params_json = json.dumps(search_params).replace("'", "''")

    result = session.sql(f"""
        SELECT PARSE_JSON(
            SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                '{SEARCH_SERVICE}',
                '{params_json}'
            )
        )['results'] AS results
    """).collect()

    raw = result[0]["RESULTS"]
    if isinstance(raw, str):
        return json.loads(raw)
    return raw
