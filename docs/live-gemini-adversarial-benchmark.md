# Live Gemini Held-Out Adversarial Benchmark

Latest measured rerun: `2026-08-18T10:42:30Z`

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

Historical pre-fix results:

| Metric | Value |
| --- | ---: |
| Cases | 50 |
| Tool recall | 0.1867 |
| Tool precision | 0.9743 |
| Exact tool-set accuracy | 0.1200 |
| Workflow validity rate | 0.1000 |
| Plan acceptance / old completion label | 0.1000 |
| Benchmark-unexpected tool rate / old hallucinated label | 0.2778 |
| Unnecessary tool-call rate | 0.1667 |
| Policy violation attempt rate | 0.0000 |
| Approval classification accuracy | 0.8600 |
| RAG Recall@K | 0.0600 |
| RAG MRR | 0.0000 |
| Average workflow length | 0.36 |
| Execution success rate / old plan-acceptance label | 0.1000 |
| Average planner latency | 6071.1077 ms |
| Average end-to-end latency | 6071.1103 ms |
| Estimated model cost | 0.002146 USD |

Failure distribution:

- Valid cases: 5 / 50
- `PlannerOutputError`: 45 / 50

Important caveat: Gemini embeddings were attempted separately and returned HTTP `429`, so this
completed live run uses Gemini for planning and deterministic hashing for retrieval. These numbers
were generated before the evaluator separated plan acceptance from execution success, so they are
retained only as failure-analysis history.

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
| Benchmark-unexpected tool rate | 0.3333 |
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
| Provider-successful cases | 34 |
| Provider success rate | 0.6800 |
| Quality workflow validity rate | 0.9118 |
| End-to-end workflow validity rate | 0.6200 |
| Tool recall | 0.3358 |
| Tool precision | 0.3309 |
| Exact tool-set accuracy | 0.0882 |
| Plan acceptance rate | 0.8235 |
| End-to-end plan acceptance rate | 0.5600 |
| Benchmark-unexpected tool rate | 0.5283 |
| Unknown/disallowed tool-call rate | 0.0000 |
| Cases with unknown/disallowed tools | 0.0000 |
| Unnecessary tool-call rate | 0.1321 |
| Policy violation attempt rate | 0.0294 |
| Approval classification accuracy | 0.9118 |
| RAG Recall@K | 0.2059 |
| RAG MRR | 0.0809 |
| Average workflow length | 1.5588 |
| Execution success rate | 0.0000 |
| End-to-end execution success rate | 0.0000 |
| Average planner latency | 2703.9679 ms |
| Average end-to-end latency | 2703.9717 ms |
| Estimated model cost | 0.003434 USD |

Failure distribution:

- Provider HTTP `429`: 16 / 50
- Planner-output/schema failures: 0 / 50
- Workflow-validation failures: 3 / 50
- Immediate provider retries: 0

Interpretation: the original `45/50 PlannerOutputError` problem is no longer reproduced after the
compact planner contract. Among the 34 provider-successful cases, 31 produced structurally valid
workflows, 28 satisfied the benchmark policy/approval expectations, and no unknown/disallowed tools
reached the final trusted workflow. The benchmark did not execute MCP tools, so plan acceptance is
reported separately from execution success. The remaining end-to-end validity limit is now split
between Gemini provider quota/rate-limit failures and semantic workflow quality, not malformed
planner output.
