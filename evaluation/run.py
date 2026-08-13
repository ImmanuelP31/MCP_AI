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
        print(
            "{config}: cases={cases} valid={workflow_validity_rate:.3f} "
            "hallucination={hallucinated_tool_rate:.3f} rag={rag_recall_at_k:.3f}".format(
                **summary
            )
        )


if __name__ == "__main__":
    main()
