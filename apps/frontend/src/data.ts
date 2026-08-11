export type Role = "VIEWER" | "ENGINEER" | "OPERATOR" | "ADMIN";
export type DeviceStatus = "HEALTHY" | "WARNING" | "CRITICAL" | "OFFLINE";
export type RiskLevel = "READ_ONLY" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "EXECUTED";
export type ServiceState = "RUNNING" | "DEGRADED" | "CRASHED" | "STOPPED";

export interface TelemetryPoint {
  timestamp: string;
  cpu: number;
  memory: number;
  temperature: number;
  latency: number;
  packetLoss: number;
  disk: number;
}

export interface DeviceService {
  name: string;
  state: ServiceState;
  version: string;
  lastRestart: string;
}

export interface Device {
  id: string;
  model: string;
  site: string;
  location: string;
  status: DeviceStatus;
  healthScore: number;
  firmware: string;
  lastSeen: string;
  uptimeHours: number;
  services: DeviceService[];
  telemetry: TelemetryPoint[];
  configuration: Record<string, string | number | boolean>;
}

export interface Incident {
  id: string;
  deviceId: string;
  title: string;
  severity: "WARNING" | "CRITICAL";
  status: "OPEN" | "INVESTIGATING" | "MITIGATED";
  owner: string;
  createdAt: string;
}

export interface Ticket {
  id: string;
  deviceId: string;
  title: string;
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  status: "OPEN" | "IN_PROGRESS" | "BLOCKED" | "RESOLVED";
  assignee: string;
  updatedAt: string;
}

export interface Approval {
  id: string;
  operation: string;
  deviceId: string;
  requestedBy: string;
  risk: RiskLevel;
  reason: string;
  requestedAt: string;
  expiresAt: string;
  status: ApprovalStatus;
}

export interface ToolMetadata {
  name: string;
  domain: string;
  description: string;
  risk: RiskLevel;
  permission: string;
  requiresApproval: boolean;
  enabled: boolean;
}

export interface AuditEntry {
  id: string;
  user: string;
  deviceId: string;
  tool: string;
  risk: RiskLevel;
  status: "ALLOW" | "DENY" | "PENDING_APPROVAL";
  timestamp: string;
  summary: string;
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  type: string;
  version: string;
  model: string;
  tags: string[];
  updatedAt: string;
  excerpt: string;
}

export interface DiagnosticReport {
  id: string;
  deviceId: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  cause: string;
  confidence: number;
  evidence: string[];
  references: string[];
  timestamp: string;
}

export interface SystemComponent {
  name: string;
  status: "HEALTHY" | "DEGRADED" | "DOWN";
  latencyMs: number;
  version: string;
  checkedAt: string;
}

const now = "2026-08-10T09:30:00Z";
const sites = ["Austin", "Bengaluru", "Frankfurt", "Toronto", "Singapore"];
const locations = ["Line A", "Line B", "Lab 2", "Edge Rack", "Validation Cell"];
const serviceNames = ["telemetry-agent", "control-plane", "sensor-ingestor", "diagnostic-runner"];

export const devices: Device[] = Array.from({ length: 50 }, (_, index) => {
  const number = index + 1;
  const id = `SIM-${String(number).padStart(3, "0")}`;
  const status = statusFor(number);
  const healthScore = scoreFor(status, number);
  return {
    id,
    model: "SIM-ENG-EDGE-1000",
    site: sites[index % sites.length],
    location: locations[index % locations.length],
    status,
    healthScore,
    firmware: `2026.${(index % 4) + 4}.${(index % 9) + 1}`,
    lastSeen: `2026-08-10T09:${String(20 + (index % 9)).padStart(2, "0")}:00Z`,
    uptimeHours: 360 + index * 11,
    services: serviceNames.map((name, serviceIndex) => ({
      name,
      state: serviceStateFor(id, name, status, serviceIndex),
      version: `1.${serviceIndex}.${index % 7}`,
      lastRestart: `2026-08-${String(2 + (index % 7)).padStart(2, "0")}T08:00:00Z`,
    })),
    telemetry: telemetryFor(number, status),
    configuration: {
      telemetry_interval_seconds: 30,
      diagnostics_enabled: true,
      firmware_channel: index % 5 === 0 ? "candidate" : "stable",
      packet_loss_threshold: 10,
      approval_required_for_restart: true,
    },
  };
});

