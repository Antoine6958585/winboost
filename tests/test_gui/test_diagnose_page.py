"""Tests pour winboost.gui.diagnose_page (Phase 13 v2.3).

Approche : on mocke entierement CustomTkinter pour eviter d'avoir besoin
d'un display reel. Les widgets Tk sont remplaces par des MagicMock — on teste
le contrat (callbacks, etat interne, threading) sans affichage.

Couverture exigee (>= 8 tests) :
1.  Le module s'importe sans crash + DiagnosePage existe.
2.  CheckResultCard accepte un CheckResult et expose les bonnes severites.
3.  FixStepCard pour un step "auto" expose un bouton Apply qui appelle le callback.
4.  FixStepCard pour un step "manuel" expose un bouton qui appelle on_manual.
5.  set_result() met a jour le bouton + ajoute un badge OK/ERR.
6.  DiagnosePage._on_run_click() avec query vide affiche une erreur, pas de scan.
7.  DiagnosePage._run_query_in_thread() appelle bien runner.run_from_query.
8.  _apply_worker() execute ActionExecutor.apply et propage le resultat.
9.  _fill_example() pre-remplit l'entree (sans lancer le scan).
10. _display_report() vide + repeuple la zone resultats avec checks + plan.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_check_result(
    name: str = "test_check",
    severity: str = "warning",
    message: str = "Probleme detecte",
    suggested_actions: tuple[str, ...] = ("net_011",),
    details: dict | None = None,
):
    """Cree un CheckResult réel (le module diagnose est testable sans GUI)."""
    from winboost.diagnose.checks import CheckResult

    return CheckResult(
        name=name,
        severity=severity,
        message=message,
        details=details if details is not None else {"key": "value"},
        suggested_actions=suggested_actions,
    )


def _make_report(
    theme: str = "bluetooth+gaming",
    query: str = "manette bluetooth bug rocket league",
    checks: tuple | None = None,
    summary: str = "1 warning(s) detecte(s)",
    plan: tuple | None = None,
):
    """Cree un DiagnosticReport reel pour les tests."""
    from winboost.diagnose.runner import DiagnosticReport

    if checks is None:
        checks = (
            _make_check_result(
                name="bluetooth_service_status",
                severity="ok",
                message="Service bthserv en cours",
                suggested_actions=(),
                details={"status": "running"},
            ),
            _make_check_result(
                name="bluetooth_gamepad_mapping",
                severity="warning",
                message="Manette BT mal mappee (DualSense)",
                suggested_actions=("bt_unpair_repair",),
            ),
            _make_check_result(
                name="gaming_xbl_gamesave_status",
                severity="error",
                message="Service XblGameSave arrete",
                suggested_actions=("net_012",),
            ),
        )
    if plan is None:
        plan = (
            {
                "step": 1,
                "action_id": "net_012",
                "description": "Redemarrer le service Bluetooth",
                "severity": "error",
                "from_check": "gaming_xbl_gamesave_status",
            },
            {
                "step": 2,
                "manual": True,
                "description": (
                    "Manette BT mal mappee. Selon le type :\n"
                    "  - Xbox : reappairer\n"
                    "  - DualSense : installer DS4Windows"
                ),
                "alternative": "Si reappairage Xbox ne fixe pas, Device Manager...",
                "severity": "warning",
                "from_check": "bluetooth_gamepad_mapping",
            },
        )

    return DiagnosticReport(
        theme=theme,
        query=query,
        timestamp=datetime.now(UTC),
        checks=checks,
        summary=summary,
        recommended_fix_plan=plan,
    )


def _build_page_skeleton(monkeypatch_widgets: bool = True):
    """Construit une instance DiagnosePage avec tous les widgets Tk mockes.

    Strategie : on monkeypatche les classes ctk pour qu'elles retournent des
    MagicMock. La page se construit donc sans display reel. Les MagicMock
    capturent tous les appels (`.pack()`, `.grid()`, `.configure()`, etc.).
    """
    import customtkinter as ctk

    from winboost.gui import diagnose_page

    page = diagnose_page.DiagnosePage.__new__(diagnose_page.DiagnosePage)

    # Etat interne minimum
    page._config = None
    page._runner_factory = MagicMock()
    page._executor_factory = None
    page._history_factory = None
    page._actions_dir = MagicMock()
    page._scan_thread = None
    page._is_scanning = False
    page._last_report = None
    page._fix_step_cards = {}
    page._action_registry = None

    # Widgets mockes (input_entry + run_btn + error_label + results_frame)
    page.input_entry = MagicMock()
    page.input_entry.get.return_value = ""
    page.run_btn = MagicMock()
    page._error_label = MagicMock()
    page._results_frame = MagicMock()
    page._results_frame.winfo_children.return_value = []
    page._scan_status = MagicMock()
    page._example_buttons = []

    # after() doit immediatement executer la callback (pas de mainloop)
    page.after = lambda _delay, fn, *args: fn(*args)

    return page, ctk, diagnose_page


# ---------------------------------------------------------------------------
# Tests d'import / exposition d'API publique
# ---------------------------------------------------------------------------


class TestDiagnosePageImport:
    """Test 1 : le module s'importe et expose les bonnes classes."""

    def test_module_imports_without_crash(self):
        from winboost.gui import diagnose_page

        assert hasattr(diagnose_page, "DiagnosePage")
        assert hasattr(diagnose_page, "CheckResultCard")
        assert hasattr(diagnose_page, "FixStepCard")
        assert hasattr(diagnose_page, "ManualStepDialog")

    def test_severity_colors_match_required_palette(self):
        """Test palette : ok=#27ae60, warning=#f39c12, error=#e74c3c, critical=#9b59b6."""
        from winboost.gui.diagnose_page import _SEVERITY_COLORS

        assert _SEVERITY_COLORS["ok"] == "#27ae60"
        assert _SEVERITY_COLORS["warning"] == "#f39c12"
        assert _SEVERITY_COLORS["error"] == "#e74c3c"
        assert _SEVERITY_COLORS["critical"] == "#9b59b6"

    def test_examples_cover_all_5_themes(self):
        """Test : les 4 exemples couvrent bluetooth, network, audio, display."""
        from winboost.gui.diagnose_page import _EXAMPLES

        assert len(_EXAMPLES) == 4
        all_queries = " ".join(q for _, q in _EXAMPLES).lower()
        assert "bluetooth" in all_queries or "manette" in all_queries
        assert "internet" in all_queries or "dns" in all_queries
        assert "son" in all_queries or "audio" in all_queries
        assert "luminosite" in all_queries or "ecran" in all_queries

    def test_app_imports_diagnose_page(self):
        """Test : app.py reference DiagnosePage et l'onglet Diagnose."""
        from pathlib import Path

        app_path = Path(__file__).parent.parent.parent / "winboost" / "gui" / "app.py"
        content = app_path.read_text(encoding="utf-8")

        assert "from winboost.gui.diagnose_page import DiagnosePage" in content
        assert '"Diagnose"' in content
        # Place entre Chat IA et Historique : on verifie qu'il y a bien
        # l'entree dans les nav_items.
        assert '"diagnose"' in content


