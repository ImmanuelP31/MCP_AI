# Final Live Demo Runbook

This runbook demonstrates the strongest vertical slice of the MCP Engineering Operations Platform:

```text
natural-language engineering request
-> semantic MCP tool discovery
-> engineering RAG over repo docs
-> typed workflow DAG
-> capability/policy checks
-> MCP gateway execution
-> human approval for high-risk rerun
-> audit/metrics
```

The goal is not to claim a fully autonomous production agent. The goal is to prove the control-plane
architecture against one real engineering system of record: GitHub.

## Preflight

Keep secrets in `.env`; never commit them.

```env
GITHUB_TOKEN=replace-with-fine-grained-github-token
GITHUB_OWNER=ImmanuelP31
GITHUB_REPO=MCP_AI
GITHUB_ALLOWED_REPOSITORIES=ImmanuelP31/MCP_AI,ImmanuelP31/mcp-ai-demo-target

GEMINI_API_KEY=replace-with-valid-gemini-key
GEMINI_MODEL=gemini-2.5-flash
LLM_PLANNER_PROVIDER=gemini
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_EMBEDDING_MODEL=gemini-embedding-001

# Alternative live planner provider.
OPENROUTER_API_KEY=replace-with-valid-openrouter-key
OPENROUTER_MODEL=openrouter/auto
```

Recommended GitHub token permissions:

- Metadata: read
- Contents: read
- Actions: read
- Issues: write
- Pull requests: read
- Actions: write, only for approval-gated reruns

Check repository-document RAG ingestion:

```powershell
python scripts/ingest_repo_docs.py --query "GitHub controlled failing build approval" --top-k 3
```

Expected: the top results include:

```text
local-repository:.github/workflows/demo-failing-build.yml
local-repository:docs/github-demo-integration.md
```

## Create A Controlled Failed Build

The workflow file is:

```text
.github/workflows/demo-failing-build.yml
```

For the clean external target repository, trigger it:

```powershell
$env:GITHUB_ALLOWED_REPOSITORIES="ImmanuelP31/MCP_AI,ImmanuelP31/mcp-ai-demo-target"
python scripts/demo/run_live_github_control_plane_demo.py `
  --repository ImmanuelP31/mcp-ai-demo-target `
  --trigger-failure `
  --wait-seconds 90
```

If the workflow is not on GitHub yet, GitHub will return a workflow-not-found error. Push the
branch first, then rerun.

## Run The Governed GitHub Demo

Read-only investigation:

```powershell
python scripts/demo/run_live_github_control_plane_demo.py
```

Full governed workflow:

```powershell
python scripts/demo/run_live_github_control_plane_demo.py `
  --repository ImmanuelP31/mcp-ai-demo-target `
  --create-issue `
  --request-rerun `
  --approve-rerun
```

What to show:

- `get_latest_failed_build` reads the failed GitHub Actions run.
- `get_workflow_run_jobs` reads failed jobs.
- `get_job_logs` retrieves bounded log evidence.
- `get_recent_commits` and `get_changed_files` inspect repository changes.
- `analyze_build_failure` produces deterministic evidence classification.
- `create_issue` opens a GitHub issue only when requested.
- `rerun_workflow` becomes `PENDING_APPROVAL`.
- `ADMIN` approval is required before rerun execution.

## Live LLM / Embedding Benchmark

With a valid Gemini key for live workflow planning:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:GEMINI_MODEL="gemini-2.5-flash"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 10
```

OpenRouter remains available by setting `LLM_PLANNER_PROVIDER=openrouter`.

For live embedding retrieval, use Gemini embeddings:

```powershell
$env:EMBEDDING_PROVIDER="gemini"
$env:GEMINI_EMBEDDING_MODEL="gemini-embedding-001"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 10
```

Use a small limit first. Then increase to 30-50 for a presentable live benchmark.

Provider HTTP 401, 429, or quota errors are infrastructure/authentication failures. Do not report
those runs as model quality.

## Interview Script

Say:

> This is a governed AI engineering control plane. The LLM proposes a workflow, but policy,
> RBAC, typed schema validation, approval binding, and the MCP gateway decide what can execute.

Then show:

1. Tool discovery returns GitHub/CI tools, not the whole tool catalog.
2. RAG cites repository docs and the controlled failing workflow.
3. The workflow DAG separates planning from execution.
4. High-risk rerun is approval-gated.
5. Audit/metrics show what happened.

## Current Verified Status

- Backend tests: 382 passed.
- Frontend tests/lint/typecheck/build: 9 tests passed, lint/typecheck/build passed.
- Python lint/type/security: ruff passed, mypy passed on 154 source files, Bandit found no issues.
- Docker Compose config: parsed successfully; local Docker config access emitted a sandbox warning.
- GitHub vertical-slice demo: live validated against dedicated target
  `ImmanuelP31/mcp-ai-demo-target`; issue
  `https://github.com/ImmanuelP31/mcp-ai-demo-target/issues/1` was created and an approval-gated
  workflow rerun executed.
- Repository-document RAG: 34 bounded repo docs/workflows ingested; controlled failing workflow was
  the top retrieved result for the demo query.
- OpenSearch RAG: live validated with `index_backend: opensearch` using
  `OPENSEARCH_URL=http://localhost:9200`.
- Controlled failing workflow: pushed to `main` and dispatched successfully.
- Live planner and embedding support: Gemini is the recommended provider for the current demo path.
  OpenRouter remains available as an alternate planner provider; deterministic hashing remains the
  CI fallback for embeddings.
- Evaluation: mock baseline is generated and clearly labeled.
