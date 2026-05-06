"""Tests pour winboost.gui.pilot_history_page (Phase 13 v2.4 polish C).

Approche : on mocke entierement CustomTkinter et HistoryManager via
unittest.mock pour eviter d'avoir besoin d'un display reel ni d'une
vraie SQLite. Les widgets Tk sont remplaces par MagicMock.

Couverture exigee >= 8 tests :
- T1 : module s'importe + classes publiques exposees
- T2 : aggregate_sessions agrege par fenetre temporelle
- T3 : aggregate_sessions detecte les statuts (completed/cancelled/error)
- T4 : page peut etre instanciee sans crash (mock CTk + HistoryManager)
- T5 : page sans session -> affiche message vide
- T6 : page avec sessions -> cards rendues
- T7 : drill-down expand/masque les iterations
- T8 : filtres correctement appliques (Termines/Cancelled/Erreur)
- T9 : stats globales calculees (sessions, completion rate)
- T10 : click screenshot -> screenshot_opener appele (mock os.startfile)
- T11 : HistoryManager get_history echoue -> page ne crash pas
- T12 : app.py reference le nouvel onglet
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from winboost.core.history import HistoryEntry

# ---------------------------------------------------------------------------
# Helpers : factories de HistoryEntry simulees
# ---------------------------------------------------------------------------


def _make_entry(
    *,
    timestamp: datetime,
    description: str = "click(100, 200)",
    result_status: str = "executed",
    result_detail: str = "",
    metadata: dict[str, Any] | None = None,
    risk_level: str = "low",
) -> HistoryEntry:
    """Construit une HistoryEntry mockee comme si elle venait de SQLite."""
    return HistoryEntry(
        entry_id=None,
        timestamp=timestamp.isoformat(),
        module_name="pilot",
        action_type="pilot",
        description=description,
        risk_level=risk_level,
        result_status=result_status,
        result_detail=result_detail,
        metadata=metadata or {},
    )


def _make_history_factory(entries: list[HistoryEntry]):
    """Factory `() -> HistoryManager` qui retourne un mock get_history."""
    mock_history = MagicMock()
    mock_history.get_history.return_value = entries
    return lambda: mock_history


def _build_page_skeleton(
    *,
    entries: list[HistoryEntry] | None = None,
    clock: datetime | None = None,
    screenshot_opener=None,
):
    """Construit une PilotHistoryPage sans GUI reelle."""
    from winboost.gui import pilot_history_page

    page = pilot_history_page.PilotHistoryPage.__new__(
        pilot_history_page.PilotHistoryPage
    )
    page._config = None
    page._history_factory = _make_history_factory(entries or [])
    page._screenshot_opener = screenshot_opener or MagicMock()
    page._clock = lambda: clock or datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    page._gap_seconds = pilot_history_page.SESSION_GAP_SECONDS
    page._max_entries = 1000
    page._current_filter = pilot_history_page.FILTER_ALL
    page._sessions = []
    page._stats = {}
    page._filter_buttons = {}
    page._stats_label = MagicMock()
    page._stats_note = MagicMock()
    page._sessions_frame = MagicMock()
    page._sessions_frame.winfo_children.return_value = []
    return page, pilot_history_page


# ---------------------------------------------------------------------------
# T1 — Module imports + public surface
# ---------------------------------------------------------------------------


class TestPilotHistoryImports:
    def test_module_imports_without_crash(self):
        from winboost.gui import pilot_history_page

        assert hasattr(pilot_history_page, "PilotHistoryPage")
        assert hasattr(pilot_history_page, "PilotSession")
        assert hasattr(pilot_history_page, "PilotSessionCard")
        assert hasattr(pilot_history_page, "aggregate_sessions")

    def test_filter_constants_exposed(self):
        from winboost.gui.pilot_history_page import (
            FILTER_ALL,
            FILTER_CANCELLED,
            FILTER_COMPLETED,
            FILTER_ERROR,
        )

        assert FILTER_ALL == "tous"
        assert FILTER_COMPLETED == "termines"
        assert FILTER_CANCELLED == "cancelled"
        assert FILTER_ERROR == "erreur"

    def test_pilot_module_name_constant_matches_backend(self):
        """PILOT_MODULE_NAME doit matcher ce qui est ecrit par le pilot backend."""
        from winboost.gui.pilot_history_page import PILOT_MODULE_NAME

        # Cf. AnthropicPilot._log_history -> module_name='pilot'
        assert PILOT_MODULE_NAME == "pilot"

    def test_app_imports_pilot_history_page(self):
        """Test : app.py reference PilotHistoryPage et l'onglet 'pilot_history'."""
        app_path = (
            Path(__file__).parent.parent.parent / "winboost" / "gui" / "app.py"
        )
        content = app_path.read_text(encoding="utf-8")

        assert (
            "from winboost.gui.pilot_history_page import PilotHistoryPage"
            in content
        )
        assert '"pilot_history"' in content


