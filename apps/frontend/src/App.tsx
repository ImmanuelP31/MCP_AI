import {
  Activity,
  AlertTriangle,
  Archive,
  BarChart3,
  BookOpen,
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleGauge,
  ClipboardCheck,
  Database,
  FileClock,
  Filter,
  Gauge,
  GitBranch,
  Home,
  KeyRound,
  ListChecks,
  LockKeyhole,
  MonitorCog,
  RefreshCw,
  Search,
  Send,
  Server,
  Share2,
  ShieldCheck,
  TicketCheck,
  Wrench,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";

import {
  type Approval,
  type ApprovalStatus,
  type AuditEntry,
  type Device,
  type DeviceStatus,
  type DiagnosticReport,
  type Incident,
  type RiskLevel,
  type Role,
  type ServiceState,
  type SystemComponent,
  approvals,
  auditEntries,
  devices,
  diagnosticReports,
  incidents,
  knowledgeDocuments,
  recentOperations,
  statusForDevice,
  systemComponents,
  tickets,
  tools,
} from "./data";

type PageState = "loading" | "ready" | "error";

interface RouteItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

const navItems: RouteItem[] = [
  { path: "/dashboard", label: "Dashboard", icon: Home },
  { path: "/devices", label: "Devices", icon: MonitorCog },
  { path: "/diagnostics", label: "Diagnostics", icon: BarChart3 },
  { path: "/incidents", label: "Incidents", icon: AlertTriangle },
  { path: "/tickets", label: "Tickets", icon: TicketCheck },
  { path: "/knowledge", label: "Knowledge", icon: BookOpen },
  { path: "/assistant", label: "Assistant", icon: Bot },
  { path: "/tool-discovery", label: "Tool Discovery", icon: Search },
  { path: "/workflows", label: "Workflows", icon: GitBranch },
  { path: "/capabilities", label: "Capabilities", icon: Share2 },
  { path: "/evaluation", label: "Evaluation", icon: BarChart3 },
  { path: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { path: "/tools", label: "Tools", icon: Wrench },
  { path: "/audit", label: "Audit", icon: FileClock },
  { path: "/security", label: "Security", icon: ShieldCheck },
  { path: "/system", label: "System", icon: Server },
];

const roleLabels: Record<Role, string> = {
  VIEWER: "Viewer",
  ENGINEER: "Engineer",
  OPERATOR: "Operator",
  ADMIN: "Admin",
};

const roleProfiles: Record<Role, { title: string; permissions: string[]; denied: string[] }> = {
  VIEWER: {
    title: "Read-only operations visibility",
    permissions: ["View fleet health", "Read device telemetry", "Search knowledge", "Read tickets"],
    denied: ["Run diagnostics", "Create tickets", "Operate devices", "Approve requests"],
  },
  ENGINEER: {
    title: "Diagnosis and maintenance planning",
    permissions: ["View telemetry", "Run diagnostics", "Create tickets", "Update tickets"],
    denied: ["Restart services", "Update configuration", "Approve high-risk requests"],
  },
  OPERATOR: {
    title: "Controlled operations execution",
    permissions: ["Run diagnostics", "Create tickets", "Request service restarts", "Request config changes"],
    denied: ["Self-approve", "Approve AI requests", "Bypass MCP gateway"],
  },
  ADMIN: {
    title: "Governance and approval authority",
    permissions: ["Approve eligible requests", "Review audit", "Inspect tool registry", "Administer policy"],
    denied: ["Self-approve own request", "Bypass audit", "Execute unknown tools"],
  },
};

const API_BASE_URL = localStorage.getItem("mcp.apiBaseUrl") || "http://127.0.0.1:18000";

export function App() {
  const [path, setPath] = useState(window.location.pathname === "/" ? "/login" : window.location.pathname);
  const [role, setRole] = useState<Role>(() => (localStorage.getItem("mcp.role") as Role) || "ADMIN");
  const [pageState, setPageState] = useState<PageState>("loading");

  useEffect(() => {
    const onPopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    setPageState("loading");
    const handle = window.setTimeout(() => setPageState("ready"), 180);
    return () => window.clearTimeout(handle);
  }, [path]);

  const navigate = (nextPath: string) => {
    window.history.pushState({}, "", nextPath);
    setPath(nextPath);
  };

  const changeRole = (nextRole: Role) => {
    localStorage.setItem("mcp.role", nextRole);
    setRole(nextRole);
  };

  if (path === "/login") {
    return <LoginPage role={role} setRole={changeRole} navigate={navigate} />;
  }

  return (
    <Shell path={path} role={role} setRole={changeRole} navigate={navigate}>
      {pageState === "loading" ? (
        <LoadingState />
      ) : (
        <PageRouter path={path} role={role} navigate={navigate} />
      )}
    </Shell>
  );
}

function LoginPage({
  role,
  setRole,
  navigate,
}: {
  role: Role;
  setRole: (role: Role) => void;
  navigate: (path: string) => void;
}) {
  const profile = roleProfiles[role];
  return (
    <main className="login-screen">
      <section className="login-panel">
        <div className="brand-row">
          <ShieldCheck className="h-6 w-6 text-emerald-700" aria-hidden="true" />
          <span>MCP Engineering Operations</span>
        </div>
        <h1>Sign in to the operations console</h1>
        <p className="muted">
          Select an access profile to inspect role-based controls, approval routing, and audit
          behavior across engineering operations.
        </p>
        <div className="role-grid" aria-label="Role selector">
          {(["VIEWER", "ENGINEER", "OPERATOR", "ADMIN"] satisfies Role[]).map((item) => (
            <button
              key={item}
              className={role === item ? "role-option selected" : "role-option"}
              type="button"
              onClick={() => setRole(item)}
            >
              <span>{roleLabels[item]}</span>
              <small>{permissionSummary(item)}</small>
            </button>
          ))}
        </div>
        <div className="authorization-panel">
          <div>
            <p className="eyebrow">Selected role</p>
            <h2>{roleLabels[role]}</h2>
            <p>{profile.title}</p>
          </div>
          <div className="auth-columns">
            <div>
              <strong>Allowed</strong>
              <ul>
                {profile.permissions.map((permission) => (
                  <li key={permission}>{permission}</li>
                ))}
              </ul>
            </div>
            <div>
              <strong>Blocked</strong>
              <ul>
                {profile.denied.map((permission) => (
                  <li key={permission}>{permission}</li>
                ))}
              </ul>
            </div>
          </div>
          <div className="policy-chip">
            <LockKeyhole className="h-4 w-4" aria-hidden="true" />
            <span>Gateway ignores model-supplied roles and approval tokens.</span>
          </div>
        </div>
        <button className="primary-action" type="button" onClick={() => navigate("/dashboard")}>
          <KeyRound className="h-4 w-4" aria-hidden="true" />
          Continue
        </button>
      </section>
    </main>
  );
}

function Shell({
  children,
  path,
  role,
  setRole,
  navigate,
}: {
  children: React.ReactNode;
  path: string;
  role: Role;
  setRole: (role: Role) => void;
  navigate: (path: string) => void;
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="sidebar-brand" type="button" onClick={() => navigate("/dashboard")}>
          <ShieldCheck className="h-5 w-5 text-emerald-700" aria-hidden="true" />
          <span>MCP Ops</span>
        </button>
        <nav className="nav-list" aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = path === item.path || (item.path === "/devices" && path.startsWith("/devices/"));
            return (
              <button
                key={item.path}
                className={active ? "nav-item active" : "nav-item"}
                type="button"
                onClick={() => navigate(item.path)}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Governed operations</p>
            <h1>{titleForPath(path)}</h1>
          </div>
          <div className="topbar-actions">
            <div className="topbar-status" aria-label="Gateway enforcement status">
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              <span>Gateway enforced</span>
            </div>
            <label className="role-select">
              <span>Role</span>
              <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
                {(["VIEWER", "ENGINEER", "OPERATOR", "ADMIN"] satisfies Role[]).map((item) => (
                  <option key={item} value={item}>
                    {roleLabels[item]}
                  </option>
                ))}
              </select>
            </label>
            <button className="icon-button" type="button" title="Refresh view" aria-label="Refresh view">
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}

function PageRouter({ path, role, navigate }: { path: string; role: Role; navigate: (path: string) => void }) {
  if (path === "/dashboard") return <DashboardPage navigate={navigate} />;
  if (path === "/devices") return <DevicesPage navigate={navigate} />;
  if (path.startsWith("/devices/")) return <DeviceDetailPage path={path} navigate={navigate} />;
  if (path === "/diagnostics") return <DiagnosticsPage />;
  if (path === "/incidents") return <IncidentsPage />;
  if (path === "/tickets") return <TicketsPage />;
  if (path === "/knowledge") return <KnowledgePage />;
  if (path === "/assistant") return <AssistantPage role={role} navigate={navigate} />;
  if (path === "/tool-discovery") return <ToolDiscoveryPage role={role} />;
  if (path === "/workflows") return <WorkflowPlannerPage role={role} />;
  if (path === "/capabilities") return <CapabilityGraphPage role={role} />;
  if (path === "/evaluation") return <EvaluationPage />;
  if (path === "/approvals") return <ApprovalsPage role={role} />;
  if (path === "/tools") return <ToolsPage />;
  if (path === "/audit") return <AuditPage />;
  if (path === "/security") return <SecurityGovernancePage />;
  if (path === "/system") return <SystemPage />;
  return <ErrorState title="Route not found" detail={`No page is registered for ${path}.`} />;
}

function DashboardPage({ navigate }: { navigate: (path: string) => void }) {
  const counts = countByStatus(devices);
  const pendingApprovals = approvals.filter((approval) => approval.status === "PENDING");
  const activeIncidents = incidents.filter((incident) => incident.status !== "MITIGATED");
  return (
    <div className="page-stack">
      <CommandCenter
        activeIncidents={activeIncidents.length}
        pendingApprovals={pendingApprovals.length}
        navigate={navigate}
      />
      <section className="metric-grid">
        <MetricTile label="Devices" value={devices.length} icon={MonitorCog} accent="neutral" />
        <MetricTile label="Healthy" value={counts.HEALTHY} icon={Check} accent="success" />
        <MetricTile label="Warning" value={counts.WARNING} icon={AlertTriangle} accent="warning" />
        <MetricTile label="Critical" value={counts.CRITICAL} icon={Activity} accent="danger" />
        <MetricTile label="Offline" value={counts.OFFLINE} icon={Archive} accent="muted" />
        <MetricTile label="Pending approvals" value={pendingApprovals.length} icon={ClipboardCheck} accent="purple" />
      </section>
      <div className="two-column">
        <Section title="Fleet status" icon={CircleGauge}>
          <HealthDistribution counts={counts} />
        </Section>
        <Section title="System health" icon={Server}>
          <CompactSystemHealth components={systemComponents} />
        </Section>
      </div>
      <div className="two-column wide-left">
        <Section title="Active incidents" icon={AlertTriangle}>
          <IncidentTable incidents={activeIncidents} compact />
        </Section>
        <Section title="Recent operations" icon={FileClock}>
          <AuditTable entries={recentOperations} compact />
        </Section>
      </div>
      <Section title="Pending approvals" icon={ClipboardCheck}>
        {pendingApprovals.length === 0 ? (
          <EmptyState title="No pending approvals" detail="High-risk operations are clear." />
        ) : (
          <ApprovalTable approvals={pendingApprovals} role="VIEWER" onStatusChange={() => undefined} />
        )}
      </Section>
      <div className="quick-links" aria-label="Primary workflow links">
        <button type="button" onClick={() => navigate("/devices/SIM-014")}>
          SIM-014 detail
        </button>
        <button type="button" onClick={() => navigate("/assistant")}>
          Ask assistant
        </button>
        <button type="button" onClick={() => navigate("/diagnostics")}>
          Diagnostic queue
        </button>
        <button type="button" onClick={() => navigate("/approvals")}>
          Approval center
        </button>
      </div>
    </div>
  );
}

function CommandCenter({
  activeIncidents,
  pendingApprovals,
  navigate,
}: {
  activeIncidents: number;
  pendingApprovals: number;
  navigate: (path: string) => void;
}) {
  return (
    <section className="command-center">
      <div className="command-copy">
        <p className="eyebrow">Operations command center</p>
        <h2>SIM-014 is driving the current incident posture</h2>
        <p>
          Network timeout evidence, degraded telemetry, pending approval control, and audit
          visibility are linked into one governed workflow.
        </p>
        <div className="command-actions">
          <button type="button" onClick={() => navigate("/devices/SIM-014")}>
            Open device
          </button>
          <button type="button" onClick={() => navigate("/assistant")}>
            Ask assistant
          </button>
          <button type="button" onClick={() => navigate("/approvals")}>
            Review approvals
          </button>
        </div>
      </div>
      <div className="command-grid">
        <PostureCard label="Active incidents" value={activeIncidents} detail="Incident queue is traceable to alerts." />
        <PostureCard label="Pending approvals" value={pendingApprovals} detail="High-risk actions wait for human review." />
        <PostureCard label="Tool boundary" value="MCP" detail="AI requests route through the gateway." />
        <PostureCard label="Audit mode" value="On" detail="Every decision is recorded with risk context." />
      </div>
    </section>
  );
}

function PostureCard({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return (
    <article className="posture-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function DevicesPage({ navigate }: { navigate: (path: string) => void }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<DeviceStatus | "ALL">("ALL");
  const [page, setPage] = useState(1);
  const filtered = devices.filter((device) => {
    const text = `${device.id} ${device.site} ${device.location} ${device.model}`.toLowerCase();
    return text.includes(query.toLowerCase()) && (status === "ALL" || device.status === status);
  });
  const paged = paginate(filtered, page, 12);

  return (
    <div className="page-stack">
      <Toolbar>
        <SearchBox value={query} onChange={setQuery} ariaLabel="Search devices" />
        <SegmentedFilter
          value={status}
          onChange={(value) => {
            setStatus(value as DeviceStatus | "ALL");
            setPage(1);
          }}
          options={["ALL", "HEALTHY", "WARNING", "CRITICAL", "OFFLINE"]}
        />
      </Toolbar>
      {filtered.length === 0 ? (
        <EmptyState title="No devices match the filters" detail="Adjust status or search terms." />
      ) : (
        <Section title="Device fleet" icon={MonitorCog}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Device</th>
                  <th>Status</th>
                  <th>Health</th>
                  <th>Site</th>
                  <th>Location</th>
                  <th>Firmware</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {paged.items.map((device) => (
                  <tr key={device.id} onClick={() => navigate(`/devices/${device.id}`)}>
                    <td>
                      <button className="table-link" type="button">
                        {device.id}
                      </button>
                    </td>
                    <td>
                      <StatusBadge status={device.status} />
                    </td>
                    <td>
                      <HealthCell score={device.healthScore} />
                    </td>
                    <td>{device.site}</td>
                    <td>{device.location}</td>
                    <td>{device.firmware}</td>
                    <td>{formatTime(device.lastSeen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} totalPages={paged.totalPages} onPageChange={setPage} />
        </Section>
      )}
    </div>
  );
}

function DeviceDetailPage({ path, navigate }: { path: string; navigate: (path: string) => void }) {
  const deviceId = path.split("/").pop() ?? "";
  const device = devices.find((item) => item.id === deviceId);
  if (!device) {
    return <ErrorState title="Device not found" detail={`${deviceId} is not in the device registry.`} />;
  }
  const deviceIncidents = incidents.filter((incident) => incident.deviceId === device.id);
  const deviceTickets = tickets.filter((ticket) => ticket.deviceId === device.id);
  const deviceDiagnostics = diagnosticReports.filter((report) => report.deviceId === device.id);

  return (
    <div className="page-stack">
      <button className="back-button" type="button" onClick={() => navigate("/devices")}>
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        Devices
      </button>
      <section className="detail-header">
        <div>
          <p className="eyebrow">{device.model}</p>
          <h2>{device.id}</h2>
          <p className="muted">
            {device.site} / {device.location} / firmware {device.firmware}
          </p>
        </div>
        <div className="detail-status">
          <StatusBadge status={device.status} />
          <HealthCell score={device.healthScore} />
        </div>
      </section>
      <div className="three-column">
        <MetricTile label="Health score" value={`${device.healthScore}%`} icon={Gauge} accent="neutral" />
        <MetricTile label="Uptime" value={`${device.uptimeHours}h`} icon={Activity} accent="success" />
        <MetricTile label="Open tickets" value={deviceTickets.filter((ticket) => ticket.status !== "RESOLVED").length} icon={TicketCheck} accent="warning" />
      </div>
      <Section title="Telemetry" icon={BarChart3}>
        <TelemetryCharts device={device} />
      </Section>
      <div className="two-column">
        <Section title="Service status" icon={ListChecks}>
          <ServiceList services={device.services} />
        </Section>
        <Section title="Configuration" icon={Wrench}>
          <KeyValueGrid values={device.configuration} />
        </Section>
      </div>
      <div className="two-column">
        <Section title="Recent errors" icon={AlertTriangle}>
          <RecentErrors device={device} />
        </Section>
        <Section title="Diagnostics" icon={CircleGauge}>
          <DiagnosticList reports={deviceDiagnostics} />
        </Section>
      </div>
      <div className="two-column">
        <Section title="Incidents" icon={AlertTriangle}>
          <IncidentTable incidents={deviceIncidents} compact />
        </Section>
        <Section title="Tickets" icon={TicketCheck}>
          <TicketTable tickets={deviceTickets} compact />
        </Section>
      </div>
    </div>
  );
}

function DiagnosticsPage() {
  return (
    <div className="page-stack">
      <Toolbar>
        <SearchBox value="" onChange={() => undefined} ariaLabel="Search diagnostics" />
      </Toolbar>
      <Section title="Diagnostic reports" icon={CircleGauge}>
        <DiagnosticList reports={diagnosticReports} />
      </Section>
    </div>
  );
}

function IncidentsPage() {
  const [status, setStatus] = useState("ALL");
  const [page, setPage] = useState(1);
  const filtered = incidents.filter((incident) => status === "ALL" || incident.status === status);
  const paged = paginate(filtered, page, 4);
  return (
    <div className="page-stack">
      <Toolbar>
        <SegmentedFilter
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          options={["ALL", "OPEN", "INVESTIGATING", "MITIGATED"]}
        />
      </Toolbar>
      <Section title="Incident queue" icon={AlertTriangle}>
        <IncidentTable incidents={paged.items} />
        <Pagination page={page} totalPages={paged.totalPages} onPageChange={setPage} />
      </Section>
    </div>
  );
}

function TicketsPage() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const filtered = tickets.filter((ticket) =>
    `${ticket.id} ${ticket.deviceId} ${ticket.title} ${ticket.assignee}`.toLowerCase().includes(query.toLowerCase()),
  );
  const paged = paginate(filtered, page, 3);
  return (
    <div className="page-stack">
      <Toolbar>
        <SearchBox value={query} onChange={setQuery} ariaLabel="Search tickets" />
      </Toolbar>
      <Section title="Maintenance tickets" icon={TicketCheck}>
        {filtered.length === 0 ? (
          <EmptyState title="No tickets found" detail="Try a device ID, owner, or title keyword." />
        ) : (
          <>
            <TicketTable tickets={paged.items} />
            <Pagination page={page} totalPages={paged.totalPages} onPageChange={setPage} />
          </>
        )}
      </Section>
    </div>
  );
}

function KnowledgePage() {
  const [query, setQuery] = useState("");
  const filtered = knowledgeDocuments.filter((document) =>
    `${document.title} ${document.type} ${document.tags.join(" ")} ${document.excerpt}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="page-stack">
      <Toolbar>
        <SearchBox value={query} onChange={setQuery} ariaLabel="Search knowledge" />
      </Toolbar>
      <Section title="Engineering knowledge" icon={BookOpen}>
        {filtered.length === 0 ? (
          <EmptyState title="No documents found" detail="Keyword search did not match available documentation." />
        ) : (
          <div className="document-grid">
            {filtered.map((document) => (
              <article className="document-card" key={document.id}>
                <div>
                  <p className="eyebrow">{document.type}</p>
                  <h3>{document.title}</h3>
                  <p>{document.excerpt}</p>
                </div>
                <dl>
                  <div>
                    <dt>Version</dt>
                    <dd>{document.version}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>{document.model}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{formatDate(document.updatedAt)}</dd>
                  </div>
                </dl>
                <div className="tag-row">
                  {document.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

interface ChatMessage {
  id: string;
  author: "user" | "assistant";
  text: string;
  intent?: string;
  ok?: boolean;
  approvalId?: string | null;
  approvalRequired?: boolean;
  trace?: AgentTrace[];
  confidence?: number;
  escalationRequired?: boolean;
  escalationReason?: string | null;
  selectedTools?: AgentSelectedTool[];
  citations?: AgentCitation[];
}

interface AgentTrace {
  tool_name: string;
  decision: string;
  ok: boolean;
  approval_id?: string | null;
  error_code?: string | null;
}

interface AgentChatResponse {
  ok: boolean;
  intent: string;
  message: string;
  approval_required: boolean;
  approval_id: string | null;
  confidence: number;
  escalation_required: boolean;
  escalation_reason: string | null;
  selected_tools: AgentSelectedTool[];
  citations: AgentCitation[];
  trace: AgentTrace[];
}

interface AgentSelectedTool {
  tool_name: string;
  reason: string;
  confidence: number;
}

interface AgentCitation {
  citation: string;
  document_id?: string | null;
  title?: string | null;
}

interface ToolDiscoveryTool {
  name: string;
  description: string;
  server: string;
  category: string;
  risk_level: RiskLevel;
  required_permission: string;
  required_roles: string[];
  tags: string[];
  executable: boolean;
  enabled: boolean;
  semantic_score: number;
  lexical_score: number;
  combined_score: number;
  authorization_status: string;
  explanation: string;
}

interface ToolDiscoveryResponse {
  query: string;
  role: string;
  ranked_tools: ToolDiscoveryTool[];
  filtered_out_unauthorized: number;
  index_backend: string;
}

interface WorkflowNode {
  id: string;
  tool_name: string;
  tool_server: string;
  description: string;
  arguments: Record<string, unknown>;
  argument_references: {
    argument: string;
    source_node_id: string;
    output_path: string;
  }[];
  depends_on: string[];
  condition: string | null;
  typed_condition: {
    source_node_id: string;
    output_path: string;
    operator: "eq" | "ne" | "gt" | "gte" | "lt" | "lte" | "contains" | "exists";
    value: unknown;
  } | null;
  risk_level: RiskLevel;
  approval_required: boolean;
  execution_status: string;
  attempts: number;
  max_retries: number;
  retry_strategy: "NO_RETRY" | "FIXED_DELAY" | "EXPONENTIAL_BACKOFF";
  timeout_seconds: number;
  last_error: string | null;
  started_at: string | null;
  completed_at: string | null;
  last_attempt_at: string | null;
  next_retry_at: string | null;
  result_reference: string | null;
  compensation_tool: string | null;
  policy_evaluation: WorkflowPolicyEvaluation | null;
  knowledge_references: string[];
}

interface WorkflowPolicyEvaluation {
  actor: string;
  role: string;
  tool: string;
  resource: string | null;
  environment: string;
  risk: RiskLevel;
  decision: "ALLOW" | "ALLOW_WITH_APPROVAL" | "DENY" | "REQUIRE_ADDITIONAL_CONTEXT";
  policy_rule: string;
  reason: string;
  timestamp: string;
}

interface WorkflowEdge {
  source: string;
  destination: string;
  condition: string | null;
}

interface Workflow {
  id: string;
  user_request: string;
  status: string;
  created_by: string;
  created_at: string;
  target_environment: string;
  planner_model: string;
  confidence: number;
  version: number;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

interface ResourceNode {
  id: string;
  type: string;
  name: string;
  metadata: Record<string, unknown>;
  environment: string | null;
}

interface CapabilityEdge {
  source_type: string;
  destination_type: string;
  tool_name: string;
  mcp_server: string;
  cost: number;
  risk: RiskLevel;
  prerequisites: string[];
  enabled: boolean;
}

interface CapabilityGraphResponse {
  resources: ResourceNode[];
  edges: CapabilityEdge[];
}

interface CapabilityPathResponse {
  source: string;
  goal: string;
  reachable: boolean;
  nodes: string[];
  edges: CapabilityEdge[];
  tools: string[];
  total_cost: number;
  risk_score: number;
  policy_compliant: boolean;
  explanation: string;
  alternatives: string[][];
}

interface WorkflowApiResponse {
  ok: boolean;
  workflow: Workflow;
  discovered_tools?: ToolDiscoveryTool[];
  validation_issues?: Array<{ code: string; message: string; node_id?: string | null }>;
  capability_path?: CapabilityPathResponse | null;
  retrieved_knowledge?: KnowledgeSearchResult[];
  planner_provider?: string;
  planner_model?: string;
  embedding_provider?: string;
  retrieval_backend?: string;
}

interface EvaluationSummary {
  config: string;
  mode: string;
  cases: number;
  provider_successful_cases?: number;
  provider_failed_cases?: number;
  provider_success_rate?: number;
  tool_recall: number;
  tool_precision: number;
  exact_tool_set_accuracy: number;
  workflow_validity_rate: number;
  workflow_completion_rate: number;
  hallucinated_tool_rate: number;
  benchmark_unexpected_tool_rate?: number;
  unknown_or_disallowed_tool_rate?: number;
  unnecessary_tool_call_rate: number;
  policy_violation_attempt_rate: number;
  approval_classification_accuracy: number;
  rag_recall_at_k: number;
  rag_mrr: number;
  average_workflow_length: number;
  execution_success_rate: number;
  end_to_end_workflow_validity_rate?: number;
  end_to_end_execution_success_rate?: number;
  planner_latency_ms: number;
  end_to_end_latency_ms: number;
  token_usage: number;
  estimated_model_cost_usd: number | null;
}

interface EvaluationLatestResponse {
  available: boolean;
  mode: string | null;
  generated_at: string | null;
  dataset_path: string | null;
  summaries: EvaluationSummary[];
  result_path: string | null;
}

interface KnowledgeSearchResult {
  chunk_id: string;
  citation_id: string;
  document: {
    document_id: string;
    title: string;
    document_type: string;
    service: string | null;
    repository: string | null;
    environment: string | null;
    owner: string | null;
    version: string;
    source: string;
    updated_at: string;
    stale: boolean;
  };
  text: string;
  lexical_score: number;
  semantic_score: number;
  combined_score: number;
  reason: string;
  classification: string;
  prompt_injection_detected: boolean;
  conflict_group: string | null;
}

function AssistantPage({ role, navigate }: { role: Role; navigate: (path: string) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "assistant-welcome",
      author: "assistant",
      text:
        "Ask any operations question or request a governed task. I can answer with LLM-backed context and can only act through MCP tools allowed for your current role.",
    },
  ]);
  const [question, setQuestion] = useState("");
  const [isThinking, setIsThinking] = useState(false);

  const ask = async (prompt: string) => {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    const userMessageId = crypto.randomUUID();
    const pendingMessageId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      { id: userMessageId, author: "user", text: trimmed },
      {
        id: pendingMessageId,
        author: "assistant",
        text: "Calling governed agent service...",
      },
    ]);
    setQuestion("");
    setIsThinking(true);
    try {
      const response = await callAgent(trimmed, role);
      setMessages((current) =>
        current.map((message) =>
          message.id === pendingMessageId
            ? {
                ...message,
                text: response.message,
                intent: response.intent,
                ok: response.ok,
                approvalId: response.approval_id,
                approvalRequired: response.approval_required,
                confidence: response.confidence,
                escalationRequired: response.escalation_required,
                escalationReason: response.escalation_reason,
                selectedTools: response.selected_tools,
                citations: response.citations,
                trace: response.trace,
              }
            : message,
        ),
      );
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === pendingMessageId
            ? {
                ...message,
                text:
                  error instanceof Error
                    ? `Agent request failed: ${error.message}`
                    : "Agent request failed.",
                ok: false,
                intent: "API_ERROR",
              }
            : message,
        ),
      );
    } finally {
      setIsThinking(false);
    }
  };

  return (
    <div className="page-stack">
      <Section title="Governed LLM agent" icon={Bot}>
        <div className="assistant-layout">
          <div className="chat-panel">
            <div className="chat-log" aria-live="polite">
              {messages.map((message) => (
                <div key={message.id} className={`chat-message ${message.author}`}>
                  <strong>{message.author === "assistant" ? "Agent" : "You"}</strong>
                  <p>{message.text}</p>
                  {message.author === "assistant" && message.intent && (
                    <AgentResultMeta message={message} />
                  )}
                </div>
              ))}
            </div>
            <form
              className="chat-input"
              onSubmit={(event) => {
                event.preventDefault();
                void ask(question);
              }}
            >
              <input
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                aria-label="Ask the AI operations agent"
                disabled={isThinking}
              />
              <button className="primary-action" type="submit" aria-label="Send question" disabled={isThinking}>
                <Send className="h-4 w-4" aria-hidden="true" />
              </button>
            </form>
          </div>
          <div className="assistant-side">
            <h3>Governed task examples</h3>
            {[
              "What is the fleet health and business impact?",
              "Why is SIM-014 unhealthy?",
              "What procedure should I follow for SIM-014?",
              "Create a maintenance ticket for SIM-014.",
              "Restart SIM-014 service.",
              "What tickets are open?",
            ].map((sample) => (
              <button key={sample} type="button" onClick={() => void ask(sample)} disabled={isThinking}>
                {sample}
              </button>
            ))}
            <button type="button" onClick={() => navigate("/devices/SIM-014")}>
              Open SIM-014
            </button>
          </div>
        </div>
      </Section>
    </div>
  );
}

function AgentResultMeta({ message }: { message: ChatMessage }) {
  return (
    <div className="agent-meta">
      <div className="agent-meta-row">
        <span>{message.ok ? "Allowed" : "Denied or failed"}</span>
        <span>{message.intent}</span>
        {typeof message.confidence === "number" && <span>{Math.round(message.confidence * 100)}% confidence</span>}
        {message.escalationRequired && <span>Escalation</span>}
        {message.approvalRequired && <span>Approval required</span>}
        {message.approvalId && <span className="mono">{message.approvalId}</span>}
      </div>
      {message.escalationReason && <p className="agent-note">{message.escalationReason}</p>}
      {message.selectedTools && message.selectedTools.length > 0 && (
        <div className="agent-trace" aria-label="Selected tool route">
          {message.selectedTools.map((tool) => (
            <span key={tool.tool_name} className="trace-ok">
              {tool.tool_name}: {Math.round(tool.confidence * 100)}%
            </span>
          ))}
        </div>
      )}
      {message.citations && message.citations.length > 0 && (
        <div className="agent-citations" aria-label="Retrieved citations">
          {message.citations.slice(0, 3).map((citation) => (
            <span key={citation.citation}>{citation.title ?? citation.document_id ?? citation.citation}</span>
          ))}
        </div>
      )}
      {message.trace && message.trace.length > 0 && (
        <div className="agent-trace" aria-label="Governed tool trace">
          {message.trace.map((step, index) => (
            <span key={`${step.tool_name}-${index}`} className={step.ok ? "trace-ok" : "trace-denied"}>
              {step.tool_name}: {step.decision}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

async function callAgent(message: string, role: Role): Promise<AgentChatResponse> {
  const response = await fetch(`${API_BASE_URL}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, role }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as AgentChatResponse;
}

function ToolDiscoveryPage({ role }: { role: Role }) {
  const [query, setQuery] = useState("Why did yesterday's production build fail?");
  const [topK, setTopK] = useState(8);
  const [result, setResult] = useState<ToolDiscoveryResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  const discover = async () => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setStatus("loading");
    try {
      setResult(await callToolDiscovery(trimmed, role, topK));
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  };

  return (
    <div className="page-stack">
      <Section title="Semantic tool discovery" icon={Search}>
        <div className="discovery-console">
          <div className="discovery-controls">
            <label>
              <span>Engineering request</span>
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Engineering request for tool discovery"
              />
            </label>
            <label>
              <span>Top K</span>
              <input
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                aria-label="Top K tools"
              />
            </label>
            <button className="primary-action" type="button" onClick={() => void discover()} disabled={status === "loading"}>
              <Search className="h-4 w-4" aria-hidden="true" />
              Retrieve tools
            </button>
          </div>
          {status === "error" && (
            <ErrorState title="Discovery request failed" detail="Confirm the API service is running and reachable." />
          )}
          {result ? (
            <div className="discovery-results">
              <div className="discovery-summary">
                <span>{result.ranked_tools.length} tools returned</span>
                <span>{result.index_backend}</span>
                <span>{result.filtered_out_unauthorized} unauthorized filtered</span>
              </div>
              {result.ranked_tools.length === 0 ? (
                <EmptyState title="No tools retrieved" detail="Try a broader engineering request or lower the minimum score." />
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Tool</th>
                        <th>Server</th>
                        <th>Risk</th>
                        <th>Auth</th>
                        <th>Scores</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.ranked_tools.map((tool, index) => (
                        <tr key={tool.name}>
                          <td>{index + 1}</td>
                          <td>
                            <strong className="mono">{tool.name}</strong>
                            <p className="table-detail">{tool.description}</p>
                          </td>
                          <td>{tool.server}</td>
                          <td>
                            <RiskBadge risk={tool.risk_level} />
                          </td>
                          <td>{tool.authorization_status}</td>
                          <td>
                            <div className="score-stack">
                              <span>combined {formatScore(tool.combined_score)}</span>
                              <span>semantic {formatScore(tool.semantic_score)}</span>
                              <span>lexical {formatScore(tool.lexical_score)}</span>
                            </div>
                          </td>
                          <td>{tool.explanation}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <EmptyState title="No discovery run yet" detail="Enter an engineering task to retrieve the planner-safe MCP tool subset." />
          )}
        </div>
      </Section>
    </div>
  );
}

async function callToolDiscovery(
  query: string,
  role: Role,
  topK: number,
): Promise<ToolDiscoveryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/ai/tool-discovery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, role, top_k: topK }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as ToolDiscoveryResponse;
}

function WorkflowPlannerPage({ role }: { role: Role }) {
  const [request, setRequest] = useState(
    "Check why the latest build failed and create a ticket if the problem comes from our code.",
  );
  const [topK, setTopK] = useState(8);
  const [environment, setEnvironment] = useState("production");
  const [result, setResult] = useState<WorkflowApiResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "planning" | "executing" | "error">("idle");

  const planWorkflow = async () => {
    const trimmed = request.trim();
    if (!trimmed) return;
    setStatus("planning");
    try {
      setResult(await callWorkflowPlan(trimmed, role, topK, environment));
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  };

  const executeWorkflow = async () => {
    if (!result) return;
    setStatus("executing");
    try {
      setResult(await callWorkflowAction(result.workflow.id, "execute", role));
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  };

  const cancelWorkflow = async () => {
    if (!result) return;
    setStatus("executing");
    try {
      setResult(await callWorkflowAction(result.workflow.id, "cancel", role));
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  };

  const resumeWorkflow = async () => {
    if (!result) return;
    setStatus("executing");
    try {
      setResult(await callWorkflowAction(result.workflow.id, "resume", role));
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  };

  const retryNode = async (nodeId: string) => {
    if (!result) return;
    setStatus("executing");
    try {
      setResult(await callWorkflowRetry(result.workflow.id, nodeId, role));
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  };

  return (
    <div className="page-stack">
      <Section title="Workflow planner" icon={GitBranch}>
        <div className="workflow-console">
          <div className="discovery-controls">
            <label>
              <span>Engineering request</span>
              <textarea
                value={request}
                onChange={(event) => setRequest(event.target.value)}
                aria-label="Engineering request for workflow planning"
              />
            </label>
            <label>
              <span>Top K</span>
              <input
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                aria-label="Top K workflow tools"
              />
            </label>
            <label>
              <span>Environment</span>
              <select
                value={environment}
                onChange={(event) => setEnvironment(event.target.value)}
                aria-label="Workflow target environment"
              >
                <option value="dev">dev</option>
                <option value="staging">staging</option>
                <option value="production">production</option>
              </select>
            </label>
            <button className="primary-action" type="button" onClick={() => void planWorkflow()} disabled={status === "planning"}>
              <GitBranch className="h-4 w-4" aria-hidden="true" />
              Plan workflow
            </button>
          </div>
          {status === "error" && (
            <ErrorState title="Workflow request failed" detail="The planner rejected the request or the API is unreachable." />
          )}
          {result ? (
            <div className="workflow-results">
              <div className="workflow-summary">
                <span>{result.workflow.status}</span>
                <span>{result.workflow.target_environment}</span>
                <span>{result.workflow.nodes.length} nodes</span>
                <span>{result.workflow.edges.length} edges</span>
                <span>{formatScore(result.workflow.confidence)} confidence</span>
                <span>{result.workflow.planner_model}</span>
              </div>
              <WorkflowGraph workflow={result.workflow} />
              <WorkflowTimeline workflow={result.workflow} onRetryNode={(nodeId) => void retryNode(nodeId)} />
              {result.retrieved_knowledge && result.retrieved_knowledge.length > 0 && (
                <KnowledgeEvidencePanel results={result.retrieved_knowledge} />
              )}
              <div className="workflow-actions">
                <button className="primary-action" type="button" onClick={() => void executeWorkflow()} disabled={status === "executing"}>
                  <Send className="h-4 w-4" aria-hidden="true" />
                  Execute
                </button>
                <button className="back-button" type="button" onClick={() => void resumeWorkflow()} disabled={status === "executing"}>
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Resume
                </button>
                <button className="back-button" type="button" onClick={() => void cancelWorkflow()} disabled={status === "executing"}>
                  <X className="h-4 w-4" aria-hidden="true" />
                  Cancel
                </button>
              </div>
              {result.discovered_tools && result.discovered_tools.length > 0 && (
                <div className="discovery-summary">
                  {result.discovered_tools.slice(0, 8).map((tool) => (
                    <span key={tool.name}>{tool.name}</span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <EmptyState title="No workflow planned yet" detail="Plan an engineering request to inspect the authorized DAG before execution." />
          )}
        </div>
      </Section>
    </div>
  );
}

function KnowledgeEvidencePanel({ results }: { results: KnowledgeSearchResult[] }) {
  return (
    <div className="knowledge-evidence-panel" aria-label="Retrieved engineering knowledge">
      <div className="workflow-node-header">
        <div>
          <p className="eyebrow">RAG evidence</p>
          <h3>Engineering knowledge used for planning</h3>
        </div>
        <span className="badge enabled">{results.length} citations</span>
      </div>
      <div className="knowledge-evidence-grid">
        {results.slice(0, 5).map((result) => (
          <article key={result.chunk_id} className="knowledge-evidence-card">
            <div>
              <strong>{result.citation_id}</strong>
              <span>{formatScore(result.combined_score)}</span>
            </div>
            <h4>{result.document.title}</h4>
            <p>{result.reason}</p>
            <div className="workflow-node-meta">
              <span>{result.document.document_type}</span>
              {result.document.repository && <span>{result.document.repository}</span>}
              {result.document.environment && <span>{result.document.environment}</span>}
              <span>v{result.document.version}</span>
              {result.prompt_injection_detected && <span>Injection flagged</span>}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function WorkflowGraph({ workflow }: { workflow: Workflow }) {
  return (
    <div className="workflow-graph" aria-label="Workflow DAG">
      {workflow.nodes.map((node) => (
        <article key={node.id} className="workflow-node">
          <div className="workflow-node-header">
            <div>
              <p className="eyebrow">{node.tool_server}</p>
              <h3>{node.tool_name}</h3>
            </div>
            <div className="workflow-node-badges">
              <RiskBadge risk={node.risk_level} />
              <span className="badge enabled">{node.execution_status}</span>
            </div>
          </div>
          <p>{node.description}</p>
          <div className="workflow-node-meta">
            <span>Node {node.id}</span>
            <span>{node.approval_required ? "Approval required" : "No approval"}</span>
            {node.policy_evaluation && <span>{node.policy_evaluation.decision}</span>}
            {node.knowledge_references.length > 0 && (
              <span>Evidence {node.knowledge_references.join(", ")}</span>
            )}
            {node.depends_on.length > 0 && <span>Depends on {node.depends_on.join(", ")}</span>}
            {node.condition && <span>Condition {node.condition}</span>}
          </div>
          {node.policy_evaluation && (
            <div className="policy-panel">
              <strong>{node.policy_evaluation.policy_rule}</strong>
              <span>{node.policy_evaluation.reason}</span>
              <small>
                {node.policy_evaluation.role} / {node.policy_evaluation.environment}
                {node.policy_evaluation.resource ? ` / ${node.policy_evaluation.resource}` : ""}
              </small>
            </div>
          )}
          {workflow.edges
            .filter((edge) => edge.source === node.id)
            .map((edge) => (
              <div key={`${edge.source}-${edge.destination}`} className="workflow-edge">
                <span>{edge.source}</span>
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
                <span>{edge.destination}</span>
                {edge.condition && <small>{edge.condition}</small>}
              </div>
            ))}
        </article>
      ))}
    </div>
  );
}

function WorkflowTimeline({
  workflow,
  onRetryNode,
}: {
  workflow: Workflow;
  onRetryNode: (nodeId: string) => void;
}) {
  return (
    <div className="workflow-timeline" aria-label="Workflow execution timeline">
      {workflow.nodes.map((node) => {
        const Icon = timelineIcon(node.execution_status);
        return (
          <article key={node.id} className={`timeline-item ${node.execution_status.toLowerCase()}`}>
            <div className="timeline-icon">
              <Icon className="h-4 w-4" aria-hidden="true" />
            </div>
            <div>
              <div className="workflow-node-header">
                <div>
                  <p className="eyebrow">{node.execution_status.replace("_", " ")}</p>
                  <h3>{node.tool_name}</h3>
                </div>
                <RiskBadge risk={node.risk_level} />
              </div>
              <div className="workflow-node-meta">
                <span>
                  attempts {node.attempts}/{node.max_retries + 1}
                </span>
                <span>{node.retry_strategy.replace("_", " ").toLowerCase()}</span>
                <span>timeout {node.timeout_seconds}s</span>
                {node.compensation_tool && <span>compensates with {node.compensation_tool}</span>}
                {node.result_reference && <span className="mono">{node.result_reference}</span>}
              </div>
              {node.last_error && <p className="timeline-error">{node.last_error}</p>}
              <div className="workflow-node-meta">
                {node.started_at && <span>started {formatTime(node.started_at)}</span>}
                {node.completed_at && <span>completed {formatTime(node.completed_at)}</span>}
                {node.next_retry_at && <span>next retry {formatTime(node.next_retry_at)}</span>}
              </div>
              {node.execution_status === "FAILED" && (
                <button className="back-button" type="button" onClick={() => onRetryNode(node.id)}>
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Retry node
                </button>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function timelineIcon(status: string): LucideIcon {
  if (status === "SUCCEEDED" || status === "COMPENSATED") return Check;
  if (status === "FAILED" || status === "DENIED") return X;
  if (status === "RETRYING" || status === "RUNNING" || status === "COMPENSATING") return RefreshCw;
  if (status === "WAITING_APPROVAL") return ClipboardCheck;
  return FileClock;
}

async function callWorkflowPlan(
  userRequest: string,
  role: Role,
  topK: number,
  environment: string,
): Promise<WorkflowApiResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/workflows/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_request: userRequest,
      role,
      target_environment: environment,
      top_k: topK,
      created_by: role.toLowerCase(),
    }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as WorkflowApiResponse;
}

async function callWorkflowAction(
  workflowId: string,
  action: "execute" | "cancel" | "resume",
  role: Role,
): Promise<WorkflowApiResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/workflows/${workflowId}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: action === "cancel" ? JSON.stringify({}) : JSON.stringify({ role }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as WorkflowApiResponse;
}

async function callWorkflowRetry(
  workflowId: string,
  nodeId: string,
  role: Role,
): Promise<WorkflowApiResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/workflows/${workflowId}/retry/${nodeId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as WorkflowApiResponse;
}

function EvaluationPage() {
  const [payload, setPayload] = useState<EvaluationLatestResponse | null>(null);
  const [state, setState] = useState<PageState>("loading");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/evaluation/latest`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as EvaluationLatestResponse;
        if (!cancelled) {
          setPayload(data);
          setState("ready");
        }
      } catch {
        if (!cancelled) setState("error");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "loading") return <LoadingState />;
  if (state === "error") {
    return <ErrorState title="Evaluation metrics unavailable" detail="The API could not load the latest evaluation results." />;
  }
  if (!payload?.available || payload.summaries.length === 0) {
    return (
      <Section title="AI workflow evaluation" icon={BarChart3}>
        <EmptyState
          title="No evaluation run generated"
          detail="Run python -m evaluation.run --config all to create deterministic benchmark results."
        />
      </Section>
    );
  }
  const latest = payload.summaries[payload.summaries.length - 1];
  const unexpectedToolRate =
    latest.benchmark_unexpected_tool_rate ?? latest.hallucinated_tool_rate;
  const unknownToolRate = latest.unknown_or_disallowed_tool_rate ?? 0;
  const providerSuccessRate = latest.provider_success_rate ?? 1;
  const providerSuccessfulCases = latest.provider_successful_cases ?? latest.cases;
  const endToEndValidity =
    latest.end_to_end_workflow_validity_rate ?? latest.workflow_validity_rate;
  return (
    <div className="page-stack">
      <Section title="AI workflow evaluation" icon={BarChart3}>
        <div className="workflow-console">
          <div className="workflow-summary">
            <span>{payload.mode}</span>
            <span>{payload.generated_at}</span>
            <span>{latest.cases} cases</span>
            <span>{latest.config}</span>
          </div>
          <div className="command-grid">
            <MetricTile label="Provider success" value={formatScore(providerSuccessRate)} icon={Activity} accent="success" />
            <MetricTile label="Quality validity" value={formatScore(latest.workflow_validity_rate)} icon={Check} accent="success" />
            <MetricTile label="E2E validity" value={formatScore(endToEndValidity)} icon={Gauge} accent="neutral" />
            <MetricTile label="Unexpected tools" value={formatScore(unexpectedToolRate)} icon={AlertTriangle} accent="warning" />
            <MetricTile label="Unknown tools" value={formatScore(unknownToolRate)} icon={ShieldCheck} accent="danger" />
            <MetricTile label="Tool recall" value={formatScore(latest.tool_recall)} icon={Wrench} accent="neutral" />
            <MetricTile label="Tool precision" value={formatScore(latest.tool_precision)} icon={ClipboardCheck} accent="neutral" />
            <MetricTile label="RAG Recall@K" value={formatScore(latest.rag_recall_at_k)} icon={BookOpen} accent="success" />
            <MetricTile label="Approval accuracy" value={formatScore(latest.approval_classification_accuracy)} icon={ClipboardCheck} accent="purple" />
            <MetricTile label="E2E latency" value={`${latest.end_to_end_latency_ms.toFixed(1)} ms`} icon={Activity} accent="muted" />
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Config</th>
                  <th>Provider</th>
                  <th>Validity</th>
                  <th>Completion</th>
                  <th>Tool F1 inputs</th>
                  <th>Unexpected</th>
                  <th>Unknown</th>
                  <th>RAG</th>
                  <th>Policy</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {payload.summaries.map((summary) => (
                  <tr key={summary.config}>
                    <td>{summary.config}</td>
                    <td>
                      {summary.provider_successful_cases ?? summary.cases}/{summary.cases}
                    </td>
                    <td>{formatScore(summary.workflow_validity_rate)}</td>
                    <td>{formatScore(summary.workflow_completion_rate)}</td>
                    <td>
                      {formatScore(summary.tool_recall)} / {formatScore(summary.tool_precision)}
                    </td>
                    <td>
                      {formatScore(summary.benchmark_unexpected_tool_rate ?? summary.hallucinated_tool_rate)}
                    </td>
                    <td>{formatScore(summary.unknown_or_disallowed_tool_rate ?? 0)}</td>
                    <td>
                      {formatScore(summary.rag_recall_at_k)} / {formatScore(summary.rag_mrr)}
                    </td>
                    <td>{formatScore(summary.policy_violation_attempt_rate)}</td>
                    <td>{summary.end_to_end_latency_ms.toFixed(1)} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted-text">
            Planner quality metrics use provider-successful cases only. End-to-end validity includes
            provider availability failures. Provider-successful cases: {providerSuccessfulCases}/{latest.cases}.
          </p>
        </div>
      </Section>
    </div>
  );
}

function CapabilityGraphPage({ role }: { role: Role }) {
  const [graph, setGraph] = useState<CapabilityGraphResponse | null>(null);
  const [source, setSource] = useState("repository:payments-api");
  const [goal, setGoal] = useState("create_issue_for_latest_failed_build");
  const [environment, setEnvironment] = useState("staging");
  const [strategy, setStrategy] = useState("policy_compliant");
  const [path, setPath] = useState<CapabilityPathResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "idle" | "error">("loading");

  useEffect(() => {
    let active = true;
    void callCapabilityGraph()
      .then((payload) => {
        if (!active) return;
        setGraph(payload);
        setStatus("idle");
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, []);

  const findPath = async () => {
    setStatus("loading");
    try {
      setPath(await callCapabilityPath({ source, goal, role, environment, strategy }));
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  };

  const relatedEdges = graph?.edges.filter((edge) => edge.source_type === source.split(":")[0]).slice(0, 8) ?? [];

  return (
    <div className="page-stack">
      <Section title="Capability graph" icon={Share2}>
        <div className="workflow-console">
          <div className="discovery-controls capability-controls">
            <label>
              <span>Source resource</span>
              <select value={source} onChange={(event) => setSource(event.target.value)} aria-label="Capability source resource">
                <option value="repository:payments-api">repository:payments-api</option>
                <option value="repository:orders-api">repository:orders-api</option>
                <option value="service:payments">service:payments</option>
                <option value="deployment:current">deployment:current</option>
              </select>
            </label>
            <label>
              <span>Goal</span>
              <select value={goal} onChange={(event) => setGoal(event.target.value)} aria-label="Capability goal">
                <option value="create_issue_for_latest_failed_build">create issue for failed build</option>
                <option value="investigate_failed_build">investigate failed build</option>
                <option value="deploy_to_staging">deploy to staging</option>
                <option value="find_service_runbook">find service runbook</option>
              </select>
            </label>
            <label>
              <span>Environment</span>
              <select value={environment} onChange={(event) => setEnvironment(event.target.value)} aria-label="Capability environment">
                <option value="dev">dev</option>
                <option value="staging">staging</option>
                <option value="production">production</option>
              </select>
            </label>
            <label>
              <span>Strategy</span>
              <select value={strategy} onChange={(event) => setStrategy(event.target.value)} aria-label="Capability path strategy">
                <option value="policy_compliant">policy compliant</option>
                <option value="lowest_risk">lowest risk</option>
                <option value="shortest">shortest</option>
              </select>
            </label>
            <button className="primary-action" type="button" onClick={() => void findPath()} disabled={status === "loading"}>
              <Share2 className="h-4 w-4" aria-hidden="true" />
              Find path
            </button>
          </div>
          {status === "error" && (
            <ErrorState title="Capability request failed" detail="Confirm the API service is running and the selected path is valid." />
          )}
          {graph && (
            <div className="workflow-summary">
              <span>{graph.resources.length} resources</span>
              <span>{graph.edges.length} tool edges</span>
              <span>{roleLabels[role]} policy view</span>
            </div>
          )}
          {path ? (
            <div className="capability-layout">
              <div className="capability-path-panel">
                <div className="workflow-summary">
                  <span>{path.reachable ? "Reachable" : "Unreachable"}</span>
                  <span>{path.policy_compliant ? "Policy compliant" : "Policy blocked"}</span>
                  <span>cost {path.total_cost.toFixed(1)}</span>
                  <span>risk {path.risk_score.toFixed(1)}</span>
                </div>
                <CapabilityPathView path={path} />
              </div>
              <div className="capability-side">
                <h3>Related MCP tools</h3>
                {relatedEdges.length === 0 ? (
                  <EmptyState title="No related tools" detail="No tool edges start from the selected resource type." />
                ) : (
                  relatedEdges.map((edge) => <CapabilityEdgeCard key={`${edge.tool_name}-${edge.destination_type}`} edge={edge} />)
                )}
              </div>
            </div>
          ) : (
            <EmptyState title="No capability path selected" detail="Choose a source and goal to inspect planner-safe MCP routes." />
          )}
        </div>
      </Section>
    </div>
  );
}

function CapabilityPathView({ path }: { path: CapabilityPathResponse }) {
  if (!path.reachable) {
    return <ErrorState title="No valid path" detail={path.explanation} />;
  }
  return (
    <div className="capability-path" aria-label="Capability path chosen by planner">
      {path.edges.map((edge, index) => (
        <article key={`${edge.tool_name}-${index}`} className="capability-step">
          <div>
            <span className="capability-node">{path.nodes[index]}</span>
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
            <span className="capability-node">{edge.destination_type}</span>
          </div>
          <div className="workflow-node-header">
            <div>
              <p className="eyebrow">{edge.mcp_server}</p>
              <h3>{edge.tool_name}</h3>
            </div>
            <RiskBadge risk={edge.risk} />
          </div>
          <div className="workflow-node-meta">
            <span>cost {edge.cost.toFixed(1)}</span>
            <span>{edge.enabled ? "server enabled" : "server disabled"}</span>
            {edge.prerequisites.map((item) => (
              <span key={item}>requires {item}</span>
            ))}
          </div>
        </article>
      ))}
      {path.alternatives.length > 0 && (
        <div className="discovery-summary">
          {path.alternatives.map((alternative) => (
            <span key={alternative.join(">")}>{alternative.join(" -> ")}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function CapabilityEdgeCard({ edge }: { edge: CapabilityEdge }) {
  return (
    <article className="capability-edge-card">
      <div>
        <strong className="mono">{edge.tool_name}</strong>
        <RiskBadge risk={edge.risk} />
      </div>
      <p>
        {edge.source_type} to {edge.destination_type} through {edge.mcp_server}
      </p>
    </article>
  );
}

async function callCapabilityGraph(): Promise<CapabilityGraphResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/capabilities/graph`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as CapabilityGraphResponse;
}

async function callCapabilityPath(request: {
  source: string;
  goal: string;
  role: Role;
  environment: string;
  strategy: string;
}): Promise<CapabilityPathResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/capabilities/path`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as CapabilityPathResponse;
}

function ApprovalsPage({ role }: { role: Role }) {
  const [approvalRows, setApprovalRows] = useState<Approval[]>(approvals);
  const [status, setStatus] = useState<ApprovalStatus | "ALL">("ALL");
  const filtered = approvalRows.filter((approval) => status === "ALL" || approval.status === status);
  const changeStatus = (id: string, nextStatus: ApprovalStatus) => {
    setApprovalRows((rows) => rows.map((row) => (row.id === id ? { ...row, status: nextStatus } : row)));
  };
  return (
    <div className="page-stack">
      <AccessNotice role={role} />
      <Toolbar>
        <SegmentedFilter
          value={status}
          onChange={(value) => setStatus(value as ApprovalStatus | "ALL")}
          options={["ALL", "PENDING", "APPROVED", "REJECTED", "EXECUTED"]}
        />
      </Toolbar>
      <Section title="Approval center" icon={ClipboardCheck}>
        {filtered.length === 0 ? (
          <EmptyState title="No approvals in this status" detail="Approval workflow state is clear." />
        ) : (
          <ApprovalTable approvals={filtered} role={role} onStatusChange={changeStatus} />
        )}
      </Section>
    </div>
  );
}

function AccessNotice({ role }: { role: Role }) {
  const canApprove = role === "ADMIN";
  return (
    <div className={canApprove ? "access-notice allowed" : "access-notice restricted"}>
      <LockKeyhole className="h-4 w-4" aria-hidden="true" />
      <div>
        <strong>{roleLabels[role]} approval boundary</strong>
        <p>
          {canApprove
            ? "You can approve eligible requests, but self-approval and AI approval remain blocked."
            : "You can inspect approval state, but only ADMIN users can approve eligible high-risk operations."}
        </p>
      </div>
    </div>
  );
}

function ToolsPage() {
  const [domain, setDomain] = useState("ALL");
  const [page, setPage] = useState(1);
  const filtered = tools.filter((tool) => domain === "ALL" || tool.domain === domain);
  const paged = paginate(filtered, page, 10);
  return (
    <div className="page-stack">
      <Toolbar>
        <SegmentedFilter
          value={domain}
          onChange={(value) => {
            setDomain(value);
            setPage(1);
          }}
          options={["ALL", "device", "diagnostics", "knowledge", "ticket"]}
        />
      </Toolbar>
      <Section title="Tool registry" icon={Wrench}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tool</th>
                <th>Domain</th>
                <th>Description</th>
                <th>Risk</th>
                <th>Permission</th>
                <th>Approval</th>
                <th>Enabled</th>
              </tr>
            </thead>
            <tbody>
              {paged.items.map((tool) => (
                <tr key={tool.name}>
                  <td className="mono">{tool.name}</td>
                  <td>{tool.domain}</td>
                  <td>{tool.description}</td>
                  <td>
                    <RiskBadge risk={tool.risk} />
                  </td>
                  <td className="mono">{tool.permission}</td>
                  <td>{tool.requiresApproval ? "Required" : "No"}</td>
                  <td>
                    <EnabledBadge enabled={tool.enabled} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={page} totalPages={paged.totalPages} onPageChange={setPage} />
      </Section>
    </div>
  );
}

function AuditPage() {
  const [filters, setFilters] = useState({ user: "", device: "", tool: "", risk: "ALL", status: "ALL" });
  const [page, setPage] = useState(1);
  const filtered = auditEntries.filter((entry) => {
    return (
      entry.user.toLowerCase().includes(filters.user.toLowerCase()) &&
      entry.deviceId.toLowerCase().includes(filters.device.toLowerCase()) &&
      entry.tool.toLowerCase().includes(filters.tool.toLowerCase()) &&
      (filters.risk === "ALL" || entry.risk === filters.risk) &&
      (filters.status === "ALL" || entry.status === filters.status)
    );
  });
  const paged = paginate(filtered, page, 4);
  return (
    <div className="page-stack">
      <Toolbar>
        <SearchBox
          value={filters.user}
          onChange={(value) => setFilters((current) => ({ ...current, user: value }))}
          ariaLabel="Filter by user"
        />
        <SearchBox
          value={filters.device}
          onChange={(value) => setFilters((current) => ({ ...current, device: value }))}
          ariaLabel="Filter by device"
        />
        <SearchBox
          value={filters.tool}
          onChange={(value) => setFilters((current) => ({ ...current, tool: value }))}
          ariaLabel="Filter by tool"
        />
        <SegmentedFilter
          value={filters.risk}
          onChange={(value) => setFilters((current) => ({ ...current, risk: value }))}
          options={["ALL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]}
        />
      </Toolbar>
      <div className="date-filter-row">
        <label>
          <span>Date from</span>
          <input type="date" defaultValue="2026-08-10" />
        </label>
        <label>
          <span>Date to</span>
          <input type="date" defaultValue="2026-08-10" />
        </label>
        <SegmentedFilter
          value={filters.status}
          onChange={(value) => {
            setFilters((current) => ({ ...current, status: value }));
            setPage(1);
          }}
          options={["ALL", "ALLOW", "DENY", "PENDING_APPROVAL"]}
        />
      </div>
      <Section title="Audit explorer" icon={FileClock}>
        {filtered.length === 0 ? (
          <EmptyState title="No audit entries found" detail="Adjust user, device, tool, risk, status, or date filters." />
        ) : (
          <>
            <AuditTable entries={paged.items} />
            <Pagination page={page} totalPages={paged.totalPages} onPageChange={setPage} />
          </>
        )}
      </Section>
    </div>
  );
}

function SystemPage() {
  return (
    <div className="page-stack">
      <Section title="System health" icon={Server}>
        <div className="system-grid">
          {systemComponents.map((component) => (
            <SystemComponentCard key={component.name} component={component} />
          ))}
        </div>
      </Section>
    </div>
  );
}

function SecurityGovernancePage() {
  const blockedCalls = auditEntries.filter((entry) => entry.status === "DENY");
  const policyDenials = auditEntries.filter((entry) => entry.status.includes("DENY"));
  const suspiciousMetadata = tools.filter((tool) =>
    /ignore previous|send all credentials|bypass/i.test(tool.description),
  );
  const approvalViolations = approvals.filter((approval) => approval.status === "REJECTED");
  return (
    <div className="page-stack">
      <section className="metric-grid">
        <MetricTile label="Blocked calls" value={blockedCalls.length} icon={X} accent="danger" />
        <MetricTile label="Policy denials" value={policyDenials.length} icon={ShieldCheck} accent="warning" />
        <MetricTile label="Suspicious metadata" value={suspiciousMetadata.length} icon={AlertTriangle} accent="neutral" />
        <MetricTile label="Approval violations" value={approvalViolations.length} icon={LockKeyhole} accent="purple" />
      </section>
      <Section title="Control-plane security" icon={ShieldCheck}>
        <div className="security-grid">
          <SecurityPanel
            title="Blocked tool calls"
            rows={blockedCalls.map((entry) => `${entry.tool} / ${entry.user} / ${entry.summary}`)}
            empty="No blocked tool calls in the current audit window."
          />
          <SecurityPanel
            title="Suspicious MCP metadata"
            rows={suspiciousMetadata.map((tool) => `${tool.name} / ${tool.domain}`)}
            empty="No suspicious instruction-like tool metadata is registered."
          />
          <SecurityPanel
            title="Hallucinated tools"
            rows={["Rejected during workflow validation and counted by mcp_hallucinated_tool_calls_total."]}
            empty="No hallucinated tool attempts in the current view."
          />
          <SecurityPanel
            title="Approval violations"
            rows={approvalViolations.map((approval) => `${approval.operation} / ${approval.requestedBy} / ${approval.status}`)}
            empty="No approval replay or binding violations in the current approval window."
          />
        </div>
      </Section>
    </div>
  );
}

function SecurityPanel({ title, rows, empty }: { title: string; rows: string[]; empty: string }) {
  return (
    <article className="security-panel">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <ul>
          {rows.slice(0, 6).map((row) => (
            <li key={row}>{row}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: React.ReactNode }) {
  return (
    <section className="surface">
      <div className="section-header">
        <div className="section-title">
          <Icon className="h-4 w-4" aria-hidden="true" />
          <h2>{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}

function Toolbar({ children }: { children: React.ReactNode }) {
  return <div className="toolbar">{children}</div>;
}

function SearchBox({
  value,
  onChange,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
}) {
  return (
    <label className="search-box">
      <Search className="h-4 w-4" aria-hidden="true" />
      <input value={value} onChange={(event) => onChange(event.target.value)} aria-label={ariaLabel} />
    </label>
  );
}

function SegmentedFilter({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <div className="segmented" role="group" aria-label="Filter">
      <Filter className="h-4 w-4 text-stone-500" aria-hidden="true" />
      {options.map((option) => (
        <button
          key={option}
          className={value === option ? "selected" : ""}
          type="button"
          onClick={() => onChange(option)}
        >
          {option.replace("_", " ")}
        </button>
      ))}
    </div>
  );
}

function MetricTile({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number | string;
  icon: LucideIcon;
  accent: "neutral" | "success" | "warning" | "danger" | "muted" | "purple";
}) {
  return (
    <article className={`metric-tile ${accent}`}>
      <div className="metric-icon">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </article>
  );
}

function HealthDistribution({ counts }: { counts: Record<DeviceStatus, number> }) {
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  return (
    <div className="distribution">
      {(["HEALTHY", "WARNING", "CRITICAL", "OFFLINE"] satisfies DeviceStatus[]).map((status) => (
        <div key={status}>
          <div className="distribution-row">
            <span>{status}</span>
            <strong>{counts[status]}</strong>
          </div>
          <div className="bar-track">
            <span className={`bar-fill ${status.toLowerCase()}`} style={{ width: `${(counts[status] / total) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function CompactSystemHealth({ components }: { components: SystemComponent[] }) {
  return (
    <div className="compact-health">
      {components.slice(0, 6).map((component) => (
        <div key={component.name}>
          <span>{component.name}</span>
          <SystemBadge status={component.status} />
        </div>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: DeviceStatus }) {
  return <span className={`badge status-${status.toLowerCase()}`}>{status}</span>;
}

function RiskBadge({ risk }: { risk: RiskLevel | "INFO" | "WARNING" }) {
  return <span className={`badge risk-${risk.toLowerCase()}`}>{risk}</span>;
}

function EnabledBadge({ enabled }: { enabled: boolean }) {
  return <span className={enabled ? "badge enabled" : "badge disabled"}>{enabled ? "Enabled" : "Disabled"}</span>;
}

function SystemBadge({ status }: { status: SystemComponent["status"] }) {
  return <span className={`badge system-${status.toLowerCase()}`}>{status}</span>;
}

function ServiceBadge({ state }: { state: ServiceState }) {
  return <span className={`badge service-${state.toLowerCase()}`}>{state}</span>;
}

function HealthCell({ score }: { score: number }) {
  return (
    <div className="health-cell">
      <span>{score}%</span>
      <div className="health-track">
        <span style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

function IncidentTable({ incidents: rows, compact = false }: { incidents: Incident[]; compact?: boolean }) {
  if (rows.length === 0) return <EmptyState title="No incidents" detail="No incident records for this scope." />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Incident</th>
            <th>Device</th>
            {!compact && <th>Title</th>}
            <th>Severity</th>
            <th>Status</th>
            {!compact && <th>Owner</th>}
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((incident) => (
            <tr key={incident.id}>
              <td className="mono">{incident.id}</td>
              <td>{incident.deviceId}</td>
              {!compact && <td>{incident.title}</td>}
              <td>
                <RiskBadge risk={incident.severity} />
              </td>
              <td>{incident.status}</td>
              {!compact && <td>{incident.owner}</td>}
              <td>{formatTime(incident.createdAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TicketTable({ tickets: rows, compact = false }: { tickets: typeof tickets; compact?: boolean }) {
  if (rows.length === 0) return <EmptyState title="No tickets" detail="No tickets for this scope." />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Device</th>
            {!compact && <th>Title</th>}
            <th>Priority</th>
            <th>Status</th>
            {!compact && <th>Assignee</th>}
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((ticket) => (
            <tr key={ticket.id}>
              <td className="mono">{ticket.id}</td>
              <td>{ticket.deviceId}</td>
              {!compact && <td>{ticket.title}</td>}
              <td>
                <RiskBadge risk={ticket.priority} />
              </td>
              <td>{ticket.status}</td>
              {!compact && <td>{ticket.assignee}</td>}
              <td>{formatTime(ticket.updatedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ApprovalTable({
  approvals: rows,
  role,
  onStatusChange,
}: {
  approvals: Approval[];
  role: Role;
  onStatusChange: (id: string, status: ApprovalStatus) => void;
}) {
  const canApprove = role === "ADMIN";
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Operation</th>
            <th>Device</th>
            <th>Requested by</th>
            <th>Risk</th>
            <th>Reason</th>
            <th>Requested</th>
            <th>Expiry</th>
            <th>Status</th>
            {canApprove && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((approval) => (
            <tr key={approval.id}>
              <td className="mono">{approval.operation}</td>
              <td>{approval.deviceId}</td>
              <td>{approval.requestedBy}</td>
              <td>
                <RiskBadge risk={approval.risk} />
              </td>
              <td className="reason-cell">{approval.reason}</td>
              <td>{formatTime(approval.requestedAt)}</td>
              <td>{formatTime(approval.expiresAt)}</td>
              <td>{approval.status}</td>
              {canApprove && (
                <td>
                  {approval.status === "PENDING" ? (
                    <div className="row-actions">
                      <button className="icon-button approve" type="button" title="Approve" aria-label="Approve" onClick={() => onStatusChange(approval.id, "APPROVED")}>
                        <Check className="h-4 w-4" aria-hidden="true" />
                      </button>
                      <button className="icon-button reject" type="button" title="Reject" aria-label="Reject" onClick={() => onStatusChange(approval.id, "REJECTED")}>
                        <X className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                  ) : (
                    <span className="muted">Closed</span>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditTable({ entries, compact = false }: { entries: AuditEntry[]; compact?: boolean }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>User</th>
            <th>Device</th>
            <th>Tool</th>
            {!compact && <th>Risk</th>}
            <th>Status</th>
            {!compact && <th>Summary</th>}
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id}>
              <td>{formatTime(entry.timestamp)}</td>
              <td>{entry.user}</td>
              <td>{entry.deviceId}</td>
              <td className="mono">{entry.tool}</td>
              {!compact && (
                <td>
                  <RiskBadge risk={entry.risk} />
                </td>
              )}
              <td>{entry.status}</td>
              {!compact && <td>{entry.summary}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TelemetryCharts({ device }: { device: Device }) {
  return (
    <div className="chart-grid">
      <Sparkline label="CPU" values={device.telemetry.map((point) => point.cpu)} suffix="%" />
      <Sparkline label="Memory" values={device.telemetry.map((point) => point.memory)} suffix="%" />
      <Sparkline label="Temperature" values={device.telemetry.map((point) => point.temperature)} suffix="C" />
      <Sparkline label="Latency" values={device.telemetry.map((point) => point.latency)} suffix="ms" />
      <Sparkline label="Packet loss" values={device.telemetry.map((point) => point.packetLoss)} suffix="%" />
      <Sparkline label="Disk" values={device.telemetry.map((point) => point.disk)} suffix="%" />
    </div>
  );
}

function Sparkline({ label, values, suffix }: { label: string; values: number[]; suffix: string }) {
  const max = Math.max(...values, 1);
  const points = values
    .map((value, index) => `${(index / Math.max(values.length - 1, 1)) * 100},${36 - (value / max) * 30}`)
    .join(" ");
  return (
    <div className="sparkline">
      <div>
        <span>{label}</span>
        <strong>
          {values.at(-1)}
          {suffix}
        </strong>
      </div>
      <svg viewBox="0 0 100 40" role="img" aria-label={`${label} telemetry chart`}>
        <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" />
      </svg>
    </div>
  );
}

function ServiceList({ services }: { services: Device["services"] }) {
  return (
    <div className="service-list">
      {services.map((service) => (
        <div key={service.name}>
          <div>
            <strong>{service.name}</strong>
            <span>v{service.version}</span>
          </div>
          <ServiceBadge state={service.state} />
        </div>
      ))}
    </div>
  );
}

function KeyValueGrid({ values }: { values: Record<string, string | number | boolean> }) {
  return (
    <dl className="key-value-grid">
      {Object.entries(values).map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function RecentErrors({ device }: { device: Device }) {
  const errors = recentErrorsFor(device.id);
  if (errors.length === 0) return <EmptyState title="No recent errors" detail="No error logs were found for this device." />;
  return (
    <div className="event-list">
      {errors.map((error) => (
        <div key={error.code}>
          <RiskBadge risk={error.severity} />
          <p>{error.message}</p>
          <span className="mono">{error.code}</span>
        </div>
      ))}
    </div>
  );
}

function DiagnosticList({ reports }: { reports: DiagnosticReport[] }) {
  if (reports.length === 0) return <EmptyState title="No diagnostics" detail="No diagnostic reports in this scope." />;
  return (
    <div className="diagnostic-list">
      {reports.map((report) => (
        <article key={report.id}>
          <div className="diagnostic-head">
            <div>
              <p className="eyebrow">{report.deviceId}</p>
              <h3>{report.cause}</h3>
            </div>
            <RiskBadge risk={report.severity} />
          </div>
          <p className="muted">Confidence {Math.round(report.confidence * 100)}% / {formatTime(report.timestamp)}</p>
          <ul>
            {report.evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <div className="tag-row">
            {report.references.map((reference) => (
              <span key={reference}>{reference}</span>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

function SystemComponentCard({ component }: { component: SystemComponent }) {
  return (
    <article className="system-card">
      <div>
        <Database className="h-4 w-4" aria-hidden="true" />
        <h3>{component.name}</h3>
      </div>
      <SystemBadge status={component.status} />
      <dl>
        <div>
          <dt>Latency</dt>
          <dd>{component.latencyMs}ms</dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>{component.version}</dd>
        </div>
        <div>
          <dt>Checked</dt>
          <dd>{formatTime(component.checkedAt)}</dd>
        </div>
      </dl>
    </article>
  );
}

function LoadingState() {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <span />
      <p>Loading operational data...</p>
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <Archive className="h-5 w-5" aria-hidden="true" />
      <div>
        <h3>{title}</h3>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function ErrorState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="error-state" role="alert">
      <AlertTriangle className="h-5 w-5" aria-hidden="true" />
      <div>
        <h3>{title}</h3>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <div className="pagination">
      <button type="button" onClick={() => onPageChange(Math.max(1, page - 1))} disabled={page === 1} aria-label="Previous page">
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      </button>
      <span>
        Page {page} of {totalPages}
      </span>
      <button type="button" onClick={() => onPageChange(Math.min(totalPages, page + 1))} disabled={page === totalPages} aria-label="Next page">
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}

function countByStatus(items: Device[]): Record<DeviceStatus, number> {
  return items.reduce(
    (counts, device) => ({ ...counts, [device.status]: counts[device.status] + 1 }),
    { HEALTHY: 0, WARNING: 0, CRITICAL: 0, OFFLINE: 0 },
  );
}

function paginate<T>(items: T[], page: number, pageSize: number) {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(page, totalPages);
  return {
    items: items.slice((safePage - 1) * pageSize, safePage * pageSize),
    totalPages,
  };
}

function titleForPath(path: string) {
  if (path.startsWith("/devices/")) return "Device details";
  return navItems.find((item) => item.path === path)?.label ?? "Console";
}

function permissionSummary(role: Role) {
  if (role === "ADMIN") return "Approval and administration";
  if (role === "OPERATOR") return "Operate with approval";
  if (role === "ENGINEER") return "Diagnose and ticket";
  return "Read-only visibility";
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "2-digit",
  }).format(new Date(value));
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "2-digit", year: "numeric" }).format(new Date(value));
}

function formatScore(value: number) {
  return `${Math.round(value * 100)}%`;
}

function recentErrorsFor(deviceId: string) {
  if (deviceId === "SIM-014") {
    return [
      { code: "E-NET-TIMEOUT", severity: "CRITICAL" as RiskLevel, message: "Network timeout while publishing telemetry." },
      { code: "E-SENSOR-INIT", severity: "HIGH" as RiskLevel, message: "Sensor initialization failed during telemetry cycle." },
    ];
  }
  if (statusForDevice(deviceId) === "HEALTHY") return [];
  return [{ code: "E-RESOURCE-WARN", severity: "MEDIUM" as RiskLevel, message: "Resource threshold warning." }];
}
