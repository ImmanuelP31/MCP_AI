from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from mcp_ops_auth.rbac import ROLE_PERMISSIONS, Permission, Role
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from mcp_ops_api.db.models import (
    AlertModel,
    ApprovalModel,
    DeviceModel,
    DeviceServiceModel,
    DiagnosticRunModel,
    IncidentEventModel,
    IncidentModel,
    KnowledgeDocumentModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    TelemetryModel,
    TicketModel,
    UserModel,
    UserRoleModel,
)

SEED_NAMESPACE = uuid.UUID("4e4883bb-37e2-5f97-9835-f2f9528a3ea5")


@dataclass(frozen=True)
class SeedSummary:
    roles: int
    permissions: int
    users: int
    devices: int
    telemetry_points: int
    incidents: int
    tickets: int
    diagnostic_runs: int


def stable_uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, name)


def seed_database(session: Session) -> SeedSummary:
    seeded_at = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

    permissions = _seed_permissions(session)
    roles = _seed_roles(session, permissions)
    users = _seed_users(session, roles)
    devices = _seed_devices(session, seeded_at)
    _seed_knowledge_documents(session)
    incidents = _seed_incidents(session, devices, seeded_at)
    _seed_alerts(session, devices, incidents, seeded_at)
    diagnostic_runs = _seed_diagnostic_runs(session, devices, users, seeded_at)
    tickets = _seed_tickets(session, devices, incidents, users)
    _seed_approvals(session, devices, users, seeded_at)
    session.flush()

    return SeedSummary(
        roles=len(roles),
        permissions=len(permissions),
        users=len(users),
        devices=len(devices),
        telemetry_points=len(devices) * 6,
        incidents=len(incidents),
        tickets=len(tickets),
        diagnostic_runs=len(diagnostic_runs),
    )


def _seed_permissions(session: Session) -> dict[Permission, PermissionModel]:
    descriptions = {
        Permission.DEVICES_READ: "Read simulator device inventory, status, and telemetry.",
        Permission.DEVICES_DIAGNOSE: "Run bounded diagnostic checks against simulator devices.",
        Permission.DEVICES_OPERATE: "Request governed operations against simulator devices.",
        Permission.TICKETS_READ: "Read engineering maintenance tickets.",
        Permission.TICKETS_CREATE: "Create engineering maintenance tickets.",
        Permission.TICKETS_UPDATE: "Update engineering maintenance tickets.",
        Permission.KNOWLEDGE_READ: "Read engineering knowledge base documents.",
        Permission.CICD_READ: "Read CI/CD workflow runs, jobs, status, and logs.",
        Permission.CICD_EXECUTE: "Request governed CI/CD workflow execution.",
        Permission.REPOSITORIES_READ: "Read repository commits, diffs, and pull request metadata.",
        Permission.DEPLOYMENTS_READ: "Read deployment state and rollout metadata.",
        Permission.DEPLOYMENTS_OPERATE: "Request governed deployment operations.",
        Permission.APPROVALS_APPROVE: "Approve high-risk operation requests.",
        Permission.AUDIT_READ: "Read audit events and tool execution history.",
    }
    return {
        permission: _get_or_create(
            session,
            PermissionModel,
            PermissionModel.name == permission.value,
            id=stable_uuid(f"permission:{permission.value}"),
            name=permission.value,
            description=descriptions[permission],
        )
        for permission in Permission
    }


def _seed_roles(
    session: Session, permissions: dict[Permission, PermissionModel]
) -> dict[Role, RoleModel]:
    role_descriptions = {
        Role.ADMIN: "Platform administrator with all permissions.",
        Role.ENGINEER: "Engineer who can investigate devices and manage tickets.",
        Role.OPERATOR: "Operations engineer who can request governed device operations.",
        Role.VIEWER: "Read-only user for fleet, ticket, and knowledge visibility.",
    }
    roles = {
        role: _get_or_create(
            session,
            RoleModel,
            RoleModel.name == role.value,
            id=stable_uuid(f"role:{role.value}"),
            name=role.value,
            description=role_descriptions[role],
        )
        for role in Role
    }
    session.flush()
    for role, granted_permissions in ROLE_PERMISSIONS.items():
        for permission in granted_permissions:
            _get_or_create(
                session,
                RolePermissionModel,
                (RolePermissionModel.role_id == roles[role].id)
                & (RolePermissionModel.permission_id == permissions[permission].id),
                id=stable_uuid(f"role-permission:{role.value}:{permission.value}"),
                role_id=roles[role].id,
                permission_id=permissions[permission].id,
            )
    return roles


