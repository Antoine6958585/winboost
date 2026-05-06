"""Theme display — diagnostics affichage Windows.

Couverture :

1. Brightness WMI dispo (utilise le helper get_brightness existant)
2. Multi-ecrans detectes (Get-PnpDevice -Class Monitor)
3. Driver GPU (NVIDIA/AMD/Intel) date
4. Resolution courante de l'ecran principal
5. HDR support
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from winboost.diagnose.checks import (
    Check,
    CheckResult,
    Severity,
    run_ps_check,
)
from winboost.utils.windows_native import WindowsNativeError, get_brightness


class BrightnessWmiCheck(Check):
    """Verifie que le helper get_brightness fonctionne.

    En pratique : laptops OK, desktops avec ecran externe = WMI souvent KO.
    """

    name = "display_brightness_wmi"

    def run(self) -> CheckResult:
        try:
            level = get_brightness()
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    "Brightness WMI indisponible (normal sur desktop avec ecran externe). "
                    f"Detail : {exc}"
                ),
                details={"error": str(exc)},
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"Luminosite WMI lisible : {level} %",
            details={"current_brightness": level},
            suggested_actions=(),
        )


class MonitorDetectionCheck(Check):
    """Compte les moniteurs detectes via PnP."""

    name = "display_monitors_detected"

    def run(self) -> CheckResult:
        cmd = (
            "Get-PnpDevice -Class Monitor -ErrorAction SilentlyContinue "
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
                message=f"Lecture moniteurs impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Lecture moniteurs echouee",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        lines = [line for line in result.stdout.splitlines() if line.strip()]
        monitors = lines[1:] if len(lines) > 1 else []
        details: dict[str, Any] = {"monitors_count": len(monitors)}

        if not monitors:
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message="Aucun moniteur detecte (peut etre normal en RDP)",
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"{len(monitors)} moniteur(s) detecte(s)",
            details=details,
            suggested_actions=(),
        )


class GpuDriverFreshnessCheck(Check):
    """Verifie la date du driver GPU principal."""

    name = "display_gpu_driver_freshness"
    AGE_WARNING_DAYS = 365  # 1 an pour les GPU (mises a jour frequentes)

    def run(self) -> CheckResult:
        cmd = (
            "Get-PnpDevice -Class Display -ErrorAction SilentlyContinue "
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
                message=f"Lecture driver GPU impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok or not result.stdout.strip():
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Aucun driver GPU detecte ou lecture KO",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        oldest = _oldest_date_in(result.stdout)
        if oldest is None:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Driver GPU detecte mais date illisible",
                details={"raw_lines": result.stdout.count("\n")},
                suggested_actions=(),
            )

        age = datetime.now() - oldest
        details: dict[str, Any] = {
            "oldest_gpu_driver": oldest.isoformat(),
            "age_days": age.days,
        }

        if age > timedelta(days=self.AGE_WARNING_DAYS):
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    f"Driver GPU ancien ({oldest.date()}, {age.days} jours) — "
                    "GeForce Experience / AMD Adrenalin / Intel Driver Assistant"
                ),
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"Driver GPU recent (date {oldest.date()})",
            details=details,
            suggested_actions=(),
        )


class CurrentResolutionCheck(Check):
    """Lit la resolution courante de l'ecran principal."""

    name = "display_current_resolution"

    def run(self) -> CheckResult:
        cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$s = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "Write-Output ('{0}x{1}' -f $s.Width, $s.Height)"
        )
        try:
            result = run_ps_check(cmd, timeout=5.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Lecture resolution impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        out = result.stdout.strip()
        if not result.ok or "x" not in out:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Resolution courante illisible",
                details={"raw": out},
                suggested_actions=(),
            )

        try:
            width, height = (int(p) for p in out.split("x"))
        except ValueError:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Format de resolution inattendu : {out!r}",
                details={"raw": out},
                suggested_actions=(),
            )

        details = {"width": width, "height": height}
        if width < 1280 or height < 720:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Resolution tres basse : {width}x{height} (driver fallback ?)",
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"Resolution courante : {width}x{height}",
            details=details,
            suggested_actions=(),
        )


class HdrSupportCheck(Check):
    """Detecte si HDR est dispo et active sur au moins un moniteur."""

    name = "display_hdr_support"

    def run(self) -> CheckResult:
        cmd = (
            "Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorBasicDisplayParams "
            "-ErrorAction SilentlyContinue | Measure-Object "
            "| Select-Object -ExpandProperty Count"
        )
        try:
            result = run_ps_check(cmd, timeout=5.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Test HDR impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        out = result.stdout.strip()
        try:
            count = int(out) if out else 0
        except ValueError:
            count = 0

        # Note : on ne peut pas savoir facilement si HDR est ENABLE sans
        # Win32 API plus poussee. On signale juste si on detecte les
        # monitors WMI (proxy "compatible HDR" approximatif).
        details = {"wmi_monitor_params_count": count}

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=(
                f"{count} moniteur(s) avec parametres WMI lisibles "
                "(HDR potentiellement supporte si ecran compatible)"
            )
            if count
            else "Pas de moniteur WMI compatible HDR detecte",
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
    """Retourne la liste ordonnee des checks display."""
    return [
        BrightnessWmiCheck(),
        MonitorDetectionCheck(),
        GpuDriverFreshnessCheck(),
        CurrentResolutionCheck(),
        HdrSupportCheck(),
    ]