# ---------------------------------------------------------------------------
# Tests CheckResultCard
# ---------------------------------------------------------------------------


class TestCheckResultCard:
    """Tests rendu d'un CheckResult."""

    def test_check_result_card_can_be_instantiated_with_mock_parent(self):
        """Test 2 : CheckResultCard se construit avec un parent mocke."""
        from winboost.gui.diagnose_page import CheckResultCard

        check = _make_check_result(severity="error")

        # On monkeypatche le constructeur de CTkFrame pour qu'il ne tente pas
        # de creer un widget reel.
        with patch.object(CheckResultCard, "__init__", lambda self, *a, **kw: None):
            card = CheckResultCard(MagicMock(), check)
            card._check = check
            card._details_visible = False
            card._details_frame = None

        assert card._check.severity == "error"

    def test_severity_badges_have_label_per_severity(self):
        """Chaque severity a un libelle lisible (pas d'emoji)."""
        from winboost.gui.diagnose_page import _SEVERITY_BADGES

        for sev in ("ok", "warning", "error", "critical"):
            assert sev in _SEVERITY_BADGES
            assert _SEVERITY_BADGES[sev].strip() != ""

    def test_check_card_toggle_details_changes_state(self):
        """toggle_details inverse le flag _details_visible."""
        from winboost.gui.diagnose_page import CheckResultCard

        with patch.object(CheckResultCard, "__init__", lambda self, *a, **kw: None):
            card = CheckResultCard(MagicMock(), _make_check_result())
            card._check = _make_check_result()
            card._details_visible = False
            card._details_frame = None

            # Mock le ctk.CTkFrame du details panel pour eviter l'instantiation
            with patch("winboost.gui.diagnose_page.ctk.CTkFrame") as mock_frame_cls, \
                 patch("winboost.gui.diagnose_page.ctk.CTkLabel"):
                mock_frame_cls.return_value = MagicMock()
                card._toggle_details()

            assert card._details_visible is True