def _seed_users(session: Session, roles: dict[Role, RoleModel]) -> dict[str, UserModel]:
    user_specs = [
        ("admin@example.internal", "Avery Admin", Role.ADMIN),
        ("engineer@example.internal", "Elliot Engineer", Role.ENGINEER),
        ("operator@example.internal", "Omar Operator", Role.OPERATOR),
        ("viewer@example.internal", "Vera Viewer", Role.VIEWER),
    ]
    users: dict[str, UserModel] = {}
    for email, display_name, role in user_specs:
        user = _get_or_create(
            session,
            UserModel,
            UserModel.email == email,
            id=stable_uuid(f"user:{email}"),
            email=email,
            display_name=display_name,
            status="ACTIVE",
        )
        users[email] = user
        session.flush()
        _get_or_create(
            session,
            UserRoleModel,
            (UserRoleModel.user_id == user.id) & (UserRoleModel.role_id == roles[role].id),
            id=stable_uuid(f"user-role:{email}:{role.value}"),
            user_id=user.id,
            role_id=roles[role].id,
        )
    return users


def _seed_devices(session: Session, seeded_at: datetime) -> list[DeviceModel]:
    devices = []
    service_names = ["telemetry-agent", "control-plane", "sensor-ingestor", "diagnostic-runner"]
    models = ["SIM-X100", "SIM-X200", "SIM-RUGGED"]
    sites = ["Bangalore Lab", "Pune Integration", "Austin HIL", "Munich Validation"]
    for number in range(1, 51):
        device_key = f"SIM-{number:03d}"
        status, health_score = _device_health(number)
        device = _get_or_create(
            session,
            DeviceModel,
            DeviceModel.device_id == device_key,
            id=stable_uuid(f"device:{device_key}"),
            device_id=device_key,
            serial_number=f"SN-MCP-{number:05d}",
            model=models[number % len(models)],
            location=f"Rack {((number - 1) % 10) + 1}, Slot {((number - 1) % 5) + 1}",
            site=sites[number % len(sites)],
            firmware_version=f"2026.{(number % 4) + 1}.{(number % 9) + 1}",
            status=status,
            health_score=Decimal(health_score),
            last_seen=seeded_at - timedelta(minutes=number % 17),
        )
        devices.append(device)
        session.flush()
        _seed_device_services(session, device, service_names, number, seeded_at)
        _seed_telemetry(session, device, number, seeded_at)
    return devices


def _seed_device_services(
    session: Session,
    device: DeviceModel,
    service_names: list[str],
    number: int,
    seeded_at: datetime,
) -> None:
    for index, service_name in enumerate(service_names):
        status = "RUNNING"
        if number == 14 and service_name == "sensor-ingestor":
            status = "CRASHED"
        elif number % 11 == 0 and service_name == "telemetry-agent":
            status = "DEGRADED"
        elif number % 17 == 0 and service_name == "diagnostic-runner":
            status = "STOPPED"

        _get_or_create(
            session,
            DeviceServiceModel,
            (DeviceServiceModel.device_id == device.id)
            & (DeviceServiceModel.service_name == service_name),
            id=stable_uuid(f"device-service:{device.device_id}:{service_name}"),
            device_id=device.id,
            service_name=service_name,
            status=status,
            service_version=f"v{2 + index}.{number % 10}.{index}",
            last_restart_at=seeded_at - timedelta(hours=number + index),
        )


