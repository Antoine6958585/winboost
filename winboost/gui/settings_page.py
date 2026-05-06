"""Settings Page — Configuration profil, API, langue, modules (Phase 9)."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from winboost.core.config import PROFILE_SETTINGS, Config
from winboost.gui.theme import COLORS, FONTS, RISK_COLORS

# Descriptions des profils
PROFILE_INFO = {
    "safe": {
        "label": "Safe",
        "desc": "Mode prudent. Dry-run obligatoire, risque max = low.",
        "color": COLORS["success"],
        "risk": "low",
    },
    "power_user": {
        "label": "Power User",
        "desc": "Mode intermediaire. Actions medium autorisees.",
        "color": COLORS["warning"],
        "risk": "medium",
    },
    "expert": {
        "label": "Expert",
        "desc": "Mode avance. Toutes les actions sauf critical auto-bloque.",
        "color": COLORS["error"],
        "risk": "high",
    },
}


class ProfileCard(ctk.CTkFrame):
    """Carte de selection de profil."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        profile_key: str,
        is_active: bool,
        on_select: Any,
        **kwargs: Any,
    ) -> None:
        info = PROFILE_INFO[profile_key]
        border_color = info["color"] if is_active else COLORS["border"]
        border_width = 2 if is_active else 1

        super().__init__(
            parent,
            fg_color=COLORS["bg_card"],
            corner_radius=10,
            border_color=border_color,
            border_width=border_width,
            **kwargs,
        )
        self.pack(fill="x", pady=4)

        self._profile_key = profile_key
        self._on_select = on_select

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="x", padx=12, pady=10)

        # Header : nom + badge risque
        header = ctk.CTkFrame(content, fg_color="transparent")
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text=info["label"],
            font=FONTS["subheading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        risk_color = RISK_COLORS.get(info["risk"], COLORS["info"])
        ctk.CTkLabel(
            header,
            text=f" {info['risk'].upper()} ",
            font=("Segoe UI", 9, "bold"),
            text_color="#ffffff",
            fg_color=risk_color,
            corner_radius=4,
            height=18,
        ).pack(side="left", padx=(8, 0))

        if is_active:
            ctk.CTkLabel(
                header,
                text="ACTIF",
                font=("Segoe UI", 9, "bold"),
                text_color=info["color"],
            ).pack(side="right")

        # Description
        ctk.CTkLabel(
            content,
            text=info["desc"],
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

        # Bouton
        if not is_active:
            ctk.CTkButton(
                content,
                text="Activer",
                font=FONTS["small"],
                fg_color=info["color"],
                hover_color=COLORS["accent_hover"],
                text_color="#ffffff",
                height=28,
                width=80,
                corner_radius=6,
                command=self._select,
            ).pack(anchor="e", pady=(6, 0))

    def _select(self) -> None:
        if self._on_select:
            self._on_select(self._profile_key)


class SettingsPage(ctk.CTkFrame):
    """Page de configuration WinBoost."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        config: Config,
        on_profile_change: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self._config = config
        self._on_profile_change = on_profile_change

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 15))

        ctk.CTkLabel(
            header,
            text="Parametres",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        # --- Contenu scrollable ---
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))

        # === Section Profil ===
        self._add_section_title(scroll, "Profil de securite")
        self._profile_container = ctk.CTkFrame(scroll, fg_color="transparent")
        self._profile_container.pack(fill="x", pady=(0, 15))
        self._render_profiles()

        # === Section API Keys ===
        self._add_section_title(scroll, "Cles API (optionnel)")

        api_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        api_frame.pack(fill="x", pady=(0, 15))

        # Anthropic
        self._anthropic_entry = self._add_api_field(
            api_frame, "Anthropic API Key", "ANTHROPIC_API_KEY",
            self._config.get("anthropic_api_key", ""),
        )

        # OpenAI
        self._openai_entry = self._add_api_field(
            api_frame, "OpenAI API Key", "OPENAI_API_KEY",
            self._config.get("openai_api_key", ""),
        )

        # Ollama URL
        self._ollama_entry = self._add_api_field(
            api_frame, "Ollama URL", "http://localhost:11434",
            self._config.get("ollama_url", "http://localhost:11434"),
            is_secret=False,
        )

        # Bouton sauvegarder API
        ctk.CTkButton(
            api_frame,
            text="Sauvegarder les cles",
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            height=34,
            corner_radius=8,
            command=self._save_api_keys,
        ).pack(padx=12, pady=(4, 12))

        self._api_status = ctk.CTkLabel(
            api_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["success"],
        )
        self._api_status.pack(padx=12, pady=(0, 8))

        # === Section Langue ===
        self._add_section_title(scroll, "Langue")

        lang_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        lang_frame.pack(fill="x", pady=(0, 15))

        lang_inner = ctk.CTkFrame(lang_frame, fg_color="transparent")
        lang_inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            lang_inner,
            text="Interface et reponses :",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(side="left")

        self._lang_var = ctk.StringVar(value=self._config.get("language", "fr"))
        lang_menu = ctk.CTkOptionMenu(
            lang_inner,
            values=["fr", "en"],
            variable=self._lang_var,
            font=FONTS["body"],
            fg_color=COLORS["bg_dark"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_card"],
            width=80,
            command=self._on_lang_change,
        )
        lang_menu.pack(side="right")

        # === Section Modules ===
        self._add_section_title(scroll, "Modules actifs")

        modules_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        modules_frame.pack(fill="x", pady=(0, 15))

        self._module_vars: dict[str, ctk.BooleanVar] = {}
        all_modules = [
            ("temp_cleaner", "Nettoyeur de fichiers temporaires"),
            ("system_info", "Informations systeme"),
            ("startup_manager", "Gestionnaire de demarrage"),
            ("ram_optimizer", "Optimiseur RAM"),
            ("disk_analyzer", "Analyseur de disque"),
            ("privacy_cleaner", "Nettoyeur vie privee"),
            ("dev_cache_cleaner", "Nettoyeur caches developpeur"),
            ("service_optimizer", "Optimiseur de services"),
        ]
        enabled = self._config.modules_enabled

        for mod_name, mod_desc in all_modules:
            var = ctk.BooleanVar(value=mod_name in enabled)
            self._module_vars[mod_name] = var

            row = ctk.CTkFrame(modules_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)

            ctk.CTkCheckBox(
                row,
                text=f"{mod_desc}  ({mod_name})",
                font=FONTS["body"],
                text_color=COLORS["text_secondary"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                variable=var,
                command=self._on_modules_change,
            ).pack(side="left")

        # Padding bas
        ctk.CTkFrame(modules_frame, fg_color="transparent", height=8).pack()

        # === Section Infos ===
        self._add_section_title(scroll, "Informations")

        info_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        info_frame.pack(fill="x", pady=(0, 15))

        info_lines = [
            ("Version", "v0.1.0 (Phase 9)"),
            ("Config", str(self._config._file)),
            ("Profil", self._config.profile.upper()),
            ("Risque max", self._config.max_risk.upper()),
            ("Dry-run", "Oui" if self._config.dry_run_first else "Non"),
        ]

        for label, value in info_lines:
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(
                row, text=f"{label} :", font=FONTS["small"],
                text_color=COLORS["text_muted"], anchor="w", width=100,
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=value, font=FONTS["small"],
                text_color=COLORS["text"], anchor="w",
            ).pack(side="left", padx=(4, 0))

        ctk.CTkFrame(info_frame, fg_color="transparent", height=8).pack()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_section_title(self, parent: ctk.CTkFrame, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=FONTS["heading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", pady=(10, 6))

    def _add_api_field(
        self,
        parent: ctk.CTkFrame,
        label: str,
        placeholder: str,
        value: str,
        is_secret: bool = True,
    ) -> ctk.CTkEntry:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(8, 2))
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row, text=label, font=FONTS["body"],
            text_color=COLORS["text_secondary"], anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        entry = ctk.CTkEntry(
            row,
            placeholder_text=placeholder,
            font=FONTS["mono"],
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            height=32,
            corner_radius=6,
            show="*" if is_secret else "",
        )
        entry.grid(row=0, column=1, sticky="ew")
        if value:
            entry.insert(0, value)

        return entry

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _render_profiles(self) -> None:
        """Affiche les cartes de profil."""
        for widget in self._profile_container.winfo_children():
            widget.destroy()

        current = self._config.profile
        for key in PROFILE_SETTINGS:
            ProfileCard(
                self._profile_container,
                profile_key=key,
                is_active=(key == current),
                on_select=self._on_profile_select,
            )

    def _on_profile_select(self, profile_key: str) -> None:
        """Change le profil actif."""
        self._config.profile = profile_key
        self._config.save()
        self._render_profiles()

        if self._on_profile_change:
            self._on_profile_change(profile_key)

    def _save_api_keys(self) -> None:
        """Sauvegarde les cles API dans la config."""
        anthropic_key = self._anthropic_entry.get().strip()
        openai_key = self._openai_entry.get().strip()
        ollama_url = self._ollama_entry.get().strip()

        if anthropic_key:
            self._config.set("anthropic_api_key", anthropic_key)
        if openai_key:
            self._config.set("openai_api_key", openai_key)
        if ollama_url:
            self._config.set("ollama_url", ollama_url)

        self._config.save()
        self._api_status.configure(text="Cles sauvegardees !", text_color=COLORS["success"])
        self.after(3000, lambda: self._api_status.configure(text=""))

    def _on_lang_change(self, value: str) -> None:
        """Change la langue."""
        self._config.set("language", value)
        self._config.save()

    def _on_modules_change(self) -> None:
        """Met a jour la liste des modules actifs."""
        enabled = [name for name, var in self._module_vars.items() if var.get()]
        self._config.set("modules_enabled", enabled)
        self._config.save()
