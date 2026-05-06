"""Tests pour core/history.py."""


from winboost.core.history import HistoryManager


class TestHistoryManager:
    def _make_mgr(self, tmp_path) -> HistoryManager:
        return HistoryManager(db_path=tmp_path / "test_history.db")

    def test_log_and_retrieve(self, tmp_path):
        """Log une action et la recupere."""
        mgr = self._make_mgr(tmp_path)
        entry_id = mgr.log_action(
            module_name="temp_cleaner",
            action_type="fix",
            description="Nettoyage temp",
            result_status="success",
            result_detail="10 fichiers supprimes",
        )
        assert entry_id > 0

        entry = mgr.get_entry(entry_id)
        assert entry is not None
        assert entry.module_name == "temp_cleaner"
        assert entry.action_type == "fix"
        assert entry.result_status == "success"
        mgr.close()

    def test_get_history(self, tmp_path):
        """Recupere l'historique filtre."""
        mgr = self._make_mgr(tmp_path)
        mgr.log_action("mod_a", "scan", "Scan A", result_status="success")
        mgr.log_action("mod_b", "fix", "Fix B", result_status="success")
        mgr.log_action("mod_a", "fix", "Fix A", result_status="error")

        # Tous
        all_entries = mgr.get_history()
        assert len(all_entries) == 3

        # Par module
        mod_a = mgr.get_history(module_name="mod_a")
        assert len(mod_a) == 2

        # Par type
        fixes = mgr.get_history(action_type="fix")
        assert len(fixes) == 2
        mgr.close()

    def test_get_history_limit(self, tmp_path):
        """Le parametre limit fonctionne."""
        mgr = self._make_mgr(tmp_path)
        for i in range(10):
            mgr.log_action("test", "scan", f"Scan {i}", result_status="success")

        limited = mgr.get_history(limit=5)
        assert len(limited) == 5
        mgr.close()

    def test_get_entry_nonexistent(self, tmp_path):
        """get_entry retourne None pour un ID inexistant."""
        mgr = self._make_mgr(tmp_path)
        assert mgr.get_entry(9999) is None
        mgr.close()

    def test_count(self, tmp_path):
        """count() retourne le bon nombre."""
        mgr = self._make_mgr(tmp_path)
        mgr.log_action("mod_a", "scan", "A", result_status="success")
        mgr.log_action("mod_b", "scan", "B", result_status="success")

        assert mgr.count() == 2
        assert mgr.count("mod_a") == 1
        assert mgr.count("nope") == 0
        mgr.close()

    def test_clear(self, tmp_path):
        """clear() supprime les entrees."""
        mgr = self._make_mgr(tmp_path)
        mgr.log_action("mod_a", "scan", "A", result_status="success")
        mgr.log_action("mod_b", "scan", "B", result_status="success")

        deleted = mgr.clear("mod_a")
        assert deleted == 1
        assert mgr.count() == 1

        deleted = mgr.clear()
        assert deleted == 1
        assert mgr.count() == 0
        mgr.close()

    def test_metadata_persistence(self, tmp_path):
        """Les metadata JSON sont preservees."""
        mgr = self._make_mgr(tmp_path)
        entry_id = mgr.log_action(
            "test", "fix", "Test",
            result_status="success",
            metadata={"files_cleaned": 42, "size_freed": 1024},
        )

        entry = mgr.get_entry(entry_id)
        assert entry is not None
        assert entry.metadata["files_cleaned"] == 42
        assert entry.metadata["size_freed"] == 1024
        mgr.close()

    def test_backup_id_field(self, tmp_path):
        """Le champ backup_id est stocke et recupere."""
        mgr = self._make_mgr(tmp_path)
        entry_id = mgr.log_action(
            "test", "fix", "With backup",
            result_status="success",
            backup_id="backup_20260325_001",
        )

        entry = mgr.get_entry(entry_id)
        assert entry is not None
        assert entry.backup_id == "backup_20260325_001"
        mgr.close()

    def test_history_order_desc(self, tmp_path):
        """L'historique est trie par timestamp desc (plus recent en premier)."""
        mgr = self._make_mgr(tmp_path)
        mgr.log_action("test", "scan", "First", result_status="success")
        mgr.log_action("test", "scan", "Second", result_status="success")
        mgr.log_action("test", "scan", "Third", result_status="success")

        history = mgr.get_history()
        assert history[0].description == "Third"
        assert history[-1].description == "First"
        mgr.close()
