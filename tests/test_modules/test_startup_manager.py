"""Tests pour modules/startup_manager.py."""

from unittest.mock import patch

from winboost.core.base_module import Issue, RiskLevel, ScanResult
from winboost.modules.startup_manager import (
    SYSTEM_CRITICAL,
    StartupEntry,
    StartupManager,
)

# --- Helpers ---

def _make_entries() -> list[StartupEntry]:
    """Cree des entrees factices."""
    return [
        StartupEntry(
            name="MyApp",
            command=r"C:\Program Files\MyApp\myapp.exe",
            source="registry",
            location=r"Software\Microsoft\Windows\CurrentVersion\Run",
            hive=1,  # HKCU simulé
            is_system=False,
        ),
        StartupEntry(
            name="SecurityHealth",
            command=r"C:\Windows\System32\SecurityHealth.exe",
            source="registry",
            location=r"Software\Microsoft\Windows\CurrentVersion\Run",
            hive=1,
            is_system=True,
        ),
        StartupEntry(
            name="ShortcutApp",
            command=r"C:\Users\Test\Startup\shortcut.lnk",
            source="folder",
            location=r"C:\Users\Test\Startup",
            is_system=False,
        ),
    ]


# --- Tests Properties ---

class TestStartupManagerProperties:
    def test_name(self):
        assert StartupManager().name == "startup_manager"

    def test_risk_level(self):
        assert StartupManager().risk_level == RiskLevel.MEDIUM

    def test_description(self):
        assert "demarrage" in StartupManager().description.lower()


# --- Tests StartupEntry ---

class TestStartupEntry:
    def test_creation(self):
        entry = StartupEntry(
            name="Test", command="test.exe", source="registry",
            location="key", hive=1, is_system=False,
        )
        assert entry.name == "Test"
        assert entry.is_system is False

    def test_system_detection(self):
        entry = StartupEntry(
            name="SecurityHealth", command="test.exe", source="registry",
            location="key", is_system=True,
        )
        assert entry.is_system is True


# --- Tests Scan ---

class TestStartupManagerScan:
    def test_scan_with_mock_entries(self):
        """Scan detecte les entrees de demarrage."""
        entries = _make_entries()
        with (
            patch(
                "winboost.modules.startup_manager._read_registry_entries",
                return_value=entries[:2],
            ),
            patch(
                "winboost.modules.startup_manager._read_folder_entries",
                return_value=entries[2:],
            ),
        ):
            result = StartupManager().scan()

        assert result.module_name == "startup_manager"
        assert result.issue_count == 3
        assert result.metadata["total"] == 3
        assert result.metadata["removable"] == 2  # MyApp + ShortcutApp

    def test_scan_empty(self):
        """Scan sans entrees retourne 0 issues."""
        with (
            patch(
                "winboost.modules.startup_manager._read_registry_entries",
                return_value=[],
            ),
            patch(
                "winboost.modules.startup_manager._read_folder_entries",
                return_value=[],
            ),
        ):
            result = StartupManager().scan()

        assert result.issue_count == 0

    def test_system_entries_not_auto_fixable(self):
        """Les entrees systeme ne sont pas auto_fixable."""
        entries = _make_entries()
        with (
            patch(
                "winboost.modules.startup_manager._read_registry_entries",
                return_value=entries[:2],
            ),
            patch(
                "winboost.modules.startup_manager._read_folder_entries",
                return_value=[],
            ),
        ):
            result = StartupManager().scan()

        system_issues = [i for i in result.issues if i.metadata.get("is_system")]
        for issue in system_issues:
            assert issue.auto_fixable is False
            assert issue.risk_level == RiskLevel.HIGH


# --- Tests Fix ---

class TestStartupManagerFix:
    def test_fix_skips_system(self):
        """Fix ignore les programmes systeme."""
        scan_result = ScanResult(
            module_name="startup_manager",
            issues=[
                Issue(
                    id="startup_registry_SecurityHealth",
                    description="SecurityHealth",
                    risk_level=RiskLevel.HIGH,
                    auto_fixable=False,
                    metadata={
                        "name": "SecurityHealth",
                        "command": "sec.exe",
                        "source": "registry",
                        "location": "key",
                        "hive": 1,
                        "is_system": True,
                    },
                ),
            ],
        )
        fix = StartupManager().fix(scan_result)
        assert fix.fixed_count == 0
        assert len(fix.skipped) == 1
        assert "systeme" in fix.skipped[0]

    def test_fix_folder_entry(self, tmp_path):
        """Fix supprime les raccourcis dans le dossier Startup."""
        shortcut = tmp_path / "app.lnk"
        shortcut.write_text("fake shortcut")

        scan_result = ScanResult(
            module_name="startup_manager",
            issues=[
                Issue(
                    id="startup_folder_app",
                    description="app",
                    metadata={
                        "name": "app",
                        "command": str(shortcut),
                        "source": "folder",
                        "location": str(tmp_path),
                        "hive": None,
                        "is_system": False,
                    },
                ),
            ],
        )
        fix = StartupManager().fix(scan_result)
        assert fix.fixed_count == 1
        assert not shortcut.exists()

    def test_fix_folder_missing_file(self, tmp_path):
        """Fix gere le cas ou le fichier n'existe plus."""
        scan_result = ScanResult(
            module_name="startup_manager",
            issues=[
                Issue(
                    id="startup_folder_gone",
                    description="gone",
                    metadata={
                        "name": "gone",
                        "command": str(tmp_path / "nope.lnk"),
                        "source": "folder",
                        "location": str(tmp_path),
                        "hive": None,
                        "is_system": False,
                    },
                ),
            ],
        )
        fix = StartupManager().fix(scan_result)
        assert fix.fixed_count == 0
        assert len(fix.skipped) == 1


# --- Tests SYSTEM_CRITICAL ---

class TestSystemCritical:
    def test_known_critical_names(self):
        assert "securityhealth" in SYSTEM_CRITICAL
        assert "explorer" in SYSTEM_CRITICAL
        assert "ctfmon" in SYSTEM_CRITICAL
