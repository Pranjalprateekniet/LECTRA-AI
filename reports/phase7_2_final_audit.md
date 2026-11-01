# Phase 7.2 — Final Evaluation Consistency Audit Report

**Date:** 2026-11-01
**Project:** YouTube Revision RAG (`Lectra`)
**Scope:** Evaluation consistency audit, reconciled dataset distribution, confusion matrix, groundedness and latency terminology clarifications, persistence verification.

---

## 1. Reconciled Dataset Distribution

The 46 evaluation questions in [`tests/evaluation/generation_questions.json`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/tests/evaluation/generation_questions.json) are partitioned strictly by their contract expected status:

| Question Classification | Expected Status | Count | Question IDs |
|---|:---:|:---:|---|
| **Fully Supported Positive Questions** | `answered` | **37** | `q01`–`q23`, `q25`–`q27`, `q29`–`q39` |
| **Partially Supported Questions** | `partially_answered` | **3** | `q24_comp_fractional_vs_01_knapsack`, `q_part_01_knapsack_greedy_and_dp`, `q_part_02_platforms_and_toposort` |
| **Negative / Unsupported Questions** | `insufficient_context` | **6** | `q28_comp_meetings_start_vs_end_sort`, `q40`–`q44` |
| **Total Evaluation Dataset** | — | **46** | All 46 verified questions |

