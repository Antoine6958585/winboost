"""Chat GUI — Interface conversationnelle IA WinBoost (Phase 8)."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import customtkinter as ctk

from winboost.gui.theme import COLORS, FONTS, RISK_COLORS

# ---------------------------------------------------------------------------
# Composants de message
# ---------------------------------------------------------------------------

class ChatBubble(ctk.CTkFrame):
    """Bulle de message utilisateur ou bot (texte simple)."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        text: str,
        is_user: bool = True,
        **kwargs: Any,
    ) -> None:
        bg = COLORS["accent"] if is_user else COLORS["bg_card"]
        super().__init__(parent, fg_color=bg, corner_radius=12, **kwargs)

        # Padding asymetrique pour l'alignement visuel
        pad_left = 80 if is_user else 15
        pad_right = 15 if is_user else 80
        self.pack(fill="x", padx=(pad_left, pad_right), pady=4)

        # Timestamp discret
        time_str = datetime.now().strftime("%H:%M")
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(6, 0))

        label_text = "Vous" if is_user else "WinBoost"
        ctk.CTkLabel(
            header,
            text=label_text,
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=time_str,
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="e",
        ).pack(side="right")

        # Contenu du message
        ctk.CTkLabel(
            self,
            text=text,
            font=FONTS["body"],
            text_color=COLORS["text"],
            wraplength=480,
            justify="left",
            anchor="w",
        ).pack(padx=12, pady=(2, 8), fill="x")


