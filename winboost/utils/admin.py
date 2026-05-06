"""Helpers d'elevation UAC (User Account Control) sous Windows.

Ce module fournit la verification du contexte admin et la relance du process
en mode eleve. Les actions YAML marquees `requires_admin: true` doivent
appeler `require_admin()` avant execution, sous peine de lever
`AdminRequiredError`.

Pattern d'usage :
    from winboost.utils.admin import is_admin, AdminRequiredError, require_admin

    if action.requires_admin:
        try:
            require_admin()  # leve si pas admin
        except AdminRequiredError as e:
            print(f"Cette action requiert les droits admin : {e}")
            return

Sur Windows : utilise ctypes.windll.shell32.IsUserAnAdmin et ShellExecuteW.
Sur autres OS : is_admin() lit os.geteuid() == 0 (pour les tests Linux/macOS).
"""

from __future__ import annotations

import ctypes
import os
import sys


class AdminRequiredError(RuntimeError):
    """Levee quand une action necessite admin et que le process n'est pas eleve."""


def is_admin() -> bool:
    """Indique si le process courant a les droits administrateur.

    Returns:
        True si le process est admin (Windows) ou root (Unix), False sinon.
        En cas d'erreur d'introspection, retourne False (fail-safe).
    """
    if sys.platform == "win32":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False
    # Fallback Unix (utilise pour les tests CI Linux)
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except AttributeError:
        return False


def require_admin(action_name: str = "") -> None:
    """Leve AdminRequiredError si le process n'est pas admin.

    Args:
        action_name: Nom de l'action pour le message d'erreur (optionnel).

    Raises:
        AdminRequiredError: Si is_admin() est False.
    """
    if not is_admin():
        msg = (
            f"L'action '{action_name}' requiert les droits administrateur."
            if action_name
            else "Cette operation requiert les droits administrateur."
        )
        msg += " Relance WinBoost en tant qu'administrateur."
        raise AdminRequiredError(msg)


def relaunch_as_admin(args: list[str] | None = None) -> bool:
    """Relance le process courant avec elevation UAC (Windows uniquement).

    Args:
        args: Arguments a passer au nouveau process. Defaut : sys.argv[1:].

    Returns:
        True si la relance a ete declenchee (le process courant doit ensuite
        s'arreter via sys.exit). False si la relance n'est pas supportee
        (non-Windows) ou a echoue.

    Note:
        ShellExecuteW("runas", ...) declenche le prompt UAC. L'utilisateur
        peut refuser : dans ce cas la relance n'a pas lieu et la fonction
        retourne quand meme True (le process courant doit decider quoi faire).
    """
    if sys.platform != "win32":
        return False

    if is_admin():
        return True  # deja admin, rien a faire

    args = args if args is not None else sys.argv[1:]
    params = " ".join(f'"{a}"' for a in args)

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            params,
            None,
            1,  # SW_SHOWNORMAL
        )
        # ShellExecuteW retourne > 32 si succes
        return result > 32
    except (AttributeError, OSError):
        return False
