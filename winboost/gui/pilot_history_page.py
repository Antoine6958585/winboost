"""Pilot History Page — Vue dediee aux sessions Computer Use (Phase 13 v2.4 polish C).

Distinct de l'historique general (`history_page.py`) : ici on agrege les
actions Pilot en **sessions** (1 invocation `winboost pilot ...` = 1 ligne)
avec drill-down sur les iterations.

Architecture
------------

`PilotHistoryPage(ctk.CTkFrame)` :
- Stats globales en tete (sessions ce mois, taux completion, note honnete
  sur l'absence de cout historique cf. limitation).
- Filtres : Tous / Terminés / Cancelled / Erreur (segmented buttons).
- Liste scrollable de `PilotSessionCard`. Chaque carte affiche :
  query (description de la 1ere action), statut, duree, nb iterations,
  bouton "Voir details" qui expand inline les iterations.

Sources de donnees
------------------

`HistoryManager.get_history(module_name="pilot", limit=...)` retourne des
HistoryEntry chronologiques. On agrege par fenetre temporelle (default 30
min entre 2 events Pilot consecutifs = meme session). Aucune cle
`session_id` n'existe encore cote backend — l'agregation est temporelle
et **approximative**. Documentee dans la limitation `LIMITATION_NO_SESSION_ID`.

Decisions UX
------------

- **Drill-down expand inline** (pas popup) : coherent avec
  `history_page.HistoryEntryCard._toggle_detail` ; preserve le contexte
  de scroll, pas de modal a fermer.
- **Cout NON affiche** : les logs Pilot sont ecrits via `_log_history()`
  sans metadata cost. On affiche une note honnete plutot que des
  pseudo-valeurs. Si le backend Pilot ajoute le cost en metadata
  (cf. `T084_PILOT_HISTORY_COST` future), `_compute_session_cost` est
  pret a le prendre.
- **Open screenshot** : `os.startfile(path)` sur Windows (gallery par
  defaut), wrappee + injectable pour les tests.
- **Vide** : message clair "Aucune session Pilot enregistree".
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import customtkinter as ctk

from winboost.core.history import HistoryEntry, HistoryManager
from winboost.gui.theme import COLORS, FONTS

logger = logging.getLogger(__name__)

__all__ = [
    "PilotHistoryPage",
    "PilotSession",
    "PilotSessionCard",
    "aggregate_sessions",
    "PILOT_MODULE_NAME",
    "SESSION_GAP_SECONDS",
    "SESSION_STATUS_COMPLETED",
    "SESSION_STATUS_CANCELLED",
    "SESSION_STATUS_ERROR",
    "SESSION_STATUS_OTHER",
    "FILTER_ALL",
    "FILTER_COMPLETED",
    "FILTER_CANCELLED",
    "FILTER_ERROR",
]

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Module utilise par AnthropicPilot._log_history. Si cela change cote backend,
#: ajuster ici.
PILOT_MODULE_NAME = "pilot"

#: Gap maximum (secondes) entre 2 events Pilot consecutifs pour les considerer
#: comme appartenant a la meme session. 30 min par defaut (cf. design Polish C).
SESSION_GAP_SECONDS = 30 * 60

#: Statuts agreges au niveau session (deduits des HistoryEntry.result_status).
SESSION_STATUS_COMPLETED = "completed"
SESSION_STATUS_CANCELLED = "cancelled"
SESSION_STATUS_ERROR = "error"
SESSION_STATUS_OTHER = "other"

#: Filtres exposes dans la GUI.
FILTER_ALL = "tous"
FILTER_COMPLETED = "termines"
FILTER_CANCELLED = "cancelled"
FILTER_ERROR = "erreur"

#: Mapping filtre -> session_status accepte.
_FILTER_TO_STATUSES: dict[str, set[str]] = {
    FILTER_ALL: {
        SESSION_STATUS_COMPLETED,
        SESSION_STATUS_CANCELLED,
        SESSION_STATUS_ERROR,
        SESSION_STATUS_OTHER,
    },
    FILTER_COMPLETED: {SESSION_STATUS_COMPLETED},
    FILTER_CANCELLED: {SESSION_STATUS_CANCELLED},
    FILTER_ERROR: {SESSION_STATUS_ERROR},
}

#: Couleurs par session_status (consistantes avec theme WinBoost).
_STATUS_COLORS: dict[str, str] = {
    SESSION_STATUS_COMPLETED: COLORS["success"],
    SESSION_STATUS_CANCELLED: COLORS["warning"],
    SESSION_STATUS_ERROR: COLORS["error"],
    SESSION_STATUS_OTHER: COLORS["text_muted"],
}

#: Libelles pour les badges statut.
_STATUS_BADGES: dict[str, str] = {
    SESSION_STATUS_COMPLETED: " TERMINE ",
    SESSION_STATUS_CANCELLED: " CANCELLED ",
    SESSION_STATUS_ERROR: " ERREUR ",
    SESSION_STATUS_OTHER: " EN COURS ",
}

#: Libelles d'iteration (HistoryEntry.result_status -> label court).
_ITER_STATUS_LABELS: dict[str, str] = {
    "executed": "Execute",
    "skipped": "Skip",
    "cancelled": "Cancel",
    "error": "Erreur",
    "completed": "Termine",
    "stopped": "Arrete",
    "aborted": "Abort",
}

#: Note honnete sur les limites de l'agregation.
LIMITATION_NO_SESSION_ID = (
    "Note : les sessions sont reconstruites par groupement temporel "
    "(events Pilot dans une fenetre de 30 min consecutifs = 1 session). "
    "Pas de session_id explicite cote backend pour le moment."
)


# ---------------------------------------------------------------------------
# Modele : PilotSession
# ---------------------------------------------------------------------------


@dataclass
class PilotSession:
    """Une session Pilot reconstruite par agregation temporelle.

    Attributs:
        started_at: datetime UTC du 1er event de la session.
        ended_at: datetime UTC du dernier event.
        query: description la plus representative (premier event explicite,
            ou label court a defaut).
        status: agregat dans {completed, cancelled, error, other}.
        iterations: liste ordonnee chronologique des HistoryEntry.
        cost_eur: cout total connu (0.0 si non disponible dans les logs).
        cost_known: True si au moins un event avait un cost dans metadata.
    """

    started_at: datetime
    ended_at: datetime
    query: str
    status: str
    iterations: list[HistoryEntry] = field(default_factory=list)
    cost_eur: float = 0.0
    cost_known: bool = False

    @property
    def duration_seconds(self) -> float:
        """Duree de la session en secondes (>= 0)."""
        return max(0.0, (self.ended_at - self.started_at).total_seconds())

    @property
    def duration_label(self) -> str:
        """Label compact 'Xm Ys' ou 'Ys'."""
        secs = int(self.duration_seconds)
        if secs < 60:
            return f"{secs}s"
        m, s = divmod(secs, 60)
        return f"{m}m {s:02d}s"

    @property
    def iteration_count(self) -> int:
        """Nombre d'iterations agregees (events HistoryEntry)."""
        return len(self.iterations)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _parse_timestamp(value: str | None) -> datetime:
    """Parse un timestamp ISO 8601, fallback datetime UTC now."""
    if not value:
        return datetime.now(tz=UTC)
    try:
        # Python 3.11+ accepte "Z" via fromisoformat.
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        try:
            return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=UTC
            )
        except ValueError:
            return datetime.now(tz=UTC)


