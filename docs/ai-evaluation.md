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

The 330-case dataset is generated from fixed categories and should be treated as a deterministic
regression suite. For stronger model-quality evidence, the repository also includes
`evaluation/datasets/heldout_adversarial_engineering_tasks.json`, a 50-case held-out set with
independently phrased requests, prompt-injection attempts, ambiguous environments, impossible
requests, distracting tools, policy conflicts, missing information, and multi-intent workflows.

## Configurations

- `all_tools`
- `semantic`
- `semantic_rag`
- `semantic_rag_graph`

## Metrics

Tracked metrics include tool recall, tool precision, exact tool-set accuracy, workflow validity, plan acceptance, benchmark-unexpected tool rate, unknown/disallowed tool-call rate, cases with unknown tools, unnecessary tool calls, policy violation attempts, approval classification accuracy, RAG Recall@K, RAG MRR, workflow length, execution success when execution is actually run, latency, token usage, and estimated cost when available.

## Latest Measured Mock Baseline

| Configuration | Cases | Tool Recall | Tool Precision | Workflow Validity | Unknown/Disallowed Tool Rate | RAG Recall@K | Plan Acceptance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_tools | 330 | 0.5379 | 0.8409 | 0.6545 | 0.2226 | 0.0000 | 0.5455 |
| semantic | 330 | 0.5015 | 0.8477 | 0.7455 | 0.2016 | 0.0000 | 0.6364 |
| semantic_rag | 330 | 0.5879 | 0.8433 | 0.7455 | 0.2013 | 0.6955 | 0.6364 |
| semantic_rag_graph | 330 | 0.5879 | 0.8433 | 0.7455 | 0.2013 | 0.6955 | 0.6364 |

These are mock-mode baseline results retained for comparison, not live LLM claims. The tracked
`evaluation/results/latest.json` file reflects the most recent evaluation run and may be either mock
or live depending on the last command executed.

## Live Provider Status

The live planner path is implemented behind the same typed workflow schema used by deterministic
mode. Live LLMs now return a compact `PlannerDecision` proposal (`PLAN`, `CLARIFY`, or `REFUSE`)
that trusted backend code compiles into the full workflow DAG. This keeps registry metadata,
risk, approval requirements, edges, retry policy, and execution settings outside model authority.

The recommended live provider is Gemini, with OpenRouter available for planner-only comparison.
The Gemini planner request includes a JSON response schema for the compact planner decision. The
embedding-provider path supports Gemini embeddings for live retrieval benchmarks and deterministic
hashing for CI.

Evaluation records planner failure taxonomy fields including `failure_category`, `error_stage`,
`error_type`, `error_reason`, `attempts`, `finish_reason`, `retry_attempted`, and
`retry_failure_reason`. This separates provider failures, planner-output failures, workflow
validation failures, execution failures, malformed JSON, schema validation, provider HTTP errors,
invalid arguments, unknown/disallowed tools, and no-action decisions.

Do not present provider-authentication or quota failures as model behavior. Provider-quality metrics
are computed over provider-successful cases only; end-to-end metrics include provider availability.
For a Gemini planner smoke, rerun:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:GEMINI_MODEL="gemini-3.5-flash"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 3
```

## Run

```bash
python -m evaluation.run --config semantic_rag_graph
```

Live provider smoke:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:GEMINI_MODEL="gemini-3.5-flash"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 3
```

OpenRouter planner smoke:

```powershell
$env:LLM_PLANNER_PROVIDER="openrouter"
$env:OPENROUTER_MODEL="openrouter/auto"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 3
```

Gemini planner and embedding comparison:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:EMBEDDING_PROVIDER="gemini"
$env:GEMINI_EMBEDDING_MODEL="gemini-embedding-001"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 3
```

In `--mode real`, embedding-provider failure must fail closed. Product runtime may fall back to
hashing for resilience, but benchmark runs should not silently report hashing results as Gemini
embedding results.

Outputs:

- `evaluation/results/latest.json`
- `evaluation/results/latest.csv`
- `evaluation/reports/latest.md`

For a real benchmark, configure a valid provider key, run the same dataset/configuration used for
mock mode, and label/report the provider, model, date, latency, token usage, and estimated cost.
Provider errors such as HTTP 401 or quota/rate-limit responses are
infrastructure/authentication failures and should not be presented as LLM quality metrics.

## Latest Live Held-Out Measurement

The latest 50-case held-out adversarial run was generated at `2026-08-18T10:42:30Z` with Gemini
planning, hashing retrieval, and the `semantic_rag_graph` configuration. Hashing retrieval was used
to isolate planner behavior while avoiding embedding-provider quota limits.

| Metric | Value |
| --- | ---: |
| Cases attempted | 50 |
| Provider-successful cases | 34 |
| Provider success rate | 0.6800 |
| Provider-success workflow validity | 0.9118 |
| Provider-success plan acceptance | 0.8235 |
| End-to-end workflow validity | 0.6200 |
| End-to-end plan acceptance | 0.5600 |
| Tool recall | 0.3358 |
| Tool precision | 0.3309 |
| Benchmark-unexpected tool rate | 0.5283 |
| Unknown/disallowed tool-call rate | 0.0000 |
| Cases with unknown/disallowed tools | 0.0000 |
| Approval classification accuracy | 0.9118 |
| RAG Recall@K | 0.2059 |
| Provider HTTP 429 failures | 16 |
| Other provider failures | 0 |
| Planner-output/schema failures | 0 |
| Workflow-validation failures | 3 |

The earlier `45 / 50 PlannerOutputError` failure mode is no longer reproduced. Remaining work is
semantic quality and provider availability rather than planner-output contract validity.
This benchmark did not execute MCP tools, so `execution_success_rate` is intentionally `0.0000`.

## Verified Live Integration Status

- GitHub API smoke was verified against `ImmanuelP31/MCP_AI`; the token was configured and the
  latest-failed-build query returned no current failed run.
- Repository-document RAG ingestion loaded 34 bounded local documentation/workflow files; the
  controlled failing GitHub Actions workflow was the top result for the demo query.
- OpenSearch-backed RAG was live validated with `index_backend: opensearch` using
  `OPENSEARCH_URL=http://localhost:9200`.
- Gemini is the recommended live provider for both planner and embeddings.
