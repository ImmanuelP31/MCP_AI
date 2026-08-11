CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL
);

CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL
);

CREATE TABLE user_roles (
    user_id UUID NOT NULL REFERENCES users(id),
    role_id UUID NOT NULL REFERENCES roles(id),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE role_permissions (
    role_id UUID NOT NULL REFERENCES roles(id),
    permission_id UUID NOT NULL REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id TEXT NOT NULL UNIQUE,
    serial_number TEXT NOT NULL UNIQUE,
    model TEXT NOT NULL,
    location TEXT NOT NULL,
    site TEXT NOT NULL,
    firmware_version TEXT NOT NULL,
    status TEXT NOT NULL,
    health_score NUMERIC(5,2) NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_devices_status ON devices(status);

CREATE TABLE device_services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    service_name TEXT NOT NULL,
    status TEXT NOT NULL,
    version TEXT NOT NULL,
    last_restart_at TIMESTAMPTZ,
    UNIQUE (device_id, service_name)
);

CREATE TABLE telemetry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    timestamp TIMESTAMPTZ NOT NULL,
    cpu_percent NUMERIC(5,2) NOT NULL,
    memory_percent NUMERIC(5,2) NOT NULL,
    network_latency_ms NUMERIC(8,2) NOT NULL,
    packet_loss_percent NUMERIC(5,2) NOT NULL,
    temperature_c NUMERIC(5,2) NOT NULL,
    uptime_seconds BIGINT NOT NULL,
    disk_percent NUMERIC(5,2) NOT NULL
);

CREATE INDEX idx_telemetry_device_timestamp ON telemetry(device_id, timestamp DESC);

CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    error_code TEXT,
    timestamp TIMESTAMPTZ NOT NULL,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES users(id)
);

CREATE INDEX idx_alerts_device_timestamp ON alerts(device_id, timestamp DESC);

CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_incidents_device_created_at ON incidents(device_id, created_at DESC);

CREATE TABLE incident_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id),
    event_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE diagnostic_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    requested_by UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    summary TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    device_id UUID REFERENCES devices(id),
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    assignee UUID REFERENCES users(id),
    team TEXT NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    related_incident UUID REFERENCES incidents(id),
    diagnostic_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL UNIQUE,
    requested_by UUID NOT NULL REFERENCES users(id),
    tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL,
    target_device UUID REFERENCES devices(id),
    risk_level TEXT NOT NULL,
    reason TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    execution_result JSONB
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    actor_id UUID REFERENCES users(id),
    actor_role TEXT NOT NULL,
    request_id UUID,
    correlation_id UUID NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_hash TEXT NOT NULL,
    target_resource TEXT,
    device_id UUID REFERENCES devices(id),
    risk_level TEXT NOT NULL,
    authorization_result TEXT NOT NULL,
    approval_required BOOLEAN NOT NULL,
    approval_status TEXT,
    execution_status TEXT NOT NULL,
    result_summary TEXT,
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX idx_audit_logs_actor_timestamp ON audit_logs(actor_id, timestamp DESC);
CREATE INDEX idx_audit_logs_device_timestamp ON audit_logs(device_id, timestamp DESC);

CREATE TABLE tool_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL,
    correlation_id UUID NOT NULL,
    tool_name TEXT NOT NULL,
    actor_id UUID REFERENCES users(id),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    latency_ms INTEGER,
    error_code TEXT,
    result_summary TEXT
);

CREATE INDEX idx_tool_executions_tool_timestamp ON tool_executions(tool_name, started_at DESC);

CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    document_type TEXT NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operation_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL UNIQUE,
    approval_id UUID REFERENCES approvals(id),
    tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL,
    target_device UUID REFERENCES devices(id),
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at TIMESTAMPTZ
);

