# PLAN 5: Native Cortex Agent Evaluation

> Setup and operationalize Snowflake's native Cortex Agent Evaluations (GA March 13, 2026)
> to replace custom `scripts/run_eval.py` with `EXECUTE_AI_EVALUATION`.
> Reference: [Cortex Agent Evaluations](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations),
> [EXECUTE_AI_EVALUATION](https://docs.snowflake.com/en/sql-reference/functions/execute_ai_evaluation)

---

## Why Native Evaluation

### Current State: Custom Eval Script (`scripts/run_eval.py`)

| Aspect | Current Custom | Native `EXECUTE_AI_EVALUATION` |
|--------|---------------|-------------------------------|
| Scoring | Custom 0-2 LLM judge via CORTEX.COMPLETE | Built-in `answer_correctness` + `logical_consistency` LLM judges |
| Dimensions | Single score (0-2) | Multi-dimensional: correctness, consistency, custom metrics |
| Tracing | None — only final answer captured | Full trace via `GET_AI_RECORD_TRACE` (tool calls, planning steps, latency) |
| Custom metrics | None | YAML-defined custom metrics with LLM prompts |
| Reference-free eval | Not supported | `logical_consistency` — no ground truth needed |
| Snowsight UI | None | Full UI in AI & ML > Agents > Evaluations tab |
| Regression pipeline | Manual script execution | Can be triggered via Snowflake Tasks |
| Token tracking | Not tracked | `TOTAL_INPUT_TOKENS`, `TOTAL_OUTPUT_TOKENS`, `LLM_CALL_COUNT` per record |
| Result storage | Local JSON files | Queryable via `GET_AI_EVALUATION_DATA` |
| Negative test cases | None | Fully supported with custom ground truth prompts |
| Feedback integration | None | Can incorporate user feedback signals |

### Permissions Audit (All Confirmed)

| Permission | Status |
|-----------|--------|
| `SNOWFLAKE.CORTEX_USER` database role | GRANTED |
| `EXECUTE TASK ON ACCOUNT` | GRANTED |
| `USAGE` on `SNOWFLAKE_INTELLIGENCE` database | GRANTED |
| `USAGE` on `SNOWFLAKE_INTELLIGENCE.AGENTS` schema | GRANTED |
| `CREATE FILE FORMAT` on AGENTS schema | GRANTED |
| `CREATE TASK` on AGENTS schema | GRANTED |
| `CREATE DATASET` on AGENTS schema | GRANTED |
| `CREATE STAGE` on AGENTS schema | GRANTED |
| `CREATE TABLE` on AGENTS schema | GRANTED |
| `OWNERSHIP` on all 3 knowledge assistant agents | GRANTED |
| `MONITOR` on all 3 knowledge assistant agents | GRANTED |
| `USAGE` on all 3 knowledge assistant agents | GRANTED |
| `OWNERSHIP` on `DOCUMENT_SEARCH` search service | GRANTED |

---

## Step 1: Create Evaluation Infrastructure

### 1.1 Create Eval Config Stage

```sql
CREATE STAGE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Stage for agent evaluation YAML configs';
```

### 1.2 Create Native Eval Dataset Table

Per Snowflake docs, the dataset requires:
- `input_query` column (VARCHAR) — the user question
- `output` column (VARIANT) — ground truth as `{"ground_truth_output": "..."}`

```sql
CREATE OR REPLACE TABLE SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET (
    input_query VARCHAR NOT NULL,
    output VARIANT NOT NULL
);
```

### 1.3 Migrate Existing 18 Questions

Convert from current `EVAL_DATASET` (question/expected_answer) to native format:

```sql
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET (input_query, output)
SELECT
    QUESTION,
    TO_VARIANT(OBJECT_CONSTRUCT('ground_truth_output', EXPECTED_ANSWER))
FROM SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_DATASET;
```

---

## Step 2: Expand to 69 Evaluation Questions

### Anti-practices fixed: #6 "Small eval dataset", #10 "Happy-path-only eval"

### Current Coverage (18 Questions)

| Category | Count | Product Areas |
|----------|-------|---------------|
| core | 7 | General(2), Royalties(2), DSP, Distribution, Content Delivery |
| ambiguous | 2 | Onboarding, Royalties |
| complex | 2 | Distribution, General |
| edge_case | 3 | DSP, Distribution, General |
| out_of_scope | 2 | General |
| validation | 2 | Billing, Content Delivery |

### Target Coverage (69 Questions)

**By Product Area** (5 per area = 50 minimum + 5 cross-area):

| Product Area | Current | Target | Gap |
|-------------|---------|--------|-----|
| Royalties | 3 | 5 | +2 |
| DSP | 2 | 5 | +3 |
| Distribution | 3 | 5 | +2 |
| Billing | 1 | 5 | +4 |
| Onboarding | 1 | 5 | +4 |
| Analytics | 0 | 5 | +5 |
| Rights Management | 0 | 5 | +5 |
| Content Delivery | 2 | 5 | +3 |
| Account Management | 0 | 5 | +5 |
| General | 6 | 5 | -1 (keep all) |
| **Total** | **18** | **69** | **+51** |

**By Category/Type** (targeting 69 total):

| Type | Count | Description | Anti-Practice Addressed |
|------|-------|-------------|------------------------|
| Factual lookup | 15 | Single-fact questions with clear answers | Baseline coverage |
| Process/How-to | 10 | Step-by-step workflow questions | Baseline coverage |
| Multi-hop reasoning | 5 | Requires synthesizing 2+ documents | Tests query expansion (#1) |
| Temporal queries | 5 | "What changed recently?", "Current process for..." | Tests temporal context (#11) |
| Negative/Out-of-scope | 5 | Questions with NO answer (expect "I don't know") | Tests negative constraints (#3) |
| Ambiguous | 5 | Vague queries requiring clarification | Tests source grounding (#14) |
| Comparison | 5 | "What's the difference between X and Y?" | Tests multi-search (#1) |
| Edge case | 5 | Unusual scenarios, boundary conditions | Tests robustness |

**Difficulty Mix**: Easy 30% (17), Medium 40% (22), Hard 30% (16)

### Ground Truth Best Practices

Per Snowflake docs: "Take advantage of the fact that ground truth is included in an LLM prompt by using natural language to describe a type of response."

**Ground truth patterns by question type:**

```
-- Factual (exact match expected)
"ground_truth_output": "Revelator Wallet supports Royalty Splits created using the Original
Works Protocol. Splits are managed via smart contracts that automatically distribute royalties
to rights holders based on allocated percentages."

-- Process (describe expected structure, not exact words)
"ground_truth_output": "The answer should describe the step-by-step process: 1) reviewing
statement data, 2) checking for metadata/payout errors, 3) updating payee info if needed,
4) final approval. Should mention error checking and payee configuration."

-- Negative/Out-of-scope (expect REFUSAL, not fabrication)
"ground_truth_output": "The agent should indicate this question is outside its domain.
The response should have answer_strength of 'no_answer' or explicitly state it cannot find
relevant information. The agent should NOT attempt to answer from general knowledge."

-- Temporal (expect recency awareness)
"ground_truth_output": "The answer should reference document dates and note if information
might be outdated. If asking about recent changes and no recent docs exist, should say
'No recent updates found' rather than presenting old info as current."

-- Multi-hop (expect synthesis from multiple sources)
"ground_truth_output": "The answer should combine information from royalty documentation
AND payment processing documentation to explain the full impact. Should cite at least
2 different source documents."

-- Ambiguous (expect clarification or best-effort with caveats)
"ground_truth_output": "The answer should either ask for clarification OR provide a
best-effort answer with a caveat that the question is ambiguous. Should NOT confidently
answer if the question could mean multiple things."

-- Comparison (expect structured side-by-side)
"ground_truth_output": "The answer should clearly compare both options, listing
similarities and differences. Should use structured format (bullets or table)."
```

### New Questions to Add (51 total)

```sql
-- ============================================================
-- ANALYTICS (5 new — currently 0)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('What analytics dashboards are available in Revelator?',
 PARSE_JSON('{"ground_truth_output": "Should describe available analytics features including revenue tracking, streaming analytics, and trend analysis tools."}')),
('How do I generate a revenue report by DSP?',
 PARSE_JSON('{"ground_truth_output": "Should describe the process of generating revenue reports filtered by Digital Service Provider (DSP)."}')),
('What metrics can I track for my catalogue performance?',
 PARSE_JSON('{"ground_truth_output": "Should mention metrics like streams, downloads, revenue, territory breakdown, and trend analysis."}')),
('How does Revelator calculate royalty analytics?',
 PARSE_JSON('{"ground_truth_output": "Should explain the royalty calculation methodology including split percentages, revenue attribution, and payment processing."}')),
('Can I export analytics data from Revelator?',
 PARSE_JSON('{"ground_truth_output": "Should describe export capabilities, supported formats, and any limitations on data export."}'));

-- ============================================================
-- RIGHTS MANAGEMENT (5 new — currently 0)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('How does rights management work in Revelator?',
 PARSE_JSON('{"ground_truth_output": "Should explain the rights management system including ownership tracking, territorial rights, and the Original Works Protocol."}')),
('What is the Original Works Protocol?',
 PARSE_JSON('{"ground_truth_output": "Should describe OWP as the blockchain-based protocol for managing music rights and royalty splits."}')),
('How do I register a new composition in Revelator?',
 PARSE_JSON('{"ground_truth_output": "Should describe the composition registration process including metadata requirements and rights holder assignment."}')),
('What happens when there is a rights conflict?',
 PARSE_JSON('{"ground_truth_output": "Should explain the conflict resolution process for overlapping rights claims."}')),
('How do territorial rights affect distribution?',
 PARSE_JSON('{"ground_truth_output": "Should explain how territorial restrictions impact which DSPs/stores receive content in which regions."}'));

-- ============================================================
-- ACCOUNT MANAGEMENT (5 new — currently 0)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('How do I create a new sub-label in Revelator?',
 PARSE_JSON('{"ground_truth_output": "Should describe the sub-label creation process within the platform."}')),
('What roles and permissions are available in Revelator?',
 PARSE_JSON('{"ground_truth_output": "Should describe available user roles, permission levels, and access control mechanisms."}')),
('How do I invite a new team member to my Revelator account?',
 PARSE_JSON('{"ground_truth_output": "Should describe the user invitation workflow and role assignment process."}')),
('What is the difference between a label and a distributor account?',
 PARSE_JSON('{"ground_truth_output": "Should explain the distinction between label accounts and distributor accounts, including different features and permissions."}')),
('How do I manage payment settings for my account?',
 PARSE_JSON('{"ground_truth_output": "Should describe payment configuration including bank details, payment thresholds, and payment schedules."}'));

-- ============================================================
-- MULTI-HOP REASONING (5 new — tests query expansion & synthesis)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('If a royalty split has 3 participants and one disputes, how does that affect the payment cycle?',
 PARSE_JSON('{"ground_truth_output": "Should combine knowledge about royalty splits, dispute resolution, and payment processing to explain the impact on payment cycles. Must cite at least 2 source documents."}')),
('What happens to a release if the distributing label loses DSP access while the release is live?',
 PARSE_JSON('{"ground_truth_output": "Should synthesize distribution, DSP integration, and release management documentation to explain the impact."}')),
('How do analytics for a release change if the territory rights are updated after initial distribution?',
 PARSE_JSON('{"ground_truth_output": "Should combine territory rights, distribution, and analytics docs to explain how rights changes affect reporting."}')),
('If I onboard a new label with existing DSP relationships, what migration steps differ from a fresh setup?',
 PARSE_JSON('{"ground_truth_output": "Should combine onboarding and distribution migration documentation to explain the differences."}')),
('How does a billing dispute affect both the label and artist royalty statements?',
 PARSE_JSON('{"ground_truth_output": "Should synthesize billing, royalty, and account management docs to explain cascading impacts."}'));

-- ============================================================
-- TEMPORAL QUERIES (5 new — tests CURRENT_DATE injection)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('What are the latest changes to the distribution process?',
 PARSE_JSON('{"ground_truth_output": "Should reference the most recent documentation and note the last_updated dates. Should warn if docs are older than 90 days."}')),
('Is the onboarding documentation current?',
 PARSE_JSON('{"ground_truth_output": "Should check last_updated dates on onboarding docs and report whether they are current (within 90 days) or potentially stale."}')),
('What DSP integrations have been added recently?',
 PARSE_JSON('{"ground_truth_output": "Should search for recent DSP-related documentation and report findings with dates. Should note if no recent changes found."}')),
('Has the royalty calculation method changed in the last year?',
 PARSE_JSON('{"ground_truth_output": "Should check royalty documentation dates and report whether any changes have occurred within the specified timeframe."}')),
('What is the current billing cycle for Q1 2026?',
 PARSE_JSON('{"ground_truth_output": "Should provide billing cycle information relevant to Q1 2026 (January-March 2026) or note if documentation does not cover this specific period."}'));

-- ============================================================
-- NEGATIVE / OUT-OF-SCOPE (3 new — tests negative constraints)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('What is the weather forecast for tomorrow?',
 PARSE_JSON('{"ground_truth_output": "The agent MUST refuse this question. It should return answer_strength no_answer and state this is outside its domain. The agent must NOT fabricate weather information."}')),
('Can you write me a Python script to scrape Spotify data?',
 PARSE_JSON('{"ground_truth_output": "The agent MUST refuse this request. It should explain it only provides information from Revelator documentation and cannot write code or assist with external scraping."}')),
('What are Apple Music''s internal royalty rates for 2025?',
 PARSE_JSON('{"ground_truth_output": "The agent should indicate this is confidential third-party information not available in Revelator docs. Should NOT guess or fabricate DSP-internal rates. May offer to look up how Revelator processes Apple Music payments instead."}'));

-- ============================================================
-- ADDITIONAL BILLING (4 new — currently only 1)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('How does Revelator handle invoice generation?',
 PARSE_JSON('{"ground_truth_output": "Should describe the invoice generation process, including triggers, formats, and delivery methods."}')),
('What happens when a payment fails?',
 PARSE_JSON('{"ground_truth_output": "Should explain the payment failure handling process, including retry policies, notifications, and manual intervention steps."}')),
('How are currency conversions handled for international payments?',
 PARSE_JSON('{"ground_truth_output": "Should describe currency conversion processes for international royalty and billing payments."}')),
('What billing reports are available in Revelator?',
 PARSE_JSON('{"ground_truth_output": "Should list available billing reports and how to access or generate them."}'));

-- ============================================================
-- ADDITIONAL ONBOARDING (4 new — currently only 1)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('What documents are needed for label onboarding?',
 PARSE_JSON('{"ground_truth_output": "Should list the required documentation for new label onboarding: legal agreements, tax forms, bank details, catalog information, etc."}')),
('How long does the typical onboarding process take?',
 PARSE_JSON('{"ground_truth_output": "Should provide typical onboarding timeline with key milestones and any factors that can affect duration."}')),
('What happens if onboarding is rejected?',
 PARSE_JSON('{"ground_truth_output": "Should explain the rejection process, reasons for rejection, and steps to reapply or remediate issues."}')),
('Can I onboard multiple sub-labels at once?',
 PARSE_JSON('{"ground_truth_output": "Should explain bulk/batch onboarding capabilities and any limitations."}'));

-- ============================================================
-- ADDITIONAL DSP (3 new — currently only 2)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('What DSPs does Revelator distribute to?',
 PARSE_JSON('{"ground_truth_output": "Should list the major Digital Service Providers that Revelator supports for content distribution (e.g., Spotify, Apple Music, Amazon Music, etc.)."}')),
('How does Revelator handle DSP-specific metadata requirements?',
 PARSE_JSON('{"ground_truth_output": "Should explain how different DSPs have different metadata requirements and how Revelator handles format conversion or validation."}')),
('What happens when a DSP rejects a release submission?',
 PARSE_JSON('{"ground_truth_output": "Should describe the rejection notification process, common rejection reasons, and steps to fix and resubmit."}'));

-- ============================================================
-- ADDITIONAL CONTENT DELIVERY (3 new — currently only 2)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('What audio formats does Revelator accept for content upload?',
 PARSE_JSON('{"ground_truth_output": "Should list accepted audio formats (e.g., WAV, FLAC) and any quality requirements like sample rate and bit depth."}')),
('How does Revelator handle artwork requirements for releases?',
 PARSE_JSON('{"ground_truth_output": "Should describe artwork specifications: dimensions, format, file size limits, and content guidelines."}')),
('What is the typical content delivery timeline from upload to store availability?',
 PARSE_JSON('{"ground_truth_output": "Should explain the timeline from upload through processing, QC, delivery to DSPs, and typical store availability timeframes."}'));

-- ============================================================
-- COMPARISON QUESTIONS (1 new to supplement existing edge_case)
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('What is the difference between a release and a product in Revelator?',
 PARSE_JSON('{"ground_truth_output": "Should clearly differentiate the concepts of a release vs a product, explaining how they relate in the Revelator platform hierarchy."}'));

-- ============================================================
-- REAL-WORLD USER QUESTIONS (8 new — sourced from actual user queries)
-- These test realistic phrasing, edge cases, and multi-domain reasoning
-- ============================================================
INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET VALUES
('What is the difference between YouTube MCN and YouTube CID?',
 PARSE_JSON('{"ground_truth_output": "Should explain that MCN (Multi-Channel Network) is a YouTube partner program for managing multiple channels, while CID (Content ID) is YouTube''s rights management system that scans uploads for copyrighted content. Should describe how each relates to Revelator''s YouTube integration and revenue collection."}')),
('Regarding UPC number: 7316482103140, it seems to have been successfully delivered and ingested by Spotify, although it is showing as not available worldwide in the Music Providers portal. What could be causing this?',
 PARSE_JSON('{"ground_truth_output": "Should explain possible causes for a delivered-but-unavailable release: territorial restrictions, metadata mismatches, DSP-side processing delays, content policy flags, or store-specific availability settings. Should NOT fabricate status for this specific UPC but describe the diagnostic steps."}')),
('What are the steps required to get fully onboarded with Revelator?',
 PARSE_JSON('{"ground_truth_output": "Should describe the complete onboarding workflow: account creation, legal agreement signing, tax form submission, bank/payment setup, catalog import or creation, DSP delivery configuration, and first release submission. Should mention approximate timeline and key milestones."}')),
('Why is my release stuck in inspection?',
 PARSE_JSON('{"ground_truth_output": "Should explain the inspection/QC process: what triggers it, common reasons for delays (metadata issues, artwork non-compliance, audio quality problems, rights conflicts), how long it typically takes, and what actions the user can take to resolve or escalate."}')),
('How do I transfer releases between accounts/enterprises?',
 PARSE_JSON('{"ground_truth_output": "Should describe the release transfer process between accounts or enterprises, including any prerequisites, who can initiate transfers, what happens to existing DSP deliveries during transfer, and any limitations or caveats."}')),
('Why am I seeing duplicate releases after API migration?',
 PARSE_JSON('{"ground_truth_output": "Should explain common causes of duplicate releases during API migration: ID mapping issues, incomplete deduplication, parallel ingestion from old and new systems, or UPC/ISRC conflicts. Should describe diagnostic steps and resolution approaches."}')),
('My cover art is 3000x3000 but getting an error saying it should be 1400x1400 - what is wrong?',
 PARSE_JSON('{"ground_truth_output": "Should explain artwork requirements: minimum dimensions (typically 1400x1400 or 3000x3000), maximum file size, required format (JPG/PNG), aspect ratio (must be square), color space requirements, and common causes of dimension errors (e.g., DPI vs pixel confusion, non-square aspect ratio). A 3000x3000 image should normally be accepted, so the issue may be file format, color space, or file size."}')),
('How do I validate my API key? I am getting account locked errors.',
 PARSE_JSON('{"ground_truth_output": "Should explain API key validation steps, common causes of account locked errors (too many failed attempts, expired credentials, IP restrictions, account suspension), and resolution steps including how to reset or regenerate API keys and who to contact for account unlock."}'));
```

### Final Dataset Composition (69 questions)

18 existing + 51 new = 69 total.

| Category | Count | Coverage |
|----------|-------|----------|
| Factual lookup | 18 | All 10 product areas (incl. DSP, Content Delivery additions) |
| Process/How-to | 13 | Onboarding, Distribution, Billing, Rights, API, Transfers |
| Multi-hop reasoning | 5 | Cross-domain synthesis |
| Temporal queries | 5 | Recency, staleness, date awareness |
| Negative/Out-of-scope | 5 | Refusal, domain boundaries |
| Ambiguous | 5 | Clarification needs |
| Comparison | 7 | Side-by-side analysis (incl. MCN vs CID) |
| Edge case | 11 | Boundary conditions, DSP rejections, content specs, real-world debugging |

---

## Step 3: Create Evaluation YAML Configs

### 3.1 Primary Agent Evaluation Config

File: `agent_evaluation_config.yaml`

```yaml
agent:
  name: KNOWLEDGE_ASSISTANT
  database: SNOWFLAKE_INTELLIGENCE
  schema: AGENTS
  type: CORTEX AGENT

dataset:
  database: SNOWFLAKE_INTELLIGENCE
  schema: AGENTS
  table: NATIVE_EVAL_DATASET
  input_column: INPUT_QUERY
  ground_truth_column: OUTPUT

metrics:
  system:
    answer_correctness:
      enabled: true
      ground_truth_key: ground_truth_output
    logical_consistency:
      enabled: true

  custom:
    source_grounding:
      enabled: true
      prompt: >
        Evaluate whether the agent's response cites specific source documents.
        A well-grounded response should include [Source: Document Title] or similar
        citations for factual claims. Check that cited sources are plausible
        (not fabricated URLs or document names).

        Scoring:
        1.0 = Every factual claim has a citation and citations appear valid
        0.7 = Most claims cited but some uncited assertions
        0.3 = Few or no citations despite factual claims
        0.0 = No citations at all or citations appear fabricated
      scoring:
        min: 0
        max: 1

    hallucination_check:
      enabled: true
      prompt: >
        Evaluate whether the agent's response contains fabricated information
        that contradicts the ground truth or adds claims not supported by any
        search results. Look for:
        - Invented URLs or document titles
        - Specific numbers/dates/names not in the ground truth
        - Confident claims about features that don't exist
        - Answering out-of-scope questions instead of refusing

        Scoring:
        1.0 = No hallucination detected, all claims appear grounded
        0.5 = Minor embellishments but core facts are correct
        0.0 = Contains fabricated information or fails to refuse out-of-scope question
      scoring:
        min: 0
        max: 1

    json_format_compliance:
      enabled: true
      prompt: >
        Evaluate whether the agent's response is valid JSON containing the required fields:
        answer, answer_strength, sources, knowledge_owner, related_questions.

        Scoring:
        1.0 = Valid JSON with all 5 required fields present
        0.7 = Valid JSON but missing 1-2 optional sub-fields
        0.3 = Partially valid JSON or wrapped in extra text
        0.0 = Not valid JSON or missing multiple required fields
      scoring:
        min: 0
        max: 1

    answer_strength_accuracy:
      enabled: true
      prompt: >
        Evaluate whether the agent correctly assessed its own confidence level
        via the answer_strength field. Compare the agent's self-assessed strength
        against the actual quality of its answer:

        - If answer is correct and well-cited, strength should be "strong" or "medium"
        - If answer is partial or has gaps, strength should be "medium" or "weak"
        - If question is out-of-scope and agent refuses, strength should be "no_answer"
        - If agent gives wrong answer but claims "strong", that is the WORST case

        Scoring:
        1.0 = Self-assessment matches actual answer quality
        0.5 = Self-assessment is off by one level (e.g., strong when medium)
        0.0 = Self-assessment is completely wrong (e.g., strong when wrong, or no_answer when correct)
      scoring:
        min: 0
        max: 1

    negative_constraint_compliance:
      enabled: true
      prompt: >
        Evaluate whether the agent properly handles out-of-scope or unanswerable questions.
        For questions that are outside the Revelator business domain or cannot be answered
        from the knowledge base:

        - Agent should NOT fabricate an answer
        - Agent should set answer_strength to "no_answer" or "weak"
        - Agent should suggest contacting a knowledge owner or rephrasing
        - Agent should NOT answer from training data

        For in-scope questions, this metric should score 1.0 (not applicable).

        Scoring:
        1.0 = Correctly handles boundaries (refuses OOS, answers in-scope)
        0.5 = Partially correct (hedges but still provides some fabricated info)
        0.0 = Violates negative constraints (answers OOS confidently, fabricates)
      scoring:
        min: 0
        max: 1

    query_expansion_evidence:
      enabled: true
      prompt: >
        Evaluate whether the agent appears to have searched multiple times with
        different query formulations, as evidenced by citing diverse source documents
        or mentioning multiple search attempts in its response.

        Scoring:
        1.0 = Evidence of multiple searches (diverse sources cited, mentions searching with different terms)
        0.5 = Some diversity in sources but may have been single search
        0.0 = Only single narrow source or no evidence of expanded search
      scoring:
        min: 0
        max: 1
```

### 3.2 Fallback Agent Config

File: `agent_evaluation_config_fallback.yaml` — identical metrics, different agent:

```yaml
agent:
  name: KNOWLEDGE_ASSISTANT_FALLBACK
  database: SNOWFLAKE_INTELLIGENCE
  schema: AGENTS
  type: CORTEX AGENT
# dataset and metrics identical to primary config
```

### 3.3 Fallback 2 Agent Config

File: `agent_evaluation_config_fallback_2.yaml`:

```yaml
agent:
  name: KNOWLEDGE_ASSISTANT_FALLBACK_2
  database: SNOWFLAKE_INTELLIGENCE
  schema: AGENTS
  type: CORTEX AGENT
# dataset and metrics identical to primary config
```

### 3.4 Upload Configs to Stage

```sql
PUT file:///path/to/agent_evaluation_config.yaml
    @SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/
    AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

PUT file:///path/to/agent_evaluation_config_fallback.yaml
    @SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/
    AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

PUT file:///path/to/agent_evaluation_config_fallback_2.yaml
    @SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/
    AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

---

## Step 4: Run First Native Evaluation

### 4.1 Start Primary Agent Evaluation

```sql
CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', 'primary-baseline-v1'),
    '@SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/agent_evaluation_config.yaml'
);
```

### 4.2 Monitor Progress

```sql
CALL EXECUTE_AI_EVALUATION(
    'STATUS',
    OBJECT_CONSTRUCT('run_name', 'primary-baseline-v1'),
    '@SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/agent_evaluation_config.yaml'
);
```

Expected status flow: `CREATED` → `INVOCATION_IN_PROGRESS` → `INVOCATION_COMPLETED` → `COMPUTATION_IN_PROGRESS` → `COMPLETED`

### 4.3 Inspect Results — Multi-Dimensional Analysis

```sql
-- Full evaluation data
SELECT * FROM TABLE(
    SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        'SNOWFLAKE_INTELLIGENCE',
        'AGENTS',
        'KNOWLEDGE_ASSISTANT',
        'CORTEX AGENT',
        'primary-baseline-v1'
    )
);

-- Summary by metric — the key comparison dashboard
SELECT
    METRIC_NAME,
    METRIC_TYPE,
    COUNT(*) AS total_records,
    ROUND(AVG(EVAL_AGG_SCORE), 3) AS avg_score,
    ROUND(MIN(EVAL_AGG_SCORE), 3) AS min_score,
    ROUND(MAX(EVAL_AGG_SCORE), 3) AS max_score,
    ROUND(STDDEV(EVAL_AGG_SCORE), 3) AS stddev_score,
    COUNT_IF(EVAL_AGG_SCORE >= 0.7) AS passing_count,
    ROUND(COUNT_IF(EVAL_AGG_SCORE >= 0.7) * 100.0 / COUNT(*), 1) AS pass_rate_pct
FROM TABLE(
    SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        'SNOWFLAKE_INTELLIGENCE',
        'AGENTS',
        'KNOWLEDGE_ASSISTANT',
        'CORTEX AGENT',
        'primary-baseline-v1'
    )
)
GROUP BY METRIC_NAME, METRIC_TYPE
ORDER BY avg_score ASC;

-- Token usage and cost summary
SELECT
    SUM(TOTAL_INPUT_TOKENS) AS total_input_tokens,
    SUM(TOTAL_OUTPUT_TOKENS) AS total_output_tokens,
    SUM(LLM_CALL_COUNT) AS total_llm_calls,
    ROUND(AVG(DURATION_MS), 0) AS avg_duration_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY DURATION_MS), 0) AS p95_duration_ms,
    MAX(DURATION_MS) AS max_duration_ms,
    MIN(DURATION_MS) AS min_duration_ms
FROM TABLE(
    SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        'SNOWFLAKE_INTELLIGENCE',
        'AGENTS',
        'KNOWLEDGE_ASSISTANT',
        'CORTEX AGENT',
        'primary-baseline-v1'
    )
);

