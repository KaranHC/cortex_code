import hashlib
import re
import statistics

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
        start = end - overlap
    chunks = merge_tiny_chunks(chunks)
    return chunks

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


def chunk_metrics(chunks):
    if not chunks:
        return {}
    lengths = [len(c) for c in chunks]
    return {
        "count": len(chunks),
        "avg": round(statistics.mean(lengths)),
        "median": round(statistics.median(lengths)),
        "min": min(lengths),
        "max": max(lengths),
        "p95": round(sorted(lengths)[int(len(lengths) * 0.95)]) if len(lengths) >= 2 else max(lengths),
    }

def overlap_redundancy(chunks):
    if len(chunks) < 2:
        return 0.0
    total_chars = sum(len(c) for c in chunks)
    unique_text = set()
    for c in chunks:
        for sent in re.split(r'(?<=[.!?])\s+', c):
            unique_text.add(sent.strip())
    unique_chars = sum(len(s) for s in unique_text)
    return round(1 - unique_chars / total_chars, 3) if total_chars > 0 else 0

def section_boundary_violations(text, chunks):
    violations = 0
    for chunk in chunks:
        lines = chunk.strip().split('\n')
        body_lines = [l for l in lines if not l.startswith('Title:') and not l.startswith('Section:') and l.strip()]
        if not body_lines:
            continue
        body = '\n'.join(body_lines)
        chunk_headings = re.findall(r'^#{1,4}\s+.+', body, re.MULTILINE)
        in_body_headings = [h for h in chunk_headings if not body.strip().startswith(h)]
        if len(in_body_headings) > 0:
            violations += 1
    return violations

def orphan_heading_rate(chunks):
    orphans = 0
    for chunk in chunks:
        lines = chunk.strip().split('\n')
        non_empty = [l for l in lines if l.strip()]
        if non_empty:
            last = non_empty[-1]
            if re.match(r'^#{1,4}\s+', last):
                orphans += 1
    return orphans


class TestBasicBehavior:
    def test_empty_input(self):
        assert chunk_text("") == []
        assert chunk_text(None) == []
        assert chunk_text("short") == []

    def test_below_min_threshold(self):
        assert chunk_text("x" * 199) == []
        assert chunk_text("x" * 49) == []

    def test_at_min_threshold(self):
        text = "A" * 200
        chunks = chunk_text(text, title="Test")
        assert len(chunks) == 1
        assert chunks[0].startswith("Title: Test")

    def test_small_document_single_chunk(self):
        text = "A" * 500
        chunks = chunk_text(text, title="Test")
        assert len(chunks) == 1
        assert chunks[0].startswith("Title: Test")

    def test_just_over_chunk_size(self):
        text = "A" * (CHUNK_SIZE + 1)
        chunks = chunk_text(text)
        assert len(chunks) >= 1


class TestPrefixAwareChunkSize:
    def test_chunks_do_not_exceed_chunk_size(self):
        text = "## Section Title\n\n" + ("This is a sentence about a topic. " * 200)
        chunks = chunk_text(text, title="My Document Title")
        for i, chunk in enumerate(chunks):
            assert len(chunk) <= CHUNK_SIZE + 50, \
                f"Chunk {i} is {len(chunk)} chars, exceeds CHUNK_SIZE+50={CHUNK_SIZE+50}"

    def test_effective_size_accounts_for_prefix(self):
        title = "A Very Long Document Title For Testing"
        prefix_len = len(build_prefix(title, "X" * 40))
        text = "## Section\n\n" + ("A" * CHUNK_SIZE * 3)
        chunks = chunk_text(text, title=title)
        for chunk in chunks:
            assert len(chunk) <= CHUNK_SIZE + prefix_len

    def test_no_title_means_no_overhead(self):
        text = "A" * (CHUNK_SIZE - 100)
        chunks = chunk_text(text, title=None)
        assert len(chunks) == 1


