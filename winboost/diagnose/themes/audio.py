"""Theme audio — diagnostics audio Windows.

Couverture :

1. Service `Audiosrv` (Windows Audio)
2. Default playback device present + non-mute
3. Default recording device present
4. Drivers audio version (date plus ancienne)
5. Conflits multiples default devices
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from winboost.diagnose.checks import (
    Check,
    CheckResult,
    Severity,
    run_ps_check,
    service_status,
)
from winboost.utils.windows_native import WindowsNativeError


class AudioServiceCheck(Check):
    """Verifie le service Audiosrv."""

    name = "audio_service_status"

    def run(self) -> CheckResult:
        status = service_status("Audiosrv")
        details = {"service": "Audiosrv", "status": status}

        if status == "running":
            return CheckResult(
                name=self.name,
                severity=Severity.OK.value,
                message="Service Audiosrv en cours d'execution",
                details=details,
                suggested_actions=(),
            )
        if status in {"stopped", "stop_pending"}:
            return CheckResult(
                name=self.name,
                severity=Severity.CRITICAL.value,
                message=f"Service Audiosrv arrete ({status}) — pas de son possible",
                details=details,
                suggested_actions=(),
            )
        return CheckResult(
            name=self.name,
            severity=Severity.WARNING.value,
            message=f"Service Audiosrv dans un etat inhabituel : {status}",
            details=details,
            suggested_actions=(),
        )


class DefaultPlaybackDeviceCheck(Check):
    """Verifie qu'un default playback device existe et n'est pas mute."""

    name = "audio_default_playback"

    def run(self) -> CheckResult:
        cmd = (
            "Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue "
            "| Where-Object { $_.Status -eq 'OK' } "
            "| Select-Object FriendlyName "
            "| ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=5.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Lecture audio endpoints impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Lecture audio endpoints echouee",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        lines = [line for line in result.stdout.splitlines() if line.strip()]
        endpoints = lines[1:] if len(lines) > 1 else []
        details: dict[str, Any] = {"endpoints_count": len(endpoints)}

        if not endpoints:
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message="Aucun audio endpoint actif (haut-parleur/casque)",
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"{len(endpoints)} audio endpoint(s) actif(s)",
            details=details,
            suggested_actions=(),
        )


class DefaultRecordingDeviceCheck(Check):
    """Verifie la presence d'un device de capture (micro)."""

    name = "audio_default_recording"

    def run(self) -> CheckResult:
        cmd = (
            "Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue "
            "| Where-Object { $_.FriendlyName -match 'Microphone|Mic|Input|Capture' } "
            "| Select-Object FriendlyName, Status "
            "| ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=5.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Lecture micro impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Lecture micro echouee",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        lines = [line for line in result.stdout.splitlines() if line.strip()]
        micros = lines[1:] if len(lines) > 1 else []
        details: dict[str, Any] = {"micros_count": len(micros)}

        if not micros:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Aucun micro detecte (normal si PC sans webcam ni casque)",
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"{len(micros)} micro(s) detecte(s)",
            details=details,
            suggested_actions=(),
        )


class AudioDriverFreshnessCheck(Check):
    """Verifie la date du driver audio principal (>2 ans = warning)."""

    name = "audio_driver_freshness"
    AGE_WARNING_DAYS = 365 * 2

    def run(self) -> CheckResult:
        cmd = (
            "Get-PnpDevice -Class MEDIA -ErrorAction SilentlyContinue "
            "| Where-Object { $_.Status -eq 'OK' } "
            "| ForEach-Object { "
            "  $d = Get-PnpDeviceProperty -InstanceId $_.InstanceId "
            "       -KeyName 'DEVPKEY_Device_DriverDate' -ErrorAction SilentlyContinue; "
            "  if ($d) { [PSCustomObject]@{ Name=$_.FriendlyName; DriverDate=$d.Data } } "
            "} | ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=10.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Lecture driver audio impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok or not result.stdout.strip():
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Aucun driver audio detecte ou lecture KO",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        oldest = _oldest_date_in(result.stdout)
        if oldest is None:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Driver audio detecte mais date illisible",
                details={"raw_lines": result.stdout.count("\n")},
                suggested_actions=(),
            )

        age = datetime.now() - oldest
        details: dict[str, Any] = {
            "oldest_audio_driver": oldest.isoformat(),
            "age_days": age.days,
        }

        if age > timedelta(days=self.AGE_WARNING_DAYS):
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    f"Driver audio ancien ({oldest.date()}, {age.days} jours) — "
                    "Windows Update Optional ou site fabricant"
                ),
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"Driver audio recent (date {oldest.date()})",
            details=details,
            suggested_actions=(),
        )


class MultipleEndpointsConflictCheck(Check):
    """Flag si >5 endpoints AudioEndpoint sont OK simultanement.

    Symptome typique : le PC bascule aleatoirement entre HP, casque BT,
    moniteur HDMI sans intervention utilisateur.
    """

    name = "audio_multiple_endpoints"

    def run(self) -> CheckResult:
        cmd = (
            "Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue "
            "| Where-Object { $_.Status -eq 'OK' } "
            "| Measure-Object | Select-Object -ExpandProperty Count"
        )
        try:
            result = run_ps_check(cmd, timeout=5.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Comptage endpoints audio impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        out = result.stdout.strip()
        try:
            count = int(out) if out else 0
        except ValueError:
            count = 0

        details = {"endpoints_ok": count}

        if count > 5:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    f"{count} endpoints audio actifs simultanement — risque de bascule "
                    "automatique inattendue"
                ),
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"{count} endpoint(s) audio actif(s)",
            details=details,
            suggested_actions=(),
        )


def _oldest_date_in(text: str) -> datetime | None:
    candidates = []
    for token in text.replace('"', " ").replace(",", " ").split():
        for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                candidates.append(datetime.strptime(token, fmt))
                break
            except ValueError:
                continue
    return min(candidates) if candidates else None


def get_checks() -> list[Check]:
    """Retourne la liste ordonnee des checks audio."""
    return [
        AudioServiceCheck(),
        DefaultPlaybackDeviceCheck(),
        DefaultRecordingDeviceCheck(),
        AudioDriverFreshnessCheck(),
        MultipleEndpointsConflictCheck(),
    ]