# ---------------------------------------------------------------------------
# T2 + T3 — Aggregation par fenetre temporelle + statut
# ---------------------------------------------------------------------------


class TestAggregateSessions:
    def test_empty_returns_empty_list(self):
        from winboost.gui.pilot_history_page import aggregate_sessions

        assert aggregate_sessions([]) == []

    def test_two_close_events_form_one_session(self):
        from winboost.gui.pilot_history_page import aggregate_sessions

        t0 = datetime(2026, 5, 6, 14, 30, tzinfo=UTC)
        entries = [
            _make_entry(timestamp=t0, description="click(100, 100)"),
            _make_entry(
                timestamp=t0 + timedelta(seconds=30),
                description="click(200, 200)",
            ),
        ]
        sessions = aggregate_sessions(entries)
        assert len(sessions) == 1
        assert sessions[0].iteration_count == 2

    def test_two_far_events_form_two_sessions(self):
        """Gap > 30 min -> 2 sessions distinctes."""
        from winboost.gui.pilot_history_page import aggregate_sessions

        t0 = datetime(2026, 5, 6, 14, 30, tzinfo=UTC)
        entries = [
            _make_entry(timestamp=t0, description="A"),
            _make_entry(
                timestamp=t0 + timedelta(hours=2), description="B"
            ),
        ]
        sessions = aggregate_sessions(entries)
        assert len(sessions) == 2
        # Sorted plus recent en premier
        assert sessions[0].query == "B"
        assert sessions[1].query == "A"

    def test_session_query_uses_first_description(self):
        from winboost.gui.pilot_history_page import aggregate_sessions

        t0 = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
        entries = [
            _make_entry(timestamp=t0, description="imprimante ne marche pas"),
            _make_entry(
                timestamp=t0 + timedelta(seconds=10),
                description="click(100, 100)",
            ),
        ]
        sessions = aggregate_sessions(entries)
        assert len(sessions) == 1
        assert "imprimante" in sessions[0].query

    def test_session_status_completed(self):
        from winboost.gui.pilot_history_page import (
            SESSION_STATUS_COMPLETED,
            aggregate_sessions,
        )

        t0 = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
        entries = [
            _make_entry(timestamp=t0, result_status="executed"),
            _make_entry(
                timestamp=t0 + timedelta(seconds=5),
                result_status="completed",
            ),
        ]
        sessions = aggregate_sessions(entries)
        assert sessions[0].status == SESSION_STATUS_COMPLETED

    def test_session_status_cancelled_via_aborted_user_stop(self):
        """aborted + 'user_stop' dans le detail -> cancelled UX."""
        from winboost.gui.pilot_history_page import (
            SESSION_STATUS_CANCELLED,
            aggregate_sessions,
        )

        t0 = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
        entries = [
            _make_entry(timestamp=t0, result_status="executed"),
            _make_entry(
                timestamp=t0 + timedelta(seconds=5),
                result_status="aborted",
                result_detail="user_stop@iter3",
            ),
        ]
        sessions = aggregate_sessions(entries)
        assert sessions[0].status == SESSION_STATUS_CANCELLED

    def test_session_status_error(self):
        from winboost.gui.pilot_history_page import (
            SESSION_STATUS_ERROR,
            aggregate_sessions,
        )

        t0 = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
        entries = [
            _make_entry(
                timestamp=t0,
                result_status="error",
                result_detail="api_error: timeout",
            ),
        ]
        sessions = aggregate_sessions(entries)
        assert sessions[0].status == SESSION_STATUS_ERROR

    def test_session_duration_label(self):
        """duration_label format 'Xm Ys' ou 'Ys'."""
        from winboost.gui.pilot_history_page import aggregate_sessions

        t0 = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
        entries = [
            _make_entry(timestamp=t0),
            _make_entry(timestamp=t0 + timedelta(seconds=125)),
        ]
        sessions = aggregate_sessions(entries)
        assert sessions[0].duration_label == "2m 05s"


# ---------------------------------------------------------------------------
# T4 + T11 — Page peut etre instanciee, robustness vs SQLite errors
# ---------------------------------------------------------------------------


