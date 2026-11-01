# Phase 6 — Semantic Retrieval Engine Evaluation Report

**Generated:** 2026-11-01 06:13:06 UTC  
**Embedding Model:** `google/embeddinggemma-2` (768d, L2 norm)  
**Vector Store:** Qdrant Cloud (`revision_chunks`)  
**Total Questions Evaluated:** 44 (39 positive, 5 negative)  
**Average Query Latency:** 492.49 ms  
**Total Benchmark Wall-clock Time:** 21.67 s  

## 1. Executive Summary & Aggregate Metrics

| Granularity | Metric | Score | Percentage | Description |
|---|---|:---:|:---:|---|
| **Chunk-level** | Recall@1 | `0.4872` | 48.7% | Supporting chunk at Rank 1 |
| **Chunk-level** | Recall@3 | `0.8205` | 82.1% | Supporting chunk within Top-3 |
| **Chunk-level** | Recall@5 | `0.8974` | 89.7% | Supporting chunk within Top-5 |
| **Chunk-level** | MRR | `0.6547` | - | Mean Reciprocal Rank of supporting chunk |
| **Video-level** | Recall@1 | `1.0000` | 100.0% | Source video at Rank 1 |
| **Video-level** | Recall@3 | `1.0000` | 100.0% | Source video within Top-3 |
| **Video-level** | Recall@5 | `1.0000` | 100.0% | Source video within Top-5 |
| **Video-level** | MRR | `1.0000` | - | Mean Reciprocal Rank of source video |

## 2. Category Performance Breakdown

| Category | Count | Video R@1 | Video R@5 | Chunk R@1 | Chunk R@5 | Chunk MRR |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `algorithm_explanation` | 6 | 100.0% | 100.0% | 66.7% | 100.0% | `0.8056` |
| `alternate_wording` | 5 | 100.0% | 100.0% | 60.0% | 100.0% | `0.7667` |
| `comparison` | 5 | 100.0% | 100.0% | 60.0% | 80.0% | `0.7000` |
| `complexity` | 5 | 100.0% | 100.0% | 0.0% | 60.0% | `0.1733` |
| `conceptual` | 6 | 100.0% | 100.0% | 33.3% | 83.3% | `0.5000` |
| `example_based` | 6 | 100.0% | 100.0% | 66.7% | 100.0% | `0.8333` |
| `problem_specific` | 6 | 100.0% | 100.0% | 50.0% | 100.0% | `0.7500` |

## 3. Negative & Out-of-Domain Query Analysis

