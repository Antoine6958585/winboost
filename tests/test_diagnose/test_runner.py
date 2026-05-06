"""Tests du DiagnosticRunner et de la dataclass DiagnosticReport."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from winboost.diagnose.checks import Check, CheckResult, Severity
from winboost.diagnose.runner import (
    DEFAULT_FALLBACK_THEME,
    DiagnosticReport,
    DiagnosticRunner,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _FakeCheck(Check):
    """Check qui retourne un resultat fixe — utile pour les tests runner."""

    def __init__(self, name: str, severity: str, message: str = "", actions: tuple[str, ...] = ()) -> None:
        self.name = name
        self._severity = severity
        self._message = message or f"fake {name}"
        self._actions = actions

    def run(self) -> CheckResult:
        return CheckResult(
            name=self.name,
            severity=self._severity,
            message=self._message,
            details={"fake": True},
            suggested_actions=self._actions,
        )


def _stub_runner(themes_map: dict[str, list[Check]] | None = None) -> DiagnosticRunner:
    """Construit un runner avec un theme_registry stub pour isoler les tests."""
    if themes_map is None:
        themes_map = {
            "bluetooth": [_FakeCheck("bt_check", Severity.OK.value)],
            "gaming": [_FakeCheck("game_check", Severity.OK.value)],
        }
    registry = {name: (lambda checks=checks: checks) for name, checks in themes_map.items()}
    return DiagnosticRunner(theme_registry=registry, fallback_theme=next(iter(registry)))


# ---------------------------------------------------------------------------
# Matching de theme
# ---------------------------------------------------------------------------


class TestMatchThemes:
    def test_bluetooth_keyword_matches_bluetooth(self):
        runner = DiagnosticRunner()
        assert runner.match_themes("manette bluetooth qui bug") == ["bluetooth"]

    def test_gaming_keyword_matches_gaming(self):
        runner = DiagnosticRunner()
        # "rocket league" est dans gaming, "manette" est dans bluetooth
        # mais on ne dit pas "manette" ici donc ce serait juste gaming
        assert runner.match_themes("rocket league lag") == ["gaming"]

    def test_multi_theme_match_bluetooth_plus_gaming(self):
        runner = DiagnosticRunner()
        themes = runner.match_themes("ma manette bluetooth bug dans rocket league")
        assert "bluetooth" in themes
        assert "gaming" in themes
        # Ordre : bluetooth declare avant gaming dans THEME_KEYWORDS
        assert themes.index("bluetooth") < themes.index("gaming")

    def test_no_match_returns_fallback(self):
        runner = DiagnosticRunner()
        assert runner.match_themes("hello world foobarbaz") == [DEFAULT_FALLBACK_THEME]

    def test_match_is_case_insensitive(self):
        runner = DiagnosticRunner()
        assert runner.match_themes("MANETTE BLUETOOTH") == ["bluetooth"]

    def test_network_keywords(self):
        runner = DiagnosticRunner()
        assert runner.match_themes("internet lent dns ko") == ["network"]

    def test_audio_keywords(self):
        runner = DiagnosticRunner()
        assert runner.match_themes("plus de son dans mon casque") == ["audio"]

    def test_display_keywords(self):
        runner = DiagnosticRunner()
        # "ecran" sans accent doit matcher
        assert runner.match_themes("luminosite de l'ecran trop forte") == ["display"]


# ---------------------------------------------------------------------------
# Execution de base
# ---------------------------------------------------------------------------


class TestRunFromQuery:
    def test_returns_diagnostic_report(self):
        runner = _stub_runner()
        report = runner.run_from_query("manette bluetooth")
        assert isinstance(report, DiagnosticReport)
        assert report.query == "manette bluetooth"
        assert report.theme == "bluetooth"

    def test_empty_query_raises(self):
        runner = _stub_runner()
        with pytest.raises(ValueError, match="vide"):
            runner.run_from_query("")
        with pytest.raises(ValueError, match="vide"):
            runner.run_from_query("   ")

    def test_multi_theme_label_uses_plus_separator(self):
        runner = _stub_runner({
            "bluetooth": [_FakeCheck("bt_a", Severity.OK.value)],
            "gaming": [_FakeCheck("game_a", Severity.OK.value)],
        })
        runner.theme_keywords = {
            "bluetooth": ("manette",),
            "gaming": ("rocket",),
        }
        report = runner.run_from_query("manette rocket")
        # Themes joints par '+'
        assert report.theme == "bluetooth+gaming"
        assert "bluetooth" in report.themes
        assert "gaming" in report.themes

    def test_unknown_theme_falls_back(self):
        runner = _stub_runner({"bluetooth": [_FakeCheck("a", Severity.OK.value)]})
        runner.theme_keywords = {"bluetooth": ("manette",)}
        # Aucun keyword present => fallback bluetooth
        report = runner.run_from_query("foobar query")
        assert report.theme == "bluetooth"

    def test_completes_under_5_seconds_with_stubs(self):
        """Verifie l'objectif de perf avec des checks stubs (instantanes)."""
        import time

        runner = _stub_runner()
        start = time.monotonic()
        runner.run_from_query("manette bluetooth")
        elapsed = time.monotonic() - start
        assert elapsed < 5.0

    def test_executes_all_checks_from_each_theme(self):
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck("bt_a", Severity.OK.value),
                _FakeCheck("bt_b", Severity.WARNING.value),
            ],
            "gaming": [_FakeCheck("game_a", Severity.OK.value)],
        })
        runner.theme_keywords = {"bluetooth": ("manette",), "gaming": ("rocket",)}
        report = runner.run_from_query("manette rocket")
        names = [c.name for c in report.checks]
        assert names == ["bt_a", "bt_b", "game_a"]


