"""Tests pour modules/privacy_cleaner.py."""

from pathlib import Path
from unittest.mock import patch

from winboost.core.base_module import Issue, RiskLevel, ScanResult
from winboost.modules.privacy_cleaner import PrivacyCleaner, _format_size, _safe_dir_size


class TestHelpers:
    def test_format_size(self):
        assert "Mo" in _format_size(5 * 1024 * 1024)

    def test_safe_dir_size_empty(self, tmp_path):
        assert _safe_dir_size(tmp_path) == 0

    def test_safe_dir_size_with_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("data" * 100)
        assert _safe_dir_size(tmp_path) > 0

    def test_safe_dir_size_nonexistent(self):
        assert _safe_dir_size(Path("/nonexistent")) == 0


class TestPrivacyCleanerProperties:
    def test_name(self):
        assert PrivacyCleaner().name == "privacy_cleaner"

    def test_risk_level(self):
        assert PrivacyCleaner().risk_level == RiskLevel.MEDIUM


class TestPrivacyCleanerScan:
    def test_scan_with_mock_targets(self, tmp_path):
        """Scan detecte les cibles mockees."""
        cache_dir = tmp_path / "Chrome Cache"
        cache_dir.mkdir()
        (cache_dir / "data_0").write_bytes(b"\x00" * 10000)

        targets = [{
            "label": "Chrome Cache",
            "path": str(cache_dir),
            "description": "Cache Chrome",
            "risk": RiskLevel.LOW,
            "size": 10000,
            "is_file": False,
        }]

        with patch("winboost.modules.privacy_cleaner._get_targets", return_value=targets):
            result = PrivacyCleaner().scan()

        assert result.module_name == "privacy_cleaner"
        assert result.issue_count == 1
        assert result.metadata["total_size"] == 10000

    def test_scan_empty(self):
        """Scan sans cibles retourne 0 issues."""
        with patch("winboost.modules.privacy_cleaner._get_targets", return_value=[]):
            result = PrivacyCleaner().scan()
        assert result.issue_count == 0


class TestPrivacyCleanerFix:
    def test_fix_cleans_directory(self, tmp_path):
        """Fix nettoie le contenu d'un dossier cible."""
        (tmp_path / "file1.dat").write_text("data")
        (tmp_path / "file2.dat").write_text("data")

        scan_result = ScanResult(
            module_name="privacy_cleaner",
            issues=[Issue(
                id="privacy_test",
                description="Test",
                metadata={
                    "label": "Test Cache",
                    "path": str(tmp_path),
                    "size": 100,
                    "is_file": False,
                },
            )],
        )
        fix = PrivacyCleaner().fix(scan_result)
        assert fix.fixed_count == 1
        assert "Test Cache" in fix.fixed[0]

    def test_fix_cleans_file(self, tmp_path):
        """Fix supprime un fichier cible."""
        target = tmp_path / "history.db"
        target.write_text("history data")

        scan_result = ScanResult(
            module_name="privacy_cleaner",
            issues=[Issue(
                id="privacy_file",
                description="History",
                metadata={
                    "label": "Browser History",
                    "path": str(target),
                    "size": 50,
                    "is_file": True,
                },
            )],
        )
        fix = PrivacyCleaner().fix(scan_result)
        assert fix.fixed_count == 1
        assert not target.exists()

    def test_fix_skips_missing(self):
        """Fix ignore les cibles inexistantes."""
        scan_result = ScanResult(
            module_name="privacy_cleaner",
            issues=[Issue(
                id="privacy_gone",
                description="Gone",
                metadata={
                    "label": "Gone",
                    "path": r"C:\nonexistent\path",
                    "size": 100,
                    "is_file": False,
                },
            )],
        )
        fix = PrivacyCleaner().fix(scan_result)
        assert fix.fixed_count == 0
        assert len(fix.skipped) == 1
