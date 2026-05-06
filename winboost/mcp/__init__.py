"""Sous-module MCP — serveur FastMCP exposant WinBoost via Model Context Protocol.

Ce sous-package est *optionnel*. Il s'active via l'extra :

    pip install winboost[mcp]

Les imports lourds (fastmcp) restent confines a `server.py` pour ne jamais
casser un utilisateur qui n'a pas installe l'extra.

Voir `winboost/mcp/README.md` pour l'usage detaille (5 tools, transport stdio,
integration Claude Desktop).
"""

from __future__ import annotations

__all__ = ["create_server"]


def create_server(*args, **kwargs):  # type: ignore[no-untyped-def]
    """Lazy proxy vers `winboost.mcp.server.create_server`.

    Permet `from winboost.mcp import create_server` sans importer fastmcp
    tant qu'on ne cree pas effectivement le serveur. Si fastmcp n'est pas
    installe, l'erreur est levee ici avec un message explicite (cf. server.py).
    """
    from winboost.mcp.server import create_server as _impl

    return _impl(*args, **kwargs)
