"""Theme bluetooth — diagnostics specifiques au Bluetooth Windows.

Use case principal : la manette BT d'Antoine qui bug dans Rocket League.
On verifie dans l'ordre :

1. Service `bthserv` running ?
2. Bluetooth radio enabled (Get-PnpDevice -Class Bluetooth) ?
3. Drivers Bluetooth recents (date du driver) ?
4. Devices appaires : combien sont Connected vs Disconnected ?
5. Conflit potentiel XInput/DirectInput sur les controllers detectes
6. Mapping driver des gamepads Bluetooth (Xbox/DualSense vu comme generique ?)
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
            result = run_ps_check(cmd, timeout=10.0)
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
            result = run_ps_check(cmd, timeout=10.0)
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
            result = run_ps_check(cmd, timeout=10.0)
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


class BluetoothGamepadMappingCheck(Check):
    """Detecte si une manette Bluetooth appairee est mal-mappee par Windows.

    Use case Antoine (cas confirme) : la manette est bien appairee et
    "Connected" cote BT, mais Windows l'enumere comme "Generic Bluetooth
    Peripheral" (classe `Bluetooth`/`BTHENUM`) au lieu de "Xbox Wireless
    Controller" (classe `XnaComposite` / `HIDClass` avec FriendlyName
    explicite). Resultat : pas de driver XINPUT, donc invisible dans
    Rocket League / Steam Input alors que la manette marche en USB.

    Strategie :
    1. Lister tous les devices BT (`Get-PnpDevice -Class Bluetooth -PresentOnly`)
       *plus* les devices HID/XnaComposite appaires en BT (instance ID
       commencant par BTHENUM).
    2. Filtrer ceux dont le FriendlyName ressemble a une manette.
    3. Pour chaque manette : la classer "well_mapped" ou "mismapped" selon
       sa classe et son FriendlyName.
    4. Si au moins 1 mismapped -> warning + suggested_action symbolique
       `bt_unpair_repair` (geree par MANUAL_FIX_DESCRIPTIONS dans le runner).
    """

    name = "bluetooth_gamepad_mapping"

    # FriendlyNames qui trahissent une manette (FR + EN, marques courantes).
    GAMEPAD_NAME_HINTS: tuple[str, ...] = (
        "Xbox",
        "Controller",
        "Gamepad",
        "DualSense",
        "DualShock",
        "Pro Controller",
        "Stadia",
    )

    # FriendlyNames generiques = signal fort de mismapping
    GENERIC_NAME_HINTS: tuple[str, ...] = (
        "Bluetooth Peripheral Device",
        "Generic Bluetooth",
        "Peripherique Bluetooth",  # locale FR
    )

    # Classes "bien mappees" pour une manette
    WELL_MAPPED_CLASSES: tuple[str, ...] = (
        "XnaComposite",  # driver Xbox officiel
        "XINPUT",
        "HIDClass",  # acceptable si FriendlyName explicite
    )

    # Classes typiques d'un mismapping (BT brut, pas de driver dedie)
    MISMAPPED_CLASSES: tuple[str, ...] = (
        "Bluetooth",
        "BTHENUM",
    )

    def run(self) -> CheckResult:
        # On scanne deux passes : (a) classe Bluetooth (cas mismap typique),
        # (b) HIDClass/XnaComposite mais via BTHENUM (cas bien mappe en BT).
        cmd = (
            "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue "
            "| Where-Object { "
            "  $_.Class -in @('Bluetooth','BTHENUM','XnaComposite','HIDClass') "
            "  -or $_.InstanceId -like 'BTHENUM*' "
            "} "
            "| Select-Object FriendlyName, Status, Class, InstanceId "
            "| ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=10.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Lecture mapping gamepads BT impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Lecture mapping gamepads BT echouee",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        gamepads = self._parse_gamepads(result.stdout)

        if not gamepads:
            return CheckResult(
                name=self.name,
                severity=Severity.OK.value,
                message="Aucune manette Bluetooth appairee detectee",
                details={"gamepads": []},
                suggested_actions=(),
            )

        mismapped = [g for g in gamepads if g["status"] == "mismapped"]
        well_mapped = [g for g in gamepads if g["status"] == "well_mapped"]
        details: dict[str, Any] = {
            "gamepads": gamepads,
            "mismapped_count": len(mismapped),
            "well_mapped_count": len(well_mapped),
        }

        if mismapped:
            faulty_names = ", ".join(g["name"] for g in mismapped) or "manette inconnue"
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=(
                    f"Manette BT mal mappee detectee ({faulty_names}) — "
                    "Windows la voit en peripherique generique au lieu de driver XINPUT/Xbox. "
                    "Cause typique : driver pas installe apres pairing."
                ),
                details=details,
                # Action symbolique (pas dans le YAML actions/) -> recuperee par
                # MANUAL_FIX_DESCRIPTIONS dans le runner pour produire un step manuel.
                suggested_actions=("bt_unpair_repair",),
            )

        labels = ", ".join(f"{g['name']} ({g['class']})" for g in well_mapped)
        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"{len(well_mapped)} manette(s) BT correctement mappee(s) : {labels}",
            details=details,
            suggested_actions=(),
        )

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_gamepads(self, csv_output: str) -> list[dict[str, str]]:
        """Parse la sortie ConvertTo-Csv et retourne les gamepads detectes.

        Robuste face a un output vide / sans header / lignes corrompues.
        """
        from winboost.diagnose.checks import _parse_csv_line  # reuse interne

        if not csv_output:
            return []

        lines = [ln for ln in csv_output.splitlines() if ln.strip()]
        if len(lines) < 2:
            return []

        gamepads: list[dict[str, str]] = []
        for line in lines[1:]:  # skip header
            parts = _parse_csv_line(line)
            if len(parts) < 3:
                continue
            name = parts[0].strip()
            klass = parts[2].strip() if len(parts) > 2 else ""
            instance_id = parts[3].strip() if len(parts) > 3 else ""

            if not self._is_gamepad_candidate(name):
                continue

            status = self._classify_mapping(name, klass, instance_id)
            gamepads.append(
                {
                    "name": name or "(unnamed)",
                    "class": klass or "Unknown",
                    "status": status,
                }
            )
        return gamepads

    def _is_gamepad_candidate(self, friendly_name: str) -> bool:
        """True si le FriendlyName ressemble a une manette OU s'il est generique
        ET qu'on est dans une classe BT brute (cas mismap typique).

        Note : on inclut les FriendlyNames generiques uniquement s'ils
        contiennent un hint de gamepad. Sinon on ne flag pas un casque BT
        nomme "Bluetooth Peripheral Device" comme une manette.
        """
        if not friendly_name:
            return False
        lower = friendly_name.lower()
        return any(hint.lower() in lower for hint in self.GAMEPAD_NAME_HINTS)

    def _classify_mapping(
        self, friendly_name: str, klass: str, instance_id: str
    ) -> str:
        """Retourne 'well_mapped' ou 'mismapped' selon classe + nom + bus.

        Logique :
        - Classe XnaComposite / XINPUT -> well_mapped (driver dedie installe)
        - Classe HIDClass + FriendlyName explicite ("Xbox Wireless Controller",
          "DualSense Wireless Controller") -> well_mapped
        - Classe Bluetooth ou BTHENUM SEUL -> mismapped (pas de driver gamepad)
        - FriendlyName generique ("Bluetooth Peripheral Device") -> mismapped
          meme en HIDClass (cas borderline, securise par defaut)
        """
        klass_norm = klass.strip()
        name_lower = friendly_name.lower()

        # FriendlyName clairement generique -> mismap quoi qu'il arrive
        for generic in self.GENERIC_NAME_HINTS:
            if generic.lower() in name_lower:
                return "mismapped"

        # Driver Xbox dedie -> well mapped
        if klass_norm in {"XnaComposite", "XINPUT"}:
            return "well_mapped"

        # HIDClass + FriendlyName specifique gamepad -> well mapped
        if klass_norm == "HIDClass":
            specific_hints = ("Xbox Wireless", "DualSense", "DualShock", "Pro Controller")
            for hint in specific_hints:
                if hint.lower() in name_lower:
                    return "well_mapped"
            # HIDClass sans nom specifique : on reste neutre = well_mapped
            # (un device HID nomme "Wireless Controller" tout court est ambigu
            # mais souvent fonctionnel ; on ne flag pas)
            return "well_mapped"

        # Classe Bluetooth/BTHENUM seule -> mismapped (pas de driver gamepad)
        if klass_norm in self.MISMAPPED_CLASSES:
            return "mismapped"

        # Inconnu : on traite comme mismapped pour ne pas masquer un cas reel
        # uniquement si l'instance_id commence par BTHENUM (manette appairee
        # en BT mais classe non standard).
        if instance_id.upper().startswith("BTHENUM"):
            return "mismapped"

        return "well_mapped"


def get_checks() -> list[Check]:
    """Retourne la liste ordonnee des checks bluetooth."""
    return [
        BluetoothServiceCheck(),
        BluetoothRadioCheck(),
        BluetoothDriverFreshnessCheck(),
        BluetoothPairedDevicesCheck(),
        BluetoothXInputConflictCheck(),
        BluetoothGamepadMappingCheck(),
    ]
