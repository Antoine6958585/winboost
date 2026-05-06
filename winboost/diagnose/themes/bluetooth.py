"""Theme bluetooth — diagnostics specifiques au Bluetooth Windows.

Use case principal : la manette BT d'Antoine qui bug dans Rocket League.
On verifie dans l'ordre :

1. Service `bthserv` running ?
2. Bluetooth radio enabled (Get-PnpDevice -Class Bluetooth) ?
3. Drivers Bluetooth recents (date du driver) ?
4. Devices appaires : combien sont Connected vs Disconnected ?
5. Conflit potentiel XInput/DirectInput sur les controllers detectes
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from winboost.diagnose.checks import (
    Check,
    CheckResult,
    Severity,
    pnp_query,
    run_ps_check,
    service_status,
)
from winboost.utils.windows_native import WindowsNativeError


class BluetoothServiceCheck(Check):
    """Verifie que le service `bthserv` (Bluetooth Support Service) tourne."""

    name = "bluetooth_service_status"

    def run(self) -> CheckResult:
        status = service_status("bthserv")
        details = {"service": "bthserv", "status": status}

        if status == "running":
            return CheckResult(
                name=self.name,
                severity=Severity.OK.value,
                message="Service bthserv en cours d'execution",
                details=details,
                suggested_actions=(),
            )
        if status == "not_installed":
            return CheckResult(
                name=self.name,
                severity=Severity.CRITICAL.value,
                message="Service bthserv introuvable — pile Bluetooth absente ou corrompue",
                details=details,
                suggested_actions=(),
            )
        if status in {"stopped", "stop_pending"}:
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message=f"Service bthserv arrete ({status})",
                details=details,
                suggested_actions=("net_012",),
            )
        # paused, unknown, start_pending
        return CheckResult(
            name=self.name,
            severity=Severity.WARNING.value,
            message=f"Service bthserv dans un etat inhabituel : {status}",
            details=details,
            suggested_actions=("net_011", "net_012"),
        )


class BluetoothRadioCheck(Check):
    """Verifie qu'au moins un radio Bluetooth est detecte ET active."""

    name = "bluetooth_radio_enabled"

    def run(self) -> CheckResult:
        devices = pnp_query(class_filter="Bluetooth")
        if not devices:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Aucun device Bluetooth detecte par PnP",
                details={"devices_count": 0},
                suggested_actions=(),
            )

        # On filtre uniquement les radios (pas les peripheriques connectes)
        radios = [d for d in devices if "radio" in d["name"].lower() or d["class"] == "Bluetooth"]
        ok_radios = [d for d in radios if d["status"].upper() == "OK"]
        details: dict[str, Any] = {
            "devices_count": len(devices),
            "radios_count": len(radios),
            "radios_ok": len(ok_radios),
        }

        if not radios:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Aucun radio Bluetooth identifie (peut-etre cle USB BT debranchee)",
                details=details,
                suggested_actions=(),
            )

        if not ok_radios:
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message=(
                    f"Radio(s) Bluetooth detecte(s) mais aucun n'est OK "
                    f"({len(radios)} en erreur)"
                ),
                details=details,
                suggested_actions=("net_011", "net_012"),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"{len(ok_radios)}/{len(radios)} radio(s) Bluetooth OK",
            details=details,
            suggested_actions=(),
        )


class BluetoothDriverFreshnessCheck(Check):
    """Verifie que les drivers Bluetooth sont recents (< 2 ans).

    Un driver vieux est une cause classique de bugs sur les manettes recentes.
    """

    name = "bluetooth_driver_freshness"

    # Seuil au-dela duquel on flag le driver comme potentiellement obsolete
    AGE_WARNING_DAYS = 365 * 2  # 2 ans

    def run(self) -> CheckResult:
        cmd = (
            "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
            "ForEach-Object { "
            "  $d = Get-PnpDeviceProperty -InstanceId $_.InstanceId "
            "       -KeyName 'DEVPKEY_Device_DriverDate' -ErrorAction SilentlyContinue; "
            "  if ($d) { "
            "    [PSCustomObject]@{ "
            "      Name = $_.FriendlyName; "
            "      DriverDate = $d.Data "
            "    } "
            "  } "
            "} | ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=3.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Impossible de lire les dates de drivers BT : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Lecture des drivers BT echouee (PowerShell KO)",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        # Parse minimal : on cherche des dates dans la sortie. Format Windows
        # courant : MM/DD/YYYY ou DD/MM/YYYY selon locale -> on tente plusieurs.
        oldest_date = self._oldest_date_in(result.stdout)
        details: dict[str, Any] = {"raw_lines": result.stdout.count("\n")}
        if oldest_date is None:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Drivers BT detectes mais dates illisibles",
                details=details,
                suggested_actions=(),
            )

        details["oldest_driver_date"] = oldest_date.isoformat()
        age = datetime.now() - oldest_date
        details["age_days"] = age.days

        if age > timedelta(days=self.AGE_WARNING_DAYS):
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    f"Driver BT le plus ancien date du {oldest_date.date()} "
                    f"({age.days} jours) — envisager une mise a jour"
                ),
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"Drivers BT recents (plus ancien : {oldest_date.date()})",
            details=details,
            suggested_actions=(),
        )

    @staticmethod
    def _oldest_date_in(text: str) -> datetime | None:
        """Cherche la date la plus ancienne dans une sortie CSV PowerShell.

        Tolere plusieurs formats : ISO, US, EU. Premier match valide gagne.
        """
        candidates = []
        for token in text.replace('"', " ").replace(",", " ").split():
            for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    candidates.append(datetime.strptime(token, fmt))
                    break
                except ValueError:
                    continue
        return min(candidates) if candidates else None


