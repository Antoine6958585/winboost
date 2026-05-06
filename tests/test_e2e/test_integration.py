"""Tests E2E — Integration engine + modules + backup + history."""


from winboost.core.backup import BackupManager
from winboost.core.config import Config
from winboost.core.engine import Engine
from winboost.core.history import HistoryManager


class TestEngineIntegration:
    """Teste le chargement dynamique reel des modules."""

    def test_discover_all_modules(self, tmp_path):
        """L'engine decouvre les 8 modules."""
        config = Config(config_dir=tmp_path)
        engine = Engine(config)
        engine.discover_modules()

        expected = {
            "temp_cleaner", "system_info", "startup_manager",
            "ram_optimizer", "disk_analyzer", "privacy_cleaner",
            "dev_cache_cleaner", "service_optimizer",
        }
        assert set(engine.list_modules()) == expected

    def test_scan_all_no_crash(self, tmp_path):
        """Scan global sur tous les modules sans crash."""
        config = Config(config_dir=tmp_path)
        engine = Engine(config)
        engine.discover_modules()

        results = engine.scan_all()
        assert len(results) == 8
        for name, result in results.items():
            assert result.module_name == name

    def test_preview_all_modules(self, tmp_path):
        """Preview fonctionne pour tous les modules."""
        config = Config(config_dir=tmp_path)
        engine = Engine(config)
        engine.discover_modules()

        results = engine.scan_all()
        for name, scan_result in results.items():
            preview = engine.preview_module(name, scan_result)
            assert isinstance(preview, str)
            assert len(preview) > 0


class TestBackupHistoryIntegration:
    """Teste l'integration backup + history."""

    def test_full_workflow(self, tmp_path):
        """Workflow complet : scan -> backup -> fix -> log history."""
        # Setup
        backup_mgr = BackupManager(backup_dir=tmp_path / "backups")
        history_mgr = HistoryManager(db_path=tmp_path / "history.db")

        # Simule un fichier a sauvegarder
        target = tmp_path / "target.txt"
        target.write_text("important data")

        # Backup
        entry = backup_mgr.create_backup(
            "test_module", "Before cleanup", [str(target)]
        )
        assert entry is not None

        # Log
        history_id = history_mgr.log_action(
            module_name="test_module",
            action_type="fix",
            description="Cleanup test",
            result_status="success",
            backup_id=entry.backup_id,
        )
        assert history_id > 0

        # Supprime le fichier original
        target.unlink()
        assert not target.exists()

        # Restore
        restored, errors = backup_mgr.restore_backup(entry.backup_id)
        assert restored == 1
        assert target.exists()
        assert target.read_text() == "important data"

        # Verifie history
        history = history_mgr.get_history()
        assert len(history) == 1
        assert history[0].backup_id == entry.backup_id

        history_mgr.close()


class TestGUIImports:
    """Verifie que les imports GUI fonctionnent."""

    def test_import_app(self):
        from winboost.gui.app import WinBoostApp
        assert WinBoostApp is not None

    def test_import_dashboard(self):
        from winboost.gui.dashboard import DashboardPage
        assert DashboardPage is not None

    def test_import_modules_page(self):
        from winboost.gui.modules_page import ModulesPage
        assert ModulesPage is not None

    def test_import_chat(self):
        from winboost.gui.chat_placeholder import ChatPage
        assert ChatPage is not None

    def test_import_theme(self):
        from winboost.gui.theme import COLORS, FONTS, RISK_COLORS
        assert "accent" in COLORS
        assert "title" in FONTS
        assert "info" in RISK_COLORS