Negative queries evaluate topics completely absent from the indexed dataset (e.g., Dijkstra, Kahn's algorithm, 0/1 Knapsack DP recurrence, Trie trees, Kadane). Because `score_threshold` is optional and disabled by default, nearest-neighbor search returns the top cosine neighbors. The table below analyzes top scores and topics retrieved:

| Query ID | Out-of-Domain Query | Top Score | Top Video | Chunk | Assessment |
|---|---|:---:|---|:---:|---|
| `q40_neg_dijkstra_shortest_path` | How does Dijkstra algorithm find single-source shortest paths in weighted directed graphs? | `0.6758` | Minimum Platforms | Greedy Algorithms | 12 | Moderate score; requires LLM abstention prompt (Phase 7) |
| `q41_neg_topological_sort` | How do you detect a cycle in a directed graph using Kahn algorithm with in-degrees? | `0.6448` | Minimum Coins | Greedy Algorithms | 7 | Low similarity (<0.65); safely rejected by threshold or LLM abstention |
| `q42_neg_01_knapsack_dp` | How to write the 2D dynamic programming recurrence relation for the 0/1 knapsack problem? | `0.6823` | Fractional Knapsack | Greedy Algorithms | 0 | Moderate score; requires LLM abstention prompt (Phase 7) |
| `q43_neg_trie_prefix_tree` | How to implement insert and search operations in a Trie prefix tree? | `0.6418` | N meetings In One Room | Greedy Algorithm | 11 | Low similarity (<0.65); safely rejected by threshold or LLM abstention |
| `q44_neg_kadane_max_subarray` | What is Kadane algorithm for finding the maximum contiguous subarray sum in linear time? | `0.6950` | Fractional Knapsack | Greedy Algorithms | 9 | Moderate score; requires LLM abstention prompt (Phase 7) |

## 4. Failure & Misclassification Diagnosis

Identified 20 queries where supporting chunk was not Rank 1:

| Query ID | Query | Expected Chunks | Top Chunk | Chunk Rk | Video Rk | Diagnosis |
|---|---|---|---|:---:|:---:|---|
| `q01_concept_greedy_choice` | Why do we sort meetings by end time rather than start time in the meeting room problem? | `8750eea6-acc3-...` | `cd6bad07-c669-...` (N meetings In One Room | Greedy Algorithm) | 4 | 1 | Competition between adjacent chunks within the same video |
| `q02_concept_knapsack_ratio` | Why is value per unit weight used to choose items in fractional knapsack? | `9256dd15-38af-...` | `970eab30-61d0-...` (Fractional Knapsack | Greedy Algorithms) | 2 | 1 | Competition between adjacent chunks within the same video |
| `q05_concept_coins_greedy_failure` | When does the greedy approach fail for finding minimum coins? | `b332aac0-e3d3-...` | `ef5e12e7-4019-...` (Minimum Coins | Greedy Algorithms) | Miss (>5) | 1 | Competition between adjacent chunks within the same video |
| `q06_concept_platform_occupancy` | How does train arrival and departure change the number of active platforms at a railway station? | `47502158-b537-...` | `9b0cc7dc-8e4f-...` (Minimum Platforms | Greedy Algorithms) | 4 | 1 | Competition between adjacent chunks within the same video |
| `q10_algo_job_sequencing_array` | How is the slot array initialized and used in job sequencing? | `ef2e7f56-9d96-...` | `27854569-11ac-...` (Job Sequencing Problem | Greedy Algorithms) | 3 | 1 | Competition between adjacent chunks within the same video |
| `q11_algo_coins_greedy_loop` | How do we iterate over the coin denominations array to make change? | `a7ab19cb-cc86-...` | `b332aac0-e3d3-...` (Minimum Coins | Greedy Algorithms) | 2 | 1 | Competition between adjacent chunks within the same video |
| `q13_complexity_platforms` | What is the time complexity and space complexity of finding the minimum railway platforms? | `4a7f6ef1-d6cb-...` | `b0a20577-614d-...` (Minimum Platforms | Greedy Algorithms) | Miss (>5) | 1 | Competition between adjacent chunks within the same video |
| `q14_complexity_job_sequencing` | What is the time complexity of the job sequencing algorithm? | `7a582a97-cb18-...` | `ef2e7f56-9d96-...` (Job Sequencing Problem | Greedy Algorithms) | 3 | 1 | Competition between adjacent chunks within the same video |
| `q15_complexity_fractional_knapsack` | What is the time complexity of the fractional knapsack algorithm? | `b864957c-feaa-...` | `70f39599-429d-...` (Fractional Knapsack | Greedy Algorithms) | 5 | 1 | Competition between adjacent chunks within the same video |
| `q16_complexity_meetings` | What is the space complexity and time complexity of solving N meetings in one room? | `41de82ec-97f6-...` | `8750eea6-acc3-...` (N meetings In One Room | Greedy Algorithm) | Miss (>5) | 1 | Competition between adjacent chunks within the same video |
| `q17_complexity_coins` | What is the time complexity of the greedy coin change algorithm? | `ef5e12e7-4019-...` | `466a7632-64ac-...` (Minimum Coins | Greedy Algorithms) | 3 | 1 | Competition between adjacent chunks within the same video |
| `q20_example_platforms_train_intervals` | In the minimum platforms example, how do trains arriving at 900 and departing at 910 get processed? | `7681be17-5a11-...` | `464d5e23-aa8a-...` (Minimum Platforms | Greedy Algorithms) | 2 | 1 | Competition between adjacent chunks within the same video |
| `q21_example_knapsack_weight_50` | In the fractional knapsack example with knapsack capacity 50, which items are chosen? | `970eab30-61d0-...` | `9133f4ee-7f12-...` (Fractional Knapsack | Greedy Algorithms) | 2 | 1 | Competition between adjacent chunks within the same video |
| `q26_comp_job_sequencing_vs_meetings` | How does job sequencing with deadlines differ from scheduling non-overlapping meetings? | `9b1ccc2a-d2b1-...` | `cd6bad07-c669-...` (N meetings In One Room | Greedy Algorithm) | Miss (>5) | 1 | Competition between adjacent chunks within the same video |
| `q28_comp_meetings_start_vs_end_sort` | What happens if you sort meetings by start time instead of finish time? | `8750eea6-acc3-...` | `453289bf-92e0-...` (N meetings In One Room | Greedy Algorithm) | 2 | 1 | Competition between adjacent chunks within the same video |
| `q31_problem_job_max_deadline` | How do you determine the maximum deadline in job sequencing to size the schedule array? | `27854569-11ac-...` | `7a582a97-cb18-...` (Job Sequencing Problem | Greedy Algorithms) | 2 | 1 | Competition between adjacent chunks within the same video |
| `q32_problem_knapsack_item_structure` | What attributes does an item have in the fractional knapsack problem? | `987dba34-ea55-...` | `970eab30-61d0-...` (Fractional Knapsack | Greedy Algorithms) | 2 | 1 | Competition between adjacent chunks within the same video |
| `q34_problem_tie_breaker_meetings` | What is the tie-breaking rule if two meetings have the exact same ending time? | `ed17a080-5ac4-...` | `cd6bad07-c669-...` (N meetings In One Room | Greedy Algorithm) | 2 | 1 | Competition between adjacent chunks within the same video |
| `q36_synonym_railway_tracks` | How to calculate the minimum railway tracks needed to avoid train collisions? | `9b0cc7dc-8e4f-...` | `7a238c5b-eadf-...` (Minimum Platforms | Greedy Algorithms) | 2 | 1 | Competition between adjacent chunks within the same video |
| `q39_synonym_cash_dispenser` | How does an ATM dispense currency notes greedily to minimize the count of bills? | `cb1e9991-091e-...` | `b332aac0-e3d3-...` (Minimum Coins | Greedy Algorithms) | 3 | 1 | Competition between adjacent chunks within the same video |

## 5. Comprehensive Individual Query Log

| ID | Query | Category | Top Video | Top Score | Chunk Rk | Video Rk | Citation |
|---|---|---|---|:---:|:---:|:---:|---|
| `q01_concept_greedy_choice` | Why do we sort meetings by end time rather than start time in the meeting room problem? | `conceptual` | N meetings In One Room | Greedy Algorithm | `0.8164` | 4 | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=439) |
| `q02_concept_knapsack_ratio` | Why is value per unit weight used to choose items in fractional knapsack? | `conceptual` | Fractional Knapsack | Greedy Algorithms | `0.8394` | 2 | 1 | [Watch](https://www.youtube.com/watch?v=F_DDzYnxO14&t=437) |
| `q03_concept_platforms_arrival_departure` | Why can arrival and departure times be sorted separately in the minimum platforms problem? | `conceptual` | Minimum Platforms | Greedy Algorithms | `0.8439` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=dxVcMDI7vyI&t=357) |
| `q04_concept_job_deadline_day` | Why should a job with a given deadline be executed as late as possible? | `conceptual` | Job Sequencing Problem | Greedy Algorithms | `0.7424` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=LjPx4wQaRIs&t=347) |
| `q05_concept_coins_greedy_failure` | When does the greedy approach fail for finding minimum coins? | `conceptual` | Minimum Coins | Greedy Algorithms | `0.8397` | None | 1 | [Watch](https://www.youtube.com/watch?v=mVg9CfJvayM&t=394) |
| `q06_concept_platform_occupancy` | How does train arrival and departure change the number of active platforms at a railway station? | `conceptual` | Minimum Platforms | Greedy Algorithms | `0.7833` | 4 | 1 | [Watch](https://www.youtube.com/watch?v=dxVcMDI7vyI&t=0) |
| `q07_algo_two_pointer_platforms` | How does the two-pointer approach work for finding the minimum number of platforms? | `algorithm_explanation` | Minimum Platforms | Greedy Algorithms | `0.8451` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=dxVcMDI7vyI&t=887) |
| `q08_algo_meetings_loop` | How do we iterate through sorted meetings and update the end limit? | `algorithm_explanation` | N meetings In One Room | Greedy Algorithm | `0.7664` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=439) |
| `q09_algo_fractional_remainder` | How do you calculate the fractional value when an item cannot fit completely into the knapsack? | `algorithm_explanation` | Fractional Knapsack | Greedy Algorithms | `0.8502` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=F_DDzYnxO14&t=437) |
| `q10_algo_job_sequencing_array` | How is the slot array initialized and used in job sequencing? | `algorithm_explanation` | Job Sequencing Problem | Greedy Algorithms | `0.7573` | 3 | 1 | [Watch](https://www.youtube.com/watch?v=LjPx4wQaRIs&t=873) |
| `q11_algo_coins_greedy_loop` | How do we iterate over the coin denominations array to make change? | `algorithm_explanation` | Minimum Coins | Greedy Algorithms | `0.7538` | 2 | 1 | [Watch](https://www.youtube.com/watch?v=mVg9CfJvayM&t=479) |
| `q12_algo_meeting_comparator` | How should the custom comparator be implemented to sort meetings in C++ or Java? | `algorithm_explanation` | N meetings In One Room | Greedy Algorithm | `0.7740` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=700) |
| `q13_complexity_platforms` | What is the time complexity and space complexity of finding the minimum railway platforms? | `complexity` | Minimum Platforms | Greedy Algorithms | `0.8544` | None | 1 | [Watch](https://www.youtube.com/watch?v=dxVcMDI7vyI&t=798) |
| `q14_complexity_job_sequencing` | What is the time complexity of the job sequencing algorithm? | `complexity` | Job Sequencing Problem | Greedy Algorithms | `0.8189` | 3 | 1 | [Watch](https://www.youtube.com/watch?v=LjPx4wQaRIs&t=697) |
| `q15_complexity_fractional_knapsack` | What is the time complexity of the fractional knapsack algorithm? | `complexity` | Fractional Knapsack | Greedy Algorithms | `0.8055` | 5 | 1 | [Watch](https://www.youtube.com/watch?v=F_DDzYnxO14&t=87) |
| `q16_complexity_meetings` | What is the space complexity and time complexity of solving N meetings in one room? | `complexity` | N meetings In One Room | Greedy Algorithm | `0.8573` | None | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=526) |
| `q17_complexity_coins` | What is the time complexity of the greedy coin change algorithm? | `complexity` | Minimum Coins | Greedy Algorithms | `0.7801` | 3 | 1 | [Watch](https://www.youtube.com/watch?v=mVg9CfJvayM&t=322) |
| `q18_example_coins_49` | How is the greedy coin algorithm applied to make change for 49 rupees? | `example_based` | Minimum Coins | Greedy Algorithms | `0.8659` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=mVg9CfJvayM&t=170) |
| `q19_example_coins_87` | What coins are selected for the value 87 in the minimum coins problem? | `example_based` | Minimum Coins | Greedy Algorithms | `0.7956` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=mVg9CfJvayM&t=86) |
| `q20_example_platforms_train_intervals` | In the minimum platforms example, how do trains arriving at 900 and departing at 910 get processed? | `example_based` | Minimum Platforms | Greedy Algorithms | `0.8008` | 2 | 1 | [Watch](https://www.youtube.com/watch?v=dxVcMDI7vyI&t=708) |
| `q21_example_knapsack_weight_50` | In the fractional knapsack example with knapsack capacity 50, which items are chosen? | `example_based` | Fractional Knapsack | Greedy Algorithms | `0.8460` | 2 | 1 | [Watch](https://www.youtube.com/watch?v=F_DDzYnxO14&t=0) |
| `q22_example_job_deadlines` | In job sequencing, if a job has deadline 2 and profit 100, which day should it be placed on? | `example_based` | Job Sequencing Problem | Greedy Algorithms | `0.8171` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=LjPx4wQaRIs&t=434) |
| `q23_example_meetings_order` | How are meetings ordered when meeting one has start 1 and end 2 and meeting two has start 3 and end 4? | `example_based` | N meetings In One Room | Greedy Algorithm | `0.7943` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=350) |
| `q24_comp_fractional_vs_01_knapsack` | What is the difference between fractional knapsack and 0/1 knapsack? | `comparison` | Fractional Knapsack | Greedy Algorithms | `0.7855` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=F_DDzYnxO14&t=87) |
| `q25_comp_coins_greedy_vs_dp` | Why does the Indian currency system allow a greedy approach whereas other denomination systems require dynamic programming? | `comparison` | Minimum Coins | Greedy Algorithms | `0.7765` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=mVg9CfJvayM&t=479) |
| `q26_comp_job_sequencing_vs_meetings` | How does job sequencing with deadlines differ from scheduling non-overlapping meetings? | `comparison` | N meetings In One Room | Greedy Algorithm | `0.7312` | None | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=439) |
| `q27_comp_sorting_arrival_vs_departure` | In minimum platforms, why is sorting arrival times alone not sufficient compared to sorting both arrivals and departures? | `comparison` | Minimum Platforms | Greedy Algorithms | `0.8341` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=dxVcMDI7vyI&t=357) |
| `q28_comp_meetings_start_vs_end_sort` | What happens if you sort meetings by start time instead of finish time? | `comparison` | N meetings In One Room | Greedy Algorithm | `0.7841` | 2 | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=700) |
| `q29_problem_indian_denominations` | What are the available coin and note denominations in the minimum coins problem? | `problem_specific` | Minimum Coins | Greedy Algorithms | `0.7785` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=mVg9CfJvayM&t=0) |
| `q30_problem_meetings_one_based_index` | Does the N meetings in one room problem require 1-based indexing for meeting numbers? | `problem_specific` | N meetings In One Room | Greedy Algorithm | `0.8347` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=174) |
| `q31_problem_job_max_deadline` | How do you determine the maximum deadline in job sequencing to size the schedule array? | `problem_specific` | Job Sequencing Problem | Greedy Algorithms | `0.8071` | 2 | 1 | [Watch](https://www.youtube.com/watch?v=LjPx4wQaRIs&t=785) |
| `q32_problem_knapsack_item_structure` | What attributes does an item have in the fractional knapsack problem? | `problem_specific` | Fractional Knapsack | Greedy Algorithms | `0.8119` | 2 | 1 | [Watch](https://www.youtube.com/watch?v=F_DDzYnxO14&t=437) |
| `q33_problem_platform_initialization` | How are the platform count and result variables initialized in minimum platforms? | `problem_specific` | Minimum Platforms | Greedy Algorithms | `0.7714` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=dxVcMDI7vyI&t=887) |
| `q34_problem_tie_breaker_meetings` | What is the tie-breaking rule if two meetings have the exact same ending time? | `problem_specific` | N meetings In One Room | Greedy Algorithm | `0.7674` | 2 | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=439) |
| `q35_synonym_non_conflicting_events` | How to schedule maximum non-conflicting activities in a conference hall? | `alternate_wording` | N meetings In One Room | Greedy Algorithm | `0.7184` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=0) |
| `q36_synonym_railway_tracks` | How to calculate the minimum railway tracks needed to avoid train collisions? | `alternate_wording` | Minimum Platforms | Greedy Algorithms | `0.7263` | 2 | 1 | [Watch](https://www.youtube.com/watch?v=dxVcMDI7vyI&t=887) |
| `q37_synonym_continuous_knapsack` | What is the optimal strategy for the continuous knapsack problem? | `alternate_wording` | Fractional Knapsack | Greedy Algorithms | `0.7657` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=F_DDzYnxO14&t=0) |
| `q38_synonym_task_scheduling_profit` | How to maximize reward when scheduling tasks with expiration times? | `alternate_wording` | Job Sequencing Problem | Greedy Algorithms | `0.7327` | 1 | 1 | [Watch](https://www.youtube.com/watch?v=LjPx4wQaRIs&t=347) |
| `q39_synonym_cash_dispenser` | How does an ATM dispense currency notes greedily to minimize the count of bills? | `alternate_wording` | Minimum Coins | Greedy Algorithms | `0.7074` | 3 | 1 | [Watch](https://www.youtube.com/watch?v=mVg9CfJvayM&t=479) |
| `q40_neg_dijkstra_shortest_path` | How does Dijkstra algorithm find single-source shortest paths in weighted directed graphs? | `negative_out_of_domain` | Minimum Platforms | Greedy Algorithms | `0.6758` | - | - | [Watch](https://www.youtube.com/watch?v=dxVcMDI7vyI&t=1062) |
| `q41_neg_topological_sort` | How do you detect a cycle in a directed graph using Kahn algorithm with in-degrees? | `negative_out_of_domain` | Minimum Coins | Greedy Algorithms | `0.6448` | - | - | [Watch](https://www.youtube.com/watch?v=mVg9CfJvayM&t=563) |
| `q42_neg_01_knapsack_dp` | How to write the 2D dynamic programming recurrence relation for the 0/1 knapsack problem? | `negative_out_of_domain` | Fractional Knapsack | Greedy Algorithms | `0.6823` | - | - | [Watch](https://www.youtube.com/watch?v=F_DDzYnxO14&t=0) |
| `q43_neg_trie_prefix_tree` | How to implement insert and search operations in a Trie prefix tree? | `negative_out_of_domain` | N meetings In One Room | Greedy Algorithm | `0.6418` | - | - | [Watch](https://www.youtube.com/watch?v=II6ziNnub1Q&t=963) |
| `q44_neg_kadane_max_subarray` | What is Kadane algorithm for finding the maximum contiguous subarray sum in linear time? | `negative_out_of_domain` | Fractional Knapsack | Greedy Algorithms | `0.6950` | - | - | [Watch](https://www.youtube.com/watch?v=F_DDzYnxO14&t=785) |

## 6. Verification Against Completion Criteria

- [x] Natural-language query acceptance & validation.
- [x] EmbeddingGemma 2 query embedding generation (`task: search result | query: ...`).
- [x] Qdrant similarity search with optional top_k, score_threshold, and filters.
- [x] Payload metadata preserved with verified start/end timestamps and URLs.
- [x] Both Chunk-level and Video-level Recall@1, 3, 5 and MRR evaluated.
- [x] Negative out-of-domain queries evaluated.
- [x] Idempotent read-only execution; existing vectors, embeddings, and tables untouched.
