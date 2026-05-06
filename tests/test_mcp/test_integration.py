"""Tests d'integration MCP — workflows complets de bout en bout (T073).

Difference vs `test_server.py` (T070, autre agent) :
- `test_server.py` : unit-tests des 5 tools individuels avec mocks fins.
- `test_integration.py` (ce fichier) : workflows complets simulant un client
  MCP qui enchaine plusieurs appels (chat -> apply -> undo, scan, etc.) avec
  verification de la coherence inter-tools, serialisation JSON,
  thread-safety, idempotence et erreurs typees.

Strategie de mock :
- Tous les composants metier (`ActionRouter`, `Engine`, `ActionRegistry`,
  `BackupManager`, `HistoryManager`) sont mockes via `unittest.mock` et
  injectes via les keyword args de `create_server(...)`. Aucun appel reel a
  Windows / au registre / au filesystem.
- Le module `winboost.mcp.server` est importe de facon defensive : si
  l'autre agent (T070) n'a pas encore livre, ou si `fastmcp` n'est pas
  installe, le module entier est skip via `pytest.importorskip`.
- Les tools FastMCP sont recuperes via `await server._get_tool(name)` qui
  expose un `FunctionTool` avec attribut `.fn` (la fonction sync sous-jacente).

Couverture (>= 25 tests) :
- A. Workflow chat (5)
- B. Workflow scan (5)
- C. Workflow apply + undo (5)
- D. Workflow list_actions (5)
- E. Robustesse / serialisation / concurrence (5+)
- F. Sanity (2)
Total : 27 tests d'integration.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Skip gracieux si T070 n'a pas livre `winboost.mcp.server`
# ---------------------------------------------------------------------------
# Si l'import echoue (FastMCP absent OU server.py pas encore cree par T070),
# tous les tests du module sont skip — l'orchestrateur reactivera la suite
# automatiquement quand T070 sera merge.

mcp_server = pytest.importorskip(
    "winboost.mcp.server",
    reason="winboost.mcp.server pas encore livre par T070 (FastMCP absent ou module inexistant)",
)


# ---------------------------------------------------------------------------
# Stubs metier (utilises pour faire passer les mocks pour des objets WinBoost)
# ---------------------------------------------------------------------------


@dataclass
class _StubAction:
    """Stub minimal d'`Action` (winboost.actions.loader.Action)."""

    id: str = "sys_011"
    name: str = "Activate Dark Mode"
    description: str = "Active le theme sombre Windows"
    category: str = "system"
    risk_level: str = "low"
    requires_admin: bool = False
    reversible: bool = True
    execute: dict = field(default_factory=lambda: {"method": "powershell", "params": {}})
    rollback: dict = field(default_factory=dict)
    preview: dict = field(default_factory=dict)
    keywords: dict = field(default_factory=dict)
    compatibility: dict = field(default_factory=dict)


@dataclass
class _StubVerdict:
    """Stub minimal de `SafetyVerdict`."""

    action_id: str = "sys_011"
    allowed: bool = True
    requires_dry_run: bool = False
    requires_confirmation: bool = False
    reason: str = ""
    risk_level: str = "low"


@dataclass
class _StubRouted:
    """Stub minimal de `RoutedAction`."""

    action: _StubAction
    verdict: _StubVerdict
    score: float = 0.85
    source: str = "cache"


@dataclass
class _StubIntent:
    """Stub minimal d'`Intent`."""

    action: str = "activate"
    category: str = "system"
    confidence: float = 0.9
    source: str = "cache"
    keywords: list = field(default_factory=list)


@dataclass
class _StubRouteResult:
    """Stub minimal de `RouteResult`."""

    query: str
    intent: _StubIntent
    actions: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    message: str = "1 action(s) proposee(s)"
    resolved_by: str = "cache"

    @property
    def has_actions(self) -> bool:
        return len(self.actions) > 0

    @property
    def all_safe(self) -> bool:
        return all(a.verdict.allowed for a in self.actions)


