"""Gestion de la configuration locale WinBoost (JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Repertoire de config par defaut : %LOCALAPPDATA%/WinBoost/
DEFAULT_CONFIG_DIR = Path.home() / "AppData" / "Local" / "WinBoost"
DEFAULT_CONFIG_FILE = "config.json"

# Configuration par defaut
DEFAULT_CONFIG: dict[str, Any] = {
    "profile": "safe",  # safe | power_user | expert
    "dry_run_first": True,
    "max_risk": "low",  # Depend du profil
    "language": "fr",
    "modules_enabled": [
        "temp_cleaner",
        "system_info",
        "startup_manager",
        "ram_optimizer",
        "disk_analyzer",
        "privacy_cleaner",
        "dev_cache_cleaner",
        "service_optimizer",
    ],
    "backup": {
        "enabled": True,
        "max_backups": 50,
    },
}

# Mapping profil -> contraintes
PROFILE_SETTINGS: dict[str, dict[str, Any]] = {
    "safe": {"max_risk": "low", "dry_run_first": True},
    "power_user": {"max_risk": "medium", "dry_run_first": False},
    "expert": {"max_risk": "high", "dry_run_first": False},
}


class Config:
    """Charge et sauvegarde la configuration JSON locale."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or DEFAULT_CONFIG_DIR
        self._file = self._dir / DEFAULT_CONFIG_FILE
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Charge le fichier config ou cree les valeurs par defaut."""
        if self._file.exists():
            with open(self._file, encoding="utf-8") as f:
                self._data = json.load(f)
            # Merge les cles manquantes depuis DEFAULT_CONFIG
            for key, value in DEFAULT_CONFIG.items():
                if key not in self._data:
                    self._data[key] = value
        else:
            self._data = DEFAULT_CONFIG.copy()

    def save(self) -> None:
        """Ecrit la config sur disque."""
        self._dir.mkdir(parents=True, exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Recupere une valeur de config."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Modifie une valeur de config (ne sauvegarde pas automatiquement)."""
        self._data[key] = value

    @property
    def profile(self) -> str:
        return self._data.get("profile", "safe")

    @profile.setter
    def profile(self, value: str) -> None:
        if value not in PROFILE_SETTINGS:
            raise ValueError(f"Profil invalide : {value}. Choix : {list(PROFILE_SETTINGS)}")
        self._data["profile"] = value
        # Applique les contraintes du profil
        for k, v in PROFILE_SETTINGS[value].items():
            self._data[k] = v

    @property
    def max_risk(self) -> str:
        return self._data.get("max_risk", "low")

    @property
    def dry_run_first(self) -> bool:
        return self._data.get("dry_run_first", True)

    @property
    def modules_enabled(self) -> list[str]:
        return self._data.get("modules_enabled", [])

    def as_dict(self) -> dict[str, Any]:
        """Retourne une copie de toute la config."""
        return self._data.copy()
