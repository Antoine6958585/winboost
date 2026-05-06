"""Installation Claude Desktop pour le serveur MCP WinBoost (T071, v2.2).

Patche `claude_desktop_config.json` pour y ajouter (ou retirer) une entree
`winboost` dans la section `mcpServers`. Backup horodate du fichier existant
avant toute modification.

Bloc JSON cible :

    {
      "mcpServers": {
        "winboost": {
          "command": "python",
          "args": ["-m", "winboost", "mcp"],
          "env": {
            "WINBOOST_MCP_TOKEN": "<token genere a l'install>"
          }
        }
      }
    }

Note v2.2.x (cf. tests/mcp_compat/VERDICT.md, recommandation Option A) :
on pourra basculer plus tard sur un binaire `winboost-mcp.exe` dedie. Pour
l'instant, on pointe sur `python -m winboost mcp` (la sous-commande livree
par T070) car c'est la voie la plus simple, testable et compatible PyPI.

Le module est purement filesystem : aucune dependance fastmcp, aucun side-
effect a l'import.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from winboost.mcp.auth import get_token_path, load_or_generate_token

__all__ = [
    "get_claude_desktop_config_path",
    "build_winboost_entry",
    "install_winboost_to_claude_desktop",
    "uninstall_winboost_from_claude_desktop",
    "WINBOOST_SERVER_KEY",
]

#: Cle utilisee dans la section `mcpServers` du config Claude Desktop.
WINBOOST_SERVER_KEY: str = "winboost"


def get_claude_desktop_config_path() -> Path:
    """Retourne le chemin standard du config Claude Desktop selon la plateforme.

    - Windows : `%APPDATA%/Claude/claude_desktop_config.json`
    - macOS  : `~/Library/Application Support/Claude/claude_desktop_config.json`
    - Linux  : `~/.config/Claude/claude_desktop_config.json` (utile en CI)

    Raises:
        RuntimeError: si la plateforme est inconnue (pas Windows / Linux / Mac).
    """
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"

    if sys.platform == "darwin":
        macos_base = Path.home() / "Library" / "Application Support" / "Claude"
        return macos_base / "claude_desktop_config.json"

    if sys.platform.startswith("linux"):
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        return base / "Claude" / "claude_desktop_config.json"

    raise RuntimeError(f"Plateforme non supportee pour Claude Desktop : {sys.platform}")


def build_winboost_entry(token: str) -> dict[str, Any]:
    """Construit le bloc JSON `winboost` a inserer dans `mcpServers`.

    Args:
        token: Token MCP local (genere par `load_or_generate_token`).

    Returns:
        Dict serialisable JSON avec command/args/env.
    """
    return {
        "command": "python",
        "args": ["-m", "winboost", "mcp"],
        "env": {
            "WINBOOST_MCP_TOKEN": token,
        },
    }


def _read_config(path: Path) -> dict[str, Any]:
    """Lit le config JSON s'il existe, sinon retourne `{}`.

    Tolere un fichier vide ou JSON invalide (-> {}). On prefere reconstruire
    une structure saine plutot que de crasher l'install.
    """
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            # Config corrompu : on repart d'une base saine. L'ancien contenu
            # est conserve via le backup (si pas dry_run).
            return {}
        return data
    except (OSError, json.JSONDecodeError):
        return {}


def _backup_config(path: Path) -> Path:
    """Cree une copie horodatee du config existant avant modification.

    Pattern : `claude_desktop_config.json.backup-YYYYMMDD-HHMMSS`.

    Returns:
        Le chemin du backup cree.
    """
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_suffix(path.suffix + f".backup-{timestamp}")
    # Si collision sur la meme seconde, on ajoute un suffixe incremental.
    counter = 1
    while backup_path.exists():
        backup_path = path.with_suffix(
            path.suffix + f".backup-{timestamp}-{counter}"
        )
        counter += 1
    backup_path.write_bytes(path.read_bytes())
    return backup_path


def _write_config(path: Path, data: dict[str, Any]) -> None:
    """Ecrit le config JSON avec indentation 2 et UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def install_winboost_to_claude_desktop(
    *,
    dry_run: bool = False,
    force: bool = False,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Installe ou met a jour l'entree `winboost` dans Claude Desktop.

    Args:
        dry_run: si True, n'ecrit rien ; retourne le bloc qui SERAIT ajoute.
        force: si True, remplace l'entree existante. Sinon, skip si presente.
        config_path: chemin du config (defaut : `get_claude_desktop_config_path`).
                     Surchargeable pour les tests.

    Returns:
        Dict structure ; `action` peut etre :
        - "dry_run"   : rien ecrit, contient `would_add`
        - "skipped"   : entree deja presente et `force=False`
        - "installed" : entree ajoutee ou remplacee

    Raises:
        OSError: si l'ecriture echoue.
        RuntimeError: si la plateforme n'est pas supportee (via get_*_path).
    """
    target_path = config_path or get_claude_desktop_config_path()
    config = _read_config(target_path)
    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}

    already_installed = WINBOOST_SERVER_KEY in servers

    # Skip rapide si deja installe sans force, meme en dry_run (semantique
    # propre : on signale "rien a faire" plutot que "voici ce qu'on ferait").
    if already_installed and not force:
        return {
            "action": "skipped",
            "reason": "winboost already installed in mcpServers (use force=True to replace)",
            "config_path": str(target_path),
            "existing": dict(servers[WINBOOST_SERVER_KEY]),
        }

    # On a besoin d'un token, qu'on soit en dry_run ou non. En dry_run on
    # genere/charge tout de meme (idempotent : si le token existe deja, on
    # ne le change pas). Si l'ecriture du token echoue, on remonte l'OSError.
    token = load_or_generate_token()
    entry = build_winboost_entry(token)

    if dry_run:
        return {
            "action": "dry_run",
            "config_path": str(target_path),
            "would_add": entry,
            "would_replace": already_installed,
            "token_path": str(get_token_path()),
        }

    # Backup du config courant si le fichier existe deja (pas si on cree from scratch).
    backup_path: str | None = None
    if target_path.exists():
        try:
            backup_path = str(_backup_config(target_path))
        except OSError as exc:
            # Pas de backup -> on refuse de continuer (defense en profondeur).
            raise OSError(
                f"Impossible de creer le backup de {target_path} : {exc}"
            ) from exc

    # Patch en memoire puis ecriture.
    servers[WINBOOST_SERVER_KEY] = entry
    config["mcpServers"] = servers
    _write_config(target_path, config)

    return {
        "action": "installed",
        "config_path": str(target_path),
        "token_path": str(get_token_path()),
        "backup_path": backup_path,
        "replaced": already_installed,
    }


def uninstall_winboost_from_claude_desktop(
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Retire l'entree `winboost` de la section `mcpServers`.

    Les autres serveurs MCP et le reste du config sont preserves intacts.
    Cree un backup avant modification (sauf si fichier absent).

    Args:
        config_path: chemin du config (defaut : `get_claude_desktop_config_path`).

    Returns:
        - {"action": "not_installed"} si le fichier n'existe pas
        - {"action": "not_installed"} si le fichier existe mais aucune entree winboost
        - {"action": "uninstalled", ...} si l'entree a ete retiree

    Raises:
        OSError: si l'ecriture echoue.
    """
    target_path = config_path or get_claude_desktop_config_path()

    if not target_path.exists():
        return {
            "action": "not_installed",
            "reason": "config file does not exist",
            "config_path": str(target_path),
        }

    config = _read_config(target_path)
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or WINBOOST_SERVER_KEY not in servers:
        return {
            "action": "not_installed",
            "reason": "winboost entry not present",
            "config_path": str(target_path),
        }

    backup_path = _backup_config(target_path)
    del servers[WINBOOST_SERVER_KEY]
    config["mcpServers"] = servers
    _write_config(target_path, config)

    return {
        "action": "uninstalled",
        "config_path": str(target_path),
        "backup_path": str(backup_path),
    }
