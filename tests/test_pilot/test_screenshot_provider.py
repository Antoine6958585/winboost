"""Tests pour winboost/pilot/screenshot_provider.py.

Approche : patcher `PIL.ImageGrab` et `winboost.pilot.screenshot_provider.ImageGrab`
pour eviter toute capture reelle. Permet aux tests de tourner sur Linux/CI sans
display.

Couvre :
- ImportError clair si Pillow absent
- Capture mode 'screen_region' / 'winboost_window' -> bbox correct
- Refus mode 'full_screen' sans flag explicit
- Mode 'full_screen' + allow_full_screen=True -> bbox=None
- all_screens=True passe a ImageGrab
- Bytes PNG valides (header 0x89 PNG ...)
- Empty bytes -> PilotError
- Performance > 500ms -> log warning (pas un fail)
"""

from __future__ import annotations

import builtins
import logging
import sys
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from winboost.pilot.anthropic_pilot import PilotError
from winboost.pilot.sandbox import Region, Sandbox

# --- Helpers --------------------------------------------------------------


def _make_fake_image(png_bytes: bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100):
    """Construit un mock d'image PIL qui ecrit `png_bytes` sur un buffer."""
    img = MagicMock(name="FakePILImage")

    def _save(buffer: BytesIO, format: str) -> None:  # noqa: A002
        buffer.write(png_bytes)

    img.save.side_effect = _save
    return img


def _make_image_grab_mock(png_bytes: bytes | None = None):
    """Mock complet de PIL.ImageGrab compatible avec all_screens kwarg."""
    if png_bytes is None:
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    fake_image_grab = MagicMock(name="ImageGrab")
    fake_image = _make_fake_image(png_bytes)
    fake_image_grab.grab = MagicMock(return_value=fake_image)
    return fake_image_grab, fake_image


# --- Tests ---------------------------------------------------------------


class TestImportError:
    """ImportError clair quand Pillow n'est pas installe."""

    def test_import_error_message_mentions_pip_install(self):
        """make_screenshot_provider() leve ImportError clair sans Pillow."""
        # On simule l'absence de PIL via builtins.__import__.
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("No module named 'PIL'")
            return real_import(name, *args, **kwargs)

        # Force la re-execution du try/except dans make_screenshot_provider
        # en patchant __import__ globalement.
        with patch.object(builtins, "__import__", side_effect=fake_import):
            from winboost.pilot import screenshot_provider

            with pytest.raises(ImportError) as exc_info:
                screenshot_provider.make_screenshot_provider()

            msg = str(exc_info.value)
            assert "Pillow" in msg
            assert "pip install winboost[pilot]" in msg


