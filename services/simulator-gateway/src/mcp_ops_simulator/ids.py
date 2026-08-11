import uuid
from datetime import datetime

SIMULATOR_NAMESPACE = uuid.UUID("0e19a9c4-901d-5f81-a113-d7f90a17c3a8")


def deterministic_uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(SIMULATOR_NAMESPACE, name)


def telemetry_id(device_id: str, timestamp: datetime) -> uuid.UUID:
    return deterministic_uuid(f"telemetry:{device_id}:{timestamp.isoformat()}")


def event_id(topic: str, device_id: str, timestamp: datetime) -> uuid.UUID:
    return deterministic_uuid(f"event:{topic}:{device_id}:{timestamp.isoformat()}")