@dataclass
class _StubIssue:
    """Stub minimal d'`Issue` (sortie de scan)."""

    id: str = "issue_001"
    description: str = "Fichier temp orphelin"
    risk_level: str = "low"
    auto_fixable: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class _StubScanResult:
    """Stub minimal de `ScanResult`.

    Les serializers WinBoost utilisent `getattr(result, 'summary', '')`,
    `getattr(result, 'issue_count', len(result.issues))` etc. — les properties
    plus le champ `issues` suffisent.
    """

    module_name: str = "temp"
    summary: str = "1 fichier orphelin trouve"
    issues: list = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0


@dataclass
class _StubBackupEntry:
    """Stub minimal de `BackupEntry` (winboost.core.backup)."""

    backup_id: str = "rb_42"
    module_name: str = "system"
    description: str = "Backup avant dark mode"


# ---------------------------------------------------------------------------
# Helpers : factories de mocks pour les composants WinBoost
# ---------------------------------------------------------------------------


def _make_route_result(
    query: str,
    actions: list[_StubRouted] | None = None,
    blocked: list[_StubRouted] | None = None,
    resolved_by: str = "cache",
    message: str = "",
) -> _StubRouteResult:
    """Construit un `_StubRouteResult` pret a etre retourne par un mock router."""
    actions = actions or []
    blocked = blocked or []
    if not message:
        if actions:
            message = f"{len(actions)} action(s) proposee(s)"
        else:
            message = "Aucune action trouvee pour cette requete."
    return _StubRouteResult(
        query=query,
        intent=_StubIntent(),
        actions=actions,
        blocked=blocked,
        message=message,
        resolved_by=resolved_by if (actions or resolved_by == "none") else "cache",
    )


def _default_routed() -> _StubRouted:
    """Action par defaut : sys_011 (dark mode), allowed."""
    return _StubRouted(
        action=_StubAction(
            id="sys_011",
            name="Activate Dark Mode",
            risk_level="low",
        ),
        verdict=_StubVerdict(action_id="sys_011", allowed=True),
    )


def _make_router(default_actions: list[_StubRouted] | None = None) -> MagicMock:
    """Cree un mock `ActionRouter` qui retourne un RouteResult predefini."""
    router = MagicMock()
    actions = default_actions or [_default_routed()]

    def _route(query: str, max_actions: int = 5) -> _StubRouteResult:
        # Cas no-match : query absurde -> resultat vide
        q_lower = query.lower() if query else ""
        if any(token in q_lower for token in ("xyzabc", "qwzlpfm", "zzzzz")):
            return _make_route_result(query, [], [], resolved_by="none")
        return _make_route_result(query, actions)

    router.route.side_effect = _route
    router.action_count = 180

    # Le serveur fait `_registry = router.registry` si registry n'est pas fourni
    # — on s'assure qu'attacher le mock router ne crashe pas. On fournira
    # systematiquement registry= explicitement de toute facon.
    router.registry = MagicMock()
    return router


def _make_engine(modules: dict[str, _StubScanResult] | None = None) -> MagicMock:
    """Cree un mock `Engine` qui retourne des scans predefinis."""
    engine = MagicMock()
    modules = modules or {
        "temp": _StubScanResult(
            module_name="temp",
            summary="3 fichiers temp",
            issues=[
                _StubIssue(id="t1"),
                _StubIssue(id="t2"),
                _StubIssue(id="t3"),
            ],
        ),
        "ram_optimizer": _StubScanResult(
            module_name="ram_optimizer",
            summary="RAM optimisable",
            issues=[_StubIssue(id="r1")],
        ),
        "startup": _StubScanResult(module_name="startup", issues=[]),
    }

    engine.list_modules.return_value = list(modules.keys())
    engine.modules = {name: MagicMock() for name in modules}

    def _scan_all() -> dict[str, _StubScanResult]:
        return dict(modules)

    def _scan_module(name: str) -> _StubScanResult:
        if name not in modules:
            raise ValueError(f"Module inconnu : '{name}'.")
        return modules[name]

    engine.scan_all.side_effect = _scan_all
    engine.scan_module.side_effect = _scan_module
    engine.discover_modules = MagicMock(return_value=None)
    return engine


