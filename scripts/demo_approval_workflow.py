from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
for source_root in [
    ROOT / "packages" / "auth" / "src",
    ROOT / "packages" / "mcp" / "src",
    ROOT / "packages" / "policy" / "src",
    ROOT / "packages" / "schemas" / "src",
    ROOT / "services" / "device-mcp" / "src",
    ROOT / "services" / "diagnostics-mcp" / "src",
    ROOT / "services" / "knowledge-mcp" / "src",
    ROOT / "services" / "mcp-gateway" / "src",
    ROOT / "services" / "simulator-gateway" / "src",
    ROOT / "services" / "ticket-mcp" / "src",
]:
    sys.path.insert(0, str(source_root))

from mcp_ops_mcp_gateway.models import GatewayToolRequest  # noqa: E402
from mcp_ops_mcp_gateway.service import McpGateway  # noqa: E402


def main() -> None:
    gateway = McpGateway()

    pending = gateway.call_tool(
        GatewayToolRequest(
            auth_token="operator-token",  # noqa: S106  # nosec B106 - deterministic demo token.
            tool_name="restart_service",
            arguments={
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Demo: recover crashed service after diagnostics.",
            },
            idempotency_key="demo-restart-service-request",
        )
    )
    approval_id = UUID(str(pending.data["approval_id"]))
    print(f"1. requested restart_service: {pending.decision.value}")
    print(f"2. approval status: {pending.data['approval_status']}")

    approval = gateway.approve_operation("admin-token", approval_id)
    print(f"3. approved by: {approval.data['approved_by']}")

    execution = gateway.call_tool(
        GatewayToolRequest(
            auth_token="operator-token",  # noqa: S106  # nosec B106 - deterministic demo token.
            tool_name="restart_service",
            arguments={
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Demo: recover crashed service after diagnostics.",
            },
            approval_id=approval_id,
            idempotency_key="demo-restart-service-execute",
        )
    )
    result = execution.data["tool_result"]["data"]
    print(f"4. executed operation: {result['operation']}")

    services = gateway.call_tool(
        GatewayToolRequest(
            auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic demo token.
            tool_name="get_device_services",
            arguments={"device_id": "SIM-014"},
            idempotency_key="demo-read-services",
        )
    )
    service = next(
        item
        for item in services.data["tool_result"]["data"]["services"]
        if item["name"] == "sensor-ingestor"
    )
    print(f"5. sensor-ingestor state: {service['state']}")
    print(f"6. audit events recorded: {len(gateway.audit_log.records)}")


if __name__ == "__main__":
    main()
