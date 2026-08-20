class GatewayError(Exception):
    code = "gateway_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthenticationFailed(GatewayError):
    code = "unauthorized_user"


class UnknownTool(GatewayError):
    code = "unknown_tool"


class DisabledTool(GatewayError):
    code = "tool_disabled"


class NonExecutableTool(GatewayError):
    code = "tool_not_executable"


class PermissionDenied(GatewayError):
    code = "permission_denied"


class MalformedArguments(GatewayError):
    code = "malformed_arguments"


class ServiceUnavailable(GatewayError):
    code = "service_unavailable"


class ApprovalRequired(GatewayError):
    code = "approval_required"


class ApprovalNotFound(GatewayError):
    code = "approval_not_found"


class ExpiredApproval(GatewayError):
    code = "expired_approval"


class DuplicateOperation(GatewayError):
    code = "duplicate_operation"


class RateLimitExceeded(GatewayError):
    code = "rate_limit_exceeded"


class ApprovalDenied(GatewayError):
    code = "approval_denied"


class ToolTimeout(GatewayError):
    code = "timeout"