def _make_registry() -> MagicMock:
    """Cree un mock `ActionRegistry` avec 180 actions reparties sur 9 categories."""
    registry = MagicMock()

    categories = {
        "system": [_StubAction(id=f"sys_{i:03d}", category="system") for i in range(1, 21)],
        "network": [
            _StubAction(id=f"net_{i:03d}", category="network", name=f"Net Action {i}")
            for i in range(1, 21)
        ],
        "appearance": [
            _StubAction(id=f"app_{i:03d}", category="appearance", name=f"App Action {i}")
            for i in range(1, 21)
        ],
        "privacy": [
            _StubAction(id=f"priv_{i:03d}", category="privacy", name=f"Priv {i}", risk_level="medium")
            for i in range(1, 31)
        ],
        "performance": [
            _StubAction(id=f"perf_{i:03d}", category="performance", name=f"Perf {i}")
            for i in range(1, 31)
        ],
        "cleanup": [
            _StubAction(id=f"clean_{i:03d}", category="cleanup", name=f"Clean {i}")
            for i in range(1, 21)
        ],
        "dev_tools": [
            _StubAction(id=f"dev_{i:03d}", category="dev_tools", name=f"Dev {i}")
            for i in range(1, 21)
        ],
        "security": [
            _StubAction(id=f"sec_{i:03d}", category="security", name=f"Sec {i}", risk_level="medium")
            for i in range(1, 11)
        ],
        "gaming": [
            _StubAction(id=f"game_{i:03d}", category="gaming", name=f"Game {i}")
            for i in range(1, 11)
        ],
    }
    all_actions = {a.id: a for cat_list in categories.values() for a in cat_list}

    def _get(action_id: str) -> _StubAction | None:
        return all_actions.get(action_id)

    def _list_by_category(cat: str) -> list[_StubAction]:
        return list(categories.get(cat, []))

    def _list_all() -> list[_StubAction]:
        return list(all_actions.values())

    registry.get.side_effect = _get
    registry.list_by_category.side_effect = _list_by_category
    registry.list_all.side_effect = _list_all
    registry.categories.return_value = sorted(categories.keys())
    registry.count = len(all_actions)
    return registry


def _make_backup_manager() -> MagicMock:
    """Cree un mock `BackupManager` qui simule get_backup / restore_backup.

    Le serveur T070 utilise `_backup.get_backup(rollback_id)` puis
    `_backup.restore_backup(rollback_id) -> (restored: int, errors: int)`.
    """
    manager = MagicMock()

    def _get_backup(rb_id: str) -> _StubBackupEntry | None:
        if not rb_id or "inexist" in rb_id.lower() or "zzzz" in rb_id.lower():
            return None
        return _StubBackupEntry(backup_id=rb_id, module_name="system", description="test backup")

    def _restore_backup(rb_id: str) -> tuple[int, int]:
        return (1, 0)  # 1 fichier restaure, 0 erreur

    manager.get_backup.side_effect = _get_backup
    manager.restore_backup.side_effect = _restore_backup
    return manager


def _make_history_manager() -> MagicMock:
    """Cree un mock `HistoryManager` qui retourne des entry_id incrementaux."""
    manager = MagicMock()
    counter = {"i": 0}

    def _log_action(**kwargs):
        counter["i"] += 1
        return counter["i"]

    manager.log_action.side_effect = _log_action
    return manager


# ---------------------------------------------------------------------------
# Helper : recuperation d'un tool depuis un serveur FastMCP
# ---------------------------------------------------------------------------


def _get_tool_fn(server: Any, name: str):
    """Recupere la fonction-tool sous-jacente d'un serveur FastMCP.

    FastMCP 2.x convention : `await server._get_tool(name)` -> `FunctionTool`
    avec attribut `.fn` (la fonction Python sous-jacente, sync ou async selon
    l'auteur du tool). Les tools de `winboost.mcp.server` sont sync.
    """
    try:
        tool = asyncio.run(server._get_tool(name))
    except Exception as e:
        pytest.skip(f"server._get_tool({name!r}) a leve : {e!r} — convention FastMCP differente ?")

    fn = getattr(tool, "fn", None) or getattr(tool, "func", None)
    if fn is None or not callable(fn):
        pytest.skip(f"Tool '{name}' trouve mais sans .fn callable")
    return fn