-- Worst-performing questions (focus improvement here)
-- NOTE: GET_AI_EVALUATION_DATA returns column "INPUT" (not "INPUT_QUERY")
SELECT
    INPUT,
    METRIC_NAME,
    EVAL_AGG_SCORE,
    DURATION_MS,
    TOTAL_INPUT_TOKENS + TOTAL_OUTPUT_TOKENS AS total_tokens
FROM TABLE(
    SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        'SNOWFLAKE_INTELLIGENCE',
        'AGENTS',
        'KNOWLEDGE_ASSISTANT',
        'CORTEX AGENT',
        'primary-baseline-v1'
    )
)
WHERE METRIC_NAME = 'answer_correctness'
ORDER BY EVAL_AGG_SCORE ASC
LIMIT 10;
```

### 4.4 Inspect Individual Trace (Debug Failures)

```sql
SELECT * FROM TABLE(
    SNOWFLAKE.LOCAL.GET_AI_RECORD_TRACE(
        'SNOWFLAKE_INTELLIGENCE',
        'AGENTS',
        'KNOWLEDGE_ASSISTANT',
        'CORTEX AGENT',
        '<record_id>'  -- from GET_AI_EVALUATION_DATA results
    )
);
```

Use this to debug WHY a question scored low:
- Did the agent search with the right terms?
- Did it find relevant chunks but misinterpret them?
- Did it fail to find anything?
- Did it hallucinate despite finding relevant content?

### 4.5 Run for All Agents

```sql
CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', 'fallback-baseline-v1'),
    '@SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/agent_evaluation_config_fallback.yaml'
);

CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', 'fallback2-baseline-v1'),
    '@SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/agent_evaluation_config_fallback_2.yaml'
);
```

### 4.6 Cross-Agent Comparison

After all 3 agents complete baseline eval:

```sql
-- Compare all agents side by side
-- NOTE: GET_AI_EVALUATION_DATA returns column "INPUT" (not "INPUT_QUERY")
WITH primary_results AS (
    SELECT INPUT, METRIC_NAME, EVAL_AGG_SCORE AS primary_score, DURATION_MS AS primary_ms
    FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        'SNOWFLAKE_INTELLIGENCE', 'AGENTS', 'KNOWLEDGE_ASSISTANT', 'CORTEX AGENT', 'primary-baseline-v1'))
    WHERE METRIC_NAME = 'answer_correctness'
),
fallback_results AS (
    SELECT INPUT, EVAL_AGG_SCORE AS fallback_score, DURATION_MS AS fallback_ms
    FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        'SNOWFLAKE_INTELLIGENCE', 'AGENTS', 'KNOWLEDGE_ASSISTANT_FALLBACK', 'CORTEX AGENT', 'fallback-baseline-v1'))
    WHERE METRIC_NAME = 'answer_correctness'
),
fallback2_results AS (
    SELECT INPUT, EVAL_AGG_SCORE AS fallback2_score, DURATION_MS AS fallback2_ms
    FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        'SNOWFLAKE_INTELLIGENCE', 'AGENTS', 'KNOWLEDGE_ASSISTANT_FALLBACK_2', 'CORTEX AGENT', 'fallback2-baseline-v1'))
    WHERE METRIC_NAME = 'answer_correctness'
)
SELECT
    p.INPUT,
    ROUND(p.primary_score, 2) AS primary_score,
    ROUND(f.fallback_score, 2) AS fallback_score,
    ROUND(f2.fallback2_score, 2) AS fallback2_score,
    p.primary_ms,
    f.fallback_ms,
    f2.fallback2_ms,
    CASE
        WHEN p.primary_score >= f.fallback_score AND p.primary_score >= f2.fallback2_score THEN 'PRIMARY'
        WHEN f.fallback_score >= f2.fallback2_score THEN 'FALLBACK'
        ELSE 'FALLBACK2'
    END AS best_agent
