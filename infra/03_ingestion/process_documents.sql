CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.PROCESS_DOCUMENTS()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
AS
$$
import hashlib
import json
import re
from snowflake.snowpark import Session

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
MIN_CHUNK_CHARS = 200

def clean_html(text):
    if not text:
        return text
    text = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<!--[\s\S]*?-->', '', text)
    def _table_to_md(m):
        html = m.group(0)
        rows = re.findall(r'<tr[^>]*>([\s\S]*?)</tr>', html, re.IGNORECASE)
        md_rows = []
        for i, row in enumerate(rows):
            cells = re.findall(r'<(?:td|th)[^>]*>([\s\S]*?)</(?:td|th)>', row, re.IGNORECASE)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            md_rows.append('| ' + ' | '.join(cells) + ' |')
            if i == 0:
                md_rows.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
        return '\n'.join(md_rows)
    text = re.sub(r'<table[^>]*>[\s\S]*?</table>', _table_to_md, text, flags=re.IGNORECASE)
    text = re.sub(r'<strong[^>]*>([\s\S]*?)</strong>', r'**\1**', text, flags=re.IGNORECASE)
    text = re.sub(r'<b[^>]*>([\s\S]*?)</b>', r'**\1**', text, flags=re.IGNORECASE)
    text = re.sub(r'<em[^>]*>([\s\S]*?)</em>', r'*\1*', text, flags=re.IGNORECASE)
    text = re.sub(r'<i[^>]*>([\s\S]*?)</i>', r'*\1*', text, flags=re.IGNORECASE)
    text = re.sub(r'<code[^>]*>([\s\S]*?)</code>', r'`\1`', text, flags=re.IGNORECASE)
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>([\s\S]*?)</a>', r'[\2](\1)', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', r'- \1\n', text, flags=re.IGNORECASE)
    for level in range(1, 7):
        text = re.sub(
            rf'<h{level}[^>]*>([\s\S]*?)</h{level}>',
            lambda m, l=level: '#' * l + ' ' + m.group(1).strip() + '\n',
            text, flags=re.IGNORECASE
        )
    text = re.sub(r'<[^>]+>', '', text)
    try:
        import html as html_mod
        text = html_mod.unescape(text)
    except ImportError:
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def extract_section_map(text):
    section_map = []
    for m in re.finditer(r'^(#{1,4})\s+(.+)', text, re.MULTILINE):
        section_map.append((m.start(), m.group(2).strip()))
    return section_map

def get_section_for_position(section_map, char_position):
    current_section = None
    for pos, header in section_map:
        if pos <= char_position:
            current_section = header
        else:
            break
    return current_section

def build_prefix(title, section):
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if section:
        parts.append(f"Section: {section}")
    if parts:
        return '\n'.join(parts) + '\n\n'
    return ''

def merge_tiny_chunks(chunks, min_chars=400, max_chars=CHUNK_SIZE):
    if not chunks:
        return chunks
    merged = []
    i = 0
    while i < len(chunks):
        current = chunks[i]
        if len(current) < min_chars and merged and len(merged[-1]) + len(current) <= max_chars:
            merged[-1] = merged[-1].rstrip() + '\n\n' + current.strip()
        elif len(current) < min_chars and i + 1 < len(chunks) and len(current) + len(chunks[i + 1]) <= max_chars:
            chunks[i + 1] = current.rstrip() + '\n\n' + chunks[i + 1].strip()
        else:
            merged.append(current)
        i += 1
    return [c for c in merged if len(c.strip()) >= MIN_CHUNK_CHARS]

