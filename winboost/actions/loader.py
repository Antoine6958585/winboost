"""Loader dynamique des actions YAML WinBoost."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from winboost.actions.schema import validate_action

# Repertoire des actions YAML
ACTIONS_DIR = Path(__file__).parent


class Action:
    """Represente une action chargee depuis un fichier YAML."""

    def __init__(self, data: dict[str, Any], source_file: str = "") -> None:
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.description: str = data["description"]
        self.category: str = data["category"]
        self.risk_level: str = data["risk_level"]
        self.requires_admin: bool = data.get("requires_admin", False)
        self.reversible: bool = data.get("reversible", True)
        self.execute: dict[str, Any] = data.get("execute", {})
        self.rollback: dict[str, Any] = data.get("rollback", {})
        self.preview: dict[str, Any] = data.get("preview", {})
        self.keywords: dict[str, list[str]] = data.get("keywords", {})
        self.compatibility: dict[str, Any] = data.get("compatibility", {})
        self.source_file = source_file
        self._raw = data

    def get_keywords_flat(self) -> list[str]:
        """Retourne tous les mots-cles (fr + en) en liste plate."""
        result: list[str] = []
        for lang_keywords in self.keywords.values():
            if isinstance(lang_keywords, list):
                result.extend(lang_keywords)
        return [k.lower() for k in result]

    def to_dict(self) -> dict[str, Any]:
        return self._raw.copy()

    def __repr__(self) -> str:
        return f"Action(id={self.id!r}, name={self.name!r}, risk={self.risk_level})"


class ActionRegistry:
    """Charge et indexe toutes les actions YAML."""

    def __init__(self, actions_dir: Path | None = None) -> None:
        self._dir = actions_dir or ACTIONS_DIR
        self._actions: dict[str, Action] = {}
        self._by_category: dict[str, list[Action]] = {}
        self._errors: list[str] = []

    def load_all(self) -> int:
        """Charge toutes les actions YAML depuis les sous-dossiers.

        Returns:
            Nombre d'actions chargees.
        """
        self._actions.clear()
        self._by_category.clear()
        self._errors.clear()

        for category_dir in sorted(self._dir.iterdir()):
            if not category_dir.is_dir() or category_dir.name.startswith("_"):
                continue
            for yaml_file in sorted(category_dir.glob("*.yaml")):
                self._load_file(yaml_file)

        return len(self._actions)

    def _load_file(self, filepath: Path) -> None:
        """Charge un fichier YAML contenant une ou plusieurs actions."""
        try:
            with open(filepath, encoding="utf-8") as f:
                content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            self._errors.append(f"YAML invalide : {filepath} — {e}")
            return

        if content is None:
            return

        # Un fichier peut contenir une seule action (dict) ou plusieurs (list)
        actions_data = content if isinstance(content, list) else [content]

        for data in actions_data:
            if not isinstance(data, dict):
                self._errors.append(f"Entree invalide dans {filepath}")
                continue

            errors = validate_action(data, filepath.name)
            if errors:
                self._errors.extend(errors)
                continue

            action = Action(data, source_file=str(filepath))
            self._actions[action.id] = action

            if action.category not in self._by_category:
                self._by_category[action.category] = []
            self._by_category[action.category].append(action)

    def get(self, action_id: str) -> Action | None:
        """Recupere une action par son ID."""
        return self._actions.get(action_id)

    def search(self, query: str) -> list[Action]:
        """Recherche des actions par mots-cles."""
        query_lower = query.lower()
        terms = query_lower.split()
        results: list[Action] = []

        for action in self._actions.values():
            keywords = action.get_keywords_flat()
            name_lower = action.name.lower()
            desc_lower = action.description.lower()

            # Score simple : nombre de termes matchant
            score = 0
            for term in terms:
                if term in name_lower or term in desc_lower:
                    score += 2
                elif any(term in kw for kw in keywords):
                    score += 1

            if score > 0:
                results.append(action)

        # Tri par pertinence (plus de keywords = plus pertinent)
        results.sort(key=lambda a: a.risk_level)
        return results

    def list_by_category(self, category: str) -> list[Action]:
        """Retourne les actions d'une categorie."""
        return self._by_category.get(category, [])

    def list_all(self) -> list[Action]:
        """Retourne toutes les actions."""
        return list(self._actions.values())

    def categories(self) -> list[str]:
        """Retourne les categories disponibles."""
        return sorted(self._by_category.keys())

    @property
    def count(self) -> int:
        return len(self._actions)

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def stats(self) -> dict[str, int]:
        """Retourne les stats par categorie."""
        return {cat: len(actions) for cat, actions in sorted(self._by_category.items())}
