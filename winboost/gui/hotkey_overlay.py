"""Hotkey Overlay — overlay global Ctrl+Alt+Espace pour requete texte rapide (T065).

Composant invocable n'importe ou sur Windows via Ctrl+Alt+Espace :
- Mini-fenetre semi-transparente centree sur l'ecran principal
- Champ de saisie focus auto, placeholder explicite
- Soumission Enter -> ActionRouter.route() -> affichage des actions inline
- Esc, click hors zone ou perte de focus -> fermeture sans action
- Re-pression du hotkey pendant overlay ouvert -> re-focus du champ (idempotent)

Choix techniques :
- Tk pur (pas CustomTkinter) : besoin natif de wm_attributes("-alpha") + always-on-top
  + overrideredirect, plus simple et plus leger pour un overlay minimal. Pas de
  conflit avec la mainloop CustomTkinter de la fenetre principale puisque
  l'overlay est lance dans un process autonome (commande `winboost overlay`).
- Package `keyboard` pour le hotkey global Windows. Peut requerir admin sur
  certaines configs ; on wrap dans try/except pour fallback propre vers le
  raccourci GUI existant (bouton Chat dans la sidebar).

Validation manuelle obligatoire : le hotkey global ne peut pas etre teste en CI
(pas d'evenement clavier reel). Tests unitaires : tous mockes (keyboard, Tk,
ActionRouter). Test in-vivo : `winboost overlay` puis Ctrl+Alt+Espace.
"""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from winboost.ai.action_router import ActionRouter, RouteResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes visuelles (alignees sur winboost.gui.theme mais dupliquees ici
# pour eviter d'importer customtkinter dans un overlay Tk pur)
# ---------------------------------------------------------------------------

OVERLAY_WIDTH = 500
OVERLAY_HEIGHT = 100
OVERLAY_ALPHA = 0.92

BG_COLOR = "#16213e"
INPUT_BG = "#1a1a2e"
TEXT_COLOR = "#ffffff"
TEXT_MUTED = "#a0a0b0"
ACCENT_COLOR = "#e94560"
BORDER_COLOR = "#2a2a4a"

RISK_COLORS = {
    "info": "#3498db",
    "low": "#2ecc71",
    "medium": "#f39c12",
    "high": "#e67e22",
    "critical": "#e74c3c",
}

# Hotkey reconnu par le package `keyboard`
HOTKEY_COMBO = "ctrl+alt+space"

# Nombre maximum d'actions affichees dans l'overlay (UI minimale)
MAX_ACTIONS_DISPLAYED = 3

PLACEHOLDER_TEXT = "Comment puis-je t'aider ?"


class HotkeyOverlay:
    """Overlay Tk minimal active par Ctrl+Alt+Espace.

    Cycle de vie :
    1. `start_listener()` enregistre le hotkey global via `keyboard.add_hotkey`.
       Si l'enregistrement echoue (admin requis, package indisponible), un
       warning est logge et le composant reste utilisable via `show()` direct
       (par exemple depuis un bouton GUI).
    2. La pression du hotkey appelle `show()` qui cree (ou refocus) la fenetre.
    3. La soumission appelle `router.route(query)` puis remplit la zone de
       resultats.
    4. `hide()` detruit la fenetre proprement et libere la reference Tk.
    5. `stop_listener()` est appele a la fermeture de l'application pour
       desenregistrer le hotkey (sinon Windows garde le binding orphelin).
    """

    def __init__(self, router: ActionRouter) -> None:
        """Initialise l'overlay avec un ActionRouter deja construit."""
        self._router = router
        self._window: tk.Toplevel | tk.Tk | None = None
        self._entry: tk.Entry | None = None
        self._results_frame: tk.Frame | None = None
        self._listener_registered = False
        self._hotkey_handle: Any = None  # opaque handle keyboard
        # Root cache pour creer le Toplevel sans avoir de mainloop visible.
        # On le garde withdrawn ; `show()` cree un Toplevel enfant.
        self._root: tk.Tk | None = None

    # ------------------------------------------------------------------
    # Listener global
    # ------------------------------------------------------------------

    def start_listener(self) -> bool:
        """Enregistre le hotkey global Ctrl+Alt+Espace.

        Returns:
            True si l'enregistrement a reussi, False sinon (fallback GUI).
        """
        if self._listener_registered:
            return True

        try:
            import keyboard  # import differe : peut lever ImportError
        except ImportError as exc:
            logger.warning(
                "Package 'keyboard' indisponible (%s). Fallback : utilise le "
                "bouton Chat de la GUI principale.",
                exc,
            )
            return False

        try:
            self._hotkey_handle = keyboard.add_hotkey(HOTKEY_COMBO, self._on_hotkey)
        except (OSError, ValueError) as exc:
            # OSError : sur Windows, droits admin requis pour le hook bas-niveau
            # ValueError : combo de touche non reconnu (peu probable mais defensif)
            logger.warning(
                "Impossible d'enregistrer le hotkey '%s' (%s). Fallback : "
                "utilise le bouton Chat de la GUI principale ou relance en "
                "administrateur.",
                HOTKEY_COMBO,
                exc,
            )
            return False

        self._listener_registered = True
        logger.info("Hotkey '%s' enregistre.", HOTKEY_COMBO)
        return True

    def stop_listener(self) -> None:
        """Desenregistre le hotkey global. Idempotent."""
        if not self._listener_registered:
            return

        try:
            import keyboard

            keyboard.remove_hotkey(self._hotkey_handle)
        except Exception as exc:  # noqa: BLE001 — desenregistrement best-effort
            logger.warning("Erreur a la desinstallation du hotkey : %s", exc)

        self._listener_registered = False
        self._hotkey_handle = None

    def _on_hotkey(self) -> None:
        """Callback du package `keyboard` (thread separe).

        Schedule `show()` sur le thread Tk via `after(0)` pour eviter les
        problemes de thread-safety (Tk n'aime pas etre touche depuis ailleurs
        que son main loop).
        """
        if self._root is not None:
            self._root.after(0, self.show)
        else:
            # Cas premier appel : pas encore de root, on l'instancie ici.
            self.show()

    # ------------------------------------------------------------------
    # Cycle de vie de la fenetre
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Affiche l'overlay au centre de l'ecran. Idempotent : si deja
        ouvert, refocus le champ texte sans recreer la fenetre."""
        if self._window is not None:
            # Idempotence : on remet le focus sans recreer
            try:
                self._window.deiconify()
                self._window.lift()
                if self._entry is not None:
                    self._entry.focus_set()
            except tk.TclError:
                # La fenetre a ete detruite entre temps : reset et recree
                self._window = None
                self._entry = None
                self._results_frame = None
                self.show()
            return

        # Creation lazy du root Tk (cache pour reuse)
        if self._root is None:
            self._root = tk.Tk()
            self._root.withdraw()  # invisible, sert juste de parent

        self._build_window()

    def hide(self) -> None:
        """Detruit la fenetre overlay (mais conserve le listener actif)."""
        if self._window is None:
            return
        with contextlib.suppress(tk.TclError):
            self._window.destroy()
        self._window = None
        self._entry = None
        self._results_frame = None

    # ------------------------------------------------------------------
    # Construction de la fenetre
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        """Cree la Toplevel transparente et son contenu."""
        assert self._root is not None
        win = tk.Toplevel(self._root)
        self._window = win

        # Configuration fenetre : sans titre, always-on-top, transparent
        win.overrideredirect(True)
        win.configure(bg=BG_COLOR)
        try:
            win.wm_attributes("-alpha", OVERLAY_ALPHA)
            win.wm_attributes("-topmost", True)
        except tk.TclError as exc:  # pragma: no cover — defensif Tk
            logger.warning("Attributs fenetre non supportes : %s", exc)

        # Centrage sur l'ecran principal (gere multi-DPI : winfo_screenwidth/height
        # retourne les dimensions logiques deja ajustees par le DPI Windows).
        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        x = (screen_w - OVERLAY_WIDTH) // 2
        y = (screen_h - OVERLAY_HEIGHT) // 2
        win.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+{x}+{y}")

        # Container principal avec une bordure simple (radius simule via padx)
        container = tk.Frame(
            win,
            bg=BG_COLOR,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        container.pack(fill="both", expand=True, padx=2, pady=2)

        # Champ de saisie
        self._entry = tk.Entry(
            container,
            font=("Segoe UI", 14),
            bg=INPUT_BG,
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,  # couleur du caret
            relief="flat",
            highlightthickness=2,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT_COLOR,
        )
        self._entry.pack(fill="x", padx=12, pady=(12, 6), ipady=8)
        self._set_placeholder()

        # Zone resultats (vide au depart, peuplee a la soumission)
        self._results_frame = tk.Frame(container, bg=BG_COLOR)
        self._results_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Bindings
        self._entry.bind("<Return>", self._on_submit)
        win.bind("<Escape>", lambda _e: self.hide())
        win.bind("<FocusOut>", self._on_focus_out)

        # Force le focus au champ texte (apres une frame pour Windows)
        win.after(50, self._focus_entry)

    def _focus_entry(self) -> None:
        """Force le focus sur le champ texte (helper pour scheduling)."""
        if self._window is None or self._entry is None:
            return
        try:
            self._window.focus_force()
            self._entry.focus_set()
            # Selection de tout le placeholder pour que la frappe le remplace
            self._entry.select_range(0, "end")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Placeholder (Tk natif n'en a pas, on simule)
    # ------------------------------------------------------------------

    def _set_placeholder(self) -> None:
        """Affiche le placeholder en gris dans le champ vide."""
        if self._entry is None:
            return
        self._entry.delete(0, "end")
        self._entry.insert(0, PLACEHOLDER_TEXT)
        self._entry.configure(fg=TEXT_MUTED)
        self._entry.bind("<FocusIn>", self._clear_placeholder, add="+")

    def _clear_placeholder(self, _event: Any = None) -> None:
        """Vide le placeholder a la premiere frappe."""
        if self._entry is None:
            return
        if self._entry.get() == PLACEHOLDER_TEXT:
            self._entry.delete(0, "end")
            self._entry.configure(fg=TEXT_COLOR)

    # ------------------------------------------------------------------
    # Soumission
    # ------------------------------------------------------------------

    def _on_submit(self, _event: Any = None) -> None:
        """Soumet la requete au router et affiche les actions."""
        if self._entry is None:
            return

        query = self._entry.get().strip()
        if not query or query == PLACEHOLDER_TEXT:
            return

        try:
            result = self._router.route(query)
        except Exception as exc:  # noqa: BLE001 — log + affichage utilisateur
            logger.exception("Erreur lors du routage de la requete")
            self._render_error(f"Erreur : {exc}")
            return

        self._render_result(result)

    def _render_result(self, result: RouteResult) -> None:
        """Affiche les actions matchees (3 max) ou un message d'erreur."""
        self._clear_results()

        if not result.has_actions:
            msg = result.message or "Aucune action trouvee pour cette requete."
            self._render_error(msg)
            self._grow_window(extra_height=30)
            return

        # Resize la fenetre pour accueillir les resultats
        actions_to_show = result.actions[:MAX_ACTIONS_DISPLAYED]
        self._grow_window(extra_height=22 + len(actions_to_show) * 26)

        for routed in actions_to_show:
            self._render_action_row(routed)

    def _render_action_row(self, routed: Any) -> None:
        """Affiche une ligne d'action : badge risk + nom."""
        if self._results_frame is None:
            return

        action = routed.action
        risk = action.risk_level
        risk_color = RISK_COLORS.get(risk, RISK_COLORS["info"])

        row = tk.Frame(self._results_frame, bg=BG_COLOR)
        row.pack(fill="x", pady=2)

        # Badge risk (label colore)
        badge = tk.Label(
            row,
            text=f" {risk.upper()} ",
            font=("Segoe UI", 9, "bold"),
            bg=risk_color,
            fg="#ffffff",
            padx=4,
        )
        badge.pack(side="left", padx=(0, 8))

        # Nom de l'action
        tk.Label(
            row,
            text=action.name,
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

    def _render_error(self, message: str) -> None:
        """Affiche un message d'erreur dans la zone resultats."""
        self._clear_results()
        if self._results_frame is None:
            return
        tk.Label(
            self._results_frame,
            text=message,
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg=TEXT_MUTED,
            anchor="w",
            wraplength=OVERLAY_WIDTH - 30,
            justify="left",
        ).pack(fill="x", pady=4)

    def _clear_results(self) -> None:
        """Vide la zone resultats pour un nouveau rendu."""
        if self._results_frame is None:
            return
        for child in self._results_frame.winfo_children():
            child.destroy()

    def _grow_window(self, extra_height: int) -> None:
        """Augmente la hauteur de la fenetre apres affichage des resultats."""
        if self._window is None:
            return
        try:
            new_h = OVERLAY_HEIGHT + max(0, extra_height)
            screen_w = self._window.winfo_screenwidth()
            screen_h = self._window.winfo_screenheight()
            x = (screen_w - OVERLAY_WIDTH) // 2
            y = (screen_h - new_h) // 2
            self._window.geometry(f"{OVERLAY_WIDTH}x{new_h}+{x}+{y}")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Gestion du focus
    # ------------------------------------------------------------------

    def _on_focus_out(self, _event: Any = None) -> None:
        """Ferme l'overlay quand le focus est perdu (click hors zone)."""
        if self._window is None:
            return
        # Petit delai : Windows envoie parfois un FocusOut transitoire pendant
        # le focus_force() initial. On verifie que la fenetre n'a pas le focus.
        self._window.after(150, self._maybe_hide_on_focus_loss)

    def _maybe_hide_on_focus_loss(self) -> None:
        """Verifie si la fenetre a vraiment perdu le focus avant de fermer."""
        if self._window is None:
            return
        try:
            focused = self._window.focus_displayof()
        except tk.TclError:
            focused = None
        # Si aucun widget de l'overlay n'a le focus, on ferme
        if focused is None:
            self.hide()


# ---------------------------------------------------------------------------
# Helper de lancement (utilise par la commande CLI `winboost overlay`)
# ---------------------------------------------------------------------------


def run_overlay_foreground() -> None:
    """Lance l'overlay en mode foreground (bloquant).

    Construit le router avec la config par defaut, demarre le listener, puis
    entre dans la mainloop Tk. Ctrl+C dans la console arrete proprement le
    listener.
    """
    from pathlib import Path

    from winboost.ai.action_router import ActionRouter
    from winboost.core.config import Config

    actions_dir = Path(__file__).parent.parent / "actions"
    router = ActionRouter(config=Config(), actions_dir=actions_dir)
    overlay = HotkeyOverlay(router)

    started = overlay.start_listener()
    if not started:
        print(
            "Hotkey global indisponible (admin requis ou package keyboard absent).\n"
            "Fallback : utilise le bouton Chat dans la GUI principale "
            "(`winboost gui`)."
        )
        return

    print(
        f"WinBoost overlay actif. Presse {HOTKEY_COMBO.replace('+', '+').upper()} "
        "n'importe ou pour invoquer. Ctrl+C pour arreter."
    )

    # On a besoin d'une mainloop Tk pour que `after()` fonctionne, mais le
    # root est withdrawn donc rien ne s'affiche jusqu'au hotkey.
    if overlay._root is None:
        overlay._root = tk.Tk()
        overlay._root.withdraw()

    try:
        overlay._root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        overlay.stop_listener()