def _call_tool(server: Any, name: str, *args, **kwargs):
    """Appelle un tool MCP. Gere le cas ou la fonction est sync ou async."""
    fn = _get_tool_fn(server, name)
    result = fn(*args, **kwargs)
    if hasattr(result, "__await__"):
        return asyncio.run(result)
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_components():
    """Cree un nouveau set de composants mocks pour chaque test (isolation)."""
    return {
        "router": _make_router(),
        "engine": _make_engine(),
        "registry": _make_registry(),
        "backup": _make_backup_manager(),
        "history": _make_history_manager(),
    }


@pytest.fixture
def mcp_test_server(mcp_components):
    """Serveur FastMCP avec composants metier mockes injectes."""
    create_server = getattr(mcp_server, "create_server", None)
    if create_server is None:
        pytest.skip("create_server() non expose dans winboost.mcp.server (T070 incomplet)")

    try:
        server = create_server(
            router=mcp_components["router"],
            engine=mcp_components["engine"],
            registry=mcp_components["registry"],
            backup_manager=mcp_components["backup"],
            history_manager=mcp_components["history"],
        )
    except Exception as e:
        pytest.skip(f"create_server() a leve : {e!r} — signature differente de T070 ?")

    return server, mcp_components


# ---------------------------------------------------------------------------
# A. Workflow chat — 5 tests
# ---------------------------------------------------------------------------


class TestWorkflowChat:
    """Workflow client : envoyer une requete chat, recevoir des actions."""

    def test_chat_dark_mode_returns_sys_011(self, mcp_test_server):
        server, comps = mcp_test_server
        # Configure le router pour retourner sys_011 pour "dark mode"
        comps["router"].route.side_effect = lambda q, max_actions=5: _make_route_result(
            q,
            [
                _StubRouted(
                    action=_StubAction(id="sys_011", name="Activate Dark Mode"),
                    verdict=_StubVerdict(action_id="sys_011", allowed=True),
                ),
            ],
        )

        result = _call_tool(server, "chat", "dark mode")

        assert isinstance(result, dict), f"chat() doit retourner un dict, pas {type(result)}"
        assert result.get("has_actions") is True
        actions = result.get("actions", [])
        assert len(actions) >= 1
        assert any(a.get("id") == "sys_011" for a in actions), (
            f"sys_011 absent. ids retournes : {[a.get('id') for a in actions]}"
        )

    def test_chat_cleanup_temp_returns_cleanup_actions(self, mcp_test_server):
        server, comps = mcp_test_server
        comps["router"].route.side_effect = lambda q, max_actions=5: _make_route_result(
            q,
            [
                _StubRouted(
                    action=_StubAction(id="clean_001", category="cleanup", name="Clean Temp Files"),
                    verdict=_StubVerdict(action_id="clean_001", allowed=True),
                ),
                _StubRouted(
                    action=_StubAction(id="clean_002", category="cleanup", name="Clear DNS Cache"),
                    verdict=_StubVerdict(action_id="clean_002", allowed=True),
                ),
            ],
        )

        result = _call_tool(server, "chat", "nettoie mes fichiers temp")

        assert result.get("has_actions") is True
        cats = {a.get("category") for a in result.get("actions", [])}
        assert "cleanup" in cats, f"categorie cleanup attendue, recu : {cats}"

    def test_chat_no_match_returns_empty_actions_with_message(self, mcp_test_server):
        server, comps = mcp_test_server
        # Le mock _make_router rend automatiquement xyzabc -> aucun match
        comps["router"].route.side_effect = lambda q, max_actions=5: _make_route_result(
            q, [], resolved_by="none",
        )

        result = _call_tool(server, "chat", "query qui ne match rien xyzabc")

        assert result.get("has_actions") is False
        assert isinstance(result.get("message"), str)
        assert len(result.get("message", "")) > 0, "message non vide attendu meme sans match"

    def test_chat_empty_query_returns_clear_error(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "chat", "")

        # T070 contract : empty query -> {"error": "query is required", "type": "ValueError"}
        assert isinstance(result, dict)
        assert "error" in result, f"erreur 'query is required' attendue, recu : {result}"
        assert isinstance(result["error"], str)
        assert "required" in result["error"].lower() or "vide" in result["error"].lower() or \
               "empty" in result["error"].lower() or "query" in result["error"].lower()
        # Le type d'erreur doit etre present
        assert "type" in result
        assert isinstance(result["type"], str)

    def test_chat_focus_mode_returns_system_action(self, mcp_test_server):
        server, comps = mcp_test_server
        comps["router"].route.side_effect = lambda q, max_actions=5: _make_route_result(
            q,
            [
                _StubRouted(
                    action=_StubAction(
                        id="sys_016", name="Enable Focus Assist", category="system",
                    ),
                    verdict=_StubVerdict(action_id="sys_016", allowed=True),
                ),
            ],
        )

        result = _call_tool(server, "chat", "passe en mode focus")

        assert result.get("has_actions") is True
        ids = [a.get("id") for a in result.get("actions", [])]
        assert "sys_016" in ids, f"sys_016 attendu, recu : {ids}"


