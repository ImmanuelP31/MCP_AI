from __future__ import annotations

import argparse

from evaluation.runner import run_evaluation
from evaluation.scenarios import config_by_name, evaluation_configs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI engineering workflow evaluation.")
    parser.add_argument(
        "--config",
        default="all",
        help="One config name or 'all'. Options: "
        + ", ".join(config.name for config in evaluation_configs()),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional case limit for smoke runs.",
    )
    parser.add_argument(
        "--mode",
        default="mock",
        choices=["mock", "real"],
        help="Use mock for deterministic CI; real labels provider-backed runs.",
    )
    parser.add_argument(
        "--dataset",
        default="synthetic",
        choices=["synthetic", "heldout_adversarial"],
        help="Benchmark dataset to evaluate.",
    )
    args = parser.parse_args()
    configs = (
        evaluation_configs()
        if args.config == "all"
        else (config_by_name(args.config),)
    )
    result = run_evaluation(
        selected_configs=configs,
        limit=args.limit,
        mode=args.mode,
        dataset_name=args.dataset,
    )
    for summary in result.summaries:
        message = (
            "{config}: cases={cases} provider_ok={provider_successful_cases} "
            "provider_success={provider_success_rate:.3f} "
            "quality_valid={workflow_validity_rate:.3f} "
            "plan_acceptance={plan_acceptance_rate:.3f} "
            "unexpected_tools={benchmark_unexpected_tool_rate:.3f} "
            "unknown_tool_calls={unknown_tool_call_rate:.3f} "
            "rag={rag_recall_at_k:.3f}"
        )
        print(
            message.format(**summary)
        )


if __name__ == "__main__":
    main()
