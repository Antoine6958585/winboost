"""Tests pour modules/service_optimizer.py."""

from unittest.mock import patch, MagicMock

from winboost.core.base_module import RiskLevel, ScanResult, Issue
from winboost.modules.service_optimizer import (
    ServiceOptimizer,
    OPTIONAL_SERVICES,
    PROTECTED_SERVICES,
)


class TestServiceOptimizerProperties:
    def test_name(self):
        assert ServiceOptimizer().name == "service_optimizer"

    def test_risk_level(self):
        assert ServiceOptimizer().risk_level == RiskLevel.HIGH


class TestServiceOptimizerScan:
    def test_scan_detects_optional_services(self):
        """Scan detecte les services optionnels actifs."""
        # Mock un service optionnel qui tourne
        mock_svc = MagicMock()
        mock_svc.as_dict.return_value = {
            "name": "DiagTrack",
            "status": "running",
            "start_type": "automatic",
            "display_name": "Connected User Experiences and Telemetry",
        }

        with patch("winboost.modules.service_optimizer.psutil.win_service_iter", return_value=[mock_svc]):
            result = ServiceOptimizer().scan()

        assert result.issue_count == 1
        assert result.metadata["running_optional"] == 1
        assert result.issues[0].id == "svc_DiagTrack"

    def test_scan_ignores_stopped_services(self):
        """Scan ignore les services optionnels arretes."""
        mock_svc = MagicMock()
        mock_svc.as_dict.return_value = {
            "name": "DiagTrack",
            "status": "stopped",
            "start_type": "disabled",
            "display_name": "Telemetry",
        }

        with patch("winboost.modules.service_optimizer.psutil.win_service_iter", return_value=[mock_svc]):
            result = ServiceOptimizer().scan()

        assert result.issue_count == 0

    def test_scan_ignores_unknown_services(self):
        """Scan ignore les services non listes."""
        mock_svc = MagicMock()
        mock_svc.as_dict.return_value = {
            "name": "CustomService",
            "status": "running",
            "start_type": "automatic",
            "display_name": "Custom",
        }

        with patch("winboost.modules.service_optimizer.psutil.win_service_iter", return_value=[mock_svc]):
            result = ServiceOptimizer().scan()

        assert result.issue_count == 0


class TestServiceOptimizerFix:
    def test_fix_skips_protected(self):
        """Fix refuse de toucher un service protege (double check)."""
        scan_result = ScanResult(
            module_name="service_optimizer",
            issues=[Issue(
                id="svc_wuauserv",
                description="Windows Update",
                metadata={
                    "name": "wuauserv",
                    "display_name": "Windows Update",
                    "status": "running",
                    "start_type": "automatic",
                },
            )],
        )
        fix = ServiceOptimizer().fix(scan_result)
        assert fix.fixed_count == 0
        assert len(fix.skipped) == 1
        assert "protege" in fix.skipped[0]


class TestConstants:
    def test_optional_services_not_in_protected(self):
        """Aucun service optionnel ne doit etre dans la liste protegee."""
        for svc in OPTIONAL_SERVICES:
            assert svc.lower() not in PROTECTED_SERVICES, f"{svc} est dans les deux listes!"

    def test_protected_contains_critical(self):
        """Les services critiques sont bien proteges."""
        assert "wuauserv" in PROTECTED_SERVICES
        assert "windefend" in PROTECTED_SERVICES
        assert "lsass" in PROTECTED_SERVICES
