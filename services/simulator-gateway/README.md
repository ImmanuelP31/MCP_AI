# Simulator Gateway

Produces deterministic simulator devices, health states, telemetry, alerts, and failure
scenarios. The gateway is modeled as an external engineering system: clients activate
scenarios and consume generated domain events instead of directly mutating platform tables.
Telemetry is emitted through the `EventPublisher` boundary; tests use the in-memory bus, and
runtime wiring can use the Kafka adapter.

Useful local endpoints:

- `GET /simulator/devices`
- `GET /simulator/devices/{device_id}/telemetry`
- `POST /simulator/scenarios/{device_id}/{scenario}`
- `POST /simulator/telemetry/publish`
- `POST /simulator/telemetry/process`

Supported scenarios:

- `service-crash`
- `cpu-saturation`
- `memory-pressure`
- `packet-loss`
- `network-timeout`
- `sensor-initialization-failure`
- `telemetry-delay`
- `disk-capacity-warning`