export const incidents: Incident[] = [
  {
    id: "INC-014-NET",
    deviceId: "SIM-014",
    title: "Network timeout and packet loss",
    severity: "CRITICAL",
    status: "INVESTIGATING",
    owner: "network-ops",
    createdAt: now,
  },
  {
    id: "INC-021-CPU",
    deviceId: "SIM-021",
    title: "CPU saturation candidate",
    severity: "CRITICAL",
    status: "OPEN",
    owner: "platform-ops",
    createdAt: "2026-08-10T08:50:00Z",
  },
  {
    id: "INC-028-SVC",
    deviceId: "SIM-028",
    title: "Sensor ingestor crash",
    severity: "CRITICAL",
    status: "OPEN",
    owner: "operations",
    createdAt: "2026-08-10T08:35:00Z",
  },
  {
    id: "INC-035-DISK",
    deviceId: "SIM-035",
    title: "Disk capacity warning",
    severity: "WARNING",
    status: "MITIGATED",
    owner: "storage-ops",
    createdAt: "2026-08-10T07:55:00Z",
  },
  {
    id: "INC-040-MEM",
    deviceId: "SIM-040",
    title: "Memory pressure warning",
    severity: "WARNING",
    status: "INVESTIGATING",
    owner: "platform-ops",
    createdAt: "2026-08-10T07:35:00Z",
  },
];

export const tickets: Ticket[] = [
  {
    id: "TCK-014",
    deviceId: "SIM-014",
    title: "Investigate telemetry timeout and sensor initialization failures",
    priority: "CRITICAL",
    status: "IN_PROGRESS",
    assignee: "operator@example.internal",
    updatedAt: now,
  },
  {
    id: "TCK-021",
    deviceId: "SIM-021",
    title: "Review diagnostic-runner CPU utilization",
    priority: "HIGH",
    status: "OPEN",
    assignee: "engineer@example.internal",
    updatedAt: "2026-08-10T08:48:00Z",
  },
  {
    id: "TCK-035",
    deviceId: "SIM-035",
    title: "Clean retained diagnostic artifacts",
    priority: "MEDIUM",
    status: "BLOCKED",
    assignee: "storage@example.internal",
    updatedAt: "2026-08-10T08:05:00Z",
  },
  {
    id: "TCK-044",
    deviceId: "SIM-044",
    title: "Confirm preventive maintenance checks",
    priority: "LOW",
    status: "RESOLVED",
    assignee: "viewer@example.internal",
    updatedAt: "2026-08-09T17:20:00Z",
  },
];

export const approvals: Approval[] = [
  {
    id: "a46f1234-9b1a-4f78-80f0-80158d9f1001",
    operation: "restart_service",
    deviceId: "SIM-014",
    requestedBy: "operator@example.internal",
    risk: "HIGH",
    reason: "Recover telemetry-agent after network timeout investigation.",
    requestedAt: "2026-08-10T09:20:00Z",
    expiresAt: "2026-08-10T10:20:00Z",
    status: "PENDING",
  },
  {
    id: "a46f1234-9b1a-4f78-80f0-80158d9f1002",
    operation: "update_device_configuration",
    deviceId: "SIM-021",
    requestedBy: "operator@example.internal",
    risk: "CRITICAL",
    reason: "Reduce telemetry interval after confirmed CPU saturation.",
    requestedAt: "2026-08-10T08:42:00Z",
    expiresAt: "2026-08-10T09:42:00Z",
    status: "APPROVED",
  },
  {
    id: "a46f1234-9b1a-4f78-80f0-80158d9f1003",
    operation: "restart_service",
    deviceId: "SIM-028",
    requestedBy: "ai-agent-1",
    risk: "HIGH",
    reason: "Governed restart request for crashed sensor-ingestor.",
    requestedAt: "2026-08-10T08:10:00Z",
    expiresAt: "2026-08-10T09:10:00Z",
    status: "EXECUTED",
  },
];

