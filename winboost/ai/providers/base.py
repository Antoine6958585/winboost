"""Base provider — Interface abstraite pour les providers LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """Reponse d'un provider LLM."""

    text: str
    model: str = ""
    provider: str = ""
    usage: dict[str, int] | None = None  # tokens in/out
    raw: Any = None


class BaseLLMProvider(ABC):
    """Interface abstraite pour un provider LLM."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nom du provider."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Verifie si le provider est configure et disponible."""
        ...

    @abstractmethod
    def complete(self, prompt: str, system: str = "") -> LLMResponse:
        """Envoie un prompt et retourne la reponse.

        Args:
            prompt: Le prompt utilisateur.
            system: Instructions systeme optionnelles.

        Returns:
            LLMResponse avec le texte genere.
        """
        ...
