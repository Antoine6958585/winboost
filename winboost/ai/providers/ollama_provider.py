"""Provider Ollama (local) pour WinBoost."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from winboost.ai.providers.base import BaseLLMProvider, LLMResponse


class OllamaProvider(BaseLLMProvider):
    """Provider utilisant Ollama en local (pas de cle API requise)."""

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """Verifie si Ollama tourne en local."""
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    DEFAULT_SYSTEM = "Tu es WinBoost, un assistant Windows. Reponds en francais, concis."

    def complete(self, prompt: str, system: str = "") -> LLMResponse:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "system": system or self.DEFAULT_SYSTEM,
            "stream": False,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        return LLMResponse(
            text=result.get("response", ""),
            model=self._model,
            provider=self.name,
            usage=None,
            raw=result,
        )
