"""Tests pour winboost.gui.pilot_page (Phase 13 v2.3 — T081).

Approche : on mocke entierement CustomTkinter pour eviter d'avoir besoin
d'un display reel. Les widgets Tk sont remplaces par des MagicMock — on teste
le contrat (gating Lab Mode, threading TkConfirmer, callbacks, error handling)
sans affichage.

Couverture exigee (>= 6 tests, 12 livres) :
- T1 : module s'importe + expose les classes publiques
- T2 : page placeholder si profile != 'lab'
- T3 : page complete si profile == 'lab' + RGPD OK
- T4 : bouton 'Lancer' lance AnthropicPilot.run() dans un thread
- T5 : Esc -> appelle pilot.stop() + cancel_all() sur le confirmer
- T6 : TkConfirmer expose l'interface ConfirmCallback (callable)
- + tests : queue decision, timeout, gating reasons
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from winboost.core.config import Config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lab_config(tmp_path: Path) -> Config:
    """Construit une Config en mode 'lab' avec opt-in RGPD complet."""
    config = Config(config_dir=tmp_path)
    config.set("profile", "lab")
    config.set(
        "pilot",
        {
            "rgpd": {
                "screenshots": True,
                "ocr_text": True,
                "system_info": True,
                "accepted_at": "2026-05-06T00:00:00Z",
            },
            "api_key": "sk-ant-test",
            "budget_eur": 5.0,
            "sandbox_mode": "winboost_window",
        },
    )
    config.save()
    return config


def _build_page_skeleton(config: Config | None = None):
    """Construit une PilotPage sans GUI reelle (full UI branch)."""
    from winboost.gui import pilot_page

    page = pilot_page.PilotPage.__new__(pilot_page.PilotPage)
    page._config = config
    page._pilot_factory = MagicMock()
    page._on_open_settings = None
    page._pilot_thread = None
    page._is_running = False
    page._pilot_instance = None
    page._tk_confirmer = None
    page._iteration_counter = 0
    page._budget_label = MagicMock()
    page._activity_frame = MagicMock()
    page._activity_frame.winfo_children.return_value = []
    page._activity_placeholder = MagicMock()
    page.run_btn = MagicMock()
    page.input_textbox = MagicMock()
    page.input_textbox.get.return_value = "test prompt"
    page._error_label = MagicMock()

    # after() doit immediatement executer la callback
    page.after = lambda _delay, fn, *args: fn(*args)

    # bind_all stub
    page.bind_all = MagicMock()
    return page, pilot_page


# ---------------------------------------------------------------------------
# Tests d'import et structure
# ---------------------------------------------------------------------------


class TestPilotPageImport:
    """T1 : le module s'importe et expose les classes publiques."""

    def test_module_imports_without_crash(self):
        from winboost.gui import pilot_page

        assert hasattr(pilot_page, "PilotPage")
        assert hasattr(pilot_page, "TkConfirmer")
        assert hasattr(pilot_page, "make_tk_confirmer")
        assert hasattr(pilot_page, "PILOT_RGPD_KEYS")

    def test_pilot_rgpd_keys_match_backend(self):
        """PILOT_RGPD_KEYS doit etre identique a celles du backend."""
        from winboost.gui.pilot_page import PILOT_RGPD_KEYS as GUI_KEYS
        from winboost.pilot.anthropic_pilot import RGPD_OPT_IN_KEYS as BACKEND_KEYS

        assert GUI_KEYS == BACKEND_KEYS

    def test_app_imports_pilot_page(self):
        """Test : app.py reference PilotPage et l'onglet Pilot."""
        app_path = Path(__file__).parent.parent.parent / "winboost" / "gui" / "app.py"
        content = app_path.read_text(encoding="utf-8")

        assert "from winboost.gui.pilot_page import PilotPage" in content
        assert '"Pilot"' in content
        assert '"pilot"' in content


# ---------------------------------------------------------------------------
# Tests Gating : Lab Mode + RGPD
# ---------------------------------------------------------------------------