def _entry_cost(entry: HistoryEntry) -> tuple[float, bool]:
    """Extrait le cost EUR de la metadata si present.

    Returns:
        (cost_eur, known). `known` est False si aucune cle reconnaissable.
        Cles reconnues : 'cost_eur', 'total_cost_eur', 'eur'.
    """
    meta = getattr(entry, "metadata", None) or {}
    if not isinstance(meta, dict):
        return 0.0, False
    for key in ("cost_eur", "total_cost_eur", "eur"):
        if key in meta:
            try:
                return float(meta[key]), True
            except (TypeError, ValueError):
                continue
    return 0.0, False


def _aggregate_status(iterations: Sequence[HistoryEntry]) -> str:
    """Deduit le statut session a partir des statuts des iterations.

    Regle :
    - 'completed' si une iteration a result_status='completed'.
    - sinon 'cancelled' si une iteration a result_status='cancelled'
      ou si la derniere iteration a result_status='aborted'/'stopped'
      avec un detail user_stop / user_cancel / consecutive_limit.
    - sinon 'error' si une iteration a result_status='error'.
    - sinon 'other' (en cours, statut indetermine).
    """
    statuses = [(it.result_status or "").lower() for it in iterations]
    if "completed" in statuses:
        return SESSION_STATUS_COMPLETED
    if "cancelled" in statuses:
        return SESSION_STATUS_CANCELLED
    # 'aborted' avec user_stop/user_cancel = cancelled UX
    last = iterations[-1] if iterations else None
    if last is not None:
        last_status = (last.result_status or "").lower()
        last_detail = (last.result_detail or "").lower()
        if last_status in {"aborted", "stopped"} and any(
            token in last_detail
            for token in (
                "user_stop",
                "user_cancel",
                "consecutive_limit",
                "budget_exceeded",
            )
        ):
            return SESSION_STATUS_CANCELLED
    if "error" in statuses:
        return SESSION_STATUS_ERROR
    return SESSION_STATUS_OTHER


