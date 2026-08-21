# AI Engineering Workflow Evaluation Report

Generated: `2026-08-20T22:45:13Z`
Mode: `real`
Dataset: `evaluation/datasets/heldout_adversarial_engineering_tasks.json`
Provider evaluation: `planner_quality`
Pace seconds: `7.0`

These results are deterministic/mock when `mode=mock`. They should not be presented as live LLM quality measurements.

## Summary

| Config | Attempted | Provider OK | Provider Success | Quality Validity | Plan Accepted | Tool Recall | Tool Precision | Unexpected Tools | Unknown Calls | Unknown Cases | E2E Validity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic_rag_graph | 50 | 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Quality metrics use provider-successful cases only. End-to-end metrics include provider availability failures.
`Plan Accepted` means the planned workflow satisfied benchmark policy/approval expectations. It is not tool execution success unless the benchmark explicitly runs execution.
`Unexpected Tools` means the tool existed but was outside benchmark expected or acceptable tools. `Unknown Calls` means unknown/disallowed tool attempts divided by all generated tool attempts. `Unknown Cases` means provider-successful cases with at least one unknown/disallowed tool.

## Failure Categories

| Category | Cases |
| --- | ---: |
| PROVIDER_FAILURE | 50 |

## Failure Taxonomy

| Error Stage | Error Reason | Cases |
| --- | --- | ---: |
| provider_http | HTTP 429 | 50 |

Retry attempts recorded: 50
Provider finish reasons: none recorded

## Interpretation Guardrails

- The benchmark is synthetic and deterministic by default.
- Mock mode does not consume live LLM tokens and sets token/cost metrics to zero/null.
- Real benchmark runs require a configured provider and should be compared against the same dataset.
- RAG context is evidence only; policy, authorization, and approval remain backend-enforced.

## Dataset Coverage

- heldout adversarial: 50
