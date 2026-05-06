"""History Page — Timeline des actions passees + Undo manager (Phase 9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import customtkinter as ctk

from winboost.core.backup import BackupManager
from winboost.core.history import HistoryManager
from winboost.gui.theme import COLORS, FONTS, RISK_COLORS

# Couleurs par statut
STATUS_COLORS = {
    "success": COLORS["success"],
    "partial": COLORS["warning"],
    "error": COLORS["error"],
    "pending": COLORS["text_muted"],
}

# Icones par type d'action
ACTION_ICONS = {
    "scan": "SCAN",
    "fix": "FIX",
    "restore": "UNDO",
    "execute": "EXEC",
    "dry_run": "SIM",
}


class HistoryEntryCard(ctk.CTkFrame):
    """Carte pour une entree d'historique dans la timeline."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        entry: Any,  # HistoryEntry
        on_undo: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=10, **kwargs)
        self.pack(fill="x", pady=3)

        self._entry = entry
        self._on_undo = on_undo
        self._detail_visible = False
        self._detail_frame: ctk.CTkFrame | None = None

        # --- Header : timestamp + type + module ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        # Badge type action
        icon = ACTION_ICONS.get(entry.action_type, "?")
        status_color = STATUS_COLORS.get(entry.result_status, COLORS["text_muted"])

        ctk.CTkLabel(
            header,
            text=f" {icon} ",
            font=("Segoe UI", 9, "bold"),
            text_color="#ffffff",
            fg_color=status_color,
            corner_radius=4,
            width=45,
            height=20,
        ).pack(side="left", padx=(0, 8))

        # Badge risque
        risk_color = RISK_COLORS.get(entry.risk_level, COLORS["info"])
        ctk.CTkLabel(
            header,
            text=f" {entry.risk_level.upper()} ",
            font=("Segoe UI", 9, "bold"),
            text_color="#ffffff",
            fg_color=risk_color,
            corner_radius=4,
            height=20,
        ).pack(side="left", padx=(0, 8))

        # Module
        ctk.CTkLabel(
            header,
            text=entry.module_name,
            font=FONTS["subheading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Timestamp
        try:
            ts = datetime.fromisoformat(entry.timestamp)
            time_str = ts.strftime("%d/%m %H:%M")
        except (ValueError, TypeError):
            time_str = entry.timestamp[:16] if entry.timestamp else "?"

        ctk.CTkLabel(
            header,
            text=time_str,
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(side="right")

        # --- Description ---
        ctk.CTkLabel(
            self,
            text=entry.description,
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            wraplength=500,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 4))

        # --- Boutons ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 8))

        # Details toggle
        ctk.CTkButton(
            btn_frame,
            text="Details",
            font=FONTS["small"],
            fg_color=COLORS["border"],
            hover_color=COLORS["bg_sidebar"],
            text_color=COLORS["text"],
            height=26,
            width=70,
            corner_radius=6,
            command=self._toggle_detail,
        ).pack(side="left", padx=(0, 6))

        # Bouton Undo (si backup_id disponible)
        if entry.backup_id and on_undo:
            ctk.CTkButton(
                btn_frame,
                text="Annuler",
                font=FONTS["small"],
                fg_color=COLORS["warning"],
                hover_color="#e67e22",
                text_color="#ffffff",
                height=26,
                width=75,
                corner_radius=6,
                command=lambda: on_undo(entry.backup_id),
            ).pack(side="left")

    def _toggle_detail(self) -> None:
        """Affiche/masque les details."""
        if self._detail_visible and self._detail_frame:
            self._detail_frame.destroy()
            self._detail_frame = None
            self._detail_visible = False
            return

        self._detail_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], corner_radius=8)
        self._detail_frame.pack(fill="x", padx=10, pady=(0, 8))

        details = [
            ("ID", str(self._entry.entry_id)),
            ("Type", self._entry.action_type),
            ("Statut", self._entry.result_status),
            ("Detail", self._entry.result_detail or "—"),
            ("Backup", self._entry.backup_id or "—"),
        ]

        for label, value in details:
            row = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=1)

            ctk.CTkLabel(
                row, text=f"{label} :", font=FONTS["mono"],
                text_color=COLORS["text_muted"], anchor="w", width=70,
            ).pack(side="left")

            ctk.CTkLabel(
                row, text=value, font=FONTS["mono"],
                text_color=COLORS["text"], anchor="w",
            ).pack(side="left", padx=(4, 0))

        self._detail_visible = True


