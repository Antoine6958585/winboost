"""Cache keyword — Resolution locale des requetes sans appel LLM.

Objectif : resoudre ~70% des requetes par matching de mots-cles
avant de faire appel a un provider LLM.
"""

from __future__ import annotations

import re
from typing import Any

from winboost.actions.loader import Action, ActionRegistry


# Mots vides a ignorer dans les requetes
STOP_WORDS_FR = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou",
    "je", "tu", "il", "nous", "vous", "ils", "mon", "ma", "mes",
    "ce", "cette", "ces", "que", "qui", "quoi", "est", "sont",
    "a", "en", "dans", "sur", "pour", "par", "avec", "ne", "pas",
    "plus", "se", "son", "sa", "ses", "au", "aux", "ai", "as",
    "faire", "fais", "fait", "veux", "peux", "dois",
}

# Synonymes courants -> terme normalise
SYNONYMS: dict[str, str] = {
    "temp": "temporaire",
    "temps": "temporaire",
    "tmp": "temporaire",
    "vie privee": "privacy",
    "confidentialite": "privacy",
    "vitesse": "performance",
    "rapide": "performance",
    "lent": "performance",
    "lag": "performance",
    "ram": "memoire",
    "memoire vive": "memoire",
    "demarrage": "startup",
    "boot": "startup",
    "disque": "disk",
    "espace": "disk",
    "stockage": "disk",
    "nettoyage": "cleanup",
    "nettoyer": "cleanup",
    "supprimer": "cleanup",
    "effacer": "cleanup",
    "pub": "publicite",
    "ads": "publicite",
    "jeu": "gaming",
    "jeux": "gaming",
    "game": "gaming",
    "apparence": "appearance",
    "theme": "appearance",
    "sombre": "dark mode",
    "dark": "dark mode",
    "securite": "security",
    "firewall": "security",
    "reseau": "network",
    "wifi": "network",
    "dns": "network",
    "dev": "dev_tools",
    "npm": "dev_tools",
    "cache": "cleanup",
    "service": "service",
    "cortana": "cortana",
    "telemetrie": "telemetry",
    "telemetry": "telemetry",
    "espion": "telemetry",
    "tracking": "telemetry",
}


def _tokenize(text: str) -> list[str]:
    """Tokenize et normalise une requete."""
    text = text.lower().strip()
    # Remplace les synonymes multi-mots d'abord
    for syn, norm in SYNONYMS.items():
        if " " in syn and syn in text:
            text = text.replace(syn, norm)
    # Split en mots
    words = re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ0-9_]+", text)
    # Filtre les stop words et applique les synonymes mono-mot
    result: list[str] = []
    for w in words:
        if w in STOP_WORDS_FR:
            continue
        result.append(SYNONYMS.get(w, w))
    return result


class KeywordCache:
    """Cache de resolution par mots-cles.

    Resout les requetes utilisateur vers des actions sans LLM
    en matchant les mots-cles de la requete avec ceux des actions.
    """

    def __init__(self, registry: ActionRegistry) -> None:
        self._registry = registry
        self._keyword_index: dict[str, list[str]] = {}  # keyword -> [action_ids]
        self._build_index()

    def _build_index(self) -> None:
        """Construit l'index inverse keyword -> action_ids."""
        self._keyword_index.clear()
        for action in self._registry.list_all():
            keywords = action.get_keywords_flat()
            # Ajoute aussi le nom et la description tokenises
            name_tokens = _tokenize(action.name)
            desc_tokens = _tokenize(action.description)
            all_kw = set(keywords + name_tokens + desc_tokens)

            for kw in all_kw:
                if kw not in self._keyword_index:
                    self._keyword_index[kw] = []
                self._keyword_index[kw].append(action.id)

    def resolve(self, query: str, max_results: int = 10) -> list[tuple[Action, float]]:
        """Resout une requete vers des actions avec un score de confiance.

        Args:
            query: Requete en langage naturel.
            max_results: Nombre max de resultats.

        Returns:
            Liste de (action, score) triee par score decroissant.
            Score entre 0.0 et 1.0.
        """
        tokens = _tokenize(query)
        if not tokens:
            return []

        # Compte les matchs par action
        scores: dict[str, int] = {}
        for token in tokens:
            # Match exact
            if token in self._keyword_index:
                for action_id in self._keyword_index[token]:
                    scores[action_id] = scores.get(action_id, 0) + 2

            # Match partiel (le token est contenu dans un keyword)
            for kw, action_ids in self._keyword_index.items():
                if token in kw and token != kw:
                    for action_id in action_ids:
                        scores[action_id] = scores.get(action_id, 0) + 1

        if not scores:
            return []

        # Normalise les scores (max = 1.0)
        max_score = max(scores.values())
        results: list[tuple[Action, float]] = []
        for action_id, raw_score in scores.items():
            action = self._registry.get(action_id)
            if action:
                normalized = min(raw_score / max(max_score, 1), 1.0)
                results.append((action, normalized))

        # Tri par score decroissant
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_results]

    def can_resolve(self, query: str, threshold: float = 0.3) -> bool:
        """Verifie si le cache peut resoudre la requete avec confiance suffisante."""
        results = self.resolve(query, max_results=1)
        return len(results) > 0 and results[0][1] >= threshold
