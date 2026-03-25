"""Schema de validation pour les actions YAML WinBoost."""

from __future__ import annotations

from typing import Any

# Valeurs valides
VALID_CATEGORIES = {
    "privacy", "performance", "cleanup", "dev_tools",
    "network", "security", "appearance", "gaming", "system",
}

VALID_RISK_LEVELS = {"info", "low", "medium", "high", "critical"}

VALID_EXECUTE_METHODS = {
    "registry_set", "registry_delete",
    "service_stop", "service_disable", "service_set_manual",
    "powershell", "cmd",
    "delete_path", "clear_directory",
    "scheduled_task_disable",
}

# Champs requis dans chaque action YAML
REQUIRED_FIELDS = {"id", "name", "description", "category", "risk_level", "execute"}


class ActionValidationError(Exception):
    """Erreur de validation d'une action YAML."""


def validate_action(data: dict[str, Any], filename: str = "") -> list[str]:
    """Valide une action YAML et retourne la liste des erreurs.

    Returns:
        Liste vide si valide, sinon liste de messages d'erreur.
    """
    errors: list[str] = []
    prefix = f"[{filename}] " if filename else ""

    # Champs requis
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"{prefix}Champ requis manquant : '{field}'")

    if errors:
        return errors  # Pas la peine de continuer si les champs de base manquent

    # Validation des valeurs
    if data.get("category") not in VALID_CATEGORIES:
        errors.append(
            f"{prefix}Categorie invalide : '{data.get('category')}'. "
            f"Valides : {VALID_CATEGORIES}"
        )

    if data.get("risk_level") not in VALID_RISK_LEVELS:
        errors.append(
            f"{prefix}Risk level invalide : '{data.get('risk_level')}'. "
            f"Valides : {VALID_RISK_LEVELS}"
        )

    # Validation execute
    execute = data.get("execute", {})
    if isinstance(execute, dict):
        method = execute.get("method")
        if method and method not in VALID_EXECUTE_METHODS:
            errors.append(
                f"{prefix}Methode d'execution invalide : '{method}'. "
                f"Valides : {VALID_EXECUTE_METHODS}"
            )
    else:
        errors.append(f"{prefix}'execute' doit etre un dictionnaire")

    # Validation keywords
    keywords = data.get("keywords", {})
    if keywords and not isinstance(keywords, dict):
        errors.append(f"{prefix}'keywords' doit etre un dictionnaire (fr/en)")

    # Validation types
    if "requires_admin" in data and not isinstance(data["requires_admin"], bool):
        errors.append(f"{prefix}'requires_admin' doit etre un booleen")

    if "reversible" in data and not isinstance(data["reversible"], bool):
        errors.append(f"{prefix}'reversible' doit etre un booleen")

    return errors
