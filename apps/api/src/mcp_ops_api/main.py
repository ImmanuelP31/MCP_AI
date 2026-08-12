import json
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp_ops_ai_agent.capabilities import (
    CapabilityGraphService,
    compare_capability_constrained_planning,
)
from mcp_ops_ai_agent.capabilities.models import CapabilityPathRequest
from mcp_ops_ai_agent.engineering_rag import EngineeringRagService, evaluate_engineering_rag
from mcp_ops_ai_agent.engineering_rag.models import (
    EngineeringKnowledgeSearchRequest,
    KnowledgeFilters,
    KnowledgeSearchMode,
)
from mcp_ops_ai_agent.evaluation import evaluate_agent
from mcp_ops_ai_agent.provider import DeterministicMockProvider, GeminiChatProvider
from mcp_ops_ai_agent.service import AiEngineeringAgent
from mcp_ops_ai_agent.tool_discovery import ToolDiscoveryService, evaluate_tool_discovery
from mcp_ops_ai_agent.workflows.models import Workflow, WorkflowPlanRequest
from mcp_ops_ai_agent.workflows.planner import PlannerOutputError, workflow_planner_from_settings
from mcp_ops_ai_agent.workflows.service import WorkflowNotFoundError, WorkflowPlanningService
from mcp_ops_ai_agent.workflows.validator import WorkflowValidationError
from mcp_ops_auth.rbac import Role
from mcp_ops_common.config import get_settings
from mcp_ops_observability.fastapi import add_observability
from mcp_ops_observability.logging import configure_logging
from pydantic import BaseModel, ConfigDict, Field

from mcp_ops_api.db.repositories import WorkflowRepository
from mcp_ops_api.db.session import create_database_engine, create_session_factory
from mcp_ops_api.health import readiness_checks

configure_logging()

settings = get_settings()
provider = (
    GeminiChatProvider(settings)
    if settings.llm_provider.lower() == "gemini"
    else DeterministicMockProvider()
)
agent = AiEngineeringAgent(provider=provider)
tool_discovery = ToolDiscoveryService()
capability_graph = CapabilityGraphService()
engineering_rag = EngineeringRagService()


class SqlAlchemyWorkflowStore:
    def __init__(self) -> None:
        self.session_factory = create_session_factory(create_database_engine(settings))

    def save_workflow(self, workflow: Workflow) -> Workflow:
        with self.session_factory() as session:
            saved = WorkflowRepository(session).save_workflow(workflow)
            session.commit()
            return saved

    def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        with self.session_factory() as session:
            return WorkflowRepository(session).get_workflow(workflow_id)


workflow_repository = SqlAlchemyWorkflowStore() if settings.environment == "production" else None
workflow_service = WorkflowPlanningService(
    discovery=tool_discovery,
    capability_graph=capability_graph,
    rag=engineering_rag,
    planner=workflow_planner_from_settings(settings),
    repository=workflow_repository,
)

app = FastAPI(
    title="MCP Engineering Operations API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.state.agent = agent
add_observability(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiError(StrictModel):
    code: str
    message: str
    details: Any | None = None


class ApiErrorResponse(StrictModel):
    ok: bool = False
    error: ApiError


class AgentChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    role: Role


class AgentChatResponse(StrictModel):
    ok: bool
    intent: str
    message: str
    evidence: list[dict[str, Any]]
    data: dict[str, Any]
    approval_required: bool
    approval_id: str | None
    confidence: float
    escalation_required: bool
    escalation_reason: str | None
    selected_tools: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    authorization: dict[str, str]


class AgentEvaluationResponse(StrictModel):
    cases: int
    intent_accuracy: float
    tool_route_accuracy: float
    outcome_accuracy: float
    escalation_accuracy: float
    hallucinated_tool_calls: int
    tool_failure_rate: float


class ToolDiscoveryRequest(StrictModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=50)
    minimum_score: float = Field(default=0.0, ge=0.0, le=1.0)
    role: Role = Role.ENGINEER
    allowed_servers: list[str] = Field(default_factory=list, max_length=20)
    allowed_categories: list[str] = Field(default_factory=list, max_length=20)


class ToolDiscoveryResponse(StrictModel):
    query: str
    role: str
    ranked_tools: list[dict[str, Any]]
    filtered_out_unauthorized: int
    index_backend: str


class ToolDiscoveryEvaluationResponse(StrictModel):
    cases: int
    recall_at_k: float
    precision_at_k: float
    mrr: float


class WorkflowPlanApiRequest(StrictModel):
    user_request: str = Field(min_length=2, max_length=2000)
    role: Role = Role.ENGINEER
    created_by: str = Field(default="api-user", min_length=1, max_length=160)
    target_environment: str = Field(default="dev", min_length=1, max_length=64)
    top_k: int = Field(default=8, ge=1, le=50)


class WorkflowActionRequest(StrictModel):
    role: Role = Role.ENGINEER


class WorkflowApiResponse(StrictModel):
    ok: bool
    workflow: dict[str, Any]
    validation_issues: list[dict[str, Any]] = Field(default_factory=list)
    discovered_tools: list[dict[str, Any]] = Field(default_factory=list)
    capability_path: dict[str, Any] | None = None
    retrieved_knowledge: list[dict[str, Any]] = Field(default_factory=list)


class KnowledgeSearchApiRequest(StrictModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = Field(default="hybrid", pattern="^(bm25|vector|hybrid)$")
    minimum_score: float = Field(default=0.0, ge=0.0, le=1.0)
    document_type: str | None = Field(default=None, max_length=80)
    service: str | None = Field(default=None, max_length=120)
    repository: str | None = Field(default=None, max_length=120)
    environment: str | None = Field(default=None, max_length=64)
    include_stale: bool = False


class KnowledgeSearchApiResponse(StrictModel):
    query: str
    mode: str
    index_backend: str
    results: list[dict[str, Any]]


class EvaluationLatestResponse(StrictModel):
    available: bool
    mode: str | None = None
    generated_at: str | None = None
    dataset_path: str | None = None
    summaries: list[dict[str, Any]] = Field(default_factory=list)
    result_path: str | None = None


class CapabilityPathApiRequest(StrictModel):
    source: str = Field(min_length=1, max_length=180)
    goal: str = Field(min_length=1, max_length=180)
    role: Role = Role.ENGINEER
    environment: str = Field(default="dev", min_length=1, max_length=64)
    strategy: str = Field(default="policy_compliant", min_length=1, max_length=64)
    disabled_servers: list[str] = Field(default_factory=list, max_length=20)


ROLE_TOKENS: dict[Role, str] = {
    Role.VIEWER: "viewer-token",
    Role.ENGINEER: "engineer-token",
    Role.OPERATOR: "operator-token",
    Role.ADMIN: "admin-token",
}


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "live"}


@app.get("/ready", tags=["health"])
def ready() -> dict[str, Any]:
    return readiness_checks(settings)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    del request
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": {
                "code": f"http_{exc.status_code}",
                "message": message,
                "details": exc.detail if not isinstance(exc.detail, str) else None,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": exc.errors(),
            },
        },
    )


