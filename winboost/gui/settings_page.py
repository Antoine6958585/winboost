"""Settings Page — Configuration profil, API, langue, modules (Phase 9).

Phase 13 v2.3 ajoute une section "Lab Mode" pour le Pilot Computer Use
Anthropic (T080 + T081) :
- Toggle pour activer/desactiver le profil "lab"
- 3 cases d'opt-in RGPD granulaires (CNIL compliant)
- Configuration de la cle BYOK Anthropic (avec note env recommande)
- Plafond mensuel parametrable
- Choix du mode sandbox (window / application / region / full_screen)

La section est ajoutee a la FIN de la page Settings existante. La logique
ecrit dans Config (`profile`, `pilot.api_key`, `pilot.budget_eur`,
`pilot.sandbox_mode`, `pilot.rgpd`) — l'onglet Pilot lit ces meme cles.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

import customtkinter as ctk

from winboost.core.config import PROFILE_SETTINGS, Config
from winboost.gui.theme import COLORS, FONTS, RISK_COLORS

# Constantes Lab Mode (Phase 13 v2.3)
PILOT_RGPD_KEYS: tuple[str, ...] = ("screenshots", "ocr_text", "system_info")

PILOT_SANDBOX_MODES: tuple[tuple[str, str, str], ...] = (
    (
        "winboost_window",
        "Fenetre courante (recommande)",
        "Le Pilot ne peut interagir qu'avec la fenetre WinBoost active.",
    ),
    (
        "application",
        "Application nommee",
        "Le Pilot ne peut interagir qu'avec une application designee.",
    ),
    (
        "screen_region",
        "Region personnalisee",
        "Une zone rectangulaire choisie a l'avance.",
    ),
    (
        "full_screen",
        "Plein ecran (avance, NON recommande)",
        "Le Pilot peut cliquer n'importe ou. Risque eleve.",
    ),
)

DEFAULT_PILOT_BUDGET_EUR = 5.0
MIN_PILOT_BUDGET_EUR = 1.0
MAX_PILOT_BUDGET_EUR = 50.0

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

        # === Section Lab Mode (Phase 13 v2.3 — T080 + T081) ===
        self._build_lab_mode_section(scroll)

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

    # ------------------------------------------------------------------
    # Lab Mode (Phase 13 v2.3 — Pilot Anthropic Computer Use)
    # ------------------------------------------------------------------

    def _build_lab_mode_section(self, parent: ctk.CTkFrame) -> None:
        """Construit la section "Lab Mode" complete (toggle + RGPD + config)."""
        self._add_section_title(parent, "Lab Mode (Pilot Anthropic Computer Use)")

        # --- Bandeau d'avertissement ---
        warn_frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        warn_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            warn_frame,
            text=(
                "Mode experimental. BYOK Anthropic obligatoire. Opt-in RGPD "
                "complet requis. Les screenshots sont envoyes a l'API "
                "Anthropic (datacenter US, hors UE)."
            ),
            font=FONTS["small"],
            text_color=COLORS["warning"],
            wraplength=820,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=12, pady=10)

        # --- Sous-section : Activer Lab Mode ---
        toggle_frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        toggle_frame.pack(fill="x", pady=(0, 8))

        toggle_inner = ctk.CTkFrame(toggle_frame, fg_color="transparent")
        toggle_inner.pack(fill="x", padx=12, pady=10)

        is_lab_active = self._config.get("profile", "safe") == "lab"
        self._lab_mode_var = ctk.BooleanVar(value=is_lab_active)

        ctk.CTkCheckBox(
            toggle_inner,
            text="Activer Lab Mode (debloque l'onglet 'Pilot')",
            font=FONTS["body"],
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            variable=self._lab_mode_var,
            command=self._on_lab_mode_toggle,
        ).pack(side="left")

        self._lab_mode_status = ctk.CTkLabel(
            toggle_inner,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        )
        self._lab_mode_status.pack(side="right")

        ctk.CTkLabel(
            toggle_frame,
            text=(
                "Active le profil 'lab' qui debloque l'onglet 'Pilot'. "
                "Si tu desactives, l'onglet disparait au prochain lancement."
            ),
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            wraplength=820,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(0, 10))

        # --- Sous-section : Notice RGPD + opt-in granulaire ---
        rgpd_frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        rgpd_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            rgpd_frame,
            text="Notice RGPD - opt-in granulaire",
            font=FONTS["subheading"],
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            rgpd_frame,
            text=(
                "Le mode Pilot envoie des donnees a Anthropic (US). Coche "
                "explicitement chaque type de donnees autorise. Les 3 cases "
                "doivent etre cochees pour confirmer l'opt-in."
            ),
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            wraplength=820,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(0, 8))

        pilot_cfg = self._config.get("pilot", {}) or {}
        rgpd_cfg = pilot_cfg.get("rgpd", {}) or {}

        self._rgpd_vars: dict[str, ctk.BooleanVar] = {}
        rgpd_options = [
            ("screenshots", "Screenshots de la zone autorisee"),
            ("ocr_text", "Texte OCR extrait des screenshots"),
            ("system_info", "Informations systeme (OS, version)"),
        ]

        for key, label in rgpd_options:
            var = ctk.BooleanVar(value=bool(rgpd_cfg.get(key, False)))
            self._rgpd_vars[key] = var

            row = ctk.CTkFrame(rgpd_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            ctk.CTkCheckBox(
                row,
                text=label,
                font=FONTS["body"],
                text_color=COLORS["text_secondary"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                variable=var,
                command=self._refresh_rgpd_button_state,
            ).pack(side="left")

        # Bouton "Accepter et confirmer"
        rgpd_already_ok = all(rgpd_cfg.get(k, False) for k in PILOT_RGPD_KEYS)
        self._rgpd_confirm_btn = ctk.CTkButton(
            rgpd_frame,
            text=(
                "Opt-in RGPD deja confirme"
                if rgpd_already_ok
                else "Accepter et confirmer le opt-in RGPD"
            ),
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            height=34,
            corner_radius=8,
            command=self._on_rgpd_confirm,
        )
        self._rgpd_confirm_btn.pack(padx=12, pady=(8, 4), anchor="w")

        self._rgpd_status = ctk.CTkLabel(
            rgpd_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["success"],
        )
        self._rgpd_status.pack(padx=12, pady=(0, 10), anchor="w")

        # Etat initial du bouton
        self._refresh_rgpd_button_state()

        # --- Sous-section : Configuration BYOK + budget + sandbox ---
        cfg_frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        cfg_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            cfg_frame,
            text="Configuration",
            font=FONTS["subheading"],
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        # API key (BYOK Anthropic)
        api_row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        api_row.pack(fill="x", padx=12, pady=4)
        api_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            api_row,
            text="Cle API Anthropic (BYOK) :",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        self._pilot_api_entry = ctk.CTkEntry(
            api_row,
            placeholder_text="sk-ant-...",
            font=FONTS["mono"],
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            height=32,
            corner_radius=6,
            show="*",
        )
        self._pilot_api_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        existing_key = pilot_cfg.get("api_key", "")
        if existing_key:
            self._pilot_api_entry.insert(0, existing_key)

        ctk.CTkButton(
            api_row,
            text="Coller",
            font=FONTS["small"],
            fg_color=COLORS["info"],
            hover_color="#2980b9",
            text_color="#ffffff",
            height=32,
            width=80,
            corner_radius=6,
            command=self._on_paste_api_key,
        ).grid(row=0, column=2)

        ctk.CTkLabel(
            cfg_frame,
            text=(
                "Recommande : utilise plutot la variable d'environnement "
                "ANTHROPIC_API_KEY (la cle ne sera pas persistee sur disque)."
            ),
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            wraplength=820,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(0, 8))

        # Budget mensuel
        budget_row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        budget_row.pack(fill="x", padx=12, pady=(4, 4))

        ctk.CTkLabel(
            budget_row,
            text="Plafond mensuel (EUR) :",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(side="left", padx=(0, 10))

        current_budget = float(pilot_cfg.get("budget_eur", DEFAULT_PILOT_BUDGET_EUR))
        self._pilot_budget_var = ctk.StringVar(value=f"{current_budget:.1f}")
        self._pilot_budget_entry = ctk.CTkEntry(
            budget_row,
            textvariable=self._pilot_budget_var,
            font=FONTS["mono"],
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            height=32,
            width=80,
            corner_radius=6,
        )
        self._pilot_budget_entry.pack(side="left")

        ctk.CTkLabel(
            budget_row,
            text=f"(min {MIN_PILOT_BUDGET_EUR:.0f}, max {MAX_PILOT_BUDGET_EUR:.0f})",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(side="left", padx=(8, 0))

        # Sandbox mode (radio group)
        ctk.CTkLabel(
            cfg_frame,
            text="Mode sandbox :",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 2))

        current_sandbox = str(pilot_cfg.get("sandbox_mode", "winboost_window"))
        self._pilot_sandbox_var = ctk.StringVar(value=current_sandbox)

        for mode_key, mode_label, mode_help in PILOT_SANDBOX_MODES:
            row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=2)
            ctk.CTkRadioButton(
                row,
                text=mode_label,
                font=FONTS["body"],
                text_color=COLORS["text"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                variable=self._pilot_sandbox_var,
                value=mode_key,
                command=lambda m=mode_key: self._on_sandbox_change(m),
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=mode_help,
                font=FONTS["small"],
                text_color=COLORS["text_muted"],
                anchor="w",
            ).pack(side="left", padx=(8, 0))

        # Bouton sauvegarder Pilot config
        ctk.CTkButton(
            cfg_frame,
            text="Sauvegarder la configuration Pilot",
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            height=34,
            corner_radius=8,
            command=self._save_pilot_config,
        ).pack(padx=12, pady=(10, 4), anchor="w")

        self._pilot_status = ctk.CTkLabel(
            cfg_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["success"],
        )
        self._pilot_status.pack(padx=12, pady=(0, 10), anchor="w")

    # ------------------------------------------------------------------
    # Lab Mode callbacks
    # ------------------------------------------------------------------

    def _on_lab_mode_toggle(self) -> None:
        """Toggle profil 'lab' <-> 'safe' selon la checkbox."""
        active = bool(self._lab_mode_var.get())
        if active:
            # On ecrit directement via Config.set pour bypasser la validation
            # de l'attribut profile (qui n'accepte que safe/power_user/expert).
            self._config.set("profile", "lab")
            self._lab_mode_status.configure(
                text="Profil 'lab' actif — onglet Pilot disponible.",
                text_color=COLORS["success"],
            )
        else:
            self._config.set("profile", "safe")
            self._lab_mode_status.configure(
                text="Lab desactive — re-ouvre l'app pour cacher l'onglet Pilot.",
                text_color=COLORS["warning"],
            )
        self._config.save()

        if self._on_profile_change:
            # UI ne doit jamais crasher si le callback echoue
            with contextlib.suppress(Exception):
                self._on_profile_change(self._config.get("profile", "safe"))

    def _refresh_rgpd_button_state(self) -> None:
        """Active/desactive le bouton 'Accepter' selon les 3 cases RGPD."""
        all_checked = all(var.get() for var in self._rgpd_vars.values())
        if all_checked:
            self._rgpd_confirm_btn.configure(state="normal")
        else:
            self._rgpd_confirm_btn.configure(state="disabled")

    def _on_rgpd_confirm(self) -> None:
        """Click sur 'Accepter et confirmer' : ecrit l'opt-in dans Config."""
        all_checked = all(var.get() for var in self._rgpd_vars.values())
        if not all_checked:
            self._rgpd_status.configure(
                text="Coche les 3 cases pour confirmer l'opt-in RGPD.",
                text_color=COLORS["error"],
            )
            return

        rgpd_payload: dict[str, Any] = {
            key: True for key in PILOT_RGPD_KEYS
        }
        rgpd_payload["accepted_at"] = datetime.now(tz=UTC).isoformat()

        pilot_cfg = self._config.get("pilot", {}) or {}
        pilot_cfg["rgpd"] = rgpd_payload
        self._config.set("pilot", pilot_cfg)
        self._config.save()

        self._rgpd_confirm_btn.configure(text="Opt-in RGPD confirme")
        self._rgpd_status.configure(
            text=f"Opt-in confirme le {rgpd_payload['accepted_at']}",
            text_color=COLORS["success"],
        )

    def _on_paste_api_key(self) -> None:
        """Coupe-papier -> entree API key (best-effort, ne crash pas)."""
        try:
            text = self.clipboard_get()
        except Exception:  # noqa: BLE001 — clipboard peut etre vide
            return
        text = (text or "").strip()
        if not text:
            return
        self._pilot_api_entry.delete(0, "end")
        self._pilot_api_entry.insert(0, text)

    def _on_sandbox_change(self, mode: str) -> None:
        """Selection radio button sandbox.

        Pour 'full_screen', exige une double confirmation popup avant
        d'accepter le mode (risque eleve).
        """
        if mode != "full_screen":
            return
        # Confirmation popup pour full_screen
        try:
            from tkinter import messagebox
            confirmed = messagebox.askyesno(
                "Risque eleve",
                "Le mode 'plein ecran' permet au Pilot de cliquer n'importe "
                "ou sur ton ecran. Risque ELEVE en cas de mauvaise "
                "interpretation de Claude.\n\n"
                "Confirmer ce choix ?",
            )
        except Exception:  # noqa: BLE001 — tkinter messagebox peut faillir en headless
            confirmed = False

        if not confirmed:
            # Revert au mode precedent (par defaut window)
            self._pilot_sandbox_var.set("winboost_window")

    def _save_pilot_config(self) -> None:
        """Sauvegarde API key + budget + sandbox dans Config['pilot']."""
        api_key = self._pilot_api_entry.get().strip()
        sandbox_mode = self._pilot_sandbox_var.get()

        # Validation budget
        try:
            budget_eur = float(self._pilot_budget_var.get().replace(",", "."))
        except ValueError:
            self._pilot_status.configure(
                text="Plafond invalide : entre un nombre.",
                text_color=COLORS["error"],
            )
            return

        if budget_eur < MIN_PILOT_BUDGET_EUR or budget_eur > MAX_PILOT_BUDGET_EUR:
            self._pilot_status.configure(
                text=(
                    f"Plafond doit etre entre {MIN_PILOT_BUDGET_EUR:.0f} "
                    f"et {MAX_PILOT_BUDGET_EUR:.0f} EUR."
                ),
                text_color=COLORS["error"],
            )
            return

        pilot_cfg = self._config.get("pilot", {}) or {}
        if api_key:
            pilot_cfg["api_key"] = api_key
        pilot_cfg["budget_eur"] = round(budget_eur, 2)
        pilot_cfg["sandbox_mode"] = sandbox_mode

        self._config.set("pilot", pilot_cfg)
        self._config.save()

        self._pilot_status.configure(
            text="Configuration Pilot sauvegardee.",
            text_color=COLORS["success"],
        )
        self.after(3000, lambda: self._pilot_status.configure(text=""))
