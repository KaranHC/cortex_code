# Research: RAG Best Practices on Snowflake
## Agent 7 Output — Comprehensive Findings

---

## RAG Architecture Pattern on Snowflake

### The Canonical Pattern

```
User Question
    │
    ▼
Cortex Agent (LLM reasoning)
    │
    ├── Tool Call: Cortex Search Service
    │       │
    │       ▼
    │   Hybrid Search (Vector + BM25)
    │       │
    │       ▼
    │   Top-K Chunks + Metadata
    │
    ▼
LLM generates answer from retrieved chunks
    │
    ▼
Structured Response (answer, confidence, sources)
```

---

## Document Chunking Best Practices

### Optimal Chunk Sizes

| Document Type | Chunk Size | Overlap | Rationale |
|--------------|-----------|---------|-----------|
| Knowledge base articles | 1000-1500 chars | 150-200 chars | Articles are focused; medium chunks preserve context |
| Long-form documentation | 1500-2000 chars | 200-300 chars | Need more context per chunk for coherence |
| FAQ entries | Full entry (no chunking) | N/A | FAQs are naturally atomic |
| Policy documents | 1000-1500 chars | 200 chars | Policies need precise boundaries |
| Step-by-step guides | Per-section | N/A | Each step/section is a natural chunk |

### Chunking Strategies

1. **Fixed-size with overlap** (recommended for MVP):
   - Simple, predictable
   - Works well with Cortex Search
   - Overlap prevents information loss at boundaries

2. **Section-based** (recommended for structured docs):
   - Split on headers (H1, H2, H3)
   - Each section is a chunk
   - Preserves document structure

3. **Semantic chunking** (future enhancement):
   - Use embeddings to find natural break points
   - More complex but better quality

### Implementation: Smart Chunking

```python
def smart_chunk(text, title, max_size=1500, overlap=200):
    """Chunk text intelligently, preserving structure."""
    # First, try section-based chunking
    sections = re.split(r'\n(?=#{1,3}\s)', text)
    
    chunks = []
    for section in sections:
        if len(section) <= max_size:
            chunks.append(section)
        else:
            # Fall back to fixed-size chunking for long sections
            chunks.extend(fixed_chunk(section, max_size, overlap))
    
    # Prepend title to first chunk for context
    if chunks:
        chunks[0] = f"# {title}\n\n{chunks[0]}"
    
    return chunks
```

---

## Preventing Hallucination

### Strategy 1: Strict System Prompt

```
CRITICAL RULES:
1. Your ONLY source of information is the documents retrieved by the search tool.
2. If the search results do not contain the answer, say:
   "I could not find documentation addressing this question."
3. NEVER fill in gaps with your own knowledge.
4. NEVER make assumptions about processes not described in the documents.
5. If a document partially answers the question, clearly state what is covered
   and what is NOT covered.
6. Always quote or closely paraphrase the source material.
```

### Strategy 2: Self-Assessment Prompt

Add to system prompt:
```
After generating your answer, evaluate it against these criteria:
- Is EVERY claim in the answer supported by a specific document?
- Are there any statements that go beyond what the documents say?
- Could any part of the answer be considered speculative?

If you find unsupported claims, remove them and adjust answer_strength downward.
```

### Strategy 3: Temperature Control

- Use **temperature = 0** (or as low as possible) for factual accuracy
- Higher temperatures increase creativity but also hallucination risk

### Strategy 4: Citation Enforcement

```
For each claim in your answer, include an inline citation like [Source: Document Title].
If you cannot cite a source for a claim, DELETE that claim from your answer.
```

---

## Confidence Scoring Implementation

### Approach 1: Retrieval Score Thresholds

```python
def assess_confidence(search_results):
    """Determine answer strength from search retrieval scores."""
    if not search_results:
        return "no_answer"
    
    top_score = search_results[0].get("score", 0)
    num_relevant = sum(1 for r in search_results if r.get("score", 0) > 0.5)
    
    if top_score > 0.8 and num_relevant >= 2:
        return "strong"
    elif top_score > 0.6 and num_relevant >= 1:
        return "medium"
    elif top_score > 0.3:
        return "weak"
    else:
        return "no_answer"
```

### Approach 2: LLM Self-Assessment (Recommended)

Include in the system prompt:
```
Assess your answer_strength using these specific criteria:

"strong": You can directly quote or closely paraphrase 2+ documents that 
          fully answer the question. No interpretation needed.

"medium": You found 1-2 relevant documents but had to interpret or combine 
          information. Some aspects of the question may not be fully covered.

"weak": The retrieved documents are only tangentially related. Your answer 
        requires significant inference. The user should verify with the owner.

"no_answer": The retrieved documents do not address the question at all. 
             Do NOT attempt to answer.
```

