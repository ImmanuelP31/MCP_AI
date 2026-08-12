from __future__ import annotations

from typing import Any

from mcp_ops_ai_agent.provider import GeminiChatProvider
from mcp_ops_common.config import Settings


class FakeGeminiChatProvider(GeminiChatProvider):
    def __init__(self) -> None:
        super().__init__(
            Settings(
                gemini_api_key="gemini-test-key",
                gemini_model="gemini-test-model",
            )
        )
        self.paths: list[str] = []
        self.payloads: list[dict[str, Any]] = []

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.paths.append(path)
        self.payloads.append(payload)
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "The build failed in the test stage."},
                        ]
                    }
                }
            ]
        }


def test_gemini_chat_provider_uses_sanitized_context_payload() -> None:
    provider = FakeGeminiChatProvider()

    answer = provider.answer_question(
        "Why did the build fail?",
        {"logs": [{"line": "pytest failed"}]},
    )

    assert answer == "The build failed in the test stage."
    assert provider.paths == ["/v1beta/models/gemini-test-model:generateContent"]
    prompt = provider.payloads[0]["contents"][0]["parts"][0]["text"]
    assert "retrieved_tool_data" in prompt
    assert "Do not approve operations" in prompt