class TestPilotPageGating:
    """T2 + T3 : la page se construit en placeholder ou full UI selon Config."""

    def test_can_show_full_ui_returns_false_when_no_config(self):
        """Sans config -> placeholder."""
        page, _mod = _build_page_skeleton(config=None)
        assert page._can_show_full_ui() is False

    def test_can_show_full_ui_returns_false_when_profile_not_lab(self, tmp_path: Path):
        """profile != 'lab' -> placeholder."""
        config = Config(config_dir=tmp_path)
        config.set("profile", "safe")
        page, _mod = _build_page_skeleton(config=config)
        assert page._can_show_full_ui() is False

    def test_can_show_full_ui_returns_false_when_rgpd_incomplete(self, tmp_path: Path):
        """profile='lab' mais RGPD incomplet -> placeholder."""
        config = Config(config_dir=tmp_path)
        config.set("profile", "lab")
        config.set("pilot", {"rgpd": {"screenshots": True, "ocr_text": False}})
        page, _mod = _build_page_skeleton(config=config)
        assert page._can_show_full_ui() is False

    def test_can_show_full_ui_returns_true_when_lab_and_rgpd_ok(self, tmp_path: Path):
        """profile='lab' + RGPD complet -> full UI."""
        config = _make_lab_config(tmp_path)
        page, _mod = _build_page_skeleton(config=config)
        assert page._can_show_full_ui() is True

    def test_gating_reason_explains_why_lab_required(self, tmp_path: Path):
        """Le message de gating mentionne 'lab'."""
        config = Config(config_dir=tmp_path)
        config.set("profile", "safe")
        page, _mod = _build_page_skeleton(config=config)

        reason = page._gating_reason()
        assert "lab" in reason.lower()

    def test_gating_reason_lists_missing_rgpd_keys(self, tmp_path: Path):
        """Le message de gating mentionne les keys RGPD manquantes."""
        config = Config(config_dir=tmp_path)
        config.set("profile", "lab")
        config.set("pilot", {"rgpd": {"screenshots": True, "ocr_text": False}})
        page, _mod = _build_page_skeleton(config=config)

        reason = page._gating_reason()
        # ocr_text et system_info sont manquants
        assert "ocr_text" in reason or "system_info" in reason


# ---------------------------------------------------------------------------
# Tests TkConfirmer
# ---------------------------------------------------------------------------