class TestPilotHistoryPageInstantiation:
    def test_skeleton_can_be_built(self):
        """Page skeleton se construit sans appel Tk reel."""
        page, _mod = _build_page_skeleton()
        assert page._current_filter == "tous"
        assert page._sessions == []

    def test_load_sessions_handles_history_manager_error(self):
        """get_history qui leve -> retourne [] sans crash."""
        from winboost.gui import pilot_history_page

        page = pilot_history_page.PilotHistoryPage.__new__(
            pilot_history_page.PilotHistoryPage
        )
        # HistoryManager mock qui leve sur get_history
        bad_history = MagicMock()
        bad_history.get_history.side_effect = RuntimeError("db locked")
        page._history_factory = lambda: bad_history
        page._max_entries = 1000
        page._gap_seconds = 1800

        sessions = page._load_sessions()
        assert sessions == []

    def test_load_sessions_handles_factory_error(self):
        """history_factory qui leve -> retourne [] (caught dans refresh)."""

        page, _mod = _build_page_skeleton()
        page._history_factory = MagicMock(
            side_effect=RuntimeError("history init failed")
        )
        # refresh ne doit pas crash
        with patch.object(page, "_render_stats"), patch.object(
            page, "_render_sessions"
        ):
            page.refresh()
        assert page._sessions == []


# ---------------------------------------------------------------------------
# T5 + T6 — Rendu vide vs rendu avec sessions
# ---------------------------------------------------------------------------


class TestSessionsRendering:
    def test_render_sessions_with_empty_list_shows_message(self):
        """Aucune session -> message 'Aucune session Pilot enregistree.'"""
        page, mod = _build_page_skeleton(entries=[])

        with patch("winboost.gui.pilot_history_page.ctk.CTkLabel") as mock_label:
            page._render_sessions()

        # Le label vide a ete cree
        calls = [str(c) for c in mock_label.call_args_list]
        assert any("Aucune session" in c for c in calls)

    def test_render_sessions_with_sessions_creates_cards(self):
        """Sessions presentes -> PilotSessionCard cree pour chacune."""
        t0 = datetime(2026, 5, 6, 14, 30, tzinfo=UTC)
        entries = [
            _make_entry(timestamp=t0, description="task A"),
            _make_entry(
                timestamp=t0 + timedelta(hours=2), description="task B"
            ),
        ]
        page, mod = _build_page_skeleton(entries=entries)
        # Charge les sessions sans render
        page._sessions = mod.aggregate_sessions(entries)

        with patch(
            "winboost.gui.pilot_history_page.PilotSessionCard"
        ) as mock_card:
            page._render_sessions()

        # 2 sessions = 2 cards instanciees
        assert mock_card.call_count == 2


# ---------------------------------------------------------------------------
# T7 — Drill-down expand/masque les iterations
# ---------------------------------------------------------------------------


class TestSessionCardDrillDown:
    def test_session_card_toggle_creates_and_destroys_details(self):
        """toggle_details cree puis detruit le frame d'iterations."""
        from winboost.gui.pilot_history_page import (
            PilotSession,
            PilotSessionCard,
        )

        # Skeleton de carte (sans __init__ Tk)
        card = PilotSessionCard.__new__(PilotSessionCard)
        card._session = PilotSession(
            started_at=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 6, 12, 1, tzinfo=UTC),
            query="dummy",
            status="completed",
            iterations=[
                _make_entry(
                    timestamp=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
                    description="click(1, 1)",
                ),
            ],
        )
        card._on_open_screenshot = None
        card._details_visible = False
        card._details_frame = None
        card._toggle_btn = MagicMock()
        # `self.pack` n'existe pas mais on n'en a pas besoin

        with patch(
            "winboost.gui.pilot_history_page.ctk.CTkFrame"
        ) as mock_frame, patch(
            "winboost.gui.pilot_history_page.IterationRow"
        ) as mock_row:
            mock_frame.return_value = MagicMock()
            card.toggle_details()
            assert card._details_visible is True
            mock_row.assert_called_once()

            # 2eme appel -> destroy
            card.toggle_details()
            assert card._details_visible is False
            assert card._details_frame is None


# ---------------------------------------------------------------------------
# T8 — Filtres
# ---------------------------------------------------------------------------


