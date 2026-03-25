"""Tests pour core/backup.py."""

from pathlib import Path

from winboost.core.backup import BackupManager, BackupEntry


class TestBackupEntry:
    def test_to_dict_roundtrip(self):
        entry = BackupEntry(
            backup_id="b1",
            module_name="test",
            description="Test backup",
            files=[{"original": "/a.txt", "backup": "/b/a.txt"}],
        )
        d = entry.to_dict()
        restored = BackupEntry.from_dict(d)
        assert restored.backup_id == "b1"
        assert restored.module_name == "test"
        assert len(restored.files) == 1


class TestBackupManager:
    def test_create_backup(self, tmp_path):
        """Cree un backup de fichiers existants."""
        # Fichier source
        src = tmp_path / "source"
        src.mkdir()
        f1 = src / "config.json"
        f1.write_text('{"key": "value"}')

        backup_dir = tmp_path / "backups"
        mgr = BackupManager(backup_dir=backup_dir)
        entry = mgr.create_backup("test_mod", "Test action", [str(f1)])

        assert entry is not None
        assert entry.module_name == "test_mod"
        assert len(entry.files) == 1
        # Le fichier backup existe
        backup_path = Path(entry.files[0]["backup"])
        assert backup_path.exists()

    def test_create_backup_no_files(self, tmp_path):
        """Backup sans fichiers existants retourne None."""
        backup_dir = tmp_path / "backups"
        mgr = BackupManager(backup_dir=backup_dir)
        entry = mgr.create_backup("test", "Nothing", ["/nonexistent/file.txt"])
        assert entry is None

    def test_restore_backup(self, tmp_path):
        """Restaure un backup avec succes."""
        src = tmp_path / "source"
        src.mkdir()
        f1 = src / "data.txt"
        f1.write_text("original")

        backup_dir = tmp_path / "backups"
        mgr = BackupManager(backup_dir=backup_dir)
        entry = mgr.create_backup("test", "Before delete", [str(f1)])

        # Supprime l'original
        f1.unlink()
        assert not f1.exists()

        # Restaure
        restored, errors = mgr.restore_backup(entry.backup_id)
        assert restored == 1
        assert errors == 0
        assert f1.exists()
        assert f1.read_text() == "original"

    def test_restore_nonexistent(self, tmp_path):
        """Restauration d'un backup inexistant."""
        mgr = BackupManager(backup_dir=tmp_path / "backups")
        restored, errors = mgr.restore_backup("nonexistent")
        assert restored == 0

    def test_list_backups(self, tmp_path):
        """Liste les backups filtres par module."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("a")
        (src / "b.txt").write_text("b")

        backup_dir = tmp_path / "backups"
        mgr = BackupManager(backup_dir=backup_dir)
        mgr.create_backup("mod_a", "Backup A", [str(src / "a.txt")])
        mgr.create_backup("mod_b", "Backup B", [str(src / "b.txt")])

        assert len(mgr.list_backups()) == 2
        assert len(mgr.list_backups("mod_a")) == 1
        assert len(mgr.list_backups("mod_c")) == 0

    def test_delete_backup(self, tmp_path):
        """Supprime un backup et ses fichiers."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "f.txt").write_text("data")

        backup_dir = tmp_path / "backups"
        mgr = BackupManager(backup_dir=backup_dir)
        entry = mgr.create_backup("test", "Delete me", [str(src / "f.txt")])

        assert mgr.delete_backup(entry.backup_id) is True
        assert len(mgr.list_backups()) == 0

    def test_delete_nonexistent(self, tmp_path):
        mgr = BackupManager(backup_dir=tmp_path / "backups")
        assert mgr.delete_backup("nope") is False

    def test_cleanup_old_backups(self, tmp_path):
        """Les anciens backups sont supprimes quand la limite est atteinte."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "f.txt").write_text("data")

        backup_dir = tmp_path / "backups"
        mgr = BackupManager(backup_dir=backup_dir, max_backups=3)

        for i in range(5):
            mgr.create_backup("test", f"Backup {i}", [str(src / "f.txt")])

        assert len(mgr.list_backups()) == 3

    def test_persistence(self, tmp_path):
        """Les backups persistent entre instances."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "f.txt").write_text("data")

        backup_dir = tmp_path / "backups"
        mgr1 = BackupManager(backup_dir=backup_dir)
        mgr1.create_backup("test", "Persistent", [str(src / "f.txt")])

        # Nouvelle instance
        mgr2 = BackupManager(backup_dir=backup_dir)
        assert len(mgr2.list_backups()) == 1
