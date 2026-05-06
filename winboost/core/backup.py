"""Backup — Systeme de sauvegarde et restauration avant actions."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from winboost.core.config import DEFAULT_CONFIG_DIR

BACKUP_DIR = DEFAULT_CONFIG_DIR / "backups"


class BackupEntry:
    """Represente un point de sauvegarde."""

    def __init__(self, backup_id: str, module_name: str, description: str,
                 files: list[dict[str, str]], created_at: str | None = None) -> None:
        self.backup_id = backup_id
        self.module_name = module_name
        self.description = description
        self.files = files  # [{"original": path, "backup": path}]
        self.created_at = created_at or datetime.now(tz=UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "module_name": self.module_name,
            "description": self.description,
            "files": self.files,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupEntry:
        return cls(
            backup_id=data["backup_id"],
            module_name=data["module_name"],
            description=data["description"],
            files=data["files"],
            created_at=data.get("created_at"),
        )


class BackupManager:
    """Gere les sauvegardes et restaurations."""

    def __init__(self, backup_dir: Path | None = None, max_backups: int = 50) -> None:
        self._dir = backup_dir or BACKUP_DIR
        self._index_file = self._dir / "index.json"
        self._max_backups = max_backups
        self._entries: list[BackupEntry] = []
        self._load_index()

    def _load_index(self) -> None:
        """Charge l'index des sauvegardes."""
        if self._index_file.exists():
            with open(self._index_file, encoding="utf-8") as f:
                data = json.load(f)
            self._entries = [BackupEntry.from_dict(e) for e in data]
        else:
            self._entries = []

    def _save_index(self) -> None:
        """Sauvegarde l'index sur disque."""
        self._dir.mkdir(parents=True, exist_ok=True)
        with open(self._index_file, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in self._entries], f, indent=2, ensure_ascii=False)

    def _generate_id(self) -> str:
        """Genere un identifiant unique pour un backup."""
        ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        return f"backup_{ts}_{len(self._entries)}"

    def create_backup(self, module_name: str, description: str,
                      files_to_backup: list[str]) -> BackupEntry | None:
        """Cree un point de sauvegarde pour des fichiers.

        Args:
            module_name: Nom du module qui lance l'action.
            description: Description de l'action qui va etre effectuee.
            files_to_backup: Liste des chemins de fichiers a sauvegarder.

        Returns:
            L'entree de backup creee, ou None si rien a sauvegarder.
        """
        backup_id = self._generate_id()
        backup_subdir = self._dir / backup_id
        backup_subdir.mkdir(parents=True, exist_ok=True)

        saved_files: list[dict[str, str]] = []
        for filepath in files_to_backup:
            src = Path(filepath)
            if not src.exists():
                continue
            # Cree un nom unique dans le dossier backup
            dest = backup_subdir / src.name
            # Gere les doublons de nom
            counter = 0
            while dest.exists():
                counter += 1
                dest = backup_subdir / f"{src.stem}_{counter}{src.suffix}"
            try:
                if src.is_file():
                    shutil.copy2(src, dest)
                elif src.is_dir():
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                saved_files.append({"original": str(src), "backup": str(dest)})
            except (OSError, PermissionError):
                continue

        if not saved_files:
            # Rien a sauvegarder — supprime le dossier vide
            shutil.rmtree(backup_subdir, ignore_errors=True)
            return None

        entry = BackupEntry(
            backup_id=backup_id,
            module_name=module_name,
            description=description,
            files=saved_files,
        )
        self._entries.append(entry)
        self._cleanup_old()
        self._save_index()
        return entry

    def restore_backup(self, backup_id: str) -> tuple[int, int]:
        """Restaure un point de sauvegarde.

        Returns:
            (nombre de fichiers restaures, nombre d'erreurs)
        """
        entry = self.get_backup(backup_id)
        if entry is None:
            return (0, 0)

        restored = 0
        errors = 0
        for f in entry.files:
            backup_path = Path(f["backup"])
            original_path = Path(f["original"])
            if not backup_path.exists():
                errors += 1
                continue
            try:
                original_path.parent.mkdir(parents=True, exist_ok=True)
                if backup_path.is_file():
                    shutil.copy2(backup_path, original_path)
                elif backup_path.is_dir():
                    shutil.copytree(backup_path, original_path, dirs_exist_ok=True)
                restored += 1
            except (OSError, PermissionError):
                errors += 1

        return (restored, errors)

    def get_backup(self, backup_id: str) -> BackupEntry | None:
        """Recupere un backup par son ID."""
        for entry in self._entries:
            if entry.backup_id == backup_id:
                return entry
        return None

    def list_backups(self, module_name: str | None = None) -> list[BackupEntry]:
        """Liste les backups, optionnellement filtres par module."""
        if module_name:
            return [e for e in self._entries if e.module_name == module_name]
        return list(self._entries)

    def delete_backup(self, backup_id: str) -> bool:
        """Supprime un backup et ses fichiers."""
        entry = self.get_backup(backup_id)
        if entry is None:
            return False

        # Supprime le dossier de backup
        backup_subdir = self._dir / backup_id
        if backup_subdir.exists():
            shutil.rmtree(backup_subdir, ignore_errors=True)

        self._entries = [e for e in self._entries if e.backup_id != backup_id]
        self._save_index()
        return True

    def _cleanup_old(self) -> None:
        """Supprime les backups les plus anciens si la limite est depassee."""
        while len(self._entries) > self._max_backups:
            oldest = self._entries.pop(0)
            backup_subdir = self._dir / oldest.backup_id
            if backup_subdir.exists():
                shutil.rmtree(backup_subdir, ignore_errors=True)
