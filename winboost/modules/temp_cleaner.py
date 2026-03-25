"""Module temp_cleaner — Nettoyage des fichiers temporaires Windows."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)


def _get_temp_dirs() -> list[Path]:
    """Retourne les repertoires temporaires a scanner."""
    dirs = []
    # %TEMP% utilisateur
    user_temp = Path(tempfile.gettempdir())
    if user_temp.exists():
        dirs.append(user_temp)
    # Windows\Temp
    win_temp = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "Temp"
    if win_temp.exists() and win_temp != user_temp:
        dirs.append(win_temp)
    return dirs


def _dir_size(path: Path) -> int:
    """Calcule la taille totale d'un repertoire en octets."""
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    return total


def _format_size(size_bytes: int) -> str:
    """Formate une taille en octets en chaine lisible."""
    for unit in ("o", "Ko", "Mo", "Go"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} To"


class TempCleaner(BaseModule):
    """Nettoie les fichiers temporaires Windows."""

    @property
    def name(self) -> str:
        return "temp_cleaner"

    @property
    def description(self) -> str:
        return "Nettoyage des fichiers temporaires Windows"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def scan(self) -> ScanResult:
        """Scanne les dossiers temp et identifie les fichiers supprimables."""
        issues: list[Issue] = []
        total_size = 0

        for temp_dir in _get_temp_dirs():
            size = _dir_size(temp_dir)
            if size > 0:
                total_size += size
                # Compte les fichiers
                file_count = sum(1 for f in temp_dir.rglob("*") if f.is_file())
                issues.append(
                    Issue(
                        id=f"temp_{temp_dir.name.lower()}",
                        description=f"{temp_dir} : {file_count} fichiers ({_format_size(size)})",
                        detail=str(temp_dir),
                        risk_level=RiskLevel.LOW,
                        auto_fixable=True,
                        metadata={"path": str(temp_dir), "size": size, "files": file_count},
                    )
                )

        return ScanResult(
            module_name=self.name,
            issues=issues,
            summary=f"Fichiers temporaires : {_format_size(total_size)} recuperables",
            metadata={"total_size": total_size},
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        """Supprime les fichiers temporaires identifies."""
        fixed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for issue in scan_result.issues:
            temp_dir = Path(issue.metadata["path"])
            try:
                for entry in temp_dir.iterdir():
                    try:
                        if entry.is_file():
                            entry.unlink()
                            fixed.append(str(entry))
                        elif entry.is_dir():
                            shutil.rmtree(entry, ignore_errors=True)
                            fixed.append(str(entry))
                    except PermissionError:
                        skipped.append(f"{entry} (en cours d'utilisation)")
                    except OSError as e:
                        errors.append(f"{entry} : {e}")
            except PermissionError:
                skipped.append(f"{temp_dir} (acces refuse)")

        return FixResult(
            module_name=self.name,
            fixed=fixed,
            skipped=skipped,
            errors=errors,
            summary=f"{len(fixed)} elements supprimes, {len(skipped)} ignores",
        )
