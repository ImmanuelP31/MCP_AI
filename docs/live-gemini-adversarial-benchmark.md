# Live Gemini Held-Out Adversarial Benchmark

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