FROM primary_results p
LEFT JOIN fallback_results f ON p.INPUT = f.INPUT
LEFT JOIN fallback2_results f2 ON p.INPUT = f2.INPUT
ORDER BY p.primary_score ASC;
```

---

## Step 5: Regression Pipeline

### 5.1 Eval Runner Stored Procedure

```sql
CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.AGENTS.RUN_NATIVE_EVAL(
    AGENT_NAME VARCHAR,
    RUN_NAME VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
AS
BEGIN
    LET config_path VARCHAR;

    CASE AGENT_NAME
        WHEN 'KNOWLEDGE_ASSISTANT'
            THEN config_path := '@SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/agent_evaluation_config.yaml';
        WHEN 'KNOWLEDGE_ASSISTANT_FALLBACK'
            THEN config_path := '@SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/agent_evaluation_config_fallback.yaml';
        WHEN 'KNOWLEDGE_ASSISTANT_FALLBACK_2'
            THEN config_path := '@SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_CONFIG/agent_evaluation_config_fallback_2.yaml';
        ELSE
            RETURN 'Unknown agent: ' || AGENT_NAME;
    END CASE;

    CALL EXECUTE_AI_EVALUATION(
        'START',
        OBJECT_CONSTRUCT('run_name', :RUN_NAME),
        :config_path
    );

    RETURN 'Evaluation started: ' || RUN_NAME || ' for agent ' || AGENT_NAME;
END;
```

### 5.2 Weekly Scheduled Eval Tasks

```sql
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.AGENTS.WEEKLY_EVAL_PRIMARY
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 6 * * MON America/Los_Angeles'
    COMMENT = 'Weekly evaluation of primary agent'
AS
    CALL SNOWFLAKE_INTELLIGENCE.AGENTS.RUN_NATIVE_EVAL(
        'KNOWLEDGE_ASSISTANT',
        'weekly-primary-' || TO_VARCHAR(CURRENT_DATE(), 'YYYYMMDD')
    );

ALTER TASK SNOWFLAKE_INTELLIGENCE.AGENTS.WEEKLY_EVAL_PRIMARY RESUME;

CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.AGENTS.WEEKLY_EVAL_FALLBACK
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 7 * * MON America/Los_Angeles'
    COMMENT = 'Weekly evaluation of fallback agent'
AS
    CALL SNOWFLAKE_INTELLIGENCE.AGENTS.RUN_NATIVE_EVAL(
        'KNOWLEDGE_ASSISTANT_FALLBACK',
        'weekly-fallback-' || TO_VARCHAR(CURRENT_DATE(), 'YYYYMMDD')
    );

ALTER TASK SNOWFLAKE_INTELLIGENCE.AGENTS.WEEKLY_EVAL_FALLBACK RESUME;

CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.AGENTS.WEEKLY_EVAL_FALLBACK2
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 8 * * MON America/Los_Angeles'
    COMMENT = 'Weekly evaluation of fallback 2 agent'
AS
    CALL SNOWFLAKE_INTELLIGENCE.AGENTS.RUN_NATIVE_EVAL(
        'KNOWLEDGE_ASSISTANT_FALLBACK_2',
        'weekly-fallback2-' || TO_VARCHAR(CURRENT_DATE(), 'YYYYMMDD')
    );

ALTER TASK SNOWFLAKE_INTELLIGENCE.AGENTS.WEEKLY_EVAL_FALLBACK2 RESUME;
```

### 5.3 Regression Check Procedure

```sql
CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.AGENTS.CHECK_EVAL_REGRESSION(
    AGENT_NAME VARCHAR,
    CURRENT_RUN VARCHAR,
    BASELINE_RUN VARCHAR,
    THRESHOLD_PCT FLOAT DEFAULT 5.0
)
RETURNS VARCHAR
LANGUAGE SQL
AS
BEGIN
    LET results VARIANT;
    LET regression_detected BOOLEAN := FALSE;
    LET report VARCHAR := '';

    -- Check each metric
    FOR metric_rec IN (
        SELECT DISTINCT METRIC_NAME
        FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
            'SNOWFLAKE_INTELLIGENCE', 'AGENTS', :AGENT_NAME, 'CORTEX AGENT', :CURRENT_RUN
        ))
    ) DO
        LET current_score FLOAT;
        SELECT AVG(EVAL_AGG_SCORE) INTO :current_score
        FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
            'SNOWFLAKE_INTELLIGENCE', 'AGENTS', :AGENT_NAME, 'CORTEX AGENT', :CURRENT_RUN
        ))
        WHERE METRIC_NAME = metric_rec.METRIC_NAME;

        LET baseline_score FLOAT;
        SELECT AVG(EVAL_AGG_SCORE) INTO :baseline_score
        FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
            'SNOWFLAKE_INTELLIGENCE', 'AGENTS', :AGENT_NAME, 'CORTEX AGENT', :BASELINE_RUN
        ))
        WHERE METRIC_NAME = metric_rec.METRIC_NAME;

        LET pct_change FLOAT := ROUND((:current_score - :baseline_score) / NULLIF(:baseline_score, 0) * 100, 1);

        IF (:current_score < :baseline_score * (1 - :THRESHOLD_PCT / 100)) THEN
            regression_detected := TRUE;
            report := report || 'REGRESSION: ' || metric_rec.METRIC_NAME ||
                      ' dropped from ' || ROUND(:baseline_score, 3) ||
                      ' to ' || ROUND(:current_score, 3) ||
                      ' (' || :pct_change || '%)\n';
        ELSE
            report := report || 'OK: ' || metric_rec.METRIC_NAME ||
                      ' = ' || ROUND(:current_score, 3) ||
                      ' (baseline: ' || ROUND(:baseline_score, 3) ||
                      ', change: ' || :pct_change || '%)\n';
        END IF;
    END FOR;

    IF (:regression_detected) THEN
        RETURN 'REGRESSION DETECTED for ' || AGENT_NAME || ':\n' || report;
    ELSE
        RETURN 'ALL METRICS OK for ' || AGENT_NAME || ':\n' || report;
    END IF;
