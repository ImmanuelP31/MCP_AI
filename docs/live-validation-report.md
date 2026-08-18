# Live Validation Report

Generated during the final presentation-readiness pass.

## Summary

| Area | Status | Evidence |
| --- | --- | --- |
| GitHub token | Configured | `.env` contains a GitHub token; token value was not printed. |
| GitHub demo target repo | Live validated | `https://github.com/ImmanuelP31/mcp-ai-demo-target` was created for clean demos. |
| GitHub read smoke | Live validated | `get_latest_failed_build` reached the demo target and returned the controlled failed run. |
| Controlled failing workflow | Live validated | `.github/workflows/demo-failing-build.yml` dispatched on the demo target `main` branch. |
| GitHub vertical-slice demo | Live validated | Failed build investigation, issue creation, approval-gated rerun request, approval, and rerun execution succeeded against the demo target. |
| Repository-document RAG | Live validated | 34 bounded repository docs/workflows ingested. |
| OpenSearch RAG backend | Live validated | Query returned `index_backend: opensearch` with the controlled failing workflow as top result. |
| Gemini planner | Live validated | `LLM_PLANNER_PROVIDER=gemini` now uses a compact `PLAN`/`CLARIFY`/`REFUSE` contract compiled by trusted backend code. |
| Gemini embeddings | Implemented | `EMBEDDING_PROVIDER=gemini` uses Gemini embeddings for tool discovery and engineering RAG. |
| 30-50 live LLM benchmark | Rerun with caveat | 50-case rerun reached 34/50 provider-successful responses, 31/34 structurally valid workflows, and 0 unknown/disallowed tool calls; 16 cases were Gemini HTTP 429 provider failures. |
| Hashing vs real embedding comparison | Ready to rerun | Hashing baseline is available; Gemini embedding mode is now the live provider path. |

## OpenSearch RAG Evidence

Command:

```powershell
$env:KNOWLEDGE_INDEX_BACKEND="opensearch"
$env:EMBEDDING_PROVIDER="hashing"
$env:OPENSEARCH_URL="http://localhost:9200"
python scripts/ingest_repo_docs.py --query "GitHub controlled failing build approval" --top-k 5
```

Measured output summary:

- Documents ingested: 34
- Index backend: `opensearch`
- Top citation: `REPO-GITHUB-WORKFLOWS-DEMO-FAILING-BUILD-YML`
- Top source: `local-repository:.github/workflows/demo-failing-build.yml`
- Top score: `1.0`

## GitHub Vertical-Slice Evidence

Live governed demo command:

```powershell
$env:GITHUB_ALLOWED_REPOSITORIES="ImmanuelP31/MCP_AI,ImmanuelP31/mcp-ai-demo-target"
python scripts/demo/run_live_github_control_plane_demo.py `
  --repository ImmanuelP31/mcp-ai-demo-target `
  --create-issue `
  --request-rerun `
  --approve-rerun
```

Measured output summary:

- Repository: `ImmanuelP31/mcp-ai-demo-target`
- Failed workflow run: `31581559101`
- Workflow name: `Demo Failing Build`
- Failed commit: `cc1a5287ef16f0a01c7129a53ba219224f0c1de4`
- Tool decisions before high-risk action: `ALLOWED`
- Failure analysis source: `source_code_failure`
- Failure analysis confidence: `0.78`
- Code files changed: `1`
- GitHub issue created: `https://github.com/ImmanuelP31/mcp-ai-demo-target/issues/1`
- High-risk rerun request decision: `PENDING_APPROVAL`
- Human approval decision: `ALLOWED`
- Rerun execution decision: `ALLOWED`

## Historical OpenAI Failure Analysis

The first 401 failure was caused by a stale machine-level `OPENAI_API_KEY` overriding the project
`.env` key. Project settings now load `.env` before inherited environment variables, and the
effective settings key matches the `.env` key.

After that fix, the OpenAI planner and embedding endpoints returned HTTP 429:

- Planner endpoint: HTTP 429, `credit_balance_exhausted`
- Embeddings endpoint: HTTP 429, `credit_balance_exhausted`

The provider message was: no credits remaining. This is a billing/quota condition, not an
invalid-key authentication failure. The benchmark runner correctly records provider failures
instead of fabricating successful model metrics.

## Latest Gemini Held-Out Benchmark

The compact planner contract and prompt semantics were rerun against the held-out adversarial set
with Gemini planning and hashing retrieval to isolate planner behavior from embedding quota.

Smoke command:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:GEMINI_MODEL="gemini-3.5-flash-lite"
$env:EMBEDDING_PROVIDER="hashing"
python -m evaluation.run --config semantic_rag_graph --mode real --dataset heldout_adversarial --limit 5
```

Smoke result:

- Cases: `5`
- Workflow validity: `1.0000`
- Planner-output/schema failures: `0`

Full-run command:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:GEMINI_MODEL="gemini-3.5-flash-lite"
$env:EMBEDDING_PROVIDER="hashing"
python -m evaluation.run --config semantic_rag_graph --mode real --dataset heldout_adversarial --limit 50
```

Full-run result:

- Cases: `50`
- Provider-successful cases: `34 / 50`
- Provider success rate: `0.6800`
- Quality workflow validity: `0.9118`
- Provider-success plan acceptance: `0.8235`
- End-to-end workflow validity: `0.6200`
- End-to-end plan acceptance: `0.5600`
- Tool recall: `0.3358`
- Tool precision: `0.3309`
- Benchmark-unexpected tool rate: `0.5283`
- Unknown/disallowed tool-call rate: `0.0000`
- Approval classification accuracy: `0.9118`
- RAG Recall@K: `0.2059`
- Provider HTTP `429`: `16 / 50`
- Planner-output/schema failures: `0 / 50`
- Workflow-validation failures: `3 / 50`

Interpretation: the earlier `45 / 50 PlannerOutputError` failure mode is no longer reproduced. On
provider-successful cases, the compact contract now mostly produces structurally valid workflows
and plan-accepted workflows. The benchmark does not execute MCP tools, so execution success remains
separate from plan acceptance. The remaining live benchmark gap is provider availability plus
semantic quality, especially tool recall, benchmark-unexpected tool selection, and RAG recall.

## Optional Rerun With Gemini Embeddings

After setting a valid Gemini key and approving external provider use:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:EMBEDDING_PROVIDER="gemini"
$env:GEMINI_EMBEDDING_MODEL="gemini-embedding-001"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 30
```

For the retrieval comparison:

```powershell
$env:EMBEDDING_PROVIDER="hashing"
python -m evaluation.run --config semantic_rag_graph --mode mock --limit 50

$env:EMBEDDING_PROVIDER="gemini"
$env:GEMINI_EMBEDDING_MODEL="gemini-embedding-001"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 50
```

Report both successful and failed cases. Do not compare mock hashing results directly against live
LLM results without labeling the different execution modes.
