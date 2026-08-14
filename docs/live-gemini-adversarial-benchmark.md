# Live Gemini Held-Out Adversarial Benchmark

Latest measured rerun: `2026-08-14T07:23:58Z`

## Baseline Before Compact Planner Contract

The first full live run used Gemini planning with the older direct `WorkflowPlanDraft` output
contract.

Generated: `2026-08-13T22:22:15Z`

Command:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:GEMINI_MODEL="gemini-3.5-flash"
$env:EMBEDDING_PROVIDER="hashing"
$env:TOOL_DISCOVERY_INDEX_BACKEND="memory"
$env:KNOWLEDGE_INDEX_BACKEND="memory"
python -m evaluation.run --config semantic_rag_graph --mode real --dataset heldout_adversarial --limit 50
```

Dataset: `evaluation/datasets/heldout_adversarial_engineering_tasks.json`

Provider provenance:

- Planner provider: `gemini`
- Planner model: `llm-workflow-planner:gemini-3.5-flash`
- Embedding provider: `hashing`
- Retrieval backend: `in-memory-hashing`
- Embedding fallback allowed: `false`

Results:

| Metric | Value |
| --- | ---: |
| Cases | 50 |
| Tool recall | 0.1867 |
| Tool precision | 0.9743 |
| Exact tool-set accuracy | 0.1200 |
| Workflow validity rate | 0.1000 |
| Workflow completion rate | 0.1000 |
| Hallucinated tool rate | 0.2778 |
| Unnecessary tool-call rate | 0.1667 |
| Policy violation attempt rate | 0.0000 |
| Approval classification accuracy | 0.8600 |
| RAG Recall@K | 0.0600 |
| RAG MRR | 0.0000 |
| Average workflow length | 0.36 |
| Execution success rate | 0.1000 |
| Average planner latency | 6071.1077 ms |
| Average end-to-end latency | 6071.1103 ms |
| Estimated model cost | 0.002146 USD |

Failure distribution:

- Valid cases: 5 / 50
- `PlannerOutputError`: 45 / 50

Important caveat: Gemini embeddings were attempted separately and returned HTTP `429`, so this
completed live run uses Gemini for planning and deterministic hashing for retrieval. The low
workflow-validity rate is retained as a failure-analysis signal rather than hidden or re-labeled as
a successful production benchmark.

## Intervention

The planner was changed to use a compact live model contract:

- `PLAN`
- `CLARIFY`
- `REFUSE`

Gemini now proposes only decision, confidence, reason, missing context, tool names, arguments,
dependencies, and typed conditions. Trusted backend code supplies MCP server metadata, risk,
approval requirements, retry policy, timeout, compensation, and DAG edges.

Two prompt semantics were tightened before rerunning:

- `CLARIFY` is used only when required context cannot be inferred from the request, retrieved
  knowledge, allowed tool schemas, or configured current repository.
- High-risk governed actions should still be planned when an allowed MCP tool exists; backend policy
  decides whether approval is required or the action is denied.

Provider HTTP failures are no longer retried immediately. Correction retry is reserved for JSON
parsing and schema-validation failures, so rate-limit responses are recorded once instead of being
amplified.

## Smoke Rerun

Command:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:GEMINI_MODEL="gemini-3.5-flash-lite"
$env:EMBEDDING_PROVIDER="hashing"
$env:TOOL_DISCOVERY_INDEX_BACKEND="memory"
$env:KNOWLEDGE_INDEX_BACKEND="memory"
python -m evaluation.run --config semantic_rag_graph --mode real --dataset heldout_adversarial --limit 5
```

Measured result:

| Metric | Value |
| --- | ---: |
| Cases | 5 |
| Workflow validity rate | 1.0000 |
| Tool recall | 0.5000 |
| Tool precision | 0.6667 |
| Hallucinated tool rate | 0.3333 |
| Approval classification accuracy | 0.6000 |
| Provider/planner-output failures | 0 |

## Full 50-Case Rerun

Command:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:GEMINI_MODEL="gemini-3.5-flash-lite"
$env:EMBEDDING_PROVIDER="hashing"
$env:TOOL_DISCOVERY_INDEX_BACKEND="memory"
$env:KNOWLEDGE_INDEX_BACKEND="memory"
python -m evaluation.run --config semantic_rag_graph --mode real --dataset heldout_adversarial --limit 50
```

Provider provenance:

- Planner provider: `gemini`
- Planner model: `llm-workflow-planner:gemini-3.5-flash-lite`
- Embedding provider: `hashing`
- Retrieval backend: `in-memory-hashing`

Measured result:

| Metric | Value |
| --- | ---: |
| Cases | 50 |
| Tool recall | 0.2383 |
| Tool precision | 0.9033 |
| Exact tool-set accuracy | 0.1400 |
| Workflow validity rate | 0.3400 |
| Workflow completion rate | 0.2800 |
| Hallucinated tool rate | 0.3077 |
| Unnecessary tool-call rate | 0.1154 |
| Policy violation attempt rate | 0.0200 |
| Approval classification accuracy | 0.8200 |
| RAG Recall@K | 0.1000 |
| RAG MRR | 0.0300 |
| Average workflow length | 0.52 |
| Execution success rate | 0.2800 |
| Average planner latency | 1023.9570 ms |
| Average end-to-end latency | 1023.9589 ms |
| Estimated model cost | 0.002530 USD |

Failure distribution:

- Provider HTTP `429`: 33 / 50
- Planner-output/schema failures: 0 / 50
- Immediate provider retries: 0

Interpretation: the original `45/50 PlannerOutputError` problem is no longer reproduced after the
compact planner contract. The full-run validity number is currently dominated by Gemini provider
quota/rate-limit failures, not malformed planner output. A higher-quota rerun is required before
claiming final live model reliability.
