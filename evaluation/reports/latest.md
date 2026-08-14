# AI Engineering Workflow Evaluation Report

Generated: `2026-08-14T08:21:08Z`
Mode: `real`
Dataset: `C:\Users\Imman\OneDrive\Desktop\MCP PROJECT\evaluation\datasets\heldout_adversarial_engineering_tasks.json`

These results are deterministic/mock when `mode=mock`. They should not be presented as live LLM quality measurements.

## Summary

| Config | Attempted | Provider OK | Provider Success | Quality Validity | Tool Recall | Tool Precision | Unexpected Tools | Unknown Calls | Unknown Cases | E2E Validity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic_rag_graph | 50 | 30 | 0.6000 | 0.9000 | 0.3556 | 0.6906 | 0.4694 | 0.0000 | 0.0000 | 0.5400 |

Quality metrics use provider-successful cases only. End-to-end metrics include provider availability failures.
`Unexpected Tools` means the tool existed but was outside benchmark expected or acceptable tools. `Unknown Calls` means unknown/disallowed tool attempts divided by all generated tool attempts. `Unknown Cases` means provider-successful cases with at least one unknown/disallowed tool.

## Failure Categories

| Category | Cases |
| --- | ---: |
| PROVIDER_FAILURE | 20 |
| WORKFLOW_VALIDATION_FAILURE | 3 |

## Failure Taxonomy

| Error Stage | Error Reason | Cases |
| --- | --- | ---: |
| provider_http | HTTP 429 | 20 |
| workflow_validation | missing_dependency: Dependency node_0 does not exist.; invalid_condition: Condition source node_0 does not exist.; missing_edge_source: Edge source node_0 missing. | 1 |
| workflow_validation | missing_dependency: Dependency node_0 does not exist.; missing_edge_source: Edge source node_0 missing. | 1 |
| workflow_validation | missing_dependency: Dependency summarize_diff_node does not exist.; missing_edge_source: Edge source summarize_diff_node missing. | 1 |

Retry attempts recorded: 0
Provider finish reasons: none recorded

## Interpretation Guardrails

- The benchmark is synthetic and deterministic by default.
- Mock mode does not consume live LLM tokens and sets token/cost metrics to zero/null.
- Real benchmark runs require a configured provider and should be compared against the same dataset.
- RAG context is evidence only; policy, authorization, and approval remain backend-enforced.

## Dataset Coverage

- heldout adversarial: 50
