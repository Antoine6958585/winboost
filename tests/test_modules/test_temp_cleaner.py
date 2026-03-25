"""Tests pour modules/temp_cleaner.py."""

from pathlib import Path
from unittest.mock import patch

from winboost.core.base_module import RiskLevel
from winboost.modules.temp_cleaner import TempCleaner, _dir_size, _format_size, _get_temp_dirs


class TestFormatSize:
    def test_bytes(self):
        assert "0.0 o" == _format_size(0)

    def test_kilobytes(self):
        result = _format_size(2048)
        assert "Ko" in result

    def test_megabytes(self):
        result = _format_size(5 * 1024 * 1024)
        assert "Mo" in result

    def test_gigabytes(self):
        result = _format_size(3 * 1024 ** 3)
        assert "Go" in result


class TestDirSize:
    def test_empty_dir(self, tmp_path):
        assert _dir_size(tmp_path) == 0

    def test_dir_with_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world!")
        size = _dir_size(tmp_path)
        assert size > 0

    def test_nested_dir(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").write_text("x" * 100)
        size = _dir_size(tmp_path)
        assert size >= 100


class TestTempCleanerProperties:
    def test_name(self):
        assert TempCleaner().name == "temp_cleaner"

    def test_risk_level(self):
        assert TempCleaner().risk_level == RiskLevel.LOW


class TestTempCleanerScan:
    def test_scan_with_mock_dirs(self, tmp_path):
        """Scan detecte les fichiers dans un repertoire temp simule."""
        # Cree des fichiers temp
        (tmp_path / "file1.tmp").write_text("data" * 100)
        (tmp_path / "file2.log").write_text("log" * 50)

        with patch(
            "winboost.modules.temp_cleaner._get_temp_dirs",
            return_value=[tmp_path],
        ):
            cleaner = TempCleaner()
            result = cleaner.scan()

        assert result.module_name == "temp_cleaner"
        assert result.has_issues is True
        assert result.metadata["total_size"] > 0

    def test_scan_empty_temp(self, tmp_path):
        """Scan sur un repertoire vide ne detecte rien."""
        with patch(
            "winboost.modules.temp_cleaner._get_temp_dirs",
            return_value=[tmp_path],
        ):
            cleaner = TempCleaner()
            result = cleaner.scan()

        # Un dossier vide a 0 fichiers -> pas d'issue
        assert result.issue_count == 0


class TestTempCleanerFix:
    def test_fix_deletes_files(self, tmp_path):
        """Fix supprime les fichiers temporaires."""
        f1 = tmp_path / "deleteme.tmp"
        f2 = tmp_path / "deleteme2.log"
        f1.write_text("data")
        f2.write_text("data")

        with patch(
            "winboost.modules.temp_cleaner._get_temp_dirs",
            return_value=[tmp_path],
        ):
            cleaner = TempCleaner()
            scan = cleaner.scan()
            fix = cleaner.fix(scan)

        assert fix.fixed_count > 0
        assert not f1.exists()
        assert not f2.exists()

    def test_fix_handles_subdirs(self, tmp_path):
        """Fix supprime aussi les sous-dossiers."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "file.txt").write_text("data")

        with patch(
            "winboost.modules.temp_cleaner._get_temp_dirs",
            return_value=[tmp_path],
        ):
            cleaner = TempCleaner()
            scan = cleaner.scan()
            fix = cleaner.fix(scan)

        assert fix.fixed_count > 0
        assert not sub.exists()
