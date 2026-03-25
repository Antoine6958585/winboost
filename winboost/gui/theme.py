"""Theme et constantes visuelles WinBoost."""

from __future__ import annotations

# Couleurs principales
COLORS = {
    "bg_dark": "#1a1a2e",
    "bg_card": "#16213e",
    "bg_sidebar": "#0f3460",
    "bg_input": "#1a1a2e",
    "accent": "#e94560",
    "accent_hover": "#ff6b81",
    "text": "#ffffff",
    "text_secondary": "#a0a0b0",
    "text_muted": "#6c6c80",
    "success": "#2ecc71",
    "warning": "#f39c12",
    "error": "#e74c3c",
    "info": "#3498db",
    "border": "#2a2a4a",
}

# Couleurs par niveau de risque
RISK_COLORS = {
    "info": COLORS["info"],
    "low": COLORS["success"],
    "medium": COLORS["warning"],
    "high": "#e67e22",
    "critical": COLORS["error"],
}

# Polices
FONTS = {
    "title": ("Segoe UI", 24, "bold"),
    "heading": ("Segoe UI", 16, "bold"),
    "subheading": ("Segoe UI", 13, "bold"),
    "body": ("Segoe UI", 12),
    "small": ("Segoe UI", 10),
    "mono": ("Consolas", 11),
}

# Dimensions
SIDEBAR_WIDTH = 220
WINDOW_MIN_WIDTH = 1100
WINDOW_MIN_HEIGHT = 700
CARD_PADDING = 15
