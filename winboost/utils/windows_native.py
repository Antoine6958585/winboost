"""Helpers pour les actions Windows-natives (luminosite, dark mode, volume, etc.).

Ce module centralise les wrappers Python autour des APIs Windows non-registry :
- WMI (luminosite, batterie)
- PowerShell (commandes systeme complexes)
- Audio (volume via interfaces COM)

Les YAML d'actions peuvent invoquer directement `method: powershell` pour les
one-liners simples. Ces helpers servent quand la GUI ou le CLI a besoin de
LIRE un etat (ex: afficher la luminosite actuelle dans un slider Settings),
ou pour encapsuler une logique trop complexe pour un one-liner.

Toutes les fonctions sont stateless et tolerantes aux erreurs : si un
helper echoue (driver manquant, ecran externe non WMI-compatible, etc.) il
leve `WindowsNativeError` avec un message explicite.

Pattern d'usage :
    from winboost.utils.windows_native import get_brightness, set_brightness

    try:
        current = get_brightness()
        set_brightness(50)
    except WindowsNativeError as e:
        logger.warning(f"Action native indisponible : {e}")
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Final


class WindowsNativeError(RuntimeError):
    """Levee quand un helper natif echoue (WMI/PS/COM)."""


# Constantes power plans Windows (GUID standards)
POWER_PLAN_HIGH_PERFORMANCE: Final[str] = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
POWER_PLAN_BALANCED: Final[str] = "381b4222-f694-41f0-9685-ff5bb260df2e"
POWER_PLAN_POWER_SAVER: Final[str] = "a1841308-3541-4fab-bc81-f71556f20b4a"


@dataclass(frozen=True)
class PowerShellResult:
    """Resultat d'execution d'un script PowerShell."""

    stdout: str
    stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_powershell(command: str, timeout: float = 10.0) -> PowerShellResult:
    """Execute un script PowerShell one-liner et retourne son resultat.

    Args:
        command: Le script PS a executer (sera passe en `-Command`).
        timeout: Timeout en secondes (defaut 10s).

    Returns:
        PowerShellResult avec stdout/stderr/returncode.

    Raises:
        WindowsNativeError: Si le timeout expire ou si PS est introuvable.
    """
    if sys.platform != "win32":
        raise WindowsNativeError("PowerShell helpers uniquement disponibles sur Windows")

    try:
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise WindowsNativeError(f"Timeout PowerShell apres {timeout}s") from exc
    except FileNotFoundError as exc:
        raise WindowsNativeError("powershell.exe introuvable dans le PATH") from exc

    return PowerShellResult(
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        returncode=proc.returncode,
    )


def get_brightness() -> int:
    """Lit la luminosite actuelle de l'ecran principal (0-100) via WMI.

    Returns:
        Niveau de luminosite entre 0 et 100.

    Raises:
        WindowsNativeError: Si WMI ne supporte pas l'ecran (ex: externe, dock).
    """
    result = run_powershell(
        "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"
    )
    if not result.ok or not result.stdout:
        err = result.stderr or "pas de sortie"
        raise WindowsNativeError(
            f"Impossible de lire la luminosite (WMI non supporte ?) : {err}"
        )
    try:
        return int(result.stdout.splitlines()[0].strip())
    except (ValueError, IndexError) as exc:
        raise WindowsNativeError(f"Sortie WMI invalide : {result.stdout!r}") from exc


def set_brightness(level: int) -> None:
    """Regle la luminosite de l'ecran principal (0-100) via WMI.

    Args:
        level: Niveau de 0 a 100. Tronque dans cet intervalle.

    Raises:
        WindowsNativeError: Si WMI ne supporte pas l'ecran ou si le set echoue.
        ValueError: Si level n'est pas un entier.
    """
    if not isinstance(level, int):
        raise ValueError(f"level doit etre un int, recu {type(level).__name__}")
    level = max(0, min(100, level))
    cmd = (
        "(Get-WmiObject -Namespace root/WMI "
        f"-Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})"
    )
    result = run_powershell(cmd)
    if not result.ok:
        raise WindowsNativeError(
            f"Echec WmiSetBrightness({level}) : {result.stderr or 'erreur inconnue'}"
        )


def is_dark_mode() -> bool:
    """Retourne True si le theme Windows actuel est sombre.

    Lit `HKCU\\...\\Themes\\Personalize\\AppsUseLightTheme` (0 = dark, 1 = light).

    Raises:
        WindowsNativeError: Si la cle registry n'est pas lisible.
    """
    cmd = (
        "(Get-ItemProperty 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion"
        "\\Themes\\Personalize').AppsUseLightTheme"
    )
    result = run_powershell(cmd)
    if not result.ok:
        raise WindowsNativeError(f"Lecture dark mode echouee : {result.stderr}")
    out = result.stdout.strip()
    # 0 = dark, 1 = light (Microsoft inverse la logique du nom de cle)
    return out == "0"


def set_dark_mode(enabled: bool) -> None:
    """Active (True) ou desactive (False) le theme sombre Windows.

    Modifie HKCU directement (pas besoin d'admin). Necessite parfois un
    re-login pour propager dans toutes les apps UWP.

    Raises:
        WindowsNativeError: Si l'ecriture registry echoue.
    """
    value = 0 if enabled else 1
    path = "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
    cmd = (
        f"Set-ItemProperty -Path '{path}' "
        f"-Name 'AppsUseLightTheme' -Value {value} -Type DWord -Force; "
        f"Set-ItemProperty -Path '{path}' "
        f"-Name 'SystemUsesLightTheme' -Value {value} -Type DWord -Force"
    )
    result = run_powershell(cmd)
    if not result.ok:
        raise WindowsNativeError(f"Echec set_dark_mode({enabled}) : {result.stderr}")


def is_focus_assist_enabled() -> bool:
    """Retourne True si les notifications toast sont desactivees (proxy Focus Assist).

    Note : c'est une approximation. Le vrai Focus Assist Windows utilise
    une cle CloudStore plus complexe. Pour le scope v2.1, on se contente du
    toggle ToastEnabled qui couvre le besoin "ne plus etre derange".
    """
    path = "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\PushNotifications"
    cmd = f"(Get-ItemProperty '{path}' -ErrorAction SilentlyContinue).ToastEnabled"
    result = run_powershell(cmd)
    if not result.ok:
        raise WindowsNativeError(f"Lecture focus assist echouee : {result.stderr}")
    return result.stdout.strip() == "0"


def get_active_power_plan() -> str:
    """Retourne le GUID du plan d'alimentation actif.

    Raises:
        WindowsNativeError: Si powercfg echoue.
    """
    result = run_powershell("powercfg /getactivescheme")
    if not result.ok:
        raise WindowsNativeError(f"powercfg echec : {result.stderr}")
    # Format : "Power Scheme GUID: {guid}  ({nom})"
    for token in result.stdout.split():
        if "-" in token and len(token) == 36:
            return token
    raise WindowsNativeError(f"GUID introuvable dans : {result.stdout!r}")


def set_power_plan(guid: str) -> None:
    """Bascule sur un plan d'alimentation par GUID.

    Args:
        guid: GUID du plan (cf. constantes POWER_PLAN_*).

    Raises:
        WindowsNativeError: Si powercfg echoue (souvent parce que pas admin).
    """
    result = run_powershell(f"powercfg /setactive {guid}")
    if not result.ok:
        raise WindowsNativeError(
            f"Echec set_power_plan({guid}) — admin requis ? : {result.stderr}"
        )
