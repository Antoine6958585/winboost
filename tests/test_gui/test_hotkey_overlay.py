"""Tests unitaires pour winboost.gui.hotkey_overlay (T065).

Tous les tests sont mockes : le hotkey global ne peut pas etre teste reellement
en CI (pas d'evenement clavier) ni la creation de fenetre Tk en headless. On
verifie le contrat de la classe `HotkeyOverlay` :
- Construction sans crash avec un router mock
- start_listener / stop_listener appellent les bonnes APIs `keyboard`
- show / hide gerent proprement la fenetre Tk
- Soumission appelle `router.route(query)` avec le bon argument
- Affichage des actions / des erreurs
- Esc et focus loss ferment l'overlay
- Idempotence de show()
- Fallback si `keyboard.add_hotkey` leve OSError

Validation finale (manuelle, hors pytest) : `winboost overlay` puis Win+Espace.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers : factories minimales pour les objets metier
# ---------------------------------------------------------------------------


@dataclass
class _MockAction:
    """Stub minimal d'Action pour les tests overlay."""

    id: str = "test_001"
    name: str = "Test Action"
    description: str = "Description test"
    category: str = "system"
    risk_level: str = "low"
    requires_admin: bool = False
    reversible: bool = True


@dataclass
class _MockVerdict:
    allowed: bool = True
    requires_dry_run: bool = False
    requires_confirmation: bool = False
    reason: str = ""


@dataclass
class _MockRouted:
    action: _MockAction
    verdict: _MockVerdict
    score: float = 0.85
    source: str = "cache"


@dataclass
class _MockRouteResult:
    """Stub minimal de RouteResult."""

    actions: list
    blocked: list
    message: str = "1 action(s) proposee(s)"
    resolved_by: str = "cache"
    query: str = ""

    @property
    def has_actions(self) -> bool:
        return len(self.actions) > 0


def _make_router_with_actions(actions: list[_MockRouted] | None = None) -> MagicMock:
    """Cree un router mock qui retourne un RouteResult predefini."""
    router = MagicMock()
    if actions is None:
        actions = [
            _MockRouted(
                action=_MockAction(name="Activate Dark Mode", risk_level="low"),
                verdict=_MockVerdict(allowed=True),
            ),
        ]
    result = _MockRouteResult(actions=actions, blocked=[])
    router.route.return_value = result
    return router


def _make_router_no_actions() -> MagicMock:
    """Router mock qui retourne un resultat vide."""
    router = MagicMock()
    result = _MockRouteResult(
        actions=[], blocked=[], message="Aucune action trouvee", resolved_by="none",
    )
    router.route.return_value = result
    return router


# ---------------------------------------------------------------------------
# Tests : construction & API publique
# ---------------------------------------------------------------------------


class TestHotkeyOverlayConstruction:
    """L'instanciation ne doit jamais lever : pas de side effect au constructeur."""

    def test_can_be_instantiated_with_mock_router(self):
        """Test 1 : construction avec un ActionRouter mock."""
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        router = _make_router_with_actions()
        overlay = HotkeyOverlay(router)

        assert overlay._router is router
        assert overlay._window is None
        assert overlay._listener_registered is False

    def test_constructor_does_not_register_hotkey(self):
        """Le constructeur ne doit pas appeler `keyboard.add_hotkey`."""
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        with patch("keyboard.add_hotkey") as mock_add:
            HotkeyOverlay(_make_router_with_actions())

        mock_add.assert_not_called()


# ---------------------------------------------------------------------------
# Tests : start_listener / stop_listener
# ---------------------------------------------------------------------------


