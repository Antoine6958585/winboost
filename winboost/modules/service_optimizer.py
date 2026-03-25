"""Module service_optimizer — Analyse et optimisation des services Windows."""

from __future__ import annotations

import subprocess
from typing import Any

import psutil

from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)

# Services potentiellement desactivables (nom_service, description, risque)
# On liste uniquement les services non-critiques courants
OPTIONAL_SERVICES: dict[str, tuple[str, RiskLevel]] = {
    "DiagTrack": ("Telemetrie Windows (Connected User Experiences)", RiskLevel.LOW),
    "dmwappushservice": ("Push WAP messages (telemetrie)", RiskLevel.LOW),
    "RetailDemo": ("Service demo retail", RiskLevel.LOW),
    "MapsBroker": ("Telechargement donnees cartes offline", RiskLevel.LOW),
    "lfsvc": ("Service de geolocalisation", RiskLevel.LOW),
    "SharedAccess": ("Partage de connexion Internet (ICS)", RiskLevel.LOW),
    "RemoteRegistry": ("Modification registre a distance", RiskLevel.LOW),
    "Fax": ("Service de fax", RiskLevel.LOW),
    "XblAuthManager": ("Xbox Live Auth Manager", RiskLevel.LOW),
    "XblGameSave": ("Xbox Live Game Save", RiskLevel.LOW),
    "XboxGipSvc": ("Xbox Accessory Management", RiskLevel.LOW),
    "XboxNetApiSvc": ("Xbox Live Networking", RiskLevel.LOW),
    "WSearch": ("Windows Search (indexation)", RiskLevel.MEDIUM),
    "SysMain": ("Superfetch / SysMain (prefetch)", RiskLevel.MEDIUM),
    "TabletInputService": ("Service tactile / stylet", RiskLevel.LOW),
    "WMPNetworkSvc": ("Partage Windows Media Player", RiskLevel.LOW),
    "WerSvc": ("Rapport d'erreurs Windows", RiskLevel.LOW),
    "wisvc": ("Windows Insider Service", RiskLevel.LOW),
}

# Services systeme critiques a ne JAMAIS toucher
PROTECTED_SERVICES = {
    "wuauserv", "bits", "cryptsvc", "trustedinstaller",
    "windefend", "mpssvc", "bfe", "eventlog", "rpcss",
    "dcomlaunch", "lsass", "samss", "spooler", "dhcp",
    "dnscache", "nsi", "lanmanworkstation", "lanmanserver",
}


class ServiceOptimizer(BaseModule):
    """Analyse les services Windows et suggere des optimisations."""

    @property
    def name(self) -> str:
        return "service_optimizer"

    @property
    def description(self) -> str:
        return "Analyse et optimisation des services Windows"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.HIGH

    def scan(self) -> ScanResult:
        """Scanne les services Windows actifs et identifie les desactivables."""
        issues: list[Issue] = []
        running_optional = 0

        for service in psutil.win_service_iter():
            try:
                info = service.as_dict()
                svc_name = info.get("name", "")
                status = info.get("status", "")
                start_type = info.get("start_type", "")
                display = info.get("display_name", svc_name)

                # Verifie si c'est un service optionnel connu
                if svc_name in OPTIONAL_SERVICES and status == "running":
                    desc, risk = OPTIONAL_SERVICES[svc_name]
                    running_optional += 1
                    issues.append(
                        Issue(
                            id=f"svc_{svc_name}",
                            description=f"{display} — {desc}",
                            detail=f"Status: {status} | Start: {start_type}",
                            risk_level=risk,
                            auto_fixable=True,
                            metadata={
                                "name": svc_name,
                                "display_name": display,
                                "status": status,
                                "start_type": start_type,
                                "description": desc,
                            },
                        )
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                continue

        return ScanResult(
            module_name=self.name,
            issues=issues,
            summary=f"{running_optional} service(s) optionnel(s) actif(s)",
            metadata={"running_optional": running_optional},
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        """Arrete et desactive les services optionnels identifies.

        Necessite les droits administrateur.
        """
        fixed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for issue in scan_result.issues:
            meta = issue.metadata
            svc_name = meta["name"]

            # Double check : ne jamais toucher un service protege
            if svc_name.lower() in PROTECTED_SERVICES:
                skipped.append(f"{svc_name} (protege)")
                continue

            try:
                # Arrete le service
                stop_result = subprocess.run(
                    ["sc", "stop", svc_name],
                    capture_output=True, text=True, timeout=30,
                )
                # Desactive le demarrage automatique
                disable_result = subprocess.run(
                    ["sc", "config", svc_name, "start=", "disabled"],
                    capture_output=True, text=True, timeout=30,
                )

                if "SUCCESS" in stop_result.stdout or "STOP_PENDING" in stop_result.stdout:
                    fixed.append(f"{meta['display_name']} — arrete et desactive")
                elif "Access is denied" in stop_result.stderr:
                    skipped.append(f"{meta['display_name']} (admin requis)")
                else:
                    skipped.append(f"{meta['display_name']} (echec arret)")

            except subprocess.TimeoutExpired:
                errors.append(f"{meta['display_name']} (timeout)")
            except OSError as e:
                errors.append(f"{meta['display_name']} : {e}")

        return FixResult(
            module_name=self.name,
            fixed=fixed,
            skipped=skipped,
            errors=errors,
            summary=f"{len(fixed)} service(s) desactive(s), {len(skipped)} ignore(s)",
        )
