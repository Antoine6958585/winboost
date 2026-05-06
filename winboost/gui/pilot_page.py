"""Pilot Page — Onglet GUI pour AnthropicPilot Computer Use (Phase 13 v2.3).

Architecture
------------

`PilotPage(ctk.CTkFrame)` expose un onglet visible UNIQUEMENT si :
- profile == "lab" (Lab Mode active dans Settings)
- pilot.rgpd.{screenshots, ocr_text, system_info} == True

Sinon : message d'erreur clair + bouton "Aller dans Settings".

Composants principaux
---------------------

1. **TkConfirmer** : implementation Tk de `ConfirmCallback` (cf.
   `winboost/pilot/confirmation_ui.py`). Le pilot tournant dans un thread
   appelle `confirmer.ask(action, screenshot)` qui bloque le thread du pilot
   et signale le main thread Tk via `Event` + `self.after()`. La GUI affiche
   les boutons (Confirmer / Skip / Cancel / Allow next 5) ; la decision
   revient au thread du pilot via la queue.

2. **PilotPage._launch_pilot** : lance `AnthropicPilot.run(query)` dans un
   thread daemon. Les iterations sont publiees au main thread Tk via
   `self.after(0, ...)`.

3. **Esc binding** : `self.bind_all("<Escape>", ...)` arrete globalement.

4. **Budget tracker** : label "Budget restant : X EUR / Y EUR" mis a jour
   apres chaque action.

5. **Activity feed** : liste verticale d'iterations avec rationale,
   action proposee, screenshot annote, boutons inline.

Decisions UX
------------

- **Threading impose** : le loop pilot peut durer plusieurs minutes, on ne
  peut pas bloquer Tk.
- **Confirmation modale par iteration** : pas de "trust me" — chaque action
  doit etre confirmee (ou batch de 5).
- **Esc global** : arret immediat, sortie propre du loop.
- **Pas de re-tentative en cas d'echec** : le user clique "Re-lancer" pour
  recommencer une session.
- **Lazy injection** : `screenshot_provider` et `action_executor` sont
  cherches dans `winboost.pilot.screenshot_provider` / `.action_executor`
  via try/except (modules optionnels). Si absents, message clair.

Tests
-----

Le module est ecrit pour etre testable sans GUI reelle (cf.
`tests/test_gui/test_pilot_page.py`). Les widgets Tk sont mockes via
`MagicMock` + `patch.object(__init__)`. `make_tk_confirmer()` est testable
isolement.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import customtkinter as ctk

from winboost.gui.theme import COLORS, FONTS

# Imports du backend pilot — tolerants en cas de modules optionnels manquants.
try:
    from winboost.pilot.anthropic_pilot import (
        AnthropicPilot,
        BYOKMissingError,
        PilotError,
        ProfileNotLabError,
        RGPDNotAcceptedError,
    )
    from winboost.pilot.budget import BudgetExceededError, BudgetManager
    from winboost.pilot.confirmation_ui import (
        ConfirmationDecision,
        ConfirmationManager,
        ProposedAction,
    )
    from winboost.pilot.sandbox import Region, Sandbox
    PILOT_BACKEND_AVAILABLE = True
except ImportError:  # pragma: no cover - module pilot optionnel
    AnthropicPilot = None  # type: ignore[assignment,misc]
    BYOKMissingError = RuntimeError  # type: ignore[assignment,misc]
    PilotError = RuntimeError  # type: ignore[assignment,misc]
    ProfileNotLabError = RuntimeError  # type: ignore[assignment,misc]
    RGPDNotAcceptedError = RuntimeError  # type: ignore[assignment,misc]
    BudgetExceededError = RuntimeError  # type: ignore[assignment,misc]
    BudgetManager = None  # type: ignore[assignment,misc]
    ConfirmationDecision = str  # type: ignore[assignment,misc]
    ConfirmationManager = None  # type: ignore[assignment,misc]
    ProposedAction = None  # type: ignore[assignment,misc]
    Sandbox = None  # type: ignore[assignment,misc]
    Region = None  # type: ignore[assignment,misc]
    PILOT_BACKEND_AVAILABLE = False

# Providers concrets injectes par T080 (ecrits par l'autre agent en parallele).
# Si absent, message clair dans la GUI.
try:
    from winboost.pilot.screenshot_provider import (
        make_screenshot_provider,  # type: ignore[import-not-found]
    )
except ImportError:  # pragma: no cover
    make_screenshot_provider = None  # type: ignore[assignment]

try:
    from winboost.pilot.action_executor import (
        make_action_executor,  # type: ignore[import-not-found]
    )
except ImportError:  # pragma: no cover
    make_action_executor = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

__all__ = [
    "PilotPage",
    "TkConfirmer",
    "make_tk_confirmer",
    "PILOT_RGPD_KEYS",
]

PILOT_RGPD_KEYS: tuple[str, ...] = ("screenshots", "ocr_text", "system_info")


# ---------------------------------------------------------------------------
# TkConfirmer — implementation Tk de ConfirmCallback
# ---------------------------------------------------------------------------


class TkConfirmer:
    """Confirmer Tk-based : bloque le thread pilot et delegue au main thread.

    Le Pilot tourne dans un thread separe. Quand il propose une action, il
    appelle `self.__call__(action, screenshot)` ce qui :
    1. Place une demande dans la `request_queue`.
    2. Signale le main thread Tk via `self.after(0, ...)` qui affiche les
       boutons.
    3. Bloque sur `decision_event` jusqu'a ce que le main thread depose la
       decision dans `decision_queue`.
    4. Retourne la decision au pilot.

    Args:
        ui_callback: callable appele depuis le thread Tk pour afficher
            l'iteration (action + screenshot) et collecter la decision via
            les boutons.
        scheduler: callable `(delay_ms, fn, *args)` pour programmer une
            execution sur le main thread Tk. Default : `tk_root.after`.
            Permet de scheduler les callbacks UI depuis le thread du pilot.
        timeout_seconds: timeout maximum d'attente d'une decision utilisateur.
            Default 600s (10 min). Si depasse, retourne 'cancel' par defense.
    """

    def __init__(
        self,
        ui_callback: Callable[[Any, bytes, Callable[[str], None]], None],
        scheduler: Callable[..., None],
        timeout_seconds: float = 600.0,
    ) -> None:
        self._ui_callback = ui_callback
        self._scheduler = scheduler
        self._timeout_seconds = float(timeout_seconds)
        self._decision_queue: queue.Queue[str] = queue.Queue()
        self._cancelled = False

    def cancel_all(self) -> None:
        """Marque toutes les futures demandes comme cancellees (Esc global)."""
        self._cancelled = True
        with contextlib.suppress(Exception):
            self._decision_queue.put_nowait("cancel")

    def __call__(
        self,
        action: Any,  # ProposedAction (typage souple)
        screenshot: bytes | Path,
    ) -> str:
        """Bloque le thread pilot jusqu'a ce que l'user decide via les boutons."""
        if self._cancelled:
            return "cancel"

        # Schedule l'affichage des boutons dans le main thread Tk
        # On normalise le screenshot en bytes pour l'UI
        shot_bytes: bytes
        if isinstance(screenshot, bytes):
            shot_bytes = screenshot
        elif isinstance(screenshot, Path):
            try:
                shot_bytes = screenshot.read_bytes()
            except OSError:
                shot_bytes = b""
        else:
            shot_bytes = b""

        def _resolve(decision: str) -> None:
            """Callback UI -> queue (appele depuis main thread Tk)."""
            with contextlib.suppress(Exception):
                self._decision_queue.put_nowait(decision)

        # Schedule le callback UI sur le main thread
        try:
            self._scheduler(0, self._ui_callback, action, shot_bytes, _resolve)
        except Exception as e:  # noqa: BLE001
            logger.warning("TkConfirmer scheduler failed: %s", e)
            return "cancel"

        # Bloque jusqu'a la decision (avec timeout par securite)
        try:
            decision = self._decision_queue.get(timeout=self._timeout_seconds)
        except queue.Empty:
            logger.warning("TkConfirmer: timeout sans decision utilisateur")
            return "cancel"

        # Validation
        if decision not in {"confirm", "cancel", "skip", "allow_batch"}:
            logger.warning("TkConfirmer: decision invalide %r -> cancel", decision)
            return "cancel"
        return decision


def make_tk_confirmer(
    ui_callback: Callable[[Any, bytes, Callable[[str], None]], None],
    scheduler: Callable[..., None],
    timeout_seconds: float = 600.0,
) -> TkConfirmer:
    """Factory pour TkConfirmer (compatible signature `ConfirmCallback`)."""
    return TkConfirmer(
        ui_callback=ui_callback,
        scheduler=scheduler,
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# IterationCard — affiche une iteration du pilot (rationale + screenshot + actions)
# ---------------------------------------------------------------------------


class IterationCard(ctk.CTkFrame):
    """Carte visuelle pour une iteration du loop pilot.

    Affiche :
    - Header : numero d'iteration + label action (ex: 'click(456, 234)')
    - Rationale en dessous
    - Screenshot annote (si fourni)
    - Boutons : Confirmer / Skip / Cancel / Allow next 5
    Apres decision : badge resultat + boutons desactives.
    """

    def __init__(
        self,
        parent: Any,
        iteration_num: int,
        action: Any,
        screenshot_bytes: bytes,
        on_decision: Callable[[str], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=10, **kwargs)
        self.pack(fill="x", padx=4, pady=6)

        self._iteration_num = iteration_num
        self._action = action
        self._screenshot_bytes = screenshot_bytes
        self._on_decision = on_decision
        self._decided = False
        self._screenshot_label: ctk.CTkLabel | None = None
        self._buttons_frame: ctk.CTkFrame | None = None

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(
            header,
            text=f"Iteration {iteration_num}",
            font=FONTS["subheading"],
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(side="left")

        action_label = self._format_action_label(action)
        ctk.CTkLabel(
            header,
            text=action_label,
            font=FONTS["mono"],
            text_color=COLORS["text"],
            anchor="e",
        ).pack(side="right")

        # Rationale (texte explicite Claude)
        rationale = getattr(action, "rationale", "") or "(pas de rationale)"
        ctk.CTkLabel(
            self,
            text=rationale,
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            wraplength=720,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 6))

        # Screenshot (best-effort - si Pillow + Tk dispo)
        if screenshot_bytes:
            self._render_screenshot(screenshot_bytes)

        # Boutons inline
        self._buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._buttons_frame.pack(fill="x", padx=10, pady=(2, 10))

        self._confirm_btn = self._make_button(
            "Confirmer", COLORS["success"], "confirm",
        )
        self._skip_btn = self._make_button(
            "Skip", COLORS["info"], "skip",
        )
        self._cancel_btn = self._make_button(
            "Cancel", COLORS["error"], "cancel",
        )
        self._batch_btn = self._make_button(
            "Allow next 5", COLORS["warning"], "allow_batch",
        )

    def _format_action_label(self, action: Any) -> str:
        """Format court de l'action pour le header."""
        try:
            short = action.short_label()
            return str(short)
        except Exception:  # noqa: BLE001
            kind = getattr(action, "kind", "?")
            return f"action({kind})"

    def _render_screenshot(self, data: bytes) -> None:
        """Rendu best-effort du screenshot via Pillow + CTkImage."""
        try:
            from io import BytesIO

            from PIL import Image  # type: ignore[import-not-found]
        except ImportError:
            return

        try:
            img = Image.open(BytesIO(data)).convert("RGB")
        except Exception as e:  # noqa: BLE001
            logger.debug("PilotPage: screenshot non rendu (decode error: %s)", e)
            return

        # Resize pour ne pas exploser la fenetre — max 600x300 keep ratio
        max_w, max_h = 600, 300
        w, h = img.size
        if w > max_w or h > max_h:
            ratio = min(max_w / w, max_h / h)
            img = img.resize((int(w * ratio), int(h * ratio)))

        try:
            tk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception as e:  # noqa: BLE001
            logger.debug("PilotPage: CTkImage failed: %s", e)
            return

        self._screenshot_label = ctk.CTkLabel(
            self,
            image=tk_img,
            text="",
        )
        self._screenshot_label.pack(padx=10, pady=(0, 6))

    def _make_button(self, label: str, color: str, decision: str) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            self._buttons_frame,
            text=label,
            font=FONTS["small"],
            fg_color=color,
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            height=28,
            width=110,
            corner_radius=6,
            command=lambda d=decision: self._handle_decision(d),
        )
        btn.pack(side="left", padx=4)
        return btn

    def _handle_decision(self, decision: str) -> None:
        """Click sur un bouton -> callback parent + UI lock."""
        if self._decided:
            return
        self._decided = True
        # Desactive tous les boutons
        for btn in (self._confirm_btn, self._skip_btn, self._cancel_btn, self._batch_btn):
            with contextlib.suppress(Exception):
                btn.configure(state="disabled")
        # Affiche badge
        color_map = {
            "confirm": COLORS["success"],
            "skip": COLORS["info"],
            "cancel": COLORS["error"],
            "allow_batch": COLORS["warning"],
        }
        ctk.CTkLabel(
            self,
            text=f"  Decision : {decision.upper()}",
            font=FONTS["small"],
            text_color="#ffffff",
            fg_color=color_map.get(decision, COLORS["text_muted"]),
            corner_radius=6,
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 8))

        # Callback parent (-> TkConfirmer queue)
        try:
            self._on_decision(decision)
        except Exception as e:  # noqa: BLE001
            logger.warning("PilotPage: on_decision failed: %s", e)


