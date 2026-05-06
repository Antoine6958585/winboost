"""Definitions de base pour les checks diagnostics.

Ce module contient :
- `Severity` : enum des niveaux de gravite d'un resultat de check
- `CheckResult` : dataclass immuable retournee par chaque check
- `Check` : classe de base abstraite pour ecrire un check
- Helpers communs (`run_ps_check`, `service_status`, `pnp_query`)

Chaque theme (`themes/{nom}.py`) reutilise ces primitives pour eviter la
duplication. Toute la logique reseau/PowerShell passe par les helpers, ce qui
permet de moquer une seule fonction (`run_powershell`) dans les tests.

Pattern d'usage :
    from winboost.diagnose.checks import Check, CheckResult, Severity

    class BluetoothServiceCheck(Check):
        name = "bluetooth_service_status"

        def run(self) -> CheckResult:
            status = service_status("bthserv")
            if status == "running":
                return CheckResult(
                    name=self.name,
                    severity=Severity.OK,
                    message="Service bthserv en cours d'execution",
                    details={"status": status},
                    suggested_actions=[],
                )
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR,
                message=f"Service bthserv inactif ({status})",
                details={"status": status},
                suggested_actions=["net_012"],
            )
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from winboost.utils.windows_native import (
    PowerShellResult,
    WindowsNativeError,
    run_powershell,
)


class Severity(StrEnum):
    """Niveau de gravite d'un resultat de check.

    StrEnum (Python 3.11+) garantit la serialisabilite JSON :
    `json.dumps(Severity.OK)` produit `"ok"`.
    """

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


_ALLOWED_SEVERITIES = {s.value for s in Severity}


@dataclass(frozen=True)
class CheckResult:
    """Resultat immuable d'un check unitaire.

    Attributes:
        name: Identifiant stable du check (ex: "bluetooth_service_status").
        severity: Niveau de gravite (ok | warning | error | critical).
        message: Message court lisible humain (FR).
        details: Donnees brutes pour debug ou pour la GUI.
        suggested_actions: Liste d'IDs d'actions YAML qui peuvent corriger
            ce probleme (ex: ["net_011", "net_012"]). Peut etre vide.
    """

    name: str
    severity: str  # str pour conserver la simplicite JSON, validee dans __post_init__
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    suggested_actions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError(f"CheckResult.name doit etre une string non vide, recu {self.name!r}")
        if self.severity not in _ALLOWED_SEVERITIES:
            raise ValueError(
                f"Severity invalide : {self.severity!r}. "
                f"Valeurs autorisees : {sorted(_ALLOWED_SEVERITIES)}"
            )
        if not isinstance(self.message, str):
            raise ValueError(f"message doit etre str, recu {type(self.message).__name__}")
        # Forcer un tuple pour l'immutabilite (frozen=True ne valide pas le contenu)
        if isinstance(self.suggested_actions, list):
            object.__setattr__(self, "suggested_actions", tuple(self.suggested_actions))

    @property
    def is_problem(self) -> bool:
        """True si le check signale un probleme (warning, error, critical)."""
        problems = {Severity.WARNING.value, Severity.ERROR.value, Severity.CRITICAL.value}
        return self.severity in problems

    def to_dict(self) -> dict[str, Any]:
        """Serialisation JSON-friendly (les tuples deviennent des listes)."""
        d = asdict(self)
        d["suggested_actions"] = list(self.suggested_actions)
        return d


class Check(ABC):
    """Classe de base pour un check unitaire d'un theme.

    Sous-classer `Check` puis implementer `run()`. Le runner instancie chaque
    Check et appelle `safe_run()` qui encapsule les exceptions pour qu'un
    crash dans un check n'interrompe pas le diagnostic complet.
    """

    name: str = "unnamed_check"

    @abstractmethod
    def run(self) -> CheckResult:
        """Execute le check et retourne un CheckResult."""

    def safe_run(self) -> CheckResult:
        """Execute le check en isolant les exceptions inattendues.

        Garantit que le runner ne crashe jamais a cause d'un check defaillant.
        Hierarchie de severite des exceptions :
        - `WindowsNativeError` : helper PS/WMI dispo mais a echoue -> warning
        - `AttributeError` / `OSError` / `UnicodeDecodeError` : subprocess
          ou parsing instable (souvent encoding cp1252 sur Windows FR) -> warning
        - tout le reste : bug inattendu dans le code du check -> error
        """
        try:
            return self.run()
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Check non executable : {exc}",
                details={"error": str(exc), "error_type": "WindowsNativeError"},
                suggested_actions=(),
            )
        except (AttributeError, OSError, UnicodeDecodeError) as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Subprocess/encoding instable : {exc}",
                details={"error": str(exc), "error_type": type(exc).__name__},
                suggested_actions=(),
            )
        except Exception as exc:  # pragma: no cover (filet de securite)
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message=f"Erreur inattendue : {exc}",
                details={"error": str(exc), "error_type": type(exc).__name__},
                suggested_actions=(),
            )


# ---------------------------------------------------------------------------
# Helpers communs reutilises par les themes
# ---------------------------------------------------------------------------


def run_ps_check(command: str, timeout: float = 10.0) -> PowerShellResult:
    """Wrapper autour de `run_powershell` avec timeout pour les checks.

    Les commandes Get-PnpDevice / Get-NetAdapter peuvent prendre 5-8s sur
    certains Windows (drivers nombreux, services lents). Default 10s donne
    de la marge tout en gardant le rapport sous 15s en parallèle (8 workers).
    """
    return run_powershell(command, timeout=timeout)


def service_status(service_name: str) -> str:
    """Retourne le status d'un service Windows via `sc.exe query`.

    Args:
        service_name: Nom court du service (ex: "bthserv", "Audiosrv").

    Returns:
        L'un de : "running", "stopped", "paused", "start_pending",
        "stop_pending", "unknown" (si service introuvable ou parsing KO).
    """
    try:
        result = run_ps_check(f"sc.exe query {service_name}")
    except WindowsNativeError:
        return "unknown"

    if not result.ok:
        # Service introuvable ou access denied
        if "1060" in result.stdout or "1060" in result.stderr:
            return "not_installed"
        return "unknown"

    text = result.stdout.upper()
    if "RUNNING" in text:
        return "running"
    if "STOPPED" in text:
        return "stopped"
    if "PAUSED" in text:
        return "paused"
    if "START_PENDING" in text:
        return "start_pending"
    if "STOP_PENDING" in text:
        return "stop_pending"
    return "unknown"


def pnp_query(
    class_filter: str | None = None,
    friendly_name_pattern: str | None = None,
) -> list[dict[str, str]]:
    """Liste les devices PnP filtres par classe ou pattern de nom.

    Args:
        class_filter: Classe device a filtrer (ex: "Bluetooth", "Display",
            "Net", "AudioEndpoint", "HIDClass"). Si None, pas de filtre.
        friendly_name_pattern: Pattern (regex PowerShell) sur FriendlyName.
            Si None, pas de filtre.

    Returns:
        Liste de dicts avec cles : "name", "status", "instance_id", "class".
        Liste vide si la query echoue ou ne renvoie rien.
    """
    filters: list[str] = []
    if class_filter:
        filters.append(f"-Class '{class_filter}'")
    cmd = f"Get-PnpDevice {' '.join(filters)} -ErrorAction SilentlyContinue"
    if friendly_name_pattern:
        cmd += f" | Where-Object {{ $_.FriendlyName -match '{friendly_name_pattern}' }}"
    cmd += (
        " | Select-Object FriendlyName, Status, InstanceId, Class "
        "| ConvertTo-Csv -NoTypeInformation"
    )

    try:
        result = run_ps_check(cmd)
    except WindowsNativeError:
        return []

    if not result.ok or not result.stdout:
        return []

    devices: list[dict[str, str]] = []
    lines = result.stdout.splitlines()
    if len(lines) < 2:
        return []

    # CSV header sans guillemets propres : on parse simplement
    for line in lines[1:]:
        # PowerShell CSV : chaque champ est entre guillemets, separateur virgule
        parts = _parse_csv_line(line)
        if len(parts) < 4:
            continue
        devices.append(
            {
                "name": parts[0],
                "status": parts[1],
                "instance_id": parts[2],
                "class": parts[3],
            }
        )
    return devices


def _parse_csv_line(line: str) -> list[str]:
    """Parse une ligne CSV simple (champs entre guillemets, separateur virgule).

    Suffit pour la sortie ConvertTo-Csv de PowerShell qui n'echappe pas les
    guillemets internes a coup sur (on tolere les valeurs simples).
    """
    fields: list[str] = []
    buf = ""
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
            continue
        if ch == "," and not in_quotes:
            fields.append(buf)
            buf = ""
            continue
        buf += ch
    fields.append(buf)
    return fields
