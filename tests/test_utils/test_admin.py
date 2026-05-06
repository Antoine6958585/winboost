"""Tests pour winboost.utils.admin (UAC helpers)."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from winboost.utils.admin import (
    AdminRequiredError,
    is_admin,
    relaunch_as_admin,
    require_admin,
)

# --- is_admin() ---


class TestIsAdmin:
    def test_returns_bool(self):
        result = is_admin()
        assert isinstance(result, bool)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_windows_uses_shell32(self):
        with patch("winboost.utils.admin.ctypes") as mock_ctypes:
            mock_ctypes.windll.shell32.IsUserAnAdmin.return_value = 1
            assert is_admin() is True
            mock_ctypes.windll.shell32.IsUserAnAdmin.assert_called_once()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_windows_returns_false_when_not_admin(self):
        with patch("winboost.utils.admin.ctypes") as mock_ctypes:
            mock_ctypes.windll.shell32.IsUserAnAdmin.return_value = 0
            assert is_admin() is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_windows_handles_oserror(self):
        with patch("winboost.utils.admin.ctypes") as mock_ctypes:
            mock_ctypes.windll.shell32.IsUserAnAdmin.side_effect = OSError("nope")
            assert is_admin() is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_windows_handles_attribute_error(self):
        with patch("winboost.utils.admin.ctypes") as mock_ctypes:
            mock_ctypes.windll.shell32.IsUserAnAdmin.side_effect = AttributeError("no shell32")
            assert is_admin() is False


# --- require_admin() ---


class TestRequireAdmin:
    def test_passes_when_admin(self):
        with patch("winboost.utils.admin.is_admin", return_value=True):
            require_admin()  # ne doit pas lever

    def test_raises_when_not_admin(self):
        with patch("winboost.utils.admin.is_admin", return_value=False):
            with pytest.raises(AdminRequiredError):
                require_admin()

    def test_raises_with_action_name(self):
        with patch("winboost.utils.admin.is_admin", return_value=False):
            with pytest.raises(AdminRequiredError) as exc:
                require_admin("desactive_telemetrie")
            assert "desactive_telemetrie" in str(exc.value)

    def test_message_mentions_admin(self):
        with patch("winboost.utils.admin.is_admin", return_value=False):
            with pytest.raises(AdminRequiredError) as exc:
                require_admin("test")
            assert "administrateur" in str(exc.value).lower()

    def test_message_without_action_name(self):
        with patch("winboost.utils.admin.is_admin", return_value=False):
            with pytest.raises(AdminRequiredError) as exc:
                require_admin()
            assert "operation" in str(exc.value).lower()


# --- relaunch_as_admin() ---


class TestRelaunchAsAdmin:
    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows path")
    def test_returns_false_on_non_windows(self):
        assert relaunch_as_admin() is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_already_admin_returns_true(self):
        with patch("winboost.utils.admin.is_admin", return_value=True):
            assert relaunch_as_admin() is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_calls_shell_execute_w(self):
        with patch("winboost.utils.admin.is_admin", return_value=False):
            with patch("winboost.utils.admin.ctypes") as mock_ctypes:
                # ShellExecuteW retourne > 32 si succes
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 42
                result = relaunch_as_admin(["arg1", "arg2"])
                assert result is True
                mock_ctypes.windll.shell32.ShellExecuteW.assert_called_once()
                call_args = mock_ctypes.windll.shell32.ShellExecuteW.call_args
                assert call_args[0][1] == "runas"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_returns_false_when_shell_execute_fails(self):
        with patch("winboost.utils.admin.is_admin", return_value=False):
            with patch("winboost.utils.admin.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 0  # echec
                assert relaunch_as_admin([]) is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_handles_oserror(self):
        with patch("winboost.utils.admin.is_admin", return_value=False):
            with patch("winboost.utils.admin.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.side_effect = OSError("nope")
                assert relaunch_as_admin([]) is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_uses_sys_argv_by_default(self):
        with patch("winboost.utils.admin.is_admin", return_value=False):
            with patch("winboost.utils.admin.ctypes") as mock_ctypes:
                with patch("winboost.utils.admin.sys") as mock_sys:
                    mock_sys.platform = "win32"
                    mock_sys.argv = ["winboost", "scan", "--module", "temp_cleaner"]
                    mock_sys.executable = "C:\\python.exe"
                    mock_ctypes.windll.shell32.ShellExecuteW.return_value = 42
                    relaunch_as_admin()  # args=None -> sys.argv[1:]
                    call_args = mock_ctypes.windll.shell32.ShellExecuteW.call_args
                    # 4eme positional = params string
                    assert "scan" in call_args[0][3]


# --- AdminRequiredError ---


class TestAdminRequiredError:
    def test_is_runtime_error(self):
        assert issubclass(AdminRequiredError, RuntimeError)

    def test_can_be_caught(self):
        with pytest.raises(AdminRequiredError):
            raise AdminRequiredError("test")

    def test_message_preserved(self):
        try:
            raise AdminRequiredError("custom message")
        except AdminRequiredError as e:
            assert str(e) == "custom message"