class TestTkConfirmer:
    """T6 : TkConfirmer respecte le contrat ConfirmCallback."""

    def test_tk_confirmer_is_callable(self):
        """TkConfirmer instances are callable (interface ConfirmCallback)."""
        from winboost.gui.pilot_page import TkConfirmer

        confirmer = TkConfirmer(
            ui_callback=lambda action, shot, on_dec: on_dec("confirm"),
            scheduler=lambda delay, fn, *args: fn(*args),
        )
        assert callable(confirmer)

    def test_tk_confirmer_returns_decision_via_queue(self):
        """L'ui_callback resoud la decision, le confirmer retourne 'confirm'."""
        from winboost.gui.pilot_page import make_tk_confirmer

        # ui_callback simule la decision utilisateur immediatement
        def ui(action, shot, on_decision):
            on_decision("confirm")

        # Scheduler synchrone (tk.after sans event loop)
        def scheduler(delay, fn, *args):
            fn(*args)

        confirmer = make_tk_confirmer(ui_callback=ui, scheduler=scheduler)

        action = MagicMock()
        action.short_label.return_value = "click(100, 100)"
        decision = confirmer(action, b"\x89PNG fake")

        assert decision == "confirm"

    def test_tk_confirmer_invalid_decision_falls_back_to_cancel(self):
        """Decision non-reconnue -> 'cancel' par defense."""
        from winboost.gui.pilot_page import make_tk_confirmer

        def ui(action, shot, on_decision):
            on_decision("yolo")  # decision invalide

        def scheduler(delay, fn, *args):
            fn(*args)

        confirmer = make_tk_confirmer(ui_callback=ui, scheduler=scheduler)
        decision = confirmer(MagicMock(), b"")

        assert decision == "cancel"

    def test_tk_confirmer_cancel_all_returns_immediately(self):
        """Apres cancel_all(), tous les futurs appels retournent 'cancel'."""
        from winboost.gui.pilot_page import TkConfirmer

        # ui_callback ne sera jamais appele car cancel_all() est appele avant
        ui = MagicMock()
        scheduler = MagicMock()

        confirmer = TkConfirmer(ui_callback=ui, scheduler=scheduler)
        confirmer.cancel_all()

        decision = confirmer(MagicMock(), b"")

        assert decision == "cancel"
        # ui n'a pas ete invoque
        ui.assert_not_called()

    def test_tk_confirmer_screenshot_path_is_read(self):
        """Si screenshot est un Path, il est lu via read_bytes."""
        from winboost.gui.pilot_page import TkConfirmer

        captured: dict = {}

        def ui(action, shot, on_decision):
            captured["shot"] = shot
            on_decision("skip")

        def scheduler(delay, fn, *args):
            fn(*args)

        confirmer = TkConfirmer(ui_callback=ui, scheduler=scheduler)

        # Path inexistant -> doit retourner b'' sans crasher
        confirmer(MagicMock(), Path("/nonexistent/path.png"))

        assert captured["shot"] == b""

    def test_tk_confirmer_threaded_decision(self):
        """Le confirmer marche dans un contexte threaded reel.

        Simule le flow : pilot thread appelle confirmer.__call__ ;
        scheduler simule `tk.after(0, fn)` en lancant un thread qui appelle
        on_decision apres un court delai.
        """
        from winboost.gui.pilot_page import TkConfirmer

        def ui_callback(action, shot, on_decision):
            on_decision("confirm")

        def scheduler(delay, fn, *args):
            # Simule tk.after -> execute dans un thread Tk-like
            t = threading.Thread(target=lambda: fn(*args), daemon=True)
            t.start()

        confirmer = TkConfirmer(ui_callback=ui_callback, scheduler=scheduler)

        decision = confirmer(MagicMock(), b"png-bytes")
        assert decision == "confirm"

    def test_tk_confirmer_timeout(self):
        """Si l'user ne decide jamais, le confirmer timeout et retourne cancel."""
        from winboost.gui.pilot_page import TkConfirmer

        # ui_callback ne resout JAMAIS la decision
        def ui_callback(action, shot, on_decision):
            pass

        def scheduler(delay, fn, *args):
            # Execute mais on_decision n'est pas appele
            fn(*args)

        confirmer = TkConfirmer(
            ui_callback=ui_callback,
            scheduler=scheduler,
            timeout_seconds=0.05,  # timeout court pour le test
        )

        start = time.monotonic()
        decision = confirmer(MagicMock(), b"")
        elapsed = time.monotonic() - start

        assert decision == "cancel"
        assert elapsed >= 0.04  # timeout respecte


# ---------------------------------------------------------------------------
# Tests : Run pilot dans un thread
# ---------------------------------------------------------------------------


