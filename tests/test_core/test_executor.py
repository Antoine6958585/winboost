"""Tests pour winboost.core.executor (ActionExecutor + ApplyResult).

Couvre les 10 methodes d'execution YAML + securite + admin + idempotence
+ dry_run + timeout + history + sérialisation. >= 30 tests.

Strategie de mock :
- winreg : module mocke globalement quand sys.platform != 'win32', sinon
  on patche `winboost.core.executor._winreg_module`
- subprocess.run : patche au niveau module
- BackupManager / HistoryManager : MagicMock
- is_admin : patche au niveau executor
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from winboost.core.executor import (
    DEFAULT_TIMEOUT_SECONDS,
    ActionExecutor,
    ApplyResult,
    _is_safe_command,
    _is_safe_filesystem_path,
    _is_safe_registry_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _StubAction:
    """Stub minimal d'`Action`."""

    id: str = "act_001"
    name: str = "Test Action"
    description: str = "Test"
    category: str = "system"
    risk_level: str = "low"
    requires_admin: bool = False
    reversible: bool = True
    execute: dict[str, Any] = field(default_factory=dict)
    rollback: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, Any] = field(default_factory=dict)
    keywords: dict[str, list[str]] = field(default_factory=dict)
    compatibility: dict[str, Any] = field(default_factory=dict)


