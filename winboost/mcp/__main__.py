"""Entry point pour le binaire `winboost-mcp.exe` (PyInstaller, T072 polish A).

Ce module est l'unique entry point du binaire MCP standalone produit par
`build_mcp.py`. Il respecte les 3 invariants T072 (verdict GO sous conditions) :

    1. `sys.stdin.reconfigure(encoding="utf-8")` — Windows utilise cp1252 par
       defaut sous PyInstaller console, le moindre caractere unicode (accent,
       emoji, kanji) leve un UnicodeEncodeError sans cette reconfiguration.
    2. `sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)` — meme
       raison, cote sortie. line_buffering complete (mais ne remplace pas) le
       flush manuel pratique cote `mcp.run(transport="stdio")`.
    3. Build en `--console` mode (gere par `build_mcp.py`, pas ici) — sans
       console, stdin/stdout sont rediriges vers NUL en l'absence d'un parent
       process pipe.

Usage end-user (Claude Desktop, Cursor, mcp-cli) :

    winboost-mcp.exe

Le binaire bloque jusqu'a EOF / SIGINT / Ctrl+C. stdout est strictement reserve
au protocole JSON-RPC. Toute trace de log va sur stderr.

Lecture des invariants : `tests/mcp_compat/VERDICT.md`.
"""

from __future__ import annotations

import sys


def _force_utf8() -> None:
    """Reconfigure stdin/stdout en UTF-8 si possible.

    Sur Python 3.7+ `TextIOWrapper.reconfigure()` est dispo. Sur quelques rares
    backends (stdin redirige vers un objet custom, environnement embarque), la
    methode peut ne pas exister ou refuser la reconfiguration : on tombe
    silencieusement (mieux vaut un binaire qui demarre quand meme et echoue
    explicitement sur un caractere unicode qu'un binaire qui crashe au boot).

    Cette fonction est isolee pour pouvoir etre testee sans demarrer le
    serveur MCP.
    """
    # stdin
    try:
        reconfigure = getattr(sys.stdin, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        # AttributeError : pas de reconfigure
        # ValueError : encoding non supporte ou stream deja ferme
        # OSError : redirection non standard
        pass

    # stdout — line_buffering=True est defensive, le flush manuel cote
    # FastMCP reste la garantie principale (cf. invariant 2 du VERDICT).
    try:
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", line_buffering=True)
    except (AttributeError, ValueError, OSError):
        pass


def main() -> int:
    """Entry point du binaire `winboost-mcp.exe`.

    Returns:
        0 en cas de sortie propre (EOF / Ctrl+C),
        1 en cas d'exception fatale (fastmcp manquant, crash interne).

    Le code de retour est exploite par PyInstaller / Claude Desktop pour
    afficher un statut "process exited" pertinent.
    """
    _force_utf8()

    # Import paresseux : permet aux tests de mocker `run_stdio` sans
    # provoquer l'import de fastmcp (et donc le crash si l'extra `mcp`
    # n'est pas installe en environnement de test).
    from winboost.mcp.server import run_stdio

    try:
        run_stdio()
    except KeyboardInterrupt:
        # Sortie propre Ctrl+C — pas un echec.
        return 0
    except SystemExit as exc:  # pragma: no cover — pour completude
        # On laisse les SystemExit explicites passer avec leur code.
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        # SystemExit avec une string -> message d'erreur
        sys.stderr.write(f"[winboost-mcp] {code}\n")
        return 1
    except Exception as exc:  # noqa: BLE001 — wrap volontaire au boundary
        # Toute exception non geree dans run_stdio doit produire un message
        # lisible sur stderr (le client MCP voit ainsi pourquoi le serveur a
        # plante au lieu d'un traceback Python brut sur stdout qui casserait
        # le protocole JSON-RPC).
        sys.stderr.write(f"[winboost-mcp] fatal: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover — execute uniquement via -m / .exe
    sys.exit(main())
