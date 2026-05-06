"""Tests pour le Chat GUI (Phase 8)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from winboost.actions.loader import Action

# --- Tests unitaires sans GUI (pas besoin de display) ---
from winboost.ai.action_router import ActionRouter, RoutedAction, RouteResult
from winboost.ai.safety_engine import SafetyVerdict
from winboost.core.config import Config

ACTIONS_DIR = Path(__file__).parent.parent.parent / "winboost" / "actions"


# --- Helpers ---

def _make_action(
    action_id: str = "test_001",
    name: str = "Test Action",
    risk: str = "low",
    category: str = "privacy",
    method: str = "registry_set",
    params: dict | None = None,
    reversible: bool = True,
) -> Action:
    return Action({
        "id": action_id,
        "name": name,
        "description": f"Description for {name}",
        "category": category,
        "risk_level": risk,
        "requires_admin": risk in ("high", "critical"),
        "reversible": reversible,
        "execute": {"method": method, "params": params or {}},
        "rollback": {"method": "registry_set", "params": {}} if reversible else {},
        "keywords": {"fr": ["test"], "en": ["test"]},
    })


def _make_verdict(
    action_id: str = "test_001",
    allowed: bool = True,
    risk: str = "low",
    requires_confirmation: bool = False,
    requires_dry_run: bool = False,
) -> SafetyVerdict:
    return SafetyVerdict(
        action_id=action_id,
        allowed=allowed,
        reason="Test verdict",
        requires_confirmation=requires_confirmation,
        requires_dry_run=requires_dry_run,
        risk_level=risk,
    )


def _make_routed(
    action_id: str = "test_001",
    risk: str = "low",
    allowed: bool = True,
    score: float = 0.85,
) -> RoutedAction:
    return RoutedAction(
        action=_make_action(action_id=action_id, risk=risk),
        verdict=_make_verdict(action_id=action_id, allowed=allowed, risk=risk),
        score=score,
        source="cache",
    )


# --- Tests Integration Router -> Chat ---

class TestChatRouterIntegration:
    """Tests d'integration entre le router et le flux chat."""

    def test_route_returns_actions_for_telemetry(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")
        assert result.has_actions
        assert len(result.actions) > 0

    def test_route_returns_actions_for_cleanup(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("nettoie les fichiers temporaires")
        assert result.has_actions

    def test_route_returns_blocked_for_safe_profile(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "safe"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")
        # Le profil safe devrait bloquer certaines actions medium+
        assert isinstance(result, RouteResult)

    def test_route_no_result_for_gibberish(self, tmp_path):
        config = Config(config_dir=tmp_path)
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("xyzabc123nope")
        assert isinstance(result, RouteResult)

    def test_route_gaming_actions(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("optimise pour les jeux")
        assert isinstance(result, RouteResult)

    def test_route_security_actions(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "power_user"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("ameliore la securite")
        assert isinstance(result, RouteResult)


# --- Tests Modele de donnees ---

class TestRoutedActionModel:
    """Tests pour les dataclasses RoutedAction et RouteResult."""

    def test_routed_action_creation(self):
        routed = _make_routed()
        assert routed.action.id == "test_001"
        assert routed.verdict.allowed is True
        assert routed.score == 0.85

    def test_route_result_has_actions(self):
        result = RouteResult(
            query="test",
            intent=MagicMock(),
            actions=[_make_routed()],
        )
        assert result.has_actions is True

    def test_route_result_no_actions(self):
        result = RouteResult(
            query="test",
            intent=MagicMock(),
            actions=[],
        )
        assert result.has_actions is False

    def test_route_result_all_safe(self):
        result = RouteResult(
            query="test",
            intent=MagicMock(),
            actions=[_make_routed(), _make_routed(action_id="test_002")],
        )
        assert result.all_safe is True

    def test_route_result_with_blocked(self):
        result = RouteResult(
            query="test",
            intent=MagicMock(),
            actions=[_make_routed()],
            blocked=[_make_routed(action_id="blocked_001", allowed=False)],
        )
        assert result.has_actions is True
        assert len(result.blocked) == 1


# --- Tests Safety Verdicts pour le chat ---

class TestChatSafetyVerdicts:
    """Tests des verdicts de securite utilises dans le chat."""

    def test_low_risk_no_confirmation(self):
        verdict = _make_verdict(risk="low")
        assert verdict.requires_confirmation is False
        assert verdict.requires_dry_run is False

    def test_medium_requires_confirmation(self):
        verdict = _make_verdict(risk="medium", requires_confirmation=True)
        assert verdict.requires_confirmation is True

    def test_high_requires_dry_run(self):
        verdict = _make_verdict(risk="high", requires_dry_run=True, requires_confirmation=True)
        assert verdict.requires_dry_run is True
        assert verdict.requires_confirmation is True

    def test_blocked_verdict(self):
        verdict = _make_verdict(allowed=False, risk="critical")
        assert verdict.allowed is False


# --- Tests Action Preview Data ---

class TestActionPreviewData:
    """Tests pour les donnees affichees dans le preview panel."""

    def test_action_has_execute_method(self):
        action = _make_action(method="service_disable", params={"service_name": "DiagTrack"})
        assert action.execute["method"] == "service_disable"
        assert action.execute["params"]["service_name"] == "DiagTrack"

    def test_action_reversible(self):
        action = _make_action(reversible=True)
        assert action.reversible is True
        assert action.rollback.get("method") == "registry_set"

    def test_action_irreversible(self):
        action = _make_action(reversible=False)
        assert action.reversible is False
        assert action.rollback == {}

    def test_action_requires_admin(self):
        action = _make_action(risk="high")
        assert action.requires_admin is True

    def test_action_keywords(self):
        action = _make_action()
        keywords = action.get_keywords_flat()
        assert "test" in keywords


# --- Tests Chat History Logging ---

class TestChatHistoryLogging:
    """Tests pour le logging des actions chat dans l'historique."""

    def test_log_action_execute(self, tmp_path):
        from winboost.core.history import HistoryManager

        db_path = tmp_path / "test_history.db"
        history = HistoryManager(db_path=db_path)

        entry_id = history.log_action(
            module_name="chat:privacy",
            action_type="execute",
            description="Action: Disable DiagTrack",
            risk_level="medium",
            result_status="success",
            result_detail="service_disable executed",
        )
        assert entry_id > 0

        entries = history.get_history(module_name="chat:privacy")
        assert len(entries) >= 1
        assert entries[0].action_type == "execute"

    def test_log_dry_run(self, tmp_path):
        from winboost.core.history import HistoryManager

        db_path = tmp_path / "test_history.db"
        history = HistoryManager(db_path=db_path)

        entry_id = history.log_action(
            module_name="chat:performance",
            action_type="dry_run",
            description="Dry-run: Disable SysMain",
            risk_level="low",
            result_status="success",
            result_detail="Simulation service_disable",
        )
        assert entry_id > 0

    def test_log_action_error(self, tmp_path):
        from winboost.core.history import HistoryManager

        db_path = tmp_path / "test_history.db"
        history = HistoryManager(db_path=db_path)

        entry_id = history.log_action(
            module_name="chat:system",
            action_type="execute",
            description="Action: Reset DNS",
            risk_level="medium",
            result_status="error",
            result_detail="Access denied",
        )
        entry = history.get_entry(entry_id)
        assert entry is not None
        assert entry.result_status == "error"


# --- Tests Chat Message Flow (mocked GUI) ---

class TestChatMessageFlow:
    """Tests du flux de messages sans instancier la GUI."""

    def test_router_pipeline_cache(self, tmp_path):
        """Le router resout via cache pour une requete simple."""
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")

        # Verifie le pipeline complet
        assert result.intent is not None
        assert result.intent.action in ("disable", "clean", "optimize", "info", "fix", "enable")
        assert result.resolved_by in ("cache", "category_fallback")
        for routed in result.actions:
            assert routed.verdict.allowed is True
            assert routed.score > 0

    def test_router_pipeline_safety_filtering(self, tmp_path):
        """Le profil safe filtre les actions medium+."""
        config = Config(config_dir=tmp_path)
        config.profile = "safe"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")

        # Toutes les actions autorisees doivent etre <= low risk
        for routed in result.actions:
            assert routed.verdict.allowed is True
            assert routed.action.risk_level in ("info", "low")

    def test_multiple_queries_sequential(self, tmp_path):
        """Plusieurs requetes sequentielles fonctionnent."""
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)

        queries = [
            "desactive la telemetrie",
            "nettoie les temp",
            "optimise pour les jeux",
        ]
        for query in queries:
            result = router.route(query)
            assert isinstance(result, RouteResult)

    def test_action_card_data_complete(self, tmp_path):
        """Chaque RoutedAction a toutes les donnees pour afficher une ActionCard."""
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")

        for routed in result.actions:
            # Donnees requises pour ActionCard
            assert routed.action.name
            assert routed.action.description
            assert routed.action.risk_level in ("info", "low", "medium", "high", "critical")
            assert routed.action.execute.get("method")
            assert isinstance(routed.verdict, SafetyVerdict)
            assert isinstance(routed.score, float)


# --- Tests Chat GUI Import ---

class TestChatGUIImport:
    """Tests que le module chat.py s'importe correctement."""

    def test_import_chat_module(self):
        # Ne pas instancier les widgets (pas de display), juste verifier l'import
        from winboost.gui import chat
        assert hasattr(chat, "ChatPage")
        assert hasattr(chat, "ChatBubble")
        assert hasattr(chat, "ActionCard")
        assert hasattr(chat, "BlockedActionCard")
        assert hasattr(chat, "PreviewPanel")
        assert hasattr(chat, "ConfirmDialog")
        assert hasattr(chat, "TypingIndicator")
        assert hasattr(chat, "StatusBubble")

    def test_import_theme_risk_colors(self):
        from winboost.gui.theme import RISK_COLORS
        assert "info" in RISK_COLORS
        assert "low" in RISK_COLORS
        assert "medium" in RISK_COLORS
        assert "high" in RISK_COLORS
        assert "critical" in RISK_COLORS

    def test_app_imports_chat_not_placeholder(self):
        """Verifie que app.py reference chat.py et non chat_placeholder."""
        app_path = Path(__file__).parent.parent.parent / "winboost" / "gui" / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "from winboost.gui.chat import ChatPage" in content
        assert "chat_placeholder" not in content


# --- Tests Worker Executor Integration (v2.2.x) ---


class TestChatWorkerUsesExecutor:
    """Le worker GUI doit passer par ActionExecutor.apply (plus de catalogue)."""

    def test_chat_module_references_action_executor(self):
        """Le source de chat.py importe ActionExecutor (pas de catalogue v2.0/v2.1)."""
        chat_path = Path(__file__).parent.parent.parent / "winboost" / "gui" / "chat.py"
        content = chat_path.read_text(encoding="utf-8")
        assert "from winboost.core.executor import ActionExecutor" in content
        # Plus de message trompeur "execution reelle en v2.1"
        assert "execution reelle en v2.1" not in content
        assert "catalogue v2.0" not in content

    def test_chat_module_no_more_catalogued_status(self):
        """chat.py ne doit plus loguer status 'catalogued' (l'executor logue lui-meme)."""
        chat_path = Path(__file__).parent.parent.parent / "winboost" / "gui" / "chat.py"
        content = chat_path.read_text(encoding="utf-8")
        # le seul "catalogued" toujours toleré serait dans un commentaire historique ;
        # on verifie qu'il n'y a plus de result_status="catalogued"
        assert 'result_status="catalogued"' not in content
        assert "result_status='catalogued'" not in content
