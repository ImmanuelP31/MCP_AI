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
| all_tools | 330 | 0.5379 | 0.8409 | 0.6545 | 0.2226 | 0.0000 | 0.5455 |
| semantic | 330 | 0.5015 | 0.8477 | 0.7455 | 0.2016 | 0.0000 | 0.6364 |
| semantic_rag | 330 | 0.5879 | 0.8433 | 0.7455 | 0.2013 | 0.6955 | 0.6364 |
| semantic_rag_graph | 330 | 0.5879 | 0.8433 | 0.7455 | 0.2013 | 0.6955 | 0.6364 |

These are mock-mode results from `evaluation/results/latest.json`, not live LLM claims.

## Live Provider Status

The live planner and embedding-provider paths are implemented behind the same typed workflow and
retrieval abstractions used by deterministic mode. In this environment, an explicit OpenAI smoke
attempt reached the provider but returned HTTP 401, so no live LLM quality result is recorded.

Do not present provider-authentication failures as model behavior. After replacing the key, rerun:

```powershell
$env:LLM_PLANNER_PROVIDER="openai"
$env:EMBEDDING_PROVIDER="openai"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 3
```

## Run

```bash
python -m evaluation.run --config semantic_rag_graph
```

Live provider smoke:

```powershell
$env:LLM_PLANNER_PROVIDER="openai"
$env:EMBEDDING_PROVIDER="openai"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 3
```

Outputs:

- `evaluation/results/latest.json`
- `evaluation/results/latest.csv`
- `evaluation/reports/latest.md`

For a real benchmark, configure a valid provider key, run the same dataset/configuration used for
mock mode, and label/report the provider, model, date, latency, token usage, and estimated cost.
Provider errors such as HTTP 401 are infrastructure/authentication failures and should not be
presented as LLM quality metrics.

## Verified Live Integration Status

- GitHub API smoke was verified against `ImmanuelP31/MCP_AI`; the token was configured and the
  latest-failed-build query returned no current failed run.
- Repository-document RAG ingestion loaded 34 bounded local documentation/workflow files; the
  controlled failing GitHub Actions workflow was the top result for the demo query.
- OpenSearch-backed RAG was live validated with `index_backend: opensearch` using
  `OPENSEARCH_URL=http://localhost:9200`.
- OpenAI real-mode planner/evaluation and embedding smoke reached the provider. The stale
  machine-level key override was fixed, and the provider then returned HTTP 429. Add quota or use a
  key with available quota before presenting live LLM or embedding benchmark numbers.
