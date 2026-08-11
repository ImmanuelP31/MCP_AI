# AI Engineering Workflow Evaluation Report

Generated: `2026-08-11T06:03:26Z`
Mode: `mock`
Dataset: `C:\Users\Imman\OneDrive\Desktop\MCP PROJECT\evaluation\datasets\engineering_tasks.json`

These results are deterministic/mock when `mode=mock`. They should not be presented as live LLM quality measurements.

## Summary

| Config | Cases | Tool Recall | Tool Precision | Validity | Hallucination | RAG Recall@K | Approval Accuracy | E2E Latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_tools | 330 | 0.5379 | 0.8427 | 0.6545 | 0.2192 | 0.0000 | 0.8091 | 52.20 |
| semantic | 330 | 0.5424 | 0.8710 | 0.7455 | 0.1761 | 0.0000 | 0.8091 | 51.57 |
| semantic_rag | 330 | 0.6288 | 0.8720 | 0.7455 | 0.1706 | 0.7318 | 0.8091 | 55.84 |
| semantic_rag_graph | 330 | 0.6318 | 0.8659 | 0.7545 | 0.1755 | 0.7409 | 0.8091 | 57.39 |

## Interpretation Guardrails

- The benchmark is synthetic and deterministic by default.
- Mock mode does not consume live LLM tokens and sets token/cost metrics to zero/null.
- Real benchmark runs require a configured provider and should be compared against the same dataset.
- RAG context is evidence only; policy, authorization, and approval remain backend-enforced.

## Dataset Coverage

- CI/CD: 30
- build investigation: 30
- deployment planning: 30
- documentation lookup: 30
- multi-tool workflows: 30
- production approval: 30
- repository inspection: 30
- service ownership: 30
- staging deployment: 30
- test execution: 30
- ticket creation: 30