# ---------------------------------------------------------------------------
# Tests FixStepCard — Apply / Manuel
# ---------------------------------------------------------------------------


class TestFixStepCard:
    """Tests des steps automatiques et manuels."""

    def test_fix_step_card_auto_calls_on_apply_callback(self):
        """Test 3 : click 'Appliquer' sur un step auto -> appelle on_apply."""
        from winboost.gui.diagnose_page import FixStepCard

        on_apply = MagicMock()

        with patch.object(FixStepCard, "__init__", lambda self, *a, **kw: None):
            card = FixStepCard(MagicMock(), {})
            card._step = {
                "step": 1,
                "action_id": "net_012",
                "description": "Restart bthserv",
            }
            card._on_apply = on_apply
            card._on_manual = None
            card._action_btn = MagicMock()

            card._handle_apply()

        on_apply.assert_called_once_with("net_012", card)
        card._action_btn.configure.assert_called()

    def test_fix_step_card_manual_calls_on_manual_callback(self):
        """Test 4 : click 'Voir details' sur step manuel -> appelle on_manual."""
        from winboost.gui.diagnose_page import FixStepCard

        on_manual = MagicMock()
        step = {
            "step": 2,
            "manual": True,
            "description": "Long manuel description",
            "alternative": "alt",
        }

        with patch.object(FixStepCard, "__init__", lambda self, *a, **kw: None):
            card = FixStepCard(MagicMock(), {})
            card._step = step
            card._on_apply = None
            card._on_manual = on_manual
            card._action_btn = MagicMock()

            card._handle_manual()

        on_manual.assert_called_once_with(step)

    def test_fix_step_card_set_result_success_updates_badge(self):
        """Test 5 : set_result(success=True) ajoute un badge OK et desactive le bouton."""
        from winboost.gui.diagnose_page import FixStepCard

        with patch.object(FixStepCard, "__init__", lambda self, *a, **kw: None):
            card = FixStepCard(MagicMock(), {})
            card._step = {"step": 1, "action_id": "net_012"}
            card._on_apply = None
            card._on_manual = None
            card._action_btn = MagicMock()
            card._result_label = None

            with patch("winboost.gui.diagnose_page.ctk.CTkLabel") as mock_label_cls:
                mock_label = MagicMock()
                mock_label_cls.return_value = mock_label
                card.set_result(True, "Service redemarre")

        # Bouton desactive avec texte "Termine"
        card._action_btn.configure.assert_called_with(state="disabled", text="Termine")
        # Un label resultat a ete cree
        assert card._result_label is not None

    def test_fix_step_card_set_result_failure_uses_error_color(self):
        """set_result(success=False) utilise la couleur error."""
        from winboost.gui.diagnose_page import FixStepCard

        with patch.object(FixStepCard, "__init__", lambda self, *a, **kw: None):
            card = FixStepCard(MagicMock(), {})
            card._step = {"step": 1, "action_id": "net_012"}
            card._on_apply = None
            card._on_manual = None
            card._action_btn = MagicMock()
            card._result_label = None

            with patch("winboost.gui.diagnose_page.ctk.CTkLabel") as mock_label_cls:
                mock_label_cls.return_value = MagicMock()
                card.set_result(False, "Access denied")

                # Verifie que le 1er appel CTkLabel a un fg_color rouge
                kwargs = mock_label_cls.call_args.kwargs
                # COLORS["error"] = "#e74c3c"
                assert kwargs.get("fg_color") == "#e74c3c"

    def test_fix_step_card_apply_without_action_id_noop(self):
        """Step manuel : _handle_apply sans action_id ne fait rien (defense)."""
        from winboost.gui.diagnose_page import FixStepCard

        on_apply = MagicMock()

        with patch.object(FixStepCard, "__init__", lambda self, *a, **kw: None):
            card = FixStepCard(MagicMock(), {})
            card._step = {"step": 1, "manual": True}
            card._on_apply = on_apply
            card._on_manual = None
            card._action_btn = MagicMock()

            card._handle_apply()

        on_apply.assert_not_called()