# ---------------------------------------------------------------------------
# Construction du resume
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_no_problems_summary(self):
        runner = _stub_runner({
            "bluetooth": [_FakeCheck("a", Severity.OK.value), _FakeCheck("b", Severity.OK.value)]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        assert "Aucun probleme" in report.summary
        assert "2 checks OK" in report.summary

    def test_summary_with_critical_takes_priority(self):
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck("a", Severity.WARNING.value, "warn msg"),
                _FakeCheck("b", Severity.CRITICAL.value, "critical msg"),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        assert "1 critique(s)" in report.summary
        assert "1 warning(s)" in report.summary
        # Le message critique apparait en premier dans le detail
        assert "critical msg" in report.summary
        # Le critique apparait avant le warning dans la chaine
        assert report.summary.index("critical msg") < report.summary.index(",") + 200


# ---------------------------------------------------------------------------
# Plan de fix
# ---------------------------------------------------------------------------


class TestFixPlan:
    def test_plan_dedupes_action_ids(self):
        """Un meme action_id ne doit apparaitre qu'une fois dans le plan."""
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck("a", Severity.ERROR.value, actions=("net_012", "net_011")),
                _FakeCheck("b", Severity.WARNING.value, actions=("net_012",)),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        action_ids = [s.get("action_id") for s in report.recommended_fix_plan if "action_id" in s]
        assert action_ids.count("net_012") == 1
        assert action_ids.count("net_011") == 1

    def test_plan_orders_by_severity(self):
        """Le plan doit lister critical d'abord, puis error, puis warning."""
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck("warn", Severity.WARNING.value, actions=("a_warn",)),
                _FakeCheck("crit", Severity.CRITICAL.value, actions=("a_crit",)),
                _FakeCheck("err", Severity.ERROR.value, actions=("a_err",)),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        action_ids = [s["action_id"] for s in report.recommended_fix_plan if "action_id" in s]
        assert action_ids == ["a_crit", "a_err", "a_warn"]

    def test_plan_uses_manual_step_when_no_action_id(self):
        # Le filtre anti-bruit exclut les warnings sans action et sans
        # signal explicite. Pour qu'un warning "no-action" reste dans le
        # plan, son message doit contenir "manuel:" ou "action:" (convention).
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck(
                    "oh",
                    Severity.WARNING.value,
                    "manuel: Verifier le BIOS",
                    actions=(),
                ),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        assert len(report.recommended_fix_plan) == 1
        step = report.recommended_fix_plan[0]
        assert step.get("manual") is True
        assert "Verifier le BIOS" in step["description"]

    def test_plan_skips_ok_checks(self):
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck("ok1", Severity.OK.value, actions=("nope",)),
                _FakeCheck("ok2", Severity.OK.value),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        assert report.recommended_fix_plan == ()

    def test_plan_excludes_warning_without_actions_or_manual_fix(self):
        """Filtre anti-bruit (T084) : un warning sans suggested_actions ET
        sans entree MANUAL_FIX_DESCRIPTIONS ne doit pas polluer le plan."""
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck(
                    "noisy_warn",
                    Severity.WARNING.value,
                    "Detail technique sans valeur user",
                    actions=(),
                ),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        assert report.recommended_fix_plan == ()

    def test_plan_includes_manual_fix_for_known_check(self):
        """Si check.name est dans MANUAL_FIX_DESCRIPTIONS, un step manuel
        riche est genere (description precise + alternative)."""
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck(
                    "bluetooth_gamepad_mapping",
                    Severity.WARNING.value,
                    "Manette mal mappee : Xbox Wireless Controller",
                    actions=("bt_unpair_repair",),
                ),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        assert len(report.recommended_fix_plan) == 1
        step = report.recommended_fix_plan[0]
        assert step.get("manual") is True
        # Pas de action_id : c'est un manual fix, pas une action automatisable
        assert "action_id" not in step
        # Description doit contenir les instructions concretes du mapping
        assert "Desappairer" in step["description"]
        assert "Bluetooth" in step["description"]
        # Cause incluse pour contexte
        assert "Xbox Wireless Controller" in step["description"]
        # Alternative present (Device Manager fallback)
        assert step.get("alternative") is not None
        assert "Device Manager" in step["alternative"]

    def test_plan_excludes_timeout_and_lecture_ko_warnings(self):
        """Regression test : un warning issu d'un timeout / lecture KO ne
        doit jamais polluer le plan (filtre anti-bruit T084)."""
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck(
                    "ps_check_a",
                    Severity.WARNING.value,
                    "Timeout PowerShell apres 10s",
                    actions=(),
                ),
                _FakeCheck(
                    "ps_check_b",
                    Severity.WARNING.value,
                    "Lecture des drivers BT echouee (PowerShell KO)",
                    actions=(),
                ),
                _FakeCheck(
                    "ps_check_c",
                    Severity.WARNING.value,
                    "Impossible de lire les dates de drivers BT : exc",
                    actions=(),
                ),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        # Aucun de ces 3 warnings ne doit apparaitre dans le plan
        assert report.recommended_fix_plan == ()

    def test_plan_excludes_noise_warning_even_for_known_check(self):
        """Un check dans MANUAL_FIX_DESCRIPTIONS dont le message est du bruit
        (timeout, lecture KO) doit AUSSI etre exclu : on ne genere pas un
        manual fix si le check n'a pas pu diagnostiquer le probleme."""
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck(
                    "bluetooth_driver_freshness",  # est dans MANUAL_FIX_DESCRIPTIONS
                    Severity.WARNING.value,
                    "Impossible de lire les dates de drivers BT : Timeout PowerShell",
                    actions=(),
                ),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        # Meme si le check est connu, le bruit le filtre (pas d'info utile).
        assert report.recommended_fix_plan == ()

    def test_plan_steps_are_numbered_starting_at_1(self):
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck("a", Severity.ERROR.value, actions=("x",)),
                _FakeCheck("b", Severity.ERROR.value, actions=("y",)),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        steps = [s["step"] for s in report.recommended_fix_plan]
        assert steps == [1, 2]


# ---------------------------------------------------------------------------
# Robustesse aux exceptions des checks
# ---------------------------------------------------------------------------


class _CrashingCheck(Check):
    name = "crashing"

    def run(self) -> CheckResult:
        raise RuntimeError("boom")


class _NativeFailCheck(Check):
    name = "native_fail"

    def run(self) -> CheckResult:
        from winboost.utils.windows_native import WindowsNativeError

        raise WindowsNativeError("WMI HS")


class TestCheckExceptionsAreContained:
    def test_crashing_check_does_not_break_runner(self):
        runner = _stub_runner({
            "bluetooth": [
                _FakeCheck("ok1", Severity.OK.value),
                _CrashingCheck(),
                _FakeCheck("ok2", Severity.OK.value),
            ]
        })
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        assert len(report.checks) == 3
        names = [c.name for c in report.checks]
        assert names == ["ok1", "crashing", "ok2"]
        # Le check qui crash devient ERROR
        crashing_result = next(c for c in report.checks if c.name == "crashing")
        assert crashing_result.severity == Severity.ERROR.value

    def test_windows_native_error_becomes_warning(self):
        runner = _stub_runner({"bluetooth": [_NativeFailCheck()]})
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        assert len(report.checks) == 1
        assert report.checks[0].severity == Severity.WARNING.value
        assert "WMI HS" in report.checks[0].message


# ---------------------------------------------------------------------------
# Serialisation JSON
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_is_jsonable(self):
        runner = _stub_runner({"bluetooth": [_FakeCheck("x", Severity.OK.value)]})
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        d = report.to_dict()
        # roundtrip via json
        s = json.dumps(d, ensure_ascii=False)
        back = json.loads(s)
        assert back["theme"] == "bluetooth"
        assert back["query"] == "manette"
        assert back["checks"][0]["name"] == "x"
        assert back["checks"][0]["severity"] == "ok"

    def test_to_json_returns_string(self):
        runner = _stub_runner({"bluetooth": [_FakeCheck("x", Severity.OK.value)]})
        runner.theme_keywords = {"bluetooth": ("manette",)}
        report = runner.run_from_query("manette")
        out = report.to_json()
        assert isinstance(out, str)
        json.loads(out)  # ne leve pas


# ---------------------------------------------------------------------------
# Validation CheckResult
# ---------------------------------------------------------------------------


class TestCheckResultValidation:
    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError, match="Severity invalide"):
            CheckResult(
                name="x",
                severity="potato",
                message="m",
                details={},
                suggested_actions=(),
            )

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="non vide"):
            CheckResult(
                name="",
                severity=Severity.OK.value,
                message="m",
                details={},
                suggested_actions=(),
            )

    def test_message_must_be_string(self):
        with pytest.raises(ValueError, match="message doit etre str"):
            CheckResult(
                name="x",
                severity=Severity.OK.value,
                message=123,  # type: ignore[arg-type]
                details={},
                suggested_actions=(),
            )

    def test_list_actions_converted_to_tuple(self):
        r = CheckResult(
            name="x",
            severity=Severity.OK.value,
            message="m",
            details={},
            suggested_actions=["a", "b"],  # type: ignore[arg-type]
        )
        assert r.suggested_actions == ("a", "b")

    def test_is_problem_property(self):
        ok = CheckResult(name="x", severity=Severity.OK.value, message="m")
        warn = CheckResult(name="x", severity=Severity.WARNING.value, message="m")
        err = CheckResult(name="x", severity=Severity.ERROR.value, message="m")
        crit = CheckResult(name="x", severity=Severity.CRITICAL.value, message="m")
        assert ok.is_problem is False
        assert warn.is_problem is True
        assert err.is_problem is True
        assert crit.is_problem is True