export const tools: ToolMetadata[] = [
  ["list_devices", "device", "List registered devices.", "LOW", "devices:read", false],
  ["get_device", "device", "Read device inventory details.", "LOW", "devices:read", false],
  ["get_device_status", "device", "Read current device status.", "LOW", "devices:read", false],
  ["get_device_health", "device", "Read health score and state.", "LOW", "devices:read", false],
  ["get_device_telemetry", "device", "Read recent telemetry.", "LOW", "devices:read", false],
  ["get_device_configuration", "device", "Read runtime configuration.", "LOW", "devices:read", false],
  ["get_device_services", "device", "Read service states.", "LOW", "devices:read", false],
  ["run_device_diagnostics", "device", "Run bounded device diagnostics.", "MEDIUM", "devices:diagnose", false],
  ["restart_device", "device", "Request governed device restart.", "HIGH", "devices:operate", true],
  ["restart_service", "device", "Request governed service restart.", "HIGH", "devices:operate", true],
  [
    "update_device_configuration",
    "device",
    "Request governed configuration update.",
    "CRITICAL",
    "devices:operate",
    true,
  ],
  ["search_logs", "diagnostics", "Search operational logs.", "LOW", "devices:read", false],
  ["get_recent_errors", "diagnostics", "Read recent errors.", "LOW", "devices:read", false],
  ["get_error_details", "diagnostics", "Read known error details.", "LOW", "devices:read", false],
  ["get_service_health", "diagnostics", "Read service diagnostic health.", "LOW", "devices:read", false],
  ["get_resource_usage", "diagnostics", "Read resource usage.", "LOW", "devices:read", false],
  ["find_similar_incidents", "diagnostics", "Find related historical incidents.", "LOW", "devices:read", false],
  ["run_diagnostic_check", "diagnostics", "Run one diagnostic check.", "MEDIUM", "devices:diagnose", false],
  ["generate_diagnostic_summary", "diagnostics", "Generate diagnostic summary.", "MEDIUM", "devices:diagnose", false],
  ["search_knowledge", "knowledge", "Search engineering documentation.", "LOW", "knowledge:read", false],
  ["get_document", "knowledge", "Read a knowledge document.", "LOW", "knowledge:read", false],
  ["get_procedure", "knowledge", "Read a governed procedure.", "LOW", "knowledge:read", false],
  ["find_troubleshooting_steps", "knowledge", "Find troubleshooting steps.", "LOW", "knowledge:read", false],
  ["search_configuration_guides", "knowledge", "Search configuration guides.", "LOW", "knowledge:read", false],
  ["create_ticket", "ticket", "Create a maintenance ticket.", "MEDIUM", "tickets:create", false],
  ["get_ticket", "ticket", "Read ticket details.", "LOW", "tickets:read", false],
  ["update_ticket", "ticket", "Update ticket fields.", "LOW", "tickets:update", false],
  ["assign_ticket", "ticket", "Assign a ticket.", "LOW", "tickets:update", false],
  ["search_tickets", "ticket", "Search tickets.", "LOW", "tickets:read", false],
  ["get_open_tickets", "ticket", "Read open tickets.", "LOW", "tickets:read", false],
].map(([name, domain, description, risk, permission, requiresApproval]) => ({
  name: String(name),
  domain: String(domain),
  description: String(description),
  risk: risk as RiskLevel,
  permission: String(permission),
  requiresApproval: Boolean(requiresApproval),
  enabled: name !== "restart_device",
}));

