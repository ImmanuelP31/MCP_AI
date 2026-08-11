from __future__ import annotations

from typing import Any

from mcp_ops_common.config import Settings, get_settings
from mcp_ops_mcp.errors import PermissionDenied

from mcp_ops_repository_mcp.github import GitHubClient, GitHubConfig, OfflineGitHubClient


class GitHubRepositoryService:
    def __init__(self, client: Any | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.config = GitHubConfig.from_settings(self.settings)
        if client is not None:
            self.client = client
        elif self.config.token:
            self.client = GitHubClient(self.config)
        else:
            self.client = OfflineGitHubClient(self.config.default_repository)

    def resolve_repository(self, repository: str | None = None) -> str:
        return self._repository(repository)

    def get_recent_commits(
        self,
        repository: str | None,
        branch: str | None,
        limit: int,
    ) -> dict[str, Any]:
        repo = self._repository(repository)
        data = self.client.request(
            "GET",
            f"/repos/{repo}/commits",
            query={"sha": branch or self.config.default_branch, "per_page": limit},
        )
        commits = [
            {
                "sha": item.get("sha", ""),
                "message": item.get("commit", {}).get("message", ""),
                "author": item.get("commit", {}).get("author", {}).get("name", ""),
                "date": item.get("commit", {}).get("author", {}).get("date", ""),
                "url": item.get("html_url", ""),
            }
            for item in data[:limit]
        ]
        return self._payload(repo, {"commits": commits})

    def get_commit_details(self, repository: str | None, sha: str) -> dict[str, Any]:
        repo = self._repository(repository)
        data = self.client.request("GET", f"/repos/{repo}/commits/{sha}")
        return self._payload(
            repo,
            {
                "sha": data.get("sha", sha),
                "message": data.get("commit", {}).get("message", ""),
                "files": [
                    {
                        "filename": item.get("filename", ""),
                        "status": item.get("status", ""),
                        "additions": item.get("additions", 0),
                        "deletions": item.get("deletions", 0),
                    }
                    for item in data.get("files", [])
                ],
            },
        )

    def get_changed_files(
        self,
        repository: str | None,
        base: str | None,
        head: str,
    ) -> dict[str, Any]:
        repo = self._repository(repository)
        if base:
            data = self.client.request("GET", f"/repos/{repo}/compare/{base}...{head}")
            commits = [item.get("sha", "") for item in data.get("commits", [])]
            files = data.get("files", [])
        else:
            data = self.client.request("GET", f"/repos/{repo}/commits/{head}")
            commits = [data.get("sha", head)]
            files = data.get("files", [])
        return self._payload(
            repo,
            {
                "commits": commits,
                "files": [
                    {
                        "filename": item.get("filename", ""),
                        "status": item.get("status", ""),
                        "additions": item.get("additions", 0),
                        "deletions": item.get("deletions", 0),
                    }
                    for item in files
                ],
            },
        )

    def summarize_diff(
        self,
        repository: str | None,
        base: str | None,
        head: str,
        max_files: int,
    ) -> dict[str, Any]:
        changed = self.get_changed_files(repository, base, head)
        files = changed["data"]["files"][:max_files]
        additions = sum(int(item.get("additions", 0)) for item in files)
        deletions = sum(int(item.get("deletions", 0)) for item in files)
        touched = ", ".join(str(item.get("filename", "")) for item in files[:8])
        return self._payload(
            changed["data"]["repository"],
            {
                "summary": {
                    "file_count": len(files),
                    "additions": additions,
                    "deletions": deletions,
                    "focus": touched,
                    "classification": (
                        "application_code_change"
                        if any("src/" in str(item.get("filename", "")) for item in files)
                        else "configuration_or_documentation_change"
                    ),
                }
            },
        )

    def get_pull_request(self, repository: str | None, pull_number: int) -> dict[str, Any]:
        repo = self._repository(repository)
        data = self.client.request("GET", f"/repos/{repo}/pulls/{pull_number}")
        return self._payload(
            repo,
            {
                "pull_request": {
                    "number": data.get("number", pull_number),
                    "title": data.get("title", ""),
                    "state": data.get("state", ""),
                    "head_sha": data.get("head", {}).get("sha", ""),
                    "base_branch": data.get("base", {}).get("ref", ""),
                    "head_branch": data.get("head", {}).get("ref", ""),
                    "url": data.get("html_url", ""),
                }
            },
        )

    def get_workflow_runs(
        self,
        repository: str | None,
        branch: str | None,
        status: str | None,
        limit: int,
    ) -> dict[str, Any]:
        repo = self._repository(repository)
        query: dict[str, str | int] = {"per_page": limit}
        if branch:
            query["branch"] = branch
        if status:
            query["status"] = status
        data = self.client.request("GET", f"/repos/{repo}/actions/runs", query=query)
        return self._payload(repo, {"workflow_runs": _workflow_runs(data, limit)})

    def get_latest_failed_build(self, repository: str | None, branch: str | None) -> dict[str, Any]:
        repo = self._repository(repository)
        query: dict[str, str | int] = {
            "status": "completed",
            "branch": branch or self.config.default_branch,
            "per_page": 20,
        }
        data = self.client.request("GET", f"/repos/{repo}/actions/runs", query=query)
        failures = [
            item
            for item in _workflow_runs(data, 20)
            if item.get("conclusion") in {"failure", "timed_out", "cancelled"}
        ]
        return self._payload(repo, {"latest_failed_build": failures[0] if failures else None})

    def get_workflow_run_jobs(self, repository: str | None, run_id: int) -> dict[str, Any]:
        repo = self._repository(repository)
        data = self.client.request("GET", f"/repos/{repo}/actions/runs/{run_id}/jobs")
        jobs = [
            {
                "id": item.get("id"),
                "name": item.get("name", ""),
                "status": item.get("status", ""),
                "conclusion": item.get("conclusion"),
                "started_at": item.get("started_at"),
                "completed_at": item.get("completed_at"),
            }
            for item in data.get("jobs", [])
        ]
        return self._payload(repo, {"jobs": jobs})

    def get_job_logs(self, repository: str | None, job_id: int, max_bytes: int) -> dict[str, Any]:
        repo = self._repository(repository)
        logs = self.client.request(
            "GET",
            f"/repos/{repo}/actions/jobs/{job_id}/logs",
            max_bytes=max_bytes,
        )
        text = str(logs)[:max_bytes]
        return self._payload(
            repo,
            {
                "job_id": job_id,
                "truncated": len(str(logs)) > max_bytes,
                "logs": text,
            },
        )

    def run_tests(
        self,
        repository: str | None,
        branch: str | None,
        test_suite: str,
        reason: str,
    ) -> dict[str, Any]:
        repo = self._repository(repository)
        selected_branch = branch or self.config.default_branch
        return self._payload(
            repo,
            {
                "test_result": {
                    "branch": selected_branch,
                    "suite": test_suite,
                    "status": "completed",
                    "conclusion": "success",
                    "duration_seconds": 42,
                    "reason": reason,
                    "backend": "local-mocked-pipeline",
                }
            },
        )

    def rerun_build(self, repository: str | None, run_id: int, reason: str) -> dict[str, Any]:
        repo = self._repository(repository)
        if getattr(self.client, "is_configured", False):
            self.client.request("POST", f"/repos/{repo}/actions/runs/{run_id}/rerun")
            backend = "github-actions"
        else:
            backend = "local-mocked-pipeline"
        return self._payload(
            repo,
            {
                "run_id": run_id,
                "rerun_requested": True,
                "reason": reason,
                "backend": backend,
            },
        )

    def analyze_build_failure(
        self,
        repository: str | None,
        logs: str,
        changed_files: list[str],
        build_conclusion: str | None,
    ) -> dict[str, Any]:
        repo = self._repository(repository)
        normalized_logs = logs.lower()
        code_files = [
            item
            for item in changed_files
            if item.startswith(("src/", "apps/", "packages/", "services/"))
            and not item.endswith((".md", ".txt"))
        ]
        if "test failure" in normalized_logs or "failed" in normalized_logs:
            failure_source = "source_code_failure" if code_files else "pipeline_or_environment"
            confidence = 0.78 if code_files else 0.61
        elif build_conclusion in {"failure", "timed_out"}:
            failure_source = "unknown_build_failure"
            confidence = 0.52
        else:
            failure_source = "no_failure_detected"
            confidence = 0.4
        return self._payload(
            repo,
            {
                "analysis": {
                    "source": failure_source,
                    "confidence": confidence,
                    "observations": [
                        f"build_conclusion={build_conclusion or 'unknown'}",
                        f"code_files_changed={len(code_files)}",
                    ],
                    "recommended_action": (
                        "Create an engineering issue and run bounded tests."
                        if failure_source == "source_code_failure"
                        else "Collect more CI logs before opening a code-defect ticket."
                    ),
                }
            },
        )

    def create_issue(
        self,
        repository: str | None,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict[str, Any]:
        repo = self._repository(repository)
        data = self.client.request(
            "POST",
            f"/repos/{repo}/issues",
            body={"title": title, "body": body, "labels": labels},
        )
        return self._payload(
            repo,
            {
                "issue": {
                    "number": data.get("number"),
                    "title": data.get("title", title),
                    "url": data.get("html_url", ""),
                    "state": data.get("state", ""),
                }
            },
        )

    def rerun_workflow(self, repository: str | None, run_id: int, reason: str) -> dict[str, Any]:
        repo = self._repository(repository)
        self.client.request("POST", f"/repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs")
        return self._payload(repo, {"run_id": run_id, "rerun_requested": True, "reason": reason})

    def _repository(self, repository: str | None) -> str:
        repo = repository or self.config.default_repository
        allowed = self.config.allowed_repositories
        if allowed and repo not in allowed:
            raise PermissionDenied(f"Repository {repo} is not in GITHUB_ALLOWED_REPOSITORIES.")
        return repo

    def _payload(self, repository: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "data": {
                "repository": repository,
                "github_configured": bool(getattr(self.client, "is_configured", False)),
                **data,
            },
        }


def _workflow_runs(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "name": item.get("name", ""),
            "branch": item.get("head_branch", ""),
            "sha": item.get("head_sha", ""),
            "status": item.get("status", ""),
            "conclusion": item.get("conclusion"),
            "url": item.get("html_url", ""),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        for item in data.get("workflow_runs", [])[:limit]
    ]
