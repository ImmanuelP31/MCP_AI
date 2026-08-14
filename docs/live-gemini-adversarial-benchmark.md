# Live Gemini Held-Out Adversarial Benchmark

Latest measured rerun: `2026-08-14T08:21:08Z`

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
| Provider-successful cases | 30 |
| Provider success rate | 0.6000 |
| Quality workflow validity rate | 0.9000 |
| End-to-end workflow validity rate | 0.5400 |
| Tool recall | 0.3556 |
| Tool precision | 0.6906 |
| Exact tool-set accuracy | 0.1000 |
| Workflow completion rate | 0.8000 |
| Benchmark-unexpected tool rate | 0.4694 |
| Unknown/disallowed tool-call rate | 0.0000 |
| Cases with unknown/disallowed tools | 0.0000 |
| Unnecessary tool-call rate | 0.1633 |
| Policy violation attempt rate | 0.0333 |
| Approval classification accuracy | 0.8333 |
| RAG Recall@K | 0.2111 |
| RAG MRR | 0.0944 |
| Average workflow length | 1.6333 |
| Execution success rate | 0.8000 |
| End-to-end execution success rate | 0.4800 |
| Average planner latency | 2470.9945 ms |
| Average end-to-end latency | 2470.9986 ms |
| Estimated model cost | 0.003130 USD |

Failure distribution:

- Provider HTTP `429`: 20 / 50
- Planner-output/schema failures: 0 / 50
- Workflow-validation failures: 3 / 50
- Immediate provider retries: 0

Interpretation: the original `45/50 PlannerOutputError` problem is no longer reproduced after the
compact planner contract. Among the 30 provider-successful cases, 27 produced structurally valid
workflows and no unknown/disallowed tools reached the final trusted workflow. The remaining
end-to-end validity limit is now split between Gemini provider quota/rate-limit failures and
semantic workflow quality, not malformed planner output.
