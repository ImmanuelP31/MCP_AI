class McpDomainError(Exception):
    code = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DeviceNotFound(McpDomainError):
    code = "device_not_found"


class TicketNotFound(McpDomainError):
    code = "ticket_not_found"


class DocumentNotFound(McpDomainError):
    code = "document_not_found"


class InvalidConfiguration(McpDomainError):
    code = "validation_error"


class PermissionDenied(McpDomainError):
    code = "permission_denied"


class ToolDisabled(McpDomainError):
    code = "tool_disabled"


class ServiceUnavailable(McpDomainError):
    code = "service_unavailable"


class ToolTimeout(McpDomainError):
    code = "timeout"
