from __future__ import annotations

from mcp_ops_ai_agent.engineering_rag.models import (
    EngineeringKnowledgeSearchRequest,
    KnowledgeSearchMode,
    RagBenchmarkCase,
    RagEvaluationResult,
)
from mcp_ops_ai_agent.engineering_rag.service import EngineeringRagService

BENCHMARK_CASES: tuple[RagBenchmarkCase, ...] = (
    RagBenchmarkCase(
        "rag-001",
        "Deploy payments-api to staging",
        ("PAYMENTS-DEPLOY-03", "ENG-POLICY-14"),
    ),
    RagBenchmarkCase("rag-002", "Who owns payments-api?", ("PAYMENTS-API-OWNERSHIP-01",)),
    RagBenchmarkCase("rag-003", "Why did the latest build fail?", ("CICD-STANDARDS-02",)),
    RagBenchmarkCase(
        "rag-004",
        "What tests are required before deployment?",
        ("TESTING-POLICY-11", "ENG-POLICY-14"),
    ),
    RagBenchmarkCase("rag-005", "Which tools can deploy staging?", ("MCP-TOOLS-DEPLOY-01",)),
    RagBenchmarkCase(
        "rag-006",
        "Production environment restrictions for rollback",
        ("ENV-PROD-09",),
    ),
    RagBenchmarkCase("rag-007", "orders-api API compatibility", ("ORDERS-API-API-01",)),
    RagBenchmarkCase("rag-008", "inventory-api service owner", ("INVENTORY-API-OWNERSHIP-01",)),
    RagBenchmarkCase(
        "rag-009",
        "run the project locally with docker compose",
        ("RUN-INSTRUCTIONS-04",),
    ),
    RagBenchmarkCase(
        "rag-010",
        "gateway-service architecture owner",
        ("GATEWAY-SERVICE-OWNERSHIP-01",),
    ),
)


def evaluate_engineering_rag(
    service: EngineeringRagService | None = None,
    *,
    mode: KnowledgeSearchMode = KnowledgeSearchMode.HYBRID,
    top_k: int = 5,
) -> RagEvaluationResult:
    rag = service or EngineeringRagService()
    recall_total = 0.0
    precision_total = 0.0
    reciprocal_rank_total = 0.0
    for case in BENCHMARK_CASES:
        response = rag.search(
            EngineeringKnowledgeSearchRequest(
                query=case.query,
                top_k=top_k,
                mode=mode,
                filters=case.filters,
            )
        )
        retrieved = [result.citation_id for result in response.results]
        expected = set(case.expected_document_ids)
        hits = [doc_id for doc_id in retrieved if doc_id in expected]
        recall_total += len(hits) / len(expected)
        precision_total += len(hits) / max(1, top_k)
        first_hit = next(
            (
                index
                for index, doc_id in enumerate(retrieved, start=1)
                if doc_id in expected
            ),
            None,
        )
        reciprocal_rank_total += 0.0 if first_hit is None else 1.0 / first_hit
    cases = len(BENCHMARK_CASES)
    return RagEvaluationResult(
        cases=cases,
        mode=mode.value,
        recall_at_k=round(recall_total / cases, 4),
        precision_at_k=round(precision_total / cases, 4),
        mrr=round(reciprocal_rank_total / cases, 4),
    )