@app.post("/agent/chat", response_model=AgentChatResponse, tags=["agent"])
def agent_chat(request: AgentChatRequest) -> dict[str, Any]:
    """Run the governed LLM agent under the caller's authorization level."""

    response = agent.handle(
        request.message,
        user_auth_token=ROLE_TOKENS[request.role],
    )
    payload = response.as_payload()
    payload["authorization"] = {
        "role": request.role.value,
        "enforcement": "MCP gateway",
        "context_source": "server-side role mapping",
    }
    return payload


@app.get("/agent/evaluate", response_model=AgentEvaluationResponse, tags=["agent"])
def agent_evaluate() -> dict[str, float | int]:
    """Run deterministic agent evaluation benchmarks."""

    return evaluate_agent(agent).as_payload()


@app.post(
    "/api/v1/ai/tool-discovery",
    response_model=ToolDiscoveryResponse,
    tags=["agent"],
)
def ai_tool_discovery(request: ToolDiscoveryRequest) -> dict[str, Any]:
    """Retrieve a policy-filtered subset of MCP tools for planner context."""

    response = tool_discovery.retrieve(
        request.query,
        role=request.role.value,
        top_k=request.top_k,
        minimum_score=request.minimum_score,
        allowed_servers=set(request.allowed_servers),
        allowed_categories=set(request.allowed_categories),
    )
    return response.as_payload()


@app.get(
    "/api/v1/ai/tool-discovery/evaluate",
    response_model=ToolDiscoveryEvaluationResponse,
    tags=["agent"],
)
def ai_tool_discovery_evaluate(top_k: int = 5) -> dict[str, float | int]:
    """Evaluate semantic tool discovery against the engineering benchmark dataset."""

    return evaluate_tool_discovery(tool_discovery, top_k=top_k).as_payload()


@app.post(
    "/api/v1/workflows/plan",
    response_model=WorkflowApiResponse,
    tags=["workflows"],
)
def workflow_plan(request: WorkflowPlanApiRequest) -> dict[str, Any]:
    """Plan a typed engineering workflow DAG without executing it."""

    try:
        result = workflow_service.plan(
            WorkflowPlanRequest(
                user_request=request.user_request,
                created_by=request.created_by,
                role=request.role.value,
                target_environment=request.target_environment,
                top_k=request.top_k,
            )
        )
    except WorkflowValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[issue.model_dump(mode="json") for issue in exc.issues],
        ) from exc
    except PlannerOutputError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"code": "planner_output_invalid", "message": str(exc)}],
        ) from exc
    return result.as_payload()


@app.post(
    "/api/v1/knowledge/search",
    response_model=KnowledgeSearchApiResponse,
    tags=["knowledge"],
)
def engineering_knowledge_search(request: KnowledgeSearchApiRequest) -> dict[str, Any]:
    """Search engineering knowledge used as untrusted RAG evidence for workflow planning."""

    response = engineering_rag.search(
        EngineeringKnowledgeSearchRequest(
            query=request.query,
            top_k=request.top_k,
            mode=KnowledgeSearchMode(request.mode),
            minimum_score=request.minimum_score,
            filters=KnowledgeFilters(
                document_type=request.document_type,
                service=request.service,
                repository=request.repository,
                environment=request.environment,
                include_stale=request.include_stale,
            ),
        )
    )
    return response.as_payload()


