"""Modules Page — Vue detaillee de chaque module avec scan/fix individuel."""

from __future__ import annotations

import threading
from typing import Any

import customtkinter as ctk

from winboost.core.base_module import ScanResult
from winboost.core.engine import Engine
from winboost.gui.theme import COLORS, FONTS, RISK_COLORS, CARD_PADDING


class ModuleDetailCard(ctk.CTkFrame):
    """Card detaillee d'un module avec scan, preview et fix."""

    def __init__(self, parent: ctk.CTkFrame, engine: Engine,
                 module_name: str, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=12, **kwargs)
        self.engine = engine
        self.module_name = module_name
        self._scan_result: ScanResult | None = None

        mod = engine.get_module(module_name)
        if mod is None:
            return

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 8))

        ctk.CTkLabel(
            header,
            text=module_name.replace("_", " ").title(),
            font=FONTS["heading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        risk_color = RISK_COLORS.get(mod.risk_level.value, COLORS["info"])
        ctk.CTkLabel(
            header,
            text=f"Risque : {mod.risk_level.value.upper()}",
            font=FONTS["small"],
            text_color=risk_color,
        ).pack(side="right")

        # Description
        ctk.CTkLabel(
            self,
            text=mod.description,
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x", padx=CARD_PADDING, pady=(0, 10))

        # Boutons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=CARD_PADDING, pady=(0, 10))

        self.scan_btn = ctk.CTkButton(
            btn_frame,
            text="Scanner",
            font=FONTS["body"],
            fg_color=COLORS["info"],
            hover_color="#2980b9",
            height=32,
            width=120,
            corner_radius=6,
            command=self._run_scan,
        )
        self.scan_btn.pack(side="left", padx=(0, 8))

        self.fix_btn = ctk.CTkButton(
            btn_frame,
            text="Corriger",
            font=FONTS["body"],
            fg_color=COLORS["success"],
            hover_color="#27ae60",
            height=32,
            width=120,
            corner_radius=6,
            state="disabled",
            command=self._run_fix,
        )
        self.fix_btn.pack(side="left")

        # Zone resultats
        self.results_text = ctk.CTkTextbox(
            self,
            height=150,
            font=FONTS["mono"],
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            state="disabled",
        )
        self.results_text.pack(fill="x", padx=CARD_PADDING, pady=(0, CARD_PADDING))

    def _set_results_text(self, text: str) -> None:
        """Ecrit dans la zone de resultats."""
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("1.0", text)
        self.results_text.configure(state="disabled")

    def _run_scan(self) -> None:
        """Lance le scan du module."""
        self.scan_btn.configure(state="disabled", text="Scan...")
        self.fix_btn.configure(state="disabled")
        self._set_results_text("Scan en cours...")
        thread = threading.Thread(target=self._scan_worker, daemon=True)
        thread.start()

    def _scan_worker(self) -> None:
        """Worker scan en arriere-plan."""
        try:
            result = self.engine.scan_module(self.module_name)
            self._scan_result = result
            preview = self.engine.preview_module(self.module_name, result)
            self.after(0, self._scan_complete, result, preview)
        except Exception as e:
            self.after(0, self._set_results_text, f"Erreur : {e}")
            self.after(0, self.scan_btn.configure, {"state": "normal", "text": "Scanner"})

    def _scan_complete(self, result: ScanResult, preview: str) -> None:
        """Callback fin de scan."""
        self.scan_btn.configure(state="normal", text="Scanner")
        self._set_results_text(preview)
        if result.has_issues:
            fixable = sum(1 for i in result.issues if i.auto_fixable)
            if fixable > 0:
                self.fix_btn.configure(state="normal")

    def _run_fix(self) -> None:
        """Lance le fix du module."""
        if self._scan_result is None:
            return
        self.fix_btn.configure(state="disabled", text="Correction...")
        thread = threading.Thread(target=self._fix_worker, daemon=True)
        thread.start()

    def _fix_worker(self) -> None:
        """Worker fix en arriere-plan."""
        try:
            result = self.engine.fix_module(self.module_name, self._scan_result)  # type: ignore[arg-type]
            lines = [result.summary, ""]
            if result.fixed:
                lines.append(f"Corriges ({len(result.fixed)}) :")
                for f in result.fixed[:10]:
                    lines.append(f"  + {f}")
            if result.skipped:
                lines.append(f"\nIgnores ({len(result.skipped)}) :")
                for s in result.skipped[:10]:
                    lines.append(f"  - {s}")
            if result.errors:
                lines.append(f"\nErreurs ({len(result.errors)}) :")
                for e in result.errors[:5]:
                    lines.append(f"  ! {e}")

            text = "\n".join(lines)
            self.after(0, self._fix_complete, text)
        except Exception as e:
            self.after(0, self._set_results_text, f"Erreur : {e}")
            self.after(0, self.fix_btn.configure, {"state": "normal", "text": "Corriger"})

    def _fix_complete(self, text: str) -> None:
        """Callback fin de fix."""
        self.fix_btn.configure(state="disabled", text="Corriger")
        self._scan_result = None
        self._set_results_text(text)


class ModulesPage(ctk.CTkFrame):
    """Page listant tous les modules avec actions individuelles."""

    def __init__(self, parent: ctk.CTkFrame, engine: Engine, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.engine = engine

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        ctk.CTkLabel(
            self,
            text="Modules",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=25, pady=(25, 15))

        # Scrollable
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        scroll.grid_columnconfigure(0, weight=1)

        # Une card par module
        for i, name in enumerate(engine.list_modules()):
            card = ModuleDetailCard(scroll, engine, name)
            card.grid(row=i, column=0, sticky="ew", padx=5, pady=8)
