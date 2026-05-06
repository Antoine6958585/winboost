"""Tests pour winboost.utils.audio_native (helpers Core Audio via pycaw).

Ces tests mockent integralement pycaw + comtypes pour pouvoir tourner sur
Linux CI sans Windows ni device audio. Verifient :
- API publique (get/set volume, get/set mute, toggle, get_default_device)
- Clamp 0-100, rejet types invalides
- Strict mute (pas un toggle), strict volume
- Erreurs claires si pycaw absent ou COM en panne
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from winboost.utils.audio_native import (
    AudioNativeError,
    _clamp_volume,
    get_default_device,
    get_volume,
    is_muted,
    set_mute,
    set_volume,
    toggle_mute,
)


def _make_endpoint(volume_scalar: float = 0.5, muted: bool = False) -> MagicMock:
    """Construit un mock IAudioEndpointVolume credible."""
    endpoint = MagicMock(name="IAudioEndpointVolume")
    endpoint.GetMasterVolumeLevelScalar.return_value = volume_scalar
    endpoint.SetMasterVolumeLevelScalar.return_value = None
    endpoint.GetMute.return_value = 1 if muted else 0
    endpoint.SetMute.return_value = None
    return endpoint


def _patch_endpoint(endpoint: MagicMock):
    """Patch _get_endpoint_volume() pour qu'il retourne notre mock."""
    return patch(
        "winboost.utils.audio_native._get_endpoint_volume", return_value=endpoint
    )


# =============================================================================
# Clamp + validation types
# =============================================================================


class TestClampVolume:
    def test_clamp_inside_range_returns_unchanged(self):
        assert _clamp_volume(50) == 50
        assert _clamp_volume(0) == 0
        assert _clamp_volume(100) == 100

    def test_clamp_above_returns_100(self):
        assert _clamp_volume(150) == 100
        assert _clamp_volume(9999) == 100

    def test_clamp_below_returns_0(self):
        assert _clamp_volume(-10) == 0
        assert _clamp_volume(-1) == 0

    def test_rejects_string(self):
        with pytest.raises(ValueError, match="int"):
            _clamp_volume("50")  # type: ignore[arg-type]

    def test_rejects_float(self):
        with pytest.raises(ValueError, match="int"):
            _clamp_volume(50.5)  # type: ignore[arg-type]

    def test_rejects_bool(self):
        # bool est techniquement int en Python — on le rejette explicitement
        with pytest.raises(ValueError, match="int"):
            _clamp_volume(True)  # type: ignore[arg-type]

    def test_rejects_none(self):
        with pytest.raises(ValueError, match="int"):
            _clamp_volume(None)  # type: ignore[arg-type]


# =============================================================================
# set_volume — appel pycaw correct
# =============================================================================