class TestSandboxModes:
    """Capture selon le mode Sandbox."""

    def test_screen_region_mode_uses_region_bbox(self):
        """Mode 'screen_region' -> ImageGrab.grab(bbox=(x, y, x+w, y+h))."""
        sandbox = Sandbox(
            mode="screen_region",
            region=Region(x=100, y=200, width=400, height=300),
        )

        fake_grab, fake_image = _make_image_grab_mock()

        with patch.dict(sys.modules, {"PIL": MagicMock(ImageGrab=fake_grab)}):
            with patch(
                "winboost.pilot.screenshot_provider._capture_with_pillow"
            ) as cap:
                from winboost.pilot.screenshot_provider import (
                    make_screenshot_provider,
                )

                provider = make_screenshot_provider()
                # On rebascule vers la vraie impl pour tester le bbox.
                cap.side_effect = None

            # Re-import direct pour ne pas dependre du patch.
            from winboost.pilot import screenshot_provider as sp_mod

            with patch.object(sp_mod, "_capture_with_pillow", wraps=sp_mod._capture_with_pillow):
                # Re-patch PIL.ImageGrab de maniere a ce que l'import dans la
                # fonction recupere notre mock.
                fake_pil = MagicMock()
                fake_pil.ImageGrab = fake_grab
                sys.modules["PIL"] = fake_pil
                try:
                    result = sp_mod._capture_with_pillow(sandbox)
                finally:
                    if "PIL" in sys.modules:
                        del sys.modules["PIL"]

        assert result.startswith(b"\x89PNG\r\n\x1a\n")
        # Verifie que ImageGrab.grab a ete appele avec le bon bbox.
        fake_grab.grab.assert_called_once()
        call_kwargs = fake_grab.grab.call_args.kwargs
        assert call_kwargs.get("bbox") == (100, 200, 500, 500)

    def test_winboost_window_mode_uses_region_bbox(self):
        """Mode 'winboost_window' (default) -> bbox derive de region."""
        sandbox = Sandbox(
            mode="winboost_window",
            region=Region(x=0, y=0, width=800, height=600),
        )

        fake_grab, _ = _make_image_grab_mock()
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            from winboost.pilot import screenshot_provider as sp_mod
            result = sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        assert result.startswith(b"\x89PNG")
        fake_grab.grab.assert_called_once()
        bbox = fake_grab.grab.call_args.kwargs.get("bbox")
        assert bbox == (0, 0, 800, 600)

    def test_full_screen_without_allow_flag_raises_at_construction(self):
        """Sandbox(mode='full_screen', allow_full_screen=False) -> refus a la
        construction (double-barriere)."""
        from winboost.pilot.sandbox import SandboxViolationError

        with pytest.raises(SandboxViolationError) as exc_info:
            Sandbox(mode="full_screen", allow_full_screen=False)
        assert "full_screen" in str(exc_info.value).lower()

    def test_full_screen_with_allow_flag_uses_none_bbox(self):
        """Sandbox full_screen + allow_full_screen=True -> bbox=None."""
        sandbox = Sandbox(
            mode="full_screen",
            region=Region(0, 0, 1, 1),
            allow_full_screen=True,
        )

        fake_grab, _ = _make_image_grab_mock()
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            from winboost.pilot import screenshot_provider as sp_mod
            result = sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        assert result.startswith(b"\x89PNG")
        fake_grab.grab.assert_called_once()
        bbox = fake_grab.grab.call_args.kwargs.get("bbox")
        assert bbox is None  # full_screen -> grab tout

    def test_full_screen_revalidate_in_provider_if_flag_tampered(self):
        """Si un caller bricole sandbox.allow_full_screen apres construction,
        le provider revalide et leve PilotError."""
        sandbox = Sandbox(
            mode="full_screen",
            region=Region(0, 0, 1, 1),
            allow_full_screen=True,
        )
        # Simule un tamper post-construction.
        sandbox.allow_full_screen = False

        from winboost.pilot import screenshot_provider as sp_mod

        with pytest.raises(PilotError) as exc_info:
            sp_mod._capture_with_pillow(sandbox)
        assert "full_screen" in str(exc_info.value).lower()


class TestImageGrabKwargs:
    """Verifie que ImageGrab est appele avec les bonnes options."""

    def test_all_screens_true_passed_to_image_grab(self):
        """all_screens=True doit etre passe pour gerer multi-ecrans."""
        sandbox = Sandbox(
            mode="screen_region",
            region=Region(x=0, y=0, width=100, height=100),
        )
        fake_grab, _ = _make_image_grab_mock()
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            from winboost.pilot import screenshot_provider as sp_mod
            sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        kwargs = fake_grab.grab.call_args.kwargs
        assert kwargs.get("all_screens") is True

    def test_all_screens_fallback_for_old_pillow(self):
        """Pillow < 9.2 ne supporte pas all_screens kwarg -> fallback retry."""
        sandbox = Sandbox(
            mode="screen_region",
            region=Region(x=0, y=0, width=100, height=100),
        )
        fake_grab = MagicMock()
        fake_image = _make_fake_image()

        # 1er appel : TypeError (signature ancienne sans all_screens).
        # 2eme appel : succes sans all_screens.
        fake_grab.grab.side_effect = [
            TypeError("grab() got unexpected keyword 'all_screens'"),
            fake_image,
        ]
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            from winboost.pilot import screenshot_provider as sp_mod
            result = sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        assert result.startswith(b"\x89PNG")
        assert fake_grab.grab.call_count == 2
        # Le 2eme appel ne doit pas avoir all_screens.
        second_kwargs = fake_grab.grab.call_args_list[1].kwargs
        assert "all_screens" not in second_kwargs


