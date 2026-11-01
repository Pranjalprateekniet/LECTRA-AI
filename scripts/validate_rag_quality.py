"""Stage 5 RAG Quality Validation across representative query types."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from lectra_core.config import get_settings
from lectra_core.generation.schemas import GenerationRequest
from lectra_core.generation.service import GenerationService


REPRESENTATIVE_TEST_CASES = [
    {
        "id": "q01_concept_greedy_choice",
        "category": "conceptual",
        "query": "Why do we sort meetings by end time rather than start time in the meeting room problem?",
        "expected_status": "answered",
        "expected_youtube_id": "II6ziNnub1Q",
    },
    {
        "id": "q07_algo_two_pointer_platforms",
        "category": "algorithm_explanation",
        "query": "How does the two-pointer approach work for finding the minimum number of platforms?",
        "expected_status": "answered",
        "expected_youtube_id": "dxVcMDI7vyI",
    },
    {
        "id": "q13_compl_platforms_space_time",
        "category": "complexity",
        "query": "What is the overall time and space complexity of finding the minimum platforms using two pointers?",
        "expected_status": "answered",
        "expected_youtube_id": "dxVcMDI7vyI",
    },
    {
        "id": "q19_step_job_sequencing_walkthrough",
        "category": "multi_step",
        "query": "Walk through the greedy choice and timeline slot assignment for Job Sequencing with deadlines.",
        "expected_status": "answered",
        "expected_youtube_id": "LjPx4wQaRIs",
    },
    {
        "id": "q02_concept_knapsack_ratio",
        "category": "multiple_chunks",
        "query": "Why is value per unit weight used to choose items in fractional knapsack?",
        "expected_status": "answered",
        "expected_youtube_id": "F_DDzYnxO14",
    },
    {
        "id": "q24_comp_fractional_vs_01_knapsack",
        "category": "cross_video_or_partial",
        "query": "What is the difference between fractional knapsack and 0/1 knapsack?",
        "expected_status": ["answered", "partially_answered", "insufficient_context"],
        "expected_youtube_id": "F_DDzYnxO14",
    },
    {
        "id": "q45_part_knapsack_with_negative_weights",
        "category": "partially_supported",
        "query": "Can fractional knapsack be solved greedily if some items have negative weights?",
        "expected_status": ["partially_answered", "insufficient_context"],
        "expected_youtube_id": None,
    },
    {
        "id": "q40_neg_dijkstra_shortest_path",
        "category": "completely_unsupported",
        "query": "How does Dijkstra algorithm find single-source shortest paths in weighted directed graphs?",
        "expected_status": "insufficient_context",
        "expected_youtube_id": None,
    },
]


def run_rag_quality_validation():
    settings = get_settings()
    service = GenerationService(settings=settings)

    results: List[Dict[str, Any]] = []
    all_passed = True

    try:
        for tc in REPRESENTATIVE_TEST_CASES:
            print(f"Testing {tc['id']} ({tc['category']}): {tc['query'][:60]}...")
            req = GenerationRequest(query=tc["query"], top_k=5)
            ans = service.generate_answer(req)

            status_ok = (
                ans.status == tc["expected_status"]
                if isinstance(tc["expected_status"], str)
                else ans.status in tc["expected_status"]
            )

            # Check citations
            citations_valid = True
            for cit in ans.citations:
                if not cit.youtube_id or not cit.video_title or cit.start_seconds < 0:
                    citations_valid = False
                if cit.end_seconds < cit.start_seconds:
                    citations_valid = False

            if tc["category"] == "completely_unsupported":
                # Must have 0 citations and no hallucinated video links
                if len(ans.citations) > 0:
                    citations_valid = False

            case_passed = status_ok and citations_valid
            if not case_passed:
                all_passed = False

            item_result = {
                "id": tc["id"],
                "category": tc["category"],
                "query": tc["query"],
                "status": ans.status,
                "status_expected": tc["expected_status"],
                "status_ok": status_ok,
                "citations_count": len(ans.citations),
                "citations": [
                    {
                        "source_id": c.source_id,
                        "youtube_id": c.youtube_id,
                        "video_title": c.video_title,
                        "start_seconds": c.start_seconds,
                        "end_seconds": c.end_seconds,
                    }
                    for c in ans.citations
                ],
                "answer_preview": ans.answer[:200] + "...",
                "passed": case_passed,
            }
            results.append(item_result)
            print(f"  -> Result: {ans.status} | Citations: {len(ans.citations)} | Passed: {case_passed}")
            time.sleep(2.5)

    finally:
        service.close()

    summary = {
        "status": "PASS" if all_passed else "FAIL",
        "total_cases": len(results),
        "passed_cases": sum(1 for r in results if r["passed"]),
        "results": results,
    }

    report_path = Path("reports/phase9_rag_quality.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nFinal RAG Quality Result: {summary['status']} ({summary['passed_cases']}/{summary['total_cases']} passed)")
    return summary


if __name__ == "__main__":
    run_rag_quality_validation()