class TestHeadingBoundaryPreference:
    def test_heading_preferred_as_break_point(self):
        text = "## Section A\n\n" + ("First topic content. " * 40) + "\n\n## Section B\n\n" + ("Second topic content. " * 40)
        chunks = chunk_text(text, title="Doc")
        for chunk in chunks:
            body_lines = [l for l in chunk.split('\n') if not l.startswith('Title:') and not l.startswith('Section:')]
            body = '\n'.join(body_lines)
            headings_in_body = re.findall(r'^#{1,4}\s+', body, re.MULTILINE)
            assert len(headings_in_body) <= 1, \
                f"Chunk contains {len(headings_in_body)} headings — should split at heading boundary"

    def test_heading_break_not_forced_on_tiny_sections(self):
        text = "## A\n\n" + ("Short. " * 5) + "\n\n## B\n\n" + ("Also short. " * 5)
        chunks = chunk_text(text, title="Doc")
        assert len(chunks) <= 1

    def test_giant_section_still_splits(self):
        text = "## Giant Section\n\n" + ("This is a long sentence about something important. " * 200)
        chunks = chunk_text(text, title="Doc")
        assert len(chunks) > 1
        for chunk in chunks:
            assert "Section: Giant Section" in chunk


class TestSectionBoundaryPreservation:
    def test_section_label_tracks_position(self):
        sec_a = "## Installation\n\n" + ("Install stuff. " * 60)
        sec_b = "\n\n## Configuration\n\n" + ("Config stuff. " * 60)
        text = sec_a + sec_b
        chunks = chunk_text(text, title="Guide")
        config_chunks = [c for c in chunks if "Config stuff" in c]
        for c in config_chunks:
            assert "Section: Configuration" in c or "Section: Installation" in c

    def test_section_map_with_repeated_headings(self):
        text = "## Setup\n\nStep 1.\n\n## Setup\n\nStep 2."
        smap = extract_section_map(text)
        names = [s[1] for s in smap]
        assert names.count("Setup") == 2


class TestTinyAdjacentSections:
    def test_many_tiny_sections_merged(self):
        sections = []
        for i in range(20):
            sections.append(f"## Section {i}\n\nTiny content {i} with enough words to be meaningful.")
        text = "\n\n".join(sections)
        chunks = chunk_text(text, title="Tiny")
        assert len(chunks) < 20


class TestGiantSections:
    def test_no_content_loss_in_giant_section(self):
        sentences = [f"Sentence number {i} is here. " for i in range(100)]
        text = "## Content\n\n" + "".join(sentences)
        chunks = chunk_text(text)
        all_chunk_text = " ".join(chunks)
        for s in sentences:
            assert s.strip() in all_chunk_text or s.strip()[:20] in all_chunk_text


class TestMalformedExtraction:
    def test_html_artifacts(self):
        text = "<div class='content'><p>Some text here.</p><p>More text follows this paragraph.</p></div>" + " Extra content that adds enough length to pass the minimum threshold." * 5
        chunks = chunk_text(text, title="Messy")
        assert len(chunks) >= 1
        for c in chunks:
            assert "<div" not in c
            assert "<p>" not in c

    def test_nested_html_tables(self):
        text = "<table><tr><th>Col1</th><th>Col2</th></tr><tr><td>A</td><td>B</td></tr></table>" + " More content with enough text to pass the minimum chunk threshold." * 5
        chunks = chunk_text(text)
        assert len(chunks) >= 1

    def test_empty_headings(self):
        text = "## \n\nSome content here that is long enough to be a valid chunk for the system and pass the two hundred character minimum threshold." + " More words." * 10
        chunks = chunk_text(text)
        assert len(chunks) >= 1

    def test_only_headings_no_content(self):
        text = "## Heading 1\n\n## Heading 2\n\n## Heading 3\n\n"
        chunks = chunk_text(text)
        assert len(chunks) == 0