def chunk_text(text, title=None, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    if not text or len(text.strip()) < MIN_CHUNK_CHARS:
        return []
    text = clean_html(text)
    if not text or len(text.strip()) < MIN_CHUNK_CHARS:
        return []
    section_map = extract_section_map(text)
    prefix_overhead = len(build_prefix(title, "X" * 40))
    effective_size = chunk_size - prefix_overhead
    if effective_size < 300:
        effective_size = 300
    if len(text) <= effective_size:
        prefix = build_prefix(title, get_section_for_position(section_map, 0))
        return [prefix + text.strip() if prefix else text.strip()]
    chunks = []
    start = 0
    while start < len(text):
        end = start + effective_size
        chunk = text[start:end]
        if end < len(text):
            heading_match = None
            for m in re.finditer(r'\n(?=#{1,4}\s)', chunk):
                if m.start() > effective_size * 0.3:
                    heading_match = m
            if heading_match:
                chunk = chunk[:heading_match.start()]
                end = start + heading_match.start()
            else:
                for sep in ['\n\n', '\n', '. ', '? ', '! ']:
                    last_break = chunk.rfind(sep)
                    if last_break > effective_size * 0.5:
                        chunk = chunk[:last_break + len(sep)]
                        end = start + last_break + len(sep)
                        break
        section = get_section_for_position(section_map, start)
        prefix = build_prefix(title, section)
        chunk = prefix + chunk.strip() if prefix else chunk.strip()
        if chunk:
            chunks.append(chunk)
        start = max(end - overlap, start + 1)
    chunks = merge_tiny_chunks(chunks)
    return chunks

def make_id(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]

def content_hash(text):
    normalized = re.sub(r'\s+', ' ', (text or '').strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]

def dedup_rows(rows, content_field, id_field):
    seen_hashes = {}
    unique = []
    for row in rows:
        h = content_hash(row[content_field] or '')
        if h not in seen_hashes:
            seen_hashes[h] = row[id_field]
            unique.append(row)
    return unique

def insert_doc(session, doc_id, source_system, source_id, source_url, title, content, created_at, updated_at, metadata, doc_type=None):
    safe = lambda s: str(s).replace("'", "''") if s else ""
    created_expr = f"'{created_at}'" if created_at else "CURRENT_TIMESTAMP()"
    updated_expr = f"'{updated_at}'" if updated_at else "CURRENT_TIMESTAMP()"
    meta = json.dumps(metadata) if metadata else "{}"
    if doc_type:
        meta_dict = metadata if metadata else {}
        meta_dict["doc_type"] = doc_type
        meta = json.dumps(meta_dict)
    session.sql(f"""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
            (document_id, source_system, source_id, source_url, title, content,
             content_length, tags, status, created_at, last_updated, metadata)
        SELECT '{doc_id}', '{safe(source_system)}', '{safe(str(source_id))}',
            '{safe(source_url)}', '{safe(title)}',
            '{safe(content[:100000])}', {len(content)},
            PARSE_JSON('[]'), 'active',
            {created_expr}, {updated_expr},
            PARSE_JSON('{safe(meta)}')
    """).collect()
    return updated_expr

def insert_chunks(session, doc_id, title, source_system, source_url, updated_expr, content, skip_chunking=False):
    safe = lambda s: str(s).replace("'", "''") if s else ""
    if skip_chunking:
        cleaned = clean_html(content)
        if not cleaned or len(cleaned.strip()) < MIN_CHUNK_CHARS:
            return 0
        prefix = build_prefix(title, None)
        full_chunk = prefix + cleaned.strip() if prefix else cleaned.strip()
        chunks_text = [full_chunk]
    else:
        chunks_text = chunk_text(content, title=title)
    for i, chunk in enumerate(chunks_text):
        chunk_id = make_id(doc_id, i)
        safe_chunk = chunk.replace("'", "''")[:50000]
        session.sql(f"""
            INSERT INTO SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
                (chunk_id, document_id, chunk_index, content, content_length,
                 title, source_system, source_url, last_updated, status)
            SELECT '{chunk_id}', '{doc_id}', {i},
                '{safe_chunk}', {len(chunk)},
                '{safe(title)}', '{safe(source_system)}',
                '{safe(source_url)}', {updated_expr}, 'active'
        """).collect()
    return len(chunks_text)

def process_gitbook(session):
    session.sql("DELETE FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS WHERE SOURCE_SYSTEM = 'gitbook'").collect()
    session.sql("DELETE FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS WHERE SOURCE_SYSTEM = 'gitbook'").collect()
    total_docs = 0
    total_chunks = 0
    gb = session.table("SNOWFLAKE_INTELLIGENCE.RAW.GITBOOK_PAGES").collect()
    gb = dedup_rows(gb, "CONTENT_MARKDOWN", "PAGE_ID")
    for row in gb:
        doc_id = make_id("gitbook", row["PAGE_ID"])
        content = row["CONTENT_MARKDOWN"] or ""
        if not content.strip() or len(content.strip()) < MIN_CHUNK_CHARS:
            continue
        title = row["TITLE"] or "Untitled"
        source_url = row["PATH"] if row["PATH"] else ""
        space_title = row["SPACE_TITLE"] if row["SPACE_TITLE"] else ""
        created_at = row["CREATED_AT"] if row["CREATED_AT"] else None
        updated_at = row["UPDATED_AT"] if row["UPDATED_AT"] else None
        metadata = {"space_id": str(row["SPACE_ID"]), "space_title": str(space_title)}
        updated_expr = insert_doc(session, doc_id, "gitbook", row["PAGE_ID"], source_url, title, content, created_at, updated_at, metadata)
        total_docs += 1
        total_chunks += insert_chunks(session, doc_id, title, "gitbook", source_url, updated_expr, content)
    return total_docs, total_chunks

def process_freshdesk(session):
    session.sql("DELETE FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS WHERE SOURCE_SYSTEM = 'freshdesk'").collect()
    session.sql("DELETE FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS WHERE SOURCE_SYSTEM = 'freshdesk'").collect()
    total_docs = 0
    total_chunks = 0

    articles = session.table("SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_SOLUTION_ARTICLES").collect()
    articles = dedup_rows(articles, "DESCRIPTION_TEXT", "ID")
    for row in articles:
        title = row["TITLE"] or "Untitled"
        description = row["DESCRIPTION_TEXT"] or ""
        content = f"{title}\n\n{description}".strip()
        if not content or len(content.strip()) < MIN_CHUNK_CHARS:
            continue
        doc_id = make_id("freshdesk", "article", row["ID"])
        source_url = f"https://support.freshdesk.com/a/solutions/articles/{row['ID']}"
        created_at = row["CREATED_AT"] if row["CREATED_AT"] else None
        updated_at = row["UPDATED_AT"] if row["UPDATED_AT"] else None
        metadata = {"doc_type": "article", "folder_id": str(row["FOLDER_ID"]), "category_id": str(row["CATEGORY_ID"]), "status": str(row["STATUS"])}
        updated_expr = insert_doc(session, doc_id, "freshdesk", row["ID"], source_url, title, content, created_at, updated_at, metadata, doc_type="article")
        total_docs += 1
        total_chunks += insert_chunks(session, doc_id, title, "freshdesk", source_url, updated_expr, content)

    conversations = session.sql("""
        SELECT c.ID AS CONV_ID, c.TICKET_ID, c.BODY_TEXT, c.CREATED_AT AS CONV_CREATED,
               c.UPDATED_AT AS CONV_UPDATED, t.SUBJECT, t.UPDATED_AT AS TICKET_UPDATED
        FROM SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKET_CONVERSATIONS c
        JOIN SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_TICKETS t ON c.TICKET_ID = t.ID
    """).collect()
    for row in conversations:
        subject = row["SUBJECT"] or "Untitled Ticket"
        body = row["BODY_TEXT"] or ""
        content = f"{subject}\n\n{body}".strip()
        if not content or len(content.strip()) < MIN_CHUNK_CHARS:
            continue
        doc_id = make_id("freshdesk", "conversation", row["CONV_ID"])
        source_url = f"https://support.freshdesk.com/a/tickets/{row['TICKET_ID']}"
        created_at = row["CONV_CREATED"] if row["CONV_CREATED"] else None
        updated_at = row["CONV_UPDATED"] if row["CONV_UPDATED"] else None
        metadata = {"doc_type": "conversation", "ticket_id": str(row["TICKET_ID"])}
        updated_expr = insert_doc(session, doc_id, "freshdesk", row["CONV_ID"], source_url, subject, content, created_at, updated_at, metadata, doc_type="conversation")
        total_docs += 1
        is_short = len(content.strip()) <= CHUNK_SIZE
        total_chunks += insert_chunks(session, doc_id, subject, "freshdesk", source_url, updated_expr, content, skip_chunking=is_short)

    discussions = session.sql("""
        SELECT dc.ID AS COMMENT_ID, dc.TOPIC_ID, dc.BODY_TEXT, dc.CREATED_AT AS COMMENT_CREATED,
               dc.UPDATED_AT AS COMMENT_UPDATED, dt.TITLE AS TOPIC_TITLE, dt.FORUM_ID
        FROM SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_COMMENTS dc
        JOIN SNOWFLAKE_INTELLIGENCE.RAW.FRESHDESK_DISCUSSION_TOPICS dt ON dc.TOPIC_ID = dt.ID
    """).collect()
    for row in discussions:
        topic_title = row["TOPIC_TITLE"] or "Untitled Discussion"
        body = row["BODY_TEXT"] or ""
        content = f"{topic_title}\n\n{body}".strip()
        if not content or len(content.strip()) < MIN_CHUNK_CHARS:
            continue
        doc_id = make_id("freshdesk", "discussion", row["COMMENT_ID"])
        source_url = f"https://support.freshdesk.com/a/discussions/topics/{row['TOPIC_ID']}"
        created_at = row["COMMENT_CREATED"] if row["COMMENT_CREATED"] else None
        updated_at = row["COMMENT_UPDATED"] if row["COMMENT_UPDATED"] else None
        metadata = {"doc_type": "discussion", "topic_id": str(row["TOPIC_ID"]), "forum_id": str(row["FORUM_ID"])}
        updated_expr = insert_doc(session, doc_id, "freshdesk", row["COMMENT_ID"], source_url, topic_title, content, created_at, updated_at, metadata, doc_type="discussion")
        total_docs += 1
        is_short = len(content.strip()) <= CHUNK_SIZE
        total_chunks += insert_chunks(session, doc_id, topic_title, "freshdesk", source_url, updated_expr, content, skip_chunking=is_short)

    return total_docs, total_chunks

def run(session):
    gb_docs, gb_chunks = process_gitbook(session)
    fd_docs, fd_chunks = process_freshdesk(session)
    total_docs = gb_docs + fd_docs
    total_chunks = gb_chunks + fd_chunks
    return f"Processed {total_docs} documents into {total_chunks} chunks (gitbook: {gb_docs} docs/{gb_chunks} chunks, freshdesk: {fd_docs} docs/{fd_chunks} chunks)"
$$;
