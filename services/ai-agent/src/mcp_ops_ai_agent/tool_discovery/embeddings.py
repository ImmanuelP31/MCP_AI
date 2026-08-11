from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]:
        """Return an embedding vector for retrieval."""


class HashingEmbeddingProvider:
    """Deterministic local embedding provider.

    This is intentionally provider-neutral: production can replace it with OpenAI, an internal
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
