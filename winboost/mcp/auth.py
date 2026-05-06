"""Auth token local pour le serveur MCP WinBoost (T071, milestone v2.2).

Genere et persiste un token aleatoire local pour identifier l'instance
WinBoost active. En v2.2, le serveur stdio (FastMCP) est local par nature
(pipes parent/child), donc le token est principalement defensif :

- documente la provenance "officielle" de l'instance MCP
- exposable au client (Claude Desktop) via la variable d'environnement
  `WINBOOST_MCP_TOKEN` injectee dans `claude_desktop_config.json`
- prepare la voie pour un futur transport HTTP/SSE (v2.2.x ou v2.3+) ou
  l'authentification deviendra obligatoire

Le token est :
- genere par `secrets.token_urlsafe(32)` (43 caracteres URL-safe minimum)
- stocke en clair dans un fichier non versionne :
    - Windows  : `%APPDATA%/WinBoost/mcp_token.txt`
    - Linux/macOS : `$HOME/.config/winboost/mcp_token.txt` (utile pour CI Linux)
- ecrit avec permissions restreintes (`0600` sur POSIX) ; sur Windows on
  ne touche pas a l'ACL (NTFS herite des perms du dossier user).

API stateless : aucun module-level state. Tous les helpers retournent ou
levent OSError si le filesystem refuse l'ecriture.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import sys
from pathlib import Path

__all__ = [
    "get_token_path",
    "load_or_generate_token",
    "reset_token",
    "TOKEN_NBYTES",
]

#: Nombre d'octets bruts demandes a `secrets.token_urlsafe`. La longueur
#: textuelle finale est ~ceil(nbytes * 4/3) caracteres URL-safe (>= 32).
TOKEN_NBYTES: int = 32


def get_token_path() -> Path:
    """Retourne le chemin canonique du fichier de token.

    - Windows : `%APPDATA%/WinBoost/mcp_token.txt`
    - POSIX  : `$HOME/.config/winboost/mcp_token.txt`

    Le dossier parent n'est PAS cree par cette fonction (lecture seule, pure).
    Voir `load_or_generate_token` pour la creation effective.
    """
    if sys.platform.startswith("win"):
        # Windows : %APPDATA% pointe vers Roaming. Fallback sur le home si la
        # variable est absente (cas tres marginal, ex: shell custom).
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "WinBoost" / "mcp_token.txt"
        return Path.home() / "AppData" / "Roaming" / "WinBoost" / "mcp_token.txt"

    # POSIX : convention XDG simplifiee (on respecte XDG_CONFIG_HOME si fourni).
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "winboost" / "mcp_token.txt"


def _generate_token() -> str:
    """Genere un nouveau token URL-safe via `secrets.token_urlsafe`.

    Isole pour permettre le mock dans les tests.
    """
    return secrets.token_urlsafe(TOKEN_NBYTES)


def _write_token(path: Path, token: str) -> None:
    """Ecrit le token sur disque avec permissions restreintes si possible.

    Cree le dossier parent au besoin. Sur POSIX on chmod 0600 le fichier
    apres ecriture ; sur Windows on laisse l'ACL heriter du dossier user
    (NTFS rend l'equivalent 0600 fastidieux et peu pertinent ici).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ecriture atomique-ish : on ecrit puis on chmod. Pas de tmpfile + rename
    # car le token n'est pas critique au point de justifier la complexite.
    path.write_text(token, encoding="utf-8")
    if os.name == "posix":
        # Permissions echouees -> non bloquant. Le fichier est ecrit, c'est
        # l'essentiel ; le defaut umask reste deja restrictif.
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)


def load_or_generate_token() -> str:
    """Charge le token depuis disque, ou en genere un nouveau si absent.

    Returns:
        Le token (str URL-safe, longueur >= 32 caracteres).

    Raises:
        OSError: si l'ecriture du fichier (ou la creation du dossier) echoue.
    """
    path = get_token_path()

    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8").strip()
        except OSError:
            # Fichier corrompu / illisible : on regenere plutot que crash.
            existing = ""
        if existing:
            return existing

    # Soit absent, soit vide -> generer + persister.
    token = _generate_token()
    _write_token(path, token)
    return token


def reset_token() -> str:
    """Force la regeneration du token (utile en cas de fuite suspectee).

    Returns:
        Le nouveau token genere.

    Raises:
        OSError: si l'ecriture echoue.
    """
    path = get_token_path()
    token = _generate_token()
    _write_token(path, token)
    return token
