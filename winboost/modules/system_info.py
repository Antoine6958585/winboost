"""Module system_info — Informations systeme (CPU, RAM, disque, OS)."""

from __future__ import annotations

import platform
from datetime import UTC, datetime

import psutil

from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)


def _format_size(size_bytes: int) -> str:
    """Formate une taille en octets en chaine lisible."""
    for unit in ("o", "Ko", "Mo", "Go"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} To"


def _uptime() -> str:
    """Retourne l'uptime du systeme en format lisible."""
    boot = datetime.fromtimestamp(psutil.boot_time(), tz=UTC)
    delta = datetime.now(tz=UTC) - boot
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}min"


class SystemInfo(BaseModule):
    """Collecte et affiche les informations systeme."""

    @property
    def name(self) -> str:
        return "system_info"

    @property
    def description(self) -> str:
        return "Informations systeme (CPU, RAM, disque, OS)"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.INFO

    def scan(self) -> ScanResult:
        """Collecte les infos systeme. Les 'issues' sont ici des points d'information."""
        issues: list[Issue] = []

        # OS
        os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
        issues.append(
            Issue(
                id="os_version",
                description=f"OS : {os_info}",
                risk_level=RiskLevel.INFO,
                auto_fixable=False,
                metadata={"os": os_info},
            )
        )

        # CPU
        cpu_name = platform.processor() or "Inconnu"
        cpu_count = psutil.cpu_count(logical=True) or 0
        cpu_freq = psutil.cpu_freq()
        freq_str = f" @ {cpu_freq.current:.0f} MHz" if cpu_freq else ""
        cpu_percent = psutil.cpu_percent(interval=0.5)
        issues.append(
            Issue(
                id="cpu_info",
                description=f"CPU : {cpu_name} ({cpu_count} threads{freq_str}) — {cpu_percent}%",
                risk_level=RiskLevel.INFO,
                auto_fixable=False,
                metadata={
                    "name": cpu_name,
                    "cores": cpu_count,
                    "usage_percent": cpu_percent,
                },
            )
        )

        # RAM
        ram = psutil.virtual_memory()
        issues.append(
            Issue(
                id="ram_info",
                description=(
                    f"RAM : {_format_size(ram.used)} / {_format_size(ram.total)} "
                    f"({ram.percent}% utilise)"
                ),
                risk_level=RiskLevel.INFO,
                auto_fixable=False,
                metadata={
                    "total": ram.total,
                    "used": ram.used,
                    "percent": ram.percent,
                },
            )
        )

        # Disques
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                issues.append(
                    Issue(
                        id=f"disk_{part.device.replace(':', '').replace('\\', '')}",
                        description=(
                            f"Disque {part.device} : "
                            f"{_format_size(usage.free)} libres / {_format_size(usage.total)} "
                            f"({usage.percent}% utilise)"
                        ),
                        risk_level=RiskLevel.INFO,
                        auto_fixable=False,
                        metadata={
                            "device": part.device,
                            "mountpoint": part.mountpoint,
                            "total": usage.total,
                            "free": usage.free,
                            "percent": usage.percent,
                        },
                    )
                )
            except (PermissionError, OSError):
                continue

        # Uptime
        uptime = _uptime()
        issues.append(
            Issue(
                id="uptime",
                description=f"Uptime : {uptime}",
                risk_level=RiskLevel.INFO,
                auto_fixable=False,
                metadata={"uptime": uptime},
            )
        )

        return ScanResult(
            module_name=self.name,
            issues=issues,
            summary=f"Systeme : {os_info} — RAM {ram.percent}% — CPU {cpu_percent}%",
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        """Module info-only — rien a corriger."""
        return FixResult(
            module_name=self.name,
            summary="Module lecture seule — aucune action applicable.",
        )
