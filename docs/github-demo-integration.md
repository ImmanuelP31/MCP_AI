# GitHub Demo Integration

## Purpose

The platform can investigate a real GitHub repository through governed MCP tools. The LLM/planner does not call GitHub directly. GitHub access is routed through the MCP gateway, RBAC, policy, approval, idempotency, and audit.

Configured target for this repository:

```text
ImmanuelP31/MCP_AI
```

## Environment

Create a fine-grained GitHub token scoped only to the demo repository. Put it in `.env`; do not paste it into chat and do not commit it.

```env
GITHUB_TOKEN=github_pat_xxx
GITHUB_OWNER=ImmanuelP31
GITHUB_REPO=MCP_AI
GITHUB_DEFAULT_BRANCH=main
GITHUB_ALLOWED_REPOSITORIES=ImmanuelP31/MCP_AI
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
| `create_issue` | MEDIUM | no | Create a GitHub issue for a governed finding |
| `rerun_workflow` | HIGH | yes | Rerun failed GitHub Actions jobs after approval |

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

## Local Verification

```bash
python -m pytest tests/unit/test_github_mcp.py tests/contract/test_mcp_tools.py -q
python -m pytest tests/unit/test_workflow_planning.py tests/unit/test_tool_discovery.py -q
```

The normal test suite uses deterministic offline GitHub data. Live GitHub calls require `GITHUB_TOKEN`.
