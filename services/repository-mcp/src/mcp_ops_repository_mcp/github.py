from __future__ import annotations

import json
from dataclasses import dataclass
from http.client import HTTPSConnection
from typing import Any
from urllib.parse import urlencode, urlparse

from mcp_ops_common.config import Settings, get_settings
from mcp_ops_mcp.errors import PermissionDenied, ServiceUnavailable


class GitHubApiError(ServiceUnavailable):
    pass


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    token: str
    owner: str
    repo: str
    default_branch: str
    allowed_repositories: frozenset[str]
    api_base_url: str = "https://api.github.com"

    @property
    def default_repository(self) -> str:
        if self.owner and self.repo:
            return f"{self.owner}/{self.repo}"
        if self.allowed_repositories:
            return sorted(self.allowed_repositories)[0]
        return "ImmanuelP31/MCP_AI"

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> GitHubConfig:
        settings = settings or get_settings()
        configured = {
            item.strip()
            for item in settings.github_allowed_repositories.split(",")
            if item.strip()
        }
        if settings.github_owner and settings.github_repo:
            configured.add(f"{settings.github_owner}/{settings.github_repo}")
        return cls(
            token=settings.github_token,
            owner=settings.github_owner,
            repo=settings.github_repo,
            default_branch=settings.github_default_branch,
            allowed_repositories=frozenset(configured),
            api_base_url=settings.github_api_base_url,
        )


class GitHubClient:
    def __init__(self, config: GitHubConfig | None = None, *, timeout_seconds: float = 8.0) -> None:
        self.config = config or GitHubConfig.from_settings()
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.config.token)

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str | int] | None = None,
        body: dict[str, Any] | None = None,
        max_bytes: int = 2_000_000,
    ) -> Any:
        if not self.config.token:
            raise GitHubApiError("GitHub token is not configured.")
        parsed = urlparse(self.config.api_base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise GitHubApiError("GitHub API base URL must be HTTPS.")
        target = path
        if query:
            target = f"{target}?{urlencode(query)}"
        encoded_body = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.config.token}",
            "User-Agent": "mcp-engineering-ops-demo",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if encoded_body is not None:
            headers["Content-Type"] = "application/json"
        connection = HTTPSConnection(
            parsed.hostname,
            parsed.port or 443,
            timeout=self.timeout_seconds,
        )
        try:
            connection.request(method, target, body=encoded_body, headers=headers)
            response = connection.getresponse()
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise GitHubApiError("GitHub response exceeded configured size limit.")
            if response.status >= 400:
                raise GitHubApiError(f"GitHub API returned HTTP {response.status}.")
            content_type = response.getheader("Content-Type") or ""
            if "application/json" in content_type:
                return json.loads(raw.decode("utf-8") or "{}")
            return raw.decode("utf-8", errors="replace")
        except OSError as exc:
            raise GitHubApiError(f"GitHub API request failed: {exc.__class__.__name__}.") from exc
        finally:
            connection.close()


class OfflineGitHubClient:
    """Deterministic fallback used when no GitHub token is configured."""

    is_configured = False

    def __init__(self, repository: str = "ImmanuelP31/MCP_AI") -> None:
        self.repository = repository

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str | int] | None = None,
        body: dict[str, Any] | None = None,
        max_bytes: int = 2_000_000,
    ) -> Any:
        del method, query, body, max_bytes
        if path.endswith("/commits"):
            return [
                {
                    "sha": "abc1234demo",
                    "commit": {
                        "message": "Fix payments validation edge case",
                        "author": {"name": "Demo Engineer", "date": "2026-08-11T06:00:00Z"},
                    },
                    "html_url": f"https://github.com/{self.repository}/commit/abc1234demo",
                }
            ]
        if "/actions/runs/" in path and path.endswith("/jobs"):
            return {
                "jobs": [
                    {
                        "id": 101,
                        "name": "test",
                        "status": "completed",
                        "conclusion": "failure",
                        "started_at": "2026-08-11T06:05:00Z",
                        "completed_at": "2026-08-11T06:06:00Z",
                    }
                ]
            }
        if path.endswith("/actions/runs"):
            return {
                "workflow_runs": [
                    {
                        "id": 9001,
                        "name": "Demo Build",
                        "head_branch": "main",
                        "head_sha": "abc1234demo",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": f"https://github.com/{self.repository}/actions/runs/9001",
                        "created_at": "2026-08-11T06:04:00Z",
                        "updated_at": "2026-08-11T06:06:00Z",
                    }
                ]
            }
        if "/actions/jobs/" in path and path.endswith("/logs"):
            return "Running demo test suite\nSimulated test failure in payments-api\n"
        if "/compare/" in path:
            return {
                "files": [
                    {
                        "filename": "src/payments/validation.py",
                        "status": "modified",
                        "additions": 12,
                        "deletions": 3,
                    }
                ],
                "commits": [{"sha": "abc1234demo"}],
            }
        if path.endswith("/issues"):
            return {
                "number": 42,
                "title": "Investigate GitHub Actions failure",
                "html_url": f"https://github.com/{self.repository}/issues/42",
                "state": "open",
            }
        if path.endswith("/rerun-failed-jobs"):
            return {"rerun_requested": True}
        if "/commits/" in path:
            return {
                "sha": "abc1234demo",
                "commit": {"message": "Fix payments validation edge case"},
                "files": [{"filename": "src/payments/validation.py", "status": "modified"}],
            }
        raise PermissionDenied("Offline GitHub demo client does not support this operation.")
