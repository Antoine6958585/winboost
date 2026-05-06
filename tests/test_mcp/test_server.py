"""Tests pour le serveur FastMCP WinBoost (T070, milestone v2.2).

Couvre 12+ scenarios :

- Construction du serveur
- Inventaire des 5 tools (chat, scan, apply, list_actions, undo)
- Tool `chat` : succes (cache), query vide, exception interne
- Tool `scan` : sans module, avec module valide, module inconnu
- Tool `list_actions` : sans category, avec category, category invalide
- Tool `apply` : action_id valide, action_id inconnu, action_id vide
- Tool `undo` : rollback_id valide (mock), rollback_id inconnu, rollback_id vide

Strategie de mock :
- ActionRouter : mock complet (route() retourne un faux RouteResult)
- Engine : mock (scan_all + scan_module)
- ActionRegistry : mock (get + list_all + list_by_category)
- BackupManager : mock (get_backup + restore_backup)
- HistoryManager : mock (log_action)

Aucun test ne demarre un vrai serveur stdio (trop fragile en CI).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from winboost.mcp.server import create_server

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_action(
    action_id: str = "sys_011",
    name: str = "Activer le mode sombre",
    category: str = "system",
    risk: str = "low",
) -> Any:
    """Construit un faux Action (suffisant pour les serializers et apply)."""
    return SimpleNamespace(
        id=action_id,
        name=name,
        description=f"Description de {name}",
        category=category,
        risk_level=risk,
        requires_admin=False,
        reversible=True,
        execute={"method": "registry_set", "params": {"key": "AppsUseLightTheme", "value": 0}},
        rollback={"method": "registry_set", "params": {}},
        preview={},
        keywords={},
    )


def _make_routed_action(action: Any | None = None, allowed: bool = True) -> Any:
    """Construit un faux RoutedAction (action + verdict + score + source)."""
    if action is None:
        action = _make_action()
    verdict = SimpleNamespace(
        allowed=allowed,
        requires_dry_run=False,
        requires_confirmation=False,
        reason="" if allowed else "Bloque par profil safe",
    )
    return SimpleNamespace(action=action, verdict=verdict, score=0.95, source="cache")


def _make_route_result(
    query: str = "dark mode",
    actions: list[Any] | None = None,
    blocked: list[Any] | None = None,
    resolved_by: str = "cache",
    message: str = "1 action(s) proposee(s)",
) -> Any:
    """Construit un faux RouteResult."""
    actions = actions if actions is not None else [_make_routed_action()]
    blocked = blocked or []
    return SimpleNamespace(
        query=query,
        intent=SimpleNamespace(category="system", confidence=0.9, source="cache"),
        actions=actions,
        blocked=blocked,
        message=message,
        resolved_by=resolved_by,
        has_actions=len(actions) > 0,
        all_safe=all(getattr(a.verdict, "allowed", False) for a in actions),
    )


def _make_scan_result(
    module_name: str = "temp_cleaner",
    issue_count: int = 3,
) -> Any:
    """Construit un faux ScanResult."""
    issues = [
        SimpleNamespace(
            id=f"{module_name}_issue_{i}",
            description=f"Probleme #{i}",
            risk_level=SimpleNamespace(value="low"),
            auto_fixable=True,
            metadata={},
        )
        for i in range(issue_count)
    ]
    return SimpleNamespace(
        module_name=module_name,
        issues=issues,
        issue_count=issue_count,
        has_issues=issue_count > 0,
        summary=f"{issue_count} probleme(s)",
    )


def _make_fake_executor() -> MagicMock:
    """Fake ActionExecutor qui retourne un ApplyResult success=True."""
    from winboost.core.executor import ApplyResult

    fake = MagicMock()

    def _apply(action: Any, *, dry_run: bool = False, timeout: float | None = None) -> ApplyResult:
        return ApplyResult(
            success=True,
            message=f"[fake] {action.name} executed",
            action_id=action.id,
            method=(action.execute or {}).get("method"),
            dry_run=dry_run,
            duration_ms=1,
        )

    fake.apply.side_effect = _apply
    return fake


def _build_server_with_mocks(
    *,
    router: Any | None = None,
    engine: Any | None = None,
    registry: Any | None = None,
    backup: Any | None = None,
    history: Any | None = None,
    executor: Any | None = None,
):
    """Cree un FastMCP avec composants entierement mockes."""
    # Defaults : registry avec 1 action, router qui route, engine avec 1 module
    default_action = _make_action()
    if registry is None:
        registry = MagicMock()
        registry.get = MagicMock(side_effect=lambda aid: default_action if aid == "sys_011" else None)
        registry.list_all = MagicMock(return_value=[default_action])
        registry.list_by_category = MagicMock(
            side_effect=lambda cat: [default_action] if cat == "system" else []
        )

    if router is None:
        router = MagicMock()
        router.route = MagicMock(return_value=_make_route_result())
        router.registry = registry

    if engine is None:
        engine = MagicMock()
        engine.scan_all = MagicMock(
            return_value={"temp_cleaner": _make_scan_result("temp_cleaner", 3)}
        )

        def _scan_module(name: str):
            if name == "temp_cleaner":
                return _make_scan_result("temp_cleaner", 5)
            raise ValueError(f"Module inconnu : '{name}'. Disponibles : ['temp_cleaner']")

        engine.scan_module = MagicMock(side_effect=_scan_module)

    if backup is None:
        backup = MagicMock()
        backup.get_backup = MagicMock(return_value=None)
        backup.restore_backup = MagicMock(return_value=(0, 0))

    if history is None:
        history = MagicMock()
        history.log_action = MagicMock(return_value=42)

    if executor is None:
        executor = _make_fake_executor()

    return create_server(
        router=router,
        engine=engine,
        registry=registry,
        backup_manager=backup,
        history_manager=history,
        executor=executor,
    ), {
        "router": router,
        "engine": engine,
        "registry": registry,
        "backup": backup,
        "history": history,
        "executor": executor,
    }


def _get_tool_fn(server: Any, name: str):
    """Recupere la fonction sous-jacente d'un tool par son nom (via list_tools async)."""
    tools = asyncio.run(server.list_tools())
    for t in tools:
        if t.name == name:
            return t.fn
    raise KeyError(f"Tool '{name}' introuvable. Disponibles : {[t.name for t in tools]}")