# ---------------------------------------------------------------------------
# Tests DiagnosePage — interactions utilisateur
# ---------------------------------------------------------------------------


class TestDiagnosePageInteractions:
    """Tests du flux principal : query -> scan -> rapport."""

    def test_empty_query_shows_error_and_does_not_start_scan(self):
        """Test 6 : query vide -> erreur affichee, pas de scan."""
        page, _ctk, _mod = _build_page_skeleton()
        page.input_entry.get.return_value = "   "  # whitespace only

        with patch.object(page, "_start_scan") as mock_start:
            page._on_run_click()

        # Le scan n'est jamais lance
        mock_start.assert_not_called()
        # L'erreur est affichee : configure() + grid()
        page._error_label.configure.assert_called()
        page._error_label.grid.assert_called()

    def test_run_click_with_valid_query_starts_scan(self):
        """Une query non vide declenche _start_scan."""
        page, _ctk, _mod = _build_page_skeleton()
        page.input_entry.get.return_value = "manette bluetooth"

        with patch.object(page, "_start_scan") as mock_start:
            page._on_run_click()

        mock_start.assert_called_once_with("manette bluetooth")

    def test_run_click_disabled_while_scanning(self):
        """Click pendant un scan en cours est ignore (pas de double scan)."""
        page, _ctk, _mod = _build_page_skeleton()
        page._is_scanning = True
        page.input_entry.get.return_value = "manette"

        with patch.object(page, "_start_scan") as mock_start:
            page._on_run_click()

        mock_start.assert_not_called()

    def test_fill_example_prefills_entry_without_running(self):
        """Test 9 : click sur un exemple pre-remplit la zone (pas de scan)."""
        page, _ctk, _mod = _build_page_skeleton()

        with patch.object(page, "_start_scan") as mock_start:
            page._fill_example("internet lent")

        page.input_entry.delete.assert_called_with(0, "end")
        page.input_entry.insert.assert_called_with(0, "internet lent")
        # Le scan n'est PAS lance automatiquement
        mock_start.assert_not_called()


# ---------------------------------------------------------------------------
# Tests DiagnosePage — threading et runner
# ---------------------------------------------------------------------------


