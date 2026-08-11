CREATE TABLE IF NOT EXISTS gateway_approvals (
  approval_id uuid PRIMARY KEY,
  requester_id varchar(160) NOT NULL,
  requester_type varchar(32) NOT NULL,
  tool_name varchar(128) NOT NULL,
  arguments jsonb NOT NULL DEFAULT '{}'::jsonb,
  risk_level varchar(32) NOT NULL,
  status varchar(32) NOT NULL CHECK (
    status IN ('PENDING','APPROVED','REJECTED','EXPIRED','EXECUTED','FAILED')
  ),
  created_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  approved_by varchar(160),
  approved_at timestamptz,
  rejected_by varchar(160),
  rejected_at timestamptz,
  executed_at timestamptz,
  failure_reason varchar(500),
  execution_result jsonb,
  version integer NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_gateway_approvals_requester_id ON gateway_approvals(requester_id);
CREATE INDEX IF NOT EXISTS ix_gateway_approvals_tool_name ON gateway_approvals(tool_name);
CREATE INDEX IF NOT EXISTS ix_gateway_approvals_status ON gateway_approvals(status);
CREATE INDEX IF NOT EXISTS ix_gateway_approvals_expires_at ON gateway_approvals(expires_at);

CREATE TABLE IF NOT EXISTS gateway_approval_events (
  event_id uuid PRIMARY KEY,
  approval_id uuid NOT NULL,
  event_type varchar(128) NOT NULL,
  timestamp timestamptz NOT NULL,
  actor_id varchar(160) NOT NULL,
  status varchar(32) NOT NULL,
  tool_name varchar(128) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_gateway_approval_events_approval_id
  ON gateway_approval_events(approval_id);

CREATE TABLE IF NOT EXISTS gateway_audit_records (
  id bigserial PRIMARY KEY,
  timestamp timestamptz NOT NULL,
  actor_id varchar(160) NOT NULL,
  actor_role varchar(64) NOT NULL,
  tool_name varchar(128) NOT NULL,
  correlation_id uuid NOT NULL,
  decision varchar(32) NOT NULL,
  authorization_result varchar(32) NOT NULL,
  risk_level varchar(32),
  approval_status varchar(32),
  execution_status varchar(64) NOT NULL,
  result_summary varchar(500) NOT NULL,
  argument_hash varchar(128),
  target_resource varchar(240)
);

CREATE INDEX IF NOT EXISTS ix_gateway_audit_records_actor_id ON gateway_audit_records(actor_id);
CREATE INDEX IF NOT EXISTS ix_gateway_audit_records_tool_name ON gateway_audit_records(tool_name);
CREATE INDEX IF NOT EXISTS ix_gateway_audit_records_correlation_id
  ON gateway_audit_records(correlation_id);
CREATE INDEX IF NOT EXISTS ix_gateway_audit_records_target_resource
  ON gateway_audit_records(target_resource);

CREATE TABLE IF NOT EXISTS gateway_idempotency_keys (
  principal_id varchar(160) NOT NULL,
  idempotency_key varchar(160) NOT NULL,
  created_at timestamptz NOT NULL,
  PRIMARY KEY (principal_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS gateway_rate_limit_calls (
  id bigserial PRIMARY KEY,
  principal_id varchar(160) NOT NULL,
  tool_name varchar(128) NOT NULL,
  called_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_gateway_rate_limit_calls_principal_id
  ON gateway_rate_limit_calls(principal_id);
CREATE INDEX IF NOT EXISTS ix_gateway_rate_limit_calls_tool_name
  ON gateway_rate_limit_calls(tool_name);
CREATE INDEX IF NOT EXISTS ix_gateway_rate_limit_calls_called_at
  ON gateway_rate_limit_calls(called_at);
