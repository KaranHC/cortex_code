# PLAN 4: Snowflake Intelligence & Agent Improvements

> Systematic improvement plan to fix ALL 20 anti-practices, reach 95%+ accuracy,
> and build production-grade RAG search quality.
> Reference: [Build agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-intelligence/build-agents),
> [Best Practices for Building Cortex Agents](https://www.snowflake.com/en/developers/guides/best-practices-to-building-cortex-agents/)

---

## Current State Audit (March 2026)

### System Inventory

| Component | Value |
|-----------|-------|
| Primary Agent | `KNOWLEDGE_ASSISTANT` — claude-sonnet-4-6 |
| Fallback Agent | `KNOWLEDGE_ASSISTANT_FALLBACK` — claude-haiku-4-5 |
| Fallback Agent 2 | `KNOWLEDGE_ASSISTANT_FALLBACK_2` — openai-gpt-5.2 |
| Search Service | `DOCUMENT_SEARCH` — 935 active chunks, `snowflake-arctic-embed-m-v1.5` |
| Eval Dataset | 18 questions (6 categories, 7 product areas, 3 difficulties) |
| Baseline Accuracy | Primary ~69-92%, Fallback 72.2%, Fallback_2 66.7% |
| Tests | 37 static + 42 integration — all passing |

### Verified Gaps

| Gap | Severity | Current State | Target |
|-----|----------|---------------|--------|
| Title prefix on chunks | CRITICAL | 28% (262/935) have "Title:" prefix | 100% |
| Section header enrichment | CRITICAL | 0% have section context | 100% |
| TEAM/OWNER fill rate | HIGH | 0% populated | 80%+ |
| HTML contamination | HIGH | 12 chunks with HTML tags/CSS | 0 |
| Tiny chunks (<100 tokens) | MEDIUM | 65 chunks | 0 |
| Stale docs (>6 months) | HIGH | 863/942 = 92% | Flagged + decay-scored |
| Query expansion | CRITICAL | Not implemented (agents only "reformulate") | 3-query structured |
| Confidence-based fallback | HIGH | Exception-only (`except: pass`) | Score-based routing |
| Agent spec: `columns_and_descriptions` | HIGH | Missing — agent can't understand column semantics | Fully described |
| Agent spec: `budget` | MEDIUM | Missing — no token/time limits | `seconds: 30, tokens: 16000` |
| Agent spec: `sample_questions` | MEDIUM | Missing — no few-shot examples | 5 per agent |
| Agent spec: `filter` in tool_resources | HIGH | Missing — no default filters | `status: active` |
| Agent spec: temporal context | HIGH | No CURRENT_DATE injection | Injected dynamically |
| Agent spec: negative constraints | CRITICAL | No explicit "do NOT" rules | Full constraint block |
| Caching | MEDIUM | None — every query hits agent | Session-level + TTL cache |
| Intent classification | LOW | None — all queries same pipeline | Pre-route by intent |
| Answer strength action | MEDIUM | Display-only badges | Trigger clarification on low |
| Race condition in log_question() | HIGH | `MAX(QUESTION_ID)` — race-prone | Client-side UUID |
| Dead code | LOW | `search_client.py` never called | Integrated or removed |
| Request tracing | HIGH | No trace_id, no latency breakdown | Full observability |
| Eval dataset size | CRITICAL | 18 questions | 55+ hard QA pairs |
| Native evaluation | CRITICAL | Not set up | EXECUTE_AI_EVALUATION |

### Anti-Practices Audit (17/20 violated → Target: 0/20)

| # | Anti-Practice | Violated? | Fix Phase | Fix Section |
|---|--------------|-----------|-----------|-------------|
| 1 | Single search query (no expansion) | YES | Phase 1 | 1.4 |
| 2 | Raw text without semantic enrichment | YES — 72% unenriched | Phase 2 | 2.1, 2.2 |
| 3 | No negative constraints in prompt | YES | Phase 1 | 1.6 |
| 4 | Fixed-size chunking ignoring structure | PARTIAL — paragraph-aware, no section awareness | Phase 2 | 2.2 |
| 5 | HTML/noise in chunks | YES — 12 chunks | Phase 2 | 2.3 |
| 6 | No eval dataset | PARTIAL — 18 questions, too small | See PLAN 5 | — |
| 7 | Over-stuffing prompt with irrelevant context | NO | — | — |
| 8 | Swallowing errors silently | YES — `except Exception: pass` | Phase 3 | 3.1 |
| 9 | No attribute filtering | YES — attributes defined, never used | Phase 1 | 1.8 |
| 10 | Happy-path-only eval | YES — no negative/OOS test cases | See PLAN 5 | — |
| 11 | Ignoring temporal context | YES — no CURRENT_DATE | Phase 1 | 1.5 |
| 12 | No caching layer | YES | Phase 3 | 3.4 |
| 13 | Monolithic agent (no intent routing) | YES | Phase 3 | 3.5 |
| 14 | No source grounding enforcement | YES — optional not required | Phase 1 | 1.7 |
| 15 | MAX(id) race condition | YES — in log_question() | Phase 3 | 3.2 |
| 16 | Dead/unused code | YES — search_client.py | Phase 3 | 3.3 |
| 17 | No observability/tracing | YES | Phase 3 | 3.6 |
| 18 | Stale docs without decay scoring | YES — 92% >6mo | Phase 2 | 2.5 |
| 19 | No regression testing pipeline | YES | See PLAN 5 | — |
| 20 | Not acting on answer_strength | YES — display only | Phase 3 | 3.7 |

---

## Phase 1: Agent Spec Engineering (CRITICAL — Highest Impact)

**File**: `infra/04_intelligence/cortex_agents.sql`

Per Snowflake docs: "Unclear tool descriptions create cascading failures and lead to hallucinations."

### 1.1 Add Orchestration Budget

Current: no budget set — agent can run indefinitely, consuming unlimited tokens.

```yaml
orchestration:
  budget:
    seconds: 45
    tokens: 16000
```

> **Note**: 45 seconds allows 3 sequential search calls + synthesis. If queries
> consistently timeout, increase to 60s. The `budget` key is nested under
> `orchestration:` (not at the top level).

### 1.2 Add `sample_questions`

Per Snowflake best practices, sample questions help the agent understand expected interaction patterns.

```yaml
sample_questions:
  - question: "How do royalty splits work in Revelator?"
    answer: "I'll search the knowledge base for information about royalty splits and the Original Works Protocol."
  - question: "What are the steps to distribute a catalogue to stores?"
    answer: "I'll look up the distribution process documentation for store delivery."
  - question: "How does Revelator match catalog to DSP revenue?"
    answer: "I'll search for DSP revenue matching and catalog reconciliation documentation."
  - question: "What is the onboarding process for new clients?"
    answer: "I'll search the onboarding documentation for the client setup process."
  - question: "How do I approve royalty statements?"
    answer: "I'll look up the royalty statement approval workflow documentation."
```

### 1.3 Add `columns_and_descriptions` to Cortex Search Tool

Current: no column descriptions — agent cannot understand what to filter on.

```yaml
tool_resources:
  search_docs:
    name: SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH
    max_results: "10"
    title_column: "title"
    id_column: "chunk_id"
    filter:
      "@eq":
        status: "active"
    columns_and_descriptions:
      content:
        description: "The main text content of the document chunk. Contains product documentation, FAQs, operational procedures, billing policies, and technical guides. Each chunk is prefixed with 'Title: {title}' and optionally 'Section: {section}' for context."
        type: "string"
        searchable: true
        filterable: false
      title:
        description: "The document title. Use to narrow search to a specific document."
        type: "string"
        searchable: true
        filterable: true
      topic:
        description: "Document classification topic. Values: Product Documentation, Support Process, Onboarding, Billing Policy, Operational Procedure, Ownership Directory, Technical Guide, FAQ, Release Notes, Training Material."
        type: "string"
        searchable: false
        filterable: true
      product_area:
        description: "Product area classification. Values: Royalties, DSP, Distribution, Billing, Onboarding, Analytics, Rights Management, Content Delivery, Account Management, General."
        type: "string"
        searchable: false
        filterable: true
      source_system:
        description: "Origin system of the document. Currently: gitbook. Future: freshdesk, notion, manual."
        type: "string"
        searchable: false
        filterable: true
      team:
        description: "Team responsible for this document. Values include: Support, Engineering, Product, Finance, Operations. May be NULL for unassigned documents."
        type: "string"
        searchable: false
        filterable: true
      owner:
        description: "Knowledge owner — the person responsible for maintaining this document. Use for routing escalations."
        type: "string"
        searchable: false
        filterable: true
      last_updated:
        description: "When the document was last modified. Use to filter for recent or historical content. Prefer documents with recent dates."
        type: "string"
        searchable: false
        filterable: true
      source_url:
        description: "URL to the original source document. Include in citations. NEVER fabricate URLs."
        type: "string"
        searchable: false
        filterable: false
```

### 1.4 Structured 3-Query Expansion Protocol

**Anti-practice fixed: #1 "Single search query"**

Add to agent instructions:

```
QUERY EXPANSION PROTOCOL (MANDATORY — execute for EVERY question):
For every user question, execute exactly 3 searches before synthesizing an answer:

Search 1 — KEYWORD EXTRACTION:
  Extract the 3-5 most specific terms from the question. Search with those exact terms.
  Example: "How do royalty splits work?" → search "royalty splits percentage allocation"

Search 2 — SEMANTIC PARAPHRASE:
  Rephrase the question as a declarative statement using synonyms and related concepts.
  Example: "How do royalty splits work?" → search "revenue sharing distribution mechanism rights holders"

Search 3 — BROADER CONTEXT:
  Search the parent topic or category that encompasses the question.
  Example: "How do royalty splits work?" → search "Original Works Protocol payment processing"

After all 3 searches:
- Deduplicate results by chunk_id (same chunk from multiple searches = higher relevance signal)
- Chunks appearing in 2+ searches should be weighted higher in your synthesis
- If Search 1 returns 0 results but Search 2 or 3 do, the question may use non-standard terminology — note this in your answer
- If ALL 3 searches return 0 relevant results, set answer_strength to "no_answer"
```

### 1.5 Temporal Context Injection

**Anti-practice fixed: #11 "Ignoring temporal context"**

Add to system/orchestration instructions. Must be dynamically generated at CREATE AGENT time:

```
TEMPORAL CONTEXT:
Today's date is [CURRENT_DATE]. Use this for reasoning about time-relative queries.
- "Recent" means within the last 90 days from today.
- "Current quarter" means Q1 2026 (January-March 2026).
- "This year" means 2026.
- If a document's last_updated is more than 180 days ago, prepend a warning:
  "Note: This information was last updated on [date] and may be outdated."
- For questions like "What changed recently?", filter or sort by last_updated DESC
  and only present documents updated within the last 90 days.
- If no documents match the temporal filter, explicitly say:
  "No recent updates found. The latest information available is from [date]."
```

Implementation — use dynamic SQL in the agent creation script:

```sql
SET current_date_str = CURRENT_DATE()::VARCHAR;
SET current_quarter = CASE
    WHEN MONTH(CURRENT_DATE()) <= 3 THEN 'Q1'
    WHEN MONTH(CURRENT_DATE()) <= 6 THEN 'Q2'
    WHEN MONTH(CURRENT_DATE()) <= 9 THEN 'Q3'
    ELSE 'Q4'
END || ' ' || YEAR(CURRENT_DATE())::VARCHAR;
```

Then interpolate `$current_date_str` and `$current_quarter` into the YAML spec.

### 1.6 Negative Constraints Block

**Anti-practice fixed: #3 "No negative constraints"**

Add to instructions:

```
CONSTRAINTS (NEVER VIOLATE — these are hard rules, not suggestions):
1. NEVER fabricate information not found in search results. If you don't find it, say so.
2. NEVER guess URLs — ONLY return source_url values retrieved from search results.
   If a search result has no source_url, omit the URL field entirely.
3. NEVER answer questions outside the Revelator business domain (music distribution,
   royalties, DSPs, billing, onboarding, rights management, analytics, content delivery).
   For out-of-domain questions, return answer_strength "no_answer" with a polite redirect.
4. If no relevant results found after all 3 searches, return answer_strength "no_answer" —
   do NOT attempt to answer from your training data.
5. NEVER combine information from different documents without explicitly noting:
   "Combining information from [Source A] and [Source B]:"
6. If documents conflict, present BOTH versions and explicitly flag the conflict:
   "Note: These documents provide conflicting information..."
7. NEVER provide financial, legal, or medical advice even if documentation touches these areas.
   Redirect to appropriate teams.
8. NEVER invent knowledge owner names. Only return owners from search result metadata.
9. NEVER claim certainty when answer_strength is "weak" — always qualify with
   "Based on limited information..." or "I found only tangential references..."
10. If a question asks about a feature that doesn't appear in ANY search result,
    do NOT speculate about whether it exists. Say "I could not find documentation about this feature."
```

### 1.7 Source Grounding Enforcement

**Anti-practice fixed: #14 "No source grounding enforcement"**

Add to instructions:

```
SOURCE GROUNDING (MANDATORY — every answer must follow these rules):

Citation Format:
- Every factual claim MUST cite at least one source: [Source: Document Title](source_url)
- If combining info from multiple documents, cite EACH one separately.
- If a claim cannot be grounded to a specific source, prefix with:
  "Note: This is inferred from context and not directly stated in documentation."

Answer Strength Calculation (based on source grounding):
  strong = directly stated in 2+ documents with consistent information, no inference needed
  medium = found in 1-2 documents, some interpretation required, no contradictions
  weak   = only tangential information found, significant inference required
  no_answer = nothing relevant found after all 3 query-expansion searches

Actions Based on Strength:
- strong/medium: Provide full answer with citations
- weak: Provide answer but PREPEND: "I found limited information on this topic.
  The following is based on tangential references and may not be fully accurate."
  ALSO include knowledge_owner.needed = true
- no_answer: Return: "I could not find documentation covering this topic.
  Please contact [knowledge owner] or submit a documentation request."
  Set knowledge_owner.needed = true
```

### 1.8 Attribute Filtering Strategy

**Anti-practice fixed: #9 "No attribute filtering"**

Add to orchestration instructions:

```
ATTRIBUTE FILTERING STRATEGY:
When executing searches, apply filters strategically:

1. Product Area Detection:
   - If question mentions royalties/splits/payments → filter product_area = 'Royalties'
   - If question mentions DSP/Spotify/Apple Music/stores → filter product_area = 'DSP'
   - If question mentions distribute/release/delivery → filter product_area = 'Distribution'
   - If question mentions invoice/billing/pricing → filter product_area = 'Billing'
   - If question mentions onboarding/setup/new client → filter product_area = 'Onboarding'
   - If question mentions dashboard/report/metrics → filter product_area = 'Analytics'
   - If question mentions rights/ownership/territory → filter product_area = 'Rights Management'
   - If question mentions upload/ingest/content → filter product_area = 'Content Delivery'
   - If question mentions account/user/permission → filter product_area = 'Account Management'
   - If unclear or broad question → do NOT filter (use General)

2. Team Detection:
   - If question mentions a team name → filter team = detected_team
   - Otherwise skip team filter (0% fill rate currently)

3. Temporal Filtering:
   - If question asks about "latest"/"current"/"recent" → prefer last_updated DESC
   - If question asks about "historical"/"previous"/"old" → no temporal filter

4. CRITICAL: Always run AT LEAST ONE unfiltered search as fallback.
   Filters can be too restrictive and miss relevant results.
   Apply filter on Search 1 (keyword), skip filter on Search 2 (semantic), skip on Search 3 (broad).
```

### 1.9 Complete Agent Spec (Primary)

Here is the FULL rewritten primary agent spec incorporating all Phase 1 changes:

```sql
-- NOTE: Session variable interpolation does NOT work inside $$ blocks.
-- We must use dynamic SQL via EXECUTE IMMEDIATE to inject temporal context.
SET current_date_str = CURRENT_DATE()::VARCHAR;
SET current_quarter = CASE
    WHEN MONTH(CURRENT_DATE()) <= 3 THEN 'Q1'
    WHEN MONTH(CURRENT_DATE()) <= 6 THEN 'Q2'
    WHEN MONTH(CURRENT_DATE()) <= 9 THEN 'Q3'
    ELSE 'Q4'
END || ' ' || YEAR(CURRENT_DATE())::VARCHAR;
SET current_year = YEAR(CURRENT_DATE())::VARCHAR;

-- Build the YAML spec as a string so session variables are interpolated
SET agent_spec = '
models:
  orchestration: claude-sonnet-4-6
orchestration:
  budget:
    seconds: 45
    tokens: 16000
instructions:
  orchestration: >
    You are RevSearch, the internal knowledge assistant for Revelator employees.
    Your domain covers music distribution, royalties, DSPs (Digital Service Providers),
    billing, onboarding, rights management, analytics, content delivery, and company processes.


    TEMPORAL CONTEXT:
    Today''s date is ' || $current_date_str || '. Current quarter is ' || $current_quarter || '.
    "Recent" means within the last 90 days. "This year" means ' || $current_year || '.
    If a document''s last_updated is >180 days ago, warn the user it may be outdated.


    QUERY EXPANSION PROTOCOL (MANDATORY):
    For every user question, execute exactly 3 searches before synthesizing:
    1. KEYWORD: Extract 3-5 specific terms and search with exact terms.
       If question mentions a specific product area, add product_area filter.
    2. SEMANTIC: Rephrase as declarative statement with synonyms. No filter.
    3. BROADER: Search the parent topic or category. No filter.
    Deduplicate by chunk_id. Chunks in 2+ searches = higher relevance.
    If ALL 3 return 0 results, set answer_strength to "no_answer".


    ATTRIBUTE FILTERING:
    Apply product_area filter on Search 1 when topic is clear:
    royalties/splits/payments → Royalties; DSP/stores → DSP;
    distribute/release → Distribution; invoice/billing → Billing;
    onboarding/setup → Onboarding; dashboard/report → Analytics;
    rights/ownership → Rights Management; upload/content → Content Delivery;
    account/user/permission → Account Management.
    Always run Search 2 and 3 WITHOUT filters as fallback.


    SOURCE GROUNDING (MANDATORY):
    Every factual claim MUST cite: [Source: Title](source_url).
    If combining multiple docs, cite each. If no source_url, omit URL.
    answer_strength: strong = 2+ docs, no inference; medium = 1-2 docs, some interpretation;
    weak = tangential only; no_answer = nothing found after 3 searches.
    If weak: prepend "I found limited information..." and set knowledge_owner.needed = true.
    If no_answer: say "I could not find documentation..." and suggest contacting owner.


    CONSTRAINTS (NEVER VIOLATE):
    1. NEVER fabricate information not in search results.
    2. NEVER guess URLs — only return source_url from search results.
    3. NEVER answer outside Revelator domain. Return no_answer for off-topic.
    4. If 0 results after 3 searches, return no_answer. Do NOT use training data.
    5. NEVER combine docs without noting it.
    6. If docs conflict, present BOTH and flag conflict.
    7. NEVER provide financial/legal/medical advice.
    8. NEVER invent knowledge owner names.
    9. If weak, qualify with "Based on limited information..."
    10. If feature not found, say "I could not find documentation about this."


    OUTPUT FORMAT:
    Always respond with valid JSON only:
    {
      "answer": "detailed answer with [Source: Title](url) citations",
      "answer_strength": "strong|medium|weak|no_answer",
      "sources": [{"title": "...", "source_system": "...", "source_url": "...",
                    "last_updated": "...", "relevance_note": "why relevant"}],
      "knowledge_owner": {"needed": true/false, "primary_owner": "name",
                          "backup_owner": "name", "reason": "why needed"},
      "related_questions": ["q1", "q2", "q3"]
    }
    Do NOT include any text before or after the JSON.

sample_questions:
  - question: "How do royalty splits work in Revelator?"
    answer: "I'll search the knowledge base for information about royalty splits and the Original Works Protocol."
  - question: "What are the steps to distribute a catalogue to stores?"
    answer: "I'll look up the distribution process documentation for store delivery."
  - question: "How does Revelator match catalog to DSP revenue?"
    answer: "I'll search for DSP revenue matching and catalog reconciliation documentation."
  - question: "What is the onboarding process for new clients?"
    answer: "I'll search the onboarding documentation for the client setup process."
  - question: "How do I approve royalty statements?"
    answer: "I'll look up the royalty statement approval workflow documentation."
tools:
  - tool_spec:
      type: cortex_search
      name: search_docs
      description: >
        Searches Revelator's internal knowledge base of 935+ document chunks.
        Coverage: Analytics, Onboarding, Billing, Distribution, Rights Management,
        Royalties, Account Management, DSP integrations, Content Delivery.
        Sources: product docs, FAQs, procedures, billing policies, technical guides,
        support processes, onboarding materials from GitBook.

        USAGE RULES:
        - Use for ANY question about Revelator products, processes, or policies.
        - Search with specific keywords — product names, feature names, process names.
        - Do NOT use for questions unrelated to Revelator's business domain.
        - Execute 3 searches per question (keyword, semantic, broader).
        - Apply product_area filter on first search when topic is identifiable.
        - Always include at least one unfiltered search.

        FILTERABLE ATTRIBUTES:
        - product_area: Royalties|DSP|Distribution|Billing|Onboarding|Analytics|Rights Management|Content Delivery|Account Management|General
        - topic: Product Documentation|Support Process|Onboarding|Billing Policy|Operational Procedure|Ownership Directory|Technical Guide|FAQ|Release Notes|Training Material
        - team: Support|Engineering|Product|Finance|Operations (may be NULL)
        - source_system: gitbook
        - status: active (always filter to active)
tool_resources:
  search_docs:
    name: SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH
    max_results: "10"
    title_column: "title"
    id_column: "chunk_id"
    filter:
      "@eq":
        status: "active"
    columns_and_descriptions:
      content:
        description: "The main text content of the document chunk. Contains product documentation, FAQs, operational procedures, billing policies, and technical guides. Each chunk is prefixed with ''Title: {title}'' and optionally ''Section: {section}'' for context."
        type: "string"
        searchable: true
        filterable: false
      title:
        description: "The document title. Use to narrow search to a specific document."
        type: "string"
        searchable: true
        filterable: true
      topic:
        description: "Document classification topic. Values: Product Documentation, Support Process, Onboarding, Billing Policy, Operational Procedure, Ownership Directory, Technical Guide, FAQ, Release Notes, Training Material."
        type: "string"
        searchable: false
        filterable: true
      product_area:
        description: "Product area classification. Values: Royalties, DSP, Distribution, Billing, Onboarding, Analytics, Rights Management, Content Delivery, Account Management, General."
        type: "string"
        searchable: false
        filterable: true
      source_system:
        description: "Origin system of the document. Currently: gitbook. Future: freshdesk, notion, manual."
        type: "string"
        searchable: false
        filterable: true
      team:
        description: "Team responsible for this document. Values include: Support, Engineering, Product, Finance, Operations. May be NULL for unassigned documents."
        type: "string"
        searchable: false
        filterable: true
      owner:
        description: "Knowledge owner — the person responsible for maintaining this document. Use for routing escalations."
        type: "string"
        searchable: false
        filterable: true
      last_updated:
        description: "When the document was last modified. Use to filter for recent or historical content. Prefer documents with recent dates."
        type: "string"
        searchable: false
        filterable: true
      source_url:
        description: "URL to the original source document. Include in citations. NEVER fabricate URLs."
        type: "string"
        searchable: false
        filterable: false
';

-- Deploy using EXECUTE IMMEDIATE to inject the interpolated spec
EXECUTE IMMEDIATE
    'CREATE OR REPLACE AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.KNOWLEDGE_ASSISTANT
     FROM SPECIFICATION $$ ' || $agent_spec || ' $$';
```

**Key differences from previous version (fixes verified against Snowflake docs):**

1. **`orchestration: budget:`** — budget is nested under `orchestration:` (not the reverse)
2. **Dynamic SQL via `EXECUTE IMMEDIATE`** — `$$` blocks are raw string literals and do NOT interpolate `$variables`. We build the YAML as a string and use `EXECUTE IMMEDIATE` to deploy.
3. **`name:` instead of `search_service:`** — per Cortex Agent docs, the tool_resource key for a Cortex Search service is `name`, not `search_service`
4. **`title_column` and `id_column`** — added for better citation formatting per docs
5. **`max_results: "10"`** — quoted as string per docs convention
6. **`seconds: 45`** — increased from 30s to allow 3 sequential search calls + synthesis
7. **Escaped single quotes** — `''` inside the string-built YAML

### 1.10 Fallback Agent Specs

Apply the SAME instruction improvements to both fallback agents, only changing the model:

- `KNOWLEDGE_ASSISTANT_FALLBACK` — `claude-haiku-4-5` with `budget: {seconds: 20, tokens: 12000}`
- `KNOWLEDGE_ASSISTANT_FALLBACK_2` — `openai-gpt-5.2` with `budget: {seconds: 20, tokens: 12000}`

Fallback agents get identical instructions but slightly tighter budgets since they're meant to be faster.

---

## Phase 2: Data Quality — Context-Enriched Chunking (Foundation)

**Files**: `infra/03_ingestion/process_documents.sql`, `infra/03_ingestion/classify_documents.sql`

### Strategy: Context-Enriched Chunking

Per Snowflake RAG best practices, standard chunks lose "global context" — a chunk about
"cancellation policies" needs to know it applies to "Enterprise Plans". The fix is to prepend
document title + section header to EVERY chunk before indexing.

**Key principles (from Snowflake docs):**
1. Respect the Cortex 512-token semantic limit (keep chunks < 400 words)
2. Use layout-aware parsing to preserve structure
3. Adopt recursive character splitting at natural boundaries
4. Enrich chunks with global metadata (title, section, date)
5. Set intelligent overlap (10-20%) to prevent boundary information loss
6. Filter low-value chunks (footers, page numbers, repetitive headers)

### 2.1 Fix Title Prefix on ALL Chunks (Critical)

**Anti-practice fixed: #2 "Raw text without semantic enrichment"**

Current code in `process_documents.sql` line 34-35:
```python
if start == 0 and title:
    chunk = f"Title: {title}\n\n{chunk.strip()}"
```

This ONLY prefixes the FIRST chunk. The fix prepends title to EVERY chunk:

```python
if title:
    chunk = f"Title: {title}\n\n{chunk.strip()}"
```

Impact: 673 additional chunks get semantic context prefix (from 28% → 100%).

### 2.2 Add Section Header Extraction and Enrichment

**Anti-practice fixed: #4 "Fixed-size chunking ignoring structure"**

The key insight: when a chunk is about "cancellation policies" under the section
"Enterprise Plan Terms", the vector embedding MUST include that section context.
Without it, a search for "enterprise cancellation" may miss this chunk entirely.

**Implementation — new functions in `process_documents.sql`:**

```python
import re

def extract_section_map(text):
    """Build a mapping of character positions to their nearest section header."""
    section_map = []
    current_header = ""
    pos = 0
    for line in text.split('\n'):
        header_match = re.match(r'^(#{1,4})\s+(.+)', line)
        if header_match:
            current_header = header_match.group(2).strip()
        section_map.append((pos, pos + len(line), current_header))
        pos += len(line) + 1  # +1 for newline
    return section_map

def get_section_for_position(section_map, char_position):
    """Find the section header that applies to a given character position."""
    current_section = ""
    for start, end, header in section_map:
        if header:
            current_section = header
        if start <= char_position <= end:
            return current_section
    return current_section

def chunk_text(text, title=None, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    if not text or len(text.strip()) < 50:
        return []

    text = clean_html(text)
    section_map = extract_section_map(text)

    if len(text) <= chunk_size:
        prefix = build_prefix(title, get_section_for_position(section_map, 0))
        return [f"{prefix}\n\n{text.strip()}" if prefix else text.strip()]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        if end < len(text):
            for sep in ['\n\n', '\n', '. ', '? ', '! ']:
                last_break = chunk.rfind(sep)
                if last_break > chunk_size * 0.5:
                    chunk = chunk[:last_break + len(sep)]
                    end = start + last_break + len(sep)
                    break

        section = get_section_for_position(section_map, start)
        prefix = build_prefix(title, section)
        enriched_chunk = f"{prefix}\n\n{chunk.strip()}" if prefix else chunk.strip()

        if len(enriched_chunk) > chunk_size + 200:
            trim_target = chunk_size - len(prefix) - 4 if prefix else chunk_size
            chunk = chunk[:trim_target]
            enriched_chunk = f"{prefix}\n\n{chunk.strip()}" if prefix else chunk.strip()

        if enriched_chunk and len(enriched_chunk.strip()) > 50:
            chunks.append(enriched_chunk)

        start = end - overlap

    return merge_tiny_chunks(chunks)

def build_prefix(title, section):
    """Build the context prefix for a chunk."""
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if section:
        parts.append(f"Section: {section}")
    return "\n".join(parts)
```

**Result format for each chunk:**
```
Title: Getting Started with Revelator
Section: Setting Up Your First Release

[actual chunk content here...]
```

### 2.3 Clean HTML Contamination

**Anti-practice fixed: #5 "HTML/noise in chunks"**

Add HTML cleanup step BEFORE chunking in `process_documents.sql`:

```python
import re

def clean_html(text):
    """Strip HTML artifacts while preserving semantic content."""
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'class="[^"]*"', '', text)
    text = re.sub(r'style="[^"]*"', '', text)
    text = re.sub(r'id="[^"]*"', '', text)

    # Convert HTML tables to markdown-style tables
    text = re.sub(r'<thead[^>]*>', '', text)
    text = re.sub(r'</thead>', '', text)
    text = re.sub(r'<tbody[^>]*>', '', text)
    text = re.sub(r'</tbody>', '', text)
    text = re.sub(r'<tr[^>]*>', '\n| ', text)
    text = re.sub(r'</tr>', ' |', text)
    text = re.sub(r'<th[^>]*>(.*?)</th>', r' **\1** |', text, flags=re.DOTALL)
    text = re.sub(r'<td[^>]*>(.*?)</td>', r' \1 |', text, flags=re.DOTALL)
    text = re.sub(r'<table[^>]*>', '\n', text)
    text = re.sub(r'</table>', '\n', text)

    # Convert common inline elements
    text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<em>(.*?)</em>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<code>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL)

    # Convert lists
    text = re.sub(r'<li[^>]*>', '\n- ', text)
    text = re.sub(r'</li>', '', text)
    text = re.sub(r'<[ou]l[^>]*>', '\n', text)
    text = re.sub(r'</[ou]l>', '\n', text)

    # Convert headings to markdown
    for i in range(6, 0, -1):
        text = re.sub(rf'<h{i}[^>]*>(.*?)</h{i}>', r'\n' + '#' * i + r' \1\n', text, flags=re.DOTALL)

    # Convert breaks and paragraphs
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<p[^>]*>', '\n\n', text)
    text = re.sub(r'</p>', '', text)

    # Strip ALL remaining tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode common HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&#39;', "'")

    # Clean up excessive whitespace
    text = re.sub(r' {3,}', '  ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
```

### 2.4 Merge Tiny Chunks

Post-chunking step to merge chunks < 100 tokens (~400 chars) with adjacent chunks:

```python
def merge_tiny_chunks(chunks, min_chars=400, max_chars=CHUNK_SIZE):
    """Merge chunks that are too small to carry semantic meaning."""
    if not chunks or len(chunks) <= 1:
        return chunks
    merged = [chunks[0]]
    for chunk in chunks[1:]:
        stripped = chunk.strip()
        # Strip prefix lines for length check (don't count Title:/Section: in size)
        content_only = re.sub(r'^(Title:.*\n)?(Section:.*\n)?\n?', '', stripped)
        if len(content_only) < min_chars and len(merged[-1]) + len(stripped) + 2 <= max_chars:
            merged[-1] += "\n\n" + stripped
        else:
            merged.append(stripped)
    # Final pass: drop any remaining tiny chunks that couldn't be merged
    return [c for c in merged if len(re.sub(r'^(Title:.*\n)?(Section:.*\n)?\n?', '', c)) >= 50]
```

### 2.5 Freshness Decay Scoring

**Anti-practice fixed: #18 "Stale docs without decay scoring"**

Add computed freshness signal to help agent reason about document currency:

```sql
ALTER TABLE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
    ADD COLUMN IF NOT EXISTS freshness_score FLOAT;

UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
SET freshness_score = CASE
    WHEN last_updated IS NULL THEN 0.1
    WHEN DATEDIFF('day', last_updated::TIMESTAMP, CURRENT_TIMESTAMP()) <= 30 THEN 1.0
    WHEN DATEDIFF('day', last_updated::TIMESTAMP, CURRENT_TIMESTAMP()) <= 90 THEN 0.8
    WHEN DATEDIFF('day', last_updated::TIMESTAMP, CURRENT_TIMESTAMP()) <= 180 THEN 0.5
    WHEN DATEDIFF('day', last_updated::TIMESTAMP, CURRENT_TIMESTAMP()) <= 365 THEN 0.3
    ELSE 0.1
END;
```

Add `freshness_score` to the search service attributes so the agent can see it:

```sql
-- Add to cortex_search.sql ATTRIBUTES list:
-- ATTRIBUTES title, team, topic, product_area, source_system, owner, backup_owner,
--            last_updated, document_id, chunk_id, source_url, status, freshness_score
```

### 2.6 Populate TEAM/OWNER/BACKUP_OWNER

Create ownership mapping table and population procedure:

```sql
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.ADMIN.TEAM_MAPPING (
    title_pattern   VARCHAR,
    source_system   VARCHAR,
    team            VARCHAR,
    owner           VARCHAR,
    backup_owner    VARCHAR
);

INSERT INTO SNOWFLAKE_INTELLIGENCE.ADMIN.TEAM_MAPPING
SELECT * FROM VALUES
    ('%royalt%', 'gitbook', 'Finance', NULL, NULL),
    ('%billing%', 'gitbook', 'Finance', NULL, NULL),
    ('%invoice%', 'gitbook', 'Finance', NULL, NULL),
    ('%payment%', 'gitbook', 'Finance', NULL, NULL),
    ('%onboard%', 'gitbook', 'Support', NULL, NULL),
    ('%getting started%', 'gitbook', 'Support', NULL, NULL),
    ('%distribut%', 'gitbook', 'Operations', NULL, NULL),
    ('%release%', 'gitbook', 'Operations', NULL, NULL),
    ('%DSP%', 'gitbook', 'Engineering', NULL, NULL),
    ('%spotify%', 'gitbook', 'Engineering', NULL, NULL),
    ('%apple music%', 'gitbook', 'Engineering', NULL, NULL),
    ('%analytic%', 'gitbook', 'Engineering', NULL, NULL),
    ('%dashboard%', 'gitbook', 'Engineering', NULL, NULL),
    ('%rights%', 'gitbook', 'Product', NULL, NULL),
    ('%ownership%', 'gitbook', 'Product', NULL, NULL),
    ('%territory%', 'gitbook', 'Product', NULL, NULL),
    ('%content deliver%', 'gitbook', 'Operations', NULL, NULL),
    ('%upload%', 'gitbook', 'Operations', NULL, NULL),
    ('%account%', 'gitbook', 'Support', NULL, NULL),
    ('%user%', 'gitbook', 'Support', NULL, NULL)
WHERE NOT EXISTS (SELECT 1 FROM SNOWFLAKE_INTELLIGENCE.ADMIN.TEAM_MAPPING LIMIT 1);

CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.INGESTION.POPULATE_OWNERSHIP()
RETURNS STRING
LANGUAGE SQL
AS
BEGIN
    UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS d
    SET d.team = m.team,
        d.owner = COALESCE(m.owner, d.owner),
        d.backup_owner = COALESCE(m.backup_owner, d.backup_owner)
    FROM SNOWFLAKE_INTELLIGENCE.ADMIN.TEAM_MAPPING m
    WHERE LOWER(d.title) LIKE LOWER(m.title_pattern)
      AND (m.source_system IS NULL OR d.source_system = m.source_system)
      AND d.team IS NULL;

    -- Fallback: classify remaining unmatched docs by content
    UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS
    SET team = SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        SUBSTR(content, 1, 2000),
        ARRAY_CONSTRUCT('Support', 'Engineering', 'Product', 'Finance', 'Operations')
    )['label']::VARCHAR
    WHERE team IS NULL;

    -- Propagate to chunks
    UPDATE SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS c
    SET c.team = d.team,
        c.owner = d.owner,
        c.backup_owner = d.backup_owner
    FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS d
    WHERE c.document_id = d.document_id;

    LET populated_count NUMBER;
    SELECT COUNT(*) INTO :populated_count
    FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS WHERE team IS NOT NULL;

    LET total_count NUMBER;
    SELECT COUNT(*) INTO :total_count FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENTS;

    RETURN 'Ownership populated: ' || :populated_count || '/' || :total_count || ' documents';
END;
```

### 2.7 Verification After Chunk Enrichment

After Phase 2 changes, the search service auto-refreshes within TARGET_LAG (1 hour). Verification:

```sql
-- Check enrichment coverage
SELECT
    COUNT(*) AS total_active,
    SUM(CASE WHEN content LIKE 'Title:%' THEN 1 ELSE 0 END) AS with_title_prefix,
    SUM(CASE WHEN content LIKE '%Section:%' THEN 1 ELSE 0 END) AS with_section,
    SUM(CASE WHEN content LIKE '%</%' OR content LIKE '%class=%' THEN 1 ELSE 0 END) AS html_contaminated,
    SUM(CASE WHEN LENGTH(content) < 400 THEN 1 ELSE 0 END) AS tiny_chunks,
    SUM(CASE WHEN team IS NOT NULL THEN 1 ELSE 0 END) AS with_team,
    SUM(CASE WHEN freshness_score IS NOT NULL THEN 1 ELSE 0 END) AS with_freshness
FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
WHERE status = 'active' AND content IS NOT NULL AND LENGTH(content) > 50;

-- Expected after Phase 2:
-- with_title_prefix ≈ total_active (100%)
-- with_section > 0 (depends on how many docs have headers)
-- html_contaminated = 0
-- tiny_chunks = 0
-- with_team > 80% of total
-- with_freshness = total_active
```

---

## Phase 3: App Architecture Improvements (Reliability)

**Files**: `app/utils/agent_client.py`, `app/pages/1_Ask_a_Question.py`, `app/utils/db_utils.py`, `app/utils/search_client.py`

### 3.1 Confidence-Based Fallback (Replace Exception-Only)

**Anti-practice fixed: #8 "Swallowing errors silently"**

Current in `agent_client.py`:
```python
try:
    result = call_primary()
except Exception:
    pass  # silent failure, try fallback
```

Replace with score-based routing that logs every failure:

```python
import logging
import traceback
import uuid

logger = logging.getLogger(__name__)

def ask_agent(session, question, conversation_history=None):
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    errors = []

    agents = [
        ("primary", PRIMARY_AGENT),
        ("fallback", FALLBACK_AGENT),
        ("fallback_2", FALLBACK_AGENT_2),
    ]

    for agent_name, agent_fqn in agents:
        try:
            agent_start = time.time()
            raw_response = _call_agent(session, agent_fqn, question, conversation_history)
            agent_latency = int((time.time() - agent_start) * 1000)

            result = _parse_agent_response(raw_response, agent_name)
            result["trace_id"] = trace_id
            result["response_latency_ms"] = int((time.time() - start_time) * 1000)
            result["agent_latency_ms"] = agent_latency
            result["fallback_triggered"] = agent_name != "primary"

            strength = result.get("answer_strength", "no_answer")

            if strength in ("strong", "medium"):
                _log_trace(session, trace_id, question, agent_name, result, errors)
                return result

            if strength == "weak":
                if agent_name == agents[-1][0]:
                    _log_trace(session, trace_id, question, agent_name, result, errors)
                    return result
                logger.warning(
                    f"[{trace_id}] {agent_name} returned '{strength}', trying next agent"
                )
                errors.append(f"{agent_name}: weak answer")
                continue

            logger.warning(
                f"[{trace_id}] {agent_name} returned '{strength}', trying next agent"
            )
            errors.append(f"{agent_name}: {strength}")

        except Exception as e:
            logger.error(f"[{trace_id}] {agent_name} failed: {traceback.format_exc()}")
            errors.append(f"{agent_name}: {str(e)}")
            continue

    result = _direct_search_fallback(session, question, trace_id)
    result["response_latency_ms"] = int((time.time() - start_time) * 1000)
    _log_trace(session, trace_id, question, "direct_search", result, errors)
    return result
```

### 3.2 Fix Race Condition in log_question()

**Anti-practice fixed: #15 "MAX(id) race condition"**

Current: `MAX(QUESTION_ID)` to retrieve last-inserted row.

The `QUESTIONS` table already has `DEFAULT UUID_STRING()` on the PK. Fix `db_utils.py` to generate the UUID client-side:

```python
import uuid

def log_question(session, question, answer_data, elapsed_ms):
    question_id = str(uuid.uuid4())
    sources_json = json.dumps(answer_data.get("sources", []))
    ko_json = json.dumps(answer_data.get("knowledge_owner") or {})
    rq_json = json.dumps(answer_data.get("related_questions", []))

    session.sql("""
        INSERT INTO SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS
        (QUESTION_ID, QUESTION_TEXT, ANSWER, ANSWER_STRENGTH, MODEL_USED,
         RESPONSE_LATENCY_MS, SOURCES_USED, KNOWLEDGE_OWNER,
         RELATED_QUESTIONS, DATE_ASKED)
        SELECT
            ?, ?, ?, ?, ?,
            ?,
            PARSE_JSON(?),
            PARSE_JSON(?),
            PARSE_JSON(?),
            CURRENT_TIMESTAMP()
    """, params=[
        question_id,
        question,
        answer_data.get("answer", ""),
        answer_data.get("answer_strength", "unknown"),
        answer_data.get("model_used", "unknown"),
        elapsed_ms,
        sources_json,
        ko_json,
        rq_json,
    ]).collect()
    return question_id
```

### 3.3 Integrate Dead Code (search_client.py) as Direct-Search Fallback

**Anti-practice fixed: #16 "Dead/unused code"**

When all 3 agents fail or return no_answer, fall back to raw Cortex Search:

```python
def _direct_search_fallback(session, question, trace_id):
    """Last resort: return raw search results when all agents fail."""
    try:
        from utils.search_client import search_documents
        results = search_documents(session, question, limit=5)
        if results:
            summaries = []
            sources = []
            for r in results[:3]:
                title = r.get("title", "Untitled") if isinstance(r, dict) else "Untitled"
                content = r.get("content", "") if isinstance(r, dict) else str(r)
                url = r.get("source_url", "") if isinstance(r, dict) else ""
                summaries.append(f"- **{title}**: {content[:300]}...")
                sources.append({"title": title, "source_url": url})
            return {
                "answer": "I couldn't synthesize a complete answer, but here are the most "
                          "relevant documents I found:\n\n" + "\n".join(summaries),
                "answer_strength": "weak",
                "sources": sources,
                "knowledge_owner": {"needed": True, "primary_owner": "", "backup_owner": "", "reason": "All agents failed"},
                "related_questions": [],
                "model_used": "direct_search",
                "trace_id": trace_id,
            }
    except Exception as e:
        import logging
        logging.warning(f"Direct search fallback failed: {e}")
    return {
        "answer": "I was unable to find any information about this topic. Please contact your team lead or submit a documentation request.",
        "answer_strength": "no_answer",
        "sources": [],
        "knowledge_owner": {"needed": True, "primary_owner": "", "backup_owner": "", "reason": "No results found"},
        "related_questions": [],
        "model_used": "none",
        "trace_id": trace_id,
    }
```

### 3.4 Session-Level Caching

**Anti-practice fixed: #12 "No caching layer"**

In `app/pages/1_Ask_a_Question.py`:

```python
import hashlib

@st.cache_data(ttl=300, show_spinner=False)
def cached_agent_call(session_key, question):
    """Cache identical questions for 5 minutes within the same session."""
    return ask_agent(session, question)

if question:
    session_key = str(id(session))
    answer_data = cached_agent_call(session_key, question)
```

### 3.5 Intent Classification Pre-Routing

**Anti-practice fixed: #13 "Monolithic agent (no intent routing)"**

Add lightweight intent detection before agent call:

```python
INTENT_PATTERNS = {
    "greeting": ["hello", "hi", "hey", "good morning", "good afternoon"],
    "off_topic": ["weather", "sports", "news", "joke", "recipe"],
}

def classify_intent(question):
    """Quick rule-based intent classification (no LLM call needed)."""
    q_lower = question.lower().strip()

    for intent, patterns in INTENT_PATTERNS.items():
        if any(q_lower.startswith(p) or q_lower == p for p in patterns):
            return intent

    if "who" in q_lower and ("owner" in q_lower or "contact" in q_lower or "responsible" in q_lower):
        return "people_lookup"

    if any(w in q_lower for w in ["difference between", "compare", "vs", "versus"]):
        return "comparison"

    if any(w in q_lower for w in ["how do i", "how to", "steps to", "process for", "guide"]):
        return "how_to"

    return "factual"

# Usage in ask_agent():
intent = classify_intent(question)
if intent == "greeting":
    return {"answer": "Hello! I'm RevSearch. Ask me anything about Revelator's products and processes.", "answer_strength": "strong", ...}
if intent == "off_topic":
    return {"answer": "I can only help with Revelator-related topics.", "answer_strength": "no_answer", ...}
# For people_lookup, comparison, how_to, factual → proceed to agent with intent hint
```

### 3.6 Request Tracing & Observability

**Anti-practice fixed: #17 "No observability/tracing"**

New table for request traces:

```sql
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.ANALYTICS.REQUEST_TRACES (
    trace_id            VARCHAR(36) PRIMARY KEY,
    question_text       VARCHAR(5000),
    intent              VARCHAR(50),
    agent_used          VARCHAR(50),
    fallback_triggered  BOOLEAN DEFAULT FALSE,
    fallback_chain      VARIANT,
    agent_latency_ms    NUMBER,
    total_latency_ms    NUMBER,
    chunks_retrieved    NUMBER,
    answer_strength     VARCHAR(20),
    error_messages      VARIANT,
    created_at          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

Logging function in `agent_client.py`:

```python
def _log_trace(session, trace_id, question, agent_used, result, errors):
    """Log request trace for observability."""
    try:
        errors_json = json.dumps(errors)
        session.sql("""
            INSERT INTO SNOWFLAKE_INTELLIGENCE.ANALYTICS.REQUEST_TRACES
            (trace_id, question_text, agent_used, fallback_triggered,
             agent_latency_ms, total_latency_ms, answer_strength, error_messages)
            SELECT ?, ?, ?, ?,
                ?, ?, ?,
                PARSE_JSON(?)
        """, params=[
            trace_id,
            question[:5000],
            agent_used,
            agent_used != 'primary',
            result.get('agent_latency_ms', 0),
            result.get('response_latency_ms', 0),
            result.get('answer_strength', 'unknown'),
            errors_json,
        ]).collect()
    except Exception as e:
        import logging
        logging.warning(f"Trace logging failed: {e}")
```

### 3.7 Act on answer_strength

**Anti-practice fixed: #20 "Not acting on answer_strength"**

In `1_Ask_a_Question.py`, enhance `display_answer()`:

```python
def display_answer(answer_data):
    strength = answer_data.get("answer_strength", "unknown")

    if strength in ("weak", "no_answer"):
        st.warning("I'm not very confident in this answer. You might want to:")
        cols = st.columns(2)
        with cols[0]:
            st.markdown("- **Rephrase your question** with more specific terms")
        with cols[1]:
            st.markdown("- **Contact the knowledge owner** below")

    st.markdown(answer_data.get("answer", ""))

    # ... existing strength badge, sources, knowledge_owner display ...

    if strength in ("weak", "no_answer"):
        ko = answer_data.get("knowledge_owner", {})
        if ko and isinstance(ko, dict) and ko.get("needed"):
            owner_name = ko.get("primary_owner", "Unknown")
            if owner_name and owner_name != "Unknown":
                st.info(f"Knowledge Owner: **{owner_name}** — they can help with this topic.")
            else:
                st.info("No specific knowledge owner found. Please contact your team lead.")
```

---

## Phase 4: Search Service & Attribute Optimization

**Files**: `infra/04_intelligence/cortex_search.sql`, `infra/03_ingestion/populate_ownership.sql`

### 4.1 Updated Search Service Definition

After Phase 2 changes, update the search service to include `freshness_score` and
keep `last_updated` as TIMESTAMP (not VARCHAR) to support native `time_decays`:

```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH
    ON content
    ATTRIBUTES title, team, topic, product_area, source_system, owner, backup_owner,
               last_updated, document_id, chunk_id, source_url, status, freshness_score
    WAREHOUSE = AI_WH
    TARGET_LAG = '1 hour'
AS (
    SELECT
        content,
        title,
        team,
        topic,
        product_area,
        source_system,
        owner,
        backup_owner,
        last_updated,
        document_id,
        chunk_id,
        source_url,
        status,
        freshness_score
    FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
    WHERE status = 'active'
      AND content IS NOT NULL
      AND LENGTH(content) > 50
);
```

> **Important**: `last_updated` is kept as TIMESTAMP (no VARCHAR cast) so it can be
> used with Cortex Search's native `time_decays` scoring feature (GA April 2025).

### 4.1.1 Native Time Decay Scoring (Cortex Search GA Feature)

Cortex Search supports native `time_decays` in the `scoring_config` at query time.
This is **superior** to the static `freshness_score` column (Phase 2.5) because it
computes decay relative to `now` at query time — no stale scores.

Use both approaches together:
- **Native `time_decays`**: affects ranking — recent docs rank higher automatically
- **Static `freshness_score`**: gives the agent explicit context about document age

When querying via SEARCH_PREVIEW (e.g. in `search_client.py` direct fallback):

```sql
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH',
        '{
            "query": "royalty splits",
            "columns": ["content", "title", "source_url", "last_updated"],
            "filter": {"@eq": {"status": "active"}},
            "scoring_config": {
                "functions": {
                    "time_decays": [
                        {"column": "last_updated", "weight": 1, "limit_hours": 4320}
                    ]
                }
            },
            "limit": 5
        }'
    )
)['results'] AS results;
```

The `limit_hours: 4320` (180 days) means documents older than 180 days get minimal
time-decay boost, while documents within that window get progressively stronger boost
the more recent they are. This matches the 180-day staleness threshold in the agent
instructions (Phase 1.5).

> **Note**: When using Cortex Agents (not direct SEARCH_PREVIEW), the agent's tool
> calls go through the search service automatically. The agent cannot pass
> `scoring_config` directly. To apply time_decays for agent queries, create a
> **named scoring profile** on the search service (GA Oct 2025):
>
> ```sql
> ALTER CORTEX SEARCH SERVICE SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH
>     SET DEFAULT_SCORING_PROFILE = 'recency_boost';
>
> -- Define the profile (syntax may vary — check latest docs)
> ```

### 4.2 Filter Attribute Validation

After TEAM/OWNER population (Phase 2.6), verify attribute filtering works:

```sql
-- Verify team fill rate
SELECT
    team, COUNT(*) AS chunk_count
FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
WHERE status = 'active'
GROUP BY team
ORDER BY chunk_count DESC;

-- Verify product_area fill rate
SELECT
    product_area, COUNT(*) AS chunk_count
FROM SNOWFLAKE_INTELLIGENCE.CURATED.DOCUMENT_CHUNKS
WHERE status = 'active'
GROUP BY product_area
ORDER BY chunk_count DESC;

-- Test filtered search via SEARCH_PREVIEW
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'SNOWFLAKE_INTELLIGENCE.SEARCH.DOCUMENT_SEARCH',
        '{"query": "royalty splits", "columns": ["content", "title", "team", "product_area"], "filter": {"@eq": {"product_area": "Royalties"}}, "limit": 3}'
    )
)['results'] AS filtered_results;
```

### 4.3 Consider TARGET_LAG

Current: 1 hour. Since docs change infrequently (GitBook sync), 1 hour is appropriate.
If future source integrations add real-time data, reduce to 15 minutes.

---

## Phase 5: Dynamic Tables & Monitoring Enhancements

### 5.1 Add Trace-Based Monitoring

```sql
CREATE OR REPLACE DYNAMIC TABLE SNOWFLAKE_INTELLIGENCE.ANALYTICS.AGENT_PERFORMANCE
    TARGET_LAG = '1 hour'
    WAREHOUSE = AI_WH
