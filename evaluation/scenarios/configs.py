from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationConfig:
    name: str
    label: str
    use_all_tools: bool
    use_semantic_retrieval: bool
    use_rag: bool
    use_capability_graph: bool
    planner_mode: str = "mock"


CONFIGS = (
    EvaluationConfig(
        name="all_tools",
        label="A: LLM planner with all tools",
        use_all_tools=True,
        use_semantic_retrieval=False,
        use_rag=False,
        use_capability_graph=False,
    ),
    EvaluationConfig(
        name="semantic",
        label="B: LLM planner + semantic tool retrieval",
        use_all_tools=False,
        use_semantic_retrieval=True,
        use_rag=False,
        use_capability_graph=False,
    ),
    EvaluationConfig(
        name="semantic_rag",
        label="C: LLM planner + semantic tool retrieval + engineering RAG",
        use_all_tools=False,
        use_semantic_retrieval=True,
        use_rag=True,
        use_capability_graph=False,
    ),
    EvaluationConfig(
        name="semantic_rag_graph",
        label="D: LLM planner + semantic tools + RAG + capability graph",
        use_all_tools=False,
        use_semantic_retrieval=True,
        use_rag=True,
        use_capability_graph=True,
    ),
)


def evaluation_configs() -> tuple[EvaluationConfig, ...]:
    return CONFIGS


def config_by_name(name: str) -> EvaluationConfig:
    for config in CONFIGS:
        if config.name == name:
            return config
    raise ValueError(f"Unknown evaluation config: {name}")
