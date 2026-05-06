"""Tests pour modules/ram_optimizer.py."""

from unittest.mock import MagicMock, patch

from winboost.core.base_module import Issue, RiskLevel, ScanResult
from winboost.modules.ram_optimizer import (
    PROTECTED_PROCESSES,
    RamOptimizer,
    _format_mb,
)

# --- Tests helpers ---

class TestFormatMb:
    def test_format(self):
        assert _format_mb(1024 * 1024 * 512) == "512 Mo"

    def test_format_small(self):
        assert _format_mb(1024 * 1024) == "1 Mo"


# --- Tests Properties ---

class TestRamOptimizerProperties:
    def test_name(self):
        assert RamOptimizer().name == "ram_optimizer"

    def test_risk_level(self):
        assert RamOptimizer().risk_level == RiskLevel.MEDIUM

    def test_description(self):
        desc = RamOptimizer().description.lower()
        assert "ram" in desc or "memoire" in desc


# --- Tests Scan ---

class TestRamOptimizerScan:
    def test_scan_returns_result(self):
        """Scan retourne un resultat valide."""
        result = RamOptimizer().scan()
        assert result.module_name == "ram_optimizer"
        assert "ram_percent" in result.metadata
        assert result.metadata["ram_percent"] >= 0

    def test_scan_high_ram_creates_issue(self):
        """Si la RAM est elevee, une issue specifique est creee."""
        # Mock psutil.virtual_memory pour simuler 95% d'utilisation
        mock_ram = MagicMock()
        mock_ram.percent = 95
        mock_ram.used = 8 * 1024**3
        mock_ram.total = 8.4 * 1024**3
        mock_ram.available = 0.4 * 1024**3

        with (
            patch("winboost.modules.ram_optimizer.psutil.virtual_memory", return_value=mock_ram),
            patch("winboost.modules.ram_optimizer._get_heavy_processes", return_value=[]),
        ):
            result = RamOptimizer().scan()

        ram_issues = [i for i in result.issues if i.id == "ram_high_usage"]
        assert len(ram_issues) == 1
        assert "95%" in ram_issues[0].description

    def test_scan_normal_ram_no_alert(self):
        """Si la RAM est normale, pas d'issue d'alerte."""
        mock_ram = MagicMock()
        mock_ram.percent = 45
        mock_ram.used = 4 * 1024**3
        mock_ram.total = 8 * 1024**3
        mock_ram.available = 4 * 1024**3

        with (
            patch("winboost.modules.ram_optimizer.psutil.virtual_memory", return_value=mock_ram),
            patch("winboost.modules.ram_optimizer._get_heavy_processes", return_value=[]),
        ):
            result = RamOptimizer().scan()

        ram_issues = [i for i in result.issues if i.id == "ram_high_usage"]
        assert len(ram_issues) == 0

    def test_scan_with_heavy_processes(self):
        """Scan detecte les processus gourmands."""
        mock_ram = MagicMock()
        mock_ram.percent = 70
        mock_ram.used = 6 * 1024**3
        mock_ram.total = 8 * 1024**3
        mock_ram.available = 2 * 1024**3

        heavy = [
            {"pid": 1234, "name": "chrome.exe", "rss": 800 * 1024**2, "is_protected": False},
            {"pid": 5678, "name": "svchost.exe", "rss": 600 * 1024**2, "is_protected": True},
        ]

        with (
            patch("winboost.modules.ram_optimizer.psutil.virtual_memory", return_value=mock_ram),
            patch("winboost.modules.ram_optimizer._get_heavy_processes", return_value=heavy),
        ):
            result = RamOptimizer().scan()

        assert result.issue_count == 2
        # Le process protege n'est pas auto_fixable
        protected = [i for i in result.issues if i.metadata.get("is_protected")]
        assert len(protected) == 1
        assert protected[0].auto_fixable is False


# --- Tests Fix ---

class TestRamOptimizerFix:
    def test_fix_skips_protected(self):
        """Fix ignore les processus proteges."""
        scan_result = ScanResult(
            module_name="ram_optimizer",
            issues=[
                Issue(
                    id="ram_proc_1",
                    description="svchost.exe",
                    metadata={"pid": 1, "name": "svchost.exe", "rss": 600_000_000, "is_protected": True},
                ),
            ],
        )
        fix = RamOptimizer().fix(scan_result)
        assert fix.fixed_count == 0
        assert len(fix.skipped) == 1
        assert "protege" in fix.skipped[0]

    def test_fix_skips_global_issue(self):
        """Fix ignore l'issue globale (pas de PID)."""
        scan_result = ScanResult(
            module_name="ram_optimizer",
            issues=[
                Issue(
                    id="ram_high_usage",
                    description="RAM elevee",
                    metadata={"percent": 95, "used": 8_000_000_000, "total": 8_400_000_000},
                ),
            ],
        )
        fix = RamOptimizer().fix(scan_result)
        assert fix.fixed_count == 0
        assert len(fix.skipped) == 0


# --- Tests PROTECTED_PROCESSES ---

class TestProtectedProcesses:
    def test_known_protected(self):
        assert "svchost.exe" in PROTECTED_PROCESSES
        assert "explorer.exe" in PROTECTED_PROCESSES
        assert "lsass.exe" in PROTECTED_PROCESSES

    def test_common_app_not_protected(self):
        assert "chrome.exe" not in PROTECTED_PROCESSES
        assert "discord.exe" not in PROTECTED_PROCESSES
