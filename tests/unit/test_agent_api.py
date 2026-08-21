from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from mcp_ops_api import main as api_main
from mcp_ops_api.main import app


def test_agent_chat_endpoint_answers_with_role_context() -> None:
    client = TestClient(app)

    response = client.post(
        "/agent/chat",
        json={"message": "What is the fleet health?", "role": "VIEWER"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["intent"] == "ANSWER_QUESTION"
    assert payload["authorization"]["role"] == "VIEWER"
    assert payload["trace"]


def test_api_ready_reports_dependency_and_mcp_component_status() -> None:
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ready", "degraded"}
    assert "postgresql" in payload["components"]
    assert "redis" in payload["components"]
    assert "kafka" in payload["components"]
    assert "opensearch" in payload["components"]
    assert "device-mcp" in payload["components"]


def test_api_validation_errors_use_structured_error_schema() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/ai/tool-discovery", json={"query": ""})

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["details"]


def test_agent_chat_endpoint_enforces_role_for_tasks() -> None:
    client = TestClient(app)

    response = client.post(
        "/agent/chat",
        json={"message": "Restart SIM-014 service.", "role": "VIEWER"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "permission_denied" in payload["message"]


def test_agent_evaluation_endpoint_reports_benchmark_metrics() -> None:
    client = TestClient(app)

    response = client.get("/agent/evaluate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cases"] == 4
    assert payload["intent_accuracy"] == 1.0
    assert payload["hallucinated_tool_calls"] == 0


def test_tool_discovery_endpoint_returns_policy_filtered_ranked_tools() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/ai/tool-discovery",
        json={"query": "Why did the latest deployment fail?", "top_k": 5, "role": "ENGINEER"},
    )

    assert response.status_code == 200
    payload = response.json()
    names = [tool["name"] for tool in payload["ranked_tools"]]
    assert payload["role"] == "ENGINEER"
    assert "get_deployment_status" in names or "compare_deployments" in names
    assert all(tool["authorization_status"] == "authorized" for tool in payload["ranked_tools"])


def test_tool_discovery_endpoint_excludes_unauthorized_viewer_operations() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/ai/tool-discovery",
        json={"query": "Restart SIM-014 service.", "top_k": 8, "role": "VIEWER"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "restart_service" not in [tool["name"] for tool in payload["ranked_tools"]]
    assert payload["filtered_out_unauthorized"] >= 1


def test_production_tool_discovery_requires_bearer_identity(
    monkeypatch: Any,
) -> None:
    client = TestClient(app)
    monkeypatch.setattr(api_main.settings, "environment", "production")

    response = client.post(
        "/api/v1/ai/tool-discovery",
        json={"query": "Restart SIM-014 service.", "top_k": 8, "role": "ADMIN"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Missing bearer token."


def test_production_tool_discovery_uses_jwt_role_not_request_role(
    monkeypatch: Any,
) -> None:
    client = TestClient(app)
    monkeypatch.setattr(api_main.settings, "environment", "production")
    monkeypatch.setattr(api_main.settings, "jwt_issuer", "https://issuer.example.internal")
    monkeypatch.setattr(api_main.settings, "jwt_audience", "mcp-engineering-ops")
    monkeypatch.setattr(api_main.settings, "jwt_secret_key", "enterprise-secret")
    token = _jwt(
        {
            "iss": api_main.settings.jwt_issuer,
            "aud": api_main.settings.jwt_audience,
            "sub": "viewer-123",
            "role": "VIEWER",
            "principal_type": "HUMAN",
            "exp": _future_timestamp(),
        },
        api_main.settings.jwt_secret_key,
    )

    response = client.post(
        "/api/v1/ai/tool-discovery",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "Restart SIM-014 service.", "top_k": 8, "role": "ADMIN"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "VIEWER"
    assert "restart_service" not in [tool["name"] for tool in payload["ranked_tools"]]


def test_workflow_plan_endpoint_returns_validated_dag_without_execution() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/workflows/plan",
        json={
            "user_request": (
                "Check why the latest build failed and create a ticket if the problem "
                "comes from our code."
            ),
            "role": "ENGINEER",
            "created_by": "engineer",
            "top_k": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["workflow"]["status"] == "VALIDATED"
    assert payload["workflow"]["nodes"]
    assert all(node["execution_status"] == "PENDING" for node in payload["workflow"]["nodes"])


def test_workflow_get_and_cancel_endpoints_return_persisted_state() -> None:
    client = TestClient(app)
    planned = client.post(
        "/api/v1/workflows/plan",
        json={
            "user_request": "Create a maintenance ticket for SIM-014.",
            "role": "ENGINEER",
            "created_by": "engineer",
        },
    ).json()
    workflow_id = planned["workflow"]["id"]

    loaded = client.get(f"/api/v1/workflows/{workflow_id}")
    cancelled = client.post(f"/api/v1/workflows/{workflow_id}/cancel")

    assert loaded.status_code == 200
    assert loaded.json()["workflow"]["id"] == workflow_id
    assert cancelled.status_code == 200
    assert cancelled.json()["workflow"]["status"] == "CANCELLED"
    assert any(
        event["event_type"] == "workflow.cancelled"
        for event in cancelled.json()["workflow"]["audit_events"]
    )


def test_capability_graph_endpoint_returns_resources_and_edges() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/capabilities/graph")

    assert response.status_code == 200
    payload = response.json()
    assert payload["resources"]
    assert payload["edges"]
    assert any(edge["tool_name"] == "get_build_status" for edge in payload["edges"])


def test_capability_path_endpoint_returns_policy_compliant_route() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/capabilities/path",
        json={
            "source": "repository:payments-api",
            "goal": "create_issue_for_latest_failed_build",
            "role": "OPERATOR",
            "environment": "staging",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reachable"] is True
    assert payload["policy_compliant"] is True
    assert "create_ticket" in payload["tools"]


def test_capability_evaluation_endpoint_compares_planning_modes() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/capabilities/evaluate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cases"] >= 4
    assert payload["graph_hallucinated_tool_rate"] == 0.0


def test_engineering_knowledge_search_endpoint_returns_rag_evidence() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/knowledge/search",
        json={
            "query": "Deploy payments-api to staging",
            "top_k": 5,
            "mode": "hybrid",
            "environment": "staging",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    citations = [result["citation_id"] for result in payload["results"]]
    assert payload["mode"] == "hybrid"
    assert "PAYMENTS-DEPLOY-03" in citations


def test_engineering_knowledge_evaluation_endpoint_compares_modes() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/knowledge/evaluate")

    assert response.status_code == 200
    payload = response.json()
    assert {"bm25", "vector", "hybrid"} <= set(payload)
    assert payload["hybrid"]["cases"] >= 10


def test_evaluation_latest_endpoint_returns_generated_summary() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/evaluation/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["mode"] in {"mock", "real"}
    assert any(summary["config"] == "semantic_rag_graph" for summary in payload["summaries"])


def _future_timestamp() -> int:
    return int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())


def _jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = _b64(header) + "." + _b64(payload)
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256)
    return signing_input + "." + base64.urlsafe_b64encode(signature.digest()).decode().rstrip("=")


def _b64(value: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