export const auditEntries: AuditEntry[] = [
  {
    id: "AUD-1001",
    user: "ai-agent-1",
    deviceId: "SIM-014",
    tool: "generate_diagnostic_summary",
    risk: "MEDIUM",
    status: "ALLOW",
    timestamp: now,
    summary: "Generated diagnostic summary.",
  },
  {
    id: "AUD-1002",
    user: "operator@example.internal",
    deviceId: "SIM-014",
    tool: "restart_service",
    risk: "HIGH",
    status: "PENDING_APPROVAL",
    timestamp: "2026-08-10T09:20:00Z",
    summary: "Approval requested for telemetry-agent restart.",
  },
  {
    id: "AUD-1003",
    user: "viewer@example.internal",
    deviceId: "SIM-014",
    tool: "restart_service",
    risk: "HIGH",
    status: "DENY",
    timestamp: "2026-08-10T09:12:00Z",
    summary: "Viewer role lacks devices:operate.",
  },
  {
    id: "AUD-1004",
    user: "admin@example.internal",
    deviceId: "SIM-028",
    tool: "approval.approved",
    risk: "HIGH",
    status: "ALLOW",
    timestamp: "2026-08-10T08:12:00Z",
    summary: "Approved service restart request.",
  },
  {
    id: "AUD-1005",
    user: "operator@example.internal",
    deviceId: "SIM-021",
    tool: "update_device_configuration",
    risk: "CRITICAL",
    status: "ALLOW",
    timestamp: "2026-08-10T08:45:00Z",
    summary: "Executed approved configuration update.",
  },
];

export const knowledgeDocuments: KnowledgeDocument[] = [
  {
    id: "kb-simulator-maintenance-manual",
    title: "Simulator Maintenance Manual",
    type: "MANUAL",
    version: "1.0",
    model: "SIM-ENG-EDGE-1000",
    tags: ["simulator", "maintenance", "telemetry"],
    updatedAt: "2026-07-10T14:30:00Z",
    excerpt: "Maintenance manual for routine inspection of engineering edge devices.",
  },
  {
    id: "kb-network-troubleshooting",
    title: "Network Troubleshooting Guide",
    type: "TROUBLESHOOTING_GUIDE",
    version: "1.0",
    model: "SIM-ENG-EDGE-1000",
    tags: ["network", "packet_loss", "E-NET-TIMEOUT"],
    updatedAt: "2026-07-10T14:30:00Z",
    excerpt: "Packet loss with E-NET-TIMEOUT indicates a network communication issue.",
  },
  {
    id: "kb-sensor-init",
    title: "Sensor Troubleshooting Guide",
    type: "TROUBLESHOOTING_GUIDE",
    version: "1.0",
    model: "SIM-ENG-EDGE-1000",
    tags: ["sensor", "E-SENSOR-INIT", "crash"],
    updatedAt: "2026-07-10T14:30:00Z",
    excerpt: "Covers sensor initialization failures and sensor-ingestor startup.",
  },
  {
    id: "kb-service-restart",
    title: "Service Restart Procedure",
    type: "PROCEDURE",
    version: "1.0",
    model: "SIM-ENG-EDGE-1000",
    tags: ["restart_service", "approval", "operations"],
    updatedAt: "2026-07-10T14:30:00Z",
    excerpt: "Governed service restarts require policy evaluation, approval, and audit.",
  },
  {
    id: "kb-configuration-guide",
    title: "Simulator Configuration Guide",
    type: "CONFIGURATION_GUIDE",
    version: "1.0",
    model: "SIM-ENG-EDGE-1000",
    tags: ["configuration", "firmware", "telemetry"],
    updatedAt: "2026-07-10T14:30:00Z",
    excerpt: "Configuration changes require bounded patches and approval for critical tools.",
  },
  {
    id: "kb-preventive-maintenance-sop",
    title: "Preventive Maintenance SOP",
    type: "SOP",
    version: "1.0",
    model: "SIM-ENG-EDGE-1000",
    tags: ["preventive", "maintenance", "cpu", "memory"],
    updatedAt: "2026-07-10T14:30:00Z",
    excerpt: "Weekly review process for repeated warnings, open tickets, and audit checks.",
  },
];

