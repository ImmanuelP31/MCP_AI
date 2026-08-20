from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from mcp_ops_auth.rbac import Role
from mcp_ops_common.config import get_settings
from mcp_ops_device_mcp.server import create_dispatcher as create_device_dispatcher
from mcp_ops_diagnostics_mcp.server import create_dispatcher as create_diagnostics_dispatcher
from mcp_ops_knowledge_mcp.server import create_dispatcher as create_knowledge_dispatcher
from mcp_ops_mcp.dispatcher import McpToolDispatcher
from mcp_ops_observability.context import (
    reset_observability_context,
    set_observability_context,
)
from mcp_ops_observability.metrics import (
    observe_approval_latency,
    record_approval_replay_attempt,
    record_argument_validation_failure,
    record_authorization_failure,
    record_mcp_call,
    record_mcp_failure,
)
from mcp_ops_observability.tracing import start_span
from mcp_ops_policy.security import hash_arguments
from mcp_ops_policy.tool_registry import TOOL_REGISTRY, ToolMetadata
from mcp_ops_repository_mcp.server import create_dispatcher as create_repository_dispatcher
from mcp_ops_ticket_mcp.server import create_dispatcher as create_ticket_dispatcher

from mcp_ops_mcp_gateway.errors import (
    DisabledTool,
    GatewayError,
    MalformedArguments,
    NonExecutableTool,
    ToolTimeout,
    UnknownTool,
)
from mcp_ops_mcp_gateway.models import (
    ApprovalRecord,
    ApprovalStatus,
    AuditRecord,
    GatewayDecision,
    GatewayToolRequest,
    GatewayToolResponse,
    Principal,
)
from mcp_ops_mcp_gateway.stores import (
    ApprovalStore,
    AuditLog,
    FixedWindowRateLimiter,
    GatewayAuthorizer,
    IdempotencyOperationStatus,
    IdempotencyStore,
    TokenAuthenticator,
    utc_now,
)

GOVERNED_OPERATION_MARKER = "APPROVED_OPERATION_TOKEN"
logger = logging.getLogger("mcp_ops.mcp_gateway")


class GatewayPolicyEvaluator:
    def evaluate_before_execution(
        self,
        metadata: ToolMetadata,
        approval: ApprovalRecord | None,
    ) -> GatewayDecision:
        if metadata.requires_approval and approval is None:
            return GatewayDecision.PENDING_APPROVAL
        return GatewayDecision.ALLOWED