class HistoryPage(ctk.CTkFrame):
    """Page d'historique avec timeline et undo manager."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        config: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self._history = HistoryManager()
        self._backup = BackupManager()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 10))

        ctk.CTkLabel(
            header,
            text="Historique",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        # Compteur
        total = self._history.count()
        ctk.CTkLabel(
            header,
            text=f"{total} action(s)",
            font=FONTS["small"],
            text_color=COLORS["accent"],
        ).pack(side="right")

        # --- Filtres ---
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.grid(row=1, column=0, sticky="ew", padx=25, pady=(0, 10))

        ctk.CTkLabel(
            filter_frame,
            text="Filtrer :",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 8))

        # Filtre par type
        self._type_var = ctk.StringVar(value="tous")
        type_menu = ctk.CTkOptionMenu(
            filter_frame,
            values=["tous", "scan", "fix", "execute", "dry_run", "restore"],
            variable=self._type_var,
            font=FONTS["small"],
            fg_color=COLORS["bg_card"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_card"],
            width=100,
            command=lambda _: self._refresh(),
        )
        type_menu.pack(side="left", padx=(0, 10))

        # Filtre par module
        self._module_var = ctk.StringVar(value="tous")
        module_menu = ctk.CTkOptionMenu(
            filter_frame,
            values=["tous"],  # Sera rempli dynamiquement
            variable=self._module_var,
            font=FONTS["small"],
            fg_color=COLORS["bg_card"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_card"],
            width=150,
            command=lambda _: self._refresh(),
        )
        module_menu.pack(side="left", padx=(0, 10))
        self._module_menu = module_menu

        # Bouton rafraichir
        ctk.CTkButton(
            filter_frame,
            text="Actualiser",
            font=FONTS["small"],
            fg_color=COLORS["border"],
            hover_color=COLORS["bg_sidebar"],
            text_color=COLORS["text"],
            height=28,
            width=80,
            corner_radius=6,
            command=self._refresh,
        ).pack(side="left")

        # Bouton tout effacer
        ctk.CTkButton(
            filter_frame,
            text="Tout effacer",
            font=FONTS["small"],
            fg_color=COLORS["error"],
            hover_color="#c0392b",
            text_color="#ffffff",
            height=28,
            width=90,
            corner_radius=6,
            command=self._clear_history,
        ).pack(side="right")

        # --- Timeline (scrollable) ---
        self._timeline = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
        )
        self._timeline.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10))

        # --- Backups section ---
        backup_header = ctk.CTkFrame(self, fg_color="transparent")
        backup_header.grid(row=3, column=0, sticky="ew", padx=25, pady=(5, 5))

        backups = self._backup.list_backups()
        ctk.CTkLabel(
            backup_header,
            text=f"Points de restauration : {len(backups)}",
            font=FONTS["subheading"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(side="left")

        # Charge les donnees
        self._refresh()

    def _refresh(self) -> None:
        """Recharge et affiche les entrees d'historique."""
        # Nettoie la timeline
        for widget in self._timeline.winfo_children():
            widget.destroy()

        # Parametres de filtre
        type_filter = self._type_var.get()
        module_filter = self._module_var.get()

        action_type = type_filter if type_filter != "tous" else None
        module_name = module_filter if module_filter != "tous" else None

        # Charge l'historique
        entries = self._history.get_history(
            module_name=module_name,
            action_type=action_type,
            limit=100,
        )

        # Mise a jour du menu modules
        all_entries = self._history.get_history(limit=200)
        modules = sorted({e.module_name for e in all_entries})
        self._module_menu.configure(values=["tous"] + modules)

        if not entries:
            ctk.CTkLabel(
                self._timeline,
                text="Aucune action dans l'historique.",
                font=FONTS["body"],
                text_color=COLORS["text_muted"],
            ).pack(pady=30)
            return

        # Affiche les entrees
        for entry in entries:
            HistoryEntryCard(
                self._timeline,
                entry,
                on_undo=self._undo_action if entry.backup_id else None,
            )

    def _undo_action(self, backup_id: str) -> None:
        """Restaure un backup."""
        restored, errors = self._backup.restore_backup(backup_id)

        # Log la restauration
        self._history.log_action(
            module_name="undo_manager",
            action_type="restore",
            description=f"Restauration backup {backup_id}",
            risk_level="medium",
            result_status="success" if errors == 0 else "partial",
            result_detail=f"{restored} fichier(s) restaure(s), {errors} erreur(s)",
            backup_id=backup_id,
        )

        self._refresh()

    def _clear_history(self) -> None:
        """Efface tout l'historique."""
        self._history.clear()
        self._refresh()
