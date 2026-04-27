
# Skill: `/lit-review`

## Purpose

Use this skill to **orchestrate a complete literature review workflow** by coordinating two MCP servers:

- **AcademicSearch MCP** – for discovering and ranking relevant papers.
- **PaperKB MCP** – for ingesting selected papers into a local knowledge base and performing retrieval/QA.

The goal is to go from a high‑level topic (e.g., *“graph neural networks for traffic prediction”*) to a **structured literature review outline** backed by specific papers.

---

## Invocation

You are invoked explicitly with a slash command:

```text
/lit-review &lt;TOPIC_OR_QUESTION&gt;
```

Examples:

- `/lit-review graph transformer models for traffic prediction`
- `/lit-review diffusion transformers for time series forecasting`
- `/lit-review retrieval-augmented generation for scientific QA`

---

## High-Level Workflow

When this skill is invoked, you MUST follow this three‑phase workflow:

1. **Discovery phase (AcademicSearch MCP)**
2. **Selection &amp; ingestion phase (PaperKB MCP)**
3. **Retrieval &amp; review synthesis phase (PaperKB MCP + reasoning)**

You are the orchestrator. MCP servers are tools; they do NOT talk to each other directly.

---

## Phase 1 – Discovery (AcademicSearch MCP)

1. Interpret the user’s topic and, if needed, rewrite it into a **clear academic search query**.
2. Use the **AcademicSearch MCP**:
   - Call its `search_papers` tool with parameters similar to:
     - `query`: the refined topic string.
     - `year_from`: default to `current_year - 5` unless user specifies a range.
     - `year_to`: current year.
     - `max_results`: start with 30–50.
3. When you receive the result:
   - Present the user a **ranked list** (top ~15–20) with:
     - index number,
     - title,
     - year,
     - venue (if available),
     - 1–2 line abstract summary,
     - `pdf_url` or a way to reference the paper later (e.g., `external_id`).
   - Ask the user to confirm which papers to ingest:
     - Either by indices (e.g., `1, 3, 5-8`)  
     - Or by a maximum number of top papers (e.g., “top 5 most relevant”).

**Never proceed to ingestion automatically without explicit user confirmation.**

---

## Phase 2 – Selection &amp; Ingestion (PaperKB MCP)

After the user selects target papers:

1. Build a list of selected papers (either by indices or metadata).
2. For **each selected paper**:
   - Prefer ingesting by `pdf_url` if available.
   - Otherwise, use whatever combination the PaperKB MCP expects (e.g., `source + external_id`).
3. Use **PaperKB MCP**:
   - Call `ingest_paper` for each paper.
   - If the number of selected papers &gt; 10, warn the user that ingestion may be slow and ask for confirmation or to reduce the set.
4. Wait until ingestion has completed for all selected papers.
   - Do not start retrieval/QA before ingestion is done.
5. Once done, summarize ingestion results:
   - How many papers were ingested.
   - Any ingestion failures or missing PDFs.

**Idempotency:**  
If a paper appears to have been ingested before (PaperKB MCP may indicate duplicates), avoid re‑ingesting unless the user explicitly asks for a refresh.

---

## Phase 3 – Retrieval &amp; Review Synthesis

Now the knowledge base contains the selected papers. You must:

### 3.1 Clarify the review goal

Ask the user (if not clear already):

- Do they want:
  - A **high‑level survey** (overview of the field)?
  - A **focused comparison** (e.g., only graph transformers vs. vanilla GNNs)?
  - A **timeline / evolution** (earliest to latest)?
  - A **methods vs. datasets vs. tasks** comparison table?

Keep the review target in mind; it should drive how you query the KB.

### 3.2 Retrieve supporting context (PaperKB MCP)

1. Use **PaperKB MCP** to get relevant chunks:
   - Call `qa_over_papers` with:
     - `paper_ids`: the IDs of the ingested papers.
     - `question`: a focused query such as:
       - “What are the key modeling approaches used across these papers for &lt;TOPIC&gt;?”
       - “How do these papers differ in datasets, metrics, and reported performance?”
       - “What are the main limitations and open problems identified by these works?”
     - `top_k`: start with ~30–50 chunks; adjust if user wants more/less depth.
2. Do **not** hallucinate content beyond what the returned chunks support.
3. Optionally perform multiple retrieval passes for sub‑questions:
   - One pass for **methods**,
   - One for **datasets/benchmarks**,
   - One for **results/metrics**,
   - One for **limitations/future work**.

### 3.3 Synthesize a structured literature review

Based on the retrieved chunks (and only those), generate a structured output. Prefer a format like:

1. **Introduction**
   - Short definition of the topic.
   - Why it matters.

2. **Key Methods / Model Families**
   - Group papers into 2–5 method categories.
   - For each category:
     - Brief description of the method idea.
     - List representative papers (with year &amp; venue).
     - Mention any typical architectural patterns.

3. **Datasets and Evaluation Protocols**
   - Summarize which datasets / benchmarks are most commonly used.
   - Note any differences in experimental settings that affect comparability.

4. **Empirical Findings**
   - High‑level observations: what tends to work better and under what conditions.
   - Avoid claiming precise numbers unless clearly supported by the retrieved chunks.

5. **Limitations and Open Problems**
   - Collect limitations explicitly mentioned in the papers.
   - Highlight gaps, failure modes, or unexplored regimes.

6. **Future Directions**
   - Reasonable extrapolations grounded in observed limitations.
   - Clearly separate “what papers say” vs. “your own speculation”.

Whenever possible:

- **Tie claims back to specific papers** (e.g., “Paper A (2023, NeurIPS)”, “Paper B (2022, ICLR)”).
- Use neutral, academic tone.
- Avoid over‑generalizing from single‑paper findings.

---

## Guardrails &amp; Constraints

- **No silent ingestion:** always get user confirmation before ingesting papers.
- **Ingestion size limit:** by default, do not ingest more than 10 papers per run unless the user explicitly requests a larger batch.
- **Grounding:** only attribute facts to papers if supported by the content returned via PaperKB MCP.
- **Transparency:** clearly distinguish:
  - Facts derived from the KB chunks.
  - Your own higher‑level interpretations or hypotheses.

---

## Example Interaction (Conceptual)

User:

&gt; /lit-review graph neural networks for traffic prediction

You:

1. Use AcademicSearch MCP → `search_papers` (query: “graph neural networks for traffic prediction”, last 5 years).
2. Show top 15 papers with indices.
3. Ask:

&gt; I’ve found 15 candidate papers. Please tell me which indices to ingest (e.g., “1,3,5-8”) or say “top 5” / “top 10”.

User:

&gt; Let’s ingest top 5.

You:

1. Call PaperKB MCP → `ingest_paper` on those 5.
2. After ingestion, ask:

&gt; Do you prefer a high-level survey of approaches, or a detailed methods/datasets comparison?

User:

&gt; Detailed methods/datasets comparison.

You:

1. Use PaperKB MCP → `qa_over_papers` with a question focused on methods/datasets.
2. Generate a structured review as per the outline above, anchored to the 5 papers.

