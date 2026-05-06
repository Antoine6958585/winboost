"""Serveur FastMCP WinBoost — expose 5 tools pilotables par Claude Desktop / Cursor / Code.

Tools exposes (T070, milestone v2.2) :

    chat(query)              -> route une requete NL -> actions YAML
    scan(module=None)        -> scanne un (ou tous) les modules -> findings
    apply(action_id)         -> consigne / declenche l'execution d'une action YAML
    list_actions(category=None) -> liste les actions du registry
    undo(rollback_id)        -> restaure un point de sauvegarde

Transport : stdio uniquement en v2.2 (compatible Claude Desktop d'office).
HTTP/SSE viendra en T071+ (avec auth token local).

Activation :
    pip install winboost[mcp]
    winboost mcp

Le module ne demarre rien a l'import. Seuls `create_server()` et la commande
CLI `winboost mcp` initialisent et lancent le serveur.

Conventions d'erreur :
- Chaque tool wrap son corps dans try/except.
- Erreurs renvoyees au client MCP en dict structure :
      {"error": str(exc), "type": exc.__class__.__name__}
  plutot que de laisser remonter une exception (qui crasherait le tool cote MCP).

Logs :
- stdout est reserve au protocole JSON-RPC (MCP stdio).
- Toute log/print va EXCLUSIVEMENT sur stderr.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from winboost.actions.loader import ActionRegistry
from winboost.ai.action_router import ActionRouter
from winboost.core.backup import BackupManager
from winboost.core.config import Config
from winboost.core.engine import Engine
from winboost.core.history import HistoryManager
from winboost.mcp.serializers import (
    action_to_dict,
    route_result_to_dict,
    scan_all_to_dict,
    scan_result_to_dict,
)


def _eprint(*args: Any, **kwargs: Any) -> None:
    """Print sur stderr (stdout est reserve au protocole MCP stdio)."""
    print(*args, file=sys.stderr, **kwargs)


def _missing_fastmcp_message() -> str:
    return (
        "Le module MCP necessite `pip install winboost[mcp]`. "
        "Installe-le pour activer cette commande."
    )


def _import_fastmcp():  # type: ignore[no-untyped-def]
    """Import paresseux de fastmcp avec message d'erreur clair."""
    try:
        from fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(_missing_fastmcp_message()) from exc
    return FastMCP


