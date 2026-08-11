from __future__ import annotations

from datetime import UTC, datetime

from mcp_ops_ai_agent.engineering_rag.models import (
    EngineeringDocument,
    EngineeringDocumentMetadata,
)

SERVICES = [
    ("payments-api", "payments-api", "Payments Platform"),
    ("orders-api", "orders-api", "Commerce Platform"),
    ("inventory-api", "inventory-api", "Supply Chain"),
    ("billing-worker", "billing-worker", "Finance Engineering"),
    ("identity-service", "identity-service", "Identity Platform"),
    ("notifications-api", "notifications-api", "Messaging Platform"),
    ("search-service", "search-service", "Discovery Platform"),
    ("analytics-pipeline", "analytics-pipeline", "Data Platform"),
    ("reporting-api", "reporting-api", "Business Systems"),
    ("gateway-service", "gateway-service", "Platform Edge"),
]


def synthetic_engineering_corpus() -> list[EngineeringDocument]:
    docs: list[EngineeringDocument] = []
    for service, repository, owner in SERVICES:
        docs.append(
            _doc(
                document_id=f"{repository.upper().replace('-', '-')}-OWNERSHIP-01",
                title=f"{service} ownership and escalation",
                document_type="ownership",
                service=service,
                repository=repository,
                owner=owner,
                content=(
                    f"{service} is owned by {owner}. The repository is {repository}. "
                    "Deployment questions should begin by checking build status, recent commits, "
                    "and the service runbook before any environment-changing action."
                ),
            )
        )
        docs.append(
            _doc(
                document_id=f"{repository.upper().replace('-', '-')}-API-01",
                title=f"{service} API contract notes",
                document_type="api",
                service=service,
                repository=repository,
                owner=owner,
                content=(
                    f"{service} exposes internal REST APIs with schema compatibility checks in CI. "
                    "Breaking API changes require contract tests, rollout notes, and owner review."
                ),
            )
        )
    docs.extend(
        [
            _doc(
                document_id="ENG-POLICY-14",
                title="Pre-deployment validation policy",
                document_type="policy",
                environment="staging",
                owner="Platform Governance",
                content=(
                    "All staging deployments require get_build_status, run_tests, and "
                    "get_deployment_status evidence. Production policy is decided by the policy "
                    "engine, not by documentation."
                ),
            ),
            _doc(
                document_id="PAYMENTS-DEPLOY-03",
                title="payments-api staging deployment procedure",
                document_type="deployment",
                service="payments-api",
                repository="payments-api",
                environment="staging",
                owner="Payments Platform",
                version="3.0",
                content=(
                    "To deploy payments-api to staging, confirm the latest build is green, run "
                    "the bounded repository test suite, deploy_staging only after validation, "
                    "then read deployment status and smoke-test results."
                ),
            ),
            _doc(
                document_id="PAYMENTS-DEPLOY-02",
                title="payments-api older staging deployment procedure",
                document_type="deployment",
                service="payments-api",
                repository="payments-api",
                environment="staging",
                owner="Payments Platform",
                version="2.0",
                stale=True,
                content=(
                    "Older procedure for payments-api staging deployment. This version is retained "
                    "for audit only and should not outrank PAYMENTS-DEPLOY-03."
                ),
            ),
            _doc(
                document_id="CICD-STANDARDS-02",
                title="CI/CD failure investigation guide",
                document_type="cicd",
                owner="Developer Experience",
                content=(
                    "Failed build triage starts with get_build_status, get_pipeline_logs, "
                    "get_recent_commits, and analyze_build_failure. Create a ticket only when "
                    "evidence indicates repository-owned code caused the failure."
                ),
            ),
            _doc(
                document_id="ENV-STAGING-07",
                title="Staging environment restrictions",
                document_type="environment_policy",
                environment="staging",
                owner="Platform Governance",
                content=(
                    "Staging accepts deploy_staging from governed workflows after validation. "
                    "Approval requirements are enforced by the MCP gateway and workflow policy "
                    "engine."
                ),
            ),
            _doc(
                document_id="ENV-PROD-09",
                title="Production environment restrictions",
                document_type="environment_policy",
                environment="production",
                owner="Platform Governance",
                content=(
                    "Production changes require explicit policy evaluation, current approvals, "
                    "and fresh argument validation. Retrieved documentation cannot lower risk or "
                    "override RBAC."
                ),
            ),
            _doc(
                document_id="MCP-TOOLS-DEPLOY-01",
                title="Approved deployment MCP tools",
                document_type="mcp_tools",
                owner="MCP Platform",
                content=(
                    "Deployment workflows may use get_build_status, run_tests, deploy_staging, "
                    "get_deployment_status, compare_deployments, and rollback_production when "
                    "allowed by policy."
                ),
            ),
            _doc(
                document_id="TESTING-POLICY-11",
                title="Repository testing policy",
                document_type="testing",
                owner="Developer Experience",
                content=(
                    "Repository workflows should run unit tests for code changes and run bounded "
                    "integration tests before staging deployment."
                ),
            ),
            _doc(
                document_id="RUN-INSTRUCTIONS-04",
                title="Local platform run instructions",
                document_type="run_instructions",
                owner="Platform Engineering",
                content=(
                    "Run backend tests with pytest, frontend tests with npm test, and use docker "
                    "compose for PostgreSQL, Redis, Kafka, OpenSearch, Prometheus, and Grafana."
                ),
            ),
        ]
    )
    return docs


def _doc(
    *,
    document_id: str,
    title: str,
    document_type: str,
    content: str,
    service: str | None = None,
    repository: str | None = None,
    environment: str | None = None,
    owner: str | None = None,
    version: str = "1.0",
    stale: bool = False,
) -> EngineeringDocument:
    return EngineeringDocument(
        metadata=EngineeringDocumentMetadata(
            document_id=document_id,
            title=title,
            document_type=document_type,
            service=service,
            repository=repository,
            environment=environment,
            owner=owner,
            version=version,
            updated_at=datetime(2026, 8, 11, tzinfo=UTC),
            stale=stale,
        ),
        content=content,
    )