@app.get("/api/v1/knowledge/evaluate", tags=["knowledge"])
def engineering_knowledge_evaluate(top_k: int = 5) -> dict[str, Any]:
    """Evaluate engineering RAG retrieval across BM25, vector, and hybrid modes."""

    return {
        mode.value: evaluate_engineering_rag(engineering_rag, mode=mode, top_k=top_k).as_payload()
        for mode in KnowledgeSearchMode
    }


@app.get(
    "/api/v1/evaluation/latest",
    response_model=EvaluationLatestResponse,
    tags=["evaluation"],
)
def evaluation_latest() -> dict[str, Any]:
    """Return the latest generated AI engineering workflow benchmark summary."""

    result_path = Path(__file__).resolve().parents[4] / "evaluation" / "results" / "latest.json"
    if not result_path.exists():
        return {
            "available": False,
            "summaries": [],
            "result_path": str(result_path),
        }
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    return {
        "available": True,
        "mode": payload.get("mode"),
        "generated_at": payload.get("generated_at"),
        "dataset_path": payload.get("dataset_path"),
        "summaries": payload.get("summaries", []),
        "result_path": str(result_path),
    }


@app.get(
    "/api/v1/workflows/{workflow_id}",
    response_model=WorkflowApiResponse,
    tags=["workflows"],
)
def workflow_get(workflow_id: UUID) -> dict[str, Any]:
    """Return workflow DAG state."""

    try:
        workflow = workflow_service.get_workflow(workflow_id)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found.") from exc
    return {"ok": True, "workflow": workflow.model_dump(mode="json")}


@app.post(
    "/api/v1/workflows/{workflow_id}/execute",
    response_model=WorkflowApiResponse,
    tags=["workflows"],
)
def workflow_execute(workflow_id: UUID, request: WorkflowActionRequest) -> dict[str, Any]:
    """Execute a previously planned workflow through the governed MCP gateway."""

    try:
        workflow = workflow_service.execute(workflow_id, role=request.role.value)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found.") from exc
    return {
        "ok": workflow.status not in {"FAILED", "CANCELLED"},
        "workflow": workflow.model_dump(mode="json"),
    }


@app.post(
    "/api/v1/workflows/{workflow_id}/resume",
    response_model=WorkflowApiResponse,
    tags=["workflows"],
)
def workflow_resume(workflow_id: UUID, request: WorkflowActionRequest) -> dict[str, Any]:
    """Resume workflow execution from the latest persisted checkpoint."""

    try:
        workflow = workflow_service.resume(workflow_id, role=request.role.value)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found.") from exc
    return {
        "ok": workflow.status not in {"FAILED", "CANCELLED"},
        "workflow": workflow.model_dump(mode="json"),
    }


@app.post(
    "/api/v1/workflows/{workflow_id}/retry/{node_id}",
    response_model=WorkflowApiResponse,
    tags=["workflows"],
)
def workflow_retry_node(
    workflow_id: UUID,
    node_id: str,
    request: WorkflowActionRequest,
) -> dict[str, Any]:
    """Retry one workflow node without replanning or restarting completed nodes."""

    try:
        workflow = workflow_service.retry_node(workflow_id, node_id, role=request.role.value)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow or node not found.") from exc
    return {
        "ok": workflow.status not in {"FAILED", "CANCELLED"},
        "workflow": workflow.model_dump(mode="json"),
    }


@app.post(
    "/api/v1/workflows/{workflow_id}/cancel",
    response_model=WorkflowApiResponse,
    tags=["workflows"],
)
def workflow_cancel(
    workflow_id: UUID,
    request: WorkflowActionRequest | None = None,
) -> dict[str, Any]:
    """Cancel a planned or running workflow."""

    try:
        role = request.role.value if request is not None else Role.ENGINEER.value
        workflow = workflow_service.cancel(workflow_id, role=role)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found.") from exc
    return {"ok": True, "workflow": workflow.model_dump(mode="json")}


@app.get("/api/v1/capabilities/graph", tags=["capabilities"])
def capability_graph_snapshot() -> dict[str, Any]:
    """Return the enterprise MCP capability graph."""

    return capability_graph.snapshot().as_payload()


@app.post("/api/v1/capabilities/path", tags=["capabilities"])
def capability_path(request: CapabilityPathApiRequest) -> dict[str, Any]:
    """Find a valid capability path between engineering resources and goals."""

    path = capability_graph.find_path(
        CapabilityPathRequest(
            source=request.source,
            goal=request.goal,
            role=request.role.value,
            environment=request.environment,
            strategy=request.strategy,
            disabled_servers=request.disabled_servers,
        )
    )
    return path.as_payload()


@app.get("/api/v1/capabilities/evaluate", tags=["capabilities"])
def capability_evaluate() -> dict[str, Any]:
    """Compare LLM-only planning with capability-graph-constrained planning."""

    return compare_capability_constrained_planning(capability_graph).as_payload()
