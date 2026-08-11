from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine.reflection import Inspector

from tests.conftest import isolated_database_path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TABLES = {
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "devices",
    "device_services",
    "telemetry",
    "alerts",
    "incidents",
    "incident_events",
    "diagnostic_runs",
    "tickets",
    "approvals",
    "audit_logs",
    "tool_executions",
    "knowledge_documents",
    "operation_requests",
    "workflows",
    "workflow_nodes",
    "workflow_edges",
}


def test_alembic_migration_builds_domain_schema_from_empty_database() -> None:
    database_url = f"sqlite:///{isolated_database_path('migrations.db')}"
    alembic_config = _alembic_config(database_url)

    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))

    devices_columns = {column["name"] for column in inspector.get_columns("devices")}
    assert {"id", "version", "created_at", "updated_at", "device_id", "status"}.issubset(
        devices_columns
    )


def test_alembic_upgrade_head_can_be_applied_repeatedly() -> None:
    database_url = f"sqlite:///{isolated_database_path('repeatable.db')}"
    alembic_config = _alembic_config(database_url)

    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()).issuperset(EXPECTED_TABLES)


def test_high_volume_indexes_exist_after_migration() -> None:
    database_url = f"sqlite:///{isolated_database_path('indexes.db')}"
    command.upgrade(_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)

    assert _index_exists(inspector, "devices", "idx_devices_status")
    assert _index_exists(inspector, "telemetry", "idx_telemetry_device_timestamp")
    assert _index_exists(inspector, "alerts", "idx_alerts_device_timestamp")
    assert _index_exists(inspector, "incidents", "idx_incidents_device_created_at")
    assert _index_exists(inspector, "audit_logs", "idx_audit_logs_actor_timestamp")
    assert _index_exists(inspector, "audit_logs", "idx_audit_logs_device_timestamp")
    assert _index_exists(inspector, "tool_executions", "idx_tool_executions_tool_timestamp")


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "apps" / "api" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _index_exists(inspector: Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))
