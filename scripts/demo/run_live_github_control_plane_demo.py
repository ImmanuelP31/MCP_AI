from __future__ import annotations

import argparse
import json
import time
from typing import Any
from uuid import UUID

from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest
from mcp_ops_mcp_gateway.service import McpGateway
from mcp_ops_repository_mcp.service import GitHubRepositoryService

ENGINEER_TOKEN = "engineer-token"  # noqa: S105  # nosec B105
ADMIN_TOKEN = "admin-token"  # noqa: S105  # nosec B105
DEMO_WORKFLOW_FILE = "demo-failing-build.yml"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the live GitHub MCP control-plane demo vertical slice."
    )
    parser.add_argument("--repository", default=None, help="owner/repo; defaults to .env config")
    parser.add_argument("--branch", default=None, help="branch/ref; defaults to .env config")
    parser.add_argument("--trigger-failure", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--create-issue", action="store_true")
    parser.add_argument("--request-rerun", action="store_true")
    parser.add_argument("--approve-rerun", action="store_true")
    args = parser.parse_args()

    github = GitHubRepositoryService()
    repository = github.resolve_repository(args.repository)
    branch = args.branch or github.config.default_branch
    trace: list[dict[str, Any]] = [
        {
            "step": "preflight",
            "repository": repository,
            "branch": branch,
            "github_configured": bool(getattr(github.client, "is_configured", False)),
        }
    ]

    if args.trigger_failure:
        trace.append(_dispatch_controlled_failure(github, repository, branch))
        if args.wait_seconds > 0:
            trace.append(_wait_for_failed_build(github, repository, branch, args.wait_seconds))

    gateway = McpGateway()
    failed_build = _call(
        gateway,
        "get_latest_failed_build",
        {"repository": repository},
        "demo-get-latest-failed-build",
    )
    trace.append(_summary("get_latest_failed_build", failed_build))
    run = (
        failed_build.data.get("tool_result", {})
        .get("data", {})
        .get("latest_failed_build")
    )
    if not isinstance(run, dict) or not run:
        trace.append(
            {
                "step": "stop",
                "reason": (
                    "No failed GitHub Actions run found. Push this branch, dispatch "
                    f"{DEMO_WORKFLOW_FILE}, then rerun with --wait-seconds 90."
                ),
            }
        )
        _print_trace(trace)
        return

    run_id = int(run["id"])
    sha = str(run.get("sha") or "")
    jobs = _call(
        gateway,
        "get_workflow_run_jobs",
        {"repository": repository, "run_id": run_id},
        f"demo-jobs-{run_id}",
    )
    trace.append(_summary("get_workflow_run_jobs", jobs))
    failed_job = _first_failed_job(jobs)
    if failed_job is not None:
        logs = _call(
            gateway,
            "get_job_logs",
            {"repository": repository, "job_id": int(failed_job["id"]), "max_bytes": 12000},
            f"demo-logs-{failed_job['id']}",
        )
        trace.append(_summary("get_job_logs", logs))

    commits = _call(
        gateway,
        "get_recent_commits",
        {"repository": repository, "branch": branch, "limit": 5},
        f"demo-commits-{run_id}",
    )
    trace.append(_summary("get_recent_commits", commits))

    changed_files: list[str] = []
    if sha:
        changed = _call(
            gateway,
            "get_changed_files",
            {"repository": repository, "head": sha},
            f"demo-changed-{sha[:12]}",
        )
        trace.append(_summary("get_changed_files", changed))
        changed_files = [
            str(item.get("filename"))
            for item in changed.data.get("tool_result", {}).get("data", {}).get("files", [])
            if isinstance(item, dict) and item.get("filename")
        ]

    analysis = _call(
        gateway,
        "analyze_build_failure",
        {
            "repository": repository,
            "logs": "Simulated payments-api validation test failure",
            "changed_files": changed_files or ["src/payments/validation.py"],
            "build_conclusion": str(run.get("conclusion") or "failure"),
        },
        f"demo-analysis-{run_id}",
    )
    trace.append(_summary("analyze_build_failure", analysis))
    source = (
        analysis.data.get("tool_result", {})
        .get("data", {})
        .get("analysis", {})
        .get("source")
    )

    if args.create_issue and source == "source_code_failure":
        issue = _call(
            gateway,
            "create_issue",
            {
                "repository": repository,
                "title": "Investigate controlled GitHub Actions failure",
                "body": (
                    "Governed MCP workflow classified the latest failed build as code-related. "
                    f"Run: {run.get('url', '')}"
                ),
                "labels": ["mcp-demo", "automated-investigation"],
            },
            f"demo-create-issue-{run_id}",
        )
        trace.append(_summary("create_issue", issue))

    if args.request_rerun:
        rerun_args = {
            "repository": repository,
            "run_id": run_id,
            "reason": "Approved rerun after governed MCP investigation.",
        }
        pending = _call(gateway, "rerun_workflow", rerun_args, f"demo-rerun-request-{run_id}")
        trace.append(_summary("rerun_workflow.request", pending))
        approval_id = pending.data.get("approval_id")
        if args.approve_rerun and isinstance(approval_id, str):
            approved = gateway.approve_operation(ADMIN_TOKEN, UUID(approval_id))
            trace.append(
                {
                    "step": "approve_rerun",
                    "ok": approved.ok,
                    "decision": approved.decision.value,
                    "approval_id": approval_id,
                }
            )
            executed = gateway.call_tool(
                GatewayToolRequest(
                    auth_token=ENGINEER_TOKEN,
                    tool_name="rerun_workflow",
                    arguments=rerun_args,
                    approval_id=UUID(approval_id),
                    idempotency_key=f"demo-rerun-execute-{run_id}",
                )
            )
            trace.append(_summary("rerun_workflow.execute", executed))

    _print_trace(trace)


def _dispatch_controlled_failure(
    github: GitHubRepositoryService,
    repository: str,
    branch: str,
) -> dict[str, Any]:
    github.client.request(
        "POST",
        f"/repos/{repository}/actions/workflows/{DEMO_WORKFLOW_FILE}/dispatches",
        body={"ref": branch, "inputs": {"fail_demo": "true", "service": "payments-api"}},
    )
    return {
        "step": "dispatch_controlled_failure",
        "workflow": DEMO_WORKFLOW_FILE,
        "repository": repository,
        "branch": branch,
        "status": "requested",
    }


def _wait_for_failed_build(
    github: GitHubRepositoryService,
    repository: str,
    branch: str,
    seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        latest = github.get_latest_failed_build(repository, branch)["data"]["latest_failed_build"]
        if latest:
            return {"step": "wait_for_failed_build", "found": True, "run_id": latest["id"]}
        time.sleep(5)
    return {"step": "wait_for_failed_build", "found": False, "waited_seconds": seconds}


def _call(
    gateway: McpGateway,
    tool_name: str,
    arguments: dict[str, Any],
    idempotency_key: str,
) -> Any:
    return gateway.call_tool(
        GatewayToolRequest(
            auth_token=ENGINEER_TOKEN,
            tool_name=tool_name,
            arguments=arguments,
            idempotency_key=idempotency_key,
        )
    )


def _summary(step: str, response: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "step": step,
        "ok": response.ok,
        "decision": response.decision.value
        if isinstance(response.decision, GatewayDecision)
        else str(response.decision),
    }
    if response.error:
        payload["error"] = response.error
    data = response.data.get("tool_result", {}).get("data", {})
    if isinstance(data, dict):
        payload["data_keys"] = sorted(data)
        if "repository" in data:
            payload["repository"] = data["repository"]
        if "latest_failed_build" in data:
            build = data["latest_failed_build"]
            payload["latest_failed_build"] = (
                None
                if build is None
                else {
                    "id": build.get("id"),
                    "name": build.get("name"),
                    "conclusion": build.get("conclusion"),
                    "sha": build.get("sha"),
                }
            )
        if "analysis" in data:
            payload["analysis"] = data["analysis"]
        if "issue" in data:
            payload["issue"] = data["issue"]
    if "approval_id" in response.data:
        payload["approval_id"] = response.data["approval_id"]
    return payload


def _first_failed_job(response: Any) -> dict[str, Any] | None:
    jobs = response.data.get("tool_result", {}).get("data", {}).get("jobs", [])
    if not isinstance(jobs, list):
        return None
    for job in jobs:
        if isinstance(job, dict) and job.get("conclusion") in {"failure", "timed_out"}:
            return job
    return jobs[0] if jobs and isinstance(jobs[0], dict) else None


def _print_trace(trace: list[dict[str, Any]]) -> None:
    print(json.dumps({"demo": "github_control_plane", "trace": trace}, indent=2))


if __name__ == "__main__":
    main()