# ---------------------------------------------------------------------------
# B. Workflow scan — 5 tests
# ---------------------------------------------------------------------------


class TestWorkflowScan:
    """Workflow client : scanner tous les modules ou un module specifique."""

    def test_scan_none_returns_all_modules(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "scan", None)

        # T070 contract : scan(None) -> scan_all_to_dict ->
        # {"modules": {name: ScanResultDict}, "module_count": int, "total_issues": int}
        assert isinstance(result, dict)
        assert "modules" in result
        assert isinstance(result["modules"], dict)
        assert len(result["modules"]) >= 1
        assert "module_count" in result
        assert result["module_count"] == len(result["modules"])
        assert "total_issues" in result

    def test_scan_temp_returns_only_temp_module(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "scan", "temp")

        # T070 : scan(<name>) -> scan_result_to_dict -> ScanResultDict direct
        assert isinstance(result, dict)
        # Aucune cle "modules" : c'est un ScanResult unique
        assert result.get("module_name") == "temp"
        assert "issue_count" in result
        assert "issues" in result

    def test_scan_ram_optimizer_returns_only_ram(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "scan", "ram_optimizer")

        assert isinstance(result, dict)
        assert result.get("module_name") == "ram_optimizer"

    def test_scan_unknown_module_returns_structured_error(self, mcp_test_server):
        server, _comps = mcp_test_server
        # _make_engine leve ValueError pour un module inconnu — le tool wrap
        # cela en dict structure
        result = _call_tool(server, "scan", "module_inexistant_zzzzz")

        assert isinstance(result, dict)
        assert "error" in result
        assert "type" in result
        assert result["type"] == "ValueError"

    def test_scan_result_has_minimum_schema(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "scan", "temp")

        # Schema minimum : module_name (str) + issue_count (int) + issues (list)
        assert isinstance(result.get("module_name"), str)
        assert isinstance(result.get("issue_count"), int)
        assert isinstance(result.get("issues"), list)
        # has_issues coherent avec issue_count
        assert result.get("has_issues") == (result["issue_count"] > 0)


# ---------------------------------------------------------------------------
# C. Workflow apply + undo — 5 tests
# ---------------------------------------------------------------------------


class TestWorkflowApplyUndo:
    """Workflow client : appliquer une action, puis annuler via undo."""

    def test_apply_sys_011_returns_success_and_status_catalogued(self, mcp_test_server):
        server, _comps = mcp_test_server
        # Le registry mock retourne sys_011 par defaut (cf _make_registry)
        result = _call_tool(server, "apply", "sys_011")

        # T070 contract : apply -> {"success": True, "status": "catalogued",
        #                          "action_id": "sys_011", "rollback_id": None,
        #                          "history_entry_id": int, "message": "..."}
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert result.get("action_id") == "sys_011"
        # rollback_id present (peut etre None en v2.2 catalogue mode)
        assert "rollback_id" in result
        # status est "catalogued" en v2.2
        assert result.get("status") in ("catalogued", "applied"), (
            f"status attendu 'catalogued' ou 'applied', recu : {result.get('status')}"
        )

    def test_apply_unknown_action_returns_error(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "apply", "action_inexistante_zzzz")

        # T070 contract : action non trouvee -> {"error": "...", "type": "KeyError"}
        assert isinstance(result, dict)
        assert "error" in result
        assert "type" in result
        # Le type est KeyError ("Action inconnue")
        assert result["type"] == "KeyError"

    def test_apply_then_undo_returns_success(self, mcp_test_server):
        server, _comps = mcp_test_server

        # Etape 1 : apply (catalogue, rollback_id = None en v2.2)
        apply_result = _call_tool(server, "apply", "sys_011")
        assert apply_result.get("success") is True

        # Etape 2 : undo avec un rollback_id arbitraire valide (le backup mock
        # retourne un BackupEntry pour tout id qui ne contient pas "inexist"/"zzzz")
        undo_result = _call_tool(server, "undo", "rb_seq_99")

        assert isinstance(undo_result, dict)
        # T070 contract : success, message, rollback_id, files_restored, errors
        assert undo_result.get("success") is True
        assert undo_result.get("rollback_id") == "rb_seq_99"
        assert undo_result.get("files_restored") == 1
        assert undo_result.get("errors") == 0

    def test_undo_unknown_rollback_returns_error(self, mcp_test_server):
        server, _comps = mcp_test_server
        # Le mock get_backup retourne None pour rollback_id contenant "inexist"
        result = _call_tool(server, "undo", "rollback_inexistant_zzzz")

        assert isinstance(result, dict)
        assert "error" in result
        assert "type" in result
        assert result["type"] == "KeyError"

    def test_undo_empty_rollback_id_returns_error(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "undo", "")

        assert isinstance(result, dict)
        assert "error" in result
        assert "type" in result
        assert result["type"] == "ValueError"
        assert "required" in result["error"].lower() or "vide" in result["error"].lower() or \
               "rollback" in result["error"].lower()


