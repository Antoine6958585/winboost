"""Tests pour la Phase 9 — Profils, Onboarding, History, Settings, Undo."""

from __future__ import annotations

from pathlib import Path

import pytest

from winboost.core.backup import BackupManager
from winboost.core.config import PROFILE_SETTINGS, Config
from winboost.core.history import HistoryManager

# =========================================================================
# Tests Systeme de profils
# =========================================================================

class TestProfileSystem:
    """Tests du systeme de profils (Safe/Power/Expert)."""

    def test_default_profile_is_safe(self, tmp_path):
        config = Config(config_dir=tmp_path)
        assert config.profile == "safe"
        assert config.max_risk == "low"
        assert config.dry_run_first is True

    def test_switch_to_power_user(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "power_user"
        assert config.profile == "power_user"
        assert config.max_risk == "medium"
        assert config.dry_run_first is False

    def test_switch_to_expert(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        assert config.profile == "expert"
        assert config.max_risk == "high"
        assert config.dry_run_first is False

    def test_invalid_profile_raises(self, tmp_path):
        config = Config(config_dir=tmp_path)
        with pytest.raises(ValueError, match="invalide"):
            config.profile = "hacker"

    def test_profile_persists_after_save(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        config.save()

        # Recharge
        config2 = Config(config_dir=tmp_path)
        assert config2.profile == "expert"

    def test_all_profiles_have_settings(self):
        for profile in ("safe", "power_user", "expert"):
            assert profile in PROFILE_SETTINGS
            settings = PROFILE_SETTINGS[profile]
            assert "max_risk" in settings
            assert "dry_run_first" in settings

    def test_profile_constraints_applied(self, tmp_path):
        config = Config(config_dir=tmp_path)
        for profile, expected in PROFILE_SETTINGS.items():
            config.profile = profile
            assert config.max_risk == expected["max_risk"]
            assert config.dry_run_first == expected["dry_run_first"]


# =========================================================================
# Tests Onboarding
# =========================================================================

class TestOnboarding:
    """Tests de la logique d'onboarding (sans GUI)."""

    def test_should_show_onboarding_first_launch(self, tmp_path):
        from winboost.gui.onboarding import should_show_onboarding
        config = Config(config_dir=tmp_path)
        assert should_show_onboarding(config) is True

    def test_should_not_show_after_done(self, tmp_path):
        from winboost.gui.onboarding import should_show_onboarding
        config = Config(config_dir=tmp_path)
        config.set("onboarding_done", True)
        assert should_show_onboarding(config) is False

    def test_onboarding_module_imports(self):
        from winboost.gui import onboarding
        assert hasattr(onboarding, "OnboardingWizard")
        assert hasattr(onboarding, "should_show_onboarding")
        assert hasattr(onboarding, "PROFILE_DETAILS")

    def test_profile_details_has_all_profiles(self):
        from winboost.gui.onboarding import PROFILE_DETAILS
        for key in PROFILE_SETTINGS:
            assert key in PROFILE_DETAILS
            info = PROFILE_DETAILS[key]
            assert "label" in info
            assert "desc" in info
            assert "color" in info


# =========================================================================
# Tests History Viewer (donnees)
# =========================================================================

class TestHistoryViewer:
    """Tests pour les donnees du history viewer."""

    def test_log_and_retrieve(self, tmp_path):
        history = HistoryManager(db_path=tmp_path / "h.db")
        entry_id = history.log_action(
            module_name="test_module",
            action_type="scan",
            description="Test scan",
            risk_level="low",
            result_status="success",
        )
        entries = history.get_history()
        assert len(entries) >= 1
        assert entries[0].module_name == "test_module"

    def test_filter_by_type(self, tmp_path):
        history = HistoryManager(db_path=tmp_path / "h.db")
        history.log_action("mod", "scan", "s1", "low", "success")
        history.log_action("mod", "fix", "f1", "medium", "success")
        history.log_action("mod", "execute", "e1", "high", "error")

        scans = history.get_history(action_type="scan")
        assert all(e.action_type == "scan" for e in scans)

        fixes = history.get_history(action_type="fix")
        assert all(e.action_type == "fix" for e in fixes)

    def test_filter_by_module(self, tmp_path):
        history = HistoryManager(db_path=tmp_path / "h.db")
        history.log_action("chat:privacy", "execute", "e1", "medium", "success")
        history.log_action("temp_cleaner", "scan", "s1", "low", "success")

        chat_entries = history.get_history(module_name="chat:privacy")
        assert all(e.module_name == "chat:privacy" for e in chat_entries)

    def test_count(self, tmp_path):
        history = HistoryManager(db_path=tmp_path / "h.db")
        assert history.count() == 0
        history.log_action("mod", "scan", "s", "low", "success")
        history.log_action("mod", "fix", "f", "low", "success")
        assert history.count() == 2

    def test_clear(self, tmp_path):
        history = HistoryManager(db_path=tmp_path / "h.db")
        history.log_action("mod", "scan", "s", "low", "success")
        history.log_action("mod", "fix", "f", "low", "success")
        deleted = history.clear()
        assert deleted == 2
        assert history.count() == 0

    def test_entry_has_all_fields(self, tmp_path):
        history = HistoryManager(db_path=tmp_path / "h.db")
        entry_id = history.log_action(
            module_name="chat:privacy",
            action_type="execute",
            description="Disable DiagTrack",
            risk_level="medium",
            result_status="success",
            result_detail="service_disable executed",
            backup_id="backup_123",
        )
        entry = history.get_entry(entry_id)
        assert entry is not None
        assert entry.module_name == "chat:privacy"
        assert entry.action_type == "execute"
        assert entry.description == "Disable DiagTrack"
        assert entry.risk_level == "medium"
        assert entry.result_status == "success"
        assert entry.result_detail == "service_disable executed"
        assert entry.backup_id == "backup_123"
        assert entry.timestamp


# =========================================================================
# Tests Undo Manager
# =========================================================================

class TestUndoManager:
    """Tests du systeme de backup/undo."""

    def test_create_and_restore_backup(self, tmp_path):
        backup_dir = tmp_path / "backups"
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")

        manager = BackupManager(backup_dir=backup_dir)
        entry = manager.create_backup(
            module_name="test",
            description="Test backup",
            files_to_backup=[str(test_file)],
        )
        assert entry is not None
        assert entry.module_name == "test"

        # Modifie le fichier
        test_file.write_text("modified content")
        assert test_file.read_text() == "modified content"

        # Restaure
        restored, errors = manager.restore_backup(entry.backup_id)
        assert restored == 1
        assert errors == 0
        assert test_file.read_text() == "original content"

    def test_list_backups(self, tmp_path):
        backup_dir = tmp_path / "backups"
        test_file = tmp_path / "f.txt"
        test_file.write_text("data")

        manager = BackupManager(backup_dir=backup_dir)
        manager.create_backup("mod_a", "b1", [str(test_file)])
        manager.create_backup("mod_b", "b2", [str(test_file)])

        all_backups = manager.list_backups()
        assert len(all_backups) == 2

        mod_a = manager.list_backups(module_name="mod_a")
        assert len(mod_a) == 1

    def test_delete_backup(self, tmp_path):
        backup_dir = tmp_path / "backups"
        test_file = tmp_path / "f.txt"
        test_file.write_text("data")

        manager = BackupManager(backup_dir=backup_dir)
        entry = manager.create_backup("mod", "b", [str(test_file)])
        assert entry is not None

        result = manager.delete_backup(entry.backup_id)
        assert result is True
        assert len(manager.list_backups()) == 0

    def test_restore_nonexistent_backup(self, tmp_path):
        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir)
        restored, errors = manager.restore_backup("nonexistent")
        assert restored == 0
        assert errors == 0

    def test_undo_with_history_logging(self, tmp_path):
        """Integration: backup + undo + history log."""
        backup_dir = tmp_path / "backups"
        test_file = tmp_path / "f.txt"
        test_file.write_text("original")

        backup_mgr = BackupManager(backup_dir=backup_dir)
        history = HistoryManager(db_path=tmp_path / "h.db")

        # Cree backup
        entry = backup_mgr.create_backup("test", "Test", [str(test_file)])
        assert entry is not None

        # Modifie
        test_file.write_text("changed")

        # Undo + log
        restored, errors = backup_mgr.restore_backup(entry.backup_id)
        history.log_action(
            module_name="undo_manager",
            action_type="restore",
            description=f"Restauration {entry.backup_id}",
            risk_level="medium",
            result_status="success" if errors == 0 else "partial",
            result_detail=f"{restored} fichier(s)",
            backup_id=entry.backup_id,
        )

        assert test_file.read_text() == "original"
        undo_entries = history.get_history(action_type="restore")
        assert len(undo_entries) >= 1


# =========================================================================
# Tests Settings (donnees config)
# =========================================================================

class TestSettingsData:
    """Tests pour les donnees manipulees par la settings page."""

    def test_api_key_storage(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.set("anthropic_api_key", "sk-ant-test123")
        config.set("openai_api_key", "sk-test456")
        config.save()

        config2 = Config(config_dir=tmp_path)
        assert config2.get("anthropic_api_key") == "sk-ant-test123"
        assert config2.get("openai_api_key") == "sk-test456"

    def test_language_setting(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.set("language", "en")
        config.save()

        config2 = Config(config_dir=tmp_path)
        assert config2.get("language") == "en"

    def test_modules_toggle(self, tmp_path):
        config = Config(config_dir=tmp_path)
        # Desactive un module
        modules = config.modules_enabled.copy()
        modules.remove("system_info")
        config.set("modules_enabled", modules)
        config.save()

        config2 = Config(config_dir=tmp_path)
        assert "system_info" not in config2.modules_enabled

    def test_ollama_url_setting(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.set("ollama_url", "http://custom:11434")
        config.save()

        config2 = Config(config_dir=tmp_path)
        assert config2.get("ollama_url") == "http://custom:11434"

    def test_config_as_dict(self, tmp_path):
        config = Config(config_dir=tmp_path)
        d = config.as_dict()
        assert "profile" in d
        assert "modules_enabled" in d
        assert "backup" in d


# =========================================================================
# Tests GUI Imports (sans display)
# =========================================================================

class TestGUIImports:
    """Verifie que tous les modules GUI s'importent."""

    def test_import_settings_page(self):
        from winboost.gui import settings_page
        assert hasattr(settings_page, "SettingsPage")
        assert hasattr(settings_page, "ProfileCard")
        assert hasattr(settings_page, "PROFILE_INFO")

    def test_import_history_page(self):
        from winboost.gui import history_page
        assert hasattr(history_page, "HistoryPage")
        assert hasattr(history_page, "HistoryEntryCard")

    def test_import_onboarding(self):
        from winboost.gui import onboarding
        assert hasattr(onboarding, "OnboardingWizard")
        assert hasattr(onboarding, "should_show_onboarding")

    def test_app_has_all_pages(self):
        """Verifie que app.py reference toutes les pages."""
        app_path = Path(__file__).parent.parent.parent / "winboost" / "gui" / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "from winboost.gui.chat import ChatPage" in content
        assert "from winboost.gui.history_page import HistoryPage" in content
        assert "from winboost.gui.settings_page import SettingsPage" in content
        assert "from winboost.gui.onboarding import" in content

    def test_app_sidebar_has_5_pages(self):
        """Verifie que la sidebar a 5 entrees."""
        app_path = Path(__file__).parent.parent.parent / "winboost" / "gui" / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert '"dashboard"' in content
        assert '"modules"' in content
        assert '"chat"' in content
        assert '"history"' in content
        assert '"settings"' in content