class TestSetVolume:
    def test_calls_pycaw_set_master_volume_level_scalar(self):
        endpoint = _make_endpoint()
        with _patch_endpoint(endpoint):
            set_volume(50)
        endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(0.5, None)

    def test_zero_volume(self):
        endpoint = _make_endpoint()
        with _patch_endpoint(endpoint):
            set_volume(0)
        endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(0.0, None)

    def test_max_volume(self):
        endpoint = _make_endpoint()
        with _patch_endpoint(endpoint):
            set_volume(100)
        endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(1.0, None)

    def test_above_100_clamped(self):
        endpoint = _make_endpoint()
        with _patch_endpoint(endpoint):
            set_volume(150)
        endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(1.0, None)

    def test_negative_clamped(self):
        endpoint = _make_endpoint()
        with _patch_endpoint(endpoint):
            set_volume(-10)
        endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(0.0, None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            set_volume("50")  # type: ignore[arg-type]

    def test_pycaw_raises_wrapped_in_audio_native_error(self):
        endpoint = _make_endpoint()
        endpoint.SetMasterVolumeLevelScalar.side_effect = OSError("COM error")
        with _patch_endpoint(endpoint), pytest.raises(AudioNativeError, match="volume"):
            set_volume(50)


# =============================================================================
# get_volume
# =============================================================================


class TestGetVolume:
    def test_returns_int_0_100(self):
        endpoint = _make_endpoint(volume_scalar=0.75)
        with _patch_endpoint(endpoint):
            result = get_volume()
        assert result == 75
        assert isinstance(result, int)

    def test_returns_zero_when_silent(self):
        endpoint = _make_endpoint(volume_scalar=0.0)
        with _patch_endpoint(endpoint):
            assert get_volume() == 0

    def test_returns_100_when_max(self):
        endpoint = _make_endpoint(volume_scalar=1.0)
        with _patch_endpoint(endpoint):
            assert get_volume() == 100

    def test_rounds_correctly(self):
        # 0.555 -> 55 (round half to even Python = banker's rounding)
        endpoint = _make_endpoint(volume_scalar=0.554)
        with _patch_endpoint(endpoint):
            assert get_volume() == 55

    def test_pycaw_failure_wrapped(self):
        endpoint = _make_endpoint()
        endpoint.GetMasterVolumeLevelScalar.side_effect = OSError("COM dead")
        with _patch_endpoint(endpoint), pytest.raises(AudioNativeError, match="volume"):
            get_volume()


# =============================================================================
# Mute strict — pas un toggle
# =============================================================================


class TestSetMute:
    def test_set_mute_true_calls_set_mute_with_one(self):
        endpoint = _make_endpoint(muted=False)
        with _patch_endpoint(endpoint):
            set_mute(True)
        endpoint.SetMute.assert_called_once_with(1, None)

    def test_set_mute_false_calls_set_mute_with_zero(self):
        endpoint = _make_endpoint(muted=True)
        with _patch_endpoint(endpoint):
            set_mute(False)
        endpoint.SetMute.assert_called_once_with(0, None)

    def test_set_mute_true_when_already_muted_still_calls_with_one(self):
        # PROPRIETE STRICTE : pas un toggle. set_mute(True) sur device deja mute
        # doit re-appeler SetMute(1) — pas no-op silencieux et surtout pas toggle.
        endpoint = _make_endpoint(muted=True)
        with _patch_endpoint(endpoint):
            set_mute(True)
        endpoint.SetMute.assert_called_once_with(1, None)

    def test_set_mute_false_when_already_unmuted_still_calls_with_zero(self):
        endpoint = _make_endpoint(muted=False)
        with _patch_endpoint(endpoint):
            set_mute(False)
        endpoint.SetMute.assert_called_once_with(0, None)

    def test_pycaw_failure_wrapped(self):
        endpoint = _make_endpoint()
        endpoint.SetMute.side_effect = OSError("COM denied")
        with _patch_endpoint(endpoint), pytest.raises(AudioNativeError, match="mute"):
            set_mute(True)


class TestIsMuted:
    def test_returns_true_when_muted(self):
        endpoint = _make_endpoint(muted=True)
        with _patch_endpoint(endpoint):
            assert is_muted() is True

    def test_returns_false_when_not_muted(self):
        endpoint = _make_endpoint(muted=False)
        with _patch_endpoint(endpoint):
            assert is_muted() is False

    def test_returns_bool_not_int(self):
        endpoint = _make_endpoint(muted=True)
        with _patch_endpoint(endpoint):
            assert isinstance(is_muted(), bool)

    def test_pycaw_failure_wrapped(self):
        endpoint = _make_endpoint()
        endpoint.GetMute.side_effect = OSError("COM unreachable")
        with _patch_endpoint(endpoint), pytest.raises(AudioNativeError, match="mute"):
            is_muted()


# =============================================================================
# Toggle mute (helper, change l'etat + retourne le NOUVEAU)
# =============================================================================


class TestToggleMute:
    def test_toggle_from_unmuted_to_muted(self):
        endpoint = _make_endpoint(muted=False)
        with _patch_endpoint(endpoint):
            new_state = toggle_mute()
        assert new_state is True
        endpoint.SetMute.assert_called_once_with(1, None)

    def test_toggle_from_muted_to_unmuted(self):
        endpoint = _make_endpoint(muted=True)
        with _patch_endpoint(endpoint):
            new_state = toggle_mute()
        assert new_state is False
        endpoint.SetMute.assert_called_once_with(0, None)


# =============================================================================
# get_default_device
# =============================================================================


class TestGetDefaultDevice:
    def test_returns_dict_with_expected_keys(self):
        endpoint = _make_endpoint(volume_scalar=0.6, muted=False)

        fake_speakers = MagicMock()
        fake_speakers.GetId.return_value = "{0.0.0.00000000}.abc"

        # On stub _import_pycaw + AudioUtilities.GetSpeakers + GetAllDevices
        fake_au = MagicMock()
        fake_au.GetSpeakers.return_value = fake_speakers
        fake_au.GetAllDevices.return_value = [
            SimpleNamespace(
                id="{0.0.0.00000000}.abc",
                FriendlyName="Speakers (Realtek)",
                state="Active",
            )
        ]

        with patch(
            "winboost.utils.audio_native._import_pycaw",
            return_value=(fake_au, MagicMock(), MagicMock()),
        ), _patch_endpoint(endpoint):
            result = get_default_device()

        assert set(result.keys()) == {"name", "id", "volume", "muted"}
        assert result["volume"] == 60
        assert result["muted"] is False
        assert result["id"] == "{0.0.0.00000000}.abc"
        assert result["name"] == "Speakers (Realtek)"

    def test_no_default_device_raises(self):
        fake_au = MagicMock()
        fake_au.GetSpeakers.return_value = None
        with patch(
            "winboost.utils.audio_native._import_pycaw",
            return_value=(fake_au, MagicMock(), MagicMock()),
        ), pytest.raises(AudioNativeError, match="Aucun"):
            get_default_device()


# =============================================================================
# pycaw absent — message d'install clair
# =============================================================================


class TestPycawAbsent:
    def test_import_error_gives_install_hint(self):
        # On simule l'absence de pycaw en patchant l'import lui-meme.
        # _import_pycaw essaie : from pycaw.pycaw import ... — on intercept.
        original_modules = {
            k: sys.modules.get(k) for k in ("pycaw", "pycaw.pycaw", "comtypes")
        }
        sys.modules["pycaw"] = None  # type: ignore[assignment]
        sys.modules["pycaw.pycaw"] = None  # type: ignore[assignment]
        try:
            # Re-import du symbole pour declencher le ImportError dans _import_pycaw
            from winboost.utils.audio_native import _import_pycaw

            with pytest.raises(AudioNativeError, match="pip install winboost\\[audio\\]"):
                _import_pycaw()
        finally:
            # Restore propre — eviter les fuites entre tests
            for k, v in original_modules.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_set_volume_when_pycaw_absent(self):
        with patch(
            "winboost.utils.audio_native._get_endpoint_volume",
            side_effect=AudioNativeError(
                "pycaw n'est pas installe. Installe-le via : pip install winboost[audio]"
            ),
        ), pytest.raises(AudioNativeError, match="winboost\\[audio\\]"):
            set_volume(50)


# =============================================================================
# COM error toleree — wrappee proprement
# =============================================================================


class TestCOMErrorTolerance:
    def test_get_endpoint_wraps_com_error(self):
        # Simule un service audio Windows arrete : Activate() leve OSError
        from winboost.utils import audio_native

        fake_speakers = MagicMock()
        fake_speakers.Activate.side_effect = OSError(-2147023174, "RPC server unavailable")

        fake_au = MagicMock()
        fake_au.GetSpeakers.return_value = fake_speakers

        with patch(
            "winboost.utils.audio_native._import_pycaw",
            return_value=(fake_au, MagicMock(), MagicMock()),
        ):
            with pytest.raises(AudioNativeError, match="audio"):
                audio_native._get_endpoint_volume()