class TestPNGValidation:
    """Validation des bytes produits."""

    def test_returns_valid_png_header(self):
        """Bytes retournes commencent par 0x89 0x50 0x4E 0x47 (PNG magic)."""
        sandbox = Sandbox(
            mode="screen_region", region=Region(0, 0, 100, 100)
        )
        png = b"\x89PNG\r\n\x1a\n" + b"valid_png_payload"
        fake_grab, _ = _make_image_grab_mock(png_bytes=png)
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            from winboost.pilot import screenshot_provider as sp_mod
            result = sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        assert result[:8] == b"\x89PNG\r\n\x1a\n"
        assert result[:4] == bytes([0x89, 0x50, 0x4E, 0x47])

    def test_empty_bytes_raises_pilot_error(self):
        """Buffer vide -> PilotError explicite."""
        sandbox = Sandbox(
            mode="screen_region", region=Region(0, 0, 100, 100)
        )
        fake_grab, _ = _make_image_grab_mock(png_bytes=b"")
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            from winboost.pilot import screenshot_provider as sp_mod
            with pytest.raises(PilotError) as exc_info:
                sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        assert "0 bytes" in str(exc_info.value) or "vide" in str(exc_info.value).lower()

    def test_non_png_header_raises_pilot_error(self):
        """Header invalide (pas PNG) -> PilotError."""
        sandbox = Sandbox(
            mode="screen_region", region=Region(0, 0, 100, 100)
        )
        fake_grab, _ = _make_image_grab_mock(png_bytes=b"GIF89a" + b"\x00" * 50)
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            from winboost.pilot import screenshot_provider as sp_mod
            with pytest.raises(PilotError) as exc_info:
                sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        assert "PNG" in str(exc_info.value)

    def test_capture_failure_relabel_as_pilot_error(self):
        """Si ImageGrab leve, on relabel en PilotError sans masquer."""
        sandbox = Sandbox(
            mode="screen_region", region=Region(0, 0, 100, 100)
        )
        fake_grab = MagicMock()
        fake_grab.grab.side_effect = OSError("display not connected")
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            from winboost.pilot import screenshot_provider as sp_mod
            with pytest.raises(PilotError) as exc_info:
                sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        assert "display not connected" in str(exc_info.value)
        assert "OSError" in str(exc_info.value)


class TestPerformance:
    """Performance : > 500ms doit logger un warning, pas fail."""

    def test_slow_capture_logs_warning(self, caplog):
        """Capture > SLOW_CAPTURE_WARN_MS -> warning log, mais succes."""
        from winboost.pilot import screenshot_provider as sp_mod

        sandbox = Sandbox(
            mode="screen_region", region=Region(0, 0, 100, 100)
        )

        # Monkeypatch time.perf_counter pour simuler une capture lente.
        original_perf = sp_mod.time.perf_counter
        timestamps = iter([0.0, 0.6])  # 600ms ecart -> > 500ms

        def fake_perf():
            try:
                return next(timestamps)
            except StopIteration:
                return original_perf()

        fake_grab, _ = _make_image_grab_mock()
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            with patch.object(sp_mod.time, "perf_counter", side_effect=fake_perf):
                with caplog.at_level(logging.WARNING, logger=sp_mod.logger.name):
                    result = sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        assert result.startswith(b"\x89PNG")
        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_logs) >= 1
        assert any("lente" in r.message.lower() for r in warning_logs)

    def test_fast_capture_no_warning(self, caplog):
        """Capture rapide -> aucun warning."""
        from winboost.pilot import screenshot_provider as sp_mod

        sandbox = Sandbox(
            mode="screen_region", region=Region(0, 0, 100, 100)
        )
        fake_grab, _ = _make_image_grab_mock()
        fake_pil = MagicMock()
        fake_pil.ImageGrab = fake_grab
        sys.modules["PIL"] = fake_pil

        try:
            with caplog.at_level(logging.WARNING, logger=sp_mod.logger.name):
                sp_mod._capture_with_pillow(sandbox)
        finally:
            del sys.modules["PIL"]

        # Aucun warning de lenteur attendu sur capture mock instantanee.
        slow_warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "lente" in r.message.lower()
        ]
        assert slow_warnings == []


class TestFactoryReturnsCallable:
    """make_screenshot_provider() retourne un callable conforme."""

    def test_factory_returns_callable_when_pil_available(self):
        """Si Pillow est dispo (mocke), le factory retourne un callable."""
        fake_pil = MagicMock()
        fake_pil.ImageGrab = MagicMock()
        sys.modules["PIL"] = fake_pil

        try:
            from winboost.pilot.screenshot_provider import (
                make_screenshot_provider,
            )

            provider = make_screenshot_provider()
            assert callable(provider)
        finally:
            del sys.modules["PIL"]
