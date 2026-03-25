"""Tests pour core/engine.py."""

import pytest

from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)
from winboost.core.config import Config
from winboost.core.engine import Engine


class FakeModule(BaseModule):
    """Module factice pour tester l'engine."""

    def __init__(self, module_name: str = "fake") -> None:
        self._name = module_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Fake module {self._name}"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def scan(self) -> ScanResult:
        return ScanResult(
            module_name=self._name,
            issues=[Issue(id="f1", description="Fake issue")],
            summary="1 probleme",
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        return FixResult(module_name=self._name, fixed=["f1"], summary="1 corrige")


class TestEngine:
    def _make_engine(self, tmp_path) -> Engine:
        config = Config(config_dir=tmp_path)
        return Engine(config)

    def test_register_module(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.register_module(FakeModule("test_mod"))
        assert "test_mod" in engine.list_modules()
        assert engine.get_module("test_mod") is not None

    def test_get_module_unknown(self, tmp_path):
        engine = self._make_engine(tmp_path)
        assert engine.get_module("inexistant") is None

    def test_scan_all(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.register_module(FakeModule("mod_a"))
        engine.register_module(FakeModule("mod_b"))
        results = engine.scan_all()
        assert len(results) == 2
        assert "mod_a" in results
        assert "mod_b" in results
        assert results["mod_a"].issue_count == 1

    def test_scan_module(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.register_module(FakeModule("target"))
        result = engine.scan_module("target")
        assert result.module_name == "target"
        assert result.issue_count == 1

    def test_scan_module_unknown(self, tmp_path):
        engine = self._make_engine(tmp_path)
        with pytest.raises(ValueError, match="Module inconnu"):
            engine.scan_module("nope")

    def test_fix_module(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.register_module(FakeModule("fixable"))
        scan = engine.scan_module("fixable")
        fix = engine.fix_module("fixable", scan)
        assert fix.success is True
        assert fix.fixed_count == 1

    def test_fix_module_unknown(self, tmp_path):
        engine = self._make_engine(tmp_path)
        dummy_scan = ScanResult(module_name="nope")
        with pytest.raises(ValueError, match="Module inconnu"):
            engine.fix_module("nope", dummy_scan)

    def test_preview_module(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.register_module(FakeModule("prev"))
        scan = engine.scan_module("prev")
        preview = engine.preview_module("prev", scan)
        assert "prev" in preview
        assert "1 probleme" in preview

    def test_preview_module_unknown(self, tmp_path):
        engine = self._make_engine(tmp_path)
        dummy_scan = ScanResult(module_name="nope")
        with pytest.raises(ValueError, match="Module inconnu"):
            engine.preview_module("nope", dummy_scan)