### Approach 3: Combined (Best Quality)

Use both retrieval scores AND LLM self-assessment:
1. Cortex Search returns results with scores
2. If no results or all scores < 0.3 → force "no_answer"
3. Otherwise, let the LLM assess based on content quality
4. Override LLM to "weak" if top score < 0.5

---

## Source Attribution

### Prompt Pattern for Citations

```
When answering, structure your response with inline citations:

"According to [Distribution Guide], the royalty clawback process involves..."
"The [Billing Policy v2.3] states that refunds are processed within..."
"Based on [Onboarding Playbook, Section: Enterprise Clients], the first step is..."

In the sources array, include:
- title: exact document title
- source_url: link to original (if available)
- last_updated: when the document was last updated
- relevance_note: one sentence explaining why this source is relevant
```

---

## Multi-Document Synthesis

When a question requires information from multiple documents:

```
If the answer requires combining information from multiple documents:
1. Clearly indicate which information comes from which document
2. Note any inconsistencies between documents
3. If documents conflict, present both perspectives and note the conflict
4. Flag the answer_strength as "medium" if synthesis is complex
```

---

## Related Question Generation

### Prompt Pattern

```
Generate 3 related questions that:
1. Are closely related to the user's question
2. Would likely be answered by the same or adjacent documents
3. Represent natural follow-up questions an employee might ask
4. Are specific and actionable (not vague)

Example: If the question is "How do royalty clawbacks work?"
Good related questions:
- "What triggers a royalty clawback?"
- "How long does the clawback process take?"
- "Who is responsible for approving clawbacks?"
```

---

## Handling Edge Cases

### Question Too Vague
```
If the question is too broad or vague to search effectively:
- Ask the user to be more specific
- Suggest 2-3 more specific versions of their question
- Set answer_strength to "weak"
```

### Question About Non-Existent Topic
```
If search returns zero relevant results:
- Clearly state no documentation was found
- Set answer_strength to "no_answer"
- Route to knowledge owner for the closest matching topic
- Suggest the user submit a documentation request
```

### Multiple Interpretations
```
If the question could be interpreted multiple ways:
- Address the most likely interpretation
- Mention alternative interpretations
- Suggest the user clarify if the answer doesn't match their intent
```

### Outdated Information
```
If the retrieved documents are dated (>6 months old):
- Include the document dates prominently
- Add a warning: "This information was last updated on [date]. Please verify with the knowledge owner."
- Set answer_strength to maximum "medium" for old documents
```

---

## Search Query Optimization

### The Agent's Query Reformulation

When Cortex Agent receives a user question, it may reformulate it for better search results. Best practices:

1. **System prompt guidance**: "When searching, try multiple query formulations if initial results are insufficient"
2. **Keyword extraction**: Agent can extract key terms from verbose questions
3. **Acronym expansion**: Agent can expand DSP → "Digital Service Provider" for broader matches

### Improving Search Relevance

1. **Include title in chunk content**: Prepend document title to each chunk
2. **Add metadata to content**: "Team: Product | Topic: Royalties\n\n[actual content]"
3. **Clean content**: Remove HTML tags, normalize whitespace, fix encoding
4. **Deduplicate**: Remove duplicate chunks from overlapping ingestion
5. **Filter archived**: Always filter `status = 'active'` at query time

---

## Evaluation Framework

### Metrics to Track

| Metric | Description | Target |
|--------|-------------|--------|
| **Retrieval Precision** | % of search results that are actually relevant | > 80% |
| **Retrieval Recall** | % of relevant documents that are retrieved | > 70% |
| **Answer Faithfulness** | % of claims in answer supported by retrieved docs | 100% |
| **Answer Relevance** | Does the answer actually address the question? | > 90% |
| **Source Quality** | Are cited sources the correct/best sources? | > 85% |
| **User Satisfaction** | Thumbs up rate | > 85% |

### Automated Evaluation (Future)

```python
# Use CORTEX.COMPLETE to auto-evaluate answer quality
evaluation_prompt = f"""
Given the question: {question}
And the retrieved documents: {documents}
And the generated answer: {answer}

Rate the following on a scale of 1-5:
1. Faithfulness: Does the answer only contain information from the documents?
2. Relevance: Does the answer address the question?
3. Completeness: Does the answer cover all relevant information?
4. Source attribution: Are all claims properly cited?

Return JSON: {{"faithfulness": N, "relevance": N, "completeness": N, "attribution": N}}
"""
```