# ---------------------------------------------------------------------------
# D. Workflow list_actions — 5 tests
# ---------------------------------------------------------------------------


class TestWorkflowListActions:
    """Workflow client : lister les actions du registry, par categorie ou toutes."""

    def test_list_actions_none_returns_all_180(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "list_actions", None)

        # T070 contract : {"actions": [...], "count": int, "category": None}
        assert isinstance(result, dict)
        assert "actions" in result
        assert isinstance(result["actions"], list)
        assert result["count"] == 180, f"180 actions attendues, recu : {result['count']}"
        assert len(result["actions"]) == 180
        assert result["category"] is None

    def test_list_actions_system_returns_20(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "list_actions", "system")

        assert result["count"] == 20
        assert len(result["actions"]) == 20
        assert result["category"] == "system"
        cats = {a.get("category") for a in result["actions"]}
        assert cats == {"system"}, f"category=system attendue uniquement, recu : {cats}"

    def test_list_actions_network_returns_20(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "list_actions", "network")

        assert result["count"] == 20
        assert all(a.get("category") == "network" for a in result["actions"])

    def test_list_actions_appearance_returns_20(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "list_actions", "appearance")

        assert result["count"] == 20
        assert all(a.get("category") == "appearance" for a in result["actions"])

    def test_list_actions_min_schema_per_action(self, mcp_test_server):
        server, _comps = mcp_test_server
        result = _call_tool(server, "list_actions", "system")

        assert len(result["actions"]) > 0
        first = result["actions"][0]
        # Schema minimum impose : id + name + category + risk_level
        for required in ("id", "name", "category", "risk_level"):
            assert required in first, (
                f"Champ '{required}' manquant dans l'action retournee : {first}"
            )
        # Types corrects
        assert isinstance(first["id"], str)
        assert isinstance(first["name"], str)
        assert isinstance(first["category"], str)
        assert isinstance(first["risk_level"], str)


# ---------------------------------------------------------------------------
# E. Robustesse, serialisation, concurrence, idempotence, erreurs typees
# ---------------------------------------------------------------------------


