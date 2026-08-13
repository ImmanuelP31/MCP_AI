# AI Engineering Workflow Evaluation

The evaluation framework quantitatively measures AI workflow behavior for enterprise engineering automation. It does not make qualitative claims such as "the AI works well" without measured evidence.

## Layout

```text
evaluation/
  datasets/
  scenarios/
  runner/
  metrics/
  reports/
  results/
```

Generated artifacts:

- `evaluation/datasets/engineering_tasks.json`
- `evaluation/results/latest.json`
- `evaluation/results/latest.csv`
- `evaluation/reports/latest.md`

## Dataset

The default synthetic dataset contains 330 deterministic enterprise engineering tasks across:

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

Each item contains expected tools, acceptable tools, prohibited tools, approvals, resources, relevant documents, and expected outcome.

## Configurations

The runner compares:

- `all_tools`: LLM planner with all tools
- `semantic`: LLM planner + semantic tool retrieval
- `semantic_rag`: LLM planner + semantic tool retrieval + engineering RAG
- `semantic_rag_graph`: LLM planner + semantic tools + RAG + capability graph

The default mode is deterministic/mock. In mock mode, token usage is `0` and model cost is `null` because no live LLM is called.

## Metrics

- Tool Recall
- Tool Precision
- Exact Tool Set Accuracy
- Workflow Validity Rate
- Workflow Completion Rate
- Hallucinated Tool Rate
- Unnecessary Tool Call Rate
- Policy Violation Attempt Rate
- Approval Classification Accuracy
- RAG Recall@K
- RAG MRR
- Average Workflow Length
- Execution Success Rate
- Planner Latency
- End-to-End Latency
- Token Usage
- Estimated model cost, when available

## Run Deterministic Evaluation

```bash
python -m evaluation.run --config all
```

Run one configuration:

```bash
python -m evaluation.run --config semantic_rag_graph
```

Run a smoke subset:

```bash
python -m evaluation.run --config semantic_rag_graph --limit 25
```

## Run A Real Benchmark

Configure a real LLM provider through the project settings first, then run:

```bash
python -m evaluation.run --config all --mode real
```

Real mode labels the output as provider-backed. The current deterministic planner remains the default CI path so normal tests do not require API keys or incur model cost. If model pricing is configured later, token and cost reporting should be wired to the provider abstraction and preserved in the same result schema.

In real mode, planner and embedding providers fail closed. If `LLM_PLANNER_PROVIDER=gemini` or
`EMBEDDING_PROVIDER=gemini` is requested without a valid key, the run records a configuration
failure instead of silently measuring deterministic fallback behavior. Each case result includes
`planner_provider`, `planner_model`, `embedding_provider`, `embedding_fallback_allowed`, and
`retrieval_backend` so benchmark artifacts show what was actually exercised.

## Prometheus

The runner records summary metrics through:

- `ai_workflow_evaluation_runs_total`
- `ai_workflow_evaluation_score`

## Frontend

The React console exposes an Evaluation page backed by:

```http
GET /api/v1/evaluation/latest
```

The page shows workflow validity, hallucination rate, tool-selection metrics, retrieval metrics, policy violation metrics, approval accuracy, and latency from the latest generated benchmark file.
