"""Tests pour modules/dev_cache_cleaner.py."""

from pathlib import Path
from unittest.mock import patch

from winboost.core.base_module import RiskLevel, ScanResult, Issue
from winboost.modules.dev_cache_cleaner import DevCacheCleaner, _format_size, _dir_size


class TestHelpers:
    def test_format_size(self):
        assert "Go" in _format_size(3 * 1024**3)

    def test_dir_size_empty(self, tmp_path):
        assert _dir_size(tmp_path) == 0

    def test_dir_size_with_files(self, tmp_path):
        (tmp_path / "pkg.tar").write_bytes(b"\x00" * 5000)
        assert _dir_size(tmp_path) >= 5000


class TestDevCacheCleanerProperties:
    def test_name(self):
        assert DevCacheCleaner().name == "dev_cache_cleaner"

    def test_risk_level(self):
        assert DevCacheCleaner().risk_level == RiskLevel.LOW


class TestDevCacheCleanerScan:
    def test_scan_detects_caches(self, tmp_path):
        """Scan detecte un cache simule."""
        # Simule un npm-cache
        npm_cache = tmp_path / "AppData" / "Local" / "npm-cache"
        npm_cache.mkdir(parents=True)
        (npm_cache / "package.tgz").write_bytes(b"\x00" * (2 * 1024 * 1024))

        with patch("winboost.modules.dev_cache_cleaner.Path.home", return_value=tmp_path):
            result = DevCacheCleaner().scan()

        assert result.module_name == "dev_cache_cleaner"
        assert result.issue_count >= 1
        npm_issues = [i for i in result.issues if "npm" in i.id]
        assert len(npm_issues) == 1

    def test_scan_skips_small_caches(self, tmp_path):
        """Scan ignore les caches < 1 Mo."""
        npm_cache = tmp_path / "AppData" / "Local" / "npm-cache"
        npm_cache.mkdir(parents=True)
        (npm_cache / "tiny.tgz").write_bytes(b"\x00" * 100)

        with patch("winboost.modules.dev_cache_cleaner.Path.home", return_value=tmp_path):
            result = DevCacheCleaner().scan()

        npm_issues = [i for i in result.issues if "npm" in i.id]
        assert len(npm_issues) == 0


class TestDevCacheCleanerFix:
    def test_fix_cleans_cache(self, tmp_path):
        """Fix nettoie le contenu d'un cache."""
        (tmp_path / "pkg1.tgz").write_bytes(b"\x00" * 100)
        (tmp_path / "pkg2.tgz").write_bytes(b"\x00" * 100)

        scan_result = ScanResult(
            module_name="dev_cache_cleaner",
            issues=[Issue(
                id="dev_npm_cache",
                description="npm cache",
                metadata={"label": "npm cache", "path": str(tmp_path), "size": 200},
            )],
        )
        fix = DevCacheCleaner().fix(scan_result)
        assert fix.fixed_count == 1

    def test_fix_skips_missing(self):
        """Fix ignore les caches inexistants."""
        scan_result = ScanResult(
            module_name="dev_cache_cleaner",
            issues=[Issue(
                id="dev_gone",
                description="Gone",
                metadata={"label": "Gone", "path": r"C:\nope", "size": 100},
            )],
        )
        fix = DevCacheCleaner().fix(scan_result)
        assert fix.fixed_count == 0
        assert len(fix.skipped) == 1
