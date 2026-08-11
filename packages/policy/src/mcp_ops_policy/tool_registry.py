from enum import StrEnum

from pydantic import BaseModel, Field

from mcp_ops_policy.security import (
    ServerTrustLevel,
    ToolMetadataSecurityError,
    fingerprint_metadata,
    sanitize_description,
    suspicious_instruction_flags,
    validate_tool_identity,
)


class RiskLevel(StrEnum):
    READ_ONLY = "READ_ONLY"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ToolMetadata(BaseModel):
    tool_name: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    description: str = Field(min_length=1)
    risk_level: RiskLevel
    required_permission: str = Field(min_length=1)
    requires_approval: bool
    server: str = Field(min_length=1)
    category: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    server_trust_level: ServerTrustLevel = ServerTrustLevel.INTERNAL
    metadata_fingerprint: str = Field(default="", min_length=0)
    security_flags: list[str] = Field(default_factory=list)
    input_resource_types: list[str] = Field(default_factory=list)
    output_resource_types: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    cost_weight: float = Field(default=1.0, ge=0.0)
    idempotent: bool = True
    retry_safe: bool = False
    default_max_retries: int = Field(default=0, ge=0, le=10)
    retry_strategy: str = Field(
        default="NO_RETRY",
        pattern="^(NO_RETRY|FIXED_DELAY|EXPONENTIAL_BACKOFF)$",
    )
    compensation_tool: str | None = None
    executable: bool = True
    timeout_seconds: int = Field(default=5, ge=1, le=120)
    rate_limit: str = Field(min_length=1)
    enabled: bool = True


TOOL_REGISTRY: dict[str, ToolMetadata] = {}


def _register(
    tool_name: str,
    domain: str,
    description: str,
    risk_level: RiskLevel,
    required_permission: str,
    *,
    requires_approval: bool = False,
    timeout_seconds: int = 5,
    rate_limit: str = "60/minute",
    server: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    required_roles: list[str] | None = None,
    server_trust_level: ServerTrustLevel = ServerTrustLevel.INTERNAL,
    input_resource_types: list[str] | None = None,
    output_resource_types: list[str] | None = None,
    preconditions: list[str] | None = None,
    cost_weight: float = 1.0,
    idempotent: bool = True,
    retry_safe: bool = False,
    default_max_retries: int = 0,
    retry_strategy: str = "NO_RETRY",
    compensation_tool: str | None = None,
    executable: bool = True,
) -> None:
    resolved_server = server or f"{domain}-mcp"
    validate_tool_identity(tool_name, resolved_server)
    sanitized_description = sanitize_description(description)
    security_flags = suspicious_instruction_flags(sanitized_description)
    if security_flags:
        from mcp_ops_observability.metrics import record_tool_metadata_rejection

        record_tool_metadata_rejection(reason="suspicious_description")
        raise ToolMetadataSecurityError("suspicious_description")
    metadata = ToolMetadata(
        tool_name=tool_name,
        domain=domain,
        description=sanitized_description,
        risk_level=risk_level,
        required_permission=required_permission,
        requires_approval=requires_approval,
        server=resolved_server,
        category=category or domain,
        tags=tags or _default_tags(tool_name, description, domain),
        required_roles=required_roles or [],
        server_trust_level=server_trust_level,
        security_flags=security_flags,
        input_resource_types=input_resource_types or [],
        output_resource_types=output_resource_types or [],
        preconditions=preconditions or [],
        cost_weight=cost_weight,
        idempotent=idempotent,
        retry_safe=retry_safe,
        default_max_retries=default_max_retries,
        retry_strategy=retry_strategy,
        compensation_tool=compensation_tool,
        executable=executable,
        timeout_seconds=timeout_seconds,
        rate_limit=rate_limit,
    )
    fingerprint = fingerprint_metadata(metadata.model_dump(mode="json"))
    metadata = metadata.model_copy(update={"metadata_fingerprint": fingerprint})
    existing = TOOL_REGISTRY.get(tool_name)
    if existing is not None:
        if existing.metadata_fingerprint != metadata.metadata_fingerprint:
            from mcp_ops_observability.metrics import record_tool_metadata_rejection

            record_tool_metadata_rejection(reason="conflicting_duplicate_tool")
            raise ToolMetadataSecurityError("conflicting_duplicate_tool")
        return
    TOOL_REGISTRY[tool_name] = metadata


def _default_tags(tool_name: str, description: str, domain: str) -> list[str]:
    words = {
        domain,
        *tool_name.replace("_", " ").split(),
        *description.lower().replace(".", "").replace(",", "").split(),
    }
    return sorted(word for word in words if len(word) >= 3)


