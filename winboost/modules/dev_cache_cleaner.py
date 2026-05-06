"""Module dev_cache_cleaner — Nettoyage des caches de developpement."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)

# Caches developpeur connus (label, chemin relatif au home, description)
DEV_CACHE_TARGETS: list[tuple[str, str, str]] = [
    # Node.js / npm / yarn / pnpm
    ("npm cache", r"AppData\Local\npm-cache", "Cache global npm"),
    ("yarn cache", r"AppData\Local\Yarn\Cache", "Cache global Yarn"),
    ("pnpm store", r"AppData\Local\pnpm-store", "Store global pnpm"),
    # Python
    ("pip cache", r"AppData\Local\pip\cache", "Cache pip"),
    ("__pycache__", "", "Bytecode Python compile"),  # Gere a part
    # .NET / NuGet
    ("NuGet cache", r"AppData\Local\NuGet\v3-cache", "Cache packages NuGet v3"),
    ("NuGet HTTP cache", r"AppData\Local\NuGet\plugins-cache", "Cache HTTP NuGet"),
    # Gradle / Maven
    ("Gradle cache", r".gradle\caches", "Cache builds Gradle"),
    ("Maven repo", r".m2\repository", "Repository local Maven"),
    # Rust
    ("Cargo registry", r".cargo\registry", "Registry crates.io local"),
    # Go
    ("Go mod cache", r"AppData\Local\go\pkg\mod\cache", "Cache modules Go"),
    # Docker
    ("Docker data", r"AppData\Local\Docker\wsl", "Donnees Docker Desktop (WSL)"),
    # VS Code
    ("VS Code cache", r"AppData\Roaming\Code\Cache", "Cache VS Code"),
    ("VS Code CachedData", r"AppData\Roaming\Code\CachedData", "Donnees en cache VS Code"),
    ("VS Code CachedExtensions", r"AppData\Roaming\Code\CachedExtensionVSIXs", "Extensions en cache VS Code"),
    # JetBrains
    ("JetBrains caches", r"AppData\Local\JetBrains", "Caches IDEs JetBrains"),
    # Visual Studio
    ("VS ComponentCache", r"AppData\Local\Microsoft\VisualStudio\ComponentModelCache", "Cache composants Visual Studio"),
]


def _format_size(size_bytes: int) -> str:
    """Formate une taille en chaine lisible."""
    for unit in ("o", "Ko", "Mo", "Go"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} To"


def _dir_size(path: Path) -> int:
    """Calcule la taille d'un repertoire."""
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += _dir_size(Path(entry.path))
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    return total


class DevCacheCleaner(BaseModule):
    """Nettoie les caches et artefacts de developpement."""

    @property
    def name(self) -> str:
        return "dev_cache_cleaner"

    @property
    def description(self) -> str:
        return "Nettoyage caches developpement (npm, pip, gradle, etc.)"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def scan(self) -> ScanResult:
        """Detecte les caches de developpement presents."""
        home = Path.home()
        issues: list[Issue] = []
        total_size = 0

        for label, rel_path, desc in DEV_CACHE_TARGETS:
            if not rel_path:
                continue  # Skip les entrees speciales

            path = home / rel_path
            if not path.exists():
                continue

            size = _dir_size(path)
            if size < 1024 * 1024:  # Skip < 1 Mo
                continue

            total_size += size
            issues.append(
                Issue(
                    id=f"dev_{label.lower().replace(' ', '_')}",
                    description=f"{label} : {_format_size(size)}",
                    detail=str(path),
                    risk_level=RiskLevel.LOW,
                    auto_fixable=True,
                    metadata={"label": label, "path": str(path), "size": size, "desc": desc},
                )
            )

        return ScanResult(
            module_name=self.name,
            issues=issues,
            summary=f"Caches dev : {_format_size(total_size)} recuperables",
            metadata={"total_size": total_size},
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        """Supprime les caches de developpement identifies."""
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
                # Supprime le contenu, pas le dossier racine
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
                    fixed.append(f"{meta['label']} — {_format_size(meta['size'])}")
                else:
                    skipped.append(f"{meta['label']} (verrouille)")
            except PermissionError:
                skipped.append(f"{meta['label']} (acces refuse)")
            except OSError as e:
                errors.append(f"{meta['label']} : {e}")

        return FixResult(
            module_name=self.name,
            fixed=fixed,
            skipped=skipped,
            errors=errors,
            summary=f"{len(fixed)} cache(s) nettoye(s), {len(skipped)} ignore(s)",
        )
