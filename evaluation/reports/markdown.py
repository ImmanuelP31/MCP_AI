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
            "| Config | Attempted | Provider OK | Provider Success | Quality Validity | "
            "Tool Recall | Tool Precision | Unexpected Tools | Unknown/Disallowed | "
            "E2E Validity |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in payload.summaries:
        lines.append(
            f"| {summary['config']} | {summary['cases']} | "
            f"{_int(summary.get('provider_successful_cases'))} | "
            f"{_number(summary.get('provider_success_rate')):.4f} | "
            f"{_number(summary['workflow_validity_rate']):.4f} | "
            f"{_number(summary['tool_recall']):.4f} | "
            f"{_number(summary['tool_precision']):.4f} | "
            f"{_number(summary.get('benchmark_unexpected_tool_rate')):.4f} | "
            f"{_number(summary.get('unknown_or_disallowed_tool_rate')):.4f} | "
            f"{_number(summary.get('end_to_end_workflow_validity_rate')):.4f} |"
        )
    lines.extend(
        [
            "",
            (
                "Quality metrics use provider-successful cases only. End-to-end metrics include "
                "provider availability failures."
            ),
            (
                "`Unexpected Tools` means the tool existed but was outside benchmark expected or "
                "acceptable tools. `Unknown/Disallowed` means an untrusted or undiscovered tool "
                "was produced."
            ),
        ]
    )
    failure_counts: dict[tuple[str, str], int] = {}
    for item in payload.cases:
        if item.get("workflow_valid"):
            continue
        stage = str(item.get("error_stage") or "unknown")
        reason = str(item.get("error_reason") or item.get("error") or "unknown")
        failure_counts[(stage, reason)] = failure_counts.get((stage, reason), 0) + 1
    if failure_counts:
        lines.extend(
            [
                "",
                "## Failure Taxonomy",
                "",
                "| Error Stage | Error Reason | Cases |",
                "| --- | --- | ---: |",
            ]
        )
        for (stage, reason), count in sorted(
            failure_counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )[:12]:
            lines.append(f"| {stage} | {_escape(reason[:180])} | {count} |")
        retry_cases = sum(1 for item in payload.cases if item.get("retry_attempted"))
        finish_reasons = sorted(
            {
                str(item.get("finish_reason"))
                for item in payload.cases
                if item.get("finish_reason")
            }
        )
        lines.extend(
            [
                "",
                f"Retry attempts recorded: {retry_cases}",
                "Provider finish reasons: "
                f"{', '.join(finish_reasons) if finish_reasons else 'none recorded'}",
            ]
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


def _int(value: object) -> int:
    return int(value) if isinstance(value, int | float) else 0


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
