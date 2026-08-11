from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ActorRole = Literal["ADMIN", "ENGINEER", "OPERATOR", "VIEWER"]
ApprovalToken = Literal["APPROVED_OPERATION_TOKEN"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AuthorizedInput(StrictModel):
    actor_role: ActorRole = Field(description="Authenticated actor role supplied by MCP gateway.")


class PaginationInput(AuthorizedInput):
    limit: int = Field(default=25, ge=1, le=100, description="Maximum records to return.")


class DeviceIdInput(AuthorizedInput):
    device_id: str = Field(pattern=r"^SIM-\d{3}$", description="Simulator device identifier.")


class DeviceTelemetryInput(DeviceIdInput):
    limit: int = Field(default=5, ge=1, le=25, description="Telemetry point count.")


class DeviceConfigurationInput(DeviceIdInput):
    pass


class RunDiagnosticsInput(DeviceIdInput):
    checks: list[str] = Field(
        default_factory=lambda: ["service_health", "resource_usage", "recent_errors"],
        min_length=1,
        max_length=8,
        description="Bounded diagnostic checks to run.",
    )


class RestartDeviceInput(DeviceIdInput):
    approval_token: ApprovalToken = Field(description="Human-approved operation token.")
    reason: str = Field(min_length=8, max_length=500, description="Operational reason.")


class RestartServiceInput(RestartDeviceInput):
    service_name: str = Field(
        min_length=1,
        max_length=128,
        description="Known device service name.",
    )


class UpdateDeviceConfigurationInput(RestartDeviceInput):
    configuration_patch: dict[str, str | int | float | bool] = Field(
        min_length=1,
        max_length=20,
        description=(
            "Validated configuration patch. Arbitrary files, SQL, and shell commands "
            "are not accepted."
        ),
    )

    @field_validator("configuration_patch")
    @classmethod
    def validate_configuration_patch(
        cls,
        value: dict[str, str | int | float | bool],
    ) -> dict[str, str | int | float | bool]:
        allowed_keys = {
            "telemetry_interval_seconds",
            "diagnostics_enabled",
            "firmware_channel",
            "packet_loss_threshold",
        }
        rejected = sorted(set(value) - allowed_keys)
        if rejected:
            raise ValueError("Unsupported configuration keys: " + ", ".join(rejected) + ".")
        for key, item in value.items():
            if key == "telemetry_interval_seconds":
                if not isinstance(item, int) or isinstance(item, bool):
                    raise ValueError(
                        "telemetry_interval_seconds must be an integer from 5 to 3600."
                    )
                if not 5 <= item <= 3600:
                    raise ValueError(
                        "telemetry_interval_seconds must be an integer from 5 to 3600."
                    )
            if key == "diagnostics_enabled":
                if not isinstance(item, bool):
                    raise ValueError("diagnostics_enabled must be a boolean.")
            if key == "firmware_channel":
                if not isinstance(item, str) or item not in {"stable", "candidate"}:
                    raise ValueError("firmware_channel must be stable or candidate.")
            if key == "packet_loss_threshold":
                if not isinstance(item, (int, float)) or isinstance(item, bool):
                    raise ValueError("packet_loss_threshold must be numeric from 0 to 100.")
                if not 0 <= item <= 100:
                    raise ValueError("packet_loss_threshold must be numeric from 0 to 100.")
        return value


class SearchLogsInput(DeviceIdInput):
    severity: Literal["INFO", "WARNING", "ERROR", "CRITICAL"] | None = None
    query: str | None = Field(default=None, min_length=1, max_length=120)
    limit: int = Field(default=20, ge=1, le=100)


class ErrorDetailsInput(AuthorizedInput):
    error_code: str = Field(min_length=3, max_length=64)


class ServiceHealthInput(DeviceIdInput):
    service_name: str = Field(min_length=1, max_length=128)


class DiagnosticCheckInput(DeviceIdInput):
    check_name: str = Field(min_length=3, max_length=80)


class KnowledgeSearchInput(AuthorizedInput):
    query: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=10, ge=1, le=50)


class KnowledgeDocumentInput(AuthorizedInput):
    document_id: str = Field(min_length=2, max_length=128)


class ProcedureInput(AuthorizedInput):
    procedure_id: str = Field(min_length=2, max_length=128)


class TroubleshootingInput(AuthorizedInput):
    error_code: str = Field(min_length=3, max_length=64)
    device_model: str | None = Field(default=None, max_length=128)


