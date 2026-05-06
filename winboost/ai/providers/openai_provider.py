"""Provider OpenAI (GPT) pour WinBoost."""

from __future__ import annotations

import os

from winboost.ai.providers.base import BaseLLMProvider, LLMResponse


class OpenAIProvider(BaseLLMProvider):
    """Provider utilisant l'API OpenAI."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini") -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    DEFAULT_SYSTEM = "Tu es WinBoost, un assistant Windows. Reponds en francais, concis."

    def complete(self, prompt: str, system: str = "") -> LLMResponse:
        import openai

        client = openai.OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system or self.DEFAULT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )

        text = response.choices[0].message.content or ""
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        return LLMResponse(
            text=text,
            model=self._model,
            provider=self.name,
            usage=usage,
            raw=response,
        )
