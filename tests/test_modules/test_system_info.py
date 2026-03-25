"""Tests pour modules/system_info.py."""

from winboost.core.base_module import RiskLevel
from winboost.modules.system_info import SystemInfo


class TestSystemInfoProperties:
    def test_name(self):
        assert SystemInfo().name == "system_info"

    def test_description(self):
        assert "systeme" in SystemInfo().description.lower() or "system" in SystemInfo().description.lower()

    def test_risk_level(self):
        assert SystemInfo().risk_level == RiskLevel.INFO


class TestSystemInfoScan:
    def test_scan_returns_issues(self):
        """Scan retourne des infos systeme (au moins OS, CPU, RAM, disque, uptime)."""
        result = SystemInfo().scan()
        assert result.module_name == "system_info"
        assert result.issue_count >= 4  # OS + CPU + RAM + au moins 1 disque

        ids = [i.id for i in result.issues]
        assert "os_version" in ids
        assert "cpu_info" in ids
        assert "ram_info" in ids
        assert "uptime" in ids

    def test_scan_all_info_level(self):
        """Toutes les issues sont de niveau INFO."""
        result = SystemInfo().scan()
        for issue in result.issues:
            assert issue.risk_level == RiskLevel.INFO

    def test_scan_none_auto_fixable(self):
        """Aucune issue n'est auto-fixable (lecture seule)."""
        result = SystemInfo().scan()
        for issue in result.issues:
            assert issue.auto_fixable is False

    def test_scan_metadata(self):
        """Les issues contiennent des metadonnees exploitables."""
        result = SystemInfo().scan()
        ram_issue = next(i for i in result.issues if i.id == "ram_info")
        assert "total" in ram_issue.metadata
        assert "used" in ram_issue.metadata
        assert ram_issue.metadata["total"] > 0


class TestSystemInfoFix:
    def test_fix_is_noop(self):
        """Fix ne fait rien sur un module lecture seule."""
        sysinfo = SystemInfo()
        scan = sysinfo.scan()
        fix = sysinfo.fix(scan)
        assert fix.fixed_count == 0
        assert fix.success is True
