# AI Engineering Workflow Evaluation Report

Generated: `2026-08-11T14:39:36Z`
Mode: `mock`
Dataset: `C:\Users\Imman\OneDrive\Desktop\MCP PROJECT\evaluation\datasets\engineering_tasks.json`

These results are deterministic/mock when `mode=mock`. They should not be presented as live LLM quality measurements.

## Summary

| Config | Cases | Tool Recall | Tool Precision | Validity | Hallucination | RAG Recall@K | Approval Accuracy | E2E Latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_tools | 330 | 0.5379 | 0.8409 | 0.6545 | 0.2226 | 0.0000 | 0.8091 | 149.29 |
| semantic | 330 | 0.5015 | 0.8477 | 0.7455 | 0.2016 | 0.0000 | 0.8091 | 151.95 |
| semantic_rag | 330 | 0.5879 | 0.8433 | 0.7455 | 0.2013 | 0.6955 | 0.8091 | 171.54 |
| semantic_rag_graph | 330 | 0.5879 | 0.8433 | 0.7455 | 0.2013 | 0.6955 | 0.8091 | 167.42 |

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
