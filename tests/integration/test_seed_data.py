from pathlib import Path

from alembic import command
from mcp_ops_api.db.models import (
    ApprovalModel,
    DeviceModel,
    DeviceServiceModel,
    DiagnosticRunModel,
    IncidentModel,
    PermissionModel,
    RoleModel,
    TelemetryModel,
    TicketModel,
    UserModel,
)
from mcp_ops_api.db.repositories import ApprovalRepository, DeviceRepository, TicketRepository
from mcp_ops_api.db.seed import seed_database
from sqlalchemy import Select, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import isolated_database_path
from tests.integration.test_database_migrations import _alembic_config


def test_seed_data_is_idempotent_and_populates_required_domain() -> None:
    session_factory = _migrated_session_factory(isolated_database_path("seed.db"))

    with session_factory() as session:
        first_summary = seed_database(session)
        session.commit()
        second_summary = seed_database(session)
        session.commit()

        assert first_summary == second_summary
        assert _count(session, select(func.count()).select_from(RoleModel)) == 4
        assert _count(session, select(func.count()).select_from(PermissionModel)) >= 9
        assert _count(session, select(func.count()).select_from(UserModel)) == 4
        assert _count(session, select(func.count()).select_from(DeviceModel)) == 50
        assert _count(session, select(func.count()).select_from(DeviceServiceModel)) == 200
        assert _count(session, select(func.count()).select_from(TelemetryModel)) == 300
        assert _count(session, select(func.count()).select_from(IncidentModel)) >= 4
        assert _count(session, select(func.count()).select_from(TicketModel)) >= 4
        assert _count(session, select(func.count()).select_from(DiagnosticRunModel)) >= 5


def test_seeded_relationships_support_device_investigation_workflow() -> None:
    session_factory = _migrated_session_factory(isolated_database_path("relationships.db"))

    with session_factory() as session:
        seed_database(session)
        session.commit()

    with session_factory() as session:
        devices = DeviceRepository(session)
        tickets = TicketRepository(session)
        approvals = ApprovalRepository(session)

        sim_014 = devices.get_by_device_id("SIM-014")
        assert sim_014 is not None
        assert sim_014.status == "CRITICAL"
        assert len(sim_014.services) == 4
        assert any(service.status == "CRASHED" for service in sim_014.services)
        assert len(devices.latest_telemetry(sim_014, limit=6)) == 6
        assert tickets.for_device(sim_014.id)

        pending = approvals.pending()
        assert len(pending) == 1
        assert pending[0].tool_name == "restart_service"
        assert pending[0].target_device_id == sim_014.id


def test_approval_and_ticket_foreign_keys_reference_seeded_users_and_devices(
) -> None:
    session_factory = _migrated_session_factory(isolated_database_path("foreign-keys.db"))

    with session_factory() as session:
        seed_database(session)
        session.commit()

        approval = session.scalars(select(ApprovalModel)).one()
        assert approval.requested_by_user.email == "engineer@example.internal"
        assert approval.target_device is not None
        assert approval.target_device.device_id == "SIM-014"

        ticket = session.scalars(
            select(TicketModel).where(TicketModel.device_id == approval.target_device_id)
        ).first()
        assert ticket is not None
        assert ticket.created_by_user.email == "engineer@example.internal"
        assert ticket.incident is not None


def _migrated_session_factory(database_path: Path) -> sessionmaker[Session]:
    database_url = f"sqlite:///{database_path}"
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _count(session: Session, statement: Select[tuple[int]]) -> int:
    return session.scalar(statement) or 0
