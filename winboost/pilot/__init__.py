"""Sous-module Pilot — Computer Use BYOK (v2.3, Lab tier).

Ce sous-package expose un orchestrateur qui pilote le PC visuellement via
l'API Anthropic Computer Use (modeles Claude). Il est *strictement opt-in* et
soumis a 4 garde-fous non-negociables (cf. README.md du module) :

1. **BYOK** Anthropic obligatoire (l'utilisateur paie sa propre cle)
2. **Profil Lab** requis (separation du tier Pro standard)
3. **Notice RGPD + opt-in granulaire** (les screenshots sortent du PC, vers
   l'API Anthropic — datacenter US, hors UE)
4. **Confirmation visuelle a chaque action** (preview annote + clic)

Imports lourds (anthropic SDK, Pillow, pyautogui) restent confines aux
modules concrets pour ne pas penaliser un utilisateur qui n'a pas installe
l'extra `pilot`.

Usage canonique :

    pip install winboost[pilot]
    # puis dans le code, apres opt-in et profil Lab :
    from winboost.pilot import AnthropicPilot
    pilot = AnthropicPilot(api_key=..., budget=..., sandbox=..., confirmer=...)
    pilot.run("ma manette bluetooth bug dans Rocket League")

Voir `winboost/pilot/README.md` pour le scenario complet (manette bluetooth)
et la liste des limitations connues.
"""

from __future__ import annotations

__all__ = [
    "AnthropicPilot",
    "BudgetManager",
    "BudgetExceededError",
    "ConfirmationManager",
    "Sandbox",
    "SandboxViolationError",
    "PilotError",
    "RGPDNotAcceptedError",
    "ProfileNotLabError",
    "BYOKMissingError",
    "PilotAction",
    "PilotResult",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    """Lazy-import pour eviter de charger anthropic/Pillow au simple import.

    Permet `from winboost.pilot import AnthropicPilot` sans tirer le SDK
    Anthropic tant qu'on n'instancie pas effectivement le pilot.
    """
    if name in {"AnthropicPilot", "PilotError", "BYOKMissingError",
                "ProfileNotLabError", "RGPDNotAcceptedError",
                "PilotAction", "PilotResult"}:
        from winboost.pilot import anthropic_pilot

        return getattr(anthropic_pilot, name)
    if name in {"BudgetManager", "BudgetExceededError"}:
        from winboost.pilot import budget

        return getattr(budget, name)
    if name in {"ConfirmationManager"}:
        from winboost.pilot import confirmation_ui

        return getattr(confirmation_ui, name)
    if name in {"Sandbox", "SandboxViolationError"}:
        from winboost.pilot import sandbox

        return getattr(sandbox, name)
    raise AttributeError(f"module 'winboost.pilot' has no attribute {name!r}")
