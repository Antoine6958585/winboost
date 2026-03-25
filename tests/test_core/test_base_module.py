"""Tests pour core/base_module.py."""

import pytest

from winboost.core.base_module import (
    BaseModule,
    FixResult,
    Issue,
    RiskLevel,
    ScanResult,
)


# --- Module concret pour les tests ---

class DummyModule(BaseModule):
    """Module factice pour tester la classe abstraite."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "Module de test"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def scan(self) -> ScanResult:
        return ScanResult(
            module_name=self.name,
            issues=[
                Issue(id="d1", description="Probleme 1", auto_fixable=True),
                Issue(id="d2", description="Probleme 2", auto_fixable=False),
            ],
            summary="2 problemes",
        )

    def fix(self, scan_result: ScanResult) -> FixResult:
        return FixResult(
            module_name=self.name,
            fixed=["d1"],
            skipped=["d2"],
            summary="1 corrige, 1 ignore",
        )


# --- Tests RiskLevel ---

class TestRiskLevel:
    def test_values(self):
        assert RiskLevel.INFO.value == "info"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_all_levels_exist(self):
        levels = [r.value for r in RiskLevel]
        assert levels == ["info", "low", "medium", "high", "critical"]


# --- Tests Issue ---

class TestIssue:
    def test_defaults(self):
        issue = Issue(id="test", description="desc")
        assert issue.risk_level == RiskLevel.LOW
        assert issue.auto_fixable is True
        assert issue.metadata == {}

    def test_custom_values(self):
        issue = Issue(
            id="x",
            description="d",
            detail="det",
            risk_level=RiskLevel.HIGH,
            auto_fixable=False,
            metadata={"key": "val"},
        )
        assert issue.risk_level == RiskLevel.HIGH
        assert issue.metadata["key"] == "val"


# --- Tests ScanResult ---

class TestScanResult:
    def test_empty(self):
        r = ScanResult(module_name="test")
        assert r.issue_count == 0
        assert r.has_issues is False

    def test_with_issues(self):
        r = ScanResult(
            module_name="test",
            issues=[Issue(id="1", description="a"), Issue(id="2", description="b")],
        )
        assert r.issue_count == 2
        assert r.has_issues is True


# --- Tests FixResult ---

class TestFixResult:
    def test_success(self):
        r = FixResult(module_name="test", fixed=["a", "b"])
        assert r.fixed_count == 2
        assert r.success is True

    def test_with_errors(self):
        r = FixResult(module_name="test", errors=["err"])
        assert r.success is False


# --- Tests BaseModule (via DummyModule) ---

class TestBaseModule:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseModule()  # type: ignore[abstract]

    def test_properties(self):
        m = DummyModule()
        assert m.name == "dummy"
        assert m.description == "Module de test"
        assert m.risk_level == RiskLevel.LOW

    def test_scan(self):
        m = DummyModule()
        result = m.scan()
        assert result.module_name == "dummy"
        assert result.issue_count == 2

    def test_fix(self):
        m = DummyModule()
        scan = m.scan()
        fix = m.fix(scan)
        assert fix.fixed_count == 1
        assert fix.success is True

    def test_preview_with_issues(self):
        m = DummyModule()
        scan = m.scan()
        preview = m.preview(scan)
        assert "[dummy]" in preview
        assert "2 probleme(s)" in preview
        assert "[AUTO]" in preview
        assert "[MANUEL]" in preview

    def test_preview_no_issues(self):
        m = DummyModule()
        empty = ScanResult(module_name="dummy")
        preview = m.preview(empty)
        assert "Aucun probleme" in preview