export const diagnosticReports: DiagnosticReport[] = [
  {
    id: "DGN-SIM-014",
    deviceId: "SIM-014",
    severity: "CRITICAL",
    cause: "network communication issue",
    confidence: 0.92,
    evidence: ["Packet loss is 18%.", "Recent errors include E-NET-TIMEOUT."],
    references: ["kb-network-troubleshooting@1.0#network-timeout"],
    timestamp: now,
  },
  {
    id: "DGN-SIM-021",
    deviceId: "SIM-021",
    severity: "CRITICAL",
    cause: "CPU saturation candidate",
    confidence: 0.86,
    evidence: ["CPU usage is 96%.", "Process response latency is elevated."],
    references: ["kb-preventive-maintenance-sop@1.0#weekly-review"],
    timestamp: "2026-08-10T08:52:00Z",
  },
  {
    id: "DGN-SIM-035",
    deviceId: "SIM-035",
    severity: "WARNING",
    cause: "disk capacity warning",
    confidence: 0.74,
    evidence: ["Disk usage is 89%.", "Retained diagnostic artifacts are high."],
    references: ["kb-configuration-guide@1.0#config-control"],
    timestamp: "2026-08-10T08:02:00Z",
  },
];

export const systemComponents: SystemComponent[] = [
  { name: "API", status: "HEALTHY", latencyMs: 24, version: "0.1.0", checkedAt: now },
  { name: "MCP Gateway", status: "HEALTHY", latencyMs: 31, version: "0.1.0", checkedAt: now },
  { name: "Device MCP", status: "HEALTHY", latencyMs: 20, version: "0.1.0", checkedAt: now },
  { name: "Diagnostics MCP", status: "HEALTHY", latencyMs: 35, version: "0.1.0", checkedAt: now },
  { name: "Knowledge MCP", status: "HEALTHY", latencyMs: 18, version: "0.1.0", checkedAt: now },
  { name: "Ticket MCP", status: "HEALTHY", latencyMs: 26, version: "0.1.0", checkedAt: now },
  { name: "PostgreSQL", status: "HEALTHY", latencyMs: 15, version: "16", checkedAt: now },
  { name: "Redis", status: "HEALTHY", latencyMs: 8, version: "7", checkedAt: now },
  { name: "Kafka", status: "DEGRADED", latencyMs: 85, version: "3.7", checkedAt: now },
  { name: "OpenSearch", status: "HEALTHY", latencyMs: 42, version: "2.x", checkedAt: now },
];

export const recentOperations = auditEntries.slice(0, 4);

export function statusForDevice(id: string): DeviceStatus {
  return devices.find((device) => device.id === id)?.status ?? "OFFLINE";
}

function statusFor(number: number): DeviceStatus {
  if ([14, 21, 28].includes(number)) return "CRITICAL";
  if ([7, 19, 35, 40, 46].includes(number)) return "WARNING";
  if ([12, 33].includes(number)) return "OFFLINE";
  return "HEALTHY";
}

function scoreFor(status: DeviceStatus, number: number): number {
  if (status === "CRITICAL") return 22 + (number % 9);
  if (status === "WARNING") return 62 + (number % 12);
  if (status === "OFFLINE") return 0;
  return 91 + (number % 7);
}

function serviceStateFor(
  deviceId: string,
  name: string,
  status: DeviceStatus,
  index: number,
): ServiceState {
  if (deviceId === "SIM-014" && name === "telemetry-agent") return "DEGRADED";
  if (deviceId === "SIM-028" && name === "sensor-ingestor") return "CRASHED";
  if (status === "OFFLINE") return "STOPPED";
  if (status === "WARNING" && index === 0) return "DEGRADED";
  return "RUNNING";
}

function telemetryFor(number: number, status: DeviceStatus): TelemetryPoint[] {
  return Array.from({ length: 12 }, (_, index) => {
    const critical = status === "CRITICAL";
    const warning = status === "WARNING";
    return {
      timestamp: `09:${String(index * 5).padStart(2, "0")}`,
      cpu: critical ? 88 + (index % 5) : warning ? 65 + (index % 12) : 34 + ((number + index) % 20),
      memory: critical ? 78 + (index % 9) : warning ? 70 + (index % 8) : 42 + ((number + index) % 18),
      temperature: critical ? 76 + (index % 6) : warning ? 65 + (index % 5) : 46 + (index % 8),
      latency: number === 14 ? 420 + index * 18 : critical ? 260 + index * 7 : 38 + index * 3,
      packetLoss: number === 14 ? 12 + (index % 8) : warning ? 3 + (index % 4) : index % 2,
      disk: number === 35 ? 86 + (index % 5) : 48 + ((number + index) % 24),
    };
  });
}
