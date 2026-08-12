from __future__ import annotations

import hashlib
import http.client
import json
import math
import re
import ssl
from typing import Any, Protocol

from mcp_ops_common.config import Settings, get_settings


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]:
        """Return an embedding vector for retrieval."""


class EmbeddingProviderUnavailable(RuntimeError):
    pass


class HashingEmbeddingProvider:
    """Deterministic local embedding provider.

    This is intentionally provider-neutral: production can replace it with Gemini, an internal
    model, or an OpenSearch neural sparse/vector implementation without changing retrieval
    contracts.
    """

    def __init__(self, dimensions: int = 96) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        for token in expanded_tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _normalize(vector)


class OpenAIEmbeddingProvider:
    """Provider-backed embeddings for live semantic retrieval.

    The provider deliberately exposes the same tiny interface as the deterministic hashing
    implementation, so retrieval, RAG, and tests do not depend on a specific model vendor.
    """

    _host = "api.openai.com"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        timeout_seconds: int = 20,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> tuple[float, ...]:
        if not self.api_key:
            raise EmbeddingProviderUnavailable("OpenAI API key is not configured.")
        payload: dict[str, object] = {"model": self.model, "input": text[:8000]}
        response = self._post_json("/v1/embeddings", payload)
        try:
            embedding = response["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise EmbeddingProviderUnavailable(
                "Embedding response shape was not recognized."
            ) from exc
        if not isinstance(embedding, list) or not all(
            isinstance(value, int | float) and not isinstance(value, bool)
            for value in embedding
        ):
            raise EmbeddingProviderUnavailable("Embedding response did not contain numeric values.")
        return _normalize([float(value) for value in embedding])

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        context = ssl.create_default_context()
        connection = http.client.HTTPSConnection(
            self._host,
            timeout=self.timeout_seconds,
            context=context,
        )
        try:
            connection.request(
                "POST",
                path,
                body=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            raw = response.read(2_000_000)
        except OSError as exc:
            raise EmbeddingProviderUnavailable(
                f"Embedding provider request failed: {exc.__class__.__name__}."
            ) from exc
        finally:
            connection.close()
        if response.status >= 400:
            raise EmbeddingProviderUnavailable(
                f"Embedding provider returned HTTP {response.status}."
            )
        decoded = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(decoded, dict):
            raise EmbeddingProviderUnavailable("Embedding provider response must be an object.")
        return decoded


class GeminiEmbeddingProvider:
    """Gemini-backed embeddings for live semantic retrieval."""

    _host = "generativelanguage.googleapis.com"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-embedding-001",
        timeout_seconds: int = 20,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> tuple[float, ...]:
        if not self.api_key:
            raise EmbeddingProviderUnavailable("Gemini API key is not configured.")
        payload: dict[str, object] = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text[:8000]}]},
            "taskType": "RETRIEVAL_DOCUMENT",
        }
        response = self._post_json(f"/v1beta/models/{self.model}:embedContent", payload)
        try:
            embedding = response["embedding"]["values"]
        except (KeyError, TypeError) as exc:
            raise EmbeddingProviderUnavailable(
                "Embedding response shape was not recognized."
            ) from exc
        if not isinstance(embedding, list) or not all(
            isinstance(value, int | float) and not isinstance(value, bool)
            for value in embedding
        ):
            raise EmbeddingProviderUnavailable("Embedding response did not contain numeric values.")
        return _normalize([float(value) for value in embedding])

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        context = ssl.create_default_context()
        connection = http.client.HTTPSConnection(
            self._host,
            timeout=self.timeout_seconds,
            context=context,
        )
        try:
            connection.request(
                "POST",
                path,
                body=body,
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            raw = response.read(2_000_000)
        except OSError as exc:
            raise EmbeddingProviderUnavailable(
                f"Embedding provider request failed: {exc.__class__.__name__}."
            ) from exc
        finally:
            connection.close()
        if response.status >= 400:
            raise EmbeddingProviderUnavailable(
                f"Embedding provider returned HTTP {response.status}."
            )
        decoded = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(decoded, dict):
            raise EmbeddingProviderUnavailable("Embedding provider response must be an object.")
        return decoded


class FallbackEmbeddingProvider:
    """Use a live provider when available and deterministic hashing when it is not."""

    def __init__(self, primary: EmbeddingProvider, fallback: EmbeddingProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_count = 0

    def embed(self, text: str) -> tuple[float, ...]:
        try:
            return self.primary.embed(text)
        except EmbeddingProviderUnavailable:
            self.fallback_count += 1
            return self.fallback.embed(text)


def embedding_provider_from_settings(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    hashing = HashingEmbeddingProvider()
    if settings.embedding_provider.lower() == "openai":
        return FallbackEmbeddingProvider(
            OpenAIEmbeddingProvider(
                api_key=settings.openai_api_key,
                model=settings.openai_embedding_model,
                timeout_seconds=settings.embedding_timeout_seconds,
            ),
            hashing,
        )
    if settings.embedding_provider.lower() == "gemini":
        return FallbackEmbeddingProvider(
            GeminiEmbeddingProvider(
                api_key=settings.gemini_api_key,
                model=settings.gemini_embedding_model,
                timeout_seconds=settings.embedding_timeout_seconds,
            ),
            hashing,
        )
    return hashing


SYNONYMS: dict[str, tuple[str, ...]] = {
    "build": ("pipeline", "ci", "job", "compile"),
    "failed": ("failure", "error", "broken", "red"),
    "fail": ("failure", "error", "broken", "red"),
    "deployment": ("deploy", "release", "rollout"),
    "deploy": ("deployment", "release", "rollout"),
    "docs": ("documentation", "knowledge", "runbook"),
    "documentation": ("docs", "knowledge", "runbook"),
    "issue": ("ticket", "workitem", "jira"),
    "jira": ("ticket", "issue", "workitem"),
    "owner": ("ownership", "team", "service"),
    "changes": ("diff", "commit", "files"),
    "changed": ("diff", "commit", "files"),
    "logs": ("log", "trace", "output"),
    "tests": ("test", "validation", "suite"),
}


def expanded_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in tokenize(text):
        tokens.append(token)
        tokens.extend(SYNONYMS.get(token, ()))
    return tokens


def tokenize(text: str) -> list[str]:
    normalized = text.lower().replace("_", " ").replace("-", " ")
    return [token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) >= 2]


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return round(sum(a * b for a, b in zip(left, right, strict=True)), 4)


def _normalize(vector: list[float]) -> tuple[float, ...]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return tuple(vector)
    return tuple(value / magnitude for value in vector)