def _seed_telemetry(
    session: Session,
    device: DeviceModel,
    number: int,
    seeded_at: datetime,
) -> None:
    for offset in range(6):
        timestamp = seeded_at - timedelta(minutes=5 * offset)
        if number == 14:
            cpu = Decimal("96.40") - offset
            memory = Decimal("91.20") - Decimal(offset) / Decimal("2")
            latency = Decimal("420.00") - offset * Decimal("7.50")
            packet_loss = Decimal("12.50") - Decimal(offset) / Decimal("3")
            temperature = Decimal("82.00") - Decimal(offset) / Decimal("2")
            disk = Decimal("88.00") - Decimal(offset)
        else:
            cpu = Decimal(25 + (number * 3 + offset) % 45)
            memory = Decimal(35 + (number * 5 + offset) % 35)
            latency = Decimal(25 + (number * 7 + offset * 3) % 100)
            packet_loss = Decimal((number + offset) % 5) / Decimal("10")
            temperature = Decimal(38 + (number + offset) % 18)
            disk = Decimal(45 + (number + offset * 2) % 30)

        _get_or_create(
            session,
            TelemetryModel,
            (TelemetryModel.device_id == device.id) & (TelemetryModel.timestamp == timestamp),
            id=stable_uuid(f"telemetry:{device.device_id}:{timestamp.isoformat()}"),
            device_id=device.id,
            timestamp=timestamp,
            cpu_percent=cpu,
            memory_percent=memory,
            network_latency_ms=latency,
            packet_loss_percent=packet_loss,
            temperature_c=temperature,
            uptime_seconds=86400 + number * 3600 + offset * 60,
            disk_percent=disk,
        )


def _seed_incidents(
    session: Session, devices: list[DeviceModel], seeded_at: datetime
) -> list[IncidentModel]:
    incident_specs = [
        (
            "SIM-014",
            "Sensor ingestor crash on SIM-014",
            "CRITICAL",
            "INVESTIGATING",
            "E-SENSOR-INIT",
        ),
        ("SIM-022", "Telemetry agent degradation", "HIGH", "OPEN", "E-TELEM-DELAY"),
        ("SIM-033", "High memory pressure detected", "MEDIUM", "MITIGATED", "E-MEM-PRESSURE"),
        ("SIM-044", "Network packet loss threshold exceeded", "HIGH", "RESOLVED", "E-NET-LOSS"),
    ]
    device_by_key = {device.device_id: device for device in devices}
    incidents = []
    for index, (device_key, title, severity, status, error_code) in enumerate(incident_specs):
        device = device_by_key[device_key]
        incident = _get_or_create(
            session,
            IncidentModel,
            IncidentModel.title == title,
            id=stable_uuid(f"incident:{title}"),
            device_id=device.id,
            title=title,
            description=f"{title}; correlated error code {error_code}.",
            severity=severity,
            status=status,
            resolved_at=None if status != "RESOLVED" else seeded_at - timedelta(days=2),
            created_at=seeded_at - timedelta(days=index + 1),
        )
        incidents.append(incident)
        session.flush()
        _get_or_create(
            session,
            IncidentEventModel,
            (IncidentEventModel.incident_id == incident.id)
            & (IncidentEventModel.event_type == "alert_correlated"),
            id=stable_uuid(f"incident-event:{title}:alert"),
            incident_id=incident.id,
            event_type="alert_correlated",
            timestamp=seeded_at - timedelta(days=index + 1, minutes=3),
            payload={"error_code": error_code, "device_id": device_key},
        )
    return incidents


def _seed_alerts(
    session: Session,
    devices: list[DeviceModel],
    incidents: list[IncidentModel],
    seeded_at: datetime,
) -> None:
    device_by_id = {device.id: device for device in devices}
    for incident in incidents:
        device = device_by_id[incident.device_id]
        _get_or_create(
            session,
            AlertModel,
            (AlertModel.device_id == device.id) & (AlertModel.error_code == "E-SEED-DEMO"),
            id=stable_uuid(f"alert:{device.device_id}:{incident.title}"),
            device_id=device.id,
            severity="CRITICAL" if incident.severity == "CRITICAL" else "WARNING",
            message=f"{incident.title} requires engineering review.",
            error_code="E-SEED-DEMO",
            timestamp=seeded_at - timedelta(minutes=17),
        )


def _seed_diagnostic_runs(
    session: Session,
    devices: list[DeviceModel],
    users: dict[str, UserModel],
    seeded_at: datetime,
) -> list[DiagnosticRunModel]:
    engineer = users["engineer@example.internal"]
    selected_devices = [
        device
        for device in devices
        if device.device_id in {"SIM-014", "SIM-022", "SIM-033", "SIM-044", "SIM-050"}
    ]
    runs = []
    for index, device in enumerate(selected_devices):
        run = _get_or_create(
            session,
            DiagnosticRunModel,
            (DiagnosticRunModel.device_id == device.id)
            & (DiagnosticRunModel.started_at == seeded_at - timedelta(hours=index + 2)),
            id=stable_uuid(f"diagnostic:{device.device_id}:{index}"),
            device_id=device.id,
            requested_by_id=engineer.id,
            status="SUCCEEDED" if device.device_id != "SIM-014" else "FAILED",
            started_at=seeded_at - timedelta(hours=index + 2),
            completed_at=seeded_at - timedelta(hours=index + 2, minutes=-4),
            summary=f"Historical diagnostic run for {device.device_id}.",
            evidence={"checks": ["service_health", "resource_usage", "recent_errors"]},
        )
        runs.append(run)
    return runs