def _pick_query(iterations: Sequence[HistoryEntry]) -> str:
    """Choisit le 'query' representatif de la session.

    Heuristique : la 1ere iteration avec une description non vide.
    Fallback : description de la 1ere iteration sinon "(session sans query)".
    """
    for it in iterations:
        desc = (getattr(it, "description", "") or "").strip()
        if desc:
            return desc
    return "(session sans query)"


def aggregate_sessions(
    entries: Iterable[HistoryEntry],
    *,
    gap_seconds: int = SESSION_GAP_SECONDS,
) -> list[PilotSession]:
    """Agrege les HistoryEntry Pilot en sessions par fenetre temporelle.

    Args:
        entries: HistoryEntry Pilot, ordre quelconque (re-trie en interne).
        gap_seconds: gap max entre 2 events pour appartenir a la meme session.

    Returns:
        Liste de `PilotSession` ordonnee du plus recent au plus ancien.
    """
    sorted_entries = sorted(
        list(entries),
        key=lambda e: _parse_timestamp(getattr(e, "timestamp", None)),
    )
    if not sorted_entries:
        return []

    sessions: list[PilotSession] = []
    current: list[HistoryEntry] = []
    last_ts: datetime | None = None

    for entry in sorted_entries:
        ts = _parse_timestamp(entry.timestamp)
        if last_ts is None or (ts - last_ts).total_seconds() <= gap_seconds:
            current.append(entry)
        else:
            sessions.append(_build_session(current))
            current = [entry]
        last_ts = ts

    if current:
        sessions.append(_build_session(current))

    # Plus recent en premier
    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions


def _build_session(iterations: Sequence[HistoryEntry]) -> PilotSession:
    """Construit une PilotSession depuis une liste ordonnee chronologique."""
    started = _parse_timestamp(iterations[0].timestamp)
    ended = _parse_timestamp(iterations[-1].timestamp)
    cost_total = 0.0
    cost_known = False
    for it in iterations:
        cost, known = _entry_cost(it)
        if known:
            cost_known = True
            cost_total += cost
    return PilotSession(
        started_at=started,
        ended_at=ended,
        query=_pick_query(iterations),
        status=_aggregate_status(iterations),
        iterations=list(iterations),
        cost_eur=cost_total,
        cost_known=cost_known,
    )


# ---------------------------------------------------------------------------
# Stats globales
# ---------------------------------------------------------------------------