class BluetoothPairedDevicesCheck(Check):
    """Compte les devices BT appaires et signale ceux Disconnected.

    Use case Antoine : sa manette est appairee mais Disconnected -> probleme
    de re-connexion ou batterie HS.
    """

    name = "bluetooth_paired_devices"

    def run(self) -> CheckResult:
        # On utilise -PresentOnly:$false pour inclure les devices appaires
        # mais non connectes
        cmd = (
            "Get-PnpDevice -Class Bluetooth -PresentOnly:$false "
            "-ErrorAction SilentlyContinue "
            "| Where-Object { $_.FriendlyName -notmatch 'Radio|Generic|Microsoft' } "
            "| Select-Object FriendlyName, Status, InstanceId, Class "
            "| ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=3.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Lecture devices appaires impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Lecture devices appaires echouee",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if len(lines) <= 1:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Aucun device BT appaire detecte (manette jamais appairee ?)",
                details={"paired_count": 0},
                suggested_actions=("net_011", "net_012"),
            )

        paired = lines[1:]  # skip header
        connected = [line for line in paired if '"OK"' in line or ",OK," in line]
        disconnected = [line for line in paired if line not in connected]

        details: dict[str, Any] = {
            "paired_count": len(paired),
            "connected_count": len(connected),
            "disconnected_count": len(disconnected),
        }

        if disconnected and not connected:
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message=(
                    f"{len(disconnected)} device(s) BT appaire(s) mais aucun connecte "
                    "— probleme de reconnexion"
                ),
                details=details,
                suggested_actions=("net_011", "net_012"),
            )
        if disconnected:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    f"{len(connected)} BT connecte(s), {len(disconnected)} "
                    "appaire(s) mais hors ligne"
                ),
                details=details,
                suggested_actions=("net_011", "net_012"),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"{len(connected)} device(s) BT connecte(s)",
            details=details,
            suggested_actions=(),
        )


class BluetoothXInputConflictCheck(Check):
    """Detecte un conflit potentiel XInput/DirectInput sur les controllers.

    Une manette BT peut etre vue par Windows comme un device HID (DirectInput)
    ET reproposee par un driver virtuel comme device XInput. Beaucoup de
    jeux (Rocket League inclus) preferent XInput ; si le driver virtuel
    n'est pas en place, la manette n'est pas detectee dans le jeu.
    """

    name = "bluetooth_xinput_compat"

    def run(self) -> CheckResult:
        # On cherche les controllers HID
        cmd = (
            "Get-PnpDevice -Class HIDClass -ErrorAction SilentlyContinue "
            "| Where-Object { $_.FriendlyName -match 'Controller|Gamepad|Wireless' } "
            "| Select-Object FriendlyName, Status, InstanceId, Class "
            "| ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=3.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Detection HID controllers impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Detection HID controllers echouee",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        lines = [line for line in result.stdout.splitlines() if line.strip()]
        controllers = lines[1:] if len(lines) > 1 else []
        details: dict[str, Any] = {"hid_controllers_count": len(controllers)}

        if not controllers:
            return CheckResult(
                name=self.name,
                severity=Severity.OK.value,
                message="Aucune manette HID detectee — pas de conflit XInput a craindre",
                details=details,
                suggested_actions=(),
            )

        xinput_compat = [c for c in controllers if "xbox" in c.lower() or "xinput" in c.lower()]
        details["xinput_compat_count"] = len(xinput_compat)

        if not xinput_compat and controllers:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    f"{len(controllers)} manette(s) detectee(s) en DirectInput mais "
                    "aucune compatible XInput — incompatible avec Rocket League / Steam Input"
                ),
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=(
                f"{len(xinput_compat)}/{len(controllers)} manette(s) HID compatibles XInput"
            ),
            details=details,
            suggested_actions=(),
        )


def get_checks() -> list[Check]:
    """Retourne la liste ordonnee des checks bluetooth."""
    return [
        BluetoothServiceCheck(),
        BluetoothRadioCheck(),
        BluetoothDriverFreshnessCheck(),
        BluetoothPairedDevicesCheck(),
        BluetoothXInputConflictCheck(),
    ]