for _name, _description in {
    "list_devices": "List simulator devices with filters and pagination.",
    "get_device": "Read full simulator device inventory details.",
    "get_device_status": "Read current simulator device status.",
    "get_device_health": "Read current simulator device health score and state.",
    "get_device_telemetry": "Read recent simulator telemetry points.",
    "get_device_configuration": "Read sanitized simulator runtime configuration.",
    "get_device_services": "Read simulator device service states.",
}.items():
    _register(
        _name,
        "device",
        _description,
        RiskLevel.READ_ONLY,
        "devices:read",
        rate_limit="120/minute",
    )

_register(
    "run_device_diagnostics",
    "device",
    "Run bounded diagnostics on a simulator device.",
    RiskLevel.MEDIUM,
    "devices:diagnose",
    rate_limit="20/minute",
)
_register(
    "restart_device",
    "device",
    "Request a governed simulator device restart.",
    RiskLevel.HIGH,
    "devices:operate",
    requires_approval=True,
    timeout_seconds=10,
    rate_limit="5/minute",
)
_register(
    "restart_service",
    "device",
    "Request a governed service restart on a simulator device.",
    RiskLevel.HIGH,
    "devices:operate",
    requires_approval=True,
    timeout_seconds=10,
    rate_limit="5/minute",
)
_register(
    "update_device_configuration",
    "device",
    "Request a governed simulator device configuration update.",
    RiskLevel.CRITICAL,
    "devices:operate",
    requires_approval=True,
    timeout_seconds=15,
    rate_limit="2/minute",
)

for _name, _description in {
    "search_logs": "Search operational logs for simulator devices.",
    "get_recent_errors": "Read recent operational errors for a simulator device.",
    "get_error_details": "Read structured details for a known error code.",
    "get_service_health": "Read diagnostic health for a specific device service.",
    "get_resource_usage": "Read resource usage summary for a simulator device.",
    "find_similar_incidents": "Find seeded historical incidents similar to a device failure.",
}.items():
    _register(_name, "diagnostics", _description, RiskLevel.READ_ONLY, "devices:read")

_register(
    "run_diagnostic_check",
    "diagnostics",
    "Run one bounded diagnostic check for a simulator device.",
    RiskLevel.MEDIUM,
    "devices:diagnose",
    rate_limit="20/minute",
)
_register(
    "generate_diagnostic_summary",
    "diagnostics",
    "Generate a structured diagnostic summary for a simulator device.",
    RiskLevel.MEDIUM,
    "devices:diagnose",
    rate_limit="20/minute",
)

for _name, _description in {
    "search_knowledge": "Search seeded engineering knowledge documents.",
    "get_document": "Read a seeded engineering knowledge document.",
    "get_procedure": "Read a seeded troubleshooting or operations procedure.",
    "find_troubleshooting_steps": "Find troubleshooting steps for a known error code.",
    "search_configuration_guides": "Search seeded configuration guides.",
}.items():
    _register(_name, "knowledge", _description, RiskLevel.READ_ONLY, "knowledge:read")

_register(
    "create_ticket",
    "ticket",
    "Create an engineering maintenance ticket.",
    RiskLevel.MEDIUM,
    "tickets:create",
    rate_limit="30/minute",
)
for _name, (_description, _permission) in {
    "get_ticket": ("Read an engineering maintenance ticket.", "tickets:read"),
    "update_ticket": (
        "Update status, priority, or description on an engineering ticket.",
        "tickets:update",
    ),
    "assign_ticket": ("Assign an engineering maintenance ticket.", "tickets:update"),
    "search_tickets": ("Search engineering maintenance tickets.", "tickets:read"),
    "get_open_tickets": ("Read open engineering maintenance tickets.", "tickets:read"),
}.items():
    _register(_name, "ticket", _description, RiskLevel.READ_ONLY, _permission)


