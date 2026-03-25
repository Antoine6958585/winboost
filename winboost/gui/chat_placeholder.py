"""Chat Placeholder — Interface de chat IA (non connectee en v1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import customtkinter as ctk

from winboost.gui.theme import COLORS, FONTS


class ChatBubble(ctk.CTkFrame):
    """Bulle de message dans le chat."""

    def __init__(self, parent: ctk.CTkFrame, text: str, is_user: bool = True,
                 **kwargs: Any) -> None:
        bg = COLORS["accent"] if is_user else COLORS["bg_card"]
        super().__init__(parent, fg_color=bg, corner_radius=12, **kwargs)

        # Alignement
        anchor = "e" if is_user else "w"
        self.pack(fill="x", padx=(80 if is_user else 15, 15 if is_user else 80), pady=4)

        ctk.CTkLabel(
            self,
            text=text,
            font=FONTS["body"],
            text_color=COLORS["text"],
            wraplength=500,
            justify="left",
            anchor="w",
        ).pack(padx=12, pady=8, fill="x")


class ChatPage(ctk.CTkFrame):
    """Page de chat IA — placeholder pour v2."""

    def __init__(self, parent: ctk.CTkFrame, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 15))

        ctk.CTkLabel(
            header,
            text="Chat IA",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="v2.0 — bientot disponible",
            font=FONTS["small"],
            text_color=COLORS["accent"],
        ).pack(side="right")

        # Zone de messages (scrollable)
        self.messages_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
        )
        self.messages_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))

        # Message de bienvenue
        self._add_bot_message(
            "Salut ! Je suis l'assistant WinBoost.\n\n"
            "En v2, je pourrai analyser ton systeme et appliquer des optimisations "
            "juste en discutant.\n\n"
            "Pour l'instant, utilise le Dashboard ou les Modules pour scanner et corriger."
        )

        # Zone de saisie
        input_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        input_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        input_frame.grid_columnconfigure(0, weight=1)

        self.input_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Ecris un message... (disponible en v2)",
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

    def _on_send(self, event: Any = None) -> None:
        """Gere l'envoi d'un message."""
        text = self.input_entry.get().strip()
        if not text:
            return

        self.input_entry.delete(0, "end")
        self._add_user_message(text)

        # Reponse placeholder
        self._add_bot_message(
            "Cette fonctionnalite sera disponible en v2.0.\n"
            "Utilise le Dashboard pour scanner ton systeme maintenant !"
        )

    def _add_user_message(self, text: str) -> None:
        """Ajoute un message utilisateur."""
        ChatBubble(self.messages_frame, text, is_user=True)
        self._scroll_to_bottom()

    def _add_bot_message(self, text: str) -> None:
        """Ajoute un message bot."""
        ChatBubble(self.messages_frame, text, is_user=False)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        """Scroll vers le bas des messages."""
        self.messages_frame.after(50, self.messages_frame._parent_canvas.yview_moveto, 1.0)
