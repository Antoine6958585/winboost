"""Tests pour winboost/pilot/action_executor.py.

Approche : injecter un faux module pyautogui dans sys.modules. Tous les
appels (click, write, hotkey, scroll, etc.) sont des MagicMock dont on
verifie les arguments. Permet de tourner sur Linux/CI sans display ni
souris reelle.

Couvre :
- ImportError clair si pyautogui absent
- Mapping kind -> appel pyautogui (click, double, right, type, key,
  hotkey, scroll, move)
- Coords hors sandbox -> PilotError, pas d'appel pyautogui
- pyautogui.FailSafeException -> PilotError(failsafe_triggered)
- kind inconnu -> PilotError(unsupported_action)
- screenshot/cursor_position -> noop
- wait -> time.sleep
"""

from __future__ import annotations

import builtins
import sys
from unittest.mock import MagicMock, patch

import pytest

from winboost.pilot.anthropic_pilot import PilotError
from winboost.pilot.confirmation_ui import ProposedAction
from winboost.pilot.sandbox import Region, Sandbox

# --- Helpers --------------------------------------------------------------


def _install_fake_pyautogui() -> MagicMock:
    """Injecte un MagicMock pyautogui dans sys.modules. A nettoyer apres."""
    fake = MagicMock(name="pyautogui")
    fake.click = MagicMock(name="click")
    fake.doubleClick = MagicMock(name="doubleClick")
    fake.rightClick = MagicMock(name="rightClick")
    fake.write = MagicMock(name="write")
    fake.press = MagicMock(name="press")
    fake.hotkey = MagicMock(name="hotkey")
    fake.scroll = MagicMock(name="scroll")
    fake.moveTo = MagicMock(name="moveTo")

    # Le module reel pyautogui expose `FailSafeException` ; on cree une
    # classe portant exactement ce __name__ pour que le code de production
    # qui inspecte `type(exc).__name__ == "FailSafeException"` matche.
    fake.FailSafeException = type("FailSafeException", (Exception,), {})  # noqa: N806
    sys.modules["pyautogui"] = fake
    return fake


def _cleanup_pyautogui() -> None:
    if "pyautogui" in sys.modules:
        del sys.modules["pyautogui"]


def _wide_sandbox() -> Sandbox:
    """Sandbox avec une grande region pour valider les coords par defaut."""
    return Sandbox(
        mode="screen_region",
        region=Region(x=0, y=0, width=1920, height=1080),
    )


@pytest.fixture
def fake_pyautogui():
    """Fixture qui installe un faux pyautogui et nettoie apres."""
    fake = _install_fake_pyautogui()
    yield fake
    _cleanup_pyautogui()


# --- Tests ---------------------------------------------------------------


class TestImportError:
    """ImportError clair si pyautogui n'est pas dispo."""

    def test_import_error_when_pyautogui_missing(self):
        """make_action_executor() leve ImportError clair sans pyautogui."""
        _cleanup_pyautogui()  # garantir l'absence
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pyautogui":
                raise ImportError("No module named 'pyautogui'")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=fake_import):
            from winboost.pilot.action_executor import make_action_executor

            with pytest.raises(ImportError) as exc_info:
                make_action_executor(_wide_sandbox())

            msg = str(exc_info.value)
            assert "pyautogui" in msg
            assert "pip install winboost[pilot]" in msg


