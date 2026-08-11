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
        compare = f"{base}...{head}" if base else head
        data = self.client.request("GET", f"/repos/{repo}/compare/{compare}")
        return self._payload(
            repo,
            {
                "commits": [item.get("sha", "") for item in data.get("commits", [])],
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
