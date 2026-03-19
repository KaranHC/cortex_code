# Research: Data Ingestion Pipelines
## Agent 4 Output — Comprehensive Findings

---

## Overview

Three data sources need to be ingested into Snowflake:
1. **Freshdesk** (helpdesk.revelator.com) — Knowledge base articles about music distribution, DSPs, royalties
2. **GitBook** — Product documentation
3. **Notion** — Internal wiki and operational docs

All ingestion will use **Snowflake-native** infrastructure:
- Snowflake Secrets (credential storage)
- External Access Integrations (outbound API access)
- Python Stored Procedures (API clients)
- Snowflake Tasks (scheduling)

---

## Freshdesk API

### Authentication
- API key used as HTTP Basic Auth username with "X" as password
- Base URL: `https://helpdesk.revelator.com/api/v2`
- Rate limit: 1000 requests/hour (Enterprise plan)

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/solutions/categories` | GET | List all KB categories |
| `/solutions/categories/{id}/folders` | GET | List folders in category |
| `/solutions/folders/{id}/articles` | GET | List articles in folder |
| `/solutions/articles/{id}` | GET | Get single article with full content |
| `/search/solutions?term=X` | GET | Search KB articles |

### Article Structure
```json
{
    "id": 123,
    "title": "Why is my music muted in a TikTok video?",
    "description": "<p>HTML content...</p>",
    "description_text": "Plain text content...",
    "status": 2,  // 1=draft, 2=published
    "folder_id": 456,
    "category_id": 789,
    "tags": ["tiktok", "muting", "ugc"],
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2025-10-14T12:42:00Z",
    "agent_id": 101
}
```

### Known Content (from helpdesk.revelator.com)
Based on the site crawl, key knowledge categories include:
- **FAQ**: Music distribution, royalties, reporting in Revelator Pro
- **Onboarding to Revelator Pro**: Account setup, tool integration, getting started
- **Creating & Updating Releases**: Music distribution management
- **Popular articles**: TikTok muting, YouTube MCN linking, DSP support list, UGC DSP policies

### Incremental Load Strategy
- Use `updated_at` field to fetch only articles modified since last ingestion
- Store `_last_ingested_at` in SYSTEM_CONFIG table
- Freshdesk supports `updated_since` parameter on list endpoints

---

## GitBook API

### Authentication
- Bearer token in Authorization header
- API key from .env: `gb_api_eRsEQjJveQ3dQh4yD1fBZlOfMip277BJ9bgnTPlf`
- Base URL: `https://api.gitbook.com/v1`
- Rate limit: 100 requests/minute

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/spaces` | GET | List all accessible spaces |
| `/spaces/{id}/content` | GET | List pages in a space (hierarchical) |
| `/spaces/{id}/content/page/{pageId}` | GET | Get page content (markdown) |
| `/spaces/{id}/content/page/{pageId}/revisions` | GET | Page revision history |

### Page Structure
```json
{
    "id": "abc-123",
    "title": "Distribution Guide",
    "description": "How to distribute music",
    "path": "/distribution-guide",
    "pages": [  // Nested child pages
        {
            "id": "def-456",
            "title": "Setting Up Distribution",
            "path": "/distribution-guide/setup"
        }
    ],
    "createdAt": "2024-03-01T00:00:00Z",
    "updatedAt": "2025-06-15T00:00:00Z"
}
```

### Content Export
GitBook returns content in **markdown format** — ideal for chunking and search indexing.

### Incremental Load Strategy
- Use `updatedAt` to track changes
- GitBook has revision history — can diff against last known revision
- Full refresh recommended initially, then incremental via `updatedAt` comparison

---

## Notion API

### Authentication
- Bearer token in Authorization header (`Bearer ntn_xxx`)
- Notion-Version header required: `2022-06-28`
- Base URL: `https://api.notion.com/v1`
- Rate limit: 3 requests/second

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/search` | POST | Search all pages/databases |
| `/pages/{id}` | GET | Get page metadata |
| `/blocks/{id}/children` | GET | Get page content (blocks) |
| `/databases/{id}/query` | POST | Query a database |

### Block Types to Handle
- `paragraph` → text content
- `heading_1/2/3` → section headers
- `bulleted_list_item` → bullet points
- `numbered_list_item` → numbered lists
- `code` → code blocks
- `table` → tables
- `toggle` → collapsible sections
- `callout` → highlighted content
- `quote` → blockquotes
- `divider` → section breaks

### Content Extraction
Notion stores content as **blocks**, not as text. Must recursively fetch children and convert to markdown.

### Incremental Load Strategy
- Use `last_edited_time` from search results
- Notion's search API supports `filter` by `last_edited_time`
- Store last ingestion timestamp and only fetch newer pages

---

## Snowflake Infrastructure for Ingestion

### Secrets

```sql
CREATE OR REPLACE SECRET REVSEARCH.INGESTION.FRESHDESK_API_SECRET
    TYPE = GENERIC_STRING
    SECRET_STRING = 'eduJofkrPjd7sDyTt1AK';

