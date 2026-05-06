"""Tests pour winboost.utils.windows_native (helpers WMI/PowerShell)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from winboost.utils.windows_native import (
    POWER_PLAN_BALANCED,
    POWER_PLAN_HIGH_PERFORMANCE,
    PowerShellResult,
    WindowsNativeError,
    get_active_power_plan,
    get_brightness,
    is_dark_mode,
    is_focus_assist_enabled,
    run_powershell,
    set_brightness,
    set_dark_mode,
    set_power_plan,
)


def _ps_ok(stdout: str = "", stderr: str = "") -> PowerShellResult:
    return PowerShellResult(stdout=stdout, stderr=stderr, returncode=0)


def _ps_fail(stderr: str = "boom") -> PowerShellResult:
    return PowerShellResult(stdout="", stderr=stderr, returncode=1)


# --- run_powershell ---


class TestRunPowershell:
    def test_returns_result_dataclass(self):
        with patch("winboost.utils.windows_native.subprocess.run") as mock_run, patch(
            "winboost.utils.windows_native.sys"
        ) as mock_sys:
            mock_sys.platform = "win32"
            mock_run.return_value = MagicMock(stdout="hello\n", stderr="", returncode=0)
            r = run_powershell("Write-Output 'hello'")
            assert r.ok is True
            assert r.stdout == "hello"
            assert r.returncode == 0

    def test_ok_property_true_on_zero_returncode(self):
        assert _ps_ok().ok is True
        assert _ps_fail().ok is False

    def test_raises_on_timeout(self):
        with patch("winboost.utils.windows_native.subprocess.run") as mock_run, patch(
            "winboost.utils.windows_native.sys"
        ) as mock_sys:
            mock_sys.platform = "win32"
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ps", timeout=1)
            with pytest.raises(WindowsNativeError, match="Timeout"):
                run_powershell("Start-Sleep 100", timeout=1)

    def test_raises_on_missing_powershell(self):
        with patch("winboost.utils.windows_native.subprocess.run") as mock_run, patch(
            "winboost.utils.windows_native.sys"
        ) as mock_sys:
            mock_sys.platform = "win32"
            mock_run.side_effect = FileNotFoundError()
            with pytest.raises(WindowsNativeError, match="introuvable"):
                run_powershell("noop")

    def test_raises_on_non_windows(self):
        with patch("winboost.utils.windows_native.sys") as mock_sys:
            mock_sys.platform = "linux"
            with pytest.raises(WindowsNativeError, match="Windows"):
                run_powershell("noop")


# --- get_brightness / set_brightness ---


class TestBrightness:
    def test_get_brightness_parses_int(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("75\n")
            assert get_brightness() == 75

    def test_get_brightness_raises_when_empty(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("")
            with pytest.raises(WindowsNativeError, match="WMI"):
                get_brightness()

    def test_get_brightness_raises_on_unparseable(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("nope")
            with pytest.raises(WindowsNativeError, match="invalide"):
                get_brightness()

    def test_set_brightness_clamps_to_0_100(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok()
            set_brightness(150)
            cmd = mock_ps.call_args.args[0]
            assert "100" in cmd
            mock_ps.reset_mock()
            mock_ps.return_value = _ps_ok()
            set_brightness(-10)
            cmd = mock_ps.call_args.args[0]
            assert ", 0)" in cmd

    def test_set_brightness_rejects_non_int(self):
        with pytest.raises(ValueError):
            set_brightness("50")  # type: ignore[arg-type]

    def test_set_brightness_raises_on_ps_failure(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_fail("ecran externe non WMI")
            with pytest.raises(WindowsNativeError, match="WmiSetBrightness"):
                set_brightness(50)


# --- Dark mode ---


class TestDarkMode:
    def test_is_dark_mode_true_when_zero(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("0")
            assert is_dark_mode() is True

    def test_is_dark_mode_false_when_one(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("1")
            assert is_dark_mode() is False

    def test_is_dark_mode_raises_on_failure(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_fail("registry locked")
            with pytest.raises(WindowsNativeError):
                is_dark_mode()

    def test_set_dark_mode_writes_zero_when_enabled(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok()
            set_dark_mode(True)
            cmd = mock_ps.call_args.args[0]
            assert "Value 0" in cmd
            assert "AppsUseLightTheme" in cmd
            assert "SystemUsesLightTheme" in cmd

    def test_set_dark_mode_writes_one_when_disabled(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok()
            set_dark_mode(False)
            cmd = mock_ps.call_args.args[0]
            assert "Value 1" in cmd

    def test_set_dark_mode_raises_on_failure(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_fail("access denied")
            with pytest.raises(WindowsNativeError):
                set_dark_mode(True)


# --- Focus Assist ---


class TestFocusAssist:
    def test_focus_assist_enabled_when_toast_zero(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("0")
            assert is_focus_assist_enabled() is True

    def test_focus_assist_disabled_when_toast_one(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("1")
            assert is_focus_assist_enabled() is False


# --- Power plans ---


class TestPowerPlan:
    def test_get_active_extracts_guid(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(
                f"Power Scheme GUID: {POWER_PLAN_BALANCED}  (Equilibre)"
            )
            assert get_active_power_plan() == POWER_PLAN_BALANCED

    def test_get_active_raises_when_no_guid(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("garbage output")
            with pytest.raises(WindowsNativeError, match="GUID introuvable"):
                get_active_power_plan()

    def test_set_power_plan_calls_powercfg(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok()
            set_power_plan(POWER_PLAN_HIGH_PERFORMANCE)
            cmd = mock_ps.call_args.args[0]
            assert "powercfg /setactive" in cmd
            assert POWER_PLAN_HIGH_PERFORMANCE in cmd

    def test_set_power_plan_raises_on_failure(self):
        with patch("winboost.utils.windows_native.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_fail("access denied")
            with pytest.raises(WindowsNativeError, match="admin"):
                set_power_plan(POWER_PLAN_BALANCED)


# --- Power plan GUIDs sont stables ---


class TestPowerPlanConstants:
    def test_high_perf_is_microsoft_official_guid(self):
        assert POWER_PLAN_HIGH_PERFORMANCE == "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

    def test_balanced_is_microsoft_official_guid(self):
        assert POWER_PLAN_BALANCED == "381b4222-f694-41f0-9685-ff5bb260df2e"