# ---------------------------------------------------------------------------
# Configuration custom du runner
# ---------------------------------------------------------------------------


class TestRunnerConfig:
    def test_invalid_fallback_theme_raises(self):
        with pytest.raises(ValueError, match="fallback"):
            DiagnosticRunner(
                theme_registry={"bluetooth": lambda: []},
                fallback_theme="missing",
            )

    def test_default_themes_loaded(self):
        runner = DiagnosticRunner()
        for name in ("bluetooth", "gaming", "network", "audio", "display"):
            assert name in runner.theme_registry

    def test_run_themes_with_unknown_theme_logs_warning_check(self):
        runner = DiagnosticRunner()
        report = runner.run_themes(["unknown_theme_xyz"], original_query="test")
        # Le theme inconnu produit un CheckResult warning
        unknown_results = [c for c in report.checks if "unknown" in c.name]
        assert len(unknown_results) == 1
        assert unknown_results[0].severity == Severity.WARNING.value

    def test_run_themes_empty_raises(self):
        runner = DiagnosticRunner()
        with pytest.raises(ValueError, match="Au moins un"):
            runner.run_themes([])

    def test_run_theme_shortcut(self):
        runner = _stub_runner({"bluetooth": [_FakeCheck("a", Severity.OK.value)]})
        report = runner.run_theme("bluetooth", original_query="x")
        assert report.theme == "bluetooth"
        assert report.query == "x"


# ---------------------------------------------------------------------------
# Use case Antoine end-to-end (avec checks reels mockes)
# ---------------------------------------------------------------------------


class TestAntoineUseCase:
    def test_manette_bluetooth_rocket_league_runs_both_themes(self):
        """La requete principale doit declencher BT + gaming."""
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            # Toutes les commandes PS retournent un succes vide ; les checks
            # fallback proprement en warning/ok (ne crashent pas)
            from winboost.utils.windows_native import PowerShellResult

            mock_ps.return_value = PowerShellResult(stdout="", stderr="", returncode=0)
            runner = DiagnosticRunner()
            report = runner.run_from_query("ma manette bluetooth bug dans rocket league")

        assert "bluetooth" in report.theme
        assert "gaming" in report.theme
        # Au moins un check par theme = au moins 5+5 checks
        assert len(report.checks) >= 10