def _seed_tickets(
    session: Session,
    devices: list[DeviceModel],
    incidents: list[IncidentModel],
    users: dict[str, UserModel],
) -> list[TicketModel]:
    engineer = users["engineer@example.internal"]
    operator = users["operator@example.internal"]
    incidents_by_device = {incident.device_id: incident for incident in incidents}
    tickets = []
    for device in devices:
        if device.device_id not in {"SIM-014", "SIM-022", "SIM-033", "SIM-044"}:
            continue
        incident = incidents_by_device[device.id]
        ticket = _get_or_create(
            session,
            TicketModel,
            TicketModel.title == f"Maintenance review for {device.device_id}",
            id=stable_uuid(f"ticket:{device.device_id}"),
            title=f"Maintenance review for {device.device_id}",
            description=f"Investigate and remediate {incident.title}.",
            device_id=device.id,
            priority=incident.severity,
            status="OPEN" if incident.status != "RESOLVED" else "RESOLVED",
            assignee_id=operator.id,
            team="Simulator Operations",
            created_by_id=engineer.id,
            related_incident_id=incident.id,
            diagnostic_evidence={"incident_id": str(incident.id), "source": "seed"},
        )
        tickets.append(ticket)
    return tickets


def _seed_approvals(
    session: Session,
    devices: list[DeviceModel],
    users: dict[str, UserModel],
    seeded_at: datetime,
) -> None:
    sim_014 = next(device for device in devices if device.device_id == "SIM-014")
    engineer = users["engineer@example.internal"]
    _get_or_create(
        session,
        ApprovalModel,
        ApprovalModel.request_id == stable_uuid("approval-request:sim-014-restart-service"),
        id=stable_uuid("approval:sim-014-restart-service"),
        request_id=stable_uuid("approval-request:sim-014-restart-service"),
        requested_by_id=engineer.id,
        tool_name="restart_service",
        arguments={"device_id": "SIM-014", "service_name": "sensor-ingestor"},
        target_device_id=sim_014.id,
        risk_level="HIGH",
        reason="Sensor ingestor is crashed and blocking telemetry processing.",
        state="PENDING",
        created_at=seeded_at,
        expires_at=seeded_at + timedelta(hours=1),
    )


def _seed_knowledge_documents(session: Session) -> None:
    documents = [
        (
            "kb-sensor-init",
            "Sensor Initialization Failure SOP",
            "TROUBLESHOOTING",
            ["sensor", "SIM-014", "E-SENSOR-INIT"],
        ),
        (
            "kb-telemetry-delay",
            "Telemetry Delay Investigation Guide",
            "CONFIGURATION_GUIDE",
            ["telemetry", "network", "E-TELEM-DELAY"],
        ),
        (
            "kb-service-restart",
            "Governed Service Restart Procedure",
            "SOP",
            ["approval", "restart_service", "operations"],
        ),
    ]
    for external_id, title, document_type, tags in documents:
        _get_or_create(
            session,
            KnowledgeDocumentModel,
            KnowledgeDocumentModel.external_id == external_id,
            id=stable_uuid(f"knowledge:{external_id}"),
            external_id=external_id,
            title=title,
            document_type=document_type,
            source="seed",
            content=f"{title}: seeded engineering guidance for demo workflows.",
            tags=tags,
        )


def _device_health(number: int) -> tuple[str, str]:
    if number == 14:
        return "CRITICAL", "18.50"
    if number % 17 == 0:
        return "OFFLINE", "0.00"
    if number % 11 == 0 or number % 7 == 0:
        return "WARNING", "64.00"
    return "HEALTHY", "96.00"


def _get_or_create[ModelT](
    session: Session,
    model_type: type[ModelT],
    predicate: ColumnElement[bool],
    **values: object,
) -> ModelT:
    existing = session.scalar(select(model_type).where(predicate))
    if existing is not None:
        return existing
    model = model_type(**values)
    session.add(model)
    return model
