"""App — Fenetre principale WinBoost (CustomTkinter)."""

from __future__ import annotations

import customtkinter as ctk

from winboost.core.config import Config
from winboost.core.engine import Engine
from winboost.gui.theme import COLORS, FONTS, SIDEBAR_WIDTH, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT


class WinBoostApp(ctk.CTk):
    """Fenetre principale de l'application WinBoost."""

    def __init__(self) -> None:
        super().__init__()

        # Config et engine
        self.config = Config()
        self.engine = Engine(self.config)
        self.engine.discover_modules()

        # Fenetre
        self.title("WinBoost")
        self.geometry(f"{WINDOW_MIN_WIDTH}x{WINDOW_MIN_HEIGHT}")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=COLORS["bg_dark"])

        # Layout principal : sidebar + contenu
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._create_sidebar()
        self._create_content_area()

        # Page par defaut
        self._current_page: str = ""
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._show_page("dashboard")

    def _create_sidebar(self) -> None:
        """Cree la barre laterale de navigation."""
        self.sidebar = ctk.CTkFrame(
            self,
            width=SIDEBAR_WIDTH,
            corner_radius=0,
            fg_color=COLORS["bg_sidebar"],
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Logo / Titre
        title_label = ctk.CTkLabel(
            self.sidebar,
            text="WinBoost",
            font=FONTS["title"],
            text_color=COLORS["accent"],
        )
        title_label.pack(pady=(30, 5))

        subtitle = ctk.CTkLabel(
            self.sidebar,
            text="Windows Assistant",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        subtitle.pack(pady=(0, 30))

        # Boutons navigation
        nav_items = [
            ("Dashboard", "dashboard"),
            ("Modules", "modules"),
            ("Chat IA", "chat"),
        ]

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        for label, page_id in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"  {label}",
                font=FONTS["body"],
                anchor="w",
                height=40,
                corner_radius=8,
                fg_color="transparent",
                hover_color=COLORS["bg_card"],
                text_color=COLORS["text"],
                command=lambda pid=page_id: self._show_page(pid),
            )
            btn.pack(fill="x", padx=15, pady=3)
            self._nav_buttons[page_id] = btn

        # Spacer
        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # Profil en bas
        profile_frame = ctk.CTkFrame(
            self.sidebar, fg_color=COLORS["bg_card"], corner_radius=8
        )
        profile_frame.pack(fill="x", padx=15, pady=15)

        ctk.CTkLabel(
            profile_frame,
            text=f"Profil : {self.config.profile.upper()}",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        ).pack(pady=8)

        # Version
        ctk.CTkLabel(
            self.sidebar,
            text="v0.1.0",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(pady=(0, 10))

    def _create_content_area(self) -> None:
        """Cree la zone de contenu principale."""
        self.content = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_dark"],
            corner_radius=0,
        )
        self.content.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _show_page(self, page_id: str) -> None:
        """Affiche une page dans la zone de contenu."""
        if page_id == self._current_page:
            return

        # Met a jour la nav
        for pid, btn in self._nav_buttons.items():
            if pid == page_id:
                btn.configure(fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
            else:
                btn.configure(fg_color="transparent", hover_color=COLORS["bg_card"])

        # Cache la page courante
        if self._current_page in self._pages:
            self._pages[self._current_page].grid_forget()

        # Cree ou affiche la nouvelle page
        if page_id not in self._pages:
            self._pages[page_id] = self._create_page(page_id)

        self._pages[page_id].grid(row=0, column=0, sticky="nsew")
        self._current_page = page_id

    def _create_page(self, page_id: str) -> ctk.CTkFrame:
        """Fabrique une page selon son identifiant."""
        if page_id == "dashboard":
            from winboost.gui.dashboard import DashboardPage
            return DashboardPage(self.content, self.engine)

        if page_id == "modules":
            from winboost.gui.modules_page import ModulesPage
            return ModulesPage(self.content, self.engine)

        if page_id == "chat":
            from winboost.gui.chat import ChatPage
            return ChatPage(self.content, config=self.config)

        # Page par defaut
        frame = ctk.CTkFrame(self.content, fg_color=COLORS["bg_dark"])
        ctk.CTkLabel(
            frame, text=f"Page '{page_id}' non implementee",
            font=FONTS["heading"], text_color=COLORS["text_secondary"],
        ).pack(expand=True)
        return frame


class SplashScreen(ctk.CTkToplevel):
    """Splash screen affiche au lancement."""

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.overrideredirect(True)

        width, height = 400, 250
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.configure(fg_color=COLORS["bg_sidebar"])

        ctk.CTkLabel(
            self, text="WinBoost", font=("Segoe UI", 36, "bold"),
            text_color=COLORS["accent"],
        ).pack(pady=(50, 5))

        ctk.CTkLabel(
            self, text="Windows AI System Assistant",
            font=FONTS["body"], text_color=COLORS["text_secondary"],
        ).pack(pady=(0, 20))

        self.status = ctk.CTkLabel(
            self, text="Chargement des modules...",
            font=FONTS["small"], text_color=COLORS["text_muted"],
        )
        self.status.pack()

        self.progress = ctk.CTkProgressBar(
            self, fg_color=COLORS["border"], progress_color=COLORS["accent"],
            width=300, height=4,
        )
        self.progress.pack(pady=(15, 0))
        self.progress.set(0)

        ctk.CTkLabel(
            self, text="v0.1.0", font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(side="bottom", pady=10)

    def update_progress(self, value: float, text: str = "") -> None:
        self.progress.set(value)
        if text:
            self.status.configure(text=text)
        self.update()


def launch_gui() -> None:
    """Point d'entree pour lancer la GUI avec splash screen."""
    app = WinBoostApp()

    # Splash screen
    splash = SplashScreen(app)
    app.withdraw()

    splash.update_progress(0.3, "Initialisation...")
    app.after(200, lambda: splash.update_progress(0.6, "Modules charges."))
    app.after(500, lambda: splash.update_progress(1.0, "Pret !"))

    def _close_splash() -> None:
        splash.destroy()
        app.deiconify()

    app.after(900, _close_splash)
    app.mainloop()
