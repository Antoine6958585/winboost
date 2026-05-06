"""Tests par theme — chaque check est mocke individuellement.

Chaque test patch `winboost.diagnose.checks.run_powershell` (le seul point
qui touche le systeme) pour exercer la logique du check sans depender
d'une vraie installation Windows.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from winboost.diagnose.checks import Check, CheckResult, Severity
from winboost.diagnose.themes import audio as audio_theme
from winboost.diagnose.themes import bluetooth as bt_theme
from winboost.diagnose.themes import display as display_theme
from winboost.diagnose.themes import gaming as gaming_theme
from winboost.diagnose.themes import network as network_theme
from winboost.utils.windows_native import PowerShellResult, WindowsNativeError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ps_ok(stdout: str = "", stderr: str = "") -> PowerShellResult:
    return PowerShellResult(stdout=stdout, stderr=stderr, returncode=0)


def _ps_fail(stderr: str = "boom") -> PowerShellResult:
    return PowerShellResult(stdout="", stderr=stderr, returncode=1)


def _run(check: Check) -> CheckResult:
    """Execute un check via safe_run() (comme le runner)."""
    return check.safe_run()


# ---------------------------------------------------------------------------
# get_checks() — coherence basique de chaque theme
# ---------------------------------------------------------------------------


class TestThemeGetChecks:
    def test_bluetooth_get_checks_returns_6(self):
        # 5 checks initiaux + BluetoothGamepadMappingCheck (T084)
        checks = bt_theme.get_checks()
        assert len(checks) == 6
        for c in checks:
            assert isinstance(c, Check)

    def test_gaming_get_checks_returns_5(self):
        checks = gaming_theme.get_checks()
        assert len(checks) == 5

    def test_network_get_checks_returns_5(self):
        checks = network_theme.get_checks()
        assert len(checks) == 5

    def test_audio_get_checks_returns_5(self):
        checks = audio_theme.get_checks()
        assert len(checks) == 5

    def test_display_get_checks_returns_5(self):
        checks = display_theme.get_checks()
        assert len(checks) == 5

    def test_all_check_names_unique_across_themes(self):
        all_names: list[str] = []
        for getter in (
            bt_theme.get_checks,
            gaming_theme.get_checks,
            network_theme.get_checks,
            audio_theme.get_checks,
            display_theme.get_checks,
        ):
            for c in getter():
                all_names.append(c.name)
        assert len(all_names) == len(set(all_names)), "noms de checks non uniques"


# ---------------------------------------------------------------------------
# Bluetooth checks
# ---------------------------------------------------------------------------


class TestBluetoothServiceCheck:
    def test_running_returns_ok(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE  : 4  RUNNING")
            r = _run(bt_theme.BluetoothServiceCheck())
        assert r.severity == Severity.OK.value
        assert "execution" in r.message

    def test_stopped_returns_error_with_action(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE  : 1  STOPPED")
            r = _run(bt_theme.BluetoothServiceCheck())
        assert r.severity == Severity.ERROR.value
        assert "net_012" in r.suggested_actions

    def test_not_installed_returns_critical(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            # Windows error 1060 = service introuvable
            mock_ps.return_value = PowerShellResult(
                stdout="FAILED 1060", stderr="", returncode=1
            )
            r = _run(bt_theme.BluetoothServiceCheck())
        assert r.severity == Severity.CRITICAL.value

    def test_native_error_becomes_warning(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.side_effect = WindowsNativeError("PS introuvable")
            r = _run(bt_theme.BluetoothServiceCheck())
        # Le service_status helper avale WindowsNativeError -> "unknown"
        # donc on aura severity warning
        assert r.severity == Severity.WARNING.value


class TestBluetoothRadioCheck:
    def test_radio_ok_returns_ok(self):
        # Simuler une sortie CSV PowerShell : header + 1 device
        csv = '"FriendlyName","Status","InstanceId","Class"\n"BT Radio","OK","BT\\1","Bluetooth"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothRadioCheck())
        assert r.severity == Severity.OK.value
        assert "OK" in r.message

    def test_no_devices_returns_warning(self):
        csv = '"FriendlyName","Status","InstanceId","Class"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothRadioCheck())
        assert r.severity == Severity.WARNING.value

    def test_radio_in_error_returns_error(self):
        csv = (
            '"FriendlyName","Status","InstanceId","Class"\n'
            '"BT Radio","Error","BT\\1","Bluetooth"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothRadioCheck())
        assert r.severity == Severity.ERROR.value
        assert "net_012" in r.suggested_actions


class TestBluetoothDriverFreshness:
    def test_old_driver_returns_warning(self):
        # Driver vieux de 3 ans
        old_date = (datetime.now() - timedelta(days=365 * 3)).strftime("%m/%d/%Y")
        csv = f'"Name","DriverDate"\n"BT Adapter","{old_date}"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothDriverFreshnessCheck())
        assert r.severity == Severity.WARNING.value
        assert "ancien" in r.message.lower()

    def test_recent_driver_returns_ok(self):
        recent = (datetime.now() - timedelta(days=30)).strftime("%m/%d/%Y")
        csv = f'"Name","DriverDate"\n"BT","{recent}"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothDriverFreshnessCheck())
        assert r.severity == Severity.OK.value

    def test_unparseable_dates_returns_warning(self):
        csv = '"Name","DriverDate"\n"BT","not_a_date"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothDriverFreshnessCheck())
        assert r.severity == Severity.WARNING.value


class TestBluetoothPairedDevices:
    def test_no_paired_returns_warning(self):
        csv = '"FriendlyName","Status","InstanceId","Class"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothPairedDevicesCheck())
        assert r.severity == Severity.WARNING.value

    def test_all_disconnected_returns_error(self):
        csv = (
            '"FriendlyName","Status","InstanceId","Class"\n'
            '"Xbox Wireless Controller","Unknown","BT\\1","Bluetooth"\n'
            '"Sony WH-1000XM4","Unknown","BT\\2","Bluetooth"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothPairedDevicesCheck())
        assert r.severity == Severity.ERROR.value
        assert "net_011" in r.suggested_actions

    def test_some_connected_returns_ok(self):
        csv = (
            '"FriendlyName","Status","InstanceId","Class"\n'
            '"Xbox Wireless Controller","OK","BT\\1","Bluetooth"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothPairedDevicesCheck())
        assert r.severity == Severity.OK.value


class TestBluetoothGamepadMapping:
    """Tests du nouveau check BluetoothGamepadMappingCheck (T084).

    Use case Antoine : detecter une manette BT mal-mappee (vue par Windows
    comme "Generic Bluetooth Peripheral" au lieu de "Xbox Wireless Controller").
    """

    def test_no_gamepad_returns_ok_with_explicit_message(self):
        # Sortie : header seul (aucun device matche)
        csv = '"FriendlyName","Status","Class","InstanceId"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothGamepadMappingCheck())
        assert r.severity == Severity.OK.value
        assert "Aucune manette" in r.message
        assert r.details["gamepads"] == []

    def test_xbox_well_mapped_via_xnacomposite(self):
        # Cas ideal : Windows reconnait la manette via le driver Xbox dedie
        csv = (
            '"FriendlyName","Status","Class","InstanceId"\n'
            '"Xbox Wireless Controller","OK","XnaComposite","BTHENUM\\\\1"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothGamepadMappingCheck())
        assert r.severity == Severity.OK.value
        assert "correctement" in r.message.lower()
        names = [g["name"] for g in r.details["gamepads"]]
        classes = [g["class"] for g in r.details["gamepads"]]
        statuses = [g["status"] for g in r.details["gamepads"]]
        assert "Xbox Wireless Controller" in names
        assert "XnaComposite" in classes
        assert statuses == ["well_mapped"]

    def test_xbox_mismapped_as_generic_bluetooth(self):
        # Cas Antoine : la manette est appairee mais Windows la voit
        # comme un peripherique BT generique. Driver XINPUT pas installe.
        csv = (
            '"FriendlyName","Status","Class","InstanceId"\n'
            '"Xbox Wireless Controller","OK","Bluetooth","BTHENUM\\\\1"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothGamepadMappingCheck())
        assert r.severity == Severity.WARNING.value
        assert "mal mappee" in r.message.lower()
        assert "Xbox Wireless Controller" in r.message
        assert "bt_unpair_repair" in r.suggested_actions
        assert r.details["mismapped_count"] == 1

    def test_dualsense_well_mapped(self):
        # Manette PS5 reconnue specifiquement en HIDClass
        csv = (
            '"FriendlyName","Status","Class","InstanceId"\n'
            '"DualSense Wireless Controller","OK","HIDClass","BTHENUM\\\\3"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothGamepadMappingCheck())
        assert r.severity == Severity.OK.value
        assert any(
            g["name"] == "DualSense Wireless Controller"
            for g in r.details["gamepads"]
        )
        assert all(g["status"] == "well_mapped" for g in r.details["gamepads"])

    def test_generic_bluetooth_peripheral_with_gamepad_hint_is_mismapped(self):
        # FriendlyName = "Bluetooth Peripheral Device" SANS hint gamepad ->
        # le check ne le considere pas comme une manette (pas de faux positif).
        # Mais "Xbox Bluetooth Peripheral Device" -> hint Xbox + nom generique
        # -> mismapped detecte.
        csv = (
            '"FriendlyName","Status","Class","InstanceId"\n'
            '"Xbox Bluetooth Peripheral Device","OK","HIDClass","BTHENUM\\\\7"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothGamepadMappingCheck())
        assert r.severity == Severity.WARNING.value
        assert "bt_unpair_repair" in r.suggested_actions

    def test_empty_or_malformed_powershell_output_is_robust(self):
        # Sortie PS vide -> ok (aucune manette), pas de crash
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("")
            r = _run(bt_theme.BluetoothGamepadMappingCheck())
        assert r.severity == Severity.OK.value

        # Sortie PS malformee (juste une virgule) -> pas de crash
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(",,,\nfoo,bar")
            r = _run(bt_theme.BluetoothGamepadMappingCheck())
        assert r.severity in {Severity.OK.value, Severity.WARNING.value}

        # PowerShell echoue -> warning sans crash
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_fail("ps boom")
            r = _run(bt_theme.BluetoothGamepadMappingCheck())
        assert r.severity == Severity.WARNING.value

    def test_native_error_becomes_warning(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.side_effect = WindowsNativeError("PS introuvable")
            r = _run(bt_theme.BluetoothGamepadMappingCheck())
        assert r.severity == Severity.WARNING.value


class TestBluetoothXInputConflict:
    def test_no_controllers_returns_ok(self):
        csv = '"FriendlyName","Status","InstanceId","Class"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothXInputConflictCheck())
        assert r.severity == Severity.OK.value

    def test_controllers_xinput_compat(self):
        csv = (
            '"FriendlyName","Status","InstanceId","Class"\n'
            '"Xbox Wireless Controller","OK","HID\\1","HIDClass"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothXInputConflictCheck())
        assert r.severity == Severity.OK.value
        assert "compatibles XInput" in r.message

    def test_controllers_directinput_only_returns_warning(self):
        csv = (
            '"FriendlyName","Status","InstanceId","Class"\n'
            '"Generic Wireless Gamepad","OK","HID\\1","HIDClass"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(bt_theme.BluetoothXInputConflictCheck())
        assert r.severity == Severity.WARNING.value
        assert "DirectInput" in r.message


# ---------------------------------------------------------------------------
# Gaming checks
# ---------------------------------------------------------------------------


class TestGamingChecks:
    def test_gamepad_detection_with_ok_pad(self):
        csv = (
            '"FriendlyName","Status","Class"\n'
            '"Xbox Wireless Controller","OK","HIDClass"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(gaming_theme.GamepadDetectionCheck())
        assert r.severity == Severity.OK.value

    def test_gamepad_detection_no_pads_returns_warning(self):
        csv = '"FriendlyName","Status","Class"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(gaming_theme.GamepadDetectionCheck())
        assert r.severity == Severity.WARNING.value

    def test_xbox_driver_old_returns_warning(self):
        old_date = (datetime.now() - timedelta(days=365 * 4)).strftime("%m/%d/%Y")
        csv = f'"Name","DriverDate"\n"Xbox Controller","{old_date}"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(gaming_theme.XboxControllerDriverCheck())
        assert r.severity == Severity.WARNING.value

    def test_xbox_driver_no_data_returns_warning(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("")
            r = _run(gaming_theme.XboxControllerDriverCheck())
        assert r.severity == Severity.WARNING.value

    def test_steam_input_present(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("True")
            r = _run(gaming_theme.SteamInputCheck())
        assert r.severity == Severity.OK.value
        assert r.details["steam_installed"] is True

    def test_steam_input_absent(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("False")
            r = _run(gaming_theme.SteamInputCheck())
        assert r.details["steam_installed"] is False

    def test_dual_input_conflict_detected(self):
        csv = (
            '"FriendlyName"\n'
            '"Xbox Wireless Controller"\n'
            '"Wireless Controller"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(gaming_theme.DualInputConflictCheck())
        assert r.severity == Severity.WARNING.value
        assert "conflit" in r.message.lower()

    def test_xbl_gamesave_running(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE : 4 RUNNING")
            r = _run(gaming_theme.XblGameSaveCheck())
        assert r.severity == Severity.OK.value

    def test_xbl_gamesave_stopped(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE : 1 STOPPED")
            r = _run(gaming_theme.XblGameSaveCheck())
        assert r.severity == Severity.WARNING.value


# ---------------------------------------------------------------------------
# Network checks
# ---------------------------------------------------------------------------


class TestNetworkChecks:
    def test_adapter_up_returns_ok(self):
        csv = (
            '"Name","InterfaceDescription","Status","LinkSpeed"\n'
            '"Wi-Fi","Intel Wi-Fi 6","Up","1 Gbps"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(network_theme.NetAdapterCheck())
        assert r.severity == Severity.OK.value

    def test_no_adapter_up_returns_critical(self):
        csv = '"Name","InterfaceDescription","Status","LinkSpeed"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(network_theme.NetAdapterCheck())
        assert r.severity == Severity.CRITICAL.value

    def test_dns_resolution_ok(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("142.250.74.46")
            r = _run(network_theme.DnsResolutionCheck())
        assert r.severity == Severity.OK.value

    def test_dns_resolution_fail(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("DNS_FAIL: server unreachable")
            r = _run(network_theme.DnsResolutionCheck())
        assert r.severity == Severity.ERROR.value
        assert "net_014" in r.suggested_actions

    def test_gateway_ping_ok(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("True")
            r = _run(network_theme.GatewayPingCheck())
        assert r.severity == Severity.OK.value

    def test_gateway_ping_no_gateway(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("NO_GATEWAY")
            r = _run(network_theme.GatewayPingCheck())
        assert r.severity == Severity.ERROR.value
        assert "net_016" in r.suggested_actions

    def test_dnscache_running(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE : 4 RUNNING")
            r = _run(network_theme.DnscacheServiceCheck())
        assert r.severity == Severity.OK.value

    def test_dnscache_stopped(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE : 1 STOPPED")
            r = _run(network_theme.DnscacheServiceCheck())
        assert r.severity == Severity.ERROR.value
        assert "net_014" in r.suggested_actions

    def test_ipv6_status(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("2")
            r = _run(network_theme.IPv6ConflictCheck())
        assert r.severity == Severity.OK.value
        assert r.details["ipv6_enabled_adapters"] == 2


# ---------------------------------------------------------------------------
# Audio checks
# ---------------------------------------------------------------------------


class TestAudioChecks:
    def test_audio_service_running(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE : 4 RUNNING")
            r = _run(audio_theme.AudioServiceCheck())
        assert r.severity == Severity.OK.value

    def test_audio_service_stopped_critical(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE : 1 STOPPED")
            r = _run(audio_theme.AudioServiceCheck())
        assert r.severity == Severity.CRITICAL.value

    def test_default_playback_present(self):
        csv = '"FriendlyName"\n"Speakers (Realtek)"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(audio_theme.DefaultPlaybackDeviceCheck())
        assert r.severity == Severity.OK.value

    def test_default_playback_absent(self):
        csv = '"FriendlyName"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(audio_theme.DefaultPlaybackDeviceCheck())
        assert r.severity == Severity.ERROR.value

    def test_recording_device_present(self):
        csv = '"FriendlyName","Status"\n"Microphone Array","OK"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(audio_theme.DefaultRecordingDeviceCheck())
        assert r.severity == Severity.OK.value

    def test_recording_device_absent(self):
        csv = '"FriendlyName","Status"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(audio_theme.DefaultRecordingDeviceCheck())
        assert r.severity == Severity.WARNING.value

    def test_audio_driver_recent(self):
        recent = (datetime.now() - timedelta(days=30)).strftime("%m/%d/%Y")
        csv = f'"Name","DriverDate"\n"Realtek HD","{recent}"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(audio_theme.AudioDriverFreshnessCheck())
        assert r.severity == Severity.OK.value

    def test_multiple_endpoints_warning(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("8")
            r = _run(audio_theme.MultipleEndpointsConflictCheck())
        assert r.severity == Severity.WARNING.value


# ---------------------------------------------------------------------------
# Display checks
# ---------------------------------------------------------------------------


class TestDisplayChecks:
    def test_brightness_wmi_ok(self):
        with patch("winboost.diagnose.themes.display.get_brightness") as mock_b:
            mock_b.return_value = 50
            r = _run(display_theme.BrightnessWmiCheck())
        assert r.severity == Severity.OK.value
        assert r.details["current_brightness"] == 50

    def test_brightness_wmi_unavailable(self):
        with patch("winboost.diagnose.themes.display.get_brightness") as mock_b:
            mock_b.side_effect = WindowsNativeError("WMI ko")
            r = _run(display_theme.BrightnessWmiCheck())
        assert r.severity == Severity.WARNING.value

    def test_monitor_detection_one_monitor(self):
        csv = '"FriendlyName"\n"Generic PnP Monitor"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(display_theme.MonitorDetectionCheck())
        assert r.severity == Severity.OK.value
        assert r.details["monitors_count"] == 1

    def test_monitor_detection_none(self):
        csv = '"FriendlyName"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(display_theme.MonitorDetectionCheck())
        assert r.severity == Severity.ERROR.value

    def test_gpu_driver_recent(self):
        recent = (datetime.now() - timedelta(days=15)).strftime("%m/%d/%Y")
        csv = f'"Name","DriverDate"\n"NVIDIA GeForce RTX","{recent}"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(display_theme.GpuDriverFreshnessCheck())
        assert r.severity == Severity.OK.value

    def test_gpu_driver_old(self):
        old = (datetime.now() - timedelta(days=400)).strftime("%m/%d/%Y")
        csv = f'"Name","DriverDate"\n"NVIDIA","{old}"'
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            r = _run(display_theme.GpuDriverFreshnessCheck())
        assert r.severity == Severity.WARNING.value

    def test_resolution_ok(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("1920x1080")
            r = _run(display_theme.CurrentResolutionCheck())
        assert r.severity == Severity.OK.value
        assert r.details["width"] == 1920

    def test_resolution_low_warning(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("800x600")
            r = _run(display_theme.CurrentResolutionCheck())
        assert r.severity == Severity.WARNING.value

    def test_hdr_support_count(self):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("1")
            r = _run(display_theme.HdrSupportCheck())
        assert r.severity == Severity.OK.value


# ---------------------------------------------------------------------------
# Helpers checks.py
# ---------------------------------------------------------------------------


class TestServiceStatusHelper:
    def test_running_parsed(self):
        from winboost.diagnose.checks import service_status

        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE : 4 RUNNING")
            assert service_status("any") == "running"

    def test_stopped_parsed(self):
        from winboost.diagnose.checks import service_status

        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok("STATE : 1 STOPPED")
            assert service_status("any") == "stopped"

    def test_not_installed_parsed(self):
        from winboost.diagnose.checks import service_status

        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = PowerShellResult(
                stdout="FAILED 1060 :", stderr="", returncode=1
            )
            assert service_status("ghost") == "not_installed"

    def test_native_error_returns_unknown(self):
        from winboost.diagnose.checks import service_status

        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.side_effect = WindowsNativeError("ko")
            assert service_status("any") == "unknown"


class TestPnpQueryHelper:
    def test_returns_empty_on_failure(self):
        from winboost.diagnose.checks import pnp_query

        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_fail("ko")
            assert pnp_query(class_filter="Bluetooth") == []

    def test_parses_csv_output(self):
        from winboost.diagnose.checks import pnp_query

        csv = (
            '"FriendlyName","Status","InstanceId","Class"\n'
            '"BT Radio","OK","BT\\1","Bluetooth"'
        )
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.return_value = _ps_ok(csv)
            devices = pnp_query(class_filter="Bluetooth")
        assert len(devices) == 1
        assert devices[0]["name"] == "BT Radio"
        assert devices[0]["status"] == "OK"

    def test_native_error_returns_empty(self):
        from winboost.diagnose.checks import pnp_query

        with patch("winboost.diagnose.checks.run_powershell") as mock_ps:
            mock_ps.side_effect = WindowsNativeError("ko")
            assert pnp_query() == []


# ---------------------------------------------------------------------------
# Validation safe_run sur tous les checks reels avec PS qui repond ""
# ---------------------------------------------------------------------------


class TestAllChecksSafeRunDontCrash:
    """Regression test : aucun check ne doit lever d'exception non geree
    quand PowerShell retourne une sortie vide ou un fail."""

    @pytest.mark.parametrize(
        "getter",
        [
            bt_theme.get_checks,
            gaming_theme.get_checks,
            network_theme.get_checks,
            audio_theme.get_checks,
            display_theme.get_checks,
        ],
    )
    def test_empty_powershell_response_does_not_crash(self, getter):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps, patch(
            "winboost.diagnose.themes.display.get_brightness"
        ) as mock_b:
            mock_ps.return_value = _ps_ok("")
            mock_b.side_effect = WindowsNativeError("no wmi")
            for check in getter():
                r = check.safe_run()
                assert isinstance(r, CheckResult)
                # severity reste valide
                assert r.severity in {s.value for s in Severity}

    @pytest.mark.parametrize(
        "getter",
        [
            bt_theme.get_checks,
            gaming_theme.get_checks,
            network_theme.get_checks,
            audio_theme.get_checks,
            display_theme.get_checks,
        ],
    )
    def test_powershell_failure_does_not_crash(self, getter):
        with patch("winboost.diagnose.checks.run_powershell") as mock_ps, patch(
            "winboost.diagnose.themes.display.get_brightness"
        ) as mock_b:
            mock_ps.return_value = _ps_fail("boom")
            mock_b.side_effect = WindowsNativeError("no wmi")
            for check in getter():
                r = check.safe_run()
                assert isinstance(r, CheckResult)
                assert r.severity in {s.value for s in Severity}