class TestListenerLifecycle:
    """Cycle de vie du hotkey global via le package `keyboard`."""

    def test_start_listener_registers_win_space(self):
        """Test 8 : `keyboard.add_hotkey` est appele avec le bon combo."""
        from winboost.gui.hotkey_overlay import HOTKEY_COMBO, HotkeyOverlay

        with patch("keyboard.add_hotkey") as mock_add:
            mock_add.return_value = "handle_123"
            overlay = HotkeyOverlay(_make_router_with_actions())
            ok = overlay.start_listener()

        assert ok is True
        assert overlay._listener_registered is True
        # Verifie l'appel : combo en 1er arg, callback en 2eme
        args, _kwargs = mock_add.call_args
        assert args[0] == HOTKEY_COMBO
        assert callable(args[1])

    def test_start_listener_idempotent(self):
        """Appeler start_listener deux fois ne reenregistre pas le hotkey."""
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        with patch("keyboard.add_hotkey") as mock_add:
            mock_add.return_value = "handle"
            overlay = HotkeyOverlay(_make_router_with_actions())
            overlay.start_listener()
            overlay.start_listener()

        assert mock_add.call_count == 1

    def test_stop_listener_calls_remove_hotkey(self):
        """Test 9 : stop_listener appelle `keyboard.remove_hotkey`."""
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        with patch("keyboard.add_hotkey") as mock_add, \
             patch("keyboard.remove_hotkey") as mock_remove:
            mock_add.return_value = "handle_xyz"
            overlay = HotkeyOverlay(_make_router_with_actions())
            overlay.start_listener()
            overlay.stop_listener()

        mock_remove.assert_called_once_with("handle_xyz")
        assert overlay._listener_registered is False

    def test_stop_listener_noop_if_not_started(self):
        """stop_listener avant start_listener ne crash pas."""
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        with patch("keyboard.remove_hotkey") as mock_remove:
            overlay = HotkeyOverlay(_make_router_with_actions())
            overlay.stop_listener()  # ne doit rien faire

        mock_remove.assert_not_called()

    def test_start_listener_handles_oserror_gracefully(self):
        """Test 10 : si keyboard leve OSError (admin requis), fallback propre."""
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        with patch("keyboard.add_hotkey", side_effect=OSError("admin required")):
            overlay = HotkeyOverlay(_make_router_with_actions())
            ok = overlay.start_listener()

        assert ok is False
        assert overlay._listener_registered is False
        # Pas de crash : l'objet reste utilisable

    def test_start_listener_handles_import_error(self):
        """Si le package `keyboard` est absent, fallback propre."""
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        # Simule l'absence du module en patchant le builtin __import__
        original_import = __builtins__["__import__"] if isinstance(
            __builtins__, dict
        ) else __builtins__.__import__

        def mock_import(name, *args, **kwargs):
            if name == "keyboard":
                raise ImportError("No module named 'keyboard'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            overlay = HotkeyOverlay(_make_router_with_actions())
            ok = overlay.start_listener()

        assert ok is False
        assert overlay._listener_registered is False


# ---------------------------------------------------------------------------
# Tests : show / hide / build_window (Tk mocke)
# ---------------------------------------------------------------------------


class TestOverlayWindow:
    """Cycle de vie de la fenetre Tk (mockee)."""

    def test_show_creates_toplevel_with_alpha_and_topmost(self):
        """Test 2 : show() configure alpha < 1.0 et topmost true."""
        from winboost.gui import hotkey_overlay
        from winboost.gui.hotkey_overlay import OVERLAY_ALPHA, HotkeyOverlay

        with patch.object(hotkey_overlay.tk, "Tk") as mock_tk_cls, \
             patch.object(hotkey_overlay.tk, "Toplevel") as mock_top_cls, \
             patch.object(hotkey_overlay.tk, "Frame"), \
             patch.object(hotkey_overlay.tk, "Entry") as mock_entry_cls, \
             patch.object(hotkey_overlay.tk, "Label"):
            mock_root = MagicMock()
            mock_tk_cls.return_value = mock_root
            mock_window = MagicMock()
            mock_window.winfo_screenwidth.return_value = 1920
            mock_window.winfo_screenheight.return_value = 1080
            mock_top_cls.return_value = mock_window
            mock_entry_cls.return_value = MagicMock()

            overlay = HotkeyOverlay(_make_router_with_actions())
            overlay.show()

        # overrideredirect + alpha + topmost
        mock_window.overrideredirect.assert_called_once_with(True)
        # wm_attributes("-alpha", OVERLAY_ALPHA) et ("-topmost", True)
        wm_calls = mock_window.wm_attributes.call_args_list
        alpha_call = next(c for c in wm_calls if c.args[0] == "-alpha")
        topmost_call = next(c for c in wm_calls if c.args[0] == "-topmost")
        assert alpha_call.args[1] == OVERLAY_ALPHA
        assert alpha_call.args[1] < 1.0
        assert topmost_call.args[1] is True

    def test_show_centers_on_screen(self):
        """show() centre la fenetre via winfo_screenwidth/height (multi-DPI safe)."""
        from winboost.gui import hotkey_overlay
        from winboost.gui.hotkey_overlay import OVERLAY_HEIGHT, OVERLAY_WIDTH, HotkeyOverlay

        with patch.object(hotkey_overlay.tk, "Tk") as mock_tk_cls, \
             patch.object(hotkey_overlay.tk, "Toplevel") as mock_top_cls, \
             patch.object(hotkey_overlay.tk, "Frame"), \
             patch.object(hotkey_overlay.tk, "Entry") as mock_entry_cls, \
             patch.object(hotkey_overlay.tk, "Label"):
            mock_tk_cls.return_value = MagicMock()
            mock_window = MagicMock()
            mock_window.winfo_screenwidth.return_value = 2560
            mock_window.winfo_screenheight.return_value = 1440
            mock_top_cls.return_value = mock_window
            mock_entry_cls.return_value = MagicMock()

            overlay = HotkeyOverlay(_make_router_with_actions())
            overlay.show()

        # Geometry : centre attendu (2560-500)/2 = 1030, (1440-100)/2 = 670
        expected_x = (2560 - OVERLAY_WIDTH) // 2
        expected_y = (1440 - OVERLAY_HEIGHT) // 2
        # On accepte plusieurs appels a geometry (initial + grow apres soumission)
        first_geom = mock_window.geometry.call_args_list[0].args[0]
        assert first_geom == f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+{expected_x}+{expected_y}"

    def test_hide_destroys_window(self):
        """Test 3 : hide() detruit la fenetre proprement."""
        from winboost.gui import hotkey_overlay
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        with patch.object(hotkey_overlay.tk, "Tk") as mock_tk_cls, \
             patch.object(hotkey_overlay.tk, "Toplevel") as mock_top_cls, \
             patch.object(hotkey_overlay.tk, "Frame"), \
             patch.object(hotkey_overlay.tk, "Entry") as mock_entry_cls, \
             patch.object(hotkey_overlay.tk, "Label"):
            mock_tk_cls.return_value = MagicMock()
            mock_window = MagicMock()
            mock_window.winfo_screenwidth.return_value = 1920
            mock_window.winfo_screenheight.return_value = 1080
            mock_top_cls.return_value = mock_window
            mock_entry_cls.return_value = MagicMock()

            overlay = HotkeyOverlay(_make_router_with_actions())
            overlay.show()
            assert overlay._window is not None
            overlay.hide()

        mock_window.destroy.assert_called_once()
        assert overlay._window is None
        assert overlay._entry is None

    def test_hide_noop_if_not_shown(self):
        """hide() avant show() ne crash pas."""
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        overlay = HotkeyOverlay(_make_router_with_actions())
        overlay.hide()  # noop

        assert overlay._window is None

    def test_show_idempotent_does_not_create_two_windows(self):
        """Test 11 : show() deux fois ne cree qu'une fenetre (refocus)."""
        from winboost.gui import hotkey_overlay
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        with patch.object(hotkey_overlay.tk, "Tk") as mock_tk_cls, \
             patch.object(hotkey_overlay.tk, "Toplevel") as mock_top_cls, \
             patch.object(hotkey_overlay.tk, "Frame"), \
             patch.object(hotkey_overlay.tk, "Entry") as mock_entry_cls, \
             patch.object(hotkey_overlay.tk, "Label"):
            mock_tk_cls.return_value = MagicMock()
            mock_window = MagicMock()
            mock_window.winfo_screenwidth.return_value = 1920
            mock_window.winfo_screenheight.return_value = 1080
            mock_top_cls.return_value = mock_window
            mock_entry_cls.return_value = MagicMock()

            overlay = HotkeyOverlay(_make_router_with_actions())
            overlay.show()
            overlay.show()  # 2eme appel

        # Toplevel n'est instancie qu'une seule fois
        assert mock_top_cls.call_count == 1
        # Le 2eme show() refocus : deiconify + lift sont appeles
        mock_window.deiconify.assert_called()
        mock_window.lift.assert_called()


# ---------------------------------------------------------------------------
# Tests : soumission (router.route)
# ---------------------------------------------------------------------------


class TestSubmission:
    """Comportement de la soumission Enter -> router -> rendu."""

    def _setup_overlay_with_entry_value(
        self, entry_value: str, router: MagicMock,
    ):
        """Helper : cree un overlay avec une fenetre montee, entry mockee
        retournant `entry_value`."""
        from winboost.gui import hotkey_overlay
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        patches = [
            patch.object(hotkey_overlay.tk, "Tk"),
            patch.object(hotkey_overlay.tk, "Toplevel"),
            patch.object(hotkey_overlay.tk, "Frame"),
            patch.object(hotkey_overlay.tk, "Entry"),
            patch.object(hotkey_overlay.tk, "Label"),
        ]
        for p in patches:
            p.start()

        mock_root = MagicMock()
        hotkey_overlay.tk.Tk.return_value = mock_root
        mock_window = MagicMock()
        mock_window.winfo_screenwidth.return_value = 1920
        mock_window.winfo_screenheight.return_value = 1080
        hotkey_overlay.tk.Toplevel.return_value = mock_window
        mock_entry = MagicMock()
        mock_entry.get.return_value = entry_value
        hotkey_overlay.tk.Entry.return_value = mock_entry

        overlay = HotkeyOverlay(router)
        overlay.show()
        return overlay, patches

    def _stop_patches(self, patches):
        for p in patches:
            p.stop()

    def test_submit_calls_router_route_with_query(self):
        """Test 4 : Soumission appelle router.route(query) une fois."""
        router = _make_router_with_actions()
        overlay, patches = self._setup_overlay_with_entry_value(
            "active le mode sombre", router,
        )
        try:
            overlay._on_submit()
        finally:
            self._stop_patches(patches)

        router.route.assert_called_once_with("active le mode sombre")

    def test_submit_ignores_empty_query(self):
        """Submit avec query vide n'appelle pas router."""
        router = _make_router_with_actions()
        overlay, patches = self._setup_overlay_with_entry_value("", router)
        try:
            overlay._on_submit()
        finally:
            self._stop_patches(patches)

        router.route.assert_not_called()

    def test_submit_ignores_placeholder_text(self):
        """Submit avec le placeholder par defaut n'appelle pas router."""
        from winboost.gui.hotkey_overlay import PLACEHOLDER_TEXT

        router = _make_router_with_actions()
        overlay, patches = self._setup_overlay_with_entry_value(
            PLACEHOLDER_TEXT, router,
        )
        try:
            overlay._on_submit()
        finally:
            self._stop_patches(patches)

        router.route.assert_not_called()

    def test_no_actions_renders_error_message_no_crash(self):
        """Test 5 : Aucune action retournee -> message d'erreur, pas de crash."""
        router = _make_router_no_actions()
        overlay, patches = self._setup_overlay_with_entry_value(
            "requete bidon", router,
        )
        try:
            # Ne doit pas crasher
            overlay._on_submit()
        finally:
            self._stop_patches(patches)

        router.route.assert_called_once()

    def test_action_returned_renders_name_and_risk(self):
        """Test 6 : Action retournee -> Label cree avec nom + badge risque."""
        from winboost.gui import hotkey_overlay
        from winboost.gui.hotkey_overlay import RISK_COLORS, HotkeyOverlay

        router = _make_router_with_actions(
            [
                _MockRouted(
                    action=_MockAction(
                        name="Disable Telemetry", risk_level="medium",
                    ),
                    verdict=_MockVerdict(allowed=True),
                ),
            ],
        )

        with patch.object(hotkey_overlay.tk, "Tk") as mock_tk_cls, \
             patch.object(hotkey_overlay.tk, "Toplevel") as mock_top_cls, \
             patch.object(hotkey_overlay.tk, "Frame"), \
             patch.object(hotkey_overlay.tk, "Entry") as mock_entry_cls, \
             patch.object(hotkey_overlay.tk, "Label") as mock_label_cls:
            mock_tk_cls.return_value = MagicMock()
            mock_window = MagicMock()
            mock_window.winfo_screenwidth.return_value = 1920
            mock_window.winfo_screenheight.return_value = 1080
            mock_top_cls.return_value = mock_window
            mock_entry = MagicMock()
            mock_entry.get.return_value = "desactive la telemetrie"
            mock_entry_cls.return_value = mock_entry

            overlay = HotkeyOverlay(router)
            overlay.show()

            # Reset les appels Label avant submit pour ne compter que ceux
            # generes par le rendu post-route()
            mock_label_cls.reset_mock()
            overlay._on_submit()

            # Capture les call_args AVANT que le patch soit relache
            all_label_calls = list(mock_label_cls.call_args_list)

        all_kwargs = [c.kwargs for c in all_label_calls]

        # Au moins un Label avec le nom de l'action
        names_rendered = [k.get("text") for k in all_kwargs]
        assert any(
            "Disable Telemetry" in (text or "") for text in names_rendered
        ), f"Action name not rendered. Texts: {names_rendered}"

        # Au moins un Label avec le bg = risk_color medium (badge)
        bgs_rendered = [k.get("bg") for k in all_kwargs]
        assert RISK_COLORS["medium"] in bgs_rendered, (
            f"Risk badge color not found. bgs: {bgs_rendered}"
        )

    def test_router_exception_does_not_crash(self):
        """Si router.route leve une exception, l'overlay reste fonctionnel."""
        router = MagicMock()
        router.route.side_effect = RuntimeError("LLM provider down")
        overlay, patches = self._setup_overlay_with_entry_value(
            "test", router,
        )
        try:
            # Ne doit pas crasher
            overlay._on_submit()
        finally:
            self._stop_patches(patches)


# ---------------------------------------------------------------------------
# Tests : Esc & focus loss
# ---------------------------------------------------------------------------


class TestEscapeAndFocusLoss:
    """Esc et perte de focus ferment l'overlay sans appeler le router."""

    def test_escape_closes_overlay_without_routing(self):
        """Test 7 : Esc ferme l'overlay sans appeler router.route."""
        from winboost.gui import hotkey_overlay
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        with patch.object(hotkey_overlay.tk, "Tk") as mock_tk_cls, \
             patch.object(hotkey_overlay.tk, "Toplevel") as mock_top_cls, \
             patch.object(hotkey_overlay.tk, "Frame"), \
             patch.object(hotkey_overlay.tk, "Entry") as mock_entry_cls, \
             patch.object(hotkey_overlay.tk, "Label"):
            mock_tk_cls.return_value = MagicMock()
            mock_window = MagicMock()
            mock_window.winfo_screenwidth.return_value = 1920
            mock_window.winfo_screenheight.return_value = 1080
            mock_top_cls.return_value = mock_window
            mock_entry_cls.return_value = MagicMock()

            router = _make_router_with_actions()
            overlay = HotkeyOverlay(router)
            overlay.show()

            # Recupere le callback bind sur <Escape>
            bind_calls = mock_window.bind.call_args_list
            escape_callback = None
            for call in bind_calls:
                if call.args[0] == "<Escape>":
                    escape_callback = call.args[1]
                    break

            assert escape_callback is not None, "<Escape> binding manquant"
            escape_callback(None)  # simule appui Esc

        # Router non appele : Esc n'execute rien
        router.route.assert_not_called()
        # Fenetre detruite
        mock_window.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# Tests : callback hotkey -> show()
# ---------------------------------------------------------------------------


class TestHotkeyCallback:
    """Le callback declenche par `keyboard` doit declencher show() sur le main thread."""

    def test_on_hotkey_schedules_show_via_after(self):
        """Le callback hotkey schedule show() via root.after(0, ...) (thread-safe)."""
        from winboost.gui.hotkey_overlay import HotkeyOverlay

        overlay = HotkeyOverlay(_make_router_with_actions())
        # Simule un root deja initialise
        mock_root = MagicMock()
        overlay._root = mock_root

        overlay._on_hotkey()

        mock_root.after.assert_called_once()
        args, _kwargs = mock_root.after.call_args
        assert args[0] == 0
        # Le callable est bien `show`
        assert args[1] == overlay.show


# ---------------------------------------------------------------------------
# Sanity check : module importable
# ---------------------------------------------------------------------------


def test_module_importable():
    """Sanity : le module s'importe sans dependance optionnelle (`keyboard`
    n'est importe qu'a `start_listener`)."""
    import winboost.gui.hotkey_overlay as mod

    assert hasattr(mod, "HotkeyOverlay")
    assert hasattr(mod, "run_overlay_foreground")
    assert mod.HOTKEY_COMBO == "windows+space"
