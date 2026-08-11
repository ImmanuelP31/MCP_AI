from __future__ import annotations

from mcp.server.lowlevel import Server
from mcp_ops_mcp.dispatcher import McpToolDispatcher, ToolDefinition, build_lowlevel_server
from mcp_ops_mcp.schemas import (
    GitHubChangedFilesInput,
    GitHubCommitInput,
    GitHubCreateIssueInput,
    GitHubRecentCommitsInput,
    GitHubRepositoryInput,
    GitHubRerunWorkflowInput,
    GitHubWorkflowJobInput,
    GitHubWorkflowRunInput,
    GitHubWorkflowRunsInput,
    StructuredOutput,
)
from mcp_ops_policy.tool_registry import TOOL_REGISTRY

from mcp_ops_repository_mcp.service import GitHubRepositoryService


def create_dispatcher(
    service: GitHubRepositoryService | None = None,
    *,
    disabled_tools: set[str] | None = None,
    unavailable_tools: set[str] | None = None,
    timeout_tools: set[str] | None = None,
) -> McpToolDispatcher:
    service = service or GitHubRepositoryService()
    tools = [
        ToolDefinition(
            TOOL_REGISTRY["get_recent_commits"],
            GitHubRecentCommitsInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_recent_commits(model.repository, model.branch, model.limit)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_commit_history"],
            GitHubRecentCommitsInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_recent_commits(model.repository, model.branch, model.limit)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["list_recent_commits"],
            GitHubRecentCommitsInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_recent_commits(model.repository, model.branch, model.limit)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_commit_details"],
            GitHubCommitInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_commit_details(model.repository, model.sha)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_changed_files"],
            GitHubChangedFilesInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_changed_files(model.repository, model.base, model.head)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_workflow_runs"],
            GitHubWorkflowRunsInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_workflow_runs(
                    model.repository,
                    model.branch,
                    model.status,
                    model.limit,
                )
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_build_status"],
            GitHubRepositoryInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_latest_failed_build(model.repository, None)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_latest_failed_build"],
            GitHubRepositoryInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_latest_failed_build(model.repository, None)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_failed_jobs"],
            GitHubWorkflowRunInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_workflow_run_jobs(model.repository, model.run_id)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_workflow_run_jobs"],
            GitHubWorkflowRunInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_workflow_run_jobs(model.repository, model.run_id)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_job_logs"],
            GitHubWorkflowJobInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_job_logs(model.repository, model.job_id, model.max_bytes)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_pipeline_logs"],
            GitHubWorkflowJobInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.get_job_logs(model.repository, model.job_id, model.max_bytes)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["create_issue"],
            GitHubCreateIssueInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.create_issue(model.repository, model.title, model.body, model.labels)
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["rerun_workflow"],
            GitHubRerunWorkflowInput,
            StructuredOutput,
            lambda model: StructuredOutput.model_validate(
                service.rerun_workflow(model.repository, model.run_id, model.reason)
            ),
        ),
    ]
    return McpToolDispatcher(
        tools,
        disabled_tools=disabled_tools,
        unavailable_tools=unavailable_tools,
        timeout_tools=timeout_tools,
    )


def create_server(dispatcher: McpToolDispatcher | None = None) -> Server:
    return build_lowlevel_server("repository-mcp", dispatcher or create_dispatcher())


server = create_server()
