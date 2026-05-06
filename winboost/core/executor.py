"""ActionExecutor — execute reellement les actions YAML WinBoost (T076-A v2.2.x).

Avant ce module, `gui/chat._execute_worker` et `mcp/server.apply` se
contentaient de cataloguer l'intention dans l'historique. Ce module branche
l'execution reelle des 10 methodes du schema (registry_set, registry_delete,
service_*, powershell, cmd, delete_path, clear_directory, scheduled_task_disable).

Principes de conception :

1. **Sécurité first**. Toute mutation destructrice (delete_path, clear_directory,
   registry_delete) est gardee par une whitelist explicite. Les zones
   sensibles (HKLM\\SYSTEM\\Setup, BCD00000000, C:\\Windows\\System32, etc.)
   sont refusees AVANT execution. Les commandes PS/CMD sont scannees pour
   les patterns destructeurs (`format`, `Remove-Item C:\\`, `del /q /s C:\\`).

2. **Backup automatique** avant high/critical. Si l'action est reversible
   (registry_set, registry_delete), on cree un dump `reg export` avant
   modification — le `rollback_id` retourne permet `undo()` MCP.

3. **Admin check propre**. `requires_admin: true` + non-admin = refus
   structure (`error_code: admin_required`), pas de crash.

4. **Idempotence**. registry_set verifie la valeur courante avant ecriture ;
   si deja a la cible, retourne success=True avec message "deja applique".

5. **Timeouts**. Toute exec PS/CMD/SC.exe a un timeout (defaut 30s). Au-dela
   le process est tue et l'erreur est `error_code: timeout`.

6. **Dry-run**. Si `dry_run=True`, aucune mutation n'est appliquee — on
   simule et retourne ce qui SERAIT fait, pour debug ou prevue UI.

7. **UTF-8 partout**. Tous les subprocess sont configures en UTF-8 (cohérent
   avec le verdict T072 du module MCP).

8. **HistoryManager**. Chaque apply (success ou fail) est loggue avec status,
   message, timestamp, rollback_id, error_code.

Architecture :
    ApplyResult                  ← dataclass de retour normalise
    ActionExecutor.apply()       ← entry point public
    _execute_*()                 ← une methode par `execute.method` du schema
    _is_safe_path() / _is_safe_command() / _is_safe_registry_path()
                                 ← gardes de securite, fail-closed
    _backup_before()             ← cree un dump reg si registry_*

Module testable a 100% : winreg / subprocess sont mockes par les tests.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from winboost.utils.admin import is_admin

if TYPE_CHECKING:
    from winboost.actions.loader import Action
    from winboost.core.backup import BackupManager
    from winboost.core.history import HistoryManager


# ---------------------------------------------------------------------------
# Constantes de securite
# ---------------------------------------------------------------------------

# Prefixes (canonicalises uppercase) autorises pour delete_path / clear_directory.
# Tout chemin doit etre `startswith()` un de ces prefixes APRES expansion %ENV%
# et resolution absolue. Tout le reste = refuse.
_FILESYSTEM_WHITELIST_PREFIXES: tuple[str, ...] = (
    # User caches/temp
    "%TEMP%",
    "%TMP%",
    "%LOCALAPPDATA%\\TEMP",
    "%LOCALAPPDATA%\\MICROSOFT\\WINDOWS\\INETCACHE",
    "%LOCALAPPDATA%\\MICROSOFT\\WINDOWS\\WER",
    "%LOCALAPPDATA%\\MICROSOFT\\WINDOWS\\EXPLORER",
    "%LOCALAPPDATA%\\MICROSOFT\\EDGE",
    "%LOCALAPPDATA%\\GOOGLE\\CHROME",
    "%LOCALAPPDATA%\\NPM-CACHE",
    "%LOCALAPPDATA%\\YARN\\CACHE",
    "%LOCALAPPDATA%\\PIP\\CACHE",
    "%APPDATA%\\NPM-CACHE",
    "%USERPROFILE%\\.BUN",
    "%USERPROFILE%\\.GRADLE",
    "%USERPROFILE%\\.M2",
    "%USERPROFILE%\\.NPM",
    "%USERPROFILE%\\.YARN",
    "%USERPROFILE%\\.CACHE",
    "%USERPROFILE%\\.CARGO",
    "%USERPROFILE%\\.DOTNET",
    "%USERPROFILE%\\.NUGET",
    "%USERPROFILE%\\APPDATA\\LOCAL\\TEMP",
    # System caches/logs OK to clear (catalogue cleanup actions referenced)
    "C:\\WINDOWS\\TEMP",
    "C:\\WINDOWS\\SOFTWAREDISTRIBUTION\\DOWNLOAD",
    "C:\\WINDOWS\\LOGS\\CBS",
    "C:\\WINDOWS\\LOGS\\DISM",
    "C:\\WINDOWS\\LOGS\\WINDOWSUPDATE",
    "C:\\WINDOWS\\MINIDUMP",
    "C:\\WINDOWS\\MEMORY.DMP",
    "C:\\PROGRAMDATA\\MICROSOFT\\WINDOWS\\WER",
)

# Chemins systeme NEVER touchable, meme si un YAML forge un path bizarre.
# Verification supplementaire au-dela de la whitelist (defense in depth).
_FILESYSTEM_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "C:\\WINDOWS\\SYSTEM32",
    "C:\\WINDOWS\\SYSWOW64",
    "C:\\WINDOWS\\WINSXS",
    "C:\\WINDOWS\\BOOT",
    "C:\\WINDOWS\\FONTS",
    "C:\\WINDOWS\\CSC",
    "C:\\PROGRAM FILES",
    "C:\\PROGRAM FILES (X86)",
    "C:\\BOOT",
    "C:\\RECOVERY",
    "C:\\$RECYCLE.BIN",
    "C:\\SYSTEM VOLUME INFORMATION",
)

# Cles registry PROHIBEES en ecriture / suppression.
# Tout path qui commence (case-insensitive) par un de ces prefixes = refus.
_REGISTRY_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "HKLM\\SYSTEM\\SETUP",
    "HKLM\\SYSTEM\\CONTROLSET",  # ControlSet001/002 etc.
    "HKLM\\SYSTEM\\CURRENTCONTROLSET\\CONTROL\\LSA",
    "HKLM\\SYSTEM\\CURRENTCONTROLSET\\CONTROL\\SECUREBOOT",
    "HKLM\\BCD00000000",
    "HKLM\\SAM",
    "HKLM\\SECURITY",
    "HKEY_LOCAL_MACHINE\\SYSTEM\\SETUP",
    "HKEY_LOCAL_MACHINE\\SYSTEM\\CONTROLSET",
    "HKEY_LOCAL_MACHINE\\BCD00000000",
    "HKEY_LOCAL_MACHINE\\SAM",
    "HKEY_LOCAL_MACHINE\\SECURITY",
)

# Patterns interdits dans les commandes powershell/cmd (regex case-insensitive).
# Si UN seul match -> refus. Defensif : on prefere un faux positif qu'un wipe.
# Note : on utilise [A-Z]: au lieu de C: pour bloquer toute lettre de drive,
# et on n'utilise pas \b apres `:` (Python regex `\b` echoue entre `:` et `\`).
_COMMAND_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),                  # format C:
    re.compile(r"Remove-Item.*[A-Z]:\\", re.IGNORECASE),               # Remove-Item ... C:\
    re.compile(r"\bdel\s+/[qsf].*[A-Z]:\\", re.IGNORECASE),
    re.compile(r"\brmdir\s+/[qsf].*[A-Z]:\\", re.IGNORECASE),
    re.compile(r"\brd\s+/[qsf].*[A-Z]:\\", re.IGNORECASE),
    re.compile(r"\bdiskpart\b.*\bclean\b", re.IGNORECASE),
    re.compile(r"\bcipher\s+/w", re.IGNORECASE),
    re.compile(r"\bbcdedit\b.*\b/delete\b", re.IGNORECASE),
    re.compile(r"\bvssadmin\b.*\bdelete\s+shadows", re.IGNORECASE),
    re.compile(r"\bsdelete\b.*[A-Z]:\\", re.IGNORECASE),
    re.compile(r"\bshutdown\s+/[fhrs]", re.IGNORECASE),                # forced reboot/shutdown
    re.compile(r"\bsfc\s+/scannow.*&.*\bformat\b", re.IGNORECASE),
)

DEFAULT_TIMEOUT_SECONDS: float = 30.0


# ---------------------------------------------------------------------------
# Mapping registry hive -> winreg constant (lazy : winreg n'existe que sur Win)
# ---------------------------------------------------------------------------


def _winreg_module():  # type: ignore[no-untyped-def]
    """Import paresseux de winreg. Leve ImportError sur non-Windows."""
    if sys.platform != "win32":
        raise ImportError("winreg uniquement disponible sur Windows")
    import winreg  # type: ignore[import-not-found]
    return winreg


def _hive_constant(hive_name: str):  # type: ignore[no-untyped-def]
    """Convertit `HKCU` / `HKEY_CURRENT_USER` -> winreg.HKEY_CURRENT_USER."""
    winreg = _winreg_module()
    mapping = {
        "HKCR": winreg.HKEY_CLASSES_ROOT,
        "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKU": winreg.HKEY_USERS,
        "HKEY_USERS": winreg.HKEY_USERS,
        "HKCC": winreg.HKEY_CURRENT_CONFIG,
        "HKEY_CURRENT_CONFIG": winreg.HKEY_CURRENT_CONFIG,
    }
    upper = hive_name.upper()
    if upper not in mapping:
        raise ValueError(f"Hive registry inconnu : '{hive_name}'")
    return mapping[upper]


def _reg_type_constant(type_name: str) -> int:
    """REG_DWORD / REG_SZ / etc. -> winreg.* int. Defaut REG_SZ."""
    winreg = _winreg_module()
    mapping = {
        "REG_SZ": winreg.REG_SZ,
        "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
        "REG_DWORD": winreg.REG_DWORD,
        "REG_QWORD": winreg.REG_QWORD,
        "REG_BINARY": winreg.REG_BINARY,
        "REG_MULTI_SZ": winreg.REG_MULTI_SZ,
    }
    return mapping.get(type_name.upper(), winreg.REG_SZ)


# ---------------------------------------------------------------------------
# ApplyResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApplyResult:
    """Resultat normalise d'un `ActionExecutor.apply()`.

    Le contrat est stable : c'est ce que GUI/CLI/MCP serialisent vers
    l'utilisateur. Les nouveaux error_code peuvent etre ajoutes mais les
    existants ne doivent pas changer de semantique.
    """

    success: bool
    message: str
    action_id: str
    rollback_id: str | None = None
    error_code: str | None = None  # admin_required | method_not_implemented |
                                    # unsafe_path | unsafe_registry | unsafe_command |
                                    # timeout | exec_failed | invalid_params |
                                    # already_applied (success=True) | dry_run |
                                    # not_supported_on_platform
    stdout: str | None = None  # debug only
    stderr: str | None = None
    duration_ms: int = 0
    method: str | None = None
    dry_run: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialisation JSON-safe (asdict + extra recursif)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers de securite
# ---------------------------------------------------------------------------


def _expand_path(raw: str) -> str:
    """Etend les variables %ENV% et resout en absolu uppercase pour comparaison.

    Ne resout PAS les symlinks (Path.resolve) — c'est volontaire car on veut
    comparer le chemin DECLARE et non sa cible (qui pourrait etre detournee).
    """
    expanded = os.path.expandvars(raw or "")
    if not expanded:
        return ""
    # Normalisation Windows : remplace / par \, supprime trailing \, uppercase.
    # On NE resout pas vers absolu (os.path.abspath ferait join avec CWD).
    norm = os.path.normpath(expanded).rstrip("\\")
    return norm.upper()


def _matches_any_prefix(canonical: str, prefixes: tuple[str, ...]) -> bool:
    """True si `canonical` commence par un des prefixes (exact ou avec separateur)."""
    if not canonical:
        return False
    for prefix in prefixes:
        prefix_canon = _expand_path(prefix)
        if not prefix_canon:
            continue
        if canonical == prefix_canon:
            return True
        if canonical.startswith(prefix_canon + "\\"):
            return True
    return False


def _is_safe_filesystem_path(raw_path: str) -> tuple[bool, str]:
    """Verifie qu'un chemin est dans la whitelist ET pas dans la forbidden list.

    Returns:
        (is_safe, reason). reason explique le refus le cas echeant.
    """
    if not raw_path or not raw_path.strip():
        return False, "chemin vide"

    canonical = _expand_path(raw_path)
    if not canonical:
        return False, "chemin invalide apres expansion"

    # Forbidden first (defense in depth)
    if _matches_any_prefix(canonical, _FILESYSTEM_FORBIDDEN_PREFIXES):
        return False, f"chemin systeme protege : {raw_path}"

    # Whitelist
    if not _matches_any_prefix(canonical, _FILESYSTEM_WHITELIST_PREFIXES):
        return False, f"chemin hors whitelist : {raw_path}"

    return True, ""


def _is_safe_registry_path(raw_path: str) -> tuple[bool, str]:
    """Refuse l'ecriture/suppression dans les hives systemes critiques.

    Pas de whitelist explicite (trop de cles legitimes) — on bloque uniquement
    une blacklist precise.
    """
    if not raw_path or not raw_path.strip():
        return False, "chemin registry vide"

    canonical = raw_path.strip().upper().replace("/", "\\")
    for prefix in _REGISTRY_FORBIDDEN_PREFIXES:
        if canonical == prefix or canonical.startswith(prefix + "\\"):
            return False, f"cle registry protegee : {raw_path}"

    return True, ""


def _is_safe_command(command: str) -> tuple[bool, str]:
    """Scan une commande PS/CMD pour patterns destructeurs.

    Note : c'est une defense secondaire. La defense primaire est la whitelist
    fichier. On considere qu'un YAML d'action peut contenir un PS one-liner
    arbitraire mais on refuse les patterns evidemment dangereux.
    """
    if not command or not command.strip():
        return False, "commande vide"

    for pattern in _COMMAND_FORBIDDEN_PATTERNS:
        if pattern.search(command):
            return False, f"pattern destructeur detecte : {pattern.pattern}"

    return True, ""


# ---------------------------------------------------------------------------
# ActionExecutor
# ---------------------------------------------------------------------------


class ActionExecutor:
    """Execute reellement les actions YAML WinBoost.

    Usage typique :
        executor = ActionExecutor()
        result = executor.apply(action, dry_run=False)
        if result.success:
            print(f"OK : {result.message}")
        else:
            print(f"FAIL [{result.error_code}] : {result.message}")

    Composition :
    - `BackupManager` (optionnel) : si fourni, on cree un dump reg avant
      registry_set/delete sur action high/critical.
    - `HistoryManager` (optionnel) : si fourni, chaque apply est loggue.
    - `default_timeout` : timeout subprocess (defaut 30s).
    - `module_label` : prefixe utilise pour HistoryManager.module_name
      (defaut "executor", la GUI passe "chat:{cat}", le MCP passe "mcp:{cat}").
    """

    def __init__(
        self,
        *,
        backup_manager: BackupManager | None = None,
        history_manager: HistoryManager | None = None,
        default_timeout: float = DEFAULT_TIMEOUT_SECONDS,
        module_label: str = "executor",
    ) -> None:
        self._backup = backup_manager
        self._history = history_manager
        self._default_timeout = float(default_timeout)
        self._module_label = module_label

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def apply(
        self,
        action: Action,
        *,
        dry_run: bool = False,
        timeout: float | None = None,
    ) -> ApplyResult:
        """Execute une action YAML.

        Args:
            action: instance `winboost.actions.loader.Action`.
            dry_run: si True, ne mute rien et retourne ce qui aurait ete fait.
            timeout: override du timeout par defaut (subprocess uniquement).

        Returns:
            ApplyResult — toujours retourne (jamais leve), success + error_code
            structures.
        """
        started = time.perf_counter()
        method = (action.execute or {}).get("method", "") if action.execute else ""
        params = (action.execute or {}).get("params", {}) if action.execute else {}

        # --- Admin check ----------------------------------------------------
        if getattr(action, "requires_admin", False) and not is_admin():
            return self._finalize(
                action=action,
                success=False,
                message=(
                    f"L'action '{action.name}' requiert les droits administrateur. "
                    "Relance WinBoost en tant qu'administrateur pour l'appliquer."
                ),
                error_code="admin_required",
                method=method,
                dry_run=dry_run,
                started=started,
            )

        # --- Methode connue ? ----------------------------------------------
        handlers = {
            "registry_set": self._execute_registry_set,
            "registry_delete": self._execute_registry_delete,
            "service_stop": self._execute_service_stop,
            "service_disable": self._execute_service_disable,
            "service_set_manual": self._execute_service_set_manual,
            "powershell": self._execute_powershell,
            "cmd": self._execute_cmd,
            "delete_path": self._execute_delete_path,
            "clear_directory": self._execute_clear_directory,
            "scheduled_task_disable": self._execute_scheduled_task_disable,
        }
        handler = handlers.get(method)
        if handler is None:
            return self._finalize(
                action=action,
                success=False,
                message=f"Methode '{method}' non implementee par l'executor.",
                error_code="method_not_implemented",
                method=method,
                dry_run=dry_run,
                started=started,
            )

        # --- Backup high/critical (avant mutation) -------------------------
        rollback_id: str | None = None
        if not dry_run and self._backup is not None and action.risk_level in ("high", "critical"):
            rollback_id = self._backup_before(action, method, params)

        # --- Execution -----------------------------------------------------
        eff_timeout = timeout if timeout is not None else self._default_timeout
        try:
            partial = handler(
                action=action,
                params=params,
                dry_run=dry_run,
                timeout=eff_timeout,
            )
        except Exception as exc:  # noqa: BLE001 — wrap volontaire
            return self._finalize(
                action=action,
                success=False,
                message=f"Erreur inattendue : {exc}",
                error_code="exec_failed",
                method=method,
                dry_run=dry_run,
                started=started,
                rollback_id=rollback_id,
                stderr=str(exc),
            )

        return self._finalize(
            action=action,
            success=partial["success"],
            message=partial["message"],
            error_code=partial.get("error_code"),
            method=method,
            dry_run=dry_run,
            started=started,
            rollback_id=rollback_id,
            stdout=partial.get("stdout"),
            stderr=partial.get("stderr"),
            extra=partial.get("extra", {}),
        )

    # ------------------------------------------------------------------
    # Methodes d'execution
    # ------------------------------------------------------------------

    def _execute_registry_set(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,  # noqa: ARG002
    ) -> dict[str, Any]:
        """registry_set : ecrit une (ou plusieurs) valeur(s) sous une cle HKxx.

        Schema YAML attendu :
            params:
              path: "HKCU\\\\Software\\\\..."
              values:
                - name: "AppsUseLightTheme"
                  type: "REG_DWORD"
                  data: 0
        OU schema raccourci :
              name: "Foo"
              type: "REG_SZ"
              data: "bar"
        """
        path = params.get("path", "")
        ok, reason = _is_safe_registry_path(path)
        if not ok:
            return {
                "success": False,
                "message": f"Chemin registry refuse : {reason}",
                "error_code": "unsafe_registry",
            }

        values = self._normalize_registry_values(params)
        if not values:
            return {
                "success": False,
                "message": "Aucune valeur a ecrire (params.values manquant)",
                "error_code": "invalid_params",
            }

        if sys.platform != "win32":
            return {
                "success": False,
                "message": "registry_set requiert Windows.",
                "error_code": "not_supported_on_platform",
            }

        if dry_run:
            preview = ", ".join(f"{v['name']}={v['data']}" for v in values)
            return {
                "success": True,
                "message": f"[dry-run] registry_set {path} : {preview}",
                "error_code": "dry_run",
                "extra": {"path": path, "values": values},
            }

        winreg = _winreg_module()
        hive_name, _, subkey = path.partition("\\")
        hive = _hive_constant(hive_name)

        # Idempotence : check current value first
        all_already = True
        try:
            with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as k:
                for v in values:
                    try:
                        current, _ = winreg.QueryValueEx(k, v["name"])
                        if current != v["data"]:
                            all_already = False
                            break
                    except FileNotFoundError:
                        all_already = False
                        break
        except (FileNotFoundError, OSError):
            all_already = False

        if all_already:
            return {
                "success": True,
                "message": f"Deja applique — registry {path} a la valeur cible.",
                "error_code": "already_applied",
                "extra": {"path": path, "values": values, "idempotent": True},
            }

        # Ecriture
        try:
            with winreg.CreateKey(hive, subkey) as k:
                for v in values:
                    reg_type = _reg_type_constant(v.get("type", "REG_SZ"))
                    winreg.SetValueEx(k, v["name"], 0, reg_type, v["data"])
        except OSError as exc:
            return {
                "success": False,
                "message": f"Echec registry_set {path} : {exc}",
                "error_code": "exec_failed",
                "stderr": str(exc),
            }

        return {
            "success": True,
            "message": f"Action executee — registry {path} mis a jour ({len(values)} valeur(s))",
            "extra": {"path": path, "values": values},
        }

    def _execute_registry_delete(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,  # noqa: ARG002
    ) -> dict[str, Any]:
        """registry_delete : supprime une valeur ou une sous-cle.

        Si `value_name` est fourni : supprime cette valeur dans la cle.
        Sinon supprime la sous-cle (recursif si `recursive: true`).
        """
        path = params.get("path", "")
        ok, reason = _is_safe_registry_path(path)
        if not ok:
            return {
                "success": False,
                "message": f"Chemin registry refuse : {reason}",
                "error_code": "unsafe_registry",
            }

        value_name = params.get("value_name") or params.get("name")
        recursive = bool(params.get("recursive", False))

        if sys.platform != "win32":
            return {
                "success": False,
                "message": "registry_delete requiert Windows.",
                "error_code": "not_supported_on_platform",
            }

        if dry_run:
            if value_name:
                target = f"value '{value_name}'"
            else:
                target = f"key '{path}' (recursive={recursive})"
            return {
                "success": True,
                "message": f"[dry-run] registry_delete {target}",
                "error_code": "dry_run",
                "extra": {"path": path, "value_name": value_name, "recursive": recursive},
            }

        winreg = _winreg_module()
        hive_name, _, subkey = path.partition("\\")
        hive = _hive_constant(hive_name)

        try:
            if value_name:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE) as k:
                    try:
                        winreg.DeleteValue(k, value_name)
                    except FileNotFoundError:
                        return {
                            "success": True,
                            "message": f"Deja supprime — valeur '{value_name}' inexistante",
                            "error_code": "already_applied",
                        }
            elif recursive:
                self._delete_registry_tree(hive, subkey)
            else:
                try:
                    winreg.DeleteKey(hive, subkey)
                except FileNotFoundError:
                    return {
                        "success": True,
                        "message": f"Deja supprime — cle '{path}' inexistante",
                        "error_code": "already_applied",
                    }
        except OSError as exc:
            return {
                "success": False,
                "message": f"Echec registry_delete {path} : {exc}",
                "error_code": "exec_failed",
                "stderr": str(exc),
            }

        return {
            "success": True,
            "message": f"Action executee — registry {path} supprime",
            "extra": {"path": path, "value_name": value_name, "recursive": recursive},
        }

    def _execute_service_stop(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,
    ) -> dict[str, Any]:
        """service_stop : `sc.exe stop <name>`."""
        name = params.get("service_name") or params.get("service") or ""
        if not name:
            return {
                "success": False,
                "message": "service_stop requiert service_name (ou service)",
                "error_code": "invalid_params",
            }
        if dry_run:
            return {
                "success": True,
                "message": f"[dry-run] sc.exe stop {name}",
                "error_code": "dry_run",
                "extra": {"service_name": name},
            }
        return self._run_subprocess(
            ["sc.exe", "stop", name],
            timeout=timeout,
            success_message=f"Action executee — service '{name}' arrete",
            shell=False,
            allow_nonzero=True,  # sc.exe retourne 1062 si deja stop
            already_applied_substrings=("1062",),
            extra={"service_name": name},
        )

    def _execute_service_disable(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,
    ) -> dict[str, Any]:
        """service_disable : `sc.exe config <name> start= disabled` + stop."""
        name = params.get("service_name") or params.get("service") or ""
        if not name:
            return {
                "success": False,
                "message": "service_disable requiert service_name",
                "error_code": "invalid_params",
            }
        if dry_run:
            return {
                "success": True,
                "message": f"[dry-run] sc.exe config {name} start= disabled (+ stop)",
                "error_code": "dry_run",
                "extra": {"service_name": name},
            }
        # Note : sc.exe veut "start= disabled" avec un espace apres "=".
        config_result = self._run_subprocess(
            ["sc.exe", "config", name, "start=", "disabled"],
            timeout=timeout,
            success_message=f"service '{name}' configure en disabled",
            shell=False,
        )
        if not config_result["success"]:
            return config_result

        # Best-effort stop (peut echouer si deja stop)
        self._run_subprocess(
            ["sc.exe", "stop", name],
            timeout=timeout,
            success_message="",
            shell=False,
            allow_nonzero=True,
            already_applied_substrings=("1062",),
        )

        return {
            "success": True,
            "message": f"Action executee — service '{name}' desactive",
            "extra": {"service_name": name},
        }

    def _execute_service_set_manual(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,
    ) -> dict[str, Any]:
        """service_set_manual : `sc.exe config <name> start= demand`."""
        name = params.get("service_name") or params.get("service") or ""
        if not name:
            return {
                "success": False,
                "message": "service_set_manual requiert service_name",
                "error_code": "invalid_params",
            }
        if dry_run:
            return {
                "success": True,
                "message": f"[dry-run] sc.exe config {name} start= demand",
                "error_code": "dry_run",
                "extra": {"service_name": name},
            }
        return self._run_subprocess(
            ["sc.exe", "config", name, "start=", "demand"],
            timeout=timeout,
            success_message=f"Action executee — service '{name}' en mode manuel",
            shell=False,
            extra={"service_name": name},
        )

    def _execute_powershell(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,
    ) -> dict[str, Any]:
        """powershell : execute un one-liner PS via -Command (UTF-8, NoProfile)."""
        command = params.get("command", "")
        if not command:
            return {
                "success": False,
                "message": "powershell requiert un parametre 'command'",
                "error_code": "invalid_params",
            }
        ok, reason = _is_safe_command(command)
        if not ok:
            return {
                "success": False,
                "message": f"Commande PS refusee : {reason}",
                "error_code": "unsafe_command",
            }
        if dry_run:
            return {
                "success": True,
                "message": f"[dry-run] powershell : {command[:120]}",
                "error_code": "dry_run",
                "extra": {"command": command},
            }
        return self._run_subprocess(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            timeout=timeout,
            success_message=f"Action executee — PowerShell : {command[:80]}",
            shell=False,
            extra={"command": command},
        )

    def _execute_cmd(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,
    ) -> dict[str, Any]:
        """cmd : execute via cmd.exe /c (string)."""
        command = params.get("command", "")
        if not command:
            return {
                "success": False,
                "message": "cmd requiert un parametre 'command'",
                "error_code": "invalid_params",
            }
        ok, reason = _is_safe_command(command)
        if not ok:
            return {
                "success": False,
                "message": f"Commande CMD refusee : {reason}",
                "error_code": "unsafe_command",
            }
        if dry_run:
            return {
                "success": True,
                "message": f"[dry-run] cmd : {command[:120]}",
                "error_code": "dry_run",
                "extra": {"command": command},
            }
        return self._run_subprocess(
            ["cmd.exe", "/c", command],
            timeout=timeout,
            success_message=f"Action executee — CMD : {command[:80]}",
            shell=False,
            extra={"command": command},
        )

    def _execute_delete_path(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,  # noqa: ARG002
    ) -> dict[str, Any]:
        """delete_path : supprime un fichier ou un dossier (whitelist enforced)."""
        raw_path = params.get("path", "")
        ok, reason = _is_safe_filesystem_path(raw_path)
        if not ok:
            return {
                "success": False,
                "message": f"Chemin refuse : {reason}",
                "error_code": "unsafe_path",
            }

        target = Path(os.path.expandvars(raw_path))

        if dry_run:
            return {
                "success": True,
                "message": f"[dry-run] delete_path {target}",
                "error_code": "dry_run",
                "extra": {"path": str(target)},
            }

        if not target.exists():
            return {
                "success": True,
                "message": f"Deja supprime — '{target}' inexistant",
                "error_code": "already_applied",
            }

        try:
            if target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target, ignore_errors=False)
        except (OSError, PermissionError) as exc:
            return {
                "success": False,
                "message": f"Echec delete_path {target} : {exc}",
                "error_code": "exec_failed",
                "stderr": str(exc),
            }

        return {
            "success": True,
            "message": f"Action executee — '{target}' supprime",
            "extra": {"path": str(target)},
        }

    def _execute_clear_directory(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,  # noqa: ARG002
    ) -> dict[str, Any]:
        """clear_directory : supprime le contenu d'un dossier (pattern, recursive).

        Le dossier lui-meme N'EST PAS supprime — on vide son contenu.
        """
        raw_path = params.get("path", "")
        ok, reason = _is_safe_filesystem_path(raw_path)
        if not ok:
            return {
                "success": False,
                "message": f"Chemin refuse : {reason}",
                "error_code": "unsafe_path",
            }

        pattern = params.get("pattern", "*") or "*"
        recursive = bool(params.get("recursive", False))

        target_dir = Path(os.path.expandvars(raw_path))

        if dry_run:
            msg = (
                f"[dry-run] clear_directory {target_dir} "
                f"(pattern={pattern}, recursive={recursive})"
            )
            return {
                "success": True,
                "message": msg,
                "error_code": "dry_run",
                "extra": {"path": str(target_dir), "pattern": pattern, "recursive": recursive},
            }

        if not target_dir.exists():
            return {
                "success": True,
                "message": f"Deja vide — '{target_dir}' inexistant",
                "error_code": "already_applied",
            }
        if not target_dir.is_dir():
            return {
                "success": False,
                "message": f"'{target_dir}' n'est pas un dossier",
                "error_code": "invalid_params",
            }

        deleted = 0
        errors = 0
        iterator = target_dir.rglob(pattern) if recursive else target_dir.glob(pattern)
        for item in iterator:
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink(missing_ok=True)
                    deleted += 1
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    deleted += 1
            except (OSError, PermissionError):
                errors += 1

        return {
            "success": True,
            "message": (
                f"Action executee — '{target_dir}' nettoye "
                f"({deleted} supprime(s), {errors} erreur(s))"
            ),
            "extra": {
                "path": str(target_dir),
                "pattern": pattern,
                "recursive": recursive,
                "deleted": deleted,
                "errors": errors,
            },
        }

    def _execute_scheduled_task_disable(
        self,
        *,
        action: Action,
        params: dict[str, Any],
        dry_run: bool,
        timeout: float,
    ) -> dict[str, Any]:
        """scheduled_task_disable : `schtasks.exe /Change /TN <name> /Disable`."""
        name = params.get("task_name") or params.get("name") or ""
        if not name:
            return {
                "success": False,
                "message": "scheduled_task_disable requiert task_name",
                "error_code": "invalid_params",
            }
        if dry_run:
            return {
                "success": True,
                "message": f"[dry-run] schtasks /Change /TN {name} /Disable",
                "error_code": "dry_run",
                "extra": {"task_name": name},
            }
        return self._run_subprocess(
            ["schtasks.exe", "/Change", "/TN", name, "/Disable"],
            timeout=timeout,
            success_message=f"Action executee — tache planifiee '{name}' desactivee",
            shell=False,
            extra={"task_name": name},
        )

    # ------------------------------------------------------------------
    # Helpers internes
    # ------------------------------------------------------------------

    def _normalize_registry_values(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalise les schemas YAML registry_set vers `[{name, type, data}, ...]`."""
        values = params.get("values")
        if isinstance(values, list) and values:
            return [
                {
                    "name": v.get("name", ""),
                    "type": v.get("type", "REG_SZ"),
                    "data": v.get("data"),
                }
                for v in values
                if isinstance(v, dict) and v.get("name")
            ]
        # Schema raccourci : name/type/data au niveau params
        name = params.get("name")
        if name:
            return [
                {
                    "name": name,
                    "type": params.get("type", "REG_SZ"),
                    "data": params.get("data"),
                }
            ]
        return []

    def _delete_registry_tree(self, hive: int, subkey: str) -> None:
        """Suppression recursive d'une cle registry et de ses enfants."""
        winreg = _winreg_module()
        try:
            with winreg.OpenKey(hive, subkey, 0, winreg.KEY_ALL_ACCESS) as k:
                # Iterer en sens inverse car on supprime
                while True:
                    try:
                        child = winreg.EnumKey(k, 0)
                    except OSError:
                        break
                    self._delete_registry_tree(hive, f"{subkey}\\{child}")
        except FileNotFoundError:
            return
        try:
            winreg.DeleteKey(hive, subkey)
        except FileNotFoundError:
            return

    def _run_subprocess(
        self,
        cmd: list[str],
        *,
        timeout: float,
        success_message: str,
        shell: bool = False,
        allow_nonzero: bool = False,
        already_applied_substrings: tuple[str, ...] = (),
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Wrapper subprocess UTF-8 avec timeout et detection idempotence."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=shell,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "success": False,
                "message": f"Timeout subprocess apres {timeout}s : {' '.join(cmd[:3])}",
                "error_code": "timeout",
                "stderr": str(exc),
            }
        except FileNotFoundError as exc:
            return {
                "success": False,
                "message": f"Executable introuvable : {cmd[0]}",
                "error_code": "exec_failed",
                "stderr": str(exc),
            }

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        combined = stdout + "\n" + stderr

        # Idempotence : code != 0 mais substring connu = "deja applique"
        if (
            proc.returncode != 0
            and already_applied_substrings
            and any(s in combined for s in already_applied_substrings)
        ):
            return {
                "success": True,
                "message": f"Deja applique — {success_message or cmd[0]}",
                "error_code": "already_applied",
                "stdout": stdout,
                "stderr": stderr,
                "extra": extra or {},
            }

        if proc.returncode != 0 and not allow_nonzero:
            return {
                "success": False,
                "message": (
                    f"Echec subprocess (code {proc.returncode}) : "
                    f"{stderr or stdout or 'pas de sortie'}"
                ),
                "error_code": "exec_failed",
                "stdout": stdout,
                "stderr": stderr,
            }

        return {
            "success": True,
            "message": success_message,
            "stdout": stdout,
            "stderr": stderr,
            "extra": extra or {},
        }

    def _backup_before(
        self,
        action: Action,
        method: str,
        params: dict[str, Any],
    ) -> str | None:
        """Cree un point de sauvegarde avant action high/critical.

        Pour registry_* : tente un `reg export` du chemin. Si ca echoue ou si la
        methode n'est pas backup-able, retourne None (l'action continue mais
        sans rollback_id).
        """
        if self._backup is None:
            return None

        try:
            if method in ("registry_set", "registry_delete"):
                path = params.get("path", "")
                if not path:
                    return None
                # Dump dans un fichier .reg que l'on retiendra dans le backup
                tmp_dir = Path(os.environ.get("TEMP", ".")) / "winboost_backup"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                ts = int(time.time() * 1000)
                dump_file = tmp_dir / f"reg_{action.id}_{ts}.reg"

                if sys.platform == "win32":
                    proc = subprocess.run(
                        ["reg.exe", "export", path, str(dump_file), "/y"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=15,
                        check=False,
                    )
                    if proc.returncode != 0 or not dump_file.exists():
                        return None

                    entry = self._backup.create_backup(
                        module_name=f"executor:{action.category}",
                        description=f"Pre-action backup for {action.id} ({action.name})",
                        files_to_backup=[str(dump_file)],
                    )
                    return entry.backup_id if entry else None
        except (OSError, subprocess.SubprocessError):
            return None
        return None

    def _finalize(
        self,
        *,
        action: Action,
        success: bool,
        message: str,
        method: str,
        dry_run: bool,
        started: float,
        error_code: str | None = None,
        rollback_id: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ApplyResult:
        """Construit ApplyResult + log dans HistoryManager (si dispo)."""
        duration_ms = int((time.perf_counter() - started) * 1000)
        result = ApplyResult(
            success=success,
            message=message,
            action_id=action.id,
            rollback_id=rollback_id,
            error_code=error_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            method=method or None,
            dry_run=dry_run,
            extra=dict(extra or {}),
        )

        if self._history is not None:
            try:
                status = (
                    "dry_run"
                    if dry_run
                    else ("success" if success else f"error:{error_code or 'unknown'}")
                )
                self._history.log_action(
                    module_name=f"{self._module_label}:{action.category}",
                    action_type="execute",
                    description=f"Action: {action.name}",
                    risk_level=action.risk_level,
                    result_status=status,
                    result_detail=message,
                    backup_id=rollback_id or "",
                    metadata={
                        "action_id": action.id,
                        "method": method,
                        "dry_run": dry_run,
                        "duration_ms": duration_ms,
                        "error_code": error_code,
                    },
                )
            except Exception:  # noqa: BLE001 — l'historique ne doit jamais casser apply
                pass

        return result


__all__ = [
    "ActionExecutor",
    "ApplyResult",
    "DEFAULT_TIMEOUT_SECONDS",
]