class TestPilotRunFlow:
    """T4 : 'Lancer le Pilot' lance AnthropicPilot.run() dans un thread."""

    def test_on_run_click_with_empty_prompt_shows_error(self, tmp_path: Path):
        """Prompt vide -> erreur, pas de thread lance."""
        config = _make_lab_config(tmp_path)
        page, _mod = _build_page_skeleton(config=config)
        page.input_textbox.get.return_value = "   "

        with patch.object(page, "_launch_pilot") as mock_launch:
            page._on_run_click()

        mock_launch.assert_not_called()
        page._error_label.configure.assert_called()

    def test_on_run_click_with_valid_prompt_launches(self, tmp_path: Path):
        """Prompt non vide -> _launch_pilot appele."""
        config = _make_lab_config(tmp_path)
        page, _mod = _build_page_skeleton(config=config)
        page.input_textbox.get.return_value = "trouve mon imprimante"

        with patch.object(page, "_launch_pilot") as mock_launch:
            page._on_run_click()

        mock_launch.assert_called_once_with("trouve mon imprimante")

    def test_on_run_click_ignored_when_already_running(self, tmp_path: Path):
        """Click pendant un run en cours -> ignore."""
        config = _make_lab_config(tmp_path)
        page, _mod = _build_page_skeleton(config=config)
        page._is_running = True

        with patch.object(page, "_launch_pilot") as mock_launch:
            page._on_run_click()

        mock_launch.assert_not_called()

    def test_launch_pilot_starts_thread_and_disables_button(self, tmp_path: Path):
        """_launch_pilot demarre un thread daemon + disable bouton."""
        config = _make_lab_config(tmp_path)
        page, mod = _build_page_skeleton(config=config)

        # Mock le pilot factory pour qu'il retourne un pilot mocke
        mock_pilot = MagicMock()
        mock_pilot.run.return_value = MagicMock(
            completed=True,
            actions=[],
            total_cost_eur=0.001,
            abort_reason="end_turn",
        )
        page._pilot_factory = MagicMock(return_value=mock_pilot)

        with patch("winboost.gui.pilot_page.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            page._launch_pilot("test prompt")

        # Bouton disabled
        page.run_btn.configure.assert_any_call(
            state="disabled", text="Pilot en cours..."
        )
        # Thread demarre
        mock_thread.start.assert_called_once()
        # Daemon thread
        kwargs = mock_thread_cls.call_args.kwargs
        assert kwargs.get("daemon") is True
        assert page._is_running is True

    def test_pilot_worker_calls_pilot_run_with_prompt(self, tmp_path: Path):
        """_pilot_worker invoque pilot.run(prompt)."""
        config = _make_lab_config(tmp_path)
        page, _mod = _build_page_skeleton(config=config)

        mock_pilot = MagicMock()
        mock_result = MagicMock()
        mock_result.completed = True
        mock_result.actions = []
        mock_result.total_cost_eur = 0.0
        mock_result.abort_reason = ""
        mock_pilot.run.return_value = mock_result
        page._pilot_factory = MagicMock(return_value=mock_pilot)

        with patch.object(page, "_on_pilot_completed") as mock_done:
            page._pilot_worker("trouve mon imprimante")

        mock_pilot.run.assert_called_once_with("trouve mon imprimante")
        mock_done.assert_called_once_with(mock_result)


# ---------------------------------------------------------------------------
# Tests : Esc -> stop pilot
# ---------------------------------------------------------------------------


class TestPilotEscape:
    """T5 : Esc -> pilot.stop() + tk_confirmer.cancel_all()."""

    def test_escape_when_not_running_is_noop(self, tmp_path: Path):
        """Esc sans run en cours -> pas d'effet."""
        config = _make_lab_config(tmp_path)
        page, _mod = _build_page_skeleton(config=config)
        page._is_running = False
        mock_pilot = MagicMock()
        page._pilot_instance = mock_pilot

        page._on_escape_key()

        mock_pilot.stop.assert_not_called()

    def test_escape_calls_pilot_stop(self, tmp_path: Path):
        """Esc pendant run -> pilot.stop() appele."""
        config = _make_lab_config(tmp_path)
        page, _mod = _build_page_skeleton(config=config)
        page._is_running = True
        mock_pilot = MagicMock()
        page._pilot_instance = mock_pilot
        mock_confirmer = MagicMock()
        page._tk_confirmer = mock_confirmer

        page._on_escape_key()

        mock_pilot.stop.assert_called_once()
        mock_confirmer.cancel_all.assert_called_once()


# ---------------------------------------------------------------------------
# Tests : Pilot completion / error handlers
# ---------------------------------------------------------------------------


class TestPilotResultHandlers:
    """Verifie l'affichage du resultat (succes / erreur)."""

    def test_on_pilot_completed_re_enables_button(self, tmp_path: Path):
        """A la fin du run, le bouton est re-active."""
        config = _make_lab_config(tmp_path)
        page, _mod = _build_page_skeleton(config=config)
        page._is_running = True

        result = MagicMock()
        result.completed = True
        result.actions = []
        result.total_cost_eur = 0.05
        result.abort_reason = ""

        with patch("winboost.gui.pilot_page.ctk.CTkLabel"):
            page._on_pilot_completed(result)

        assert page._is_running is False
        page.run_btn.configure.assert_any_call(state="normal", text="Lancer le Pilot")

    def test_on_pilot_error_displays_message(self, tmp_path: Path):
        """Erreur pilot -> message affiche en rouge, bouton re-active."""
        config = _make_lab_config(tmp_path)
        page, _mod = _build_page_skeleton(config=config)
        page._is_running = True

        with patch("winboost.gui.pilot_page.ctk.CTkLabel") as mock_label:
            page._on_pilot_error("BYOK manquant", "API key vide")

        assert page._is_running is False
        page.run_btn.configure.assert_any_call(state="normal", text="Lancer le Pilot")
        # Un label avec le message a ete cree
        mock_label.assert_called()


# ---------------------------------------------------------------------------
# Tests : IterationCard
# ---------------------------------------------------------------------------


class TestIterationCard:
    """Tests visuels d'une carte d'iteration."""

    def test_iteration_card_decision_callback_invoked(self):
        """Click bouton -> on_decision appele avec la decision."""
        from winboost.gui.pilot_page import IterationCard

        on_decision = MagicMock()

        with patch.object(IterationCard, "__init__", lambda self, *a, **kw: None):
            card = IterationCard(MagicMock(), 1, MagicMock(), b"", on_decision)
            card._iteration_num = 1
            card._action = MagicMock()
            card._screenshot_bytes = b""
            card._on_decision = on_decision
            card._decided = False
            card._screenshot_label = None
            card._buttons_frame = MagicMock()
            card._confirm_btn = MagicMock()
            card._skip_btn = MagicMock()
            card._cancel_btn = MagicMock()
            card._batch_btn = MagicMock()

            # Patch le pack du label resultat pour eviter widget reel
            with patch("winboost.gui.pilot_page.ctk.CTkLabel") as mock_label_cls:
                mock_label_cls.return_value = MagicMock()
                card._handle_decision("confirm")

        on_decision.assert_called_once_with("confirm")
        card._confirm_btn.configure.assert_called_with(state="disabled")

    def test_iteration_card_double_click_ignored(self):
        """Click apres decision -> ignore (pas de double-fire)."""
        from winboost.gui.pilot_page import IterationCard

        on_decision = MagicMock()

        with patch.object(IterationCard, "__init__", lambda self, *a, **kw: None):
            card = IterationCard(MagicMock(), 1, MagicMock(), b"", on_decision)
            card._decided = True  # deja decide
            card._on_decision = on_decision
            card._confirm_btn = MagicMock()
            card._skip_btn = MagicMock()
            card._cancel_btn = MagicMock()
            card._batch_btn = MagicMock()

            card._handle_decision("skip")

        on_decision.assert_not_called()


# ---------------------------------------------------------------------------
# Tests : default factory + integration soft
# ---------------------------------------------------------------------------


class TestDefaultPilotFactory:
    """Tests le branchement Config -> AnthropicPilot."""

    def test_default_factory_raises_without_api_key(self, tmp_path: Path):
        """Sans cle API dans Config -> BYOKMissingError au build du pilot."""
        from winboost.gui.pilot_page import _default_pilot_factory
        from winboost.pilot.anthropic_pilot import BYOKMissingError

        config = Config(config_dir=tmp_path)
        config.set("profile", "lab")
        config.set("pilot", {"budget_eur": 5.0, "sandbox_mode": "winboost_window"})

        # Pas de cle -> BYOKMissingError au constructeur AnthropicPilot
        with pytest.raises(BYOKMissingError):
            _default_pilot_factory(config, MagicMock())

    def test_default_factory_builds_pilot_with_api_key(self, tmp_path: Path):
        """Avec cle API -> construit un AnthropicPilot."""
        from winboost.gui.pilot_page import _default_pilot_factory

        config = _make_lab_config(tmp_path)
        confirmer = MagicMock()

        pilot = _default_pilot_factory(config, confirmer)

        # On a bien un AnthropicPilot
        assert pilot is not None
        assert hasattr(pilot, "run")
        assert hasattr(pilot, "stop")