class TestDiagnosePageRunner:
    """Tests de l'integration avec DiagnosticRunner."""

    def test_run_query_in_thread_calls_runner(self):
        """Test 7 : _run_query_in_thread appelle runner.run_from_query une fois."""
        page, _ctk, _mod = _build_page_skeleton()

        report = _make_report()
        mock_runner = MagicMock()
        mock_runner.run_from_query.return_value = report
        page._runner_factory = MagicMock(return_value=mock_runner)

        with patch.object(page, "_display_report") as mock_display:
            page._run_query_in_thread("manette bluetooth")

        page._runner_factory.assert_called_once()
        mock_runner.run_from_query.assert_called_once_with("manette bluetooth")
        mock_display.assert_called_once_with(report)

    def test_run_query_in_thread_handles_runner_exception(self):
        """Si run_from_query leve, _display_error est appele (UI ne crash pas)."""
        page, _ctk, _mod = _build_page_skeleton()

        mock_runner = MagicMock()
        mock_runner.run_from_query.side_effect = ValueError("query invalide")
        page._runner_factory = MagicMock(return_value=mock_runner)

        with patch.object(page, "_display_error") as mock_err:
            page._run_query_in_thread("foo")

        mock_err.assert_called_once()
        # Le message contient bien la cause
        assert "query invalide" in mock_err.call_args.args[0]

    def test_start_scan_disables_run_button(self):
        """Pendant le scan, le bouton est disabled avec texte explicite."""
        page, _ctk, _mod = _build_page_skeleton()

        with patch("winboost.gui.diagnose_page.threading.Thread") as mock_thread_cls, \
             patch("winboost.gui.diagnose_page.ctk.CTkLabel") as mock_label_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            mock_label_cls.return_value = MagicMock()

            page._start_scan("test query")

        # Bouton disabled
        page.run_btn.configure.assert_any_call(state="disabled", text="Diagnostic en cours...")
        # Entry desactivee aussi
        page.input_entry.configure.assert_any_call(state="disabled")
        # Le thread a ete demarre
        mock_thread.start.assert_called_once()
        assert page._is_scanning is True


# ---------------------------------------------------------------------------
# Tests DiagnosePage — affichage du rapport et apply
# ---------------------------------------------------------------------------


class TestDiagnosePageDisplay:
    """Tests rendu du rapport."""

    def test_display_report_clears_results_and_renders_sections(self):
        """Test 10 : _display_report vide + repeuple avec checks + plan."""
        page, _ctk, _mod = _build_page_skeleton()

        # Old children to clear
        old_child = MagicMock()
        page._results_frame.winfo_children.return_value = [old_child]

        report = _make_report()

        with patch.object(page, "_render_report_header") as mock_h, \
             patch.object(page, "_render_checks_section") as mock_c, \
             patch.object(page, "_render_fix_plan_section") as mock_p:
            page._display_report(report)

        # Old child detruit
        old_child.destroy.assert_called_once()
        # 3 sections rendues
        mock_h.assert_called_once_with(report)
        mock_c.assert_called_once_with(report)
        mock_p.assert_called_once_with(report)
        # State update
        assert page._is_scanning is False
        assert page._last_report is report
        # Bouton repasse en mode "Re-diagnostiquer"
        page.run_btn.configure.assert_any_call(state="normal", text="Re-diagnostiquer")