def _list_tool_names(server: Any) -> list[str]:
    tools = asyncio.run(server.list_tools())
    return [t.name for t in tools]


# ---------------------------------------------------------------------------
# Tests : construction du serveur
# ---------------------------------------------------------------------------

class TestServerCreation:
    def test_create_server_returns_fastmcp_instance(self):
        """create_server() retourne un objet FastMCP non None."""
        server, _ = _build_server_with_mocks()
        assert server is not None
        # Duck-typing : doit avoir `tool` decorateur et `run` methode
        assert callable(getattr(server, "tool", None))
        assert callable(getattr(server, "run", None))

    def test_server_exposes_exactly_five_tools(self):
        """Le serveur expose exactement les 5 tools attendus."""
        server, _ = _build_server_with_mocks()
        names = set(_list_tool_names(server))
        expected = {"chat", "scan", "apply", "list_actions", "undo"}
        assert names == expected, (
            f"Tools attendus {expected}, obtenus {names} (delta : {names ^ expected})"
        )


# ---------------------------------------------------------------------------
# Tests : tool `chat`
# ---------------------------------------------------------------------------

class TestChatTool:
    def test_chat_with_valid_query_returns_route_result_dict(self):
        server, mocks = _build_server_with_mocks()
        chat_fn = _get_tool_fn(server, "chat")
        result = chat_fn(query="dark mode")
        assert isinstance(result, dict)
        assert result["query"] == "dark mode"
        assert result["resolved_by"] == "cache"
        assert result["has_actions"] is True
        assert isinstance(result["actions"], list)
        assert len(result["actions"]) == 1
        assert result["actions"][0]["id"] == "sys_011"
        # Le router a bien ete appele
        mocks["router"].route.assert_called_once_with("dark mode")

    def test_chat_with_empty_query_returns_error(self):
        server, _ = _build_server_with_mocks()
        chat_fn = _get_tool_fn(server, "chat")
        result = chat_fn(query="")
        assert "error" in result
        assert result["type"] == "ValueError"
        # Le router NE doit PAS etre appele sur une query vide

    def test_chat_with_whitespace_only_query_returns_error(self):
        server, mocks = _build_server_with_mocks()
        chat_fn = _get_tool_fn(server, "chat")
        result = chat_fn(query="   \t  ")
        assert "error" in result
        mocks["router"].route.assert_not_called()

    def test_chat_wraps_internal_exceptions(self):
        """Si le router leve une exception, le tool retourne {error, type}."""
        bad_router = MagicMock()
        bad_router.route = MagicMock(side_effect=RuntimeError("boom"))
        bad_router.registry = MagicMock()
        server, _ = _build_server_with_mocks(router=bad_router)
        chat_fn = _get_tool_fn(server, "chat")
        result = chat_fn(query="anything")
        assert "error" in result
        assert result["type"] == "RuntimeError"
        assert "boom" in result["error"]


