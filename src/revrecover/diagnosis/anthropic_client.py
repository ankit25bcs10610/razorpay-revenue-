"""Anthropic SDK adapter implementing the LLMClient protocol.

Uses structured outputs (output_config.format json_schema) so the response
is guaranteed-parseable JSON matching DIAGNOSIS_SCHEMA. The SDK client is
injectable for tests; the zero-arg default resolves credentials from the
environment (ANTHROPIC_API_KEY or an `ant auth login` profile).
"""

from __future__ import annotations

from typing import Any

DEFAULT_MODEL = "claude-opus-5"


class AnthropicDiagnosisClient:
    def __init__(self, *, sdk_client: Any | None = None, model: str = DEFAULT_MODEL):
        if sdk_client is None:
            import anthropic

            sdk_client = anthropic.Anthropic()
        self._sdk = sdk_client
        self._model = model

    def complete(self, *, system: str, user: str, schema: dict) -> str:
        response = self._sdk.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        raise ValueError("no text block in model response")