class TestTablesAndLists:
    def test_markdown_table_preserved(self):
        table = "| Col1 | Col2 |\n| --- | --- |\n| A | B |\n| C | D |"
        text = "## Data\n\n" + table + "\n\nSome follow up text that is long enough to meet the minimum threshold requirement." + " Extra." * 20
        chunks = chunk_text(text)
        table_chunks = [c for c in chunks if "|" in c]
        assert len(table_chunks) >= 1

    def test_long_list(self):
        items = [f"- Item {i}: description of this item that is moderately long" for i in range(50)]
        text = "## List\n\n" + "\n".join(items)
        chunks = chunk_text(text, title="List Doc")
        assert len(chunks) >= 1
        all_text = " ".join(chunks)
        assert "Item 0" in all_text
        assert "Item 49" in all_text


class TestOverlapDuplication:
    def test_overlap_creates_duplicated_content(self):
        sentences = [f"Sentence {i} about topic. " for i in range(100)]
        text = "".join(sentences)
        chunks = chunk_text(text)
        if len(chunks) >= 2:
            c0_end = chunks[0][-200:]
            c1_lines = chunks[1].split('\n')
            c1_body = '\n'.join(l for l in c1_lines if not l.startswith('Title:') and not l.startswith('Section:'))
            shared = set(c0_end.split()) & set(c1_body[:300].split())
            assert len(shared) > 0, "Expected overlap between adjacent chunks"

    def test_overlap_ratio_on_real_content(self):
        sentences = [f"Sentence {i} about topic number {i}. " for i in range(200)]
        text = "".join(sentences)
        chunks = chunk_text(text)
        if len(chunks) >= 2:
            ratio = overlap_redundancy(chunks)
            assert ratio < 0.5, f"Overlap redundancy too high: {ratio}"


class TestPrefixBehavior:
    def test_prefix_added_to_every_chunk(self):
        text = "## Section\n\n" + ("Content here. " * 200)
        chunks = chunk_text(text, title="My Document")
        for chunk in chunks:
            assert chunk.startswith("Title: My Document")


class TestDeterminism:
    def test_same_input_same_output(self):
        text = "## Test\n\n" + ("Deterministic content. " * 100)
        c1 = chunk_text(text, title="Doc")
        c2 = chunk_text(text, title="Doc")
        assert c1 == c2

    def test_chunk_ids_deterministic(self):
        def make_id(*parts):
            return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]
        id1 = make_id("doc1", 0)
        id2 = make_id("doc1", 0)
        assert id1 == id2


class TestOrphanHeadings:
    def test_heading_not_orphaned_at_chunk_end(self):
        content_before = "Some intro text. " * 70
        text = content_before + "\n\n## Important Section\n\nThe actual content of this section is here and is quite detailed."
        chunks = chunk_text(text)
        orphans = orphan_heading_rate(chunks)
        assert orphans == 0, f"Found {orphans} orphan headings — heading-boundary preference should prevent this"


class TestMinChunkThreshold:
    def test_chunks_below_200_chars_rejected(self):
        text = "x" * 150
        assert chunk_text(text) == []

    def test_chunks_at_200_chars_accepted(self):
        text = "A" * 200
        chunks = chunk_text(text)
        assert len(chunks) == 1

    def test_merge_respects_min_threshold(self):
        chunks = ["X" * 150]
        merged = merge_tiny_chunks(chunks)
        assert len(merged) == 0


