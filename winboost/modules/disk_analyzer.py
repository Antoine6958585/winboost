"""Module disk_analyzer — Analyse de l'espace disque et detection gros fichiers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psutil

from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)

# Seuils
DISK_WARNING_PERCENT = 85  # % d'utilisation disque = warning
BIG_FILE_MB = 500  # Fichiers > X Mo
MAX_BIG_FILES = 20  # Nombre max de gros fichiers a reporter

# Dossiers connus recuperables (relatifs au profil utilisateur)
KNOWN_RECLAIMABLE = [
    ("Downloads", "Telechargements"),
    ("AppData/Local/Temp", "Fichiers temporaires"),
    ("AppData/Local/CrashDumps", "Crash dumps"),
    ("AppData/Local/D3DSCache", "Cache DirectX Shader"),
    ("AppData/Local/Microsoft/Windows/INetCache", "Cache Internet"),
]


def _format_size(size_bytes: int) -> str:
    """Formate une taille en chaine lisible."""
    for unit in ("o", "Ko", "Mo", "Go"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} To"


def _dir_size_fast(path: Path, max_depth: int = 2) -> int:
    """Calcule la taille d'un repertoire (profondeur limitee pour la perf)."""
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False) and max_depth > 0:
                    total += _dir_size_fast(Path(entry.path), max_depth - 1)
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    return total


def _find_big_files(root: Path, threshold_bytes: int, max_results: int) -> list[dict[str, Any]]:
    """Trouve les gros fichiers dans un repertoire."""
    big_files: list[dict[str, Any]] = []
    try:
        for entry in os.scandir(root):
            try:
                if entry.is_file(follow_symlinks=False):
                    size = entry.stat(follow_symlinks=False).st_size
                    if size >= threshold_bytes:
                        big_files.append({"path": entry.path, "size": size})
                elif entry.is_dir(follow_symlinks=False):
                    big_files.extend(_find_big_files(
                        Path(entry.path), threshold_bytes, max_results - len(big_files)
                    ))
                if len(big_files) >= max_results:
                    break
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    big_files.sort(key=lambda f: f["size"], reverse=True)
    return big_files[:max_results]


class DiskAnalyzer(BaseModule):
    """Analyse l'espace disque et identifie les fichiers/dossiers volumineux."""

    @property
    def name(self) -> str:
        return "disk_analyzer"

    @property
    def description(self) -> str:
        return "Analyse de l'espace disque et detection gros fichiers"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def scan(self) -> ScanResult:
        """Analyse les disques : espace libre, dossiers recuperables, gros fichiers."""
        issues: list[Issue] = []
        total_reclaimable = 0

        # Espace disque par partition
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                if usage.percent >= DISK_WARNING_PERCENT:
                    issues.append(
                        Issue(
                            id=f"disk_low_{part.device.replace(':', '').replace(chr(92), '')}",
                            description=(
                                f"Disque {part.device} presque plein : {usage.percent}% "
                                f"({_format_size(usage.free)} libres)"
                            ),
                            risk_level=RiskLevel.MEDIUM,
                            auto_fixable=False,
                            metadata={
                                "device": part.device,
                                "percent": usage.percent,
                                "free": usage.free,
                            },
                        )
                    )
            except (PermissionError, OSError):
                continue

        # Dossiers connus recuperables
        home = Path.home()
        for rel_path, label in KNOWN_RECLAIMABLE:
            folder = home / rel_path
            if folder.exists():
                size = _dir_size_fast(folder)
                if size > 10 * 1024 * 1024:  # > 10 Mo
                    total_reclaimable += size
                    issues.append(
                        Issue(
                            id=f"disk_reclaimable_{rel_path.replace('/', '_').lower()}",
                            description=f"{label} : {_format_size(size)}",
                            detail=str(folder),
                            risk_level=RiskLevel.LOW,
                            auto_fixable=True,
                            metadata={
                                "path": str(folder),
                                "size": size,
                                "label": label,
                                "category": "reclaimable",
                            },
                        )
                    )

        # Gros fichiers dans le profil utilisateur
        threshold = BIG_FILE_MB * 1024 * 1024
        big_files = _find_big_files(home / "Downloads", threshold, MAX_BIG_FILES)
        for bf in big_files:
            issues.append(
                Issue(
                    id=f"disk_bigfile_{Path(bf['path']).stem[:30]}",
                    description=f"Gros fichier : {Path(bf['path']).name} ({_format_size(bf['size'])})",
                    detail=bf["path"],
                    risk_level=RiskLevel.LOW,
                    auto_fixable=False,  # Ne pas supprimer automatiquement
                    metadata={"path": bf["path"], "size": bf["size"], "category": "big_file"},
                )
            )

        return ScanResult(
            module_name=self.name,
            issues=issues,
            summary=f"{_format_size(total_reclaimable)} potentiellement recuperables",
            metadata={"total_reclaimable": total_reclaimable, "big_files": len(big_files)},
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        """Nettoie les dossiers recuperables identifies (pas les gros fichiers utilisateur)."""
        fixed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for issue in scan_result.issues:
            meta = issue.metadata
            category = meta.get("category", "")

            if category == "big_file":
                skipped.append(f"{Path(meta['path']).name} (fichier utilisateur — suppression manuelle)")
                continue

            if category != "reclaimable":
                continue

            folder = Path(meta["path"])
            if not folder.exists():
                skipped.append(f"{meta['label']} (dossier introuvable)")
                continue

            cleaned = 0
            for entry in folder.iterdir():
                try:
                    if entry.is_file():
                        size = entry.stat().st_size
                        entry.unlink()
                        cleaned += size
                    elif entry.is_dir():
                        import shutil
                        shutil.rmtree(entry, ignore_errors=True)
                        cleaned += meta.get("size", 0)
                except (PermissionError, OSError):
                    continue

            if cleaned > 0:
                fixed.append(f"{meta['label']} — {_format_size(cleaned)} liberes")
            else:
                skipped.append(f"{meta['label']} (rien a nettoyer)")

        return FixResult(
            module_name=self.name,
            fixed=fixed,
            skipped=skipped,
            errors=errors,
            summary=f"{len(fixed)} dossier(s) nettoye(s), {len(skipped)} ignore(s)",
        )
