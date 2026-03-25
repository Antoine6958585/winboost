"""Module privacy_cleaner — Nettoyage des traces de navigation et donnees privees."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)

# Chemins relatifs au profil utilisateur
# (label, chemin relatif, description, risk_level)
PRIVACY_TARGETS: list[tuple[str, str, str, RiskLevel]] = [
    # Chrome
    ("Chrome Cache", r"AppData\Local\Google\Chrome\User Data\Default\Cache", "Cache navigateur Chrome", RiskLevel.LOW),
    ("Chrome Code Cache", r"AppData\Local\Google\Chrome\User Data\Default\Code Cache", "Cache code Chrome", RiskLevel.LOW),
    ("Chrome History", r"AppData\Local\Google\Chrome\User Data\Default\History", "Historique Chrome", RiskLevel.MEDIUM),
    # Edge
    ("Edge Cache", r"AppData\Local\Microsoft\Edge\User Data\Default\Cache", "Cache navigateur Edge", RiskLevel.LOW),
    ("Edge Code Cache", r"AppData\Local\Microsoft\Edge\User Data\Default\Code Cache", "Cache code Edge", RiskLevel.LOW),
    # Firefox
    ("Firefox Cache", r"AppData\Local\Mozilla\Firefox\Profiles", "Cache Firefox (tous profils)", RiskLevel.LOW),
    # Opera
    ("Opera Cache", r"AppData\Local\Opera Software\Opera Stable\Cache", "Cache Opera", RiskLevel.LOW),
    # Windows
    ("Recent Files", r"AppData\Roaming\Microsoft\Windows\Recent", "Fichiers recents Windows", RiskLevel.LOW),
    ("Thumbnails", r"AppData\Local\Microsoft\Windows\Explorer", "Cache miniatures Explorer", RiskLevel.LOW),
    ("Windows Temp", r"AppData\Local\Temp", "Fichiers temporaires utilisateur", RiskLevel.LOW),
    # Autres
    ("Prefetch", "", "Prefetch Windows", RiskLevel.MEDIUM),  # Chemin absolu gere a part
]


def _format_size(size_bytes: int) -> str:
    """Formate une taille en chaine lisible."""
    for unit in ("o", "Ko", "Mo", "Go"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} To"


def _safe_dir_size(path: Path) -> int:
    """Calcule la taille d'un repertoire de maniere securisee."""
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += _safe_dir_size(Path(entry.path))
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    return total


def _get_targets() -> list[dict[str, Any]]:
    """Construit la liste des cibles de nettoyage avec chemins absolus."""
    home = Path.home()
    targets: list[dict[str, Any]] = []

    for label, rel_path, desc, risk in PRIVACY_TARGETS:
        if label == "Prefetch":
            path = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "Prefetch"
        else:
            path = home / rel_path

        if path.exists():
            size = _safe_dir_size(path) if path.is_dir() else path.stat().st_size
            if size > 1024:  # > 1 Ko
                targets.append({
                    "label": label,
                    "path": str(path),
                    "description": desc,
                    "risk": risk,
                    "size": size,
                    "is_file": path.is_file(),
                })

    return targets


class PrivacyCleaner(BaseModule):
    """Nettoie les traces de navigation et donnees privees."""

    @property
    def name(self) -> str:
        return "privacy_cleaner"

    @property
    def description(self) -> str:
        return "Nettoyage traces navigateurs et donnees privees"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    def scan(self) -> ScanResult:
        """Detecte les traces et caches de navigation."""
        targets = _get_targets()
        issues: list[Issue] = []
        total_size = 0

        for t in targets:
            total_size += t["size"]
            issues.append(
                Issue(
                    id=f"privacy_{t['label'].lower().replace(' ', '_')}",
                    description=f"{t['label']} : {_format_size(t['size'])}",
                    detail=t["path"],
                    risk_level=t["risk"],
                    auto_fixable=t["risk"] in (RiskLevel.LOW, RiskLevel.MEDIUM),
                    metadata=t,
                )
            )

        return ScanResult(
            module_name=self.name,
            issues=issues,
            summary=f"Traces privees : {_format_size(total_size)} recuperables",
            metadata={"total_size": total_size, "target_count": len(targets)},
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        """Supprime les traces identifiees."""
        fixed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for issue in scan_result.issues:
            meta = issue.metadata
            path = Path(meta["path"])

            if not path.exists():
                skipped.append(f"{meta['label']} (introuvable)")
                continue

            try:
                if meta.get("is_file"):
                    path.unlink()
                    fixed.append(f"{meta['label']} — {_format_size(meta['size'])}")
                else:
                    # Supprime le contenu du dossier, pas le dossier lui-meme
                    cleaned = 0
                    for entry in path.iterdir():
                        try:
                            if entry.is_file():
                                entry.unlink()
                                cleaned += 1
                            elif entry.is_dir():
                                shutil.rmtree(entry, ignore_errors=True)
                                cleaned += 1
                        except (PermissionError, OSError):
                            continue
                    if cleaned > 0:
                        fixed.append(f"{meta['label']} — {cleaned} element(s)")
                    else:
                        skipped.append(f"{meta['label']} (rien a supprimer)")
            except PermissionError:
                skipped.append(f"{meta['label']} (acces refuse)")
            except OSError as e:
                errors.append(f"{meta['label']} : {e}")

        return FixResult(
            module_name=self.name,
            fixed=fixed,
            skipped=skipped,
            errors=errors,
            summary=f"{len(fixed)} cible(s) nettoyee(s), {len(skipped)} ignoree(s)",
        )