class McpGateway:
    def __init__(
        self,
        *,
        registry: dict[str, ToolMetadata] | None = None,
        authenticator: Any | None = None,
        authorizer: GatewayAuthorizer | None = None,
        rate_limiter: Any | None = None,
        idempotency: Any | None = None,
        approvals: Any | None = None,
        audit_log: Any | None = None,
        clock: Callable[[], datetime] = utc_now,
        disabled_tools: set[str] | None = None,
    ) -> None:
        self.registry = registry or TOOL_REGISTRY
        if authenticator is None and get_settings().environment == "production":
            raise RuntimeError(
                "McpGateway requires an explicit production authenticator when "
                "ENVIRONMENT=production."
            )
        self.authenticator = authenticator or TokenAuthenticator()
        self.authorizer = authorizer or GatewayAuthorizer()
        self.rate_limiter = rate_limiter or FixedWindowRateLimiter()
        self.idempotency = idempotency or IdempotencyStore()
        self.approvals = approvals or ApprovalStore()
        self.audit_log = audit_log or AuditLog()
        self.approvals.attach_audit_log(self.audit_log)
        self.policy = GatewayPolicyEvaluator()
        self.clock = clock
        self.disabled_tools = disabled_tools or set()
        self._dispatchers = {
            "cicd": create_repository_dispatcher(),
            "device": create_device_dispatcher(),
            "diagnostics": create_diagnostics_dispatcher(),
            "knowledge": create_knowledge_dispatcher(),
            "repository": create_repository_dispatcher(),
            "ticket": create_ticket_dispatcher(),
        }

    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        principal: Principal | None = None
        metadata: ToolMetadata | None = None
        idempotency_reserved = False
        started_perf = time.perf_counter()
        tokens = set_observability_context(
            request_id=str(request.correlation_id),
            correlation_id=str(request.correlation_id),
        )
        now = self.clock()
        try:
            with start_span("mcp_gateway.call_tool", tool_name=request.tool_name):
                principal = self.authenticator.authenticate(request.auth_token)
                metadata = self._metadata(request.tool_name)
                self._check_tool_enabled(metadata)
                self._check_tool_executable(metadata)
                self.authorizer.authorize(principal, metadata.required_permission)
                self.rate_limiter.check(principal, metadata.tool_name, metadata.rate_limit, now)

                sanitized_args = _strip_untrusted_model_fields(request.arguments)
                self._validate_domain_arguments(sanitized_args, principal, metadata)
                replay = self.idempotency.reserve(principal, request.idempotency_key, now)
                if replay is not None:
                    self._record_tool_observability(replay, metadata, started_perf)
                    return replay
                idempotency_reserved = True
                approval = self._approval_for_request(request, metadata, sanitized_args, now)
                decision = self.policy.evaluate_before_execution(metadata, approval)
                if decision == GatewayDecision.PENDING_APPROVAL:
                    approval = self.approvals.create(
                        principal,
                        metadata.tool_name,
                        sanitized_args,
                        metadata.risk_level,
                        now,
                        workflow_id=request.workflow_id,
                        workflow_node_id=request.workflow_node_id,
                        arguments_hash=hash_arguments(sanitized_args),
                        approval_binding_hash=_approval_binding_hash(
                            request,
                            principal.principal_id,
                            metadata.tool_name,
                            sanitized_args,
                        ),
                    )
                    response = self._success(
                        request,
                        principal,
                        metadata,
                        GatewayDecision.PENDING_APPROVAL,
                        {
                            "approval_id": str(approval.approval_id),
                            "approval_status": approval.status.value,
                            "risk_level": metadata.risk_level.value,
                        },
                        approval_status=approval.status,
                        execution_status="PENDING_APPROVAL",
                    )
                    self._record_tool_observability(response, metadata, started_perf)
                    return response

                try:
                    _mark_idempotency_running(
                        self.idempotency,
                        principal,
                        request.idempotency_key,
                        self.clock(),
                    )
                    routed_args = self._trusted_domain_arguments(
                        sanitized_args,
                        principal,
                        metadata,
                    )
                    result = self._dispatcher(metadata).call_tool(metadata.tool_name, routed_args)
                    self._enforce_timeout(metadata, now)
                    if result.is_error:
                        raise MalformedArguments(str(result.structured_content["error"]))
                except GatewayError as exc:
                    if approval is not None:
                        self.approvals.mark_failed(approval, principal, self.clock(), exc.code)
                    raise

                if approval is not None:
                    executed = self.approvals.mark_executed(
                        approval,
                        principal,
                        self.clock(),
                        result.structured_content,
                    )
                    observe_approval_latency(
                        tool_name=executed.tool_name,
                        risk_level=executed.risk_level.value,
                        status=executed.status.value,
                        latency_seconds=_seconds_between(
                            executed.created_at,
                            executed.executed_at or self.clock(),
                        ),
                    )

                response = self._success(
                    request,
                    principal,
                    metadata,
                    GatewayDecision.ALLOWED,
                    {"tool_result": result.structured_content},
                    approval_status=approval.status if approval else None,
                    execution_status="SUCCEEDED",
                )
                _complete_idempotency(
                    self.idempotency,
                    principal,
                    request.idempotency_key,
                    response,
                    status=IdempotencyOperationStatus.SUCCEEDED,
                    now=self.clock(),
                )
                self._record_tool_observability(response, metadata, started_perf)
                return response
        except GatewayError as exc:
            actor = principal or Principal(principal_id="anonymous", role=Role.VIEWER)
            response = self._failure(request, actor, metadata, exc)
            if principal is not None and idempotency_reserved:
                _complete_idempotency(
                    self.idempotency,
                    principal,
                    request.idempotency_key,
                    response,
                    status=IdempotencyOperationStatus.PERMANENT_FAILED,
                    now=self.clock(),
                )
            self._record_tool_observability(response, metadata, started_perf, exc, actor)
            return response
        finally:
            reset_observability_context(tokens)

    def approve_operation(self, auth_token: str, approval_id: UUID) -> GatewayToolResponse:
        now = self.clock()
        try:
            principal = self.authenticator.authenticate(auth_token)
            approval = self.approvals.get(approval_id, now)
            self.authorizer.authorize_approval(principal, approval)
            approved = self.approvals.approve(approval.approval_id, principal, now)
            observe_approval_latency(
                tool_name=approved.tool_name,
                risk_level=approved.risk_level.value,
                status=approved.status.value,
                latency_seconds=_seconds_between(approved.created_at, approved.approved_at or now),
            )
            return GatewayToolResponse(
                ok=True,
                decision=GatewayDecision.ALLOWED,
                correlation_id=approval.approval_id,
                data={
                    "approval_id": str(approved.approval_id),
                    "approval_status": approved.status.value,
                    "approved_by": approved.approved_by or "",
                },
            )
        except GatewayError as exc:
            return GatewayToolResponse(
                ok=False,
                decision=GatewayDecision.DENIED,
                correlation_id=approval_id,
                error={"code": exc.code, "message": exc.message},
            )

    def reject_operation(
        self,
        auth_token: str,
        approval_id: UUID,
        reason: str,
    ) -> GatewayToolResponse:
        now = self.clock()
        try:
            principal = self.authenticator.authenticate(auth_token)
            approval = self.approvals.get(approval_id, now)
            self.authorizer.authorize_approval(principal, approval)
            rejected = self.approvals.reject(approval_id, principal, reason, now)
            observe_approval_latency(
                tool_name=rejected.tool_name,
                risk_level=rejected.risk_level.value,
                status=rejected.status.value,
                latency_seconds=_seconds_between(rejected.created_at, rejected.rejected_at or now),
            )
            return GatewayToolResponse(
                ok=True,
                decision=GatewayDecision.DENIED,
                correlation_id=approval_id,
                data={
                    "approval_id": str(rejected.approval_id),
                    "approval_status": rejected.status.value,
                    "rejected_by": rejected.rejected_by or "",
                },
            )
        except GatewayError as exc:
            return GatewayToolResponse(
                ok=False,
                decision=GatewayDecision.DENIED,
                correlation_id=approval_id,
                error={"code": exc.code, "message": exc.message},
            )

    def list_approvals(self, auth_token: str) -> GatewayToolResponse:
        now = self.clock()
        try:
            principal = self.authenticator.authenticate(auth_token)
            self.authorizer.authorize(principal, "approvals:approve")
            approvals = [
                approval.model_dump(mode="json")
                for approval in self.approvals.list_approvals(now)
            ]
            return GatewayToolResponse(
                ok=True,
                decision=GatewayDecision.ALLOWED,
                correlation_id=UUID("00000000-0000-0000-0000-000000000001"),
                data={"approvals": approvals},
            )
        except GatewayError as exc:
            return GatewayToolResponse(
                ok=False,
                decision=GatewayDecision.DENIED,
                correlation_id=UUID("00000000-0000-0000-0000-000000000001"),
                error={"code": exc.code, "message": exc.message},
            )

    def get_approval(self, auth_token: str, approval_id: UUID) -> GatewayToolResponse:
        now = self.clock()
        try:
            principal = self.authenticator.authenticate(auth_token)
            self.authorizer.authorize(principal, "approvals:approve")
            approval = self.approvals.detail(approval_id, now)
            return GatewayToolResponse(
                ok=True,
                decision=GatewayDecision.ALLOWED,
                correlation_id=approval_id,
                data={"approval": approval.model_dump(mode="json")},
            )
        except GatewayError as exc:
            return GatewayToolResponse(
                ok=False,
                decision=GatewayDecision.DENIED,
                correlation_id=approval_id,
                error={"code": exc.code, "message": exc.message},
            )

    def _metadata(self, tool_name: str) -> ToolMetadata:
        try:
            return self.registry[tool_name]
        except KeyError as exc:
            raise UnknownTool(f"Unknown tool {tool_name}.") from exc

    def _check_tool_enabled(self, metadata: ToolMetadata) -> None:
        if metadata.tool_name in self.disabled_tools or not metadata.enabled:
            raise DisabledTool(f"Tool {metadata.tool_name} is disabled.")

    def _check_tool_executable(self, metadata: ToolMetadata) -> None:
        if not metadata.executable:
            raise NonExecutableTool(f"Tool {metadata.tool_name} is not executable.")

    def _approval_for_request(
        self,
        request: GatewayToolRequest,
        metadata: ToolMetadata,
        arguments: dict[str, Any],
        now: datetime,
    ) -> ApprovalRecord | None:
        if not metadata.requires_approval:
            return None
        if request.approval_id is None:
            return None
        approval = self.approvals.get(request.approval_id, now)
        expected_hash = hash_arguments(arguments)
        expected_binding = _approval_binding_hash(
            request,
            approval.requester_id,
            metadata.tool_name,
            arguments,
        )
        if approval.tool_name != metadata.tool_name or approval.arguments != arguments:
            record_approval_replay_attempt(
                tool_name=metadata.tool_name,
                reason="arguments_mismatch",
            )
            raise MalformedArguments("Approval does not match requested tool arguments.")
        if approval.arguments_hash and approval.arguments_hash != expected_hash:
            record_approval_replay_attempt(
                tool_name=metadata.tool_name,
                reason="arguments_hash_mismatch",
            )
            raise MalformedArguments("Approval argument hash does not match requested arguments.")
        if approval.workflow_id is not None and approval.workflow_id != request.workflow_id:
            record_approval_replay_attempt(tool_name=metadata.tool_name, reason="workflow_mismatch")
            raise MalformedArguments("Approval is bound to a different workflow.")
        node_mismatch = (
            approval.workflow_node_id is not None
            and approval.workflow_node_id != request.workflow_node_id
        )
        if node_mismatch:
            record_approval_replay_attempt(tool_name=metadata.tool_name, reason="node_mismatch")
            raise MalformedArguments("Approval is bound to a different workflow node.")
        if approval.approval_binding_hash and approval.approval_binding_hash != expected_binding:
            record_approval_replay_attempt(tool_name=metadata.tool_name, reason="binding_mismatch")
            raise MalformedArguments("Approval does not match requested tool arguments.")
        if approval.status != ApprovalStatus.APPROVED:
            record_approval_replay_attempt(
                tool_name=metadata.tool_name,
                reason="status_not_approved",
            )
            raise MalformedArguments(f"Approval status is {approval.status.value}.")
        return approval

    def _trusted_domain_arguments(
        self,
        arguments: dict[str, Any],
        principal: Principal,
        metadata: ToolMetadata,
    ) -> dict[str, Any]:
        routed = dict(arguments)
        routed["actor_role"] = principal.role.value
        if metadata.requires_approval:
            routed["approval_token"] = GOVERNED_OPERATION_MARKER
        return routed

    def _dispatcher(self, metadata: ToolMetadata) -> McpToolDispatcher:
        return self._dispatchers[metadata.domain]

    def _validate_domain_arguments(
        self,
        arguments: dict[str, Any],
        principal: Principal,
        metadata: ToolMetadata,
    ) -> None:
        validation_args = self._trusted_domain_arguments(arguments, principal, metadata)
        result = self._dispatcher(metadata).validate_tool(metadata.tool_name, validation_args)
        if result.is_error:
            record_argument_validation_failure(
                tool_name=metadata.tool_name,
                reason="schema_validation_failed",
            )
            raise MalformedArguments(str(result.structured_content["error"]))

    def _enforce_timeout(self, metadata: ToolMetadata, started_at: datetime) -> None:
        elapsed_seconds = (self.clock() - started_at).total_seconds()
        if elapsed_seconds > metadata.timeout_seconds:
            raise ToolTimeout(f"Tool {metadata.tool_name} exceeded timeout.")

    def _success(
        self,
        request: GatewayToolRequest,
        principal: Principal,
        metadata: ToolMetadata,
        decision: GatewayDecision,
        data: dict[str, Any],
        *,
        approval_status: ApprovalStatus | None,
        execution_status: str,
    ) -> GatewayToolResponse:
        self.audit_log.append(
            AuditRecord(
                timestamp=self.clock(),
                actor_id=principal.principal_id,
                actor_role=principal.role,
                tool_name=metadata.tool_name,
                correlation_id=request.correlation_id,
                decision=decision,
                authorization_result="ALLOW",
                risk_level=metadata.risk_level,
                approval_status=approval_status,
                execution_status=execution_status,
                result_summary=decision.value,
                argument_hash=_argument_hash(request.arguments),
                target_resource=_target_resource(request.arguments),
            )
        )
        return GatewayToolResponse(
            ok=True,
            decision=decision,
            correlation_id=request.correlation_id,
            data={"tool_name": metadata.tool_name, **data},
        )

    def _failure(
        self,
        request: GatewayToolRequest,
        principal: Principal,
        metadata: ToolMetadata | None,
        exc: GatewayError,
    ) -> GatewayToolResponse:
        self.audit_log.append(
            AuditRecord(
                timestamp=self.clock(),
                actor_id=principal.principal_id,
                actor_role=principal.role,
                tool_name=request.tool_name,
                correlation_id=request.correlation_id,
                decision=GatewayDecision.DENIED,
                authorization_result="DENY",
                risk_level=metadata.risk_level if metadata else None,
                approval_status=None,
                execution_status="DENIED",
                result_summary=exc.code,
                argument_hash=_argument_hash(request.arguments),
                target_resource=_target_resource(request.arguments),
            )
        )
        return GatewayToolResponse(
            ok=False,
            decision=GatewayDecision.DENIED,
            correlation_id=request.correlation_id,
            data={"tool_name": request.tool_name},
            error={"code": exc.code, "message": exc.message},
        )

    def _record_tool_observability(
        self,
        response: GatewayToolResponse,
        metadata: ToolMetadata | None,
        started_perf: float,
        exc: GatewayError | None = None,
        actor: Principal | None = None,
    ) -> None:
        tool_name = metadata.tool_name if metadata else "unknown"
        domain = metadata.domain if metadata else "unknown"
        latency_seconds = time.perf_counter() - started_perf
        record_mcp_call(
            tool_name=tool_name,
            domain=domain,
            decision=response.decision.value,
            latency_seconds=latency_seconds,
        )
        if exc is not None:
            record_mcp_failure(tool_name, domain, exc.code)
            if exc.code == "permission_denied":
                record_authorization_failure(
                    tool_name=tool_name,
                    required_permission=metadata.required_permission if metadata else "unknown",
                    role=actor.role.value if actor else "unknown",
                )
        logger.info(
            "mcp.tool.completed",
            extra={
                "tool_name": tool_name,
                "domain": domain,
                "decision": response.decision.value,
                "ok": response.ok,
                "latency_ms": round(latency_seconds * 1000, 3),
                "error_code": exc.code if exc else None,
            },
        )


