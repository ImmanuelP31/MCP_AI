from __future__ import annotations

from typing import Any


def render_markdown_report(payload: Any) -> str:
    lines = [
        "# AI Engineering Workflow Evaluation Report",
        "",
        f"Generated: `{payload.generated_at}`",
        f"Mode: `{payload.mode}`",
        f"Dataset: `{payload.dataset_path}`",
        "",
        (
            "These results are deterministic/mock when `mode=mock`. They should not be "
            "presented as live LLM quality measurements."
        ),
        "",
        "## Summary",
        "",
        (
            "| Config | Cases | Tool Recall | Tool Precision | Validity | Hallucination | "
            "RAG Recall@K | Approval Accuracy | E2E Latency ms |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in payload.summaries:
        lines.append(
            f"| {summary['config']} | {summary['cases']} | "
            f"{_number(summary['tool_recall']):.4f} | "
            f"{_number(summary['tool_precision']):.4f} | "
            f"{_number(summary['workflow_validity_rate']):.4f} | "
            f"{_number(summary['hallucinated_tool_rate']):.4f} | "
            f"{_number(summary['rag_recall_at_k']):.4f} | "
            f"{_number(summary['approval_classification_accuracy']):.4f} | "
            f"{_number(summary['end_to_end_latency_ms']):.2f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation Guardrails",
            "",
            "- The benchmark is synthetic and deterministic by default.",
            (
                "- Mock mode does not consume live LLM tokens and sets token/cost metrics "
                "to zero/null."
            ),
            (
                "- Real benchmark runs require a configured provider and should be compared "
                "against the same dataset."
            ),
            (
                "- RAG context is evidence only; policy, authorization, and approval remain "
                "backend-enforced."
            ),
            "",
            "## Dataset Coverage",
            "",
        ]
    )
    categories: dict[str, set[str]] = {}
    for item in payload.cases:
        category = str(item["category"])
        case_id = str(item["id"])
        categories.setdefault(category, set()).add(case_id)
    for category, case_ids in sorted(categories.items()):
        lines.append(f"- {category}: {len(case_ids)}")
    return "\n".join(lines) + "\n"


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0