def _is_in_current_month(ts: datetime, *, now: datetime | None = None) -> bool:
    """True si `ts` est dans le mois calendaire courant (UTC)."""
    ref = now or datetime.now(tz=UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.year == ref.year and ts.month == ref.month


def _compute_stats(
    sessions: Sequence[PilotSession],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Calcule les stats globales pour le bandeau en tete.

    Returns:
        dict avec :
        - sessions_this_month: int
        - sessions_completed: int
        - completion_rate: float [0..1]
        - cost_total_eur: float
        - cost_known: bool (True si au moins une session avait un cout)
    """
    month_sessions = [
        s for s in sessions if _is_in_current_month(s.started_at, now=now)
    ]
    completed = [s for s in month_sessions if s.status == SESSION_STATUS_COMPLETED]
    cost_total = sum(s.cost_eur for s in month_sessions if s.cost_known)
    cost_known = any(s.cost_known for s in month_sessions)
    rate = (
        (len(completed) / len(month_sessions))
        if month_sessions
        else 0.0
    )
    return {
        "sessions_this_month": len(month_sessions),
        "sessions_completed": len(completed),
        "completion_rate": rate,
        "cost_total_eur": cost_total,
        "cost_known": cost_known,
    }


# ---------------------------------------------------------------------------
# IterationRow — rendu compact d'une iteration dans le drill-down
# ---------------------------------------------------------------------------


class IterationRow(ctk.CTkFrame):
    """Ligne compacte representant une iteration Pilot dans le drill-down.

    Affiche :
    - Index iteration + decision/result (badge couleur)
    - Description courte (de l'action proposee, ex: 'click(456, 234)')
    - Bouton 'Screenshot' si un chemin valide est present dans
      `result_detail` (heuristique : se termine par .png/.jpg).
    """

    def __init__(
        self,
        parent: Any,
        index: int,
        entry: HistoryEntry,
        on_open_screenshot: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent, fg_color=COLORS["bg_dark"], corner_radius=6, **kwargs
        )
        self.pack(fill="x", padx=6, pady=2)

        self._entry = entry
        self._on_open_screenshot = on_open_screenshot

        status_raw = (entry.result_status or "").lower()
        label = _ITER_STATUS_LABELS.get(status_raw, status_raw or "?")
        color = _STATUS_COLORS.get(
            _normalize_iter_status_to_session(status_raw),
            COLORS["text_muted"],
        )

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=6, pady=4)

        # Numero
        ctk.CTkLabel(
            row,
            text=f"Iter {index}",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            width=60,
            anchor="w",
        ).pack(side="left", padx=(0, 6))

        # Badge decision
        ctk.CTkLabel(
            row,
            text=f" {label} ",
            font=("Segoe UI", 9, "bold"),
            text_color="#ffffff",
            fg_color=color,
            corner_radius=4,
            width=80,
            height=18,
        ).pack(side="left", padx=(0, 6))

        # Description (action proposee)
        desc = (entry.description or "").strip() or "—"
        ctk.CTkLabel(
            row,
            text=desc,
            font=FONTS["mono"],
            text_color=COLORS["text"],
            anchor="w",
            wraplength=520,
            justify="left",
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        # Bouton screenshot si chemin detecte
        screenshot_path = _extract_screenshot_path(entry)
        if screenshot_path and on_open_screenshot is not None:
            ctk.CTkButton(
                row,
                text="Screenshot",
                font=FONTS["small"],
                fg_color=COLORS["info"],
                hover_color="#2980b9",
                text_color="#ffffff",
                height=22,
                width=90,
                corner_radius=6,
                command=lambda p=screenshot_path: on_open_screenshot(p),
            ).pack(side="right")


def _normalize_iter_status_to_session(status: str) -> str:
    """Map un result_status iteration vers une couleur cote session."""
    status = (status or "").lower()
    if status == "executed":
        return SESSION_STATUS_COMPLETED
    if status in {"skipped"}:
        return SESSION_STATUS_OTHER
    if status in {"cancelled", "aborted", "stopped"}:
        return SESSION_STATUS_CANCELLED
    if status == "completed":
        return SESSION_STATUS_COMPLETED
    if status == "error":
        return SESSION_STATUS_ERROR
    return SESSION_STATUS_OTHER


def _extract_screenshot_path(entry: HistoryEntry) -> str:
    """Heuristique : retourne un chemin .png/.jpg trouve dans metadata/detail.

    Cherche, dans l'ordre :
    1. metadata['screenshot_path'] / 'screenshot_before' / 'screenshot_after'
    2. result_detail si finit par .png/.jpg/.jpeg (cas legacy)
    """
    meta = getattr(entry, "metadata", None) or {}
    if isinstance(meta, dict):
        for key in ("screenshot_path", "screenshot_before", "screenshot_after"):
            value = meta.get(key)
            if isinstance(value, str) and value.lower().endswith(
                (".png", ".jpg", ".jpeg")
            ):
                return value
    detail = (entry.result_detail or "").strip()
    if detail.lower().endswith((".png", ".jpg", ".jpeg")):
        return detail
    return ""


# ---------------------------------------------------------------------------
# PilotSessionCard — carte d'une session avec drill-down inline
# ---------------------------------------------------------------------------


class PilotSessionCard(ctk.CTkFrame):
    """Carte visuelle pour une session Pilot, avec drill-down inline.

    Args:
        parent: widget Tk parent.
        session: PilotSession a afficher.
        on_open_screenshot: callback `(path: str) -> None` pour ouvrir un
            screenshot dans la galerie OS. Defaut : `os.startfile`.
    """

    def __init__(
        self,
        parent: Any,
        session: PilotSession,
        on_open_screenshot: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent, fg_color=COLORS["bg_card"], corner_radius=10, **kwargs
        )
        self.pack(fill="x", padx=4, pady=4)

        self._session = session
        self._on_open_screenshot = on_open_screenshot
        self._details_visible = False
        self._details_frame: ctk.CTkFrame | None = None

        # ---- Header : timestamp + query
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        try:
            ts_str = session.started_at.strftime("%Y-%m-%d %H:%M")
        except Exception:  # noqa: BLE001
            ts_str = str(session.started_at)

        ctk.CTkLabel(
            header,
            text=ts_str,
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            width=130,
            anchor="w",
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            header,
            text=session.query,
            font=FONTS["subheading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # ---- Ligne 2 : badge statut + duree + iterations + cost
        meta = ctk.CTkFrame(self, fg_color="transparent")
        meta.pack(fill="x", padx=10, pady=(0, 4))

        # Badge statut
        badge_color = _STATUS_COLORS.get(session.status, COLORS["text_muted"])
        badge_text = _STATUS_BADGES.get(session.status, " ? ")
        ctk.CTkLabel(
            meta,
            text=badge_text,
            font=("Segoe UI", 10, "bold"),
            text_color="#ffffff",
            fg_color=badge_color,
            corner_radius=4,
            width=110,
            height=22,
        ).pack(side="left", padx=(0, 8))

        # Duree
        ctk.CTkLabel(
            meta,
            text=f"Duree : {session.duration_label}",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 12))

        # Iterations
        ctk.CTkLabel(
            meta,
            text=f"Iterations : {session.iteration_count}",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 12))

        # Cout (si connu)
        if session.cost_known:
            ctk.CTkLabel(
                meta,
                text=f"Cout : {session.cost_eur:.4f} EUR",
                font=FONTS["small"],
                text_color=COLORS["accent"],
            ).pack(side="left")

        # ---- Bouton drill-down
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 8))

        self._toggle_btn = ctk.CTkButton(
            btn_row,
            text="Voir details",
            font=FONTS["small"],
            fg_color=COLORS["border"],
            hover_color=COLORS["bg_sidebar"],
            text_color=COLORS["text"],
            height=26,
            width=110,
            corner_radius=6,
            command=self.toggle_details,
        )
        self._toggle_btn.pack(side="left")

    # ------------------------------------------------------------------
    # Drill-down
    # ------------------------------------------------------------------

    def toggle_details(self) -> None:
        """Affiche/masque le panneau d'iterations."""
        if self._details_visible and self._details_frame is not None:
            with contextlib.suppress(Exception):
                self._details_frame.destroy()
            self._details_frame = None
            self._details_visible = False
            self._toggle_btn.configure(text="Voir details")
            return

        self._details_frame = ctk.CTkFrame(
            self, fg_color=COLORS["bg_dark"], corner_radius=8
        )
        self._details_frame.pack(fill="x", padx=10, pady=(0, 10))

        if not self._session.iterations:
            ctk.CTkLabel(
                self._details_frame,
                text="(pas d'iteration enregistree)",
                font=FONTS["small"],
                text_color=COLORS["text_muted"],
            ).pack(padx=10, pady=8)
        else:
            for idx, entry in enumerate(self._session.iterations, start=1):
                IterationRow(
                    self._details_frame,
                    idx,
                    entry,
                    on_open_screenshot=self._on_open_screenshot,
                )

        self._details_visible = True
        self._toggle_btn.configure(text="Masquer details")


# ---------------------------------------------------------------------------
# PilotHistoryPage — page principale
# ---------------------------------------------------------------------------


class PilotHistoryPage(ctk.CTkFrame):
    """Onglet "Historique Pilot" — sessions Computer Use agregees.

    Args:
        parent: widget Tk parent.
        config: Config WinBoost (non utilisee pour l'instant, gardee pour
            future personalisation).
        history_factory: factory `() -> HistoryManager` pour les tests.
        screenshot_opener: callable `(path: str) -> None` injectable
            (default : `os.startfile`).
        clock: callable `() -> datetime` injectable pour stats deterministes
            (default : `datetime.now(UTC)`).
        gap_seconds: gap max pour l'agregation (default `SESSION_GAP_SECONDS`).
        max_entries: limite haute des HistoryEntry charges depuis SQLite.
    """

    def __init__(
        self,
        parent: Any,
        config: Any = None,
        history_factory: Callable[[], HistoryManager] | None = None,
        screenshot_opener: Callable[[str], None] | None = None,
        clock: Callable[[], datetime] | None = None,
        gap_seconds: int = SESSION_GAP_SECONDS,
        max_entries: int = 1000,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self._config = config
        self._history_factory = history_factory or HistoryManager
        self._screenshot_opener = screenshot_opener or _default_screenshot_opener
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._gap_seconds = int(gap_seconds)
        self._max_entries = int(max_entries)

        # Etat
        self._current_filter: str = FILTER_ALL
        self._sessions: list[PilotSession] = []
        self._stats: dict[str, Any] = {}
        self._filter_buttons: dict[str, ctk.CTkButton] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._create_header()
        self._create_stats_panel()
        self._create_filter_bar()
        self._create_sessions_panel()

        # 1er rendu
        self.refresh()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _create_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 6))

        ctk.CTkLabel(
            header,
            text="Historique Pilot",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Actualiser",
            font=FONTS["small"],
            fg_color=COLORS["border"],
            hover_color=COLORS["bg_sidebar"],
            text_color=COLORS["text"],
            height=28,
            width=90,
            corner_radius=6,
            command=self.refresh,
        ).pack(side="right")

    def _create_stats_panel(self) -> None:
        """Bandeau de stats globales (sessions ce mois, completion, cout)."""
        wrapper = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=10)
        wrapper.grid(row=1, column=0, sticky="ew", padx=25, pady=(0, 8))

        self._stats_label = ctk.CTkLabel(
            wrapper,
            text="Chargement...",
            font=FONTS["body"],
            text_color=COLORS["text"],
            anchor="w",
            wraplength=900,
            justify="left",
        )
        self._stats_label.pack(fill="x", padx=12, pady=(10, 4))

        self._stats_note = ctk.CTkLabel(
            wrapper,
            text=LIMITATION_NO_SESSION_ID,
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
            wraplength=900,
            justify="left",
        )
        self._stats_note.pack(fill="x", padx=12, pady=(0, 10))

    def _create_filter_bar(self) -> None:
        """Barre de filtres : Tous / Termines / Cancelled / Erreur."""
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=25, pady=(0, 8))

        ctk.CTkLabel(
            bar,
            text="Filtrer :",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 8))

        for key, label in (
            (FILTER_ALL, "Tous"),
            (FILTER_COMPLETED, "Termines"),
            (FILTER_CANCELLED, "Cancelled"),
            (FILTER_ERROR, "Erreur"),
        ):
            btn = ctk.CTkButton(
                bar,
                text=label,
                font=FONTS["small"],
                fg_color=(
                    COLORS["accent"]
                    if key == self._current_filter
                    else COLORS["border"]
                ),
                hover_color=COLORS["accent_hover"],
                text_color=COLORS["text"],
                height=28,
                width=110,
                corner_radius=6,
                command=lambda k=key: self.set_filter(k),
            )
            btn.pack(side="left", padx=4)
            self._filter_buttons[key] = btn

    def _create_sessions_panel(self) -> None:
        """Zone scrollable des cartes session."""
        self._sessions_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
        )
        self._sessions_frame.grid(
            row=3, column=0, sticky="nsew", padx=20, pady=(0, 20)
        )

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Recharge depuis HistoryManager et re-rend la liste."""
        try:
            self._sessions = self._load_sessions()
        except Exception as e:  # noqa: BLE001 — la GUI ne doit pas crasher
            logger.warning("PilotHistoryPage: chargement sessions echoue : %s", e)
            self._sessions = []

        self._stats = _compute_stats(self._sessions, now=self._clock())
        self._render_stats()
        self._render_sessions()

    def set_filter(self, filter_key: str) -> None:
        """Change le filtre courant et re-render la liste."""
        if filter_key not in _FILTER_TO_STATUSES:
            return
        self._current_filter = filter_key
        # Re-style les boutons
        for key, btn in self._filter_buttons.items():
            with contextlib.suppress(Exception):
                btn.configure(
                    fg_color=(
                        COLORS["accent"]
                        if key == self._current_filter
                        else COLORS["border"]
                    )
                )
        self._render_sessions()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_sessions(self) -> list[PilotSession]:
        """Charge les HistoryEntry Pilot et agrege en sessions."""
        history = self._history_factory()
        try:
            entries = history.get_history(
                module_name=PILOT_MODULE_NAME,
                limit=self._max_entries,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("PilotHistoryPage: get_history echec : %s", e)
            return []

        # `get_history` retourne ORDER BY timestamp DESC — on retri ascendant
        # avant l'agregation pour reconstruire la chronologie.
        return aggregate_sessions(entries, gap_seconds=self._gap_seconds)

    def _render_stats(self) -> None:
        """Met a jour le bandeau de stats."""
        s = self._stats
        rate_pct = int(round(s.get("completion_rate", 0.0) * 100))
        cost_text = (
            f" Cout total : {s.get('cost_total_eur', 0.0):.4f} EUR"
            if s.get("cost_known")
            else " Cout total : N/A (logs sans metadata cost)"
        )

        text = (
            f"Sessions ce mois : {s.get('sessions_this_month', 0)}    "
            f"Terminees : {s.get('sessions_completed', 0)}    "
            f"Taux de completion : {rate_pct}%{cost_text}"
        )
        with contextlib.suppress(Exception):
            self._stats_label.configure(text=text)

    def _render_sessions(self) -> None:
        """Re-render la liste en fonction du filtre courant."""
        # Nettoie
        try:
            for child in list(self._sessions_frame.winfo_children()):
                child.destroy()
        except Exception:  # noqa: BLE001
            pass

        if not self._sessions:
            ctk.CTkLabel(
                self._sessions_frame,
                text="Aucune session Pilot enregistree.",
                font=FONTS["body"],
                text_color=COLORS["text_muted"],
                wraplength=600,
                justify="center",
            ).pack(pady=40)
            return

        accepted = _FILTER_TO_STATUSES.get(self._current_filter, set())
        filtered = [s for s in self._sessions if s.status in accepted]

        if not filtered:
            ctk.CTkLabel(
                self._sessions_frame,
                text=f"Aucune session avec le filtre '{self._current_filter}'.",
                font=FONTS["body"],
                text_color=COLORS["text_muted"],
                wraplength=600,
                justify="center",
            ).pack(pady=30)
            return

        for session in filtered:
            PilotSessionCard(
                self._sessions_frame,
                session,
                on_open_screenshot=self._open_screenshot,
            )

    def _open_screenshot(self, path: str) -> None:
        """Wrapper protege autour du screenshot opener."""
        if not path:
            return
        try:
            self._screenshot_opener(path)
        except Exception as e:  # noqa: BLE001
            logger.warning("PilotHistoryPage: open screenshot %r echec : %s", path, e)


# ---------------------------------------------------------------------------
# Default screenshot opener
# ---------------------------------------------------------------------------


def _default_screenshot_opener(path: str) -> None:
    """Ouvre un fichier dans la visionneuse par defaut (Windows : os.startfile).

    Sur Linux/macOS, retombe sur xdg-open / open via subprocess (best-effort).
    """
    if not path:
        return
    p = Path(path)
    if not p.exists():
        logger.info("PilotHistoryPage: screenshot inexistant %r", path)
        return

    # Windows
    startfile = getattr(os, "startfile", None)
    if callable(startfile):
        startfile(str(p))  # type: ignore[misc]
        return

    # POSIX fallback (best-effort)
    import subprocess
    import sys

    cmd = ["xdg-open"] if sys.platform.startswith("linux") else ["open"]
    with contextlib.suppress(Exception):
        subprocess.Popen([*cmd, str(p)])  # noqa: S603 — utility opener


if __name__ == "__main__":  # pragma: no cover
    print("PilotHistoryPage module loaded.")