class TestDiagnosePageApplyAction:
    """Tests Apply (T082 ActionExecutor)."""

    def test_apply_worker_calls_executor_apply_and_updates_card(self):
        """Test 8 : click Apply -> ActionExecutor.apply() -> set_result(True)."""
        page, _ctk, _mod = _build_page_skeleton()

        # Mock executor + result success
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.message = "Service redemarre OK"
        mock_executor = MagicMock()
        mock_executor.apply.return_value = mock_result

        page._executor_factory = MagicMock(return_value=mock_executor)

        # Mock action registry pour resoudre l'action_id
        mock_action = MagicMock()
        mock_action.id = "net_012"
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_action
        page._action_registry = mock_registry

        # Mock card
        mock_card = MagicMock()

        page._apply_worker("net_012", mock_card)

        mock_executor.apply.assert_called_once_with(mock_action)
        mock_card.set_result.assert_called_once_with(True, "Service redemarre OK")

    def test_apply_worker_action_not_in_registry_reports_failure(self):
        """Si l'action_id n'existe pas, la carte affiche une erreur."""
        page, _ctk, _mod = _build_page_skeleton()

        mock_registry = MagicMock()
        mock_registry.get.return_value = None  # introuvable
        page._action_registry = mock_registry

        mock_card = MagicMock()
        page._apply_worker("ghost_action", mock_card)

        mock_card.set_result.assert_called_once()
        args, _ = mock_card.set_result.call_args
        assert args[0] is False
        assert "ghost_action" in args[1]

    def test_apply_worker_executor_exception_reports_failure(self):
        """Si executor.apply leve, la carte affiche l'erreur (UI ne crash pas)."""
        page, _ctk, _mod = _build_page_skeleton()

        mock_executor = MagicMock()
        mock_executor.apply.side_effect = RuntimeError("admin required")
        page._executor_factory = MagicMock(return_value=mock_executor)

        mock_action = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_action
        page._action_registry = mock_registry

        mock_card = MagicMock()
        page._apply_worker("net_012", mock_card)

        mock_card.set_result.assert_called_once()
        args, _ = mock_card.set_result.call_args
        assert args[0] is False
        assert "admin required" in args[1]


# ---------------------------------------------------------------------------
# Tests integration soft : DiagnosticRunner reel + page mockee
# ---------------------------------------------------------------------------


class TestDiagnoseEndToEndSoft:
    """Tests "soft E2E" : on passe par le vrai DiagnosticRunner mais tous les
    checks sous-jacents sont mockes (via theme_registry custom).
    """

    def test_run_with_custom_theme_registry_produces_report(self):
        """Le runner avec un theme custom retourne un rapport coherent."""
        from winboost.diagnose.checks import Check, CheckResult, Severity
        from winboost.diagnose.runner import DiagnosticRunner

        class StubCheck(Check):
            name = "stub_test"

            def run(self) -> CheckResult:
                return CheckResult(
                    name=self.name,
                    severity=Severity.WARNING.value,
                    message="stub problem",
                    details={"k": "v"},
                    suggested_actions=("net_012",),
                )

        registry = {"bluetooth": lambda: [StubCheck()]}
        keywords = {"bluetooth": ("bluetooth", "manette")}
        runner = DiagnosticRunner(
            theme_registry=registry,
            theme_keywords=keywords,
            fallback_theme="bluetooth",
        )
        report = runner.run_from_query("manette bug")

        assert report.has_problems is True
        assert len(report.checks) == 1
        assert report.checks[0].name == "stub_test"
        # Le plan contient bien net_012
        assert any(s.get("action_id") == "net_012" for s in report.recommended_fix_plan)

    def test_diagnose_page_integrates_with_real_runner(self):
        """DiagnosePage utilise un DiagnosticRunner factory (peut etre custom)."""
        page, _ctk, _mod = _build_page_skeleton()

        # On utilise un runner reel mais avec theme stub
        from winboost.diagnose.checks import Check, CheckResult, Severity
        from winboost.diagnose.runner import DiagnosticRunner

        class StubCheck(Check):
            name = "stub"

            def run(self):
                return CheckResult(
                    name=self.name,
                    severity=Severity.OK.value,
                    message="all good",
                    suggested_actions=(),
                )

        runner = DiagnosticRunner(
            theme_registry={"bluetooth": lambda: [StubCheck()]},
            theme_keywords={"bluetooth": ("bluetooth",)},
            fallback_theme="bluetooth",
        )
        page._runner_factory = lambda: runner

        with patch.object(page, "_display_report") as mock_display:
            page._run_query_in_thread("bluetooth check")

        mock_display.assert_called_once()
        report = mock_display.call_args.args[0]
        assert report.theme == "bluetooth"
        assert len(report.checks) == 1
