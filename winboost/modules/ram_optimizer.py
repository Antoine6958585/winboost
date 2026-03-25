"""Module ram_optimizer — Analyse et optimisation de la memoire vive."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
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
HIGH_RAM_PERCENT = 80  # % d'utilisation RAM considere comme eleve
HIGH_PROCESS_MB = 500  # Processus utilisant plus de X Mo

# Processus systeme a ne jamais toucher
PROTECTED_PROCESSES = {
    "system", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
    "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "winlogon.exe",
    "taskhostw.exe", "runtimebroker.exe", "searchindexer.exe",
    "securityhealthservice.exe", "msmpeng.exe", "audiodg.exe",
}


def _format_mb(bytes_val: int) -> str:
    """Formate en Mo."""
    return f"{bytes_val / (1024 * 1024):.0f} Mo"


def _get_heavy_processes(threshold_mb: int = HIGH_PROCESS_MB) -> list[dict[str, Any]]:
    """Retourne les processus utilisant plus de threshold_mb de RAM."""
    heavy: list[dict[str, Any]] = []
    threshold_bytes = threshold_mb * 1024 * 1024

    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mem = proc.info["memory_info"]
            if mem and mem.rss > threshold_bytes:
                name = proc.info["name"] or "inconnu"
                is_protected = name.lower() in PROTECTED_PROCESSES
                heavy.append({
                    "pid": proc.info["pid"],
                    "name": name,
                    "rss": mem.rss,
                    "is_protected": is_protected,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    heavy.sort(key=lambda p: p["rss"], reverse=True)
    return heavy


class RamOptimizer(BaseModule):
    """Analyse l'utilisation RAM et suggere des optimisations."""

    @property
    def name(self) -> str:
        return "ram_optimizer"

    @property
    def description(self) -> str:
        return "Analyse et optimisation de la memoire vive"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    def scan(self) -> ScanResult:
        """Analyse la RAM : utilisation globale + processus gourmands."""
        issues: list[Issue] = []
        ram = psutil.virtual_memory()

        # Utilisation globale
        if ram.percent >= HIGH_RAM_PERCENT:
            issues.append(
                Issue(
                    id="ram_high_usage",
                    description=(
                        f"Utilisation RAM elevee : {ram.percent}% "
                        f"({_format_mb(ram.used)} / {_format_mb(ram.total)})"
                    ),
                    risk_level=RiskLevel.MEDIUM,
                    auto_fixable=False,
                    metadata={"percent": ram.percent, "used": ram.used, "total": ram.total},
                )
            )

        # Processus gourmands
        heavy = _get_heavy_processes()
        for proc in heavy:
            risk = RiskLevel.HIGH if proc["is_protected"] else RiskLevel.MEDIUM
            issues.append(
                Issue(
                    id=f"ram_proc_{proc['pid']}",
                    description=(
                        f"{proc['name']} (PID {proc['pid']}) — {_format_mb(proc['rss'])}"
                    ),
                    risk_level=risk,
                    auto_fixable=not proc["is_protected"],
                    metadata=proc,
                )
            )

        return ScanResult(
            module_name=self.name,
            issues=issues,
            summary=(
                f"RAM {ram.percent}% — {_format_mb(ram.available)} disponibles — "
                f"{len(heavy)} processus gourmand(s)"
            ),
            metadata={
                "ram_percent": ram.percent,
                "ram_available": ram.available,
                "heavy_count": len(heavy),
            },
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        """Tente de liberer la RAM en vidant les working sets des processus non proteges."""
        fixed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for issue in scan_result.issues:
            meta = issue.metadata
            if "pid" not in meta:
                continue  # Skip l'issue globale

            if meta.get("is_protected"):
                skipped.append(f"{meta['name']} (protege)")
                continue

            pid = meta["pid"]
            try:
                # Tente de reduire le working set via l'API Windows
                proc = psutil.Process(pid)
                if not proc.is_running():
                    skipped.append(f"{meta['name']} (termine)")
                    continue

                # EmptyWorkingSet via kernel32
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                handle = kernel32.OpenProcess(0x1F0FFF, False, pid)  # PROCESS_ALL_ACCESS
                if handle:
                    result = kernel32.SetProcessWorkingSetSizeEx(
                        handle,
                        ctypes.c_size_t(-1),  # type: ignore[arg-type]
                        ctypes.c_size_t(-1),  # type: ignore[arg-type]
                        0,
                    )
                    kernel32.CloseHandle(handle)
                    if result:
                        fixed.append(f"{meta['name']} (PID {pid}) — working set reduit")
                    else:
                        skipped.append(f"{meta['name']} (PID {pid}) — echec reduction")
                else:
                    skipped.append(f"{meta['name']} (PID {pid}) — acces refuse")

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                skipped.append(f"{meta['name']} (PID {pid}) — inaccessible")
            except OSError as e:
                errors.append(f"{meta['name']} (PID {pid}) : {e}")

        return FixResult(
            module_name=self.name,
            fixed=fixed,
            skipped=skipped,
            errors=errors,
            summary=f"{len(fixed)} processus optimise(s), {len(skipped)} ignore(s)",
        )