END;
```

### 5.4 Regression Alert

```sql
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.AGENTS.WEEKLY_REGRESSION_CHECK
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 12 * * MON America/Los_Angeles'
    COMMENT = 'Check for eval regression after weekly eval completes'
AS
BEGIN
    LET current_run VARCHAR := 'weekly-primary-' || TO_VARCHAR(CURRENT_DATE(), 'YYYYMMDD');
    LET prev_run VARCHAR := 'weekly-primary-' || TO_VARCHAR(DATEADD('week', -1, CURRENT_DATE()), 'YYYYMMDD');

    LET result VARCHAR;
    CALL SNOWFLAKE_INTELLIGENCE.AGENTS.CHECK_EVAL_REGRESSION(
        'KNOWLEDGE_ASSISTANT', :current_run, :prev_run, 5.0
    ) INTO :result;

    IF (result LIKE 'REGRESSION%') THEN
        CALL SYSTEM$SEND_EMAIL(
            'SI_EMAIL_NOTIFICATIONS',
            'admin@revelator.com',
            'RevSearch REGRESSION: Agent quality dropped >5%',
            :result
        );
    END IF;
END;

ALTER TASK SNOWFLAKE_INTELLIGENCE.AGENTS.WEEKLY_REGRESSION_CHECK RESUME;
```

### 5.5 Eval History Table (for Trend Analysis)

```sql
CREATE TABLE IF NOT EXISTS SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_HISTORY (
    run_name        VARCHAR,
    agent_name      VARCHAR,
    metric_name     VARCHAR,
    avg_score       FLOAT,
    min_score       FLOAT,
    max_score       FLOAT,
    pass_rate_pct   FLOAT,
    total_records   NUMBER,
    total_tokens    NUMBER,
    avg_duration_ms NUMBER,
    run_date        DATE DEFAULT CURRENT_DATE(),
    PRIMARY KEY (run_name, agent_name, metric_name)
);

CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.AGENTS.SAVE_EVAL_HISTORY(
    AGENT_NAME VARCHAR,
    RUN_NAME VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
AS
BEGIN
    INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.EVAL_HISTORY
        (run_name, agent_name, metric_name, avg_score, min_score, max_score,
         pass_rate_pct, total_records, total_tokens, avg_duration_ms)
    SELECT
        :RUN_NAME,
        :AGENT_NAME,
        METRIC_NAME,
        AVG(EVAL_AGG_SCORE),
        MIN(EVAL_AGG_SCORE),
        MAX(EVAL_AGG_SCORE),
        COUNT_IF(EVAL_AGG_SCORE >= 0.7) * 100.0 / NULLIF(COUNT(*), 0),
        COUNT(*),
        SUM(TOTAL_INPUT_TOKENS + TOTAL_OUTPUT_TOKENS),
        AVG(DURATION_MS)
    FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        'SNOWFLAKE_INTELLIGENCE', 'AGENTS', :AGENT_NAME, 'CORTEX AGENT', :RUN_NAME
    ))
    GROUP BY METRIC_NAME;

    RETURN 'History saved for ' || AGENT_NAME || ' run ' || RUN_NAME;
END;
```

---

## Step 6: Feedback Loop Integration

### 6.1 Connect User Feedback to Eval Dataset

Currently, user feedback (thumbs up/down) is collected in `ANALYTICS.FEEDBACK` but never used.
Use negative feedback to identify questions that should be added to the eval dataset:

```sql
CREATE OR REPLACE PROCEDURE SNOWFLAKE_INTELLIGENCE.AGENTS.FEEDBACK_TO_EVAL()
RETURNS VARCHAR
LANGUAGE SQL
AS
BEGIN
    INSERT INTO SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET (input_query, output)
    SELECT DISTINCT
        q.QUESTION_TEXT,
        TO_VARIANT(OBJECT_CONSTRUCT(
            'ground_truth_output',
            'User gave negative feedback on this question. The previous answer was: ' ||
            SUBSTR(q.ANSWER, 1, 500) ||
            '. The answer should be improved to correctly address this question.'
        ))
    FROM SNOWFLAKE_INTELLIGENCE.ANALYTICS.FEEDBACK f
    JOIN SNOWFLAKE_INTELLIGENCE.ANALYTICS.QUESTIONS q ON f.QUESTION_ID = q.QUESTION_ID
    WHERE f.FEEDBACK_TYPE = 'negative'
      AND f.CREATED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())
      AND q.QUESTION_TEXT NOT IN (
          SELECT INPUT_QUERY FROM SNOWFLAKE_INTELLIGENCE.AGENTS.NATIVE_EVAL_DATASET
      );

    LET added_count NUMBER := SQLROWCOUNT;

    RETURN 'Added ' || :added_count || ' feedback-driven questions to eval dataset';