def _make_action(method: str, params: dict[str, Any], **kwargs: Any) -> _StubAction:
    return _StubAction(execute={"method": method, "params": params}, **kwargs)


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> Any:
    """Faux subprocess.CompletedProcess."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ---------------------------------------------------------------------------
# 1. ApplyResult dataclass + sérialisation
# ---------------------------------------------------------------------------


class TestApplyResult:
    def test_apply_result_default_fields(self) -> None:
        r = ApplyResult(success=True, message="ok", action_id="x")
        assert r.success is True
        assert r.message == "ok"
        assert r.action_id == "x"
        assert r.rollback_id is None
        assert r.error_code is None
        assert r.duration_ms == 0
        assert r.dry_run is False
        assert r.extra == {}

    def test_apply_result_to_dict_roundtrip(self) -> None:
        r = ApplyResult(
            success=False,
            message="boom",
            action_id="x",
            error_code="exec_failed",
            stdout="hello",
            stderr="err",
            duration_ms=42,
            method="powershell",
            dry_run=False,
            extra={"k": 1},
        )
        d = r.to_dict()
        # JSON-safe : doit pouvoir round-tripper en JSON
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2["success"] is False
        assert d2["error_code"] == "exec_failed"
        assert d2["duration_ms"] == 42
        assert d2["extra"]["k"] == 1


# ---------------------------------------------------------------------------
# 2. Helpers de securite (whitelist filesystem, blacklist registry, command)
# ---------------------------------------------------------------------------


class TestSecurityHelpers:
    def test_safe_filesystem_temp_ok(self) -> None:
        ok, _ = _is_safe_filesystem_path("%TEMP%")
        assert ok is True

    def test_safe_filesystem_localappdata_temp_ok(self) -> None:
        ok, _ = _is_safe_filesystem_path("%LOCALAPPDATA%\\Temp")
        assert ok is True

    def test_safe_filesystem_system32_refused(self) -> None:
        ok, reason = _is_safe_filesystem_path("C:\\Windows\\System32\\anything")
        assert ok is False
        assert "system" in reason.lower() or "protege" in reason.lower()

    def test_safe_filesystem_program_files_refused(self) -> None:
        ok, _ = _is_safe_filesystem_path("C:\\Program Files\\evil")
        assert ok is False

    def test_safe_filesystem_outside_whitelist_refused(self) -> None:
        ok, reason = _is_safe_filesystem_path("D:\\my_data")
        assert ok is False
        assert "whitelist" in reason.lower() or "hors" in reason.lower()

    def test_safe_filesystem_empty_refused(self) -> None:
        ok, _ = _is_safe_filesystem_path("")
        assert ok is False

    def test_safe_registry_hkcu_ok(self) -> None:
        ok, _ = _is_safe_registry_path("HKCU\\SOFTWARE\\Microsoft\\Windows\\Explorer")
        assert ok is True

    def test_safe_registry_hklm_setup_refused(self) -> None:
        ok, reason = _is_safe_registry_path("HKLM\\SYSTEM\\Setup\\anything")
        assert ok is False
        assert "protegee" in reason.lower()

    def test_safe_registry_bcd_refused(self) -> None:
        ok, _ = _is_safe_registry_path("HKLM\\BCD00000000")
        assert ok is False

    def test_safe_registry_lsa_refused(self) -> None:
        ok, _ = _is_safe_registry_path("HKLM\\SYSTEM\\CurrentControlSet\\Control\\Lsa")
        assert ok is False

    def test_safe_command_innocuous_ok(self) -> None:
        ok, _ = _is_safe_command("Get-Process | Select-Object -First 5")
        assert ok is True

    def test_safe_command_format_c_refused(self) -> None:
        ok, _ = _is_safe_command("format C: /q")
        assert ok is False

    def test_safe_command_remove_item_c_refused(self) -> None:
        ok, _ = _is_safe_command("Remove-Item -Recurse -Force C:\\")
        assert ok is False

    def test_safe_command_diskpart_clean_refused(self) -> None:
        ok, _ = _is_safe_command("echo select disk 0 | diskpart && echo clean | diskpart")
        assert ok is False

    def test_safe_command_empty_refused(self) -> None:
        ok, _ = _is_safe_command("")
        assert ok is False


# ---------------------------------------------------------------------------
# 3. Admin check
# ---------------------------------------------------------------------------


class TestAdminCheck:
    def test_admin_required_but_not_admin_returns_admin_required(self) -> None:
        action = _make_action(
            method="registry_set",
            params={"path": "HKCU\\Software\\X", "values": [{"name": "A", "type": "REG_DWORD", "data": 0}]},
            requires_admin=True,
        )
        with patch("winboost.core.executor.is_admin", return_value=False):
            ex = ActionExecutor()
            result = ex.apply(action)
        assert result.success is False
        assert result.error_code == "admin_required"
        assert "administrateur" in result.message.lower()

    def test_admin_required_and_admin_proceeds(self) -> None:
        action = _make_action(
            method="powershell",
            params={"command": "Write-Host hello"},
            requires_admin=True,
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "hello", "")):
            ex = ActionExecutor()
            result = ex.apply(action)
        assert result.success is True
        assert result.error_code is None or result.error_code != "admin_required"

    def test_no_admin_required_runs_without_check(self) -> None:
        action = _make_action(
            method="powershell",
            params={"command": "Write-Host hi"},
            requires_admin=False,
        )
        with patch("winboost.core.executor.is_admin", return_value=False), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "hi", "")):
            ex = ActionExecutor()
            result = ex.apply(action)
        assert result.success is True


# ---------------------------------------------------------------------------
# 4. Method not implemented + Timeout
# ---------------------------------------------------------------------------


class TestMethodAndTimeout:
    def test_unknown_method_returns_method_not_implemented(self) -> None:
        action = _make_action(method="quantum_entanglement", params={})
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "method_not_implemented"

    def test_powershell_timeout_returns_timeout_error(self) -> None:
        action = _make_action(method="powershell", params={"command": "Start-Sleep 100"})

        def _raise(*args: Any, **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 30))

        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", side_effect=_raise):
            result = ActionExecutor(default_timeout=1.0).apply(action)
        assert result.success is False
        assert result.error_code == "timeout"

    def test_default_timeout_constant(self) -> None:
        assert DEFAULT_TIMEOUT_SECONDS == 30.0


# ---------------------------------------------------------------------------
# 5. registry_set : success / idempotence / unsafe / not Windows
# ---------------------------------------------------------------------------


class TestRegistrySet:
    def _patch_winreg(self) -> Any:
        """Cree un faux module winreg minimal."""
        winreg = MagicMock()
        winreg.HKEY_CURRENT_USER = 0x80000001
        winreg.HKEY_LOCAL_MACHINE = 0x80000002
        winreg.REG_DWORD = 4
        winreg.REG_SZ = 1
        winreg.REG_QWORD = 11
        winreg.REG_BINARY = 3
        winreg.REG_MULTI_SZ = 7
        winreg.REG_EXPAND_SZ = 2
        winreg.KEY_READ = 0x20019
        winreg.KEY_SET_VALUE = 0x2
        winreg.KEY_ALL_ACCESS = 0xF003F
        return winreg

    def test_registry_set_unsafe_path_refused(self) -> None:
        action = _make_action(
            method="registry_set",
            params={
                "path": "HKLM\\SYSTEM\\Setup",
                "values": [{"name": "X", "type": "REG_DWORD", "data": 1}],
            },
        )
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "unsafe_registry"

    def test_registry_set_invalid_params_no_values(self) -> None:
        action = _make_action(
            method="registry_set",
            params={"path": "HKCU\\Software\\Test"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "invalid_params"

    def test_registry_set_dry_run_does_not_call_winreg(self) -> None:
        action = _make_action(
            method="registry_set",
            params={
                "path": "HKCU\\Software\\WinBoostTest",
                "values": [{"name": "X", "type": "REG_DWORD", "data": 1}],
            },
        )
        winreg = self._patch_winreg()
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor._winreg_module", return_value=winreg):
            result = ActionExecutor().apply(action, dry_run=True)
        assert result.success is True
        assert result.error_code == "dry_run"
        assert "[dry-run]" in result.message
        # winreg n'a JAMAIS ete appele en dry-run
        winreg.CreateKey.assert_not_called()
        winreg.SetValueEx.assert_not_called()

    def test_registry_set_success_calls_set_value_ex(self) -> None:
        action = _make_action(
            method="registry_set",
            params={
                "path": "HKCU\\Software\\WinBoostTest",
                "values": [
                    {"name": "Foo", "type": "REG_DWORD", "data": 1},
                    {"name": "Bar", "type": "REG_SZ", "data": "hello"},
                ],
            },
        )
        winreg = self._patch_winreg()
        # OpenKey leve FileNotFoundError -> on tombe en CreateKey
        winreg.OpenKey.side_effect = FileNotFoundError()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        winreg.CreateKey.return_value = ctx

        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor._winreg_module", return_value=winreg):
            result = ActionExecutor().apply(action)
        assert result.success is True, result.message
        assert result.error_code is None
        assert winreg.SetValueEx.call_count == 2
        # Verifie les arguments du premier set
        first_call = winreg.SetValueEx.call_args_list[0]
        # SetValueEx(handle, name, 0, type, data)
        assert first_call.args[1] == "Foo"
        assert first_call.args[3] == winreg.REG_DWORD
        assert first_call.args[4] == 1

    def test_registry_set_idempotent_already_applied(self) -> None:
        """Si la valeur est deja a la cible, on retourne already_applied."""
        action = _make_action(
            method="registry_set",
            params={
                "path": "HKCU\\Software\\WinBoostTest",
                "values": [{"name": "Foo", "type": "REG_DWORD", "data": 1}],
            },
        )
        winreg = self._patch_winreg()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        winreg.OpenKey.return_value = ctx
        winreg.QueryValueEx.return_value = (1, winreg.REG_DWORD)  # deja a 1

        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor._winreg_module", return_value=winreg):
            result = ActionExecutor().apply(action)
        assert result.success is True
        assert result.error_code == "already_applied"
        assert "deja applique" in result.message.lower()
        winreg.SetValueEx.assert_not_called()


# ---------------------------------------------------------------------------
# 6. registry_delete
# ---------------------------------------------------------------------------


class TestRegistryDelete:
    def test_registry_delete_unsafe_refused(self) -> None:
        action = _make_action(
            method="registry_delete",
            params={"path": "HKLM\\SAM\\anything"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "unsafe_registry"

    def test_registry_delete_dry_run(self) -> None:
        action = _make_action(
            method="registry_delete",
            params={"path": "HKCU\\Software\\WinBoostTest", "value_name": "Foo"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action, dry_run=True)
        assert result.success is True
        assert result.error_code == "dry_run"

    def test_registry_delete_value_success(self) -> None:
        action = _make_action(
            method="registry_delete",
            params={"path": "HKCU\\Software\\WinBoostTest", "value_name": "Foo"},
        )
        winreg = MagicMock()
        winreg.HKEY_CURRENT_USER = 0x80000001
        winreg.KEY_SET_VALUE = 0x2
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        winreg.OpenKey.return_value = ctx

        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor._winreg_module", return_value=winreg):
            result = ActionExecutor().apply(action)
        assert result.success is True
        winreg.DeleteValue.assert_called_once_with(ctx, "Foo")


# ---------------------------------------------------------------------------
# 7. service_stop / service_disable / service_set_manual
# ---------------------------------------------------------------------------


class TestServiceMethods:
    def test_service_stop_invalid_no_name(self) -> None:
        action = _make_action(method="service_stop", params={})
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "invalid_params"

    def test_service_stop_calls_sc_stop(self) -> None:
        action = _make_action(
            method="service_stop",
            params={"service": "bthserv"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "stopped", "")) as mrun:
            result = ActionExecutor().apply(action)
        assert result.success is True
        cmd = mrun.call_args.args[0]
        assert cmd[0] == "sc.exe"
        assert cmd[1] == "stop"
        assert cmd[2] == "bthserv"

    def test_service_stop_already_stopped_idempotent(self) -> None:
        """sc.exe retourne 1062 si service deja arrete : on traite comme idempotent."""
        action = _make_action(method="service_stop", params={"service": "bthserv"})
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch(
                "winboost.core.executor.subprocess.run",
                return_value=_completed(1062, "", "FAILED 1062: service is not started"),
            ):
            result = ActionExecutor().apply(action)
        assert result.success is True
        assert result.error_code == "already_applied"

    def test_service_disable_calls_sc_config_disabled(self) -> None:
        action = _make_action(
            method="service_disable",
            params={"service_name": "DiagTrack"},
            risk_level="medium",
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "OK", "")) as mrun:
            result = ActionExecutor().apply(action)
        assert result.success is True
        # 2 appels : config + stop best-effort
        assert mrun.call_count == 2
        first = mrun.call_args_list[0].args[0]
        assert first[0] == "sc.exe"
        assert first[1] == "config"
        assert first[2] == "DiagTrack"
        assert "disabled" in first

    def test_service_set_manual_calls_sc_config_demand(self) -> None:
        action = _make_action(
            method="service_set_manual",
            params={"service_name": "Spooler"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "OK", "")) as mrun:
            result = ActionExecutor().apply(action)
        assert result.success is True
        cmd = mrun.call_args.args[0]
        assert "demand" in cmd


# ---------------------------------------------------------------------------
# 8. powershell + cmd
# ---------------------------------------------------------------------------


class TestPowerShellAndCmd:
    def test_powershell_invalid_no_command(self) -> None:
        action = _make_action(method="powershell", params={})
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "invalid_params"

    def test_powershell_unsafe_command_refused(self) -> None:
        action = _make_action(
            method="powershell",
            params={"command": "Remove-Item -Recurse -Force C:\\"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "unsafe_command"

    def test_powershell_success_calls_subprocess_with_utf8(self) -> None:
        action = _make_action(
            method="powershell",
            params={"command": "Write-Host hello"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "hello", "")) as mrun:
            result = ActionExecutor().apply(action)
        assert result.success is True
        kwargs = mrun.call_args.kwargs
        assert kwargs["encoding"] == "utf-8"
        cmd = mrun.call_args.args[0]
        assert cmd[0] == "powershell.exe"
        assert "-NoProfile" in cmd
        assert "Bypass" in cmd

    def test_powershell_returncode_nonzero_returns_exec_failed(self) -> None:
        action = _make_action(
            method="powershell",
            params={"command": "Write-Host bonjour"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch(
                "winboost.core.executor.subprocess.run",
                return_value=_completed(1, "", "Erreur PS"),
            ):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "exec_failed"
        assert "Erreur PS" in (result.stderr or "") or "Erreur PS" in result.message

    def test_cmd_unsafe_refused(self) -> None:
        action = _make_action(method="cmd", params={"command": "format C: /q"})
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "unsafe_command"

    def test_cmd_success_calls_cmd_exe(self) -> None:
        action = _make_action(
            method="cmd",
            params={"command": "echo hello"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "hello", "")) as mrun:
            result = ActionExecutor().apply(action)
        assert result.success is True
        cmd = mrun.call_args.args[0]
        assert cmd[0] == "cmd.exe"
        assert cmd[1] == "/c"


# ---------------------------------------------------------------------------
# 9. delete_path + clear_directory
# ---------------------------------------------------------------------------


class TestFilesystemMethods:
    def test_delete_path_outside_whitelist_refused(self) -> None:
        action = _make_action(
            method="delete_path",
            params={"path": "C:\\Windows\\System32\\important.dll"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "unsafe_path"

    def test_delete_path_dry_run_does_not_unlink(self, tmp_path: Path) -> None:
        # Cree un faux %TEMP% pour le whitelist match
        target = tmp_path / "victim.txt"
        target.write_text("data")
        action = _make_action(
            method="delete_path",
            params={"path": str(target)},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch.dict("os.environ", {"TEMP": str(tmp_path), "TMP": str(tmp_path)}):
            result = ActionExecutor().apply(action, dry_run=True)
        # En dry-run, la securite verifie %TEMP% — comme on a mis %TEMP%=tmp_path,
        # tmp_path lui-meme commence par %TEMP%, donc whitelist OK
        assert result.dry_run is True
        assert target.exists()  # rien supprime

    def test_delete_path_real_unlink(self, tmp_path: Path) -> None:
        target = tmp_path / "victim.txt"
        target.write_text("data")
        action = _make_action(
            method="delete_path",
            params={"path": str(target)},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch.dict("os.environ", {"TEMP": str(tmp_path), "TMP": str(tmp_path)}):
            result = ActionExecutor().apply(action)
        assert result.success is True
        assert not target.exists()

    def test_delete_path_already_gone_idempotent(self, tmp_path: Path) -> None:
        action = _make_action(
            method="delete_path",
            params={"path": str(tmp_path / "doesnotexist.txt")},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch.dict("os.environ", {"TEMP": str(tmp_path), "TMP": str(tmp_path)}):
            result = ActionExecutor().apply(action)
        assert result.success is True
        assert result.error_code == "already_applied"

    def test_clear_directory_outside_whitelist_refused(self) -> None:
        action = _make_action(
            method="clear_directory",
            params={"path": "C:\\Program Files\\victim", "pattern": "*"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "unsafe_path"

    def test_clear_directory_real(self, tmp_path: Path) -> None:
        d = tmp_path / "tempdir"
        d.mkdir()
        (d / "a.tmp").write_text("a")
        (d / "b.tmp").write_text("b")
        (d / "keep.log").write_text("keep")
        action = _make_action(
            method="clear_directory",
            params={"path": str(d), "pattern": "*.tmp", "recursive": False},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch.dict("os.environ", {"TEMP": str(tmp_path), "TMP": str(tmp_path)}):
            result = ActionExecutor().apply(action)
        assert result.success is True
        assert not (d / "a.tmp").exists()
        assert not (d / "b.tmp").exists()
        assert (d / "keep.log").exists()  # autres patterns intacts

    def test_clear_directory_dry_run_keeps_files(self, tmp_path: Path) -> None:
        d = tmp_path / "tempdir"
        d.mkdir()
        (d / "a.tmp").write_text("a")
        action = _make_action(
            method="clear_directory",
            params={"path": str(d), "pattern": "*.tmp"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch.dict("os.environ", {"TEMP": str(tmp_path), "TMP": str(tmp_path)}):
            result = ActionExecutor().apply(action, dry_run=True)
        assert result.dry_run is True
        assert (d / "a.tmp").exists()


# ---------------------------------------------------------------------------
# 10. scheduled_task_disable
# ---------------------------------------------------------------------------


class TestScheduledTaskDisable:
    def test_no_task_name_returns_invalid(self) -> None:
        action = _make_action(method="scheduled_task_disable", params={})
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor().apply(action)
        assert result.success is False
        assert result.error_code == "invalid_params"

    def test_calls_schtasks_disable(self) -> None:
        action = _make_action(
            method="scheduled_task_disable",
            params={"task_name": "Microsoft\\Windows\\Telemetry"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "", "")) as mrun:
            result = ActionExecutor().apply(action)
        assert result.success is True
        cmd = mrun.call_args.args[0]
        assert cmd[0] == "schtasks.exe"
        assert "/Disable" in cmd

    def test_dry_run_does_not_call_subprocess(self) -> None:
        action = _make_action(
            method="scheduled_task_disable",
            params={"task_name": "FooTask"},
        )
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run") as mrun:
            result = ActionExecutor().apply(action, dry_run=True)
        assert result.dry_run is True
        mrun.assert_not_called()


# ---------------------------------------------------------------------------
# 11. Backup automatique high/critical
# ---------------------------------------------------------------------------


class TestBackupAutomatic:
    def test_high_risk_triggers_backup_for_registry(self, tmp_path: Path) -> None:
        action = _make_action(
            method="registry_set",
            params={
                "path": "HKCU\\Software\\WBTest",
                "values": [{"name": "X", "type": "REG_DWORD", "data": 1}],
            },
            risk_level="high",
        )
        backup = MagicMock()
        backup_entry = MagicMock()
        backup_entry.backup_id = "backup_123"
        backup.create_backup.return_value = backup_entry

        winreg = MagicMock()
        winreg.HKEY_CURRENT_USER = 0x80000001
        winreg.REG_DWORD = 4
        winreg.REG_SZ = 1
        winreg.KEY_READ = 0x20019
        winreg.OpenKey.side_effect = FileNotFoundError()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        winreg.CreateKey.return_value = ctx

        # Le subprocess de reg.exe export doit ecrire un faux fichier pour
        # que _backup_before considere le dump comme reussi.
        def _fake_run(cmd: list[str], **kwargs: Any) -> Any:
            if cmd and cmd[0] == "reg.exe" and "export" in cmd:
                # cmd = ["reg.exe", "export", path, dump_path, "/y"]
                Path(cmd[3]).write_text(";dump")
                return _completed(0, "OK", "")
            return _completed(0, "", "")

        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor._winreg_module", return_value=winreg), \
             patch("winboost.core.executor.subprocess.run", side_effect=_fake_run), \
             patch("winboost.core.executor.sys.platform", "win32"), \
             patch.dict("os.environ", {"TEMP": str(tmp_path)}):
            ex = ActionExecutor(backup_manager=backup)
            result = ex.apply(action)

        assert result.success is True
        # Le backup a ete tente
        backup.create_backup.assert_called_once()
        # rollback_id propage
        assert result.rollback_id == "backup_123"

    def test_low_risk_does_not_trigger_backup(self) -> None:
        action = _make_action(
            method="powershell",
            params={"command": "Write-Host hi"},
            risk_level="low",
        )
        backup = MagicMock()
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "hi", "")):
            result = ActionExecutor(backup_manager=backup).apply(action)
        assert result.success is True
        backup.create_backup.assert_not_called()
        assert result.rollback_id is None

    def test_dry_run_does_not_trigger_backup_even_high(self) -> None:
        action = _make_action(
            method="registry_set",
            params={
                "path": "HKCU\\Software\\WBTest",
                "values": [{"name": "X", "type": "REG_DWORD", "data": 1}],
            },
            risk_level="critical",
        )
        backup = MagicMock()
        with patch("winboost.core.executor.is_admin", return_value=True):
            result = ActionExecutor(backup_manager=backup).apply(action, dry_run=True)
        assert result.dry_run is True
        backup.create_backup.assert_not_called()


# ---------------------------------------------------------------------------
# 12. HistoryManager logging
# ---------------------------------------------------------------------------


class TestHistoryLogging:
    def test_history_logged_on_success(self) -> None:
        action = _make_action(
            method="powershell",
            params={"command": "Write-Host ok"},
        )
        history = MagicMock()
        history.log_action.return_value = 7
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "ok", "")):
            result = ActionExecutor(history_manager=history).apply(action)
        assert result.success is True
        history.log_action.assert_called_once()
        kwargs = history.log_action.call_args.kwargs
        assert kwargs["action_type"] == "execute"
        assert kwargs["result_status"] == "success"
        assert kwargs["risk_level"] == "low"
        assert kwargs["module_name"].startswith("executor:")

    def test_history_logged_on_failure(self) -> None:
        action = _make_action(method="quantum_x", params={})
        history = MagicMock()
        with patch("winboost.core.executor.is_admin", return_value=True):
            ActionExecutor(history_manager=history).apply(action)
        history.log_action.assert_called_once()
        kwargs = history.log_action.call_args.kwargs
        assert "error" in kwargs["result_status"]

    def test_history_logged_on_admin_required(self) -> None:
        action = _make_action(
            method="powershell",
            params={"command": "Write-Host ok"},
            requires_admin=True,
        )
        history = MagicMock()
        with patch("winboost.core.executor.is_admin", return_value=False):
            result = ActionExecutor(history_manager=history).apply(action)
        assert result.error_code == "admin_required"
        history.log_action.assert_called_once()

    def test_history_logged_on_dry_run(self) -> None:
        action = _make_action(
            method="powershell",
            params={"command": "Write-Host ok"},
        )
        history = MagicMock()
        with patch("winboost.core.executor.is_admin", return_value=True):
            ActionExecutor(history_manager=history).apply(action, dry_run=True)
        history.log_action.assert_called_once()
        kwargs = history.log_action.call_args.kwargs
        assert kwargs["result_status"] == "dry_run"

    def test_history_failure_does_not_break_apply(self) -> None:
        """Si HistoryManager.log_action leve, apply doit quand meme retourner ApplyResult."""
        action = _make_action(method="powershell", params={"command": "Write-Host ok"})
        history = MagicMock()
        history.log_action.side_effect = RuntimeError("DB locked")
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "ok", "")):
            result = ActionExecutor(history_manager=history).apply(action)
        assert isinstance(result, ApplyResult)
        assert result.success is True


# ---------------------------------------------------------------------------
# 13. Sérialisation ApplyResult.to_dict + JSON roundtrip
# ---------------------------------------------------------------------------


class TestApplyResultSerialization:
    def test_to_dict_keys_present(self) -> None:
        r = ApplyResult(success=True, message="x", action_id="a")
        d = r.to_dict()
        for k in (
            "success", "message", "action_id", "rollback_id", "error_code",
            "stdout", "stderr", "duration_ms", "method", "dry_run", "extra",
        ):
            assert k in d

    def test_json_roundtrip_complex_extra(self) -> None:
        r = ApplyResult(
            success=True,
            message="ok",
            action_id="x",
            method="registry_set",
            extra={"path": "HKCU\\Test", "values": [{"n": "A", "d": 1}]},
        )
        s = json.dumps(r.to_dict())
        parsed = json.loads(s)
        assert parsed["extra"]["values"][0]["d"] == 1


# ---------------------------------------------------------------------------
# 14. Duration_ms est calcule
# ---------------------------------------------------------------------------


class TestDurationMs:
    def test_duration_ms_present_and_nonneg(self) -> None:
        action = _make_action(method="powershell", params={"command": "Write-Host hi"})
        with patch("winboost.core.executor.is_admin", return_value=True), \
             patch("winboost.core.executor.subprocess.run", return_value=_completed(0, "hi", "")):
            result = ActionExecutor().apply(action)
        assert result.duration_ms >= 0