class TestFilters:
    def test_filter_completed_only_shows_completed(self):
        from winboost.gui.pilot_history_page import (
            FILTER_COMPLETED,
            SESSION_STATUS_CANCELLED,
            SESSION_STATUS_COMPLETED,
            PilotSession,
        )

        page, mod = _build_page_skeleton()
        page._sessions = [
            PilotSession(
                started_at=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 6, 12, 5, tzinfo=UTC),
                query="A",
                status=SESSION_STATUS_COMPLETED,
            ),
            PilotSession(
                started_at=datetime(2026, 5, 6, 13, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 6, 13, 1, tzinfo=UTC),
                query="B",
                status=SESSION_STATUS_CANCELLED,
            ),
        ]
        page._current_filter = FILTER_COMPLETED

        with patch(
            "winboost.gui.pilot_history_page.PilotSessionCard"
        ) as mock_card:
            page._render_sessions()

        # Une seule carte rendue (la completed)
        assert mock_card.call_count == 1

    def test_filter_cancelled_only_shows_cancelled(self):
        from winboost.gui.pilot_history_page import (
            FILTER_CANCELLED,
            SESSION_STATUS_CANCELLED,
            SESSION_STATUS_COMPLETED,
            PilotSession,
        )

        page, mod = _build_page_skeleton()
        page._sessions = [
            PilotSession(
                started_at=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 6, 12, 5, tzinfo=UTC),
                query="A",
                status=SESSION_STATUS_COMPLETED,
            ),
            PilotSession(
                started_at=datetime(2026, 5, 6, 13, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 6, 13, 1, tzinfo=UTC),
                query="B",
                status=SESSION_STATUS_CANCELLED,
            ),
        ]
        page._current_filter = FILTER_CANCELLED

        with patch(
            "winboost.gui.pilot_history_page.PilotSessionCard"
        ) as mock_card:
            page._render_sessions()

        assert mock_card.call_count == 1

    def test_filter_error_only_shows_errors(self):
        from winboost.gui.pilot_history_page import (
            FILTER_ERROR,
            SESSION_STATUS_COMPLETED,
            SESSION_STATUS_ERROR,
            PilotSession,
        )

        page, _mod = _build_page_skeleton()
        page._sessions = [
            PilotSession(
                started_at=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 6, 12, 5, tzinfo=UTC),
                query="ok",
                status=SESSION_STATUS_COMPLETED,
            ),
            PilotSession(
                started_at=datetime(2026, 5, 6, 13, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 6, 13, 1, tzinfo=UTC),
                query="bug",
                status=SESSION_STATUS_ERROR,
            ),
        ]
        page._current_filter = FILTER_ERROR

        with patch(
            "winboost.gui.pilot_history_page.PilotSessionCard"
        ) as mock_card:
            page._render_sessions()

        assert mock_card.call_count == 1

    def test_set_filter_changes_current_filter(self):
        from winboost.gui.pilot_history_page import (
            FILTER_CANCELLED,
            FILTER_COMPLETED,
        )

        page, _mod = _build_page_skeleton()
        page._filter_buttons = {
            FILTER_COMPLETED: MagicMock(),
            FILTER_CANCELLED: MagicMock(),
        }
        with patch.object(page, "_render_sessions"):
            page.set_filter(FILTER_CANCELLED)
        assert page._current_filter == FILTER_CANCELLED

    def test_set_filter_invalid_is_noop(self):
        page, _mod = _build_page_skeleton()
        with patch.object(page, "_render_sessions") as mock_render:
            page.set_filter("invalid_key")
        mock_render.assert_not_called()


# ---------------------------------------------------------------------------
# T9 — Stats globales
# ---------------------------------------------------------------------------


class TestStats:
    def test_compute_stats_empty_returns_zeros(self):
        from winboost.gui.pilot_history_page import _compute_stats

        stats = _compute_stats([])
        assert stats["sessions_this_month"] == 0
        assert stats["sessions_completed"] == 0
        assert stats["completion_rate"] == 0.0

    def test_compute_stats_completion_rate(self):
        """3 sessions ce mois, 2 completed -> rate = 2/3."""
        from winboost.gui.pilot_history_page import (
            SESSION_STATUS_CANCELLED,
            SESSION_STATUS_COMPLETED,
            PilotSession,
            _compute_stats,
        )

        now = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
        sessions = [
            PilotSession(
                started_at=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 6, 12, 1, tzinfo=UTC),
                query="A",
                status=SESSION_STATUS_COMPLETED,
            ),
            PilotSession(
                started_at=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 8, 12, 1, tzinfo=UTC),
                query="B",
                status=SESSION_STATUS_COMPLETED,
            ),
            PilotSession(
                started_at=datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 10, 12, 1, tzinfo=UTC),
                query="C",
                status=SESSION_STATUS_CANCELLED,
            ),
        ]
        stats = _compute_stats(sessions, now=now)
        assert stats["sessions_this_month"] == 3
        assert stats["sessions_completed"] == 2
        assert abs(stats["completion_rate"] - (2 / 3)) < 1e-6

    def test_compute_stats_excludes_other_months(self):
        """Une session du mois precedent ne compte pas."""
        from winboost.gui.pilot_history_page import (
            SESSION_STATUS_COMPLETED,
            PilotSession,
            _compute_stats,
        )

        now = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
        sessions = [
            PilotSession(
                started_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
                ended_at=datetime(2026, 4, 6, 12, 1, tzinfo=UTC),
                query="old",
                status=SESSION_STATUS_COMPLETED,
            ),
            PilotSession(
                started_at=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 6, 12, 1, tzinfo=UTC),
                query="new",
                status=SESSION_STATUS_COMPLETED,
            ),
        ]
        stats = _compute_stats(sessions, now=now)
        assert stats["sessions_this_month"] == 1

    def test_compute_stats_cost_known_when_metadata_present(self):
        from winboost.gui.pilot_history_page import (
            SESSION_STATUS_COMPLETED,
            PilotSession,
            _compute_stats,
        )

        now = datetime(2026, 5, 15, tzinfo=UTC)
        sessions = [
            PilotSession(
                started_at=datetime(2026, 5, 6, tzinfo=UTC),
                ended_at=datetime(2026, 5, 6, 0, 1, tzinfo=UTC),
                query="x",
                status=SESSION_STATUS_COMPLETED,
                cost_eur=0.18,
                cost_known=True,
            ),
        ]
        stats = _compute_stats(sessions, now=now)
        assert stats["cost_known"] is True
        assert abs(stats["cost_total_eur"] - 0.18) < 1e-6