CREATE OR REPLACE SECRET REVSEARCH.INGESTION.GITBOOK_API_SECRET
    TYPE = GENERIC_STRING
    SECRET_STRING = 'gb_api_eRsEQjJveQ3dQh4yD1fBZlOfMip277BJ9bgnTPlf';
```

### Network Rules

```sql
CREATE OR REPLACE NETWORK RULE REVSEARCH.INGESTION.FRESHDESK_RULE
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = ('helpdesk.revelator.com');

CREATE OR REPLACE NETWORK RULE REVSEARCH.INGESTION.GITBOOK_RULE
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = ('api.gitbook.com');

CREATE OR REPLACE NETWORK RULE REVSEARCH.INGESTION.NOTION_RULE
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = ('api.notion.com');
```

### External Access Integrations

```sql
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION REVSEARCH_FRESHDESK_EAI
    ALLOWED_NETWORK_RULES = (REVSEARCH.INGESTION.FRESHDESK_RULE)
    ALLOWED_AUTHENTICATION_SECRETS = (REVSEARCH.INGESTION.FRESHDESK_API_SECRET)
    ENABLED = TRUE;
```

### Task Scheduling (Weekly Re-ingestion)

```sql
-- Weekly full refresh (Sunday 2 AM)
CREATE OR REPLACE TASK REVSEARCH.INGESTION.WEEKLY_FULL_REFRESH
    WAREHOUSE = REVSEARCH_INGESTION_WH
    SCHEDULE = 'USING CRON 0 2 * * 0 America/Los_Angeles'
AS
    CALL REVSEARCH.INGESTION.INGEST_ALL_SOURCES('full');

-- 6-hourly incremental (new/updated articles only)
CREATE OR REPLACE TASK REVSEARCH.INGESTION.INCREMENTAL_INGEST
    WAREHOUSE = REVSEARCH_INGESTION_WH
    SCHEDULE = 'USING CRON 0 */6 * * * America/Los_Angeles'
AS
    CALL REVSEARCH.INGESTION.INGEST_ALL_SOURCES('incremental');
```

---

## Document Chunking Strategy

### Recommended Parameters
- **Chunk size**: 1500 characters (~375-500 tokens)
- **Overlap**: 200 characters (~50 tokens, ~13% overlap)
- **Break points**: Prefer sentence boundaries (`. `) or paragraph boundaries (`\n\n`)

### Why these values?
- **1500 chars**: Fits well within Cortex Search's indexing sweet spot
- **Overlap**: Ensures no information is lost at chunk boundaries
- **Sentence breaks**: Preserves semantic coherence within chunks

### Chunking Logic
```python
def chunk_text(text, chunk_size=1500, overlap=200):
    if not text or len(text) <= chunk_size:
        return [text] if text else []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # Break at sentence or paragraph boundary
        if end < len(text):
            for sep in ['\n\n', '\n', '. ', '? ', '! ']:
                last_break = chunk.rfind(sep)
                if last_break > chunk_size * 0.5:
                    chunk = chunk[:last_break + len(sep)]
                    end = start + last_break + len(sep)
                    break
        
        chunks.append(chunk.strip())
        start = end - overlap
    
    return chunks
```

---

## Unified Schema Design

All three sources converge into:

1. **DOCUMENTS** table: One row per source document (article/page)
2. **DOCUMENT_CHUNKS** table: Multiple rows per document (chunks)

### Source Mapping

| Field | Freshdesk Source | GitBook Source | Notion Source |
|-------|-----------------|---------------|---------------|
| title | `title` | `title` | Page title property |
| content | `description_text` | `content_markdown` | Blocks → markdown |
| source_id | `article_id` | `page_id` | `page_id` |
| source_url | `helpdesk.revelator.com/a/{id}` | `path` | `notion.so/{id}` |
| created_at | `created_at` | `createdAt` | `created_time` |
| last_updated | `updated_at` | `updatedAt` | `last_edited_time` |
| status | `status == 2 → active` | `active` | `active` |

---

## Error Handling

### Common Failure Points
1. **API rate limits**: Implement exponential backoff (2s, 4s, 8s, 16s)
2. **Network timeouts**: Set 30s timeout on all API calls
3. **Malformed content**: Skip empty/null content, log warning
4. **Large pages**: Notion pages with 1000+ blocks — paginate block fetches
5. **Authentication failures**: Secrets expired — alert and retry

### Monitoring
```sql
-- Check task history for failures
SELECT name, state, error_code, error_message, scheduled_time
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
))
WHERE state = 'FAILED'
ORDER BY scheduled_time DESC;
```