def create_server(
    *,
    config: Config | None = None,
    actions_dir: Path | None = None,
    backup_manager: BackupManager | None = None,
    history_manager: HistoryManager | None = None,
    router: ActionRouter | None = None,
    engine: Engine | None = None,
    registry: ActionRegistry | None = None,
):  # type: ignore[no-untyped-def]
    """Construit et retourne une instance FastMCP avec les 5 tools enregistres.

    Tous les composants (router, engine, backup, history, registry) sont
    injectables pour permettre les tests. Si non fournis, on instancie les
    valeurs par defaut.

    Returns:
        Instance `fastmcp.FastMCP` prete a `run(transport="stdio")`.

    Raises:
        ImportError: si `fastmcp` n'est pas installe (extra `mcp` manquant).
    """
    fast_mcp_cls = _import_fastmcp()

    cfg = config or Config()
    actions_path = actions_dir or (Path(__file__).parent.parent / "actions")

    # Composants partages — instancies une seule fois pour la duree du serveur.
    _router = router or ActionRouter(config=cfg, actions_dir=actions_path)
    _registry = registry or _router.registry
    _backup = backup_manager or BackupManager()
    _history = history_manager or HistoryManager()

    if engine is not None:
        _engine = engine
    else:
        _engine = Engine(cfg)
        _engine.discover_modules()

    mcp = fast_mcp_cls("winboost")

    # -------------------------------------------------------------------------
    # Tool : chat
    # -------------------------------------------------------------------------
    @mcp.tool()
    def chat(query: str) -> dict[str, Any]:
        """Route une requete en langage naturel vers les actions WinBoost.

        Args:
            query: Requete utilisateur ("active le mode focus", "nettoie mes temp"...).

        Returns:
            Schema identique a `winboost chat --json` :
            {
              "query": str,
              "resolved_by": "cache" | "llm" | "category_fallback" | "none",
              "message": str,
              "has_actions": bool,
              "actions": [...],   # actions autorisees par le profil
              "blocked": [...]    # actions bloquees par le profil
            }
        """
        try:
            q = (query or "").strip()
            if not q:
                return {
                    "error": "query is required",
                    "type": "ValueError",
                }
            result = _router.route(q)
            return route_result_to_dict(q, result)
        except Exception as exc:  # noqa: BLE001 — wrap volontaire pour MCP
            return {"error": str(exc), "type": exc.__class__.__name__}

    # -------------------------------------------------------------------------
    # Tool : scan
    # -------------------------------------------------------------------------
    @mcp.tool()
    def scan(module: str | None = None) -> dict[str, Any]:
        """Scanne un module (ou tous) et retourne les findings.

        Args:
            module: Nom du module (`temp_cleaner`, `ram_optimizer`...). Si `None`,
                    scanne tous les modules charges.

        Returns:
            Si module=None :
              {"modules": {name: ScanResultDict}, "module_count": int, "total_issues": int}
            Si module=<name> :
              ScanResultDict = {"module_name", "summary", "issue_count",
                                "has_issues", "issues": [...]}
            Si module inconnu :
              {"error": "...", "type": "ValueError"}
        """
        try:
            if module is None:
                results = _engine.scan_all()
                return scan_all_to_dict(results)
            single = _engine.scan_module(module)
            return scan_result_to_dict(single)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "type": exc.__class__.__name__}

    # -------------------------------------------------------------------------
    # Tool : apply
    # -------------------------------------------------------------------------
    @mcp.tool()
    def apply(action_id: str) -> dict[str, Any]:
        """Applique une action YAML par son ID.

        Comportement v2.2 (aligne avec `gui/chat._execute_worker`) :
        - L'action est cherchee dans le registry.
        - Si introuvable -> error.
        - Sinon, l'intention est consignee dans l'historique avec status
          `catalogued` (catalogue v2.0/v2.1). L'executor reel des YAML
          (registry_set, powershell, service_*) sera branche dans une phase
          ulterieure ; ce contrat MCP est stable et ne changera pas alors.

        Args:
            action_id: ID de l'action (ex: "sys_011" pour dark_mode_on).

        Returns:
            {
              "success": bool,
              "message": str,                  # description humaine
              "action_id": str,                # echo
              "rollback_id": str | None,       # backup_id si un backup a ete cree
              "status": "catalogued" | "applied" | "blocked_admin_required"
            }
            ou {"error": "...", "type": "..."} si action_id introuvable.
        """
        try:
            if not action_id or not str(action_id).strip():
                return {"error": "action_id is required", "type": "ValueError"}

            action = _registry.get(action_id)
            if action is None:
                return {
                    "error": f"Action inconnue : '{action_id}'",
                    "type": "KeyError",
                }

            # Phase v2.2 : on consigne dans l'historique. L'execution reelle
            # (registry_set / powershell / service_*) est planifiee post-MCP.
            method = action.execute.get("method", "N/A") if action.execute else "N/A"
            params = action.execute.get("params", {}) if action.execute else {}

            detail = (
                f"Action enregistree (catalogue v2.x via MCP, methode '{method}'"
            )
            if params:
                param_str = ", ".join(f"{k}={v}" for k, v in params.items())
                detail += f", parametres : {param_str}"
            detail += "). Execution systeme reelle prevue post-MCP standalone."

            entry_id = _history.log_action(
                module_name=f"mcp:{action.category}",
                action_type="execute",
                description=f"Action: {action.name}",
                risk_level=action.risk_level,
                result_status="catalogued",
                result_detail=detail,
            )

            return {
                "success": True,
                "message": detail,
                "action_id": action.id,
                "rollback_id": None,
                "status": "catalogued",
                "history_entry_id": entry_id,
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "type": exc.__class__.__name__}

    # -------------------------------------------------------------------------
    # Tool : list_actions
    # -------------------------------------------------------------------------
    @mcp.tool()
    def list_actions(category: str | None = None) -> dict[str, Any]:
        """Liste les actions disponibles dans le registry.

        Args:
            category: Filtre par categorie (`system`, `network`, `appearance`,
                      `privacy`, `performance`, `cleanup`, `dev_tools`,
                      `security`, `gaming`). Si `None`, retourne toutes les actions.

        Returns:
            {
              "actions": [{id, name, description, category, risk_level,
                           requires_admin, reversible}, ...],
              "count": int,
              "category": str | None
            }
            Si category invalide -> liste vide + message indicatif (pas d'erreur
            dure : on prefere la souplesse pour les consommateurs MCP).
        """
        try:
            items = _registry.list_by_category(category) if category else _registry.list_all()
            return {
                "actions": [action_to_dict(a) for a in items],
                "count": len(items),
                "category": category,
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "type": exc.__class__.__name__}

    # -------------------------------------------------------------------------
    # Tool : undo
    # -------------------------------------------------------------------------
    @mcp.tool()
    def undo(rollback_id: str) -> dict[str, Any]:
        """Restaure un point de sauvegarde par son backup_id.

        Args:
            rollback_id: ID du backup a restaurer (correspond a `BackupEntry.backup_id`).

        Returns:
            {
              "success": bool,
              "message": str,
              "rollback_id": str,
              "files_restored": int,
              "errors": int
            }
            ou {"error": "...", "type": "..."} si rollback_id introuvable / vide.
        """
        try:
            if not rollback_id or not str(rollback_id).strip():
                return {"error": "rollback_id is required", "type": "ValueError"}

            entry = _backup.get_backup(rollback_id)
            if entry is None:
                return {
                    "error": f"Rollback inconnu : '{rollback_id}'",
                    "type": "KeyError",
                }

            restored, errors = _backup.restore_backup(rollback_id)

            # Trace dans l'historique pour le history-viewer GUI
            _history.log_action(
                module_name=entry.module_name,
                action_type="restore",
                description=f"Rollback via MCP : {entry.description}",
                risk_level="low",
                result_status="success" if errors == 0 else "partial",
                result_detail=f"{restored} fichier(s) restaure(s), {errors} erreur(s)",
                backup_id=rollback_id,
            )

            return {
                "success": errors == 0,
                "message": f"{restored} fichier(s) restaure(s), {errors} erreur(s)",
                "rollback_id": rollback_id,
                "files_restored": restored,
                "errors": errors,
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "type": exc.__class__.__name__}

    return mcp


def run_stdio() -> None:
    """Lance le serveur FastMCP en mode stdio (Claude Desktop par defaut).

    Cette fonction bloque jusqu'a EOF / SIGINT. stdout est reserve au protocole
    MCP — on log uniquement sur stderr.
    """
    try:
        mcp = create_server()
    except ImportError as exc:
        _eprint(f"[winboost mcp] {exc}")
        raise

    _eprint("[winboost mcp] FastMCP server demarre en stdio. Ctrl+C pour arreter.")
    mcp.run(transport="stdio")


__all__ = ["create_server", "run_stdio"]