### Reconciliation of the 38/38 Citation Coverage Metric in Phase 7.1
In Phase 7.1, citation coverage was reported with a denominator of **38** (`38/38`):
- **Root Cause of 38 Denominator:** The Phase 7.1 filtering logic used `category != "partially_supported"`. Because `q24` retained `category: "comparison"` while its expected status was changed to `"partially_answered"`, it slipped past the category filter and was counted among positive evaluations ($37 + 1 = 38$). Conversely, `q_part_01` and `q_part_02` were excluded because their category was `"partially_supported"`.
- **Reconciliation & Correction:** The evaluation runner [`scripts/evaluate_generation.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/scripts/evaluate_generation.py) now segments queries strictly by `expected_status`:
  - **Fully Supported Positives:** Denominator is exactly **37**.
    - Citation Coverage (Answered Positives): $37 / 37 = 100.0\%$
    - Citation Recall (All Positives): $37 / 37 = 100.0\%$
  - **Partially Supported:** Evaluated as an independent category ($N=3$).
    - Partial Citation Fidelity: $3 / 3 = 100.0\%$ (all 3 cited the supported sub-claim).
  - **Negative Queries:** Evaluated for zero hallucinated citations ($N=6$).
    - Abstention Accuracy: $6 / 6 = 100.0\%$ (all 6 returned 0 citations and empty citation array).

---

## 2. Confusion Matrix

The confusion matrix compares expected status against predicted status across all 46 evaluation questions loaded from [`reports/phase7_generation_results.jsonl`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/reports/phase7_generation_results.jsonl):

```
                       PREDICTED STATUS
               answered | partially_answered | insufficient_context | Total
EXPECTED -------------------------------------------------------------------
answered            37  |          0         |          0           |   37
partially_answered   0  |          3         |          0           |    3
insufficient_ctx     0  |          0         |          6           |    6
----------------------------------------------------------------------------
Total               37  |          3         |          6           |   46
```

- **Diagonal Elements (Exact Matches):** $37 + 3 + 6 = 46$
- **Off-Diagonal Errors:** $0$
- **Overall Status Accuracy:** **100.0%** ($46 / 46$)

---

## 3. Metric Definitions and Denominators

| Metric | Exact Mathematical Formula | Value | Denominator Scope & Audit |
|---|:---:|:---:|---|
| **Overall Status Accuracy** | $\frac{\sum \mathbb{I}(\text{pred\_status} = \text{exp\_status})}{N_{\text{total}}}$ | **100.0%** (46/46) | All 46 evaluation queries in the benchmark. |
| **Abstention Accuracy (Negatives)** | $\frac{\sum_{i \in \text{neg}} \mathbb{I}(\text{status}_i = \text{insufficient\_ctx} \land \text{cits}_i = 0)}{N_{\text{neg}}}$ | **100.0%** (6/6) | All 6 negative / unsupported queries (`q28`, `q40`–`q44`). |
| **Citation Coverage (Answered Positives)** | $\frac{\sum_{i \in \text{ans\_pos}} \mathbb{I}(\text{cits}_i > 0)}{N_{\text{ans\_pos}}}$ | **100.0%** (37/37) | All answered positive queries ($N=37$). Measures whether generation reliably attaches citations when answering. |
| **Citation Recall (All Positives)** | $\frac{\sum_{i \in \text{exp\_pos}} \mathbb{I}(\text{cits}_i > 0)}{N_{\text{exp\_pos}}}$ | **100.0%** (37/37) | All 37 expected positive queries regardless of whether the model answered or abstained. |
| **Partial Citation Fidelity** | $\frac{\sum_{i \in \text{part}} \mathbb{I}(\text{status}_i = \text{partially\_answered} \land \text{cits}_i > 0)}{N_{\text{part}}}$ | **100.0%** (3/3) | All 3 partially supported queries (`q24`, `q_part_01`, `q_part_02`). |
| **Citation Syntactic Validity** | $\frac{\sum_{c} \mathbb{I}(\text{valid\_yt\_url}(c))}{N_{\text{citations}}}$ | **100.0%** (98/98) | Syntactic verification that URLs match `https://www.youtube.com/watch?v=...&t=...`. |
| **Citation Video Alignment** | $\frac{\sum_{i \in \text{ans\_pos}} \mathbb{I}(\forall c \in \text{cits}_i, c.\text{yt\_id} \in \text{exp\_yts}_i)}{N_{\text{ans\_pos}}}$ | **100.0%** (37/37) | Coarse groundedness: citations point to the expected lecture video ID in SQLite. |

---

## 4. Groundedness Terminology & Limitations

To maintain scientific precision, the system distinguishes four tiers of verification:

1. **Citation ID Validity (Syntactic):**
   - *What is verified:* Inline tokens (`[S1]`, `[S2]`) map to source keys present in `source_map`. Unknown IDs (e.g. `[S99]`) are rejected.
   - *Limitation:* Does not verify whether the chunk supports the claim.
2. **Citation URL and Timestamp Validity (Syntactic & Referential):**
   - *What is verified:* URLs are synthesized strictly by server code using SQLite records (`youtube_id` and `start_seconds`).
   - *Limitation:* Does not prove the instructor spoke about the claim at that exact second.
3. **Citation-to-Video Alignment (Coarse Groundedness):**
   - *What is verified:* The cited chunk belongs to the video specified in `expected_youtube_ids`.
   - *Limitation:* Video-level match only; does not prove chunk-level semantic entailment.
4. **Semantic Relevance of a Citation to its Claim (Fine-Grained Entailment):**
   - *What is required:* Sentence-level Natural Language Inference (NLI) proving that the chunk text logically entails the generated statement.
   - *Limitation:* **Not automated.** Semantic claim entailment is not evaluated by automated unit metrics and requires manual verification or an auxiliary NLI entailment model.

---

## 5. Latency Measurements & Limitations

Two distinct latency figures were recorded during evaluation. They represent different sample scopes and must not be conflated:

### A. Full Benchmark Latency ($N=46$ queries)
- **Mean Latency:** **15,746.98 ms (~15.75 s)**
- **Scope:** Complete evaluation across all 46 questions during the end-to-end benchmark.
- **Cause:** Open-weights `openai/gpt-oss-120b` generates variable-length internal reasoning chains before emitting structured JSON. Queries with extensive algorithm walkthroughs, negative queries verifying absence of evidence, and multi-step comparisons generated long reasoning traces (up to 33.0s on `q06`).

### B. Instrumented Pipeline Probe ($N=5$ queries)
- **Mean Latency:** **6,013.51 ms (~6.01 s)**
- **Scope:** Isolated 5-query probe designed exclusively to measure stage-by-stage runtime distribution:
  - *Query Embedding (`embeddinggemma-2`):* 16.59 ms (0.28%)
  - *Qdrant Cloud Retrieval:* 597.98 ms (9.94%)
  - *Context Construction:* 0.26 ms (< 0.01%)
  - *Groq Request (`gpt-oss-120b`):* 5,382.03 ms (89.49%)
  - *Citation Validation & URL Synthesis:* 0.05 ms (< 0.01%)
- **Clarification:** The 6.01s sample average was skewed by several concise queries (`q15` @ 1.3s, `q01` @ 2.3s, `q07` @ 2.5s) and **does not represent a benchmark-wide speedup**. The benchmark-wide average remains ~15.75 seconds.

---

## 6. Persistence & Reproducibility Verification

1. **Immediate JSONL Writes:** [`scripts/evaluate_generation.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/scripts/evaluate_generation.py#L320-L330) appends and flushes every completed question immediately to [`reports/phase7_generation_results.jsonl`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/reports/phase7_generation_results.jsonl). Interrupted runs retain completed queries.
2. **Zero-API-Call Report Regeneration:**
   ```bash
   .venv/bin/python scripts/evaluate_generation.py --regenerate-report
   ```
   Re-reads [`reports/phase7_generation_results.jsonl`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/reports/phase7_generation_results.jsonl), compiles all audited metrics, and writes [`reports/phase7_generation_evaluation.md`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/reports/phase7_generation_evaluation.md) in ~4 seconds without importing or calling Groq.
3. **No Duplicate Records:** In-memory and on-disk records are keyed by question ID (`dict[str, Any]`), ensuring targeted evaluations update existing records in place.

---

## 7. Automated Test Verification Results

All checks passed with zero errors:

1. **Unit & API Tests:**
   ```bash
   .venv/bin/pytest core/tests/retrieval/ core/tests/generation/ core/tests/embeddings/ core/tests/vectorstore/ backend/tests/ core/tests/test_config.py
   ```
   **74 passed in 7.15s** (100% pass rate).

2. **Ruff Linter:**
   ```bash
   .venv/bin/ruff check core/src core/tests backend/src backend/tests scripts/evaluate_generation.py
   ```
   **All checks passed!** (0 errors).

3. **Mypy Type Checking:**
   ```bash
   .venv/bin/mypy core/src backend/src
   ```
   **Success: no issues found in 54 source files**.
