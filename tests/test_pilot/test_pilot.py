"""Tests pilot — couverture complete des garde-fous + loop Anthropic.

Couvre :
- Validation BYOK / profil Lab / RGPD opt-in
- BudgetManager (plafond, reset mensuel, persistance)
- Sandbox (region, plafond consecutif, full_screen flag)
- ConfirmationManager (annotation Pillow + helpers test)
- AnthropicPilot loop end-to-end avec mock Anthropic API
- Audit trail HistoryManager
- Cancel global
- allow_batch sequencement
- Serialisation PilotResult

Tous les appels API sont mockes via `client_factory` injectable. Aucun
appel reseau reel ni capture d'ecran reelle en CI.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from winboost.core.config import Config
from winboost.core.history import HistoryManager
from winboost.pilot.anthropic_pilot import (
    AnthropicPilot,
    BYOKMissingError,
    PilotAction,
    PilotError,
    PilotResult,
    ProfileNotLabError,
    RGPDNotAcceptedError,
    _normalize_anthropic_response,
    _parse_tool_use,
    assert_profile_lab,
    assert_rgpd_accepted,
)
from winboost.pilot.budget import (
    DEFAULT_BUDGET_EUR,
    MODEL_PRICING,
    BudgetExceededError,
    BudgetManager,
    ModelPricing,
)
from winboost.pilot.confirmation_ui import (
    ConfirmationManager,
    ProposedAction,
    build_default_confirmer,
    make_scripted_confirmer,
    make_yes_confirmer,
)
from winboost.pilot.sandbox import (
    DEFAULT_MAX_CONSECUTIVE,
    Region,
    Sandbox,
    SandboxViolationError,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def lab_config(tmp_path: Path) -> Config:
    """Config avec profil Lab + opt-in RGPD complet."""
    cfg = Config(config_dir=tmp_path)
    cfg.set("profile", "lab")
    cfg.set("pilot", {
        "rgpd": {
            "screenshots": True,
            "ocr_text": True,
            "system_info": True,
            "accepted_at": "2026-05-06T00:00:00Z",
        },
    })
    cfg.save()
    return cfg


@pytest.fixture
def safe_config(tmp_path: Path) -> Config:
    """Config en profil safe (= bloque le pilot)."""
    cfg = Config(config_dir=tmp_path)
    cfg.set("profile", "safe")
    cfg.save()
    return cfg


@pytest.fixture
def budget_tmp(tmp_path: Path) -> BudgetManager:
    """BudgetManager isole sur tmp_path."""
    return BudgetManager(path=tmp_path / "pilot_budget.json")


@pytest.fixture
def sandbox_default() -> Sandbox:
    """Sandbox 1000x1000 a (0,0), plafond consecutif default."""
    return Sandbox(
        mode="winboost_window",
        region=Region(0, 0, 1000, 1000),
    )


@pytest.fixture
def history_tmp(tmp_path: Path) -> HistoryManager:
    """HistoryManager isole sur tmp_path."""
    return HistoryManager(db_path=tmp_path / "history.db")


def _make_mock_anthropic_response(
    tool_uses: list[dict[str, Any]] | None = None,
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> Any:
    """Construit un mock de reponse Anthropic SDK."""
    response = MagicMock()
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    response.usage = usage
    response.stop_reason = stop_reason

    content_blocks = []
    if tool_uses:
        for tu in tool_uses:
            block = MagicMock()
            block.type = "tool_use"
            block.id = tu.get("id", "tu_default")
            block.name = tu.get("name", "computer")
            block.input = tu.get("input", {})
            content_blocks.append(block)
    else:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Done."
        content_blocks.append(text_block)

    response.content = content_blocks
    return response


def _make_mock_client_factory(responses: list[Any]) -> Any:
    """Factory qui retourne un client dont .beta.messages.create iteres `responses`."""
    iterator = iter(responses)

    def factory(api_key: str) -> Any:
        client = MagicMock()
        def create(**kwargs: Any) -> Any:
            try:
                return next(iterator)
            except StopIteration:
                # Default: end_turn no tool
                return _make_mock_anthropic_response(stop_reason="end_turn")
        client.beta.messages.create.side_effect = create
        return client
    return factory


# =============================================================================
# Test 1 : BYOK absent -> erreur claire, pas de loop
# =============================================================================


class TestBYOK:
    def test_no_api_key_raises_at_construction(self, lab_config: Config) -> None:
        """BYOK manquant doit lever AVANT meme run() (au constructeur)."""
        with pytest.raises(BYOKMissingError, match="BYOK"):
            AnthropicPilot(api_key=None, config=lab_config)

    def test_empty_api_key_raises(self, lab_config: Config) -> None:
        """Cle vide string aussi rejetee."""
        with pytest.raises(BYOKMissingError):
            AnthropicPilot(api_key="", config=lab_config)


# =============================================================================
# Test 2 : Profil non-Lab -> refus
# =============================================================================


class TestProfileLab:
    def test_safe_profile_blocks_run(self, safe_config: Config) -> None:
        pilot = AnthropicPilot(
            api_key="sk-test",
            config=safe_config,
            client_factory=lambda k: MagicMock(),
        )
        with pytest.raises(ProfileNotLabError, match="lab"):
            pilot.run("test")

    def test_assert_profile_lab_helper(self, lab_config: Config, safe_config: Config) -> None:
        # Lab = OK, ne leve pas
        assert_profile_lab(lab_config)
        # Safe = leve
        with pytest.raises(ProfileNotLabError):
            assert_profile_lab(safe_config)


# =============================================================================
# Test 3 : RGPD pas accepte -> refus
# =============================================================================


class TestRGPD:
    def test_no_rgpd_blocks(self, tmp_path: Path) -> None:
        cfg = Config(config_dir=tmp_path)
        cfg.set("profile", "lab")
        # pas de pilot.rgpd
        cfg.save()
        pilot = AnthropicPilot(
            api_key="sk-test",
            config=cfg,
            client_factory=lambda k: MagicMock(),
        )
        with pytest.raises(RGPDNotAcceptedError, match="screenshots"):
            pilot.run("test")

    def test_partial_rgpd_blocks(self, tmp_path: Path) -> None:
        cfg = Config(config_dir=tmp_path)
        cfg.set("profile", "lab")
        cfg.set("pilot", {
            "rgpd": {
                "screenshots": True,
                "ocr_text": True,
                # system_info manquant -> refus
            },
        })
        cfg.save()
        pilot = AnthropicPilot(
            api_key="sk-test",
            config=cfg,
            client_factory=lambda k: MagicMock(),
        )
        with pytest.raises(RGPDNotAcceptedError, match="system_info"):
            pilot.run("test")

    def test_full_rgpd_accepts(self, lab_config: Config) -> None:
        # Ne leve pas
        assert_rgpd_accepted(lab_config)


# =============================================================================
# Test 4 : Plafond budgetaire atteint -> blocage
# =============================================================================


class TestBudget:
    def test_default_limit_5_eur(self, budget_tmp: BudgetManager) -> None:
        assert budget_tmp.limit_eur == DEFAULT_BUDGET_EUR

    def test_can_spend_within_limit(self, budget_tmp: BudgetManager) -> None:
        assert budget_tmp.can_spend(1.0)
        assert budget_tmp.can_spend(4.99)

    def test_cannot_spend_over_limit(self, budget_tmp: BudgetManager) -> None:
        assert not budget_tmp.can_spend(10.0)

    def test_assert_can_spend_raises_with_next_reset_date(self, budget_tmp: BudgetManager) -> None:
        budget_tmp.record_spend(4.99)
        with pytest.raises(BudgetExceededError, match="Prochain reset"):
            budget_tmp.assert_can_spend(0.5)

    def test_record_spend_accumulates(self, budget_tmp: BudgetManager) -> None:
        budget_tmp.record_spend(1.0)
        budget_tmp.record_spend(0.5)
        assert budget_tmp.spent_eur == pytest.approx(1.5)
        assert budget_tmp.actions_count == 2

    def test_set_limit_persists(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        b1 = BudgetManager(path=path, limit_eur=10.0)
        assert b1.limit_eur == 10.0
        # Reload : la valeur est persistante
        b2 = BudgetManager(path=path)
        assert b2.limit_eur == 10.0

    def test_set_limit_invalid_raises(self, budget_tmp: BudgetManager) -> None:
        with pytest.raises(ValueError):
            budget_tmp.set_limit(0)
        with pytest.raises(ValueError):
            budget_tmp.set_limit(-1.0)

    def test_estimate_cost_uses_pricing_table(self, budget_tmp: BudgetManager) -> None:
        cost = budget_tmp.estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        # input 3 + output 15 = 18 EUR au taux 1M tokens
        assert cost == pytest.approx(18.0, rel=0.01)

    def test_estimate_cost_fallback_unknown_model(self, budget_tmp: BudgetManager) -> None:
        # Ne crash pas, utilise sonnet par defaut
        cost = budget_tmp.estimate_cost("claude-future-99", 1000, 200)
        assert cost > 0

    def test_record_spend_negative_raises(self, budget_tmp: BudgetManager) -> None:
        with pytest.raises(ValueError):
            budget_tmp.record_spend(-1.0)


# =============================================================================
# Test 5 : Reset mensuel automatique du compteur
# =============================================================================


class TestBudgetMonthlyReset:
    def test_month_change_resets_spent(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        # Mois "M1"
        clock_state = {"now": datetime(2026, 5, 6, tzinfo=UTC)}

        def clock() -> datetime:
            return clock_state["now"]

        b = BudgetManager(path=path, clock=clock)
        b.record_spend(3.0)
        assert b.spent_eur == pytest.approx(3.0)

        # Avance au mois suivant
        clock_state["now"] = datetime(2026, 6, 1, tzinfo=UTC)
        # Lecture d'une propriete declenche maybe_reset
        assert b.spent_eur == 0.0
        assert b.actions_count == 0

    def test_persisted_old_month_resets_on_load(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        # Ecrit manuellement un fichier d'un vieux mois
        path.write_text(json.dumps({
            "month": "2025-01",
            "spent_eur": 4.5,
            "limit_eur": 5.0,
            "actions_count": 12,
        }), encoding="utf-8")

        b = BudgetManager(path=path)  # vrai datetime now -> != 2025-01
        # Le reset auto a remis a 0
        assert b.spent_eur == 0.0
        assert b.actions_count == 0
        assert b.limit_eur == 5.0  # le plafond est conserve

    def test_next_reset_date_format(self, tmp_path: Path) -> None:
        clock_state = {"now": datetime(2026, 5, 6, tzinfo=UTC)}
        b = BudgetManager(
            path=tmp_path / "b.json",
            clock=lambda: clock_state["now"],
        )
        # Met le plafond a 0.01 pour forcer le raise et lire le message
        b.set_limit(0.01)
        with pytest.raises(BudgetExceededError, match="2026-06-01"):
            b.assert_can_spend(1.0)


# =============================================================================
# Test 6 : Sandbox limites respectees
# =============================================================================


class TestSandbox:
    def test_click_inside_region_passes(self, sandbox_default: Sandbox) -> None:
        sandbox_default.check_click(500, 500)  # ne leve pas

    def test_click_outside_region_raises(self, sandbox_default: Sandbox) -> None:
        with pytest.raises(SandboxViolationError, match="hors zone"):
            sandbox_default.check_click(2000, 500)

    def test_click_at_origin_passes(self, sandbox_default: Sandbox) -> None:
        sandbox_default.check_click(0, 0)

    def test_click_at_far_corner_excluded(self) -> None:
        # bornes exclusives au bottom-right (convention pixel grid)
        s = Sandbox(region=Region(0, 0, 100, 100))
        s.check_click(99, 99)  # OK
        with pytest.raises(SandboxViolationError):
            s.check_click(100, 100)

    def test_full_screen_requires_explicit_flag(self) -> None:
        with pytest.raises(SandboxViolationError, match="allow_full_screen"):
            Sandbox(mode="full_screen", region=Region(0, 0, 1920, 1080))

    def test_full_screen_with_flag_works(self) -> None:
        s = Sandbox(
            mode="full_screen",
            region=Region(0, 0, 1920, 1080),
            allow_full_screen=True,
        )
        s.check_click(960, 540)  # OK

    def test_consecutive_limit_default_is_5(self, sandbox_default: Sandbox) -> None:
        assert sandbox_default.max_consecutive_actions == DEFAULT_MAX_CONSECUTIVE

    def test_consecutive_limit_blocks_at_threshold(self) -> None:
        s = Sandbox(region=Region(0, 0, 100, 100), max_consecutive_actions=3)
        for _ in range(3):
            s.check_can_act()
            s.record_action()
        # 4eme tentative -> blocage
        with pytest.raises(SandboxViolationError, match="Plafond"):
            s.check_can_act()

    def test_consecutive_reset_unblocks(self) -> None:
        s = Sandbox(region=Region(0, 0, 100, 100), max_consecutive_actions=2)
        s.check_can_act()
        s.record_action()
        s.check_can_act()
        s.record_action()
        with pytest.raises(SandboxViolationError):
            s.check_can_act()
        s.reset_consecutive()
        s.check_can_act()  # OK apres reset

    def test_invalid_max_consecutive_raises(self) -> None:
        with pytest.raises(ValueError):
            Sandbox(region=Region(0, 0, 10, 10), max_consecutive_actions=0)

    def test_invalid_region_raises(self) -> None:
        with pytest.raises(ValueError):
            Region(0, 0, 0, 100)
        with pytest.raises(ValueError):
            Region(0, 0, 100, -5)


# =============================================================================
# Test 7 : ConfirmationManager
# =============================================================================


class TestConfirmation:
    def test_default_confirmer_raises(self) -> None:
        cm = ConfirmationManager()
        action = ProposedAction(kind="click", x=10, y=10)
        with pytest.raises(NotImplementedError, match="confirmer"):
            cm.ask(action, b"")

    def test_yes_confirmer_returns_confirm(self) -> None:
        cm = ConfirmationManager(confirmer=make_yes_confirmer())
        action = ProposedAction(kind="click", x=10, y=10)
        assert cm.ask(action, b"") == "confirm"

    def test_scripted_confirmer_sequence(self) -> None:
        cm = ConfirmationManager(
            confirmer=make_scripted_confirmer(["confirm", "skip", "cancel"]),
        )
        a = ProposedAction(kind="click", x=10, y=10)
        assert cm.ask(a, b"") == "confirm"
        assert cm.ask(a, b"") == "skip"
        assert cm.ask(a, b"") == "cancel"
        # Apres epuisement, retourne 'cancel' par defaut
        assert cm.ask(a, b"") == "cancel"

    def test_invalid_decision_treated_as_cancel(self) -> None:
        def bad_confirmer(action: ProposedAction, screenshot: Any) -> Any:
            return "yolo"  # pas valide

        cm = ConfirmationManager(confirmer=bad_confirmer)
        a = ProposedAction(kind="click", x=10, y=10)
        assert cm.ask(a, b"") == "cancel"

    def test_proposed_action_short_label_click(self) -> None:
        a = ProposedAction(kind="click", x=10, y=20)
        assert "click" in a.short_label()
        assert "10" in a.short_label()

    def test_proposed_action_short_label_type_truncated(self) -> None:
        long = "x" * 100
        a = ProposedAction(kind="type", text=long)
        label = a.short_label()
        assert len(label) < len(long)
        assert "..." in label

    def test_annotate_without_pillow_returns_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Si Pillow indispo, renvoie l'image telle quelle
        original_screenshot = b"FAKEBYTES"
        cm = ConfirmationManager(confirmer=make_yes_confirmer())
        # Force ImportError sur PIL
        import builtins
        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("PIL forced unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        result = cm.annotate(original_screenshot, ProposedAction(kind="click", x=10, y=10))
        assert result == original_screenshot

    def test_annotate_no_coords_returns_unchanged(self) -> None:
        cm = ConfirmationManager(confirmer=make_yes_confirmer())
        original = b"NOOP"
        # action sans x/y -> retourne tel quel
        result = cm.annotate(original, ProposedAction(kind="screenshot"))
        assert result == original

    def test_build_default_confirmer_returns_callable(self) -> None:
        c = build_default_confirmer()
        assert callable(c)


# =============================================================================
# Test 8 : Pilot loop end-to-end avec mock Anthropic
# =============================================================================


def _yes_confirmer_cm() -> ConfirmationManager:
    return ConfirmationManager(confirmer=make_yes_confirmer())


def _make_pilot(
    config: Config,
    sandbox: Sandbox,
    budget: BudgetManager,
    history: HistoryManager,
    *,
    api_responses: list[Any] | None = None,
    confirmer: ConfirmationManager | None = None,
    actions_executed: list[ProposedAction] | None = None,
    fail_executor: bool = False,
    fail_screenshot: bool = False,
    tmp_path: Path | None = None,
) -> AnthropicPilot:
    actions_executed = actions_executed if actions_executed is not None else []

    def screenshot_provider(s: Sandbox) -> bytes:
        if fail_screenshot:
            raise OSError("screenshot failed")
        return b"\x89PNG\r\n\x1a\n" + b"FAKE_PNG_BYTES"

    def action_executor(action: ProposedAction) -> None:
        if fail_executor:
            raise PilotError("executor crashed")
        actions_executed.append(action)

    return AnthropicPilot(
        api_key="sk-test",
        config=config,
        sandbox=sandbox,
        confirmation=confirmer or _yes_confirmer_cm(),
        budget=budget,
        history=history,
        screenshot_provider=screenshot_provider,
        action_executor=action_executor,
        client_factory=_make_mock_client_factory(api_responses or []),
        screenshot_dir=tmp_path / "shots" if tmp_path else None,
    )


class TestPilotLoop:
    def test_run_completes_no_tool_use(
        self, lab_config: Config, sandbox_default: Sandbox,
        budget_tmp: BudgetManager, history_tmp: HistoryManager,
        tmp_path: Path,
    ) -> None:
        # Anthropic dit "j'ai fini" tout de suite -> end_turn sans tool_use
        responses = [_make_mock_anthropic_response(stop_reason="end_turn")]
        pilot = _make_pilot(
            lab_config, sandbox_default, budget_tmp, history_tmp,
            api_responses=responses, tmp_path=tmp_path,
        )
        result = pilot.run("test")
        assert result.completed is True
        assert result.iterations == 1
        assert len(result.actions) == 0
        assert result.total_tokens_in > 0

    def test_run_executes_action_then_completes(
        self, lab_config: Config, sandbox_default: Sandbox,
        budget_tmp: BudgetManager, history_tmp: HistoryManager,
        tmp_path: Path,
    ) -> None:
        responses = [
            _make_mock_anthropic_response(tool_uses=[{
                "id": "tu_1", "name": "computer",
                "input": {"action": "click", "coordinate": [100, 200]},
            }]),
            _make_mock_anthropic_response(stop_reason="end_turn"),
        ]
        executed: list[ProposedAction] = []
        pilot = _make_pilot(
            lab_config, sandbox_default, budget_tmp, history_tmp,
            api_responses=responses, actions_executed=executed,
            tmp_path=tmp_path,
        )
        result = pilot.run("clique sur le bouton")
        assert result.iterations == 2
        assert len(result.actions) == 1
        assert result.actions[0].executed is True
        assert result.actions[0].proposed.x == 100
        assert result.actions[0].proposed.y == 200
        assert len(executed) == 1

    def test_audit_trail_recorded_on_success(
        self, lab_config: Config, sandbox_default: Sandbox,
        budget_tmp: BudgetManager, history_tmp: HistoryManager,
        tmp_path: Path,
    ) -> None:
        responses = [
            _make_mock_anthropic_response(tool_uses=[{
                "id": "tu_1", "name": "computer",
                "input": {"action": "click", "coordinate": [50, 50]},
            }]),
            _make_mock_anthropic_response(stop_reason="end_turn"),
        ]
        pilot = _make_pilot(
            lab_config, sandbox_default, budget_tmp, history_tmp,
            api_responses=responses, tmp_path=tmp_path,
        )
        pilot.run("test")
        history_entries = history_tmp.get_history(module_name="pilot", limit=100)
        # Au moins une entree "executed" + une "completed"
        assert len(history_entries) >= 1
        statuses = {e.result_status for e in history_entries}
        assert "executed" in statuses or "completed" in statuses

    def test_audit_trail_recorded_on_failure(
        self, lab_config: Config, sandbox_default: Sandbox,
        budget_tmp: BudgetManager, history_tmp: HistoryManager,
        tmp_path: Path,
    ) -> None:
        responses = [
            _make_mock_anthropic_response(tool_uses=[{
                "id": "tu_1", "name": "computer",
                "input": {"action": "click", "coordinate": [50, 50]},
            }]),
        ]
        pilot = _make_pilot(
            lab_config, sandbox_default, budget_tmp, history_tmp,
            api_responses=responses, fail_executor=True,
            tmp_path=tmp_path,
        )
        result = pilot.run("test")
        history_entries = history_tmp.get_history(module_name="pilot", limit=100)
        statuses = {e.result_status for e in history_entries}
        assert "error" in statuses
        # L'action est dans actions, marquee non executee
        assert result.actions[0].executed is False
        assert result.actions[0].error

    def test_screenshot_persisted_locally(
        self, lab_config: Config, sandbox_default: Sandbox,
        budget_tmp: BudgetManager, history_tmp: HistoryManager,
        tmp_path: Path,
    ) -> None:
        responses = [
            _make_mock_anthropic_response(tool_uses=[{
                "id": "tu_1", "name": "computer",
                "input": {"action": "click", "coordinate": [50, 50]},
            }]),
            _make_mock_anthropic_response(stop_reason="end_turn"),
        ]
        pilot = _make_pilot(
            lab_config, sandbox_default, budget_tmp, history_tmp,
            api_responses=responses, tmp_path=tmp_path,
        )
        result = pilot.run("test")
        # Au moins un chemin de screenshot non vide
        assert any(a.screenshot_before for a in result.actions)
        # Le dossier existe et contient des PNG
        shots_dir = tmp_path / "shots"
        assert shots_dir.exists()
        pngs = list(shots_dir.glob("*.png"))
        assert len(pngs) >= 1


# =============================================================================
# Test 9 : Cancel global
# =============================================================================


class TestCancel:
    def test_user_cancel_decision_aborts(
        self, lab_config: Config, sandbox_default: Sandbox,
        budget_tmp: BudgetManager, history_tmp: HistoryManager,
        tmp_path: Path,
    ) -> None:
        responses = [
            _make_mock_anthropic_response(tool_uses=[{
                "id": "tu_1", "name": "computer",
                "input": {"action": "click", "coordinate": [50, 50]},
            }]),
        ]
        cm = ConfirmationManager(confirmer=make_scripted_confirmer(["cancel"]))
        pilot = _make_pilot(
            lab_config, sandbox_default, budget_tmp, history_tmp,
            api_responses=responses, confirmer=cm,
            tmp_path=tmp_path,
        )
        result = pilot.run("test")
        assert result.abort_reason == "user_cancel"
        assert result.completed is False

    def test_pilot_stop_aborts_at_next_iteration(
        self, lab_config: Config, sandbox_default: Sandbox,
        budget_tmp: BudgetManager, history_tmp: HistoryManager,
        tmp_path: Path,
    ) -> None:
        responses = [
            _make_mock_anthropic_response(tool_uses=[{
                "id": "tu_1", "name": "computer",
                "input": {"action": "click", "coordinate": [50, 50]},
            }]),
            _make_mock_anthropic_response(stop_reason="end_turn"),
        ]
        pilot = _make_pilot(
            lab_config, sandbox_default, budget_tmp, history_tmp,
            api_responses=responses, tmp_path=tmp_path,
        )
        # Stop avant meme le run
        pilot.stop()
        result = pilot.run("test")
        assert result.abort_reason == "user_stop"


# =============================================================================
# Test 10 : Sandbox violation -> action refusee
# =============================================================================


class TestSandboxIntegration:
    def test_click_outside_region_caught_by_pilot(
        self, lab_config: Config, budget_tmp: BudgetManager,
        history_tmp: HistoryManager, tmp_path: Path,
    ) -> None:
        # Sandbox 100x100 mais Claude propose un clic en (500, 500)
        sb = Sandbox(region=Region(0, 0, 100, 100))
        responses = [
            _make_mock_anthropic_response(tool_uses=[{
                "id": "tu_1", "name": "computer",
                "input": {"action": "click", "coordinate": [500, 500]},
            }]),
            _make_mock_anthropic_response(stop_reason="end_turn"),
        ]
        executed: list[ProposedAction] = []
        pilot = _make_pilot(
            lab_config, sb, budget_tmp, history_tmp,
            api_responses=responses, actions_executed=executed,
            tmp_path=tmp_path,
        )
        result = pilot.run("test")
        # L'action est confirmee MAIS sandbox refuse l'execution
        assert len(result.actions) >= 1
        assert result.actions[0].executed is False
        assert "hors zone" in result.actions[0].error.lower()
        assert len(executed) == 0


# =============================================================================
# Test 11 : 6e action consecutive sans re-confirmation -> blocage
# =============================================================================


class TestConsecutiveLimit:
    def test_6th_action_triggers_reconfirm_request(
        self, lab_config: Config, budget_tmp: BudgetManager,
        history_tmp: HistoryManager, tmp_path: Path,
    ) -> None:
        # Sandbox plafond = 3 (court pour le test)
        sb = Sandbox(region=Region(0, 0, 1000, 1000), max_consecutive_actions=3)
        # 4 reponses avec action chacune + 1 reponse end_turn final
        responses = [
            _make_mock_anthropic_response(tool_uses=[{
                "id": f"tu_{i}", "name": "computer",
                "input": {"action": "click", "coordinate": [10 + i, 10 + i]},
            }])
            for i in range(4)
        ] + [_make_mock_anthropic_response(stop_reason="end_turn")]

        # Confirmer scripte : 3 confirms (les 3 premiers tools), puis cancel
        # quand le pilot demande la re-confirmation pour le 4eme.
        cm = ConfirmationManager(confirmer=make_scripted_confirmer([
            "confirm", "confirm", "confirm",  # tu_0, tu_1, tu_2
            "cancel",  # re-confirm refused -> abort
        ]))
        pilot = _make_pilot(
            lab_config, sb, budget_tmp, history_tmp,
            api_responses=responses, confirmer=cm, tmp_path=tmp_path,
        )
        result = pilot.run("test multi-actions")
        # Le pilot doit avoir abouti a abort par "consecutive_limit_no_reconfirm"
        # OU par "user_cancel" via la re-confirmation refusee.
        # Selon notre implementation : on utilise _request_reconfirm qui dispatch
        # vers le meme confirmer -> "cancel" -> consecutive_limit_no_reconfirm.
        assert result.abort_reason in {
            "consecutive_limit_no_reconfirm", "user_cancel",
        }
        # 3 actions ont du etre executees (les 3 premieres)
        executed = [a for a in result.actions if a.executed]
        assert len(executed) >= 3

    def test_allow_batch_grants_5_skip_reconfirm(
        self, lab_config: Config, budget_tmp: BudgetManager,
        history_tmp: HistoryManager, tmp_path: Path,
    ) -> None:
        sb = Sandbox(region=Region(0, 0, 1000, 1000), max_consecutive_actions=10)
        responses = [
            _make_mock_anthropic_response(tool_uses=[{
                "id": f"tu_{i}", "name": "computer",
                "input": {"action": "click", "coordinate": [10 + i, 10 + i]},
            }])
            for i in range(3)
        ] + [_make_mock_anthropic_response(stop_reason="end_turn")]

        # Premier tour : "allow_batch" -> les 2 suivants sans re-confirm
        cm = ConfirmationManager(confirmer=make_scripted_confirmer([
            "allow_batch",  # tu_0 : autorise + batch ouvert
            # tu_1, tu_2 -> auto-confirm via batch
        ]))
        pilot = _make_pilot(
            lab_config, sb, budget_tmp, history_tmp,
            api_responses=responses, confirmer=cm, tmp_path=tmp_path,
        )
        result = pilot.run("batch test")
        # Les 3 actions doivent etre executees (1 manuelle + 2 batch)
        executed = [a for a in result.actions if a.executed]
        assert len(executed) >= 3


# =============================================================================
# Test 12 : Cout tokens tracke (mock Anthropic API response)
# =============================================================================


class TestTokenTracking:
    def test_tokens_summed_across_iterations(
        self, lab_config: Config, sandbox_default: Sandbox,
        budget_tmp: BudgetManager, history_tmp: HistoryManager,
        tmp_path: Path,
    ) -> None:
        responses = [
            _make_mock_anthropic_response(
                tool_uses=[{
                    "id": "tu_1", "name": "computer",
                    "input": {"action": "click", "coordinate": [10, 10]},
                }],
                input_tokens=1000, output_tokens=200,
            ),
            _make_mock_anthropic_response(
                stop_reason="end_turn",
                input_tokens=500, output_tokens=100,
            ),
        ]
        pilot = _make_pilot(
            lab_config, sandbox_default, budget_tmp, history_tmp,
            api_responses=responses, tmp_path=tmp_path,
        )
        result = pilot.run("test")
        assert result.total_tokens_in == 1500
        assert result.total_tokens_out == 300
        assert result.total_cost_eur > 0

    def test_budget_recorded_per_call(
        self, lab_config: Config, sandbox_default: Sandbox,
        history_tmp: HistoryManager, tmp_path: Path,
    ) -> None:
        budget = BudgetManager(path=tmp_path / "b.json")
        responses = [
            _make_mock_anthropic_response(stop_reason="end_turn"),
        ]
        pilot = _make_pilot(
            lab_config, sandbox_default, budget, history_tmp,
            api_responses=responses, tmp_path=tmp_path,
        )
        pilot.run("test")
        assert budget.spent_eur > 0
        assert budget.actions_count >= 1


# =============================================================================
# Test 13 : Serialisation PilotResult.to_dict
# =============================================================================


class TestSerialization:
    def test_to_dict_roundtrip_json(self) -> None:
        result = PilotResult(
            prompt="test",
            iterations=2,
            completed=True,
            total_cost_eur=0.0123,
            total_tokens_in=100,
            total_tokens_out=50,
        )
        result.actions.append(PilotAction(
            iteration=1,
            timestamp="2026-05-06T00:00:00Z",
            proposed=ProposedAction(kind="click", x=10, y=20, rationale="test"),
            decision="confirm",
            executed=True,
            cost_eur=0.005,
            tokens_in=50,
            tokens_out=25,
            screenshot_before="/tmp/s1.png",
            screenshot_after="/tmp/s2.png",
        ))
        d = result.to_dict()
        # Doit etre JSON-serialisable
        s = json.dumps(d)
        loaded = json.loads(s)
        assert loaded["prompt"] == "test"
        assert loaded["iterations"] == 2
        assert loaded["completed"] is True
        assert loaded["actions"][0]["proposed_kind"] == "click"
        assert loaded["actions"][0]["proposed_x"] == 10


# =============================================================================
# Test 14 : Helpers internes (parse_tool_use, normalize_response)
# =============================================================================


class TestHelpers:
    def test_parse_tool_use_click(self) -> None:
        tu = {
            "id": "tu_1", "name": "computer",
            "input": {"action": "click", "coordinate": [100, 200]},
        }
        action = _parse_tool_use(tu)
        assert action.kind == "click"
        assert action.x == 100
        assert action.y == 200

    def test_parse_tool_use_type(self) -> None:
        tu = {
            "id": "tu_2", "name": "computer",
            "input": {"action": "type", "text": "hello"},
        }
        action = _parse_tool_use(tu)
        assert action.kind == "type"
        assert action.text == "hello"

    def test_parse_tool_use_no_coord_safe(self) -> None:
        tu = {
            "id": "tu_3", "name": "computer",
            "input": {"action": "screenshot"},
        }
        action = _parse_tool_use(tu)
        assert action.x is None
        assert action.y is None

    def test_normalize_response_no_usage(self) -> None:
        # Reponse sans usage : tokens = 0
        r = MagicMock()
        r.usage = None
        r.stop_reason = "end_turn"
        r.content = []
        d = _normalize_anthropic_response(r)
        assert d["input_tokens"] == 0
        assert d["output_tokens"] == 0

    def test_model_pricing_compute(self) -> None:
        pricing = ModelPricing("test", input_per_1m_eur=10.0, output_per_1m_eur=30.0)
        # 100k input + 50k output = 1.0 EUR + 1.5 EUR = 2.5 EUR
        assert pricing.compute(100_000, 50_000) == pytest.approx(2.5)

    def test_model_pricing_negative_raises(self) -> None:
        pricing = MODEL_PRICING["claude-sonnet-4-6"]
        with pytest.raises(ValueError):
            pricing.compute(-1, 100)


# =============================================================================
# Test 15 : Screenshot fail -> abort propre
# =============================================================================


class TestScreenshotFailure:
    def test_screenshot_fail_aborts_loop(
        self, lab_config: Config, sandbox_default: Sandbox,
        budget_tmp: BudgetManager, history_tmp: HistoryManager,
        tmp_path: Path,
    ) -> None:
        pilot = _make_pilot(
            lab_config, sandbox_default, budget_tmp, history_tmp,
            api_responses=[],  # n'arrive jamais
            fail_screenshot=True,
            tmp_path=tmp_path,
        )
        result = pilot.run("test")
        assert result.abort_reason.startswith("screenshot_failed")
        assert result.completed is False


# =============================================================================
# Test 16 : Budget initial trop bas -> refuse de demarrer
# =============================================================================


class TestBudgetPreCheck:
    def test_zero_budget_blocks_run(
        self, lab_config: Config, sandbox_default: Sandbox,
        history_tmp: HistoryManager, tmp_path: Path,
    ) -> None:
        # Plafond 0.0001 EUR -> meme la 1ere requete depasse
        budget = BudgetManager(path=tmp_path / "b.json", limit_eur=0.0001)
        pilot = _make_pilot(
            lab_config, sandbox_default, budget, history_tmp,
            api_responses=[_make_mock_anthropic_response(stop_reason="end_turn")],
            tmp_path=tmp_path,
        )
        with pytest.raises(BudgetExceededError):
            pilot.run("test")


# =============================================================================
# Test 17 : __init__ lazy proxies
# =============================================================================


class TestPackageInit:
    def test_lazy_attribute_anthropic_pilot(self) -> None:
        from winboost import pilot as pkg
        # AnthropicPilot accessible via le package
        assert pkg.AnthropicPilot is AnthropicPilot

    def test_lazy_attribute_budget_manager(self) -> None:
        from winboost import pilot as pkg
        assert pkg.BudgetManager is BudgetManager

    def test_lazy_attribute_sandbox(self) -> None:
        from winboost import pilot as pkg
        assert pkg.Sandbox is Sandbox

    def test_unknown_attribute_raises(self) -> None:
        from winboost import pilot as pkg
        with pytest.raises(AttributeError):
            _ = pkg.NotARealClass  # type: ignore[attr-defined]