class StatusBubble(ctk.CTkFrame):
    """Message systeme centre (info, erreur, notification)."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        text: str,
        color: str = "text_muted",
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.pack(fill="x", padx=40, pady=6)

        ctk.CTkLabel(
            self,
            text=text,
            font=FONTS["small"],
            text_color=COLORS.get(color, color),
            anchor="center",
        ).pack()


class TypingIndicator(ctk.CTkFrame):
    """Indicateur de saisie (animation "..." pendant le traitement)."""

    def __init__(self, parent: ctk.CTkFrame, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=12, **kwargs)
        self.pack(fill="x", padx=(15, 200), pady=4)

        self._label = ctk.CTkLabel(
            self,
            text="WinBoost reflechit...",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self._label.pack(padx=12, pady=8)
        self._dots = 0
        self._running = True
        self._animate()

    def _animate(self) -> None:
        if not self._running:
            return
        self._dots = (self._dots % 3) + 1
        self._label.configure(text="WinBoost reflechit" + "." * self._dots)
        self.after(400, self._animate)

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# ActionCard — carte d'action avec badge risque + boutons inline
# ---------------------------------------------------------------------------

class ActionCard(ctk.CTkFrame):
    """Carte d'action proposee par l'IA avec risque, preview et boutons."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        routed_action: Any,  # RoutedAction
        on_execute: Any = None,  # callback(action_id)
        on_dry_run: Any = None,  # callback(action_id)
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=10, **kwargs)
        self.pack(fill="x", padx=(15, 80), pady=3)

        self._routed = routed_action
        self._on_execute = on_execute
        self._on_dry_run = on_dry_run
        self._preview_visible = False
        self._preview_frame: ctk.CTkFrame | None = None

        action = routed_action.action
        verdict = routed_action.verdict
        risk = action.risk_level
        risk_color = RISK_COLORS.get(risk, COLORS["info"])

        # --- Header : badge risque + nom ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        # Badge risque
        badge = ctk.CTkLabel(
            header,
            text=f" {risk.upper()} ",
            font=("Segoe UI", 10, "bold"),
            text_color="#ffffff",
            fg_color=risk_color,
            corner_radius=4,
            width=60,
            height=22,
        )
        badge.pack(side="left", padx=(0, 8))

        # Nom de l'action
        ctk.CTkLabel(
            header,
            text=action.name,
            font=FONTS["subheading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Score
        score_pct = int(routed_action.score * 100)
        ctk.CTkLabel(
            header,
            text=f"{score_pct}%",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(side="right")

        # --- Description ---
        ctk.CTkLabel(
            self,
            text=action.description,
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            wraplength=450,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 4))

        # --- Conditions (confirmation, dry-run) ---
        conditions: list[str] = []
        if verdict.requires_dry_run:
            conditions.append("Dry-run requis")
        if verdict.requires_confirmation:
            conditions.append("Confirmation requise")
        if action.requires_admin:
            conditions.append("Admin requis")
        if not action.reversible:
            conditions.append("Irreversible")

        if conditions:
            cond_text = " | ".join(conditions)
            ctk.CTkLabel(
                self,
                text=cond_text,
                font=FONTS["small"],
                text_color=COLORS["warning"],
                anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 4))

        # --- Boutons inline ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(2, 8))

        # Bouton Details (toggle preview)
        ctk.CTkButton(
            btn_frame,
            text="Details",
            font=FONTS["small"],
            fg_color=COLORS["border"],
            hover_color=COLORS["bg_sidebar"],
            text_color=COLORS["text"],
            height=28,
            width=75,
            corner_radius=6,
            command=self._toggle_preview,
        ).pack(side="left", padx=(0, 6))

        # Bouton Dry-run (si requis ou disponible)
        self._dry_run_btn = ctk.CTkButton(
            btn_frame,
            text="Simuler",
            font=FONTS["small"],
            fg_color=COLORS["info"],
            hover_color="#2980b9",
            text_color="#ffffff",
            height=28,
            width=75,
            corner_radius=6,
            command=self._handle_dry_run,
        )
        self._dry_run_btn.pack(side="left", padx=(0, 6))

        # Bouton Appliquer
        apply_color = COLORS["success"] if risk in ("info", "low") else COLORS["warning"]
        self._apply_btn = ctk.CTkButton(
            btn_frame,
            text="Appliquer",
            font=FONTS["small"],
            fg_color=apply_color,
            hover_color="#27ae60" if risk in ("info", "low") else "#e67e22",
            text_color="#ffffff",
            height=28,
            width=85,
            corner_radius=6,
            command=self._handle_execute,
        )
        self._apply_btn.pack(side="left")

    def _toggle_preview(self) -> None:
        """Affiche/masque le panel de preview."""
        if self._preview_visible and self._preview_frame:
            self._preview_frame.destroy()
            self._preview_frame = None
            self._preview_visible = False
            return

        self._preview_frame = PreviewPanel(self, self._routed.action)
        self._preview_visible = True

    def _handle_dry_run(self) -> None:
        """Declenche un dry-run de l'action."""
        if self._on_dry_run:
            self._dry_run_btn.configure(state="disabled", text="...")
            self._on_dry_run(self._routed.action.id)

    def _handle_execute(self) -> None:
        """Declenche l'execution de l'action (avec confirmation si requis)."""
        if self._on_execute:
            self._apply_btn.configure(state="disabled", text="...")
            self._on_execute(self._routed.action.id)

    def set_result(self, success: bool, message: str) -> None:
        """Met a jour la carte apres execution."""
        color = COLORS["success"] if success else COLORS["error"]
        icon = "OK" if success else "ERREUR"

        result_frame = ctk.CTkFrame(self, fg_color=color, corner_radius=6)
        result_frame.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(
            result_frame,
            text=f" {icon} — {message}",
            font=FONTS["small"],
            text_color="#ffffff",
            anchor="w",
        ).pack(padx=8, pady=4, fill="x")

        # Desactive les boutons
        self._apply_btn.configure(state="disabled")
        self._dry_run_btn.configure(state="disabled")


class BlockedActionCard(ctk.CTkFrame):
    """Carte pour une action bloquee par le profil de securite."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        routed_action: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=10, **kwargs)
        self.pack(fill="x", padx=(15, 80), pady=3)

        action = routed_action.action
        verdict = routed_action.verdict

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        # Badge BLOQUE
        ctk.CTkLabel(
            header,
            text=" BLOQUE ",
            font=("Segoe UI", 10, "bold"),
            text_color="#ffffff",
            fg_color=COLORS["error"],
            corner_radius=4,
            width=60,
            height=22,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            header,
            text=action.name,
            font=FONTS["subheading"],
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Raison du blocage
        ctk.CTkLabel(
            self,
            text=verdict.reason,
            font=FONTS["small"],
            text_color=COLORS["error"],
            wraplength=450,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 8))


# ---------------------------------------------------------------------------
# PreviewPanel — details before/after d'une action
# ---------------------------------------------------------------------------

class PreviewPanel(ctk.CTkFrame):
    """Panel de preview montrant les details d'execution d'une action."""

    def __init__(self, parent: ctk.CTkFrame, action: Any, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], corner_radius=8, **kwargs)
        self.pack(fill="x", padx=10, pady=(0, 8))

        # Methode d'execution
        method = action.execute.get("method", "N/A")
        params = action.execute.get("params", {})

        self._add_row("Methode", method)

        # Parametres
        if params:
            for key, value in params.items():
                self._add_row(f"  {key}", str(value))

        # Reversibilite
        reversible_text = "Oui (rollback disponible)" if action.reversible else "Non (irreversible)"
        reversible_color = COLORS["success"] if action.reversible else COLORS["error"]
        self._add_row("Reversible", reversible_text, value_color=reversible_color)

        # Rollback info
        if action.reversible and action.rollback:
            rollback_method = action.rollback.get("method", "N/A")
            self._add_row("Rollback", rollback_method)

        # Admin requis
        if action.requires_admin:
            self._add_row("Admin", "Requis (elevation necessaire)", value_color=COLORS["warning"])

        # Categorie
        self._add_row("Categorie", action.category)

    def _add_row(
        self, label: str, value: str, value_color: str | None = None,
    ) -> None:
        """Ajoute une ligne label: valeur dans le panel."""
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=1)

        ctk.CTkLabel(
            row,
            text=label + " :",
            font=FONTS["mono"],
            text_color=COLORS["text_muted"],
            anchor="w",
            width=100,
        ).pack(side="left")

        ctk.CTkLabel(
            row,
            text=value,
            font=FONTS["mono"],
            text_color=value_color or COLORS["text"],
            anchor="w",
        ).pack(side="left", padx=(4, 0))


# ---------------------------------------------------------------------------
# ConfirmDialog — dialogue de confirmation modale
# ---------------------------------------------------------------------------

class ConfirmDialog(ctk.CTkToplevel):
    """Dialogue de confirmation pour les actions a risque."""

    def __init__(
        self,
        parent: Any,
        action_name: str,
        risk_level: str,
        message: str,
        on_confirm: Any,
        on_cancel: Any = None,
    ) -> None:
        super().__init__(parent)
        self.title("Confirmation requise")
        self.geometry("420x220")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        risk_color = RISK_COLORS.get(risk_level, COLORS["warning"])

        # Icone risque
        ctk.CTkLabel(
            self,
            text=f"Action {risk_level.upper()}",
            font=FONTS["heading"],
            text_color=risk_color,
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            self,
            text=action_name,
            font=FONTS["subheading"],
            text_color=COLORS["text"],
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            self,
            text=message,
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            wraplength=380,
        ).pack(padx=20, pady=(0, 20))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        ctk.CTkButton(
            btn_frame,
            text="Annuler",
            font=FONTS["body"],
            fg_color=COLORS["border"],
            hover_color=COLORS["bg_sidebar"],
            text_color=COLORS["text"],
            height=36,
            width=120,
            corner_radius=8,
            command=lambda: self._cancel(on_cancel),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="Confirmer",
            font=FONTS["body"],
            fg_color=risk_color,
            hover_color=COLORS["error"],
            text_color="#ffffff",
            height=36,
            width=120,
            corner_radius=8,
            command=lambda: self._confirm(on_confirm),
        ).pack(side="left")

    def _confirm(self, callback: Any) -> None:
        self.grab_release()
        self.destroy()
        if callback:
            callback()

    def _cancel(self, callback: Any) -> None:
        self.grab_release()
        self.destroy()
        if callback:
            callback()


# ---------------------------------------------------------------------------
# ChatPage — page principale du chat IA
# ---------------------------------------------------------------------------

class ChatPage(ctk.CTkFrame):
    """Page de chat IA integree avec ActionRouter et modules WinBoost."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        config: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        # Lazy imports pour eviter les imports circulaires
        from winboost.ai.action_router import ActionRouter
        from winboost.core.config import Config
        from winboost.core.history import HistoryManager

        self._config = config or Config()
        self._actions_dir = Path(__file__).parent.parent / "actions"
        self._router = ActionRouter(config=self._config, actions_dir=self._actions_dir)
        self._history = HistoryManager()

        # Cache des action cards pour les callbacks
        self._action_cards: dict[str, ActionCard] = {}
        self._routed_actions: dict[str, Any] = {}  # action_id -> RoutedAction
        self._typing_indicator: TypingIndicator | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 15))

        ctk.CTkLabel(
            header,
            text="Chat IA",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        # Indicateur profil + nombre d'actions
        profile_text = (
            f"Profil: {self._config.profile.upper()} "
            f"| {self._router.action_count} actions"
        )
        ctk.CTkLabel(
            header,
            text=profile_text,
            font=FONTS["small"],
            text_color=COLORS["accent"],
        ).pack(side="right")

        # --- Zone de messages (scrollable) ---
        self.messages_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
        )
        self.messages_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))

        # Message de bienvenue
        self._add_bot_message(
            "Salut ! Je suis l'assistant WinBoost.\n\n"
            "Dis-moi ce que tu veux faire et je te proposerai les actions adaptees "
            "a ton profil de securite.\n\n"
            "Exemples :\n"
            "  - \"desactive la telemetrie\"\n"
            "  - \"nettoie les fichiers temporaires\"\n"
            "  - \"optimise pour les jeux\"\n"
            "  - \"ameliore la securite\""
        )

        # --- Zone de saisie ---
        input_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        input_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        input_frame.grid_columnconfigure(0, weight=1)

        self.input_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Demande-moi quelque chose...",
            font=FONTS["body"],
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            height=40,
            corner_radius=8,
        )
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.input_entry.bind("<Return>", self._on_send)

        self.send_btn = ctk.CTkButton(
            input_frame,
            text="Envoyer",
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            height=38,
            width=100,
            corner_radius=8,
            command=self._on_send,
        )
        self.send_btn.grid(row=0, column=1, padx=(0, 10), pady=10)

    # ------------------------------------------------------------------
    # Gestion des messages
    # ------------------------------------------------------------------

    def _on_send(self, event: Any = None) -> None:
        """Gere l'envoi d'un message utilisateur."""
        text = self.input_entry.get().strip()
        if not text:
            return

        self.input_entry.delete(0, "end")
        self._add_user_message(text)

        # Desactive l'input pendant le traitement
        self.input_entry.configure(state="disabled")
        self.send_btn.configure(state="disabled")

        # Indicateur de saisie
        self._typing_indicator = TypingIndicator(self.messages_frame)
        self._scroll_to_bottom()

        # Route la requete dans un thread
        thread = threading.Thread(
            target=self._route_query,
            args=(text,),
            daemon=True,
        )
        thread.start()

    def _route_query(self, query: str) -> None:
        """Route la requete via ActionRouter (thread worker)."""
        try:
            result = self._router.route(query)
            self.after(0, self._display_result, result)
        except Exception as e:
            self.after(0, self._display_error, str(e))

    def _display_result(self, result: Any) -> None:
        """Affiche le resultat du routage dans le chat (thread-safe)."""
        # Supprime l'indicateur de saisie
        if self._typing_indicator:
            self._typing_indicator.stop()
            self._typing_indicator.destroy()
            self._typing_indicator = None

        # Reactive l'input
        self.input_entry.configure(state="normal")
        self.send_btn.configure(state="normal")

        if not result.has_actions and not result.blocked:
            self._add_bot_message(
                "Je n'ai trouve aucune action pour cette demande.\n"
                "Essaie de reformuler ou d'etre plus precis."
            )
            return

        # Message resume
        source_label = {
            "cache": "mots-cles",
            "category_fallback": "categorie",
            "llm": "IA",
            "none": "-",
        }.get(result.resolved_by, result.resolved_by)

        summary = f"{result.message}  (via {source_label})"
        self._add_bot_message(summary)

        # Actions autorisees
        for routed in result.actions:
            self._routed_actions[routed.action.id] = routed
            card = ActionCard(
                self.messages_frame,
                routed,
                on_execute=self._on_execute_action,
                on_dry_run=self._on_dry_run_action,
            )
            self._action_cards[routed.action.id] = card

        # Actions bloquees
        if result.blocked:
            StatusBubble(
                self.messages_frame,
                f"{len(result.blocked)} action(s) bloquee(s) par votre profil :",
                color="error",
            )
            for routed in result.blocked:
                BlockedActionCard(self.messages_frame, routed)

        self._scroll_to_bottom()

    def _display_error(self, error: str) -> None:
        """Affiche une erreur dans le chat."""
        if self._typing_indicator:
            self._typing_indicator.stop()
            self._typing_indicator.destroy()
            self._typing_indicator = None

        self.input_entry.configure(state="normal")
        self.send_btn.configure(state="normal")

        self._add_bot_message(f"Erreur : {error}")

    # ------------------------------------------------------------------
    # Execution des actions
    # ------------------------------------------------------------------

    def _on_execute_action(self, action_id: str) -> None:
        """Gere le clic sur 'Appliquer' d'une action."""
        routed = self._routed_actions.get(action_id)
        if not routed:
            return

        action = routed.action
        verdict = routed.verdict

        # Si confirmation requise, affiche le dialogue
        if verdict.requires_confirmation:
            # Si dry-run requis aussi, on force un dry-run d'abord
            if verdict.requires_dry_run:
                msg = (
                    "Cette action necessite un dry-run avant execution.\n"
                    "Voulez-vous simuler puis appliquer ?"
                )
            else:
                msg = "Voulez-vous appliquer cette action sur votre systeme ?"

            ConfirmDialog(
                self,
                action_name=action.name,
                risk_level=action.risk_level,
                message=msg,
                on_confirm=lambda: self._execute_action(action_id),
            )
        else:
            self._execute_action(action_id)

    def _execute_action(self, action_id: str) -> None:
        """Execute une action dans un thread."""
        thread = threading.Thread(
            target=self._execute_worker,
            args=(action_id,),
            daemon=True,
        )
        thread.start()

    def _execute_worker(self, action_id: str) -> None:
        """Worker d'execution (thread).

        Note v2.0 : les 150 actions YAML constituent un catalogue valide ; leur
        execution reelle (registre, services, PowerShell) est planifiee en v2.1
        avec elevation UAC selective. En v2.0, on enregistre l'intention dans
        l'historique mais aucune modification systeme n'est appliquee.
        """
        from winboost.utils.admin import AdminRequiredError, is_admin

        routed = self._routed_actions.get(action_id)
        if not routed:
            return

        action = routed.action

        # Check UAC : refuser proprement les actions admin si on n'est pas eleve
        if action.requires_admin and not is_admin():
            err_msg = (
                f"L'action '{action.name}' requiert les droits administrateur. "
                "Relance WinBoost en tant qu'administrateur pour l'appliquer."
            )
            self._history.log_action(
                module_name=f"chat:{action.category}",
                action_type="execute",
                description=f"Action: {action.name}",
                risk_level=action.risk_level,
                result_status="blocked_admin_required",
                result_detail=err_msg,
            )
            self.after(0, self._on_action_complete, action_id, False, err_msg)
            return

        try:
            # Log l'action dans l'historique
            self._history.log_action(
                module_name=f"chat:{action.category}",
                action_type="execute",
                description=f"Action: {action.name}",
                risk_level=action.risk_level,
                result_status="pending",
                result_detail=f"Methode: {action.execute.get('method', 'N/A')}",
            )

            # v2.0 : enregistrement dans le catalogue, pas d'execution reelle.
            # L'executor (registry_set, service_disable, powershell, etc.) sera
            # implemente en v2.1 avec branchement UAC selectif.
            method = action.execute.get("method", "")
            params = action.execute.get("params", {})

            detail = f"Action enregistree (catalogue v2.0, methode '{method}'"
            if params:
                param_str = ", ".join(f"{k}={v}" for k, v in params.items())
                detail += f", parametres : {param_str}"
            detail += "). Execution reelle systeme prevue en v2.1."

            # Log dans l'historique avec un statut explicite
            self._history.log_action(
                module_name=f"chat:{action.category}",
                action_type="execute",
                description=f"Action: {action.name}",
                risk_level=action.risk_level,
                result_status="catalogued",
                result_detail=detail,
            )

            self.after(0, self._on_action_complete, action_id, True, detail)

        except AdminRequiredError as e:
            self._history.log_action(
                module_name=f"chat:{action.category}",
                action_type="execute",
                description=f"Action: {action.name}",
                risk_level=action.risk_level,
                result_status="blocked_admin_required",
                result_detail=str(e),
            )
            self.after(0, self._on_action_complete, action_id, False, str(e))

        except Exception as e:
            self._history.log_action(
                module_name=f"chat:{action.category}",
                action_type="execute",
                description=f"Action: {action.name}",
                risk_level=action.risk_level,
                result_status="error",
                result_detail=str(e),
            )
            self.after(0, self._on_action_complete, action_id, False, str(e))

    def _on_action_complete(self, action_id: str, success: bool, message: str) -> None:
        """Callback apres execution d'une action (thread-safe)."""
        card = self._action_cards.get(action_id)
        if card:
            card.set_result(success, message)

        # Message dans le chat
        if success:
            StatusBubble(
                self.messages_frame,
                "Action executee avec succes",
                color="success",
            )
        else:
            StatusBubble(
                self.messages_frame,
                f"Echec : {message}",
                color="error",
            )

        self._scroll_to_bottom()

    def _on_dry_run_action(self, action_id: str) -> None:
        """Gere le clic sur 'Simuler' d'une action."""
        routed = self._routed_actions.get(action_id)
        if not routed:
            return

        action = routed.action
        method = action.execute.get("method", "N/A")
        params = action.execute.get("params", {})

        # Affiche le resultat du dry-run dans le chat
        lines = [f"Dry-run : {action.name}"]
        lines.append(f"  Methode : {method}")
        if params:
            for k, v in params.items():
                lines.append(f"  {k} : {v}")
        lines.append(f"  Risque : {action.risk_level}")
        lines.append(f"  Reversible : {'Oui' if action.reversible else 'Non'}")
        if action.reversible and action.rollback:
            lines.append(f"  Rollback : {action.rollback.get('method', 'N/A')}")

        self._add_bot_message("\n".join(lines))

        # Log le dry-run
        self._history.log_action(
            module_name=f"chat:{action.category}",
            action_type="dry_run",
            description=f"Dry-run: {action.name}",
            risk_level=action.risk_level,
            result_status="success",
            result_detail=f"Simulation {method}",
        )

        # Met a jour le bouton
        card = self._action_cards.get(action_id)
        if card:
            card._dry_run_btn.configure(text="Simule", state="disabled")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_user_message(self, text: str) -> None:
        """Ajoute un message utilisateur au chat."""
        ChatBubble(self.messages_frame, text, is_user=True)
        self._scroll_to_bottom()

    def _add_bot_message(self, text: str) -> None:
        """Ajoute un message bot au chat."""
        ChatBubble(self.messages_frame, text, is_user=False)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        """Scroll vers le bas des messages."""
        self.messages_frame.after(
            50, self.messages_frame._parent_canvas.yview_moveto, 1.0,
        )