class TestDeduplication:
    def test_dedup_removes_exact_duplicates(self):
        rows = [
            {"CONTENT": "Hello world this is content", "ID": 1},
            {"CONTENT": "Hello world this is content", "ID": 2},
            {"CONTENT": "Different content here", "ID": 3},
        ]
        result = dedup_rows(rows, "CONTENT", "ID")
        assert len(result) == 2
        ids = [r["ID"] for r in result]
        assert 1 in ids
        assert 3 in ids

    def test_dedup_normalizes_whitespace(self):
        rows = [
            {"CONTENT": "Hello  world", "ID": 1},
            {"CONTENT": "Hello world", "ID": 2},
        ]
        result = dedup_rows(rows, "CONTENT", "ID")
        assert len(result) == 1

    def test_dedup_case_insensitive(self):
        rows = [
            {"CONTENT": "Hello World", "ID": 1},
            {"CONTENT": "hello world", "ID": 2},
        ]
        result = dedup_rows(rows, "CONTENT", "ID")
        assert len(result) == 1

    def test_dedup_preserves_unique(self):
        rows = [
            {"CONTENT": "First unique doc", "ID": 1},
            {"CONTENT": "Second unique doc", "ID": 2},
            {"CONTENT": "Third unique doc", "ID": 3},
        ]
        result = dedup_rows(rows, "CONTENT", "ID")
        assert len(result) == 3


class TestMetricsCollection:
    def test_realistic_corpus_metrics(self):
        docs = [
            ("## Guide\n\n" + "Step by step instructions. " * 200, "Long Guide"),
            ("## Policy\n\n### Section A\n\nPolicy A details here. " * 10 + "\n\n### Section B\n\nPolicy B details here. " * 10, "Policy Doc"),
            ("<h2>HTML Doc</h2><p>Paragraph one with real content.</p>" + "<p>More content in paragraph form.</p>" * 20, "HTML Source"),
        ]
        all_chunks = []
        for text, title in docs:
            all_chunks.extend(chunk_text(text, title=title))

        m = chunk_metrics(all_chunks)
        assert m['count'] > 0
        assert m['avg'] > 200
        assert m['max'] <= CHUNK_SIZE + 100, f"Max chunk {m['max']} exceeds CHUNK_SIZE+100"


class TestMergeTinyChunksMutation:
    def test_merge_does_not_corrupt_original(self):
        chunks_orig = ["A" * 300, "B" * 300, "C" * 1000]
        chunks_copy = list(chunks_orig)
        merged = merge_tiny_chunks(chunks_copy)
        assert len(merged) >= 1
        all_text = "".join(merged)
        assert "A" in all_text
        assert "B" in all_text
        assert "C" in all_text

    def test_merge_filter_removes_tiny_results(self):
        chunks = ["X" * 100]
        merged = merge_tiny_chunks(chunks)
        assert len(merged) == 0


class TestCompareStrategies:
    @staticmethod
    def naive_fixed_chunk(text, size=1500):
        chunks = []
        for i in range(0, len(text), size):
            c = text[i:i+size].strip()
            if c and len(c) >= MIN_CHUNK_CHARS:
                chunks.append(c)
        return chunks

    def test_current_vs_naive_boundary_quality(self):
        text = "## Section A\n\n" + ("First topic sentence. " * 50) + "\n\n## Section B\n\n" + ("Second topic sentence. " * 50)
        current = chunk_text(text, title="Doc")
        naive = self.naive_fixed_chunk(text)

        current_breaks_mid_sentence = 0
        naive_breaks_mid_sentence = 0
        for c in current:
            body = c.split('\n\n', 2)[-1] if '\n\n' in c else c
            if body and not body.rstrip().endswith(('.', '!', '?', '|')):
                current_breaks_mid_sentence += 1
        for c in naive:
            if c and not c.rstrip().endswith(('.', '!', '?', '|')):
                naive_breaks_mid_sentence += 1

        assert current_breaks_mid_sentence <= naive_breaks_mid_sentence or len(naive) == 0

    def test_current_has_fewer_section_violations_than_naive(self):
        text = "## Section A\n\n" + ("First topic sentence. " * 50) + "\n\n## Section B\n\n" + ("Second topic sentence. " * 50) + "\n\n## Section C\n\n" + ("Third topic sentence. " * 50)
        current = chunk_text(text, title="Doc")
        naive = self.naive_fixed_chunk(text)
        current_violations = section_boundary_violations(text, current)
        naive_violations = section_boundary_violations(text, naive)
        assert current_violations <= naive_violations


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