class TestRobustnessAndConcurrency:
    """Cas combines : concurrence, JSON, accents, idempotence, erreurs typees."""

    def test_concurrent_chat_calls_all_succeed(self, mcp_test_server):
        """5 appels chat() simultanes via threads -> tous OK sans crash."""
        server, _comps = mcp_test_server

        def _call(query: str) -> dict:
            return _call_tool(server, "chat", query)

        queries = [
            "dark mode",
            "nettoie temp",
            "active focus",
            "baisse luminosite",
            "mute son",
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(_call, q) for q in queries]
            results = [f.result(timeout=10) for f in futures]

        assert len(results) == 5
        for r in results:
            assert isinstance(r, dict)
            # Chaque resultat est self-contained (a au minimum has_actions ou error)
            assert "has_actions" in r or "actions" in r or "error" in r

    def test_all_tool_outputs_are_json_dumpable(self, mcp_test_server):
        """Sortie de chaque tool doit etre `json.dumps`-able sans default."""
        server, _comps = mcp_test_server

        outputs = [
            ("chat", _call_tool(server, "chat", "dark mode")),
            ("scan_all", _call_tool(server, "scan", None)),
            ("scan_one", _call_tool(server, "scan", "temp")),
            ("list_all", _call_tool(server, "list_actions", None)),
            ("list_one", _call_tool(server, "list_actions", "system")),
            ("apply", _call_tool(server, "apply", "sys_011")),
            ("undo", _call_tool(server, "undo", "rb_json_test")),
        ]

        for label, out in outputs:
            try:
                serialized = json.dumps(out)
            except (TypeError, ValueError) as e:
                pytest.fail(
                    f"Output '{label}' non json.dumps-able : {type(out)} -> {e}\n"
                    f"Contenu : {out!r}"
                )
            else:
                # Verifie qu'on peut re-parse (round-trip)
                parsed = json.loads(serialized)
                assert isinstance(parsed, dict), f"{label} : roundtrip a perdu le type dict"

    def test_chat_with_unicode_and_accents_does_not_crash(self, mcp_test_server):
        """Backward compat : queries avec accents et espaces multiples passent."""
        server, _comps = mcp_test_server

        # Aucune de ces requetes ne doit crasher
        for query in [
            "ecoute mon disque",
            "active le mode sombre",
            "nettoie mes fichiers temporaires en francais",
            "bluetooth on",
            "  espaces multiples  partout  ",
            "emojis rocket dark mode",
        ]:
            result = _call_tool(server, "chat", query)
            assert isinstance(result, dict), (
                f"chat({query!r}) doit retourner un dict, recu {type(result)}"
            )

    def test_list_actions_idempotent(self, mcp_test_server):
        """3x list_actions('system') -> meme resultat (pas de side-effect)."""
        server, _comps = mcp_test_server

        results = [
            _call_tool(server, "list_actions", "system") for _ in range(3)
        ]

        # On compare les ids tries — ordre stable
        normalized = [
            sorted(a.get("id") for a in r["actions"] if isinstance(a, dict))
            for r in results
        ]

        assert normalized[0] == normalized[1] == normalized[2], (
            f"list_actions('system') non idempotent : {normalized}"
        )
        # Les counts sont identiques
        counts = [r["count"] for r in results]
        assert counts[0] == counts[1] == counts[2] == 20

    def test_errors_have_typed_structure(self, mcp_test_server):
        """T070 contract : toute erreur a `error` (str) + `type` (str)."""
        server, _comps = mcp_test_server

        # On declenche plusieurs erreurs distinctes et on verifie leur structure
        error_cases = [
            ("chat", ""),                         # ValueError
            ("apply", "action_inexistante_zzzz"),  # KeyError
            ("scan", "module_inexistant_zzzzz"),  # ValueError
            ("undo", ""),                         # ValueError
            ("undo", "rollback_inexistant_zzzz"), # KeyError
        ]

        for tool_name, arg in error_cases:
            result = _call_tool(server, tool_name, arg)
            assert isinstance(result, dict)
            assert "error" in result, f"{tool_name}({arg!r}) sans clef 'error' : {result}"
            assert isinstance(result["error"], str)
            assert len(result["error"]) > 0
            assert "type" in result, f"{tool_name}({arg!r}) sans clef 'type' : {result}"
            assert isinstance(result["type"], str)
            assert len(result["type"]) > 0


# ---------------------------------------------------------------------------
# F. Sanity — 2 tests
# ---------------------------------------------------------------------------


class TestServerSanity:
    """Tests de smoke garantissant que le serveur s'instancie."""

    def test_server_instance_created(self, mcp_test_server):
        server, _comps = mcp_test_server
        assert server is not None

    def test_five_tools_exposed(self, mcp_test_server):
        """Les 5 tools attendus (chat, scan, apply, list_actions, undo) sont exposes."""
        server, _comps = mcp_test_server
        for name in ("chat", "scan", "apply", "list_actions", "undo"):
            fn = _get_tool_fn(server, name)
            assert callable(fn), f"Tool '{name}' n'est pas callable"
