"""Tests pour cli/main.py."""

from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from winboost.cli.main import cli
from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)


class FakeCLIModule(BaseModule):
    """Module factice pour tester le CLI."""

    @property
    def name(self) -> str:
        return "fake_cli"

    @property
    def description(self) -> str:
        return "Module CLI test"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def scan(self) -> ScanResult:
        return ScanResult(
            module_name=self.name,
            issues=[Issue(id="c1", description="CLI issue")],
            summary="1 probleme",
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        return FixResult(module_name=self.name, fixed=["c1"], summary="1 corrige")


def _mock_engine():
    """Cree un engine mocke avec un module factice."""
    from winboost.core.config import Config
    from winboost.core.engine import Engine
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    config = Config(config_dir=tmp)
    engine = Engine(config)
    engine.register_module(FakeCLIModule())
    return engine


class TestCLIScan:
    def test_scan_all(self):
        runner = CliRunner()
        with patch("winboost.cli.main._create_engine", return_value=_mock_engine()):
            result = runner.invoke(cli, ["scan"])
        assert result.exit_code == 0
        assert "1 probleme" in result.output

    def test_scan_specific_module(self):
        runner = CliRunner()
        with patch("winboost.cli.main._create_engine", return_value=_mock_engine()):
            result = runner.invoke(cli, ["scan", "--module", "fake_cli"])
        assert result.exit_code == 0
        assert "CLI issue" in result.output

    def test_scan_unknown_module(self):
        runner = CliRunner()
        with patch("winboost.cli.main._create_engine", return_value=_mock_engine()):
            result = runner.invoke(cli, ["scan", "--module", "nope"])
        assert result.exit_code == 0
        assert "Module inconnu" in result.output


class TestCLIFix:
    def test_fix_with_confirm(self):
        runner = CliRunner()
        with patch("winboost.cli.main._create_engine", return_value=_mock_engine()):
            result = runner.invoke(cli, ["fix", "--module", "fake_cli", "--yes"])
        assert result.exit_code == 0
        assert "1 corrige" in result.output

    def test_fix_unknown_module(self):
        runner = CliRunner()
        with patch("winboost.cli.main._create_engine", return_value=_mock_engine()):
            result = runner.invoke(cli, ["fix", "--module", "nope", "--yes"])
        assert result.exit_code == 0
        assert "Module inconnu" in result.output


class TestCLIInfo:
    def test_info_without_sysinfo_module(self):
        runner = CliRunner()
        with patch("winboost.cli.main._create_engine", return_value=_mock_engine()):
            result = runner.invoke(cli, ["info"])
        assert result.exit_code == 0
        assert "non disponible" in result.output


class TestCLIModules:
    def test_list_modules(self):
        runner = CliRunner()
        with patch("winboost.cli.main._create_engine", return_value=_mock_engine()):
            result = runner.invoke(cli, ["modules"])
        assert result.exit_code == 0
        assert "fake_cli" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert "0.1.0" in result.output