class TestClickActions:
    """Mapping click / double_click / right_click."""

    def test_click_calls_pyautogui_click_with_coords(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        sandbox = _wide_sandbox()
        executor = make_action_executor(sandbox)
        action = ProposedAction(kind="click", x=400, y=300, rationale="ouvre menu")
        executor(action)

        fake_pyautogui.click.assert_called_once_with(400, 300)
        fake_pyautogui.doubleClick.assert_not_called()
        fake_pyautogui.rightClick.assert_not_called()

    def test_double_click_calls_pyautogui_doubleclick(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(kind="double_click", x=100, y=100)
        executor(action)

        fake_pyautogui.doubleClick.assert_called_once_with(100, 100)

    def test_right_click_calls_pyautogui_rightclick(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(kind="right_click", x=50, y=60)
        executor(action)

        fake_pyautogui.rightClick.assert_called_once_with(50, 60)


class TestTypeAction:
    """Action 'type' = pyautogui.write avec interval configurable."""

    def test_type_calls_write_with_default_interval(self, fake_pyautogui):
        from winboost.pilot.action_executor import (
            DEFAULT_TYPE_INTERVAL,
            make_action_executor,
        )

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(kind="type", text="hello world")
        executor(action)

        fake_pyautogui.write.assert_called_once_with(
            "hello world", interval=DEFAULT_TYPE_INTERVAL
        )

    def test_type_custom_interval(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox(), type_interval=0.05)
        action = ProposedAction(kind="type", text="abc")
        executor(action)

        fake_pyautogui.write.assert_called_once_with("abc", interval=0.05)

    def test_type_empty_text_is_noop(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(kind="type", text="")
        executor(action)

        fake_pyautogui.write.assert_not_called()


class TestKeyAction:
    """Action 'key' = press simple ou hotkey si combo."""

    def test_simple_key_calls_press(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(kind="key", key="enter")
        executor(action)

        fake_pyautogui.press.assert_called_once_with("enter")
        fake_pyautogui.hotkey.assert_not_called()

    def test_escape_key_calls_press(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        executor(ProposedAction(kind="key", key="esc"))

        fake_pyautogui.press.assert_called_once_with("esc")

    def test_hotkey_combo_calls_hotkey(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(kind="key", key="ctrl+c")
        executor(action)

        fake_pyautogui.hotkey.assert_called_once_with("ctrl", "c")
        fake_pyautogui.press.assert_not_called()

    def test_hotkey_three_keys(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        executor(ProposedAction(kind="key", key="ctrl+alt+del"))

        fake_pyautogui.hotkey.assert_called_once_with("ctrl", "alt", "del")

    def test_key_without_value_raises(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        with pytest.raises(PilotError) as exc_info:
            executor(ProposedAction(kind="key", key=None))
        assert "unsupported_action" in str(exc_info.value)


class TestScrollAction:
    """Action scroll : pyautogui.scroll(amount * sign), up=+, down=-."""

    def test_scroll_down_negative_sign(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(
            kind="scroll", x=100, y=100,
            scroll_direction="down", scroll_amount=3,
        )
        executor(action)

        fake_pyautogui.scroll.assert_called_once_with(-3)

    def test_scroll_up_positive_sign(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(
            kind="scroll", x=100, y=100,
            scroll_direction="up", scroll_amount=5,
        )
        executor(action)

        fake_pyautogui.scroll.assert_called_once_with(5)

    def test_scroll_horizontal_is_noop_with_warning(self, fake_pyautogui, caplog):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(
            kind="scroll", x=100, y=100,
            scroll_direction="left", scroll_amount=2,
        )
        with caplog.at_level("WARNING"):
            executor(action)

        fake_pyautogui.scroll.assert_not_called()


class TestMoveAction:
    """Action move : pyautogui.moveTo(x, y, duration=...)."""

    def test_move_calls_moveto_with_duration(self, fake_pyautogui):
        from winboost.pilot.action_executor import (
            DEFAULT_MOVE_DURATION,
            make_action_executor,
        )

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(kind="move", x=200, y=300)
        executor(action)

        fake_pyautogui.moveTo.assert_called_once_with(
            200, 300, duration=DEFAULT_MOVE_DURATION
        )


class TestSandboxBoundsEnforcement:
    """Coords hors region.region -> PilotError, AUCUN appel pyautogui."""

    def test_click_out_of_bounds_raises(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        sandbox = Sandbox(
            mode="screen_region",
            region=Region(x=0, y=0, width=800, height=600),
        )
        executor = make_action_executor(sandbox)
        action = ProposedAction(kind="click", x=900, y=100)

        with pytest.raises(PilotError) as exc_info:
            executor(action)

        assert "out_of_bounds" in str(exc_info.value)
        fake_pyautogui.click.assert_not_called()

    def test_click_negative_coords_out_of_bounds(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        sandbox = Sandbox(
            mode="screen_region",
            region=Region(x=0, y=0, width=800, height=600),
        )
        executor = make_action_executor(sandbox)

        with pytest.raises(PilotError) as exc_info:
            executor(ProposedAction(kind="click", x=-10, y=100))
        assert "out_of_bounds" in str(exc_info.value)
        fake_pyautogui.click.assert_not_called()

    def test_click_missing_coords_raises(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        with pytest.raises(PilotError) as exc_info:
            executor(ProposedAction(kind="click", x=None, y=None))
        assert "out_of_bounds" in str(exc_info.value)
        fake_pyautogui.click.assert_not_called()


class TestFailsafe:
    """pyautogui.FailSafeException -> PilotError(failsafe_triggered)."""

    def test_failsafe_relabel_with_explicit_message(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        # On configure click pour lever FailSafe
        fake_pyautogui.click.side_effect = fake_pyautogui.FailSafeException(
            "PyAutoGUI fail-safe triggered"
        )

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(kind="click", x=100, y=100)

        with pytest.raises(PilotError) as exc_info:
            executor(action)

        msg = str(exc_info.value)
        assert "failsafe_triggered" in msg
        assert "haut-gauche" in msg.lower() or "interrompre" in msg.lower()

    def test_other_pyautogui_error_relabel_as_pyautogui_error(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        fake_pyautogui.click.side_effect = RuntimeError("driver crash")
        executor = make_action_executor(_wide_sandbox())

        with pytest.raises(PilotError) as exc_info:
            executor(ProposedAction(kind="click", x=10, y=10))

        msg = str(exc_info.value)
        assert "pyautogui_error" in msg
        assert "driver crash" in msg


class TestUnsupportedKind:
    """Kind inconnu -> PilotError(unsupported_action)."""

    def test_unknown_kind_raises(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(kind="warp_speed", rationale="ad hoc")

        with pytest.raises(PilotError) as exc_info:
            executor(action)
        assert "unsupported_action" in str(exc_info.value)
        # Aucun appel pyautogui n'a ete fait.
        fake_pyautogui.click.assert_not_called()
        fake_pyautogui.write.assert_not_called()


class TestNoopActions:
    """screenshot et cursor_position sont des noops -> aucune erreur."""

    def test_screenshot_kind_is_noop(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        executor(ProposedAction(kind="screenshot"))

        fake_pyautogui.click.assert_not_called()
        fake_pyautogui.write.assert_not_called()
        fake_pyautogui.scroll.assert_not_called()

    def test_cursor_position_kind_is_noop(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        executor(ProposedAction(kind="cursor_position"))

        fake_pyautogui.click.assert_not_called()
        fake_pyautogui.moveTo.assert_not_called()


class TestWaitAction:
    """Action 'wait' utilise time.sleep, pas pyautogui."""

    def test_wait_calls_time_sleep_with_default(self, fake_pyautogui):
        from winboost.pilot import action_executor as ae_mod

        executor = ae_mod.make_action_executor(_wide_sandbox())
        with patch.object(ae_mod.time, "sleep") as mock_sleep:
            executor(ProposedAction(kind="wait"))
        mock_sleep.assert_called_once_with(ae_mod.DEFAULT_WAIT_SECONDS)

    def test_wait_with_scroll_amount_overrides_default(self, fake_pyautogui):
        from winboost.pilot import action_executor as ae_mod

        executor = ae_mod.make_action_executor(_wide_sandbox())
        with patch.object(ae_mod.time, "sleep") as mock_sleep:
            executor(ProposedAction(kind="wait", scroll_amount=3))
        mock_sleep.assert_called_once_with(3.0)


class TestRationaleLogging:
    """Avant chaque action, on log le rationale (audit / debug)."""

    def test_rationale_logged_at_info_level(self, fake_pyautogui, caplog):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        action = ProposedAction(
            kind="click",
            x=100, y=100,
            rationale="ouvrir le menu Bluetooth",
        )

        with caplog.at_level("INFO"):
            executor(action)

        assert any(
            "ouvrir le menu Bluetooth" in r.message for r in caplog.records
        )


class TestFactoryReturnsCallable:
    """make_action_executor retourne un callable conforme."""

    def test_factory_returns_callable(self, fake_pyautogui):
        from winboost.pilot.action_executor import make_action_executor

        executor = make_action_executor(_wide_sandbox())
        assert callable(executor)
