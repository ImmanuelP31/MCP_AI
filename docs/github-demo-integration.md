# GitHub Demo Integration

## Purpose

The platform can investigate a real GitHub repository through governed MCP tools. The LLM/planner does not call GitHub directly. GitHub access is routed through the MCP gateway, RBAC, policy, approval, idempotency, and audit.

Configured platform repository:

```text
ImmanuelP31/MCP_AI
```

Dedicated external demo target:

```text
ImmanuelP31/mcp-ai-demo-target
```

## Environment

Create a fine-grained GitHub token scoped only to the demo repository. Put it in `.env`; do not paste it into chat and do not commit it.

```env
GITHUB_TOKEN=replace-with-fine-grained-github-token
GITHUB_OWNER=ImmanuelP31
GITHUB_REPO=MCP_AI
GITHUB_DEFAULT_BRANCH=main
GITHUB_ALLOWED_REPOSITORIES=ImmanuelP31/MCP_AI,ImmanuelP31/mcp-ai-demo-target
GITHUB_API_BASE_URL=https://api.github.com
```

Recommended token permissions:

- Metadata: read
- Contents: read
- Actions: read
- Issues: write
- Pull requests: read
- Actions: write, only if you want approval-gated workflow reruns

## Implemented MCP Tools

Live-backed when `GITHUB_TOKEN` is configured; otherwise they return explicit offline demo data for local tests.

| Tool | Risk | Approval | Purpose |
| --- | --- | --- | --- |
| `get_latest_failed_build` | READ_ONLY | no | Find latest failed GitHub Actions run |
| `get_build_status` | READ_ONLY | no | Existing planner alias for failed-build status |
| `get_workflow_runs` | READ_ONLY | no | List GitHub Actions workflow runs |
| `get_workflow_run_jobs` | READ_ONLY | no | List jobs for a workflow run |
| `get_failed_jobs` | READ_ONLY | no | Existing planner alias for failed jobs |
| `get_job_logs` | READ_ONLY | no | Retrieve bounded job logs |
| `get_pipeline_logs` | READ_ONLY | no | Existing planner alias for job logs |
| `get_recent_commits` | READ_ONLY | no | Inspect recent commits |
| `get_commit_history` | READ_ONLY | no | Existing planner alias for commit history |
| `list_recent_commits` | READ_ONLY | no | Existing planner alias for recent commits |
| `get_commit_details` | READ_ONLY | no | Inspect one commit and changed files |
| `get_changed_files` | READ_ONLY | no | Compare changed files |
| `summarize_diff` | READ_ONLY | no | Summarize changed files and classify code/config impact |
| `get_pull_request` | READ_ONLY | no | Retrieve pull request metadata |
| `run_tests` | MEDIUM | no | Run a bounded local mocked pipeline test suite |
| `rerun_build` | MEDIUM | no | Rerun a build through GitHub Actions when configured, mocked locally otherwise |
| `analyze_build_failure` | MEDIUM | no | Classify build failure evidence with deterministic rules |
| `create_issue` | MEDIUM | no | Create a GitHub issue for a governed finding |
| `rerun_workflow` | HIGH | yes | Rerun failed GitHub Actions jobs after approval |

This gives the demo an executable vertical slice:

```text
get_latest_failed_build
-> get_workflow_run_jobs
-> get_job_logs
-> get_recent_commits
-> get_changed_files
-> analyze_build_failure
-> create_issue
-> rerun_workflow, approval-gated
```

`run_tests`, `summarize_diff`, and `analyze_build_failure` are bounded local mocked pipeline tools
for reproducible demos and tests. The GitHub read/write tools use live GitHub when
`GITHUB_TOKEN` is configured.

## Live LLM And Embedding Mode

Keep deterministic defaults for tests:

```env
LLM_PLANNER_PROVIDER=deterministic
EMBEDDING_PROVIDER=hashing
TOOL_DISCOVERY_INDEX_BACKEND=memory
KNOWLEDGE_INDEX_BACKEND=memory
```

For a live AI demo, set:

```env
GEMINI_API_KEY=your-valid-gemini-key
GEMINI_MODEL=gemini-3.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
LLM_PROVIDER=gemini
LLM_PLANNER_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
TOOL_DISCOVERY_INDEX_BACKEND=opensearch
KNOWLEDGE_INDEX_BACKEND=opensearch
```

The live LLM planner still returns a typed `WorkflowPlanDraft`. Backend validation and policy
remain authoritative. The LLM cannot approve operations, downgrade risk, invent executable tools,
or bypass the MCP gateway.

## Demo Prompt

```text
Check why the latest GitHub build failed and create a GitHub issue if the problem comes from our code. Ask for approval before rerunning the workflow.
```

Expected flow:

1. Semantic tool discovery retrieves GitHub CI/CD and repository tools.
2. Workflow planner builds a typed DAG.
3. `get_build_status`, `get_pipeline_logs`, and `get_recent_commits` use GitHub-backed schemas.
4. `create_issue` is selected when the user asks for a GitHub issue.
5. `rerun_workflow` is classified as HIGH risk and returns pending approval.
6. Admin approval is required before execution.
7. Audit records include repository/run/job target resources.

## Controlled Failed Build

For a clean interview/demo failure, use the dedicated target repository:

```text
https://github.com/ImmanuelP31/mcp-ai-demo-target
```

It contains:

```text
.github/workflows/demo-failing-build.yml
docs/deployment.md
src/payments/validation.py
```

The workflow is manual-only. Trigger a fresh failure:

```powershell
$env:GITHUB_ALLOWED_REPOSITORIES="ImmanuelP31/MCP_AI,ImmanuelP31/mcp-ai-demo-target"
python scripts/demo/run_live_github_control_plane_demo.py `
  --repository ImmanuelP31/mcp-ai-demo-target `
  --trigger-failure `
  --wait-seconds 90
```

Then run the governed investigation:

```powershell
python scripts/demo/run_live_github_control_plane_demo.py `
  --repository ImmanuelP31/mcp-ai-demo-target `
  --create-issue `
  --request-rerun `
  --approve-rerun
```

The script calls GitHub through governed MCP gateway tools and prints a compact JSON trace for
presentation.

Full runbook: `docs/final-live-demo-runbook.md`.

## Local Verification

```bash
python -m pytest tests/unit/test_github_mcp.py tests/contract/test_mcp_tools.py -q
python -m pytest tests/unit/test_workflow_planning.py tests/unit/test_tool_discovery.py -q
```

The normal test suite uses deterministic offline GitHub data. Live GitHub calls require `GITHUB_TOKEN`.

Live smoke commands:

```powershell
$env:LLM_PLANNER_PROVIDER="gemini"
$env:EMBEDDING_PROVIDER="gemini"
$env:GEMINI_EMBEDDING_MODEL="gemini-embedding-001"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 3
```

If Gemini returns HTTP 401/403, rotate or replace `GEMINI_API_KEY`. If Gemini returns quota or
rate-limit errors, reduce the benchmark limit or add quota before running live benchmarks. If GitHub
has no failed workflow run, the live GitHub smoke will correctly report no latest failed build.