class CreateTicketInput(DeviceIdInput):
    title: str = Field(min_length=5, max_length=240)
    description: str = Field(min_length=10, max_length=2000)
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    team: str = Field(min_length=2, max_length=128)
    diagnostic_evidence: dict[str, Any] = Field(default_factory=dict, max_length=20)


class TicketIdInput(AuthorizedInput):
    ticket_id: str = Field(min_length=2, max_length=128)


class UpdateTicketInput(TicketIdInput):
    status: Literal["OPEN", "IN_PROGRESS", "BLOCKED", "RESOLVED", "CLOSED"] | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None
    description: str | None = Field(default=None, min_length=10, max_length=2000)


class AssignTicketInput(TicketIdInput):
    assignee: str = Field(min_length=2, max_length=128)


class SearchTicketsInput(AuthorizedInput):
    query: str | None = Field(default=None, min_length=2, max_length=120)
    status: Literal["OPEN", "IN_PROGRESS", "BLOCKED", "RESOLVED", "CLOSED"] | None = None
    device_id: str | None = Field(default=None, pattern=r"^SIM-\d{3}$")
    limit: int = Field(default=25, ge=1, le=100)


class OpenTicketsInput(AuthorizedInput):
    limit: int = Field(default=25, ge=1, le=100)


RepositoryName = str


class GitHubRepositoryInput(AuthorizedInput):
    repository: RepositoryName | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
        description="Allowed GitHub repository in owner/name form.",
    )


class GitHubRecentCommitsInput(GitHubRepositoryInput):
    branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._/\-]+$",
    )
    limit: int = Field(default=5, ge=1, le=25)


class GitHubCommitInput(GitHubRepositoryInput):
    sha: str = Field(min_length=7, max_length=64, pattern=r"^[A-Fa-f0-9]+$")


class GitHubChangedFilesInput(GitHubRepositoryInput):
    base: str | None = Field(default=None, min_length=7, max_length=64, pattern=r"^[A-Fa-f0-9]+$")
    head: str = Field(min_length=7, max_length=64, pattern=r"^[A-Fa-f0-9]+$")


class GitHubPullRequestInput(GitHubRepositoryInput):
    pull_number: int = Field(ge=1)


class GitHubDiffSummaryInput(GitHubChangedFilesInput):
    max_files: int = Field(default=20, ge=1, le=100)


class GitHubWorkflowRunsInput(GitHubRepositoryInput):
    branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._/\-]+$",
    )
    status: Literal[
        "completed",
        "action_required",
        "cancelled",
        "failure",
        "neutral",
        "skipped",
        "stale",
        "success",
        "timed_out",
        "in_progress",
        "queued",
        "requested",
        "waiting",
    ] | None = None
    limit: int = Field(default=10, ge=1, le=30)


class GitHubWorkflowRunInput(GitHubRepositoryInput):
    run_id: int = Field(ge=1)


class GitHubWorkflowJobInput(GitHubRepositoryInput):
    job_id: int = Field(ge=1)
    max_bytes: int = Field(default=12000, ge=1000, le=60000)


class GitHubCreateIssueInput(GitHubRepositoryInput):
    title: str = Field(min_length=5, max_length=240)
    body: str = Field(min_length=10, max_length=8000)
    labels: list[str] = Field(default_factory=list, max_length=10)


class GitHubRerunWorkflowInput(GitHubWorkflowRunInput):
    approval_token: ApprovalToken = Field(description="Human-approved operation token.")
    reason: str = Field(min_length=8, max_length=500)


class GitHubRunTestsInput(GitHubRepositoryInput):
    branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._/\-]+$",
    )
    test_suite: str = Field(
        default="bounded",
        min_length=3,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    reason: str = Field(default="Governed workflow validation.", min_length=8, max_length=500)


class GitHubRerunBuildInput(GitHubWorkflowRunInput):
    reason: str = Field(default="Governed CI rerun.", min_length=8, max_length=500)


class AnalyzeBuildFailureInput(GitHubRepositoryInput):
    logs: str = Field(default="", max_length=12000)
    changed_files: list[str] = Field(default_factory=list, max_length=100)
    build_conclusion: str | None = Field(default=None, max_length=80)


class StructuredOutput(StrictModel):
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)


class StructuredError(StrictModel):
    ok: bool = False
    error: dict[str, str]


class ToolCatalogEntry(StrictModel):
    tool_name: str
    domain: str
    description: str
    risk_level: str
    required_permission: str
    requires_approval: bool
    enabled: bool


class ToolExecutionRecord(StrictModel):
    tool_name: str
    timestamp: datetime
    result: Literal["allowed", "denied", "validation_error", "failed"]