for _name, _description, _risk, _permission, _approval, _tags in [
    (
        "get_pipeline_logs",
        "Retrieve logs from a CI/CD pipeline execution or failed build job.",
        RiskLevel.READ_ONLY,
        "cicd:read",
        False,
        ["pipeline", "build", "logs", "ci", "failure", "job"],
    ),
    (
        "get_build_status",
        "Read latest build status, failed jobs, stages, and pipeline result metadata.",
        RiskLevel.READ_ONLY,
        "cicd:read",
        False,
        ["build", "status", "pipeline", "ci", "failed", "stage"],
    ),
    (
        "get_failed_jobs",
        "List failed CI/CD jobs with failure reasons and timestamps.",
        RiskLevel.READ_ONLY,
        "cicd:read",
        False,
        ["failed", "jobs", "build", "pipeline", "ci"],
    ),
    (
        "analyze_build_failure",
        "Analyze build status, logs, commits, and changed files to classify likely failure source.",
        RiskLevel.MEDIUM,
        "cicd:read",
        False,
        ["analyze", "build", "failure", "logs", "commits", "classification"],
    ),
    (
        "run_tests",
        "Run a bounded test suite for a repository branch or pull request.",
        RiskLevel.MEDIUM,
        "cicd:execute",
        False,
        ["tests", "ci", "validation", "branch", "pull-request"],
    ),
    (
        "rerun_build",
        "Rerun a failed CI/CD build or pipeline job.",
        RiskLevel.MEDIUM,
        "cicd:execute",
        False,
        ["rerun", "build", "pipeline", "job", "ci"],
    ),
    (
        "deploy_staging",
        "Deploy a validated build to the staging environment.",
        RiskLevel.HIGH,
        "deployments:operate",
        True,
        ["deploy", "staging", "release", "environment"],
    ),
    (
        "rollback_production",
        "Request rollback of a production deployment to a previous validated release.",
        RiskLevel.HIGH,
        "deployments:operate",
        True,
        ["rollback", "production", "deployment", "release", "approval"],
    ),
    (
        "delete_bad_deployment",
        "Delete deployment artifacts and release records after governance review.",
        RiskLevel.CRITICAL,
        "deployments:operate",
        True,
        ["delete", "deployment", "artifact", "release", "critical"],
    ),
    (
        "get_deployment_status",
        "Retrieve deployment state, version, environment, and rollout health.",
        RiskLevel.READ_ONLY,
        "deployments:read",
        False,
        ["deployment", "status", "environment", "rollout", "release"],
    ),
    (
        "compare_deployments",
        "Compare two deployments, versions, environments, or rollout states.",
        RiskLevel.READ_ONLY,
        "deployments:read",
        False,
        ["compare", "deployment", "version", "release", "environment"],
    ),
]:
    _register(
        _name,
        "cicd",
        _description,
        _risk,
        _permission,
        requires_approval=_approval,
        server="cicd-mcp",
        category="cicd",
        tags=_tags,
        required_roles=["ENGINEER", "OPERATOR", "ADMIN"],
        executable=False,
    )

for _name, _description, _tags in [
    (
        "get_commit_history",
        "Read repository commit history for a branch, time window, or deployment range.",
        ["commit", "history", "repository", "git", "changes"],
    ),
    (
        "list_recent_commits",
        "List recent repository commits with authors, timestamps, and messages.",
        ["commit", "recent", "repository", "git", "history"],
    ),
    (
        "get_recent_commits",
        "Read recent repository commits for a branch, build, or deployment investigation.",
        ["commit", "recent", "repository", "git", "history", "build"],
    ),
    (
        "get_changed_files",
        "List files changed in a commit, pull request, or deployment comparison.",
        ["changed", "files", "diff", "repository", "pull-request"],
    ),
    (
        "summarize_diff",
        "Summarize repository diffs for code-review or build-failure investigation.",
        ["diff", "summary", "repository", "code", "changes"],
    ),
    (
        "get_pull_request",
        "Retrieve pull request metadata, checks, changed files, and review status.",
        ["pull-request", "pr", "review", "repository", "checks"],
    ),
]:
    _register(
        _name,
        "repository",
        _description,
        RiskLevel.READ_ONLY,
        "repositories:read",
        server="repository-mcp",
        category="repository",
        tags=_tags,
        required_roles=["ENGINEER", "OPERATOR", "ADMIN"],
        executable=False,
    )

for _name, _description, _tags in [
    (
        "get_service_owner",
        "Retrieve service ownership, team, escalation, and repository mapping.",
        ["service", "owner", "team", "catalog", "ownership"],
    ),
    (
        "get_runbook",
        "Retrieve an engineering runbook for a service, build, deployment, or incident.",
        ["runbook", "documentation", "service", "procedure", "operations"],
    ),
    (
        "search_documentation",
        "Search engineering documentation, runbooks, architecture notes, and release guides.",
        ["documentation", "search", "runbook", "guide", "knowledge"],
    ),
]:
    _register(
        _name,
        "service_catalog",
        _description,
        RiskLevel.READ_ONLY,
        "knowledge:read",
        server="service-catalog-mcp",
        category="service_catalog",
        tags=_tags,
        required_roles=["VIEWER", "ENGINEER", "OPERATOR", "ADMIN"],
        executable=False,
    )


def _update_metadata(tool_name: str, **updates: object) -> None:
    metadata = TOOL_REGISTRY[tool_name].model_copy(update=updates)
    TOOL_REGISTRY[tool_name] = metadata.model_copy(
        update={"metadata_fingerprint": fingerprint_metadata(metadata.model_dump(mode="json"))}
    )


