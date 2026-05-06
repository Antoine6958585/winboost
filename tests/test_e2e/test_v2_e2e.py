"""Tests E2E — v2.0 complet (Chat + Profils + History + Settings + Actions)."""

from pathlib import Path

from click.testing import CliRunner

from winboost.actions.loader import ActionRegistry
from winboost.ai.action_router import ActionRouter, RouteResult
from winboost.cli.main import cli
from winboost.core.backup import BackupManager
from winboost.core.config import Config
from winboost.core.history import HistoryManager

ACTIONS_DIR = Path(__file__).parent.parent.parent / "winboost" / "actions"
runner = CliRunner()


# =========================================================================
# E2E Chat Pipeline
# =========================================================================

class TestChatPipelineE2E:
    """Pipeline complet : requete -> NLParser -> Cache -> Safety -> Result."""

    def test_full_pipeline_telemetry(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")

        assert result.has_actions
        assert result.intent.action == "disable"
        assert result.intent.category == "privacy"
        for routed in result.actions:
            assert routed.action.category == "privacy"
            assert routed.verdict.allowed is True

    def test_full_pipeline_cleanup(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("nettoie les fichiers temporaires")

        assert result.has_actions
        assert result.intent.action in ("clean", "optimize")  # Parser peut matcher les deux

    def test_full_pipeline_gaming(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("optimise pour les jeux")

        assert isinstance(result, RouteResult)
        assert result.intent.category == "gaming"

    def test_pipeline_safe_profile_blocks(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "safe"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")

        # Safe ne devrait autoriser que les low
        for routed in result.actions:
            assert routed.action.risk_level in ("info", "low")

    def test_pipeline_power_user_profile(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "power_user"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")

        for routed in result.actions:
            assert routed.action.risk_level in ("info", "low", "medium")

    def test_pipeline_returns_scores(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")

        for routed in result.actions:
            assert 0.0 <= routed.score <= 1.0


# =========================================================================
# E2E CLI Chat
# =========================================================================

class TestCLIChatE2E:
    """Tests E2E de la commande chat CLI."""

    def test_chat_telemetry(self):
        result = runner.invoke(cli, ["chat", "desactive", "la", "telemetrie"])
        assert result.exit_code == 0
        assert "action(s)" in result.output

    def test_chat_cleanup(self):
        result = runner.invoke(cli, ["chat", "nettoie", "les", "temp"])
        assert result.exit_code == 0

    def test_chat_gaming(self):
        result = runner.invoke(cli, ["chat", "optimise", "pour", "les", "jeux"])
        assert result.exit_code == 0

    def test_chat_security(self):
        result = runner.invoke(cli, ["chat", "ameliore", "la", "securite"])
        assert result.exit_code == 0

    def test_chat_privacy(self):
        result = runner.invoke(cli, ["chat", "protege", "ma", "vie", "privee"])
        assert result.exit_code == 0

    def test_chat_unknown_query(self):
        result = runner.invoke(cli, ["chat", "xyzabc123"])
        assert result.exit_code == 0


# =========================================================================
# E2E Actions Registry
# =========================================================================

class TestActionsRegistryE2E:
    """Tests E2E du registre d'actions complet."""

    def test_load_160_actions(self):
        registry = ActionRegistry(actions_dir=ACTIONS_DIR)
        count = registry.load_all()
        assert count == 160  # 150 v2.0 + 10 v2.1 native

    def test_9_categories(self):
        registry = ActionRegistry(actions_dir=ACTIONS_DIR)
        registry.load_all()
        cats = registry.categories()
        assert len(cats) == 9
        expected = {
            "privacy", "performance", "cleanup", "dev_tools",
            "network", "security", "appearance", "gaming", "system",
        }
        assert set(cats) == expected

    def test_all_actions_have_keywords(self):
        registry = ActionRegistry(actions_dir=ACTIONS_DIR)
        registry.load_all()
        for action in registry.list_all():
            keywords = action.get_keywords_flat()
            assert len(keywords) > 0, f"Action {action.id} sans keywords"

    def test_no_validation_errors(self):
        registry = ActionRegistry(actions_dir=ACTIONS_DIR)
        registry.load_all()
        assert len(registry.errors) == 0


# =========================================================================
# E2E Profils
# =========================================================================

class TestProfilesE2E:
    """Tests E2E du systeme de profils."""

    def test_profile_switch_and_persist(self, tmp_path):
        config = Config(config_dir=tmp_path)
        assert config.profile == "safe"

        config.profile = "expert"
        config.save()

        config2 = Config(config_dir=tmp_path)
        assert config2.profile == "expert"
        assert config2.max_risk == "high"

    def test_profile_affects_routing(self, tmp_path):
        """Le profil affecte directement les actions autorisees."""
        # Safe
        config_safe = Config(config_dir=tmp_path / "safe")
        config_safe.profile = "safe"
        router_safe = ActionRouter(config=config_safe, actions_dir=ACTIONS_DIR)
        result_safe = router_safe.route("desactive la telemetrie")

        # Expert
        config_expert = Config(config_dir=tmp_path / "expert")
        config_expert.profile = "expert"
        router_expert = ActionRouter(config=config_expert, actions_dir=ACTIONS_DIR)
        result_expert = router_expert.route("desactive la telemetrie")

        # Expert devrait avoir plus ou autant d'actions que safe
        safe_total = len(result_safe.actions) + len(result_safe.blocked)
        expert_total = len(result_expert.actions) + len(result_expert.blocked)
        assert expert_total >= safe_total
        assert len(result_expert.actions) >= len(result_safe.actions)


# =========================================================================
# E2E History + Undo
# =========================================================================

class TestHistoryUndoE2E:
    """Tests E2E integration history + backup + undo."""

    def test_full_undo_workflow(self, tmp_path):
        """Workflow complet : action -> log -> modify -> undo -> verify."""
        backup_mgr = BackupManager(backup_dir=tmp_path / "backups")
        history = HistoryManager(db_path=tmp_path / "h.db")

        # Fichier cible
        target = tmp_path / "data.txt"
        target.write_text("original")

        # 1. Backup avant action
        entry = backup_mgr.create_backup("chat:privacy", "Before disable", [str(target)])
        assert entry is not None

        # 2. Log l'action
        history.log_action(
            module_name="chat:privacy",
            action_type="execute",
            description="Disable DiagTrack",
            risk_level="medium",
            result_status="success",
            backup_id=entry.backup_id,
        )

        # 3. Simule la modification
        target.write_text("modified")

        # 4. Undo
        restored, errors = backup_mgr.restore_backup(entry.backup_id)
        assert restored == 1
        assert errors == 0

        # 5. Log l'undo
        history.log_action(
            module_name="undo_manager",
            action_type="restore",
            description=f"Undo {entry.backup_id}",
            risk_level="medium",
            result_status="success",
            backup_id=entry.backup_id,
        )

        # 6. Verifie
        assert target.read_text() == "original"
        all_entries = history.get_history()
        assert len(all_entries) == 2
        assert all_entries[0].action_type == "restore"

    def test_history_filters(self, tmp_path):
        history = HistoryManager(db_path=tmp_path / "h.db")

        # Ajoute plusieurs types
        history.log_action("chat:privacy", "execute", "a1", "medium", "success")
        history.log_action("temp_cleaner", "scan", "a2", "low", "success")
        history.log_action("chat:gaming", "dry_run", "a3", "low", "success")
        history.log_action("undo_manager", "restore", "a4", "medium", "success")

        assert history.count() == 4

        # Filtre par type
        execs = history.get_history(action_type="execute")
        assert len(execs) == 1

        # Filtre par module
        chat = history.get_history(module_name="chat:privacy")
        assert len(chat) == 1


# =========================================================================
# E2E Onboarding
# =========================================================================

class TestOnboardingE2E:
    """Tests E2E de la logique d'onboarding."""

    def test_first_launch_detected(self, tmp_path):
        from winboost.gui.onboarding import should_show_onboarding
        config = Config(config_dir=tmp_path)
        assert should_show_onboarding(config) is True

    def test_onboarding_marks_done(self, tmp_path):
        from winboost.gui.onboarding import should_show_onboarding
        config = Config(config_dir=tmp_path)
        config.set("onboarding_done", True)
        config.save()

        config2 = Config(config_dir=tmp_path)
        assert should_show_onboarding(config2) is False


# =========================================================================
# E2E GUI Imports (sans display)
# =========================================================================

class TestGUIImportsV2:
    """Verifie que tous les modules GUI v2 s'importent."""

    def test_import_chat(self):
        from winboost.gui.chat import ChatPage
        assert ChatPage is not None

    def test_import_history(self):
        from winboost.gui.history_page import HistoryPage
        assert HistoryPage is not None

    def test_import_settings(self):
        from winboost.gui.settings_page import SettingsPage
        assert SettingsPage is not None

    def test_import_onboarding(self):
        from winboost.gui.onboarding import OnboardingWizard
        assert OnboardingWizard is not None

    def test_import_app_has_5_pages(self):
        app_path = Path(__file__).parent.parent.parent / "winboost" / "gui" / "app.py"
        content = app_path.read_text(encoding="utf-8")
        for page in ["dashboard", "modules", "chat", "history", "settings"]:
            assert f'"{page}"' in content
