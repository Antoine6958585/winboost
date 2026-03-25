"""NL Parser — Transforme les requetes en langage naturel en intents structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Intent:
    """Intent structure extrait d'une requete NL."""

    raw_query: str
    action: str = ""  # "optimize", "clean", "disable", "enable", "info", "fix"
    target: str = ""  # "telemetry", "temp_files", "startup", etc.
    category: str = ""  # "privacy", "performance", etc.
    confidence: float = 0.0
    source: str = ""  # "cache" ou "llm"
    metadata: dict[str, Any] = field(default_factory=dict)


# Patterns d'action reconnus
ACTION_PATTERNS: dict[str, list[str]] = {
    "disable": [
        "desactiver", "desactive", "couper", "arreter", "bloquer",
        "supprimer", "virer", "enlever", "retirer", "disable", "stop",
        "remove", "block", "turn off", "kill",
    ],
    "enable": [
        "activer", "active", "allumer", "demarrer", "lancer",
        "enable", "turn on", "start", "activate",
    ],
    "clean": [
        "nettoyer", "nettoyage", "vider", "purger", "liberer",
        "clean", "clear", "purge", "free", "wipe",
    ],
    "optimize": [
        "optimiser", "ameliorer", "booster", "accelerer",
        "optimize", "boost", "speed up", "improve", "tweak",
    ],
    "info": [
        "info", "informations", "afficher", "montrer", "voir",
        "status", "show", "display", "check", "diagnostic",
    ],
    "fix": [
        "reparer", "corriger", "fixer", "resoudre",
        "fix", "repair", "resolve", "restore",
    ],
}

# Patterns de categorie
CATEGORY_PATTERNS: dict[str, list[str]] = {
    "privacy": [
        "vie privee", "privacy", "telemetrie", "telemetry", "espion",
        "tracking", "camera", "micro", "publicite", "cortana",
    ],
    "performance": [
        "performance", "vitesse", "rapide", "lent", "ram", "memoire",
        "cpu", "processeur", "animation", "service",
    ],
    "cleanup": [
        "nettoyage", "temp", "temporaire", "cache", "log", "crash",
        "dump", "corbeille", "recycle",
    ],
    "dev_tools": [
        "dev", "npm", "pip", "gradle", "docker", "node_modules",
        "cargo", "maven", "vscode", "jetbrains",
    ],
    "network": [
        "reseau", "network", "dns", "wifi", "tcp", "ip", "ipv6",
        "winsock", "netbios",
    ],
    "security": [
        "securite", "security", "firewall", "pare-feu", "smb",
        "remote", "admin", "uac", "bitlocker",
    ],
    "appearance": [
        "apparence", "theme", "sombre", "dark", "clair", "taskbar",
        "barre des taches", "menu", "contexte",
    ],
    "gaming": [
        "jeu", "jeux", "game", "gaming", "fps", "gpu", "souris",
        "mouse", "nagle", "fullscreen",
    ],
    "system": [
        "systeme", "system", "fichier", "extensions", "caches",
        "explorateur", "explorer", "demarrage", "boot",
    ],
}


class NLParser:
    """Parse les requetes NL en intents structures."""

    def parse(self, query: str) -> Intent:
        """Parse une requete en langage naturel.

        Args:
            query: Requete utilisateur (ex: "desactive la telemetrie")

        Returns:
            Intent structure avec action, target, categorie, confiance.
        """
        query_lower = query.lower().strip()

        # Detecte l'action
        action, action_conf = self._detect_action(query_lower)

        # Detecte la categorie
        category, cat_conf = self._detect_category(query_lower)

        # La target est le reste de la requete apres nettoyage
        target = self._extract_target(query_lower)

        # Confiance = moyenne des sous-confiances
        confidence = (action_conf + cat_conf) / 2

        return Intent(
            raw_query=query,
            action=action,
            target=target,
            category=category,
            confidence=confidence,
            source="parser",
        )

    def _detect_action(self, query: str) -> tuple[str, float]:
        """Detecte le type d'action dans la requete."""
        best_action = "optimize"  # defaut
        best_score = 0.0

        for action, patterns in ACTION_PATTERNS.items():
            for pattern in patterns:
                if pattern in query:
                    score = len(pattern) / len(query) + 0.5
                    if score > best_score:
                        best_score = score
                        best_action = action

        return best_action, min(best_score, 1.0)

    def _detect_category(self, query: str) -> tuple[str, float]:
        """Detecte la categorie cible."""
        scores: dict[str, float] = {}

        for category, patterns in CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if pattern in query:
                    scores[category] = scores.get(category, 0) + len(pattern) / len(query) + 0.3

        if not scores:
            return "", 0.0

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        return best, min(scores[best], 1.0)

    def _extract_target(self, query: str) -> str:
        """Extrait la cible de la requete (mots significatifs)."""
        # Retire les mots d'action
        all_action_words = set()
        for patterns in ACTION_PATTERNS.values():
            all_action_words.update(patterns)

        words = query.split()
        target_words = [w for w in words if w not in all_action_words and len(w) > 2]
        return " ".join(target_words[:5])
