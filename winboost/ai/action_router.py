"""Action Router — Route les intents vers les actions YAML correspondantes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from winboost.actions.loader import Action, ActionRegistry
from winboost.ai.cache import KeywordCache
from winboost.ai.nl_parser import Intent, NLParser
from winboost.ai.safety_engine import SafetyEngine, SafetyVerdict
from winboost.core.config import Config


@dataclass
class RoutedAction:
    """Action routee avec son verdict de securite et son score."""

    action: Action
    verdict: SafetyVerdict
    score: float = 0.0
    source: str = "cache"  # "cache" ou "llm"


@dataclass
class RouteResult:
    """Resultat complet du routage d'une requete."""

    query: str
    intent: Intent
    actions: list[RoutedAction] = field(default_factory=list)
    blocked: list[RoutedAction] = field(default_factory=list)
    message: str = ""
    resolved_by: str = "cache"  # "cache", "llm", ou "none"

    @property
    def has_actions(self) -> bool:
        return len(self.actions) > 0

    @property
    def all_safe(self) -> bool:
        return all(a.verdict.allowed for a in self.actions)


class ActionRouter:
    """Route les requetes NL vers des actions via cache ou LLM.

    Pipeline :
    1. NLParser : requete -> intent
    2. KeywordCache : resolution locale par mots-cles
    3. (Si echec) LLM Provider : resolution par IA
    4. SafetyEngine : filtrage par profil
    """

    def __init__(
        self,
        config: Config | None = None,
        actions_dir: Path | None = None,
    ) -> None:
        self._config = config or Config()
        self._registry = ActionRegistry(actions_dir=actions_dir)
        self._registry.load_all()
        self._parser = NLParser()
        self._cache = KeywordCache(self._registry)
        self._safety = SafetyEngine(self._config)

    @property
    def registry(self) -> ActionRegistry:
        return self._registry

    @property
    def action_count(self) -> int:
        return self._registry.count

    def route(self, query: str, max_actions: int = 5) -> RouteResult:
        """Route une requete NL vers des actions.

        Args:
            query: Requete en langage naturel.
            max_actions: Nombre max d'actions a retourner.

        Returns:
            RouteResult avec les actions routees et filtrees.
        """
        # 1. Parse la requete
        intent = self._parser.parse(query)

        # 2. Tente la resolution par cache keyword
        cache_results = self._cache.resolve(query, max_results=max_actions * 2)

        if cache_results:
            # Filtre par categorie si detectee
            if intent.category:
                cache_results = [
                    (a, s) for a, s in cache_results
                    if a.category == intent.category
                ] or cache_results  # Fallback si le filtre vide tout

            intent.source = "cache"
            intent.confidence = max(s for _, s in cache_results[:1])
            return self._build_result(query, intent, cache_results[:max_actions], "cache")

        # 3. Fallback : recherche par categorie dans le registry
        if intent.category:
            category_actions = self._registry.list_by_category(intent.category)
            if category_actions:
                results = [(a, 0.3) for a in category_actions[:max_actions]]
                return self._build_result(query, intent, results, "category_fallback")

        # 4. Aucun resultat
        return RouteResult(
            query=query,
            intent=intent,
            message="Aucune action trouvee pour cette requete.",
            resolved_by="none",
        )

    def _build_result(
        self,
        query: str,
        intent: Intent,
        scored_actions: list[tuple[Action, float]],
        source: str,
    ) -> RouteResult:
        """Construit le RouteResult avec filtrage de securite."""
        allowed: list[RoutedAction] = []
        blocked: list[RoutedAction] = []

        for action, score in scored_actions:
            verdict = self._safety.check_action(action)
            routed = RoutedAction(
                action=action,
                verdict=verdict,
                score=score,
                source=source,
            )
            if verdict.allowed:
                allowed.append(routed)
            else:
                blocked.append(routed)

        n_total = len(allowed) + len(blocked)
        msg = f"{len(allowed)} action(s) proposee(s)"
        if blocked:
            msg += f", {len(blocked)} bloquee(s) par le profil"

        return RouteResult(
            query=query,
            intent=intent,
            actions=allowed,
            blocked=blocked,
            message=msg,
            resolved_by=source,
        )