# ---------------------------------------------------------------------------
# PilotPage — page principale
# ---------------------------------------------------------------------------


class PilotPage(ctk.CTkFrame):
    """Onglet "Pilot" — visible uniquement si Lab Mode + RGPD OK.

    Args:
        parent: widget Tk parent.
        config: Config WinBoost (lecture profile + pilot.* settings).
        pilot_factory: factory pour AnthropicPilot (injectable pour tests).
        on_open_settings: callback invoque quand l'user clique
            "Aller dans Settings".
    """

    def __init__(
        self,
        parent: Any,
        config: Any = None,
        pilot_factory: Callable[..., Any] | None = None,
        on_open_settings: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self._config = config
        self._pilot_factory = pilot_factory or _default_pilot_factory
        self._on_open_settings = on_open_settings

        # Etat interne
        self._pilot_thread: threading.Thread | None = None
        self._is_running = False
        self._pilot_instance: Any = None
        self._tk_confirmer: TkConfirmer | None = None
        self._iteration_counter = 0
        self._budget_label: ctk.CTkLabel | None = None
        self._activity_frame: ctk.CTkScrollableFrame | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Detecte si on a le droit d'afficher la vraie UI
        if self._can_show_full_ui():
            self._build_full_ui()
        else:
            self._build_placeholder_ui()

    # ------------------------------------------------------------------
    # Gating
    # ------------------------------------------------------------------

    def _can_show_full_ui(self) -> bool:
        """True si profile == 'lab' + RGPD complet."""
        if self._config is None:
            return False
        profile = self._config.get("profile", "safe")
        if profile != "lab":
            return False
        pilot_cfg = self._config.get("pilot", {}) or {}
        rgpd = pilot_cfg.get("rgpd", {}) or {}
        return all(rgpd.get(k, False) for k in PILOT_RGPD_KEYS)

    def _gating_reason(self) -> str:
        """Retourne un message court expliquant pourquoi le Pilot est cache."""
        if self._config is None:
            return "Configuration absente."
        profile = self._config.get("profile", "safe")
        if profile != "lab":
            return (
                "Le Pilot est reserve au profil 'lab' (mode experimental). "
                "Active le Lab Mode dans Settings pour debloquer cet onglet."
            )
        pilot_cfg = self._config.get("pilot", {}) or {}
        rgpd = pilot_cfg.get("rgpd", {}) or {}
        missing = [k for k in PILOT_RGPD_KEYS if not rgpd.get(k, False)]
        if missing:
            return (
                f"Opt-in RGPD incomplet (manquant : {', '.join(missing)}). "
                "Coche les 3 cases dans Settings -> Lab Mode et confirme."
            )
        return "Pre-requis non satisfaits."

    # ------------------------------------------------------------------
    # UI placeholder (Lab Mode pas active)
    # ------------------------------------------------------------------

    def _build_placeholder_ui(self) -> None:
        """Affichage minimaliste quand le Pilot n'est pas debloque."""
        wrapper = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        wrapper.grid(row=0, column=0, padx=40, pady=40, sticky="nsew")

        ctk.CTkLabel(
            wrapper,
            text="Pilot Anthropic",
            font=FONTS["title"],
            text_color=COLORS["accent"],
        ).pack(pady=(40, 10))

        ctk.CTkLabel(
            wrapper,
            text="Mode Lab requis",
            font=FONTS["heading"],
            text_color=COLORS["warning"],
        ).pack(pady=(0, 20))

        ctk.CTkLabel(
            wrapper,
            text=self._gating_reason(),
            font=FONTS["body"],
            text_color=COLORS["text"],
            wraplength=600,
            justify="center",
        ).pack(padx=30, pady=(0, 30))

        ctk.CTkButton(
            wrapper,
            text="Aller dans Settings",
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            height=40,
            width=200,
            corner_radius=8,
            command=self._handle_open_settings,
        ).pack(pady=(0, 40))

    def _handle_open_settings(self) -> None:
        if self._on_open_settings is not None:
            try:
                self._on_open_settings()
            except Exception as e:  # noqa: BLE001
                logger.warning("PilotPage: on_open_settings failed: %s", e)

    # ------------------------------------------------------------------
    # UI complete (Lab Mode + RGPD OK)
    # ------------------------------------------------------------------

    def _build_full_ui(self) -> None:
        """Construit l'UI complete : input + activity feed + budget tracker."""
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_input_area()
        self._build_activity_area()

        # Esc binding global pour cancel
        with contextlib.suppress(Exception):
            self.bind_all("<Escape>", self._on_escape_key)

    def _build_header(self) -> None:
        """Header avec titre + sous-titre."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 10))

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x")

        ctk.CTkLabel(
            title_row,
            text="Pilot Anthropic - Mode Lab",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        # Budget tracker (mis a jour en temps reel)
        self._budget_label = ctk.CTkLabel(
            title_row,
            text=self._format_budget_text(),
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="e",
        )
        self._budget_label.pack(side="right")

        ctk.CTkLabel(
            header,
            text=(
                "Decris ce que tu veux faire. Claude propose chaque clic, "
                "tu confirmes avant execution. Esc a tout moment = arret."
            ),
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

    def _build_input_area(self) -> None:
        """Zone de saisie multi-line + bouton 'Lancer'."""
        wrapper = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        wrapper.grid(row=1, column=0, sticky="ew", padx=25, pady=(0, 10))
        wrapper.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            wrapper,
            text="Que veux-tu faire ?",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        self.input_textbox = ctk.CTkTextbox(
            wrapper,
            font=FONTS["body"],
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            height=80,
            corner_radius=8,
        )
        self.input_textbox.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkLabel(
            wrapper,
            text=(
                "Exemples : 'trouve pourquoi mon imprimante ne marche pas', "
                "'configure 2 ecrans en miroir'."
            ),
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
            wraplength=900,
            justify="left",
        ).pack(fill="x", padx=12, pady=(0, 6))

        # Bouton lancer + status inline
        action_row = ctk.CTkFrame(wrapper, fg_color="transparent")
        action_row.pack(fill="x", padx=12, pady=(0, 10))

        self.run_btn = ctk.CTkButton(
            action_row,
            text="Lancer le Pilot",
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            height=40,
            width=180,
            corner_radius=8,
            command=self._on_run_click,
        )
        self.run_btn.pack(side="left")

        self._error_label = ctk.CTkLabel(
            action_row,
            text="",
            font=FONTS["small"],
            text_color=COLORS["error"],
            anchor="w",
        )
        self._error_label.pack(side="left", padx=(10, 0), fill="x", expand=True)

    def _build_activity_area(self) -> None:
        """Zone scrollable avec les iterations du pilot."""
        ctk.CTkLabel(
            self,
            text="Activite",
            font=FONTS["heading"],
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=2, column=0, sticky="new", padx=25, pady=(0, 4))

        self._activity_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
        )
        self._activity_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.grid_rowconfigure(3, weight=1)

        # Placeholder
        self._activity_placeholder = ctk.CTkLabel(
            self._activity_frame,
            text=(
                "Pret. Decris ce que tu veux faire et clique 'Lancer le "
                "Pilot'. Chaque iteration s'affichera ici avec un screenshot "
                "annote et des boutons Confirmer / Skip / Cancel."
            ),
            font=FONTS["body"],
            text_color=COLORS["text_muted"],
            wraplength=700,
            justify="center",
        )
        self._activity_placeholder.pack(pady=40)

    # ------------------------------------------------------------------
    # Run handlers
    # ------------------------------------------------------------------

    def _format_budget_text(self) -> str:
        """Recupere le budget courant via BudgetManager (best-effort)."""
        if BudgetManager is None:
            return "Budget : (module pilot non installe)"
        try:
            pilot_cfg = (self._config.get("pilot", {}) or {}) if self._config else {}
            limit = float(pilot_cfg.get("budget_eur", 5.0))
            mgr = BudgetManager(limit_eur=limit)
            remaining = mgr.remaining_eur
            return f"Budget restant : {remaining:.2f} EUR / {limit:.2f} EUR"
        except Exception as e:  # noqa: BLE001
            logger.debug("PilotPage: budget read failed: %s", e)
            return "Budget : (lecture echouee)"

    def _refresh_budget_label(self) -> None:
        if self._budget_label is None:
            return
        with contextlib.suppress(Exception):
            self._budget_label.configure(text=self._format_budget_text())

    def _on_run_click(self) -> None:
        """Click sur 'Lancer le Pilot'."""
        if self._is_running:
            return

        if not PILOT_BACKEND_AVAILABLE or AnthropicPilot is None:
            self._show_error(
                "Module pilot non installe. pip install winboost[pilot]"
            )
            return

        prompt = self.input_textbox.get("1.0", "end").strip()
        if not prompt:
            self._show_error("Decris ce que tu veux faire avant de lancer.")
            return

        self._hide_error()
        self._launch_pilot(prompt)

    def _show_error(self, text: str) -> None:
        with contextlib.suppress(Exception):
            self._error_label.configure(text=text)

    def _hide_error(self) -> None:
        with contextlib.suppress(Exception):
            self._error_label.configure(text="")

    def _launch_pilot(self, prompt: str) -> None:
        """Demarre le pilot dans un thread separe."""
        self._is_running = True
        self._iteration_counter = 0

        try:
            self.run_btn.configure(state="disabled", text="Pilot en cours...")
            self.input_textbox.configure(state="disabled")
        except Exception:  # noqa: BLE001
            pass

        # Reset activity
        if self._activity_frame is not None:
            try:
                for child in list(self._activity_frame.winfo_children()):
                    child.destroy()
            except Exception:  # noqa: BLE001
                pass

        # TkConfirmer : bridge thread pilot <-> main thread Tk
        self._tk_confirmer = make_tk_confirmer(
            ui_callback=self._show_iteration_card,
            scheduler=self.after,
        )

        # Thread worker
        self._pilot_thread = threading.Thread(
            target=self._pilot_worker,
            args=(prompt,),
            daemon=True,
        )
        self._pilot_thread.start()

    def _pilot_worker(self, prompt: str) -> None:
        """Worker thread : construit le pilot et execute run().

        Toutes les exceptions sont rattrapees et envoyees au main thread Tk
        via `after(0, ...)` — la GUI ne doit jamais crasher.
        """
        try:
            pilot = self._build_pilot(self._tk_confirmer)
            self._pilot_instance = pilot
            result = pilot.run(prompt)
            self.after(0, self._on_pilot_completed, result)
        except BYOKMissingError as e:
            self.after(0, self._on_pilot_error, "BYOK manquant", str(e))
        except ProfileNotLabError as e:
            self.after(0, self._on_pilot_error, "Profil non Lab", str(e))
        except RGPDNotAcceptedError as e:
            self.after(0, self._on_pilot_error, "RGPD non accepte", str(e))
        except BudgetExceededError as e:
            self.after(0, self._on_pilot_error, "Budget depasse", str(e))
        except PilotError as e:
            self.after(0, self._on_pilot_error, "Pilot Error", str(e))
        except Exception as e:  # noqa: BLE001
            self.after(0, self._on_pilot_error, "Erreur inattendue", str(e))

    def _build_pilot(self, confirmer: Any) -> Any:
        """Construit AnthropicPilot avec injections issues de Config."""
        if self._pilot_factory is _default_pilot_factory:
            return _default_pilot_factory(self._config, confirmer)
        return self._pilot_factory(self._config, confirmer)

    # ------------------------------------------------------------------
    # UI callbacks (depuis main thread Tk via after(0, ...))
    # ------------------------------------------------------------------

    def _show_iteration_card(
        self,
        action: Any,
        screenshot_bytes: bytes,
        on_decision: Callable[[str], None],
    ) -> None:
        """Cree une IterationCard pour l'iteration courante (UI thread)."""
        self._iteration_counter += 1
        # Drop placeholder si toujours present
        if self._activity_frame is None:
            return
        try:
            if self._activity_placeholder is not None:
                self._activity_placeholder.pack_forget()
                self._activity_placeholder = None
        except Exception:  # noqa: BLE001
            pass

        try:
            IterationCard(
                self._activity_frame,
                iteration_num=self._iteration_counter,
                action=action,
                screenshot_bytes=screenshot_bytes,
                on_decision=on_decision,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("PilotPage: IterationCard creation failed: %s", e)
            on_decision("cancel")

        self._refresh_budget_label()

    def _on_pilot_completed(self, result: Any) -> None:
        """Pilot termine normalement (succes ou abort propre)."""
        self._is_running = False
        try:
            self.run_btn.configure(state="normal", text="Lancer le Pilot")
            self.input_textbox.configure(state="normal")
        except Exception:  # noqa: BLE001
            pass

        completed = bool(getattr(result, "completed", False))
        abort_reason = getattr(result, "abort_reason", "")
        actions = getattr(result, "actions", []) or []
        cost_eur = float(getattr(result, "total_cost_eur", 0.0))

        if completed:
            text = (
                f"Pilot termine. {len(actions)} action(s), "
                f"cout total {cost_eur:.4f} EUR."
            )
            color = COLORS["success"]
        else:
            text = (
                f"Pilot arrete : {abort_reason or 'inconnu'}. "
                f"{len(actions)} action(s), cout {cost_eur:.4f} EUR."
            )
            color = COLORS["warning"]

        with contextlib.suppress(Exception):
            ctk.CTkLabel(
                self._activity_frame,
                text=text,
                font=FONTS["body"],
                text_color="#ffffff",
                fg_color=color,
                corner_radius=8,
                wraplength=720,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=4, pady=10)

        self._refresh_budget_label()

    def _on_pilot_error(self, kind: str, message: str) -> None:
        """Pilot a leve une exception (BYOK, RGPD, network...)."""
        self._is_running = False
        try:
            self.run_btn.configure(state="normal", text="Lancer le Pilot")
            self.input_textbox.configure(state="normal")
        except Exception:  # noqa: BLE001
            pass

        with contextlib.suppress(Exception):
            ctk.CTkLabel(
                self._activity_frame,
                text=f"{kind} : {message}",
                font=FONTS["body"],
                text_color="#ffffff",
                fg_color=COLORS["error"],
                corner_radius=8,
                wraplength=720,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=4, pady=10)

    # ------------------------------------------------------------------
    # Cancel global (Esc)
    # ------------------------------------------------------------------

    def _on_escape_key(self, _event: Any = None) -> None:
        """Esc -> stop pilot + cancel queue confirmer."""
        if not self._is_running:
            return
        self._cancel_pilot()

    def _cancel_pilot(self) -> None:
        """Stop pilot + signale cancel a tous les confirmers en attente."""
        if self._pilot_instance is not None:
            with contextlib.suppress(Exception):
                self._pilot_instance.stop()
        if self._tk_confirmer is not None:
            with contextlib.suppress(Exception):
                self._tk_confirmer.cancel_all()


# ---------------------------------------------------------------------------
# Default pilot factory (utilise la config + injecte les providers concrets)
# ---------------------------------------------------------------------------


def _default_pilot_factory(config: Any, confirmer: Any) -> Any:
    """Factory par defaut : construit AnthropicPilot depuis Config.

    Utilise les providers concrets `make_screenshot_provider` /
    `make_action_executor` s'ils sont disponibles. Sinon, le pilot lance
    NotImplementedError au moment du run (et la GUI affiche l'erreur).
    """
    if AnthropicPilot is None:
        raise PilotError(
            "Module pilot non installe. pip install winboost[pilot]"
        )

    pilot_cfg = (config.get("pilot", {}) if config is not None else {}) or {}
    api_key = pilot_cfg.get("api_key", "")
    budget_eur = float(pilot_cfg.get("budget_eur", 5.0))
    sandbox_mode = pilot_cfg.get("sandbox_mode", "winboost_window")

    # Sandbox — region par defaut 1920x1080. Pour 'application' / 'screen_region'
    # un futur enrichissement permettra de choisir la region precise.
    if Region is None or Sandbox is None:
        raise PilotError(
            "Module pilot non installe (Sandbox/Region manquants)."
        )

    # Si le mode est full_screen, on EXIGE allow_full_screen=True (deja
    # confirme par double popup dans Settings).
    region = Region(0, 0, 1920, 1080)
    sandbox = Sandbox(
        mode=sandbox_mode,
        region=region,
        allow_full_screen=(sandbox_mode == "full_screen"),
    )

    if ConfirmationManager is None:
        raise PilotError("ConfirmationManager indisponible.")
    confirmation = ConfirmationManager(confirmer=confirmer)

    if BudgetManager is None:
        raise PilotError("BudgetManager indisponible.")
    budget = BudgetManager(limit_eur=budget_eur)

    # Providers concrets fournis par T080 (parallel agent)
    screenshot_provider = None
    action_executor = None
    if make_screenshot_provider is not None:
        try:
            screenshot_provider = make_screenshot_provider(sandbox)
        except Exception as e:  # noqa: BLE001
            logger.warning("PilotPage: screenshot_provider factory failed: %s", e)
    if make_action_executor is not None:
        try:
            action_executor = make_action_executor(sandbox)
        except Exception as e:  # noqa: BLE001
            logger.warning("PilotPage: action_executor factory failed: %s", e)

    return AnthropicPilot(
        api_key=api_key,
        config=config,
        sandbox=sandbox,
        confirmation=confirmation,
        budget=budget,
        screenshot_provider=screenshot_provider,
        action_executor=action_executor,
    )


# Type alias public pour utilisation externe
PilotPageFactory = Callable[[Any, Any], Any]


# Trace dev-only
if __name__ == "__main__":  # pragma: no cover
    print("PilotPage module loaded.")
    print(f"Backend available: {PILOT_BACKEND_AVAILABLE}")
    print(f"Screenshot provider available: {make_screenshot_provider is not None}")
    print(f"Action executor available: {make_action_executor is not None}")
    # Note : datetime importe pour annotations futures uniquement
    _ = datetime.now(tz=UTC)