# ---------------------------------------------------------------------------
# T10 — Open screenshot dispatche vers screenshot_opener
# ---------------------------------------------------------------------------


class TestScreenshotOpener:
    def test_open_screenshot_calls_opener(self):
        page, _mod = _build_page_skeleton()
        opener = MagicMock()
        page._screenshot_opener = opener

        page._open_screenshot("C:/tmp/iter1.png")
        opener.assert_called_once_with("C:/tmp/iter1.png")

    def test_open_screenshot_empty_path_is_noop(self):
        page, _mod = _build_page_skeleton()
        opener = MagicMock()
        page._screenshot_opener = opener

        page._open_screenshot("")
        opener.assert_not_called()

    def test_open_screenshot_handles_opener_exception(self):
        """Si opener leve -> page ne crash pas."""
        page, _mod = _build_page_skeleton()
        opener = MagicMock(side_effect=OSError("permission denied"))
        page._screenshot_opener = opener

        # Ne doit pas lever
        page._open_screenshot("C:/tmp/iter1.png")
        opener.assert_called_once()

    def test_default_screenshot_opener_uses_os_startfile_when_present(
        self, tmp_path: Path
    ):
        """Sur Windows : os.startfile invoque sur path existant."""
        from winboost.gui import pilot_history_page

        # Cree un fichier reel
        target = tmp_path / "screenshot.png"
        target.write_bytes(b"\x89PNG fake")

        # Patch os.startfile (existe sur Windows)
        with patch.object(
            pilot_history_page.os, "startfile", create=True
        ) as mock_start:
            pilot_history_page._default_screenshot_opener(str(target))
        mock_start.assert_called_once()

    def test_default_screenshot_opener_skips_missing_path(
        self, tmp_path: Path
    ):
        """Path inexistant -> noop, pas de crash."""
        from winboost.gui import pilot_history_page

        nonexistent = str(tmp_path / "nope.png")
        with patch.object(
            pilot_history_page.os, "startfile", create=True
        ) as mock_start:
            pilot_history_page._default_screenshot_opener(nonexistent)
        mock_start.assert_not_called()


# ---------------------------------------------------------------------------
# T12 — Iteration row screenshot extraction
# ---------------------------------------------------------------------------


class TestScreenshotPathExtraction:
    def test_metadata_screenshot_path_detected(self):
        from winboost.gui.pilot_history_page import _extract_screenshot_path

        entry = _make_entry(
            timestamp=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            metadata={"screenshot_path": "C:/tmp/foo.png"},
        )
        assert _extract_screenshot_path(entry) == "C:/tmp/foo.png"

    def test_result_detail_with_png_suffix_detected(self):
        from winboost.gui.pilot_history_page import _extract_screenshot_path

        entry = _make_entry(
            timestamp=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            result_detail="C:/Users/me/winboost/iter1.png",
        )
        assert _extract_screenshot_path(entry).endswith(".png")

    def test_no_screenshot_returns_empty(self):
        from winboost.gui.pilot_history_page import _extract_screenshot_path

        entry = _make_entry(
            timestamp=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            result_detail="click(1,1)",
        )
        assert _extract_screenshot_path(entry) == ""