AS
SELECT
    DATE_TRUNC('hour', created_at) AS hour,
    agent_used,
    COUNT(*) AS total_requests,
    COUNT_IF(answer_strength = 'strong') AS strong_count,
    COUNT_IF(answer_strength = 'medium') AS medium_count,
    COUNT_IF(answer_strength IN ('weak', 'no_answer')) AS weak_or_none,
    COUNT_IF(fallback_triggered) AS fallback_count,
    AVG(total_latency_ms) AS avg_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_latency_ms) AS p95_latency_ms,
    ARRAY_AGG(DISTINCT error_messages) FILTER (WHERE error_messages IS NOT NULL) AS errors
FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.REQUEST_TRACES
GROUP BY hour, agent_used;
```

### 5.2 Add Regression Alert

```sql
CREATE OR REPLACE ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUALITY_REGRESSION_ALERT
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 10 * * * America/Los_Angeles'
    IF (EXISTS (
        SELECT 1
        FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.REQUEST_TRACES
        WHERE created_at >= DATEADD('hour', -24, CURRENT_TIMESTAMP())
        GROUP BY ALL
        HAVING COUNT_IF(answer_strength IN ('weak', 'no_answer')) * 100.0 / COUNT(*) > 30
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'SI_EMAIL_NOTIFICATIONS',
            'admin@revelator.com',
            'RevSearch: Quality Regression — >30% weak/no_answer in last 24h',
            'More than 30% of queries in the last 24 hours received weak or no answers. Review Agent Performance dashboard.'
        );

ALTER ALERT SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUALITY_REGRESSION_ALERT RESUME;
```

---

## Implementation Priority & Sequencing

```
Week 1: Phase 1 (Agent Spec) — Highest impact, no data pipeline changes needed
  Day 1: 1.1 Budget + 1.2 Sample questions + 1.3 columns_and_descriptions
  Day 2: 1.4 Query expansion + 1.5 Temporal context + 1.6 Negative constraints
  Day 3: 1.7 Source grounding + 1.8 Attribute filtering + 1.9 Deploy full spec
  Day 4: Run native eval baseline (see 05-native-agent-evaluation.md)
  Day 5: Compare pre/post agent spec change accuracy, iterate

Week 2: Phase 2 (Data Quality) — Foundation for retrieval improvement
  Day 1: 2.1 Title prefix ALL chunks + 2.3 HTML cleanup
  Day 2: 2.2 Section headers + 2.4 Merge tiny chunks
  Day 3: 2.5 Freshness score + 2.6 TEAM/OWNER population
  Day 4: Re-run PROCESS_DOCUMENTS + CLASSIFY_DOCUMENTS + POPULATE_OWNERSHIP
  Day 5: Wait for search service re-index, verify with 2.7, run eval

Week 3: Phase 3 (App Architecture) + Phase 4-5
  Day 1: 3.1 Confidence-based fallback + 3.2 Race condition fix
  Day 2: 3.3 Integrate search_client.py + 3.4 Caching
  Day 3: 3.5 Intent classification + 3.6 Request tracing
  Day 4: 3.7 Answer strength actions + Phase 4 search service update
  Day 5: Phase 5 monitoring + Full regression eval

Week 4: Validation & Hardening
  Full eval runs across all 3 agents, compare against Week 1 baseline
  Update all tests (static + integration) for new patterns
  Deploy updated Streamlit app
  Verify 0/20 anti-practices violated
```

## Expected Outcomes

| Metric | Current | After Phase 1 | After Phase 1+2 | After All Phases |
|--------|---------|---------------|-----------------|------------------|
| Primary accuracy | ~69-92% | 85-92% | 90-95% | 95%+ |
| Fallback accuracy | 72.2% | 78%+ | 83%+ | 88%+ |
| Eval coverage | 18 questions | 50+ (see PLAN 5) | 55+ | 55+ with regression |
| Title-enriched chunks | 28% | 28% (unchanged) | 100% | 100% |
| Section-enriched chunks | 0% | 0% | 60%+ | 60%+ |
| HTML contamination | 12 chunks | 12 (unchanged) | 0 | 0 |
| Tiny chunks | 65 | 65 (unchanged) | 0 | 0 |
| TEAM fill rate | 0% | 0% | 80%+ | 80%+ |
| Freshness scoring | None | None | 100% | 100% |
| Anti-practices violated | 17/20 | 8/20 | 4/20 | 0/20 |
| Error visibility | Silent (`pass`) | Logged + traced | Full observability | Full + alerts |
| Avg response latency | Unknown | ~20s primary | ~18s (better chunks) | <15s (caching) |
| Fallback strategy | Exception-only | Exception-only | Confidence-based | Confidence + intent |

---

## Anti-Practice Resolution Matrix

| # | Anti-Practice | Fix | Phase | Expected Impact |
|---|-------------|-----|-------|-----------------|
| 1 | Single search query | 3-query expansion protocol | 1.4 | +10-15% recall |
| 2 | Raw text without enrichment | Title + Section prefix on 100% chunks | 2.1, 2.2 | +5-10% precision |
| 3 | No negative constraints | 10-rule constraint block | 1.6 | -50% hallucination |
| 4 | Chunking ignoring structure | Section-aware chunking | 2.2 | +5% relevance |
| 5 | HTML/noise in chunks | HTML → markdown conversion | 2.3 | Cleaner embeddings |
| 6 | Small eval dataset | 55+ questions (PLAN 5) | PLAN 5 | Better measurement |
| 7 | Over-stuffing prompt | NOT VIOLATED | — | — |
| 8 | Swallowing errors | Full logging + traceback | 3.1 | Debuggable failures |
| 9 | No attribute filtering | product_area + team filtering | 1.8 | +10% precision |
| 10 | Happy-path-only eval | Negative test cases (PLAN 5) | PLAN 5 | Catch regressions |
| 11 | Ignoring temporal context | CURRENT_DATE injection | 1.5 | Time-aware answers |
| 12 | No caching | 5-min TTL session cache | 3.4 | <100ms repeated |
| 13 | Monolithic agent | Intent pre-routing | 3.5 | Faster OOS rejection |
| 14 | No source grounding | Mandatory citation rules | 1.7 | Verifiable answers |
| 15 | MAX(id) race condition | Client-side UUID | 3.2 | No duplicate IDs |
| 16 | Dead/unused code | search_client.py → fallback | 3.3 | Graceful degradation |
| 17 | No observability | REQUEST_TRACES table + alerts | 3.6 | Full visibility |
| 18 | Stale docs without decay | freshness_score column | 2.5 | Recency awareness |
| 19 | No regression testing | Weekly eval Tasks (PLAN 5) | PLAN 5 | Automated quality |
| 20 | Not acting on answer_strength | UI warnings + owner routing | 3.7 | Better UX on weak |

---

## Cross-Reference to Prior Plans

| Item | PLAN_1 | PLAN_2 | PLAN_3 | PLAN_4 (this) |
|------|--------|--------|--------|---------------|
| Chunk quality | R4, R5 | Phase 2 | Enh. 4 | Phase 2 (context-enriched) |
| Agent improvement | R6 | Phase 4 | — | Phase 1 (comprehensive spec) |
| Caching | R18 | — | Enh. 1 | Phase 3.4 |
| Evaluation | — | — | — | See PLAN_5 |
| Ownership/Teams | — | — | — | Phase 2.6 |
| Observability | R20 | Phase 6 | — | Phase 3.6 + Phase 5 |
| Section headers | — | — | — | Phase 2.2 (NEW) |
| Intent routing | — | — | — | Phase 3.5 (NEW) |
| Freshness decay | — | — | — | Phase 2.5 (NEW) |
| Quality alerts | — | — | — | Phase 5.2 (NEW) |
