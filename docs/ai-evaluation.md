# AI Evaluation

## Goal

The project evaluates AI workflow behavior quantitatively instead of relying on qualitative claims. The framework lives in `evaluation/` and generates deterministic mock results for CI/local validation.

## Dataset

The current dataset contains 330 synthetic enterprise engineering tasks across:

- build investigation
- CI/CD
- repository inspection
- test execution
- ticket creation
- documentation lookup
- service ownership
- deployment planning
- staging deployment
- production approval
- multi-tool workflows

Each item includes expected tools, acceptable tools, prohibited tools, required approvals, expected resources, relevant documents, and expected outcome.

## Configurations

- `all_tools`
- `semantic`
- `semantic_rag`
- `semantic_rag_graph`

## Metrics

Tracked metrics include tool recall, tool precision, exact tool-set accuracy, workflow validity, workflow completion, hallucinated tool rate, unnecessary tool calls, policy violation attempts, approval classification accuracy, RAG Recall@K, RAG MRR, workflow length, execution success, latency, token usage, and estimated cost when available.

## Latest Measured Mock Baseline

| Configuration | Cases | Tool Recall | Tool Precision | Workflow Validity | Hallucinated Tool Rate | RAG Recall@K | Execution Success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_tools | 330 | 0.5379 | 0.8427 | 0.6545 | 0.2192 | 0.0000 | 0.5455 |
| semantic | 330 | 0.5424 | 0.8710 | 0.7455 | 0.1761 | 0.0000 | 0.6364 |
| semantic_rag | 330 | 0.6288 | 0.8720 | 0.7455 | 0.1706 | 0.7318 | 0.6364 |
| semantic_rag_graph | 330 | 0.6318 | 0.8659 | 0.7545 | 0.1755 | 0.7409 | 0.6364 |

These are mock-mode results from `evaluation/results/latest.json`, not live LLM claims.

## Run

```bash
python -m evaluation.run --config semantic_rag_graph
```

Outputs:

- `evaluation/results/latest.json`
- `evaluation/results/latest.csv`
- `evaluation/reports/latest.md`

For a real benchmark, configure the model provider, disable deterministic mock mode in the runner configuration, run the same CLI, and label/report the provider, model, date, and cost inputs.
