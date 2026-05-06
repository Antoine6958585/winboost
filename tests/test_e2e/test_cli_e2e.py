"""Tests E2E — CLI WinBoost (scan reel, pas de mocks)."""

from click.testing import CliRunner

from winboost.cli.main import cli

runner = CliRunner()


class TestCLIE2EScan:
    """Tests E2E du scan CLI sur le systeme reel."""

    def test_scan_all_modules(self):
        """Scan global fonctionne sans crash."""
        result = runner.invoke(cli, ["scan"])
        assert result.exit_code == 0
        assert "probleme(s) detecte(s)" in result.output

    def test_scan_temp_cleaner(self):
        """Scan temp_cleaner fonctionne."""
        result = runner.invoke(cli, ["scan", "-m", "temp_cleaner"])
        assert result.exit_code == 0
        assert "temp_cleaner" in result.output

    def test_scan_system_info(self):
        """Scan system_info retourne des infos."""
        result = runner.invoke(cli, ["scan", "-m", "system_info"])
        assert result.exit_code == 0
        assert "system_info" in result.output

    def test_scan_startup_manager(self):
        result = runner.invoke(cli, ["scan", "-m", "startup_manager"])
        assert result.exit_code == 0

    def test_scan_ram_optimizer(self):
        result = runner.invoke(cli, ["scan", "-m", "ram_optimizer"])
        assert result.exit_code == 0

    def test_scan_disk_analyzer(self):
        result = runner.invoke(cli, ["scan", "-m", "disk_analyzer"])
        assert result.exit_code == 0

    def test_scan_privacy_cleaner(self):
        result = runner.invoke(cli, ["scan", "-m", "privacy_cleaner"])
        assert result.exit_code == 0

    def test_scan_dev_cache_cleaner(self):
        result = runner.invoke(cli, ["scan", "-m", "dev_cache_cleaner"])
        assert result.exit_code == 0

    def test_scan_service_optimizer(self):
        result = runner.invoke(cli, ["scan", "-m", "service_optimizer"])
        assert result.exit_code == 0

    def test_scan_invalid_module(self):
        """Scan module inexistant = message d'erreur propre."""
        result = runner.invoke(cli, ["scan", "-m", "fake_module"])
        assert result.exit_code == 0
        assert "Module inconnu" in result.output


class TestCLIE2EInfo:
    def test_info_displays_system(self):
        """La commande info affiche les infos systeme."""
        result = runner.invoke(cli, ["info"])
        assert result.exit_code == 0
        assert "OS" in result.output or "Windows" in result.output
        assert "CPU" in result.output
        assert "RAM" in result.output


class TestCLIE2EModules:
    def test_modules_lists_all(self):
        """La commande modules liste les 8 modules."""
        result = runner.invoke(cli, ["modules"])
        assert result.exit_code == 0
        expected = [
            "temp_cleaner", "system_info", "startup_manager",
            "ram_optimizer", "disk_analyzer", "privacy_cleaner",
            "dev_cache_cleaner", "service_optimizer",
        ]
        for mod in expected:
            assert mod in result.output, f"Module {mod} manquant"


class TestCLIE2EVersion:
    def test_version(self):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "2.2.0" in result.output


class TestCLIE2EFix:
    def test_fix_requires_module(self):
        """Fix sans --module echoue proprement."""
        result = runner.invoke(cli, ["fix"])
        assert result.exit_code != 0  # Click error: missing required option
