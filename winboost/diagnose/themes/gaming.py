"""Theme gaming — diagnostics drivers gamepad et compatibilite jeux.

Couverture :

1. Gamepads detectes (XInput / DirectInput) via HID
2. Driver Xbox Controller version (date)
3. Steam Input config (Steam present, registry stable)
4. Conflits dual-input (gamepad reconnu en XInput ET DirectInput)
5. Service `XblGameSave` (utile pour Rocket League / Game Pass)
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


class GamepadDetectionCheck(Check):
    """Liste les gamepads detectes (HID Controller / Wireless / Gamepad)."""

    name = "gaming_gamepad_detection"

    def run(self) -> CheckResult:
        pattern = "Gamepad|Controller|Joystick|Xbox|Wireless Controller"
        cmd = (
            "Get-PnpDevice -ErrorAction SilentlyContinue "
            f"| Where-Object {{ $_.FriendlyName -match '{pattern}' }} "
            "| Select-Object FriendlyName, Status, Class "
            "| ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=10.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Lecture gamepads impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Lecture gamepads echouee",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        lines = [line for line in result.stdout.splitlines() if line.strip()]
        gamepads = lines[1:] if len(lines) > 1 else []
        details: dict[str, Any] = {"gamepads_count": len(gamepads)}

        if not gamepads:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Aucun gamepad detecte (HID / XInput / DirectInput)",
                details=details,
                suggested_actions=(),
            )

        ok_count = sum(1 for line in gamepads if '"OK"' in line)
        details["gamepads_ok"] = ok_count

        if ok_count == 0:
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message=f"{len(gamepads)} gamepad(s) detecte(s) mais aucun en status OK",
                details=details,
                suggested_actions=("net_011", "net_012"),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"{ok_count}/{len(gamepads)} gamepad(s) en status OK",
            details=details,
            suggested_actions=(),
        )


class XboxControllerDriverCheck(Check):
    """Verifie le driver Xbox Controller (date raisonnable).

    Un driver Xbox tres ancien (>3 ans) ne supporte pas certaines manettes
    Series X|S et casse l'auto-pairing en BT.
    """

    name = "gaming_xbox_driver_freshness"
    AGE_WARNING_DAYS = 365 * 3

    def run(self) -> CheckResult:
        cmd = (
            "Get-PnpDevice -ErrorAction SilentlyContinue "
            "| Where-Object { $_.FriendlyName -match 'Xbox' } "
            "| ForEach-Object { "
            "  $d = Get-PnpDeviceProperty -InstanceId $_.InstanceId "
            "       -KeyName 'DEVPKEY_Device_DriverDate' -ErrorAction SilentlyContinue; "
            "  if ($d) { "
            "    [PSCustomObject]@{ Name=$_.FriendlyName; DriverDate=$d.Data } "
            "  } "
            "} | ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=10.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Lecture driver Xbox impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok or not result.stdout.strip():
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Aucun driver Xbox detecte ou lecture KO",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        oldest = _oldest_date_in(result.stdout)
        if oldest is None:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Driver Xbox detecte mais date illisible",
                details={"raw_lines": result.stdout.count("\n")},
                suggested_actions=(),
            )

        age = datetime.now() - oldest
        details: dict[str, Any] = {
            "oldest_xbox_driver": oldest.isoformat(),
            "age_days": age.days,
        }

        if age > timedelta(days=self.AGE_WARNING_DAYS):
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    f"Driver Xbox tres ancien ({oldest.date()}, {age.days} jours) — "
                    "Windows Update Optional peut proposer une version recente"
                ),
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"Driver Xbox a jour (date {oldest.date()})",
            details=details,
            suggested_actions=(),
        )


class SteamInputCheck(Check):
    """Detecte la presence de Steam (utilise Steam Input pour piloter la manette).

    Steam Input agit comme pont XInput pour Steam, ce qui peut creer des
    conflits avec d'autres jeux non-Steam. On flag uniquement la presence
    pour info.
    """

    name = "gaming_steam_input_present"

    def run(self) -> CheckResult:
        cmd = (
            "Test-Path 'HKCU:\\Software\\Valve\\Steam'"
        )
        try:
            result = run_ps_check(cmd, timeout=8.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Detection Steam impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        present = result.ok and result.stdout.strip().lower() == "true"
        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=(
                "Steam detecte (Steam Input peut intercepter la manette)"
                if present
                else "Steam non detecte sur ce profil utilisateur"
            ),
            details={"steam_installed": present},
            suggested_actions=(),
        )


class DualInputConflictCheck(Check):
    """Detecte si la meme manette est exposee en XInput ET DirectInput.

    Symptome typique : la manette double-tap chaque action. Diagnostic :
    >1 device avec FriendlyName proche dans la classe HIDClass.
    """

    name = "gaming_dual_input_conflict"

    def run(self) -> CheckResult:
        cmd = (
            "Get-PnpDevice -Class HIDClass -ErrorAction SilentlyContinue "
            "| Where-Object { $_.FriendlyName -match 'Controller|Gamepad|Xbox|Wireless' } "
            "| Select-Object FriendlyName "
            "| ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=10.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Detection conflits dual-input impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Detection conflits dual-input echouee",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        names = [line.strip().strip('"') for line in result.stdout.splitlines()[1:] if line.strip()]
        details: dict[str, Any] = {"hid_controllers_count": len(names)}

        # Conflit si on trouve >1 device avec un nom contenant "Controller"
        # (cas typique : "Xbox Wireless Controller" + "Controller (Xbox One)")
        if len(names) > 1:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    f"{len(names)} entrees HID controllers detectees — risque de conflit "
                    "XInput/DirectInput, ouvre Devices and Printers et debranche les doublons"
                ),
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"Pas de conflit dual-input ({len(names)} entree HID controller)",
            details=details,
            suggested_actions=(),
        )


class XblGameSaveCheck(Check):
    """Verifie le service XblGameSave (utile pour Game Pass / saves cloud)."""

    name = "gaming_xbl_gamesave_status"

    def run(self) -> CheckResult:
        status = service_status("XblGameSave")
        details = {"service": "XblGameSave", "status": status}

        if status == "running":
            return CheckResult(
                name=self.name,
                severity=Severity.OK.value,
                message="Service XblGameSave en cours d'execution",
                details=details,
                suggested_actions=(),
            )
        if status == "not_installed":
            return CheckResult(
                name=self.name,
                severity=Severity.OK.value,
                message="XblGameSave non installe (normal sur edition LTSC / Pro stripped)",
                details=details,
                suggested_actions=(),
            )
        if status in {"stopped", "stop_pending"}:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Service XblGameSave arrete ({status}) — saves cloud Xbox indisponibles",
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.WARNING.value,
            message=f"XblGameSave dans un etat inhabituel : {status}",
            details=details,
            suggested_actions=(),
        )


def _oldest_date_in(text: str) -> datetime | None:
    """Identique a la version bluetooth — duplication assumee pour l'isolation theme."""
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
    """Retourne la liste ordonnee des checks gaming."""
    return [
        GamepadDetectionCheck(),
        XboxControllerDriverCheck(),
        SteamInputCheck(),
        DualInputConflictCheck(),
        XblGameSaveCheck(),
    ]