END;
```

### 6.2 Monthly Feedback-to-Eval Task

```sql
CREATE OR REPLACE TASK SNOWFLAKE_INTELLIGENCE.AGENTS.MONTHLY_FEEDBACK_TO_EVAL
    WAREHOUSE = AI_WH
    SCHEDULE = 'USING CRON 0 9 1 * * America/Los_Angeles'
    COMMENT = 'Monthly: add negatively-rated questions to eval dataset'
AS
    CALL SNOWFLAKE_INTELLIGENCE.AGENTS.FEEDBACK_TO_EVAL();

ALTER TASK SNOWFLAKE_INTELLIGENCE.AGENTS.MONTHLY_FEEDBACK_TO_EVAL RESUME;
```

---

## Step 7: Retire Custom Eval Script

### Migration Path

| Phase | Custom `run_eval.py` | Native `EXECUTE_AI_EVALUATION` |
|-------|---------------------|-------------------------------|
| Step 4 (baseline) | Run both side-by-side | Run native eval, compare results |
| Step 5 (regression) | Keep as backup | Primary eval method |
| After 2 weeks stable | Archive, stop using | Sole eval method |

### What to Keep from Custom Script

- The `JUDGE_PROMPT` logic in `run_eval.py` can inform custom metric prompts in YAML config
- The per-category breakdown logic can be replicated via SQL queries on `GET_AI_EVALUATION_DATA` results
- The `call_agent()` function pattern remains useful for ad-hoc testing outside formal eval runs

### What Native Eval Adds (Not in Custom)

- **Logical consistency** — reference-free metric measuring instruction compliance, planning quality, tool call correctness
- **Full traces** — see every tool call, planning step, and intermediate result
- **Token accounting** — track input/output tokens and LLM call count per question
- **Snowsight UI** — visual eval results, no terminal needed
- **6 custom metrics** — source_grounding, hallucination_check, json_format_compliance, answer_strength_accuracy, negative_constraint_compliance, query_expansion_evidence
- **Dataset versioning** — Snowflake Datasets for eval data management
- **Feedback loop** — negative user feedback auto-populates eval dataset
- **Trend analysis** — EVAL_HISTORY table tracks scores over time
- **Cross-agent comparison** — side-by-side query comparing all 3 agents

---

## Verification Checklist

- [ ] Stage `EVAL_CONFIG` created successfully
- [ ] `NATIVE_EVAL_DATASET` table created with correct schema (input_query VARCHAR, output VARIANT)
- [ ] 18 existing questions migrated successfully
- [ ] 51 new questions added (total 69)
- [ ] All 10 product areas have 5+ questions (incl. DSP and Content Delivery additions)
- [ ] 8 real-world user questions included
- [ ] 5 negative/out-of-scope questions included
- [ ] 5 temporal questions included
- [ ] 5 multi-hop reasoning questions included
- [ ] YAML config files uploaded to stage (3 configs)
- [ ] All 6 custom metrics defined in YAML
- [ ] `EXECUTE_AI_EVALUATION('START', ...)` executes without errors
- [ ] `EXECUTE_AI_EVALUATION('STATUS', ...)` returns valid status
- [ ] `GET_AI_EVALUATION_DATA` returns results after COMPLETED status
- [ ] `GET_AI_RECORD_TRACE` returns trace for individual records
- [ ] answer_correctness scores are comparable to custom eval baseline
- [ ] logical_consistency scores are reasonable (>0.7)
- [ ] Custom metrics return meaningful scores (not all 0 or all 1)
- [ ] EVAL_HISTORY table populated by SAVE_EVAL_HISTORY procedure
- [ ] Weekly eval Tasks resume and execute on schedule
- [ ] Regression check procedure correctly detects score drops >5%
- [ ] Regression alert fires when threshold exceeded
- [ ] Feedback-to-eval procedure adds negative-feedback questions
- [ ] Cross-agent comparison query works for all 3 agents
- [ ] All 37 static + 42 integration tests still pass

---

## Timeline

```
Day 1: Steps 1.1-1.3 — Create infra, migrate existing 18 questions
Day 2: Step 2 — Add 51 new questions to reach 69 total
Day 3: Step 3 — Write YAML configs with 6 custom metrics, upload to stage
Day 4: Step 4 — Run first native evaluation for all 3 agents
Day 5: Step 4.6 — Cross-agent comparison, identify worst performers
Day 6: Step 5 — Set up regression pipeline (stored proc, tasks, alerts)
Day 7: Step 6 — Set up feedback loop integration
Week 2: Step 7 — Run native + custom side-by-side, validate consistency
Week 3+: Retire custom eval, native eval is sole method
```

---

## Metric Targets (Post-PLAN 4 Implementation)

| Metric | Baseline (Pre) | Target (Post Phase 1) | Target (Post All) |
|--------|----------------|----------------------|-------------------|
| answer_correctness | TBD (first run) | >0.75 | >0.90 |
| logical_consistency | TBD | >0.70 | >0.85 |
| source_grounding | TBD | >0.60 | >0.85 |
| hallucination_check | TBD | >0.80 | >0.95 |
| json_format_compliance | TBD | >0.80 | >0.95 |
| answer_strength_accuracy | TBD | >0.50 | >0.80 |
| negative_constraint_compliance | TBD | >0.70 | >0.95 |
| query_expansion_evidence | TBD | >0.40 | >0.70 |

---

## Cross-Reference to PLAN_4

| PLAN_4 Phase | Eval Touchpoint | Expected Impact on Scores |
|-------------|-----------------|--------------------------|
| Phase 1 (Agent Spec) Day 4 | Run native eval BEFORE changes = baseline | — |
| Phase 1 (Agent Spec) Day 5 | Run native eval AFTER changes = measure improvement | +10-15% answer_correctness, +20% negative_constraint |
| Phase 2 (Chunk Quality) Day 5 | Run eval after re-index = measure retrieval quality | +5-10% answer_correctness, +15% source_grounding |
| Phase 3 (App Architecture) | App changes don't affect agent eval directly | Trace data helps debug failures |
| Phase 4 (Attributes) | Run eval after TEAM/OWNER populated | +5% answer_correctness on team-specific questions |
| Feedback loop (Step 6) | Monthly addition of hard questions | Continuously harder dataset = honest measurement |