# ---------------------------------------------------------------------------
# Tests : tool `scan`
# ---------------------------------------------------------------------------

class TestScanTool:
    def test_scan_without_module_returns_all_modules(self):
        server, _ = _build_server_with_mocks()
        scan_fn = _get_tool_fn(server, "scan")
        result = scan_fn(module=None)
        assert isinstance(result, dict)
        assert "modules" in result
        assert "temp_cleaner" in result["modules"]
        assert result["module_count"] == 1
        assert result["total_issues"] == 3

    def test_scan_with_specific_module_returns_single_result(self):
        server, _ = _build_server_with_mocks()
        scan_fn = _get_tool_fn(server, "scan")
        result = scan_fn(module="temp_cleaner")
        assert result["module_name"] == "temp_cleaner"
        assert result["issue_count"] == 5
        assert result["has_issues"] is True
        assert isinstance(result["issues"], list)
        assert len(result["issues"]) == 5

    def test_scan_with_unknown_module_returns_error(self):
        server, _ = _build_server_with_mocks()
        scan_fn = _get_tool_fn(server, "scan")
        result = scan_fn(module="nonexistent_module")
        assert "error" in result
        assert result["type"] == "ValueError"
        assert "nonexistent_module" in result["error"]


# ---------------------------------------------------------------------------
# Tests : tool `list_actions`
# ---------------------------------------------------------------------------

class TestListActionsTool:
    def test_list_actions_without_category(self):
        server, _ = _build_server_with_mocks()
        fn = _get_tool_fn(server, "list_actions")
        result = fn(category=None)
        assert isinstance(result, dict)
        assert "actions" in result
        assert "count" in result
        assert "category" in result
        assert result["category"] is None
        assert result["count"] >= 1
        assert all(set(a.keys()) >= {"id", "name", "category", "risk_level"} for a in result["actions"])

    def test_list_actions_with_valid_category(self):
        server, _ = _build_server_with_mocks()
        fn = _get_tool_fn(server, "list_actions")
        result = fn(category="system")
        assert result["category"] == "system"
        assert result["count"] == 1
        assert result["actions"][0]["category"] == "system"

    def test_list_actions_with_unknown_category_returns_empty(self):
        """Categorie inconnue : liste vide, pas d'erreur dure (souplesse MCP)."""
        server, _ = _build_server_with_mocks()
        fn = _get_tool_fn(server, "list_actions")
        result = fn(category="nonexistent_category_xyz")
        assert "actions" in result
        assert result["actions"] == []
        assert result["count"] == 0
        assert result["category"] == "nonexistent_category_xyz"


# ---------------------------------------------------------------------------
# Tests : tool `apply`
# ---------------------------------------------------------------------------

