"""Module startup_manager — Gestion des programmes au demarrage Windows."""

from __future__ import annotations

import os
import winreg
from dataclasses import dataclass
from pathlib import Path

from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)

# Cles du registre contenant les programmes au demarrage
STARTUP_REGISTRY_KEYS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
]

# Dossiers Startup
STARTUP_FOLDERS = [
    Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup",
    Path(os.environ.get("PROGRAMDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup",
]

# Programmes systeme critiques a ne jamais toucher
SYSTEM_CRITICAL = {
    "securityhealth",
    "windowsdefender",
    "securitycenter",
    "ctfmon",
    "explorer",
}


@dataclass
class StartupEntry:
    """Entree de programme au demarrage."""

    name: str
    command: str
    source: str  # "registry" ou "folder"
    location: str  # Cle registre ou chemin dossier
    hive: int | None = None  # HKEY pour les entrees registre
    is_system: bool = False


def _read_registry_entries() -> list[StartupEntry]:
    """Lit les entrees de demarrage depuis le registre."""
    entries: list[StartupEntry] = []
    for hive, key_path in STARTUP_REGISTRY_KEYS:
        try:
            with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        is_sys = any(s in name.lower() for s in SYSTEM_CRITICAL)
                        entries.append(
                            StartupEntry(
                                name=name,
                                command=str(value),
                                source="registry",
                                location=key_path,
                                hive=hive,
                                is_system=is_sys,
                            )
                        )
                        i += 1
                    except OSError:
                        break
        except OSError:
            continue
    return entries


def _read_folder_entries() -> list[StartupEntry]:
    """Lit les raccourcis dans les dossiers Startup."""
    entries: list[StartupEntry] = []
    for folder in STARTUP_FOLDERS:
        if not folder.exists():
            continue
        for item in folder.iterdir():
            if item.is_file():
                entries.append(
                    StartupEntry(
                        name=item.stem,
                        command=str(item),
                        source="folder",
                        location=str(folder),
                        is_system=False,
                    )
                )
    return entries


class StartupManager(BaseModule):
    """Gere les programmes au demarrage de Windows."""

    @property
    def name(self) -> str:
        return "startup_manager"

    @property
    def description(self) -> str:
        return "Gestion des programmes au demarrage Windows"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    def scan(self) -> ScanResult:
        """Scanne les programmes au demarrage (registre + dossiers)."""
        registry_entries = _read_registry_entries()
        folder_entries = _read_folder_entries()
        all_entries = registry_entries + folder_entries

        issues: list[Issue] = []
        for entry in all_entries:
            risk = RiskLevel.HIGH if entry.is_system else RiskLevel.MEDIUM
            issues.append(
                Issue(
                    id=f"startup_{entry.source}_{entry.name}",
                    description=f"{entry.name} — {entry.command[:80]}",
                    detail=f"Source: {entry.source} | {entry.location}",
                    risk_level=risk,
                    auto_fixable=not entry.is_system,
                    metadata={
                        "name": entry.name,
                        "command": entry.command,
                        "source": entry.source,
                        "location": entry.location,
                        "hive": entry.hive,
                        "is_system": entry.is_system,
                    },
                )
            )

        non_system = [e for e in all_entries if not e.is_system]
        return ScanResult(
            module_name=self.name,
            issues=issues,
            summary=(
                f"{len(all_entries)} programme(s) au demarrage "
                f"({len(non_system)} desactivable(s))"
            ),
            metadata={"total": len(all_entries), "removable": len(non_system)},
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        """Desactive les programmes non-systeme au demarrage."""
        fixed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for issue in scan_result.issues:
            meta = issue.metadata
            if meta.get("is_system"):
                skipped.append(f"{meta['name']} (programme systeme)")
                continue

            if meta["source"] == "registry":
                try:
                    hive = meta["hive"]
                    with winreg.OpenKey(
                        hive, meta["location"], 0, winreg.KEY_SET_VALUE
                    ) as key:
                        winreg.DeleteValue(key, meta["name"])
                    fixed.append(f"{meta['name']} (registre)")
                except PermissionError:
                    skipped.append(f"{meta['name']} (acces refuse — admin requis)")
                except OSError as e:
                    errors.append(f"{meta['name']} : {e}")

            elif meta["source"] == "folder":
                try:
                    path = Path(meta["command"])
                    if path.exists():
                        path.unlink()
                        fixed.append(f"{meta['name']} (dossier)")
                    else:
                        skipped.append(f"{meta['name']} (fichier introuvable)")
                except OSError as e:
                    errors.append(f"{meta['name']} : {e}")

        return FixResult(
            module_name=self.name,
            fixed=fixed,
            skipped=skipped,
            errors=errors,
            summary=f"{len(fixed)} desactive(s), {len(skipped)} ignore(s)",
        )