_update_metadata(
    "get_pipeline_logs",
    executable=True,
    default_max_retries=2,
    retry_strategy="EXPONENTIAL_BACKOFF",
    retry_safe=True,
)
_update_metadata(
    "get_build_status",
    executable=True,
    default_max_retries=2,
    retry_strategy="FIXED_DELAY",
    retry_safe=True,
)
_update_metadata(
    "get_failed_jobs",
    executable=True,
    default_max_retries=2,
    retry_strategy="FIXED_DELAY",
    retry_safe=True,
)
for _implemented_repository_tool in (
    "get_commit_history",
    "list_recent_commits",
    "get_recent_commits",
    "get_changed_files",
):
    _update_metadata(_implemented_repository_tool, executable=True)

for _name, _description, _risk, _permission, _approval, _tags in [
    (
        "get_commit_details",
        "Retrieve one GitHub commit with changed files for build-failure investigation.",
        RiskLevel.READ_ONLY,
        "repositories:read",
        False,
        ["commit", "details", "github", "repository", "files"],
    ),
    (
        "get_workflow_runs",
        "List GitHub Actions workflow runs for an allowed repository.",
        RiskLevel.READ_ONLY,
        "cicd:read",
        False,
        ["github", "actions", "workflow", "runs", "ci"],
    ),
    (
        "get_latest_failed_build",
        "Retrieve the latest failed GitHub Actions build for an allowed repository.",
        RiskLevel.READ_ONLY,
        "cicd:read",
        False,
        ["github", "actions", "failed", "build", "ci"],
    ),
    (
        "get_workflow_run_jobs",
        "List jobs for a GitHub Actions workflow run.",
        RiskLevel.READ_ONLY,
        "cicd:read",
        False,
        ["github", "actions", "jobs", "workflow", "ci"],
    ),
    (
        "get_job_logs",
        "Retrieve bounded logs for a GitHub Actions workflow job.",
        RiskLevel.READ_ONLY,
        "cicd:read",
        False,
        ["github", "actions", "logs", "job", "ci"],
    ),
    (
        "create_issue",
        "Create a GitHub issue for a governed engineering workflow finding.",
        RiskLevel.MEDIUM,
        "tickets:create",
        False,
        ["github", "issue", "ticket", "maintenance", "workflow"],
    ),
    (
        "rerun_workflow",
        "Request a governed rerun of failed GitHub Actions jobs after human approval.",
        RiskLevel.HIGH,
        "cicd:execute",
        True,
        ["github", "actions", "rerun", "workflow", "approval"],
    ),
]:
    _register(
        _name,
        "cicd" if _permission.startswith("cicd:") else "repository",
        _description,
        _risk,
        _permission,
        requires_approval=_approval,
        server="cicd-mcp" if _permission.startswith("cicd:") else "repository-mcp",
        category="cicd" if _permission.startswith("cicd:") else "repository",
        tags=_tags,
        required_roles=["ENGINEER", "OPERATOR", "ADMIN"],
        executable=True,
        idempotent=_name not in {"create_issue", "rerun_workflow"},
        retry_safe=_name not in {"create_issue", "rerun_workflow"},
        default_max_retries=1 if _name not in {"create_issue", "rerun_workflow"} else 0,
        retry_strategy="FIXED_DELAY",
        rate_limit="10/minute" if _name in {"create_issue", "rerun_workflow"} else "60/minute",
    )
_update_metadata(
    "run_tests",
    idempotent=False,
    retry_safe=True,
    default_max_retries=1,
    retry_strategy="FIXED_DELAY",
)
_update_metadata(
    "deploy_staging",
    idempotent=False,
    default_max_retries=1,
    retry_strategy="EXPONENTIAL_BACKOFF",
    compensation_tool="restore_previous_staging_release",
)
_update_metadata(
    "create_ticket",
    idempotent=False,
    retry_safe=False,
    default_max_retries=1,
    retry_strategy="FIXED_DELAY",
    compensation_tool="close_ticket_if_created_by_failed_workflow",
)

_register(
    "restore_previous_staging_release",
    "cicd",
    "Restore the previous staging release after a failed governed deployment workflow.",
    RiskLevel.HIGH,
    "deployments:operate",
    requires_approval=True,
    server="cicd-mcp",
    category="cicd",
    tags=["restore", "staging", "deployment", "compensation"],
    required_roles=["OPERATOR", "ADMIN"],
    executable=False,
    idempotent=False,
    retry_safe=False,
)
_register(
    "close_ticket_if_created_by_failed_workflow",
    "ticket",
    "Close a ticket only when it was created by the failed workflow being compensated.",
    RiskLevel.MEDIUM,
    "tickets:update",
    server="ticket-mcp",
    category="ticket",
    tags=["ticket", "close", "workflow", "compensation"],
    required_roles=["ENGINEER", "OPERATOR", "ADMIN"],
    executable=False,
    idempotent=False,
    retry_safe=False,
)


def get_tool_metadata(tool_name: str) -> ToolMetadata | None:
    return TOOL_REGISTRY.get(tool_name)