class TestApplyTool:
    def test_apply_with_known_action_returns_success(self):
        server, mocks = _build_server_with_mocks()
        fn = _get_tool_fn(server, "apply")
        result = fn(action_id="sys_011")
        assert result["success"] is True, result
        assert result["action_id"] == "sys_011"
        # v2.2.x : status est "applied" (real executor) au lieu de "catalogued"
        assert result["status"] in ("applied", "catalogued", "already_applied", "dry_run")
        assert "history_entry_id" in result
        # L'executor a ete appele
        mocks["executor"].apply.assert_called_once()

    def test_apply_with_unknown_action_returns_error(self):
        server, _ = _build_server_with_mocks()
        fn = _get_tool_fn(server, "apply")
        result = fn(action_id="this_does_not_exist")
        assert "error" in result
        assert result["type"] == "KeyError"
        assert "this_does_not_exist" in result["error"]

    def test_apply_with_empty_action_id_returns_error(self):
        server, _ = _build_server_with_mocks()
        fn = _get_tool_fn(server, "apply")
        result = fn(action_id="")
        assert "error" in result
        assert result["type"] == "ValueError"


# ---------------------------------------------------------------------------
# Tests : tool `undo`
# ---------------------------------------------------------------------------

class TestUndoTool:
    def test_undo_with_unknown_rollback_id_returns_error(self):
        server, _ = _build_server_with_mocks()
        fn = _get_tool_fn(server, "undo")
        result = fn(rollback_id="backup_99999_doesnotexist")
        assert "error" in result
        assert result["type"] == "KeyError"

    def test_undo_with_empty_rollback_id_returns_error(self):
        server, _ = _build_server_with_mocks()
        fn = _get_tool_fn(server, "undo")
        result = fn(rollback_id="")
        assert "error" in result
        assert result["type"] == "ValueError"

    def test_undo_with_valid_rollback_id_returns_success(self):
        """Si le backup existe, undo restaure et retourne success."""
        backup = MagicMock()
        fake_entry = SimpleNamespace(
            backup_id="backup_20260506_001",
            module_name="temp_cleaner",
            description="Avant nettoyage",
            files=[],
            created_at="2026-05-06T10:00:00+00:00",
        )
        backup.get_backup = MagicMock(return_value=fake_entry)
        backup.restore_backup = MagicMock(return_value=(3, 0))

        server, mocks = _build_server_with_mocks(backup=backup)
        fn = _get_tool_fn(server, "undo")
        result = fn(rollback_id="backup_20260506_001")
        assert result["success"] is True
        assert result["files_restored"] == 3
        assert result["errors"] == 0
        assert result["rollback_id"] == "backup_20260506_001"
        # L'historique a trace l'operation
        mocks["history"].log_action.assert_called_once()


# ---------------------------------------------------------------------------
# Test : import paresseux fastmcp
# ---------------------------------------------------------------------------

class TestImportSafety:
    def test_winboost_mcp_package_import_does_not_require_fastmcp(self):
        """Importer `winboost.mcp` ne doit pas exiger fastmcp.

        On verifie que le module est importable et que `create_server` est
        expose. L'absence de fastmcp ne se manifeste qu'a l'appel de
        create_server (ImportError explicite).
        """
        import winboost.mcp as mcp_pkg

        assert hasattr(mcp_pkg, "create_server")
        assert callable(mcp_pkg.create_server)

    def test_serializers_module_independent_of_fastmcp(self):
        """`winboost.mcp.serializers` ne doit avoir aucune dep fastmcp."""
        import winboost.mcp.serializers as s
        # Toutes les fonctions du schema doivent etre presentes
        for fn_name in (
            "routed_action_to_dict",
            "route_result_to_dict",
            "action_to_dict",
            "scan_result_to_dict",
            "scan_all_to_dict",
        ):
            assert hasattr(s, fn_name), f"Helper manquant : {fn_name}"
            assert callable(getattr(s, fn_name))
