"""Dashboard — Vue principale avec cards de modules et scan global."""

from __future__ import annotations

import threading
from typing import Any

import customtkinter as ctk

from winboost.core.base_module import ScanResult
from winboost.core.engine import Engine
from winboost.gui.theme import CARD_PADDING, COLORS, FONTS, RISK_COLORS


class ModuleCard(ctk.CTkFrame):
    """Card representant un module avec ses resultats de scan."""

    def __init__(self, parent: ctk.CTkFrame, module_name: str, description: str,
                 risk_level: str, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=12, **kwargs)

        self.module_name = module_name
        self._risk_level = risk_level

        # Header : nom + badge risque
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 5))

        ctk.CTkLabel(
            header,
            text=module_name.replace("_", " ").title(),
            font=FONTS["subheading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        risk_color = RISK_COLORS.get(risk_level, COLORS["info"])
        ctk.CTkLabel(
            header,
            text=risk_level.upper(),
            font=FONTS["small"],
            text_color=risk_color,
            anchor="e",
        ).pack(side="right")

        # Description
        ctk.CTkLabel(
            self,
            text=description,
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x", padx=CARD_PADDING, pady=(0, 8))

        # Zone resultats (vide par defaut)
        self.result_label = ctk.CTkLabel(
            self,
            text="En attente de scan...",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        self.result_label.pack(fill="x", padx=CARD_PADDING, pady=(0, 5))

        # Compteur issues
        self.count_label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["body"],
            text_color=COLORS["text"],
            anchor="w",
        )
        self.count_label.pack(fill="x", padx=CARD_PADDING, pady=(0, CARD_PADDING))

    def update_result(self, scan_result: ScanResult) -> None:
        """Met a jour la card avec les resultats du scan."""
        if scan_result.has_issues:
            self.result_label.configure(
                text=scan_result.summary,
                text_color=RISK_COLORS.get(self._risk_level, COLORS["warning"]),
            )
            self.count_label.configure(
                text=f"{scan_result.issue_count} probleme(s) detecte(s)",
                text_color=COLORS["text"],
            )
        else:
            self.result_label.configure(
                text="Aucun probleme detecte",
                text_color=COLORS["success"],
            )
            self.count_label.configure(text="")

    def set_scanning(self) -> None:
        """Affiche l'etat de scan en cours."""
        self.result_label.configure(
            text="Scan en cours...",
            text_color=COLORS["info"],
        )
        self.count_label.configure(text="")


class DashboardPage(ctk.CTkFrame):
    """Page dashboard avec vue d'ensemble des modules."""

    def __init__(self, parent: ctk.CTkFrame, engine: Engine, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.engine = engine
        self._cards: dict[str, ModuleCard] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._create_header()
        self._create_cards_area()

    def _create_header(self) -> None:
        """Header avec titre + bouton scan global."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 15))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Dashboard",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        # Bouton scan global
        self.scan_btn = ctk.CTkButton(
            header,
            text="Scanner tout",
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            height=38,
            corner_radius=8,
            command=self._run_scan,
        )
        self.scan_btn.grid(row=0, column=1, sticky="e")

        # Status bar
        self.status_label = ctk.CTkLabel(
            header,
            text=f"{len(self.engine.modules)} modules charges",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.status_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

        # Progress bar (cachee par defaut)
        self.progress = ctk.CTkProgressBar(
            header,
            fg_color=COLORS["border"],
            progress_color=COLORS["accent"],
            height=4,
        )
        self.progress.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.progress.set(0)
        self.progress.grid_remove()

    def _create_cards_area(self) -> None:
        """Grille de cards pour chaque module."""
        # Scrollable frame
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        # Cree une card par module
        row, col = 0, 0
        for mod in self.engine.modules.values():
            card = ModuleCard(
                scroll,
                module_name=mod.name,
                description=mod.description,
                risk_level=mod.risk_level.value,
            )
            card.grid(row=row, column=col, sticky="nsew", padx=8, pady=8)
            self._cards[mod.name] = card

            col += 1
            if col > 1:
                col = 0
                row += 1

    def _run_scan(self) -> None:
        """Lance le scan global en arriere-plan."""
        self.scan_btn.configure(state="disabled", text="Scan en cours...")
        self.progress.grid()
        self.progress.set(0)

        for card in self._cards.values():
            card.set_scanning()

        self.status_label.configure(text="Scan en cours...")

        # Lance dans un thread pour ne pas bloquer la GUI
        thread = threading.Thread(target=self._scan_worker, daemon=True)
        thread.start()

    def _scan_worker(self) -> None:
        """Worker de scan (execute dans un thread)."""
        modules = list(self.engine.modules.keys())
        total = len(modules)
        total_issues = 0

        for i, name in enumerate(modules):
            try:
                result = self.engine.scan_module(name)
                total_issues += result.issue_count
                # Met a jour la card dans le thread principal
                self.after(0, self._cards[name].update_result, result)
            except Exception:
                pass

            progress = (i + 1) / total
            self.after(0, self.progress.set, progress)

        # Fin du scan
        self.after(0, self._scan_complete, total_issues)

    def _scan_complete(self, total_issues: int) -> None:
        """Callback fin de scan."""
        self.scan_btn.configure(state="normal", text="Scanner tout")
        self.status_label.configure(
            text=f"Scan termine — {total_issues} probleme(s) detecte(s)",
            text_color=COLORS["success"] if total_issues == 0 else COLORS["warning"],
        )
        self.progress.set(1)
