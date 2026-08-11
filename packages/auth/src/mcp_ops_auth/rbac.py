from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    ENGINEER = "ENGINEER"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class Permission(StrEnum):
    DEVICES_READ = "devices:read"
    DEVICES_DIAGNOSE = "devices:diagnose"
    DEVICES_OPERATE = "devices:operate"
    TICKETS_READ = "tickets:read"
    TICKETS_CREATE = "tickets:create"
    TICKETS_UPDATE = "tickets:update"
    KNOWLEDGE_READ = "knowledge:read"
    CICD_READ = "cicd:read"
    CICD_EXECUTE = "cicd:execute"
    REPOSITORIES_READ = "repositories:read"
    DEPLOYMENTS_READ = "deployments:read"
    DEPLOYMENTS_OPERATE = "deployments:operate"
    APPROVALS_APPROVE = "approvals:approve"
    AUDIT_READ = "audit:read"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(
        {
            Permission.DEVICES_READ,
            Permission.KNOWLEDGE_READ,
            Permission.TICKETS_READ,
            Permission.CICD_READ,
            Permission.REPOSITORIES_READ,
            Permission.DEPLOYMENTS_READ,
        }
    ),
    Role.ENGINEER: frozenset(
        {
            Permission.DEVICES_READ,
            Permission.KNOWLEDGE_READ,
            Permission.TICKETS_READ,
            Permission.DEVICES_DIAGNOSE,
            Permission.TICKETS_CREATE,
            Permission.TICKETS_UPDATE,
            Permission.CICD_READ,
            Permission.CICD_EXECUTE,
            Permission.REPOSITORIES_READ,
            Permission.DEPLOYMENTS_READ,
        }
    ),
    Role.OPERATOR: frozenset(
        {
            Permission.DEVICES_READ,
            Permission.KNOWLEDGE_READ,
            Permission.TICKETS_READ,
            Permission.DEVICES_DIAGNOSE,
            Permission.TICKETS_CREATE,
            Permission.TICKETS_UPDATE,
            Permission.DEVICES_OPERATE,
            Permission.CICD_READ,
            Permission.CICD_EXECUTE,
            Permission.REPOSITORIES_READ,
            Permission.DEPLOYMENTS_READ,
            Permission.DEPLOYMENTS_OPERATE,
        }
    ),
    Role.ADMIN: frozenset(Permission),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