def _mark_idempotency_running(
    store: Any,
    principal: Principal,
    idempotency_key: str,
    now: datetime,
) -> None:
    mark_running = getattr(store, "mark_running", None)
    if callable(mark_running):
        mark_running(principal, idempotency_key, now)


def _complete_idempotency(
    store: Any,
    principal: Principal,
    idempotency_key: str,
    response: GatewayToolResponse,
    *,
    status: IdempotencyOperationStatus,
    now: datetime,
) -> None:
    complete = getattr(store, "complete", None)
    if callable(complete):
        complete(principal, idempotency_key, response, status=status, now=now)


def _strip_untrusted_model_fields(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in arguments.items()
        if key not in {"actor_role", "approval_token", "required_permission", "risk_level"}
    }


def _argument_hash(arguments: dict[str, Any]) -> str:
    encoded = json.dumps(arguments, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _approval_binding_hash(
    request: GatewayToolRequest,
    actor_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    payload = {
        "workflow_id": str(request.workflow_id) if request.workflow_id else None,
        "workflow_node_id": request.workflow_node_id,
        "tool_name": tool_name,
        "actor_id": actor_id,
        "arguments_hash": hash_arguments(arguments),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _target_resource(arguments: dict[str, Any]) -> str | None:
    for key in (
        "device_id",
        "repository",
        "run_id",
        "job_id",
        "ticket_id",
        "document_id",
        "procedure_id",
    ):
        value = arguments.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, int):
            return str(value)
    return None


def _seconds_between(started_at: datetime, completed_at: datetime) -> float:
    return max(0.0, (completed_at - started_at).total_seconds())
