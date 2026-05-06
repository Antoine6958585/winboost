"""Diagnose GUI — Page CustomTkinter du diagnostic systeme (Phase 13 v2.3).

Architecture
------------

`DiagnosePage(ctk.CTkFrame)` expose un onglet complet :

1. Zone de saisie (`CTkEntry`) avec 4 boutons d'exemples cliquables qui
   pre-remplissent la query (mais ne lancent pas le diagnostic — l'utilisateur
   peut adapter avant d'appuyer sur Entree).
2. Bouton "Lancer le diagnostic" qui appelle
   `DiagnosticRunner.run_from_query(query)` dans un **thread** (les checks
   PowerShell prennent 5-10s en cumule, on ne bloque pas l'UI principal).
3. Zone scrollable resultats : header (theme, summary, timestamp) + cartes par
   `CheckResult` (couleur par severity, expand/collapse pour details) + plan
   de fix (steps numerotes, bouton "Appliquer" pour les actions YAML, bouton
   "Manuel" qui ouvre un popup avec instructions completes).
4. "Appliquer" passe par `ActionExecutor.apply()` (Option A v2.3 deja livree)
   et met a jour visuellement le step (badge OK/ERR + message).

Decisions UX
------------

- **Couleurs severity** alignees sur le theme WinBoost
  (`_SEVERITY_COLORS`) : ok=success, warning=warning, error=error,
  critical=#9b59b6. Pas de RISK_COLORS car ici on parle de severite *check*,
  pas de risque *action*.
- **Lazy refresh** : pas de re-scan automatique. L'utilisateur clique sur
  "Re-diagnostiquer" pour relancer apres un fix (verifier l'etat).
- **Threading** : un seul thread worker concurrent ; durant le scan, le
  bouton est `disabled` et porte le label "Diagnostic en cours...". Tout
  retour au thread UI passe par `self.after(0, ...)` pour respecter la
  contrainte mono-thread Tk.
- **Empty query** : on n'expose pas un bouton grise (Tk gere mal la
  reactivite cross-event). On affiche un message d'erreur clair sous la
  zone de saisie quand la query est vide.

Tests
-----

Le module est ecrit pour etre testable sans GUI reelle (cf.
`tests/test_gui/test_diagnose_page.py`) :
- `_run_query_in_thread(query)` est testable independamment (injection
  `_runner_factory` dans le constructeur).
- `_handle_apply_action(action_id, executor=)` accepte un executor injectable.
- Les widgets Tk sont entierement mockables via `patch`.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import customtkinter as ctk

from winboost.diagnose.runner import DiagnosticRunner
from winboost.gui.theme import COLORS, FONTS

# ---------------------------------------------------------------------------
# Couleurs et exemples
# ---------------------------------------------------------------------------

# Mapping severity -> couleur. Cohérent avec le theme WinBoost mais avec un
# magenta dedie pour "critical" (pas de mapping existant).
_SEVERITY_COLORS: dict[str, str] = {
    "ok": "#27ae60",
    "warning": "#f39c12",
    "error": "#e74c3c",
    "critical": "#9b59b6",
}

# Libelles courts par severity (icone-like, sans emoji)
_SEVERITY_BADGES: dict[str, str] = {
    "ok": " OK ",
    "warning": " WARN ",
    "error": " ERROR ",
    "critical": " CRIT ",
}

# Exemples cliquables — couvrent les 5 themes du module diagnose
_EXAMPLES: list[tuple[str, str]] = [
    ("Manette ne marche pas", "ma manette bluetooth bug dans rocket league"),
    ("Internet lent", "internet lent et dns qui rame"),
    ("Son qui coupe", "le son coupe sur mon casque"),
    ("Ecran trop sombre", "luminosite ecran trop basse"),
]


# ---------------------------------------------------------------------------
# CheckResultCard — affiche un check avec couleur par severity
# ---------------------------------------------------------------------------


class CheckResultCard(ctk.CTkFrame):
    """Carte visuelle pour un seul `CheckResult`.

    Affiche :
    - Badge severity (couleur)
    - Nom du check (mono)
    - Message
    - Bouton "Details" qui expand un panel (severity, suggested_actions,
      details bruts)
    """

    def __init__(
        self,
        parent: Any,
        check_result: Any,  # CheckResult (typage souple pour faciliter les mocks)
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=10, **kwargs)
        self.pack(fill="x", padx=4, pady=4)

        self._check = check_result
        self._details_visible = False
        self._details_frame: ctk.CTkFrame | None = None

        severity = getattr(check_result, "severity", "ok")
        sev_color = _SEVERITY_COLORS.get(severity, COLORS["info"])
        sev_badge = _SEVERITY_BADGES.get(severity, f" {severity.upper()} ")

        # Header : badge severity + nom du check
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(
            header,
            text=sev_badge,
            font=("Segoe UI", 10, "bold"),
            text_color="#ffffff",
            fg_color=sev_color,
            corner_radius=4,
            width=70,
            height=22,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            header,
            text=check_result.name,
            font=FONTS["mono"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Message du check
        ctk.CTkLabel(
            self,
            text=check_result.message,
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            wraplength=720,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 4))

        # Bouton details (visible si on a quelque chose a montrer)
        suggested = list(getattr(check_result, "suggested_actions", []) or [])
        details = getattr(check_result, "details", {}) or {}
        if suggested or details:
            ctk.CTkButton(
                self,
                text="Details",
                font=FONTS["small"],
                fg_color=COLORS["border"],
                hover_color=COLORS["bg_sidebar"],
                text_color=COLORS["text"],
                height=24,
                width=80,
                corner_radius=6,
                command=self._toggle_details,
            ).pack(anchor="w", padx=10, pady=(0, 8))
        else:
            # Spacer pour garder une marge inferieure coherente
            ctk.CTkLabel(self, text="", height=4).pack()

    def _toggle_details(self) -> None:
        """Affiche/masque le panel details."""
        if self._details_visible and self._details_frame is not None:
            self._details_frame.destroy()
            self._details_frame = None
            self._details_visible = False
            return

        self._details_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], corner_radius=6)
        self._details_frame.pack(fill="x", padx=10, pady=(0, 8))

        # Suggested actions
        suggested = list(getattr(self._check, "suggested_actions", []) or [])
        if suggested:
            ctk.CTkLabel(
                self._details_frame,
                text="Actions suggerees : " + ", ".join(suggested),
                font=FONTS["mono"],
                text_color=COLORS["accent"],
                wraplength=700,
                anchor="w",
                justify="left",
            ).pack(fill="x", padx=8, pady=(6, 2))

        # Details bruts (1 par ligne)
        details = getattr(self._check, "details", {}) or {}
        if details:
            for key, value in details.items():
                ctk.CTkLabel(
                    self._details_frame,
                    text=f"{key} = {value}",
                    font=FONTS["mono"],
                    text_color=COLORS["text_muted"],
                    wraplength=700,
                    anchor="w",
                    justify="left",
                ).pack(fill="x", padx=8, pady=1)

        # Bottom margin
        ctk.CTkLabel(self._details_frame, text="", height=4).pack()
        self._details_visible = True


# ---------------------------------------------------------------------------
# FixStepCard — affiche un step du recommended_fix_plan
# ---------------------------------------------------------------------------


class FixStepCard(ctk.CTkFrame):
    """Carte visuelle pour un step du `recommended_fix_plan`.

    - Step automatisable (`action_id` defini) : bouton "Appliquer".
    - Step manuel (`manual: True`) : bouton "Voir details" qui ouvre un popup.

    Apres execution :
    - badge OK (vert) / ERR (rouge) ajoute en bas de la carte
    - bouton desactive
    """

    def __init__(
        self,
        parent: Any,
        step: dict[str, Any],
        on_apply: Callable[[str, FixStepCard], None] | None = None,
        on_manual: Callable[[dict[str, Any]], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=10, **kwargs)
        self.pack(fill="x", padx=4, pady=4)

        self._step = step
        self._on_apply = on_apply
        self._on_manual = on_manual
        self._result_label: ctk.CTkLabel | None = None

        step_num = step.get("step", "?")
        action_id = step.get("action_id")
        is_manual = bool(step.get("manual", False)) or action_id is None
        severity = step.get("severity", "warning")

        # Header : numero + badge type
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(
            header,
            text=f"({step_num})",
            font=FONTS["subheading"],
            text_color=COLORS["text_muted"],
            width=40,
        ).pack(side="left", padx=(0, 8))

        # Badge type
        if is_manual:
            badge_text = " MANUEL "
            badge_color = COLORS["warning"]
        else:
            badge_text = " AUTO "
            badge_color = COLORS["success"]

        ctk.CTkLabel(
            header,
            text=badge_text,
            font=("Segoe UI", 10, "bold"),
            text_color="#ffffff",
            fg_color=badge_color,
            corner_radius=4,
            width=70,
            height=22,
        ).pack(side="left", padx=(0, 8))

        # action_id (mono) si dispo, sinon nom du check origine
        identifier = action_id or step.get("from_check", "manual")
        ctk.CTkLabel(
            header,
            text=identifier,
            font=FONTS["mono"],
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Tag severity en haut a droite
        sev_color = _SEVERITY_COLORS.get(severity, COLORS["info"])
        ctk.CTkLabel(
            header,
            text=severity.upper(),
            font=FONTS["small"],
            text_color=sev_color,
        ).pack(side="right")

        # Description (texte du step)
        ctk.CTkLabel(
            self,
            text=step.get("description", ""),
            font=FONTS["body"],
            text_color=COLORS["text"],
            wraplength=720,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 6))

        # Boutons inline
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(2, 8))

        if is_manual:
            self._action_btn = ctk.CTkButton(
                btn_frame,
                text="Voir details",
                font=FONTS["small"],
                fg_color=COLORS["info"],
                hover_color="#2980b9",
                text_color="#ffffff",
                height=28,
                width=110,
                corner_radius=6,
                command=self._handle_manual,
            )
            self._action_btn.pack(side="left")
        else:
            self._action_btn = ctk.CTkButton(
                btn_frame,
                text="Appliquer",
                font=FONTS["small"],
                fg_color=COLORS["success"],
                hover_color="#27ae60",
                text_color="#ffffff",
                height=28,
                width=110,
                corner_radius=6,
                command=self._handle_apply,
            )
            self._action_btn.pack(side="left")

    def _handle_apply(self) -> None:
        """Click sur 'Appliquer' — delegue au callback parent."""
        if self._on_apply is None:
            return
        action_id = self._step.get("action_id", "")
        if not action_id:
            return
        self._action_btn.configure(state="disabled", text="...")
        self._on_apply(action_id, self)

    def _handle_manual(self) -> None:
        """Click sur 'Voir details' — ouvre un popup avec la description complete."""
        if self._on_manual is None:
            return
        self._on_manual(self._step)

    def set_result(self, success: bool, message: str) -> None:
        """Met a jour la carte apres execution d'une action automatique.

        Affiche un badge OK ou ERR + le message. Le bouton reste desactive.
        """
        if self._result_label is not None:
            # Re-execution : on remplace l'ancien label
            self._result_label.destroy()

        color = COLORS["success"] if success else COLORS["error"]
        prefix = "OK" if success else "ERREUR"
        text = f"  {prefix} — {message}"

        self._result_label = ctk.CTkLabel(
            self,
            text=text,
            font=FONTS["small"],
            text_color="#ffffff",
            fg_color=color,
            corner_radius=6,
            anchor="w",
            wraplength=720,
            justify="left",
        )
        self._result_label.pack(fill="x", padx=10, pady=(0, 8))
        self._action_btn.configure(state="disabled", text="Termine")


# ---------------------------------------------------------------------------
# ManualStepDialog — popup avec description complete d'un step manuel
# ---------------------------------------------------------------------------


class ManualStepDialog(ctk.CTkToplevel):
    """Popup affichant la description complete d'un step manuel.

    Le `recommended_fix_plan` peut contenir des steps avec une description
    longue (cf. `MANUAL_FIX_DESCRIPTIONS` du runner). On les affiche dans un
    Toplevel scrollable plutot que dans la carte (qui doit rester compacte).
    """

    def __init__(self, parent: Any, step: dict[str, Any]) -> None:
        super().__init__(parent)
        self.title("Procedure manuelle")
        self.geometry("520x360")
        self.resizable(True, True)
        self.configure(fg_color=COLORS["bg_dark"])
        try:
            self.transient(parent.winfo_toplevel())
            self.grab_set()
        except Exception:  # noqa: BLE001 — fallback pour environnement non-GUI
            pass

        # Header
        ctk.CTkLabel(
            self,
            text="Etape manuelle",
            font=FONTS["heading"],
            text_color=COLORS["accent"],
        ).pack(pady=(15, 5))

        from_check = step.get("from_check", "manual")
        ctk.CTkLabel(
            self,
            text=f"check : {from_check}",
            font=FONTS["mono"],
            text_color=COLORS["text_muted"],
        ).pack(pady=(0, 10))

        # Zone scrollable description
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_card"],
            scrollbar_button_color=COLORS["border"],
            corner_radius=8,
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        ctk.CTkLabel(
            scroll,
            text=step.get("description", ""),
            font=FONTS["body"],
            text_color=COLORS["text"],
            wraplength=460,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10, pady=10)

        alternative = step.get("alternative")
        if alternative:
            ctk.CTkLabel(
                scroll,
                text="Alternative",
                font=FONTS["subheading"],
                text_color=COLORS["warning"],
                anchor="w",
            ).pack(fill="x", padx=10, pady=(10, 4))
            ctk.CTkLabel(
                scroll,
                text=str(alternative),
                font=FONTS["body"],
                text_color=COLORS["text_secondary"],
                wraplength=460,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 10))

        # Bouton Fermer
        ctk.CTkButton(
            self,
            text="Fermer",
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            height=36,
            width=120,
            corner_radius=8,
            command=self._close,
        ).pack(pady=(0, 15))

    def _close(self) -> None:
        with contextlib.suppress(Exception):
            self.grab_release()
        self.destroy()


# ---------------------------------------------------------------------------
# DiagnosePage — page principale
# ---------------------------------------------------------------------------


class DiagnosePage(ctk.CTkFrame):
    """Onglet "Diagnose un probleme" — entree texte -> rapport visuel + plan de fix.

    Args:
        parent: Le widget Tk parent (typiquement `app.content`).
        config: La `Config` WinBoost (pour HistoryManager + dry_run defaut).
        runner_factory: Factory pour DiagnosticRunner (injectable pour tests).
        executor_factory: Factory pour ActionExecutor (injectable pour tests).
        history_factory: Factory pour HistoryManager (injectable pour tests).
        actions_dir: Chemin du repertoire actions (default = winboost/actions).
    """

    def __init__(
        self,
        parent: Any,
        config: Any = None,
        runner_factory: Callable[[], Any] | None = None,
        executor_factory: Callable[..., Any] | None = None,
        history_factory: Callable[[], Any] | None = None,
        actions_dir: Path | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self._config = config
        self._runner_factory = runner_factory or DiagnosticRunner
        self._executor_factory = executor_factory
        self._history_factory = history_factory
        self._actions_dir = actions_dir or (Path(__file__).parent.parent / "actions")

        # Etat interne
        self._scan_thread: threading.Thread | None = None
        self._is_scanning = False
        self._last_report: Any = None
        self._fix_step_cards: dict[str, FixStepCard] = {}  # action_id -> card
        self._action_registry: Any = None  # lazy-loaded au 1er Apply

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._create_header()
        self._create_input_area()
        self._create_results_area()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _create_header(self) -> None:
        """Header — titre + sous-titre."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 10))

        ctk.CTkLabel(
            header,
            text="Diagnose un probleme",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text=(
                "Decris ton probleme en francais, WinBoost lance les checks "
                "rules-based et te propose un plan de fix actionnable."
            ),
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

    def _create_input_area(self) -> None:
        """Zone de saisie + boutons d'exemples + bouton "Lancer"."""
        wrapper = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        wrapper.grid(row=1, column=0, sticky="ew", padx=25, pady=(0, 10))
        wrapper.grid_columnconfigure(0, weight=1)

        # Ligne 1 : entree + bouton lancer
        input_row = ctk.CTkFrame(wrapper, fg_color="transparent")
        input_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        input_row.grid_columnconfigure(0, weight=1)

        self.input_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Decris ton probleme en francais...",
            font=FONTS["body"],
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            height=42,
            corner_radius=8,
        )
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.input_entry.bind("<Return>", lambda _e: self._on_run_click())

        self.run_btn = ctk.CTkButton(
            input_row,
            text="Lancer le diagnostic",
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            height=40,
            width=180,
            corner_radius=8,
            command=self._on_run_click,
        )
        self.run_btn.grid(row=0, column=1)

        # Ligne 2 : exemples cliquables
        examples_row = ctk.CTkFrame(wrapper, fg_color="transparent")
        examples_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            examples_row,
            text="Exemples :",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(side="left", padx=(0, 8))

        self._example_buttons: list[ctk.CTkButton] = []
        for label, query in _EXAMPLES:
            btn = ctk.CTkButton(
                examples_row,
                text=label,
                font=FONTS["small"],
                fg_color=COLORS["border"],
                hover_color=COLORS["bg_sidebar"],
                text_color=COLORS["text"],
                height=26,
                corner_radius=6,
                command=lambda q=query: self._fill_example(q),
            )
            btn.pack(side="left", padx=4)
            self._example_buttons.append(btn)

        # Ligne 3 : message d'erreur (cache par defaut)
        self._error_label = ctk.CTkLabel(
            wrapper,
            text="",
            font=FONTS["small"],
            text_color=COLORS["error"],
            anchor="w",
        )
        self._error_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        self._error_label.grid_remove()

    def _create_results_area(self) -> None:
        """Zone scrollable resultats."""
        self._results_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
        )
        self._results_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))

        # Etat initial : message d'accueil
        self._placeholder = ctk.CTkLabel(
            self._results_frame,
            text=(
                "Pret. Decris ton probleme dans la zone ci-dessus ou clique sur "
                "un exemple pour pre-remplir."
            ),
            font=FONTS["body"],
            text_color=COLORS["text_muted"],
            wraplength=700,
            justify="center",
        )
        self._placeholder.pack(pady=40)

    # ------------------------------------------------------------------
    # Interactions utilisateur
    # ------------------------------------------------------------------

    def _fill_example(self, query: str) -> None:
        """Pre-remplit la zone de saisie avec un exemple (sans lancer le scan)."""
        self.input_entry.delete(0, "end")
        self.input_entry.insert(0, query)
        self._hide_error()

    def _hide_error(self) -> None:
        self._error_label.grid_remove()

    def _show_error(self, text: str) -> None:
        self._error_label.configure(text=text)
        self._error_label.grid()

    def _on_run_click(self) -> None:
        """Click sur 'Lancer le diagnostic' (ou Entree dans la zone)."""
        if self._is_scanning:
            return

        query = self.input_entry.get().strip()
        if not query:
            self._show_error("Decris ton probleme avant de lancer le diagnostic.")
            return

        self._hide_error()
        self._start_scan(query)

    def _start_scan(self, query: str) -> None:
        """Demarre le scan dans un thread."""
        self._is_scanning = True
        self.run_btn.configure(state="disabled", text="Diagnostic en cours...")
        self.input_entry.configure(state="disabled")

        # Reset zone resultats
        for child in list(self._results_frame.winfo_children()):
            child.destroy()
        self._fix_step_cards.clear()

        # Loader pendant le scan
        self._scan_status = ctk.CTkLabel(
            self._results_frame,
            text="Lancement des checks systeme... (5-10s typique)",
            font=FONTS["body"],
            text_color=COLORS["info"],
        )
        self._scan_status.pack(pady=20)

        # Thread worker
        self._scan_thread = threading.Thread(
            target=self._run_query_in_thread,
            args=(query,),
            daemon=True,
        )
        self._scan_thread.start()

    def _run_query_in_thread(self, query: str) -> None:
        """Worker thread : execute DiagnosticRunner.run_from_query.

        Toute exception est rattrapee et envoyee au thread UI via `after`.
        """
        try:
            runner = self._runner_factory()
            report = runner.run_from_query(query)
            self.after(0, self._display_report, report)
        except Exception as exc:  # noqa: BLE001 — l'UI ne doit jamais crasher
            self.after(0, self._display_error, str(exc))

    def _display_error(self, message: str) -> None:
        """Thread UI : affiche une erreur de scan."""
        self._is_scanning = False
        self.run_btn.configure(state="normal", text="Lancer le diagnostic")
        self.input_entry.configure(state="normal")

        for child in list(self._results_frame.winfo_children()):
            child.destroy()

        ctk.CTkLabel(
            self._results_frame,
            text=f"Erreur durant le diagnostic :\n{message}",
            font=FONTS["body"],
            text_color=COLORS["error"],
            wraplength=700,
            justify="left",
        ).pack(pady=20, padx=20)

    def _display_report(self, report: Any) -> None:
        """Thread UI : affiche le DiagnosticReport complet."""
        self._is_scanning = False
        self.run_btn.configure(state="normal", text="Re-diagnostiquer")
        self.input_entry.configure(state="normal")
        self._last_report = report

        # Reset
        for child in list(self._results_frame.winfo_children()):
            child.destroy()

        # Header rapport
        self._render_report_header(report)

        # Section checks
        self._render_checks_section(report)

        # Section plan de fix
        self._render_fix_plan_section(report)

    def _render_report_header(self, report: Any) -> None:
        """Affiche le bandeau de synthese du rapport."""
        header = ctk.CTkFrame(self._results_frame, fg_color=COLORS["bg_card"], corner_radius=12)
        header.pack(fill="x", padx=4, pady=(0, 10))

        # Theme + timestamp
        line1 = ctk.CTkFrame(header, fg_color="transparent")
        line1.pack(fill="x", padx=12, pady=(10, 2))

        theme = getattr(report, "theme", "?")
        ctk.CTkLabel(
            line1,
            text=f"Theme : {theme}",
            font=FONTS["subheading"],
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(side="left")

        timestamp = getattr(report, "timestamp", None)
        if timestamp is not None:
            try:
                ts_text = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:  # noqa: BLE001
                ts_text = str(timestamp)
        else:
            ts_text = datetime.now().strftime("%H:%M:%S")

        ctk.CTkLabel(
            line1,
            text=ts_text,
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(side="right")

        # Resume
        summary = getattr(report, "summary", "")
        ctk.CTkLabel(
            header,
            text=summary,
            font=FONTS["body"],
            text_color=COLORS["text"],
            anchor="w",
            wraplength=900,
            justify="left",
        ).pack(fill="x", padx=12, pady=(2, 10))

    def _render_checks_section(self, report: Any) -> None:
        """Affiche la liste des CheckResult (ordre d'execution)."""
        checks = list(getattr(report, "checks", ()) or ())
        if not checks:
            return

        section_label = ctk.CTkLabel(
            self._results_frame,
            text=f"Checks ({len(checks)})",
            font=FONTS["heading"],
            text_color=COLORS["text"],
            anchor="w",
        )
        section_label.pack(fill="x", padx=4, pady=(8, 4))

        for check in checks:
            CheckResultCard(self._results_frame, check)

    def _render_fix_plan_section(self, report: Any) -> None:
        """Affiche le recommended_fix_plan, avec boutons Apply/Manuel."""
        plan = list(getattr(report, "recommended_fix_plan", ()) or ())
        if not plan:
            ctk.CTkLabel(
                self._results_frame,
                text="Aucun fix necessaire.",
                font=FONTS["body"],
                text_color=COLORS["success"],
                anchor="w",
            ).pack(fill="x", padx=4, pady=(8, 4))
            return

        ctk.CTkLabel(
            self._results_frame,
            text=f"Plan de fix recommande ({len(plan)} etape(s))",
            font=FONTS["heading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", padx=4, pady=(16, 4))

        for step in plan:
            card = FixStepCard(
                self._results_frame,
                step,
                on_apply=self._handle_apply_action,
                on_manual=self._handle_manual_step,
            )
            action_id = step.get("action_id")
            if action_id:
                self._fix_step_cards[action_id] = card

    # ------------------------------------------------------------------
    # Apply / Manual handlers
    # ------------------------------------------------------------------

    def _handle_apply_action(self, action_id: str, card: FixStepCard) -> None:
        """Click 'Appliquer' sur un step automatique.

        Charge l'action via ActionRegistry, instancie ActionExecutor (injectable
        pour les tests), execute en arriere-plan, met a jour la carte.
        """
        thread = threading.Thread(
            target=self._apply_worker,
            args=(action_id, card),
            daemon=True,
        )
        thread.start()

    def _apply_worker(self, action_id: str, card: FixStepCard) -> None:
        """Worker thread : charge l'action et l'execute via ActionExecutor."""
        try:
            action = self._resolve_action(action_id)
        except Exception as exc:  # noqa: BLE001
            self.after(0, card.set_result, False, f"Action introuvable : {exc}")
            return

        if action is None:
            self.after(
                0, card.set_result, False, f"Action {action_id} non trouvee dans le registry."
            )
            return

        try:
            executor = self._build_executor()
            result = executor.apply(action)
        except Exception as exc:  # noqa: BLE001
            self.after(0, card.set_result, False, str(exc))
            return

        success = bool(getattr(result, "success", False))
        message = getattr(result, "message", "OK" if success else "Echec")
        self.after(0, card.set_result, success, message)

    def _resolve_action(self, action_id: str) -> Any:
        """Charge le registry au premier Apply (lazy)."""
        if self._action_registry is None:
            from winboost.actions.loader import ActionRegistry

            registry = ActionRegistry(actions_dir=self._actions_dir)
            registry.load_all()
            self._action_registry = registry
        return self._action_registry.get(action_id)

    def _build_executor(self) -> Any:
        """Construit un ActionExecutor (injectable via executor_factory)."""
        if self._executor_factory is not None:
            return self._executor_factory()
        from winboost.core.executor import ActionExecutor

        history = None
        if self._history_factory is not None:
            try:
                history = self._history_factory()
            except Exception:  # noqa: BLE001 — degrade gracefully
                history = None
        else:
            try:
                from winboost.core.history import HistoryManager

                history = HistoryManager()
            except Exception:  # noqa: BLE001
                history = None

        return ActionExecutor(history_manager=history, module_label="diagnose")

    def _handle_manual_step(self, step: dict[str, Any]) -> None:
        """Click 'Voir details' — ouvre le popup avec la description complete."""
        ManualStepDialog(self, step)
