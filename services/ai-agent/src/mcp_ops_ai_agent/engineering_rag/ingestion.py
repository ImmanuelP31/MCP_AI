from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from mcp_ops_policy.security import detect_prompt_injection, sanitize_description

from mcp_ops_ai_agent.engineering_rag.models import (
    EngineeringDocument,
    EngineeringDocumentMetadata,
    KnowledgeChunk,
)
from mcp_ops_ai_agent.tool_discovery.embeddings import EmbeddingProvider


class RagIngestionError(ValueError):
    pass


def ingest_document(
    document: EngineeringDocument,
    *,
    embedding_provider: EmbeddingProvider,
    chunk_size: int = 900,
) -> list[KnowledgeChunk]:
    _validate_metadata(document.metadata)
    if not isinstance(document.content, str) or not document.content.strip():
        raise RagIngestionError("document content must be a non-empty string")
    chunks: list[KnowledgeChunk] = []
    for index, text in enumerate(_chunk_text(document.content, chunk_size), start=1):
        cleaned = sanitize_description(text)
        injection = detect_prompt_injection(cleaned, source="rag_document")
        chunk_id = f"{document.metadata.document_id}#chunk-{index}"
        embedding_text = _embedding_text(document.metadata, cleaned)
        chunks.append(
            KnowledgeChunk(
                chunk_id=chunk_id,
                metadata=document.metadata,
                text=cleaned,
                embedding=embedding_provider.embed(embedding_text),
                prompt_injection_detected=injection,
            )
        )
    return chunks


def ingest_markdown(
    text: str,
    metadata: EngineeringDocumentMetadata,
    *,
    embedding_provider: EmbeddingProvider,
) -> list[KnowledgeChunk]:
    return ingest_document(
        EngineeringDocument(metadata=metadata, content=text, format="markdown"),
        embedding_provider=embedding_provider,
    )


def ingest_plain_text(
    text: str,
    metadata: EngineeringDocumentMetadata,
    *,
    embedding_provider: EmbeddingProvider,
) -> list[KnowledgeChunk]:
    return ingest_document(
        EngineeringDocument(metadata=metadata, content=text, format="text"),
        embedding_provider=embedding_provider,
    )


def ingest_json(
    payload: dict[str, Any] | str,
    metadata: EngineeringDocumentMetadata,
    *,
    embedding_provider: EmbeddingProvider,
) -> list[KnowledgeChunk]:
    try:
        decoded = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError as exc:
        raise RagIngestionError("json document is malformed") from exc
    if not isinstance(decoded, dict):
        raise RagIngestionError("json document must be an object")
    return ingest_document(
        EngineeringDocument(
            metadata=metadata,
            content=json.dumps(decoded, sort_keys=True),
            format="json",
        ),
        embedding_provider=embedding_provider,
    )


def _validate_metadata(metadata: EngineeringDocumentMetadata) -> None:
    required = {
        "document_id": metadata.document_id,
        "title": metadata.title,
        "document_type": metadata.document_type,
        "version": metadata.version,
        "source": metadata.source,
    }
    missing = [name for name, value in required.items() if not isinstance(value, str) or not value]
    if missing:
        raise RagIngestionError("missing metadata fields: " + ", ".join(missing))
    if not isinstance(metadata.updated_at, datetime):
        raise RagIngestionError("updated_at must be a datetime")
    if metadata.updated_at.tzinfo is None:
        raise RagIngestionError("updated_at must include timezone")


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    sectioned = _markdown_sections(text)
    if sectioned:
        chunks: list[str] = []
        for heading, body in sectioned:
            prefix = f"Section: {heading}. "
            for chunk in _sentence_chunks(body, max(100, chunk_size - len(prefix))):
                chunks.append(f"{prefix}{chunk}".strip())
        return chunks
    return _sentence_chunks(text, chunk_size)


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^\s*(#{1,6})\s+(.+?)\s*$", text))
    if not matches:
        return []
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        heading = re.sub(r"\s+", " ", match.group(2)).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((heading, body))
    return sections


def _sentence_chunks(text: str, chunk_size: int) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= chunk_size:
        return [normalized]
    chunks: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", normalized):
        if len(current) + len(sentence) + 1 > chunk_size and current:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def _embedding_text(metadata: EngineeringDocumentMetadata, text: str) -> str:
    return "\n".join(
        [
            f"Title: {metadata.title}",
            f"Type: {metadata.document_type}",
            f"Service: {metadata.service or ''}",
            f"Repository: {metadata.repository or ''}",
            f"Environment: {metadata.environment or ''}",
            f"Owner: {metadata.owner or ''}",
            f"Version: {metadata.version}",
            "Capabilities: " + " ".join(metadata.capability_categories),
            text,
        ]
    )


def metadata_from_mapping(payload: dict[str, Any]) -> EngineeringDocumentMetadata:
    try:
        updated_at = payload.get("updated_at") or datetime.now(UTC)
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        return EngineeringDocumentMetadata(
            document_id=str(payload["document_id"]),
            title=str(payload["title"]),
            document_type=str(payload["document_type"]),
            service=payload.get("service"),
            repository=payload.get("repository"),
            environment=payload.get("environment"),
            owner=payload.get("owner"),
            version=str(payload.get("version", "1.0")),
            source=str(payload.get("source", "ingested")),
            updated_at=updated_at,
            stale=bool(payload.get("stale", False)),
            capability_categories=tuple(
                str(item)
                for item in payload.get("capability_categories", [])
                if isinstance(item, str)
            ),
        )
    except KeyError as exc:
        raise RagIngestionError(f"missing metadata field: {exc.args[0]}") from exc
