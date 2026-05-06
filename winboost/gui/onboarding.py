"""Onboarding — Assistant premier lancement WinBoost (Phase 9)."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from winboost.core.config import Config
from winboost.gui.theme import COLORS, FONTS

# Descriptions detaillees pour l'onboarding
PROFILE_DETAILS = {
    "safe": {
        "label": "Safe (Recommande)",
        "icon": "SAFE",
        "desc": (
            "Mode prudent pour debutants.\n"
            "- Dry-run obligatoire avant chaque action\n"
            "- Seules les actions a faible risque sont autorisees\n"
            "- Confirmation requise pour toute modification"
        ),
        "color": COLORS["success"],
    },
    "power_user": {
        "label": "Power User",
        "icon": "POWER",
        "desc": (
            "Mode intermediaire pour utilisateurs avises.\n"
            "- Actions a risque moyen autorisees\n"
            "- Pas de dry-run obligatoire\n"
            "- Confirmation requise pour les actions medium+"
        ),
        "color": COLORS["warning"],
    },
    "expert": {
        "label": "Expert",
        "icon": "EXPERT",
        "desc": (
            "Mode avance pour administrateurs.\n"
            "- Toutes les actions sauf critical\n"
            "- Controle total sur le systeme\n"
            "- Dry-run et confirmation uniquement pour high+"
        ),
        "color": COLORS["error"],
    },
}


class OnboardingWizard(ctk.CTkToplevel):
    """Assistant de premier lancement WinBoost."""

    def __init__(
        self,
        parent: Any,
        config: Config,
        on_complete: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)

        self._config = config
        self._on_complete = on_complete
        self._selected_profile: str = "safe"
        self._step = 0

        # Fenetre
        self.title("WinBoost — Premier lancement")
        width, height = 600, 520
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        # Protocole fermeture
        self.protocol("WM_DELETE_WINDOW", self._on_skip)

        # Container principal
        self._container = ctk.CTkFrame(self, fg_color="transparent")
        self._container.pack(fill="both", expand=True, padx=30, pady=20)

        # Affiche l'etape 1
        self._show_step_welcome()

    # ------------------------------------------------------------------
    # Etape 1 : Bienvenue
    # ------------------------------------------------------------------

    def _show_step_welcome(self) -> None:
        self._clear_container()
        self._step = 1

        ctk.CTkLabel(
            self._container,
            text="Bienvenue sur WinBoost !",
            font=("Segoe UI", 28, "bold"),
            text_color=COLORS["accent"],
        ).pack(pady=(30, 10))

        ctk.CTkLabel(
            self._container,
            text="L'assistant Windows qui ne te ment pas.",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
        ).pack(pady=(0, 30))

        features = [
            "8 modules d'optimisation systeme",
            "150+ actions intelligentes",
            "Chat IA conversationnel",
            "Sauvegarde et undo automatiques",
            "Profils de securite adaptatifs",
        ]

        for feat in features:
            row = ctk.CTkFrame(self._container, fg_color="transparent")
            row.pack(fill="x", padx=40, pady=2)

            ctk.CTkLabel(
                row,
                text="->",
                font=FONTS["body"],
                text_color=COLORS["accent"],
                width=30,
            ).pack(side="left")

            ctk.CTkLabel(
                row,
                text=feat,
                font=FONTS["body"],
                text_color=COLORS["text"],
                anchor="w",
            ).pack(side="left")

        # Navigation
        self._add_nav(show_back=False, next_text="Commencer", next_cmd=self._show_step_profile)

    # ------------------------------------------------------------------
    # Etape 2 : Choix du profil
    # ------------------------------------------------------------------

    def _show_step_profile(self) -> None:
        self._clear_container()
        self._step = 2

        ctk.CTkLabel(
            self._container,
            text="Choisis ton profil",
            font=FONTS["title"],
            text_color=COLORS["text"],
        ).pack(pady=(10, 5))

        ctk.CTkLabel(
            self._container,
            text="Tu pourras le changer a tout moment dans les parametres.",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        ).pack(pady=(0, 15))

        # Cartes de profil
        self._profile_buttons: dict[str, ctk.CTkFrame] = {}

        for key, info in PROFILE_DETAILS.items():
            is_selected = key == self._selected_profile
            card = ctk.CTkFrame(
                self._container,
                fg_color=COLORS["bg_card"],
                corner_radius=10,
                border_color=info["color"] if is_selected else COLORS["border"],
                border_width=2 if is_selected else 1,
                cursor="hand2",
            )
            card.pack(fill="x", pady=4)
            self._profile_buttons[key] = card

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=12, pady=8)

            # Badge + label
            header = ctk.CTkFrame(inner, fg_color="transparent")
            header.pack(fill="x")

            ctk.CTkLabel(
                header,
                text=f" {info['icon']} ",
                font=("Segoe UI", 9, "bold"),
                text_color="#ffffff",
                fg_color=info["color"],
                corner_radius=4,
                height=20,
            ).pack(side="left", padx=(0, 8))

            ctk.CTkLabel(
                header,
                text=info["label"],
                font=FONTS["subheading"],
                text_color=COLORS["text"],
                anchor="w",
            ).pack(side="left")

            if is_selected:
                ctk.CTkLabel(
                    header,
                    text="SELECTIONNE",
                    font=("Segoe UI", 9, "bold"),
                    text_color=info["color"],
                ).pack(side="right")

            ctk.CTkLabel(
                inner,
                text=info["desc"],
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=(4, 0))

            # Bind click
            for widget in [card, inner]:
                widget.bind("<Button-1>", lambda e, k=key: self._select_profile(k))

        # Navigation
        self._add_nav(
            show_back=True,
            back_cmd=self._show_step_welcome,
            next_text="Suivant",
            next_cmd=self._show_step_api,
        )

    def _select_profile(self, key: str) -> None:
        """Selectionne un profil."""
        self._selected_profile = key
        self._show_step_profile()

    # ------------------------------------------------------------------
    # Etape 3 : Configuration API (optionnel)
    # ------------------------------------------------------------------

    def _show_step_api(self) -> None:
        self._clear_container()
        self._step = 3

        ctk.CTkLabel(
            self._container,
            text="Configuration IA (optionnel)",
            font=FONTS["title"],
            text_color=COLORS["text"],
        ).pack(pady=(10, 5))

        ctk.CTkLabel(
            self._container,
            text=(
                "Le chat IA fonctionne deja avec le cache local (70% des requetes).\n"
                "Ajoute une cle API pour les requetes complexes."
            ),
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            justify="center",
        ).pack(pady=(0, 20))

        # Anthropic
        api_frame = ctk.CTkFrame(self._container, fg_color=COLORS["bg_card"], corner_radius=10)
        api_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            api_frame, text="Anthropic API Key (Claude)",
            font=FONTS["body"], text_color=COLORS["text_secondary"],
        ).pack(padx=12, pady=(10, 4), anchor="w")

        self._api_anthropic = ctk.CTkEntry(
            api_frame,
            placeholder_text="sk-ant-...",
            font=FONTS["mono"],
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            height=34,
            show="*",
        )
        self._api_anthropic.pack(fill="x", padx=12, pady=(0, 10))

        # OpenAI
        ctk.CTkLabel(
            api_frame, text="OpenAI API Key (optionnel)",
            font=FONTS["body"], text_color=COLORS["text_secondary"],
        ).pack(padx=12, pady=(4, 4), anchor="w")

        self._api_openai = ctk.CTkEntry(
            api_frame,
            placeholder_text="sk-...",
            font=FONTS["mono"],
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            height=34,
            show="*",
        )
        self._api_openai.pack(fill="x", padx=12, pady=(0, 12))

        # Info
        ctk.CTkLabel(
            self._container,
            text="Les cles sont stockees localement dans la config WinBoost.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(pady=(5, 0))

        # Navigation
        self._add_nav(
            show_back=True,
            back_cmd=self._show_step_profile,
            next_text="Terminer",
            next_cmd=self._finish,
        )

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------

    def _finish(self) -> None:
        """Applique les choix et ferme l'onboarding."""
        # Profil
        self._config.profile = self._selected_profile

        # API keys
        anthropic = self._api_anthropic.get().strip()
        openai = self._api_openai.get().strip()
        if anthropic:
            self._config.set("anthropic_api_key", anthropic)
        if openai:
            self._config.set("openai_api_key", openai)

        # Marque l'onboarding comme complete
        self._config.set("onboarding_done", True)
        self._config.save()

        self.grab_release()
        self.destroy()

        if self._on_complete:
            self._on_complete(self._selected_profile)

    def _on_skip(self) -> None:
        """Ferme l'onboarding sans sauvegarder (utilise profil safe par defaut)."""
        self._config.set("onboarding_done", True)
        self._config.save()

        self.grab_release()
        self.destroy()

        if self._on_complete:
            self._on_complete("safe")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_container(self) -> None:
        for widget in self._container.winfo_children():
            widget.destroy()

    def _add_nav(
        self,
        show_back: bool = True,
        back_cmd: Any = None,
        next_text: str = "Suivant",
        next_cmd: Any = None,
    ) -> None:
        """Ajoute la barre de navigation en bas."""
        spacer = ctk.CTkFrame(self._container, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # Indicateur d'etape
        steps_frame = ctk.CTkFrame(self._container, fg_color="transparent")
        steps_frame.pack(pady=(5, 8))

        for i in range(1, 4):
            color = COLORS["accent"] if i == self._step else COLORS["border"]
            ctk.CTkFrame(
                steps_frame,
                width=30,
                height=4,
                fg_color=color,
                corner_radius=2,
            ).pack(side="left", padx=3)

        nav = ctk.CTkFrame(self._container, fg_color="transparent")
        nav.pack(fill="x")

        if show_back:
            ctk.CTkButton(
                nav,
                text="Retour",
                font=FONTS["body"],
                fg_color=COLORS["border"],
                hover_color=COLORS["bg_sidebar"],
                text_color=COLORS["text"],
                height=36,
                width=100,
                corner_radius=8,
                command=back_cmd,
            ).pack(side="left")

        ctk.CTkButton(
            nav,
            text=next_text,
            font=FONTS["body"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            height=36,
            width=120,
            corner_radius=8,
            command=next_cmd,
        ).pack(side="right")


def should_show_onboarding(config: Config) -> bool:
    """Verifie si l'onboarding doit etre affiche."""
    return not config.get("onboarding_done", False)
