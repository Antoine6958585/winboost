"""Safety Engine — Filtrage des actions selon le profil et les regles de securite."""

from __future__ import annotations

from dataclasses import dataclass

from winboost.actions.loader import Action
from winboost.core.config import Config

# Mapping risk_level -> ordre numerique
RISK_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class SafetyVerdict:
    """Resultat de la verification de securite d'une action."""

    action_id: str
    allowed: bool
    reason: str = ""
    requires_confirmation: bool = False
    requires_dry_run: bool = False
    risk_level: str = "low"


class SafetyEngine:
    """Filtre les actions selon le profil utilisateur et les regles de securite."""

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def max_risk_level(self) -> str:
        """Niveau de risque maximum autorise par le profil courant."""
        return self._config.max_risk

    @property
    def dry_run_first(self) -> bool:
        """Le profil requiert-il un dry-run avant execution ?"""
        return self._config.dry_run_first

    def check_action(self, action: Action) -> SafetyVerdict:
        """Verifie si une action est autorisee pour le profil courant.

        Returns:
            SafetyVerdict avec le statut et les conditions.
        """
        action_risk = RISK_ORDER.get(action.risk_level, 5)
        max_risk = RISK_ORDER.get(self.max_risk_level, 1)

        # Actions critiques : seul le profil expert peut les executer
        if action.risk_level == "critical":
            if self._config.profile != "expert":
                return SafetyVerdict(
                    action_id=action.id,
                    allowed=False,
                    reason=(
                        f"Action critique bloquee — profil "
                        f"'{self._config.profile}' (mode expert requis)"
                    ),
                    risk_level=action.risk_level,
                )
            # Expert peut executer les critiques — skip le check de seuil
            return SafetyVerdict(
                action_id=action.id,
                allowed=True,
                reason="Action critique autorisee (profil expert)",
                requires_confirmation=True,
                requires_dry_run=True,
                risk_level=action.risk_level,
            )

        # Risque au-dessus du seuil du profil
        if action_risk > max_risk:
            return SafetyVerdict(
                action_id=action.id,
                allowed=False,
                reason=(
                    f"Risque '{action.risk_level}' depasse le maximum "
                    f"'{self.max_risk_level}' du profil '{self._config.profile}'"
                ),
                risk_level=action.risk_level,
            )

        # Determine les conditions d'execution
        requires_confirm = action_risk >= RISK_ORDER.get("medium", 2)
        requires_dry = self.dry_run_first or action_risk >= RISK_ORDER.get("high", 3)

        return SafetyVerdict(
            action_id=action.id,
            allowed=True,
            reason="Action autorisee",
            requires_confirmation=requires_confirm,
            requires_dry_run=requires_dry,
            risk_level=action.risk_level,
        )

    def filter_actions(self, actions: list[Action]) -> list[tuple[Action, SafetyVerdict]]:
        """Filtre une liste d'actions et retourne les verdicts.

        Returns:
            Liste de (action, verdict) pour chaque action.
        """
        return [(a, self.check_action(a)) for a in actions]

    def get_allowed_actions(self, actions: list[Action]) -> list[Action]:
        """Retourne uniquement les actions autorisees."""
        return [a for a, v in self.filter_actions(actions) if v.allowed]
