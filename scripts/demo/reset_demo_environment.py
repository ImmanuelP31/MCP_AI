# ruff: noqa: E402

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for source_root in [
    ROOT / "packages" / "auth" / "src",
    ROOT / "packages" / "common" / "src",
    ROOT / "packages" / "mcp" / "src",
    ROOT / "packages" / "observability" / "src",
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

from mcp_ops_simulator.clock import DEFAULT_TEST_TIME
from mcp_ops_simulator.registry import DeviceRegistry


def main() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)
    devices = registry.list_devices()
    distribution = Counter(device.status.value for device in devices)
    sim_014 = registry.clear_scenario("SIM-014", DEFAULT_TEST_TIME)

    print(
        json.dumps(
            {
                "demo_environment": "reset",
                "timestamp": DEFAULT_TEST_TIME.isoformat(),
                "device_count": len(devices),
                "distribution": {
                    "HEALTHY": distribution.get("HEALTHY", 0),
                    "WARNING": distribution.get("WARNING", 0),
                    "CRITICAL": distribution.get("CRITICAL", 0),
                    "OFFLINE": distribution.get("OFFLINE", 0),
                },
                "sim_014": {
                    "status": sim_014.status.value,
                    "health_score": sim_014.health_score,
                    "active_scenario": sim_014.active_scenario,
                    "services": {
                        name: service.state.value
                        for name, service in sorted(sim_014.services.items())
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
