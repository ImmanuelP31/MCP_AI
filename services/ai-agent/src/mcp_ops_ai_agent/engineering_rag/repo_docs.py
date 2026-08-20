from __future__ import annotations

import fnmatch
from datetime import UTC, datetime
from pathlib import Path

from mcp_ops_ai_agent.engineering_rag.models import (
    EngineeringDocument,
    EngineeringDocumentMetadata,
)

ALLOWED_PATTERNS = (
    "README.md",
    "docs/*.md",
    "docs/architecture/*.md",
    "docs/architecture/decisions/*.md",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
)
EXCLUDED_PATTERNS = (
    "docs/resume/*",
    "**/.env",
    "**/.env.*",
    "**/node_modules/*",
    "**/dist/*",
)
MAX_DOCUMENT_BYTES = 200_000


def repository_engineering_documents(root: Path | None = None) -> list[EngineeringDocument]:
    """Load bounded repository documentation for engineering RAG.

    This is intentionally not a generic file reader. It only ingests known documentation and
    workflow files under the repository root, and it never reads secrets or user-provided paths.
    """

    repo_root = (root or _default_repo_root()).resolve()
    documents: list[EngineeringDocument] = []
    for path in sorted(_candidate_paths(repo_root)):
        if not _allowed(path, repo_root):
            continue
        content = _read_bounded_text(path)
        if not content.strip():
            continue
        documents.append(
            EngineeringDocument(
                metadata=_metadata_for(path, repo_root),
                content=content,
                format=_format_for(path),
            )
        )
    return documents


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _candidate_paths(root: Path) -> list[Path]:
    candidates: set[Path] = set()
    for pattern in ALLOWED_PATTERNS:
        candidates.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(candidates)


def _allowed(path: Path, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return False
    normalized = relative.as_posix()
    if any(fnmatch.fnmatch(normalized, pattern) for pattern in EXCLUDED_PATTERNS):
        return False
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in ALLOWED_PATTERNS)


def _read_bounded_text(path: Path) -> str:
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_DOCUMENT_BYTES]
    return path.read_text(encoding="utf-8", errors="replace")


def _metadata_for(path: Path, root: Path) -> EngineeringDocumentMetadata:
    relative = path.resolve().relative_to(root).as_posix()
    document_id = "REPO-" + _sanitize_identifier(relative)
    updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    document_type = _document_type(relative)
    return EngineeringDocumentMetadata(
        document_id=document_id,
        title=_title_for(relative),
        document_type=document_type,
        repository="MCP_AI",
        environment=_environment_for(relative),
        owner="engineering-platform",
        version="workspace",
        source=f"local-repository:{relative}",
        updated_at=updated_at,
        capability_categories=_capability_categories_for(relative, document_type),
    )


def _sanitize_identifier(relative: str) -> str:
    cleaned = "".join(character if character.isalnum() else "-" for character in relative.upper())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:120]


def _title_for(relative: str) -> str:
    stem = Path(relative).stem.replace("-", " ").replace("_", " ")
    if relative == "README.md":
        return "Repository README"
    if relative.startswith(".github/workflows/"):
        return f"GitHub Actions workflow: {stem}"
    return stem.title()


def _document_type(relative: str) -> str:
    if relative.startswith(".github/workflows/"):
        return "cicd_workflow"
    if "security" in relative or "threat-model" in relative:
        return "security_model"
    if "demo" in relative or "github-demo" in relative:
        return "demo_runbook"
    if "evaluation" in relative:
        return "evaluation"
    if "architecture" in relative:
        return "architecture"
    if "workflow" in relative:
        return "workflow"
    return "repo_doc"


def _environment_for(relative: str) -> str | None:
    normalized = relative.lower()
    if "production" in normalized:
        return "production"
    if "staging" in normalized:
        return "staging"
    if "github" in normalized or "ci" in normalized or "workflow" in normalized:
        return "dev"
    return None


def _capability_categories_for(relative: str, document_type: str) -> tuple[str, ...]:
    normalized = relative.lower()
    categories: set[str] = {"documentation"}
    if document_type in {"cicd_workflow", "workflow"} or ".github/workflows/" in normalized:
        categories.update({"cicd", "testing", "repository"})
    if "deploy" in normalized or "deployment" in normalized:
        categories.add("deployment")
    if "approval" in normalized:
        categories.add("approval")
    if "security" in normalized or "threat-model" in normalized:
        categories.add("policy")
    if "evaluation" in normalized:
        categories.add("evaluation")
    if "demo" in normalized:
        categories.add("run_instructions")
    if "architecture" in normalized:
        categories.add("architecture")
    return tuple(sorted(categories))


def _format_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix in {".yml", ".yaml"}:
        return "yaml"
    return "text"
