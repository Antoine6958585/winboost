"""Provider Anthropic (Claude) pour WinBoost."""

from __future__ import annotations

import os

from winboost.ai.providers.base import BaseLLMProvider, LLMResponse


class AnthropicProvider(BaseLLMProvider):
    """Provider utilisant l'API Anthropic (Claude)."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def complete(self, prompt: str, system: str = "") -> LLMResponse:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system or "Tu es WinBoost, un assistant Windows. Reponds en francais, concis.",
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text if message.content else ""
        return LLMResponse(
            text=text,
            model=self._model,
            provider=self.name,
            usage={
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            },
            raw=message,
        )
