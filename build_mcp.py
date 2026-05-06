"""Build script pour `winboost-mcp.exe` — binaire MCP standalone (Polish A v2.4).

Genere `dist/winboost-mcp.exe` : un binaire dedie au serveur Model Context
Protocol, totalement decouple du `WinBoost.exe` GUI principal (62.5 Mo).

Pourquoi un binaire separe :

- Distribution massive via les registres MCP (smithery.ai, anthropic.com/mcp)
  necessite un binaire leger (~10-15 Mo, pas 62 Mo).
- Le `WinBoost.exe` GUI reste pur (zero dependance fastmcp/anthropic dans le
  binaire principal).
- Cold-start MCP plus rapide : pas de chargement CustomTkinter, PIL, ou des
  modules GUI lourds — seulement les couches business (router, registry,
  executor) + fastmcp.

Cible empirique de taille : 10-15 Mo ideal, jusqu'a 25 Mo acceptable.

Architecture du binaire :
- Entry point : `winboost/mcp/__main__.py` (UTF-8 reconfigure + run_stdio)
- Hidden imports : `winboost.mcp.*`, `winboost.actions.*`, `winboost.ai.*`,
  `winboost.core.*`, `winboost.modules.*` (pour Engine.scan_module).
- Exclusions agressives : tkinter, customtkinter, PIL, pyautogui, gui, pilot.
- Data files : actions YAML (180 actions, ~150 Ko cumule).
- Flags PyInstaller : `--onefile --console --name winboost-mcp`.

Le `--console` est OBLIGATOIRE (cf. invariant 3 du verdict T072 :
`tests/mcp_compat/VERDICT.md`). Sans console, stdin/stdout sont redirigees
vers NUL en l'absence de parent pipe — incompatible avec le double-clic
end-user (qui n'arrive jamais via Claude Desktop, mais arrive en debug).

Cohabite avec `build.py` : aucun fichier partage, aucun side-effect croise.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Hidden imports — strictement minimaux pour faire tourner le serveur MCP.
# Toute addition doit etre justifiee par un import direct ou indirect du code
# expose par les 5 tools (chat, scan, apply, list_actions, undo).
# ---------------------------------------------------------------------------
HIDDEN_IMPORTS = [
    # MCP — entry point + serveur + helpers
    "winboost.mcp",
    "winboost.mcp.__main__",
    "winboost.mcp.server",
    "winboost.mcp.serializers",
    "winboost.mcp.auth",
    "winboost.mcp.install",
    # Core — engine, executor, backup, history, config (utilises par 5 tools)
    "winboost.core.engine",
    "winboost.core.executor",
    "winboost.core.backup",
    "winboost.core.history",
    "winboost.core.config",
    "winboost.core.base_module",
    # AI Engine — router (chat tool) + parser + safety + cache
    # Note : winboost.ai.providers.* exclus volontairement. Le MCP ne lance
    # JAMAIS un LLM lui-meme (le client MCP — Claude Desktop, Cursor — gere
    # son propre modele). Le `chat` tool MCP route via cache + category
    # fallback uniquement, pas via LLM. Cette decision economise ~30 Mo
    # (anthropic + openai + httpx + pydantic + jiter + ...).
    "winboost.ai.action_router",
    "winboost.ai.nl_parser",
    "winboost.ai.safety_engine",
    "winboost.ai.cache",
    # Actions — registry + schema (loader des 180 YAML)
    "winboost.actions.loader",
    "winboost.actions.schema",
    # Modules — Engine.scan_module() les charge dynamiquement, donc tous
    # doivent etre dans le binaire MCP pour que `scan` fonctionne.
    "winboost.modules.temp_cleaner",
    "winboost.modules.system_info",
    "winboost.modules.startup_manager",
    "winboost.modules.ram_optimizer",
    "winboost.modules.disk_analyzer",
    "winboost.modules.privacy_cleaner",
    "winboost.modules.dev_cache_cleaner",
    "winboost.modules.service_optimizer",
    # Utils — windows_native (helpers WMI/PowerShell utilises par actions),
    # admin (verif elevation) et logger.
    "winboost.utils.windows_native",
    "winboost.utils.admin",
    "winboost.utils.logger",
    # FastMCP — explicite pour PyInstaller (sinon resolve dynamique mal vu)
    "fastmcp",
]

# ---------------------------------------------------------------------------
# Exclusions agressives — chaque module ici economise un paquet d'octets.
# La regle d'or : tout ce qui est GUI / pilot / Anthropic Computer Use
# n'a PAS sa place dans `winboost-mcp.exe`.
# ---------------------------------------------------------------------------
EXCLUDED_MODULES = [
    # GUI stack — gain estime ~25-30 Mo
    "tkinter",
    "_tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.filedialog",
    "tkinter.simpledialog",
    "customtkinter",
    "darkdetect",  # dep de customtkinter
    # Imagerie — gain estime ~10-15 Mo
    "PIL",
    "PIL.Image",
    "PIL.ImageGrab",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageTk",
    "Pillow",
    # Automation desktop — gain estime ~3-5 Mo
    "pyautogui",
    "pyscreeze",
    "pymsgbox",
    "pytweening",
    "mouseinfo",
    # Pilot / Computer Use — pas dans le binaire MCP
    "winboost.pilot",
    "winboost.pilot.anthropic_pilot",
    "winboost.pilot.screenshot_provider",
    "winboost.pilot.action_executor",
    "winboost.pilot.sandbox",
    "winboost.pilot.budget",
    "winboost.pilot.confirmation_ui",
    # GUI WinBoost — pas dans le binaire MCP
    "winboost.gui",
    "winboost.gui.app",
    "winboost.gui.dashboard",
    "winboost.gui.modules_page",
    "winboost.gui.chat",
    "winboost.gui.chat_placeholder",
    "winboost.gui.history_page",
    "winboost.gui.settings_page",
    "winboost.gui.onboarding",
    "winboost.gui.theme",
    "winboost.gui.diagnose_page",
    "winboost.gui.hotkey_overlay",
    "winboost.gui.pilot_page",
    # Diagnose — pas necessaire pour les 5 tools MCP (chat/scan/apply/list/undo)
    "winboost.diagnose",
    "winboost.diagnose.runner",
    "winboost.diagnose.checks",
    "winboost.diagnose.themes",
    # Hotkey overlay — dep keyboard non requise pour MCP
    "keyboard",
    # LLM provider SDKs — gain estime ~15-20 Mo. Le `chat` tool MCP route
    # via cache + category fallback ; le client MCP (Claude Desktop, Cursor)
    # gere lui-meme son LLM. Pas besoin d'embarquer ces SDK dans le binaire.
    # Note : on N'EXCLUT PAS httpx/pydantic/h11 — fastmcp en depend directement.
    "anthropic",
    "openai",
    "jiter",  # dep specifique aux SDK LLM (parsing JSON streaming)
    "tiktoken",
    "tokenizers",
    "winboost.ai.providers",
    "winboost.ai.providers.base",
    "winboost.ai.providers.anthropic_provider",
    "winboost.ai.providers.openai_provider",
    "winboost.ai.providers.ollama_provider",
    # Test stack — jamais dans un binaire ship
    "pytest",
    "pytest_mock",
    "pytest_cov",
    "ruff",
    "_pytest",
]


def build() -> int:
    """Lance le build PyInstaller pour `winboost-mcp.exe`.

    Returns:
        Code de sortie : 0 en cas de succes, 1 sinon.
    """
    root = Path(__file__).parent.resolve()
    entry_point = root / "winboost" / "mcp" / "__main__.py"

    print("=" * 60)
    print("WinBoost MCP — Build winboost-mcp.exe")
    print("=" * 60)

    if not entry_point.exists():
        print(f"[build_mcp] entry point introuvable : {entry_point}")
        return 1

    # Verifie PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[build_mcp] PyInstaller non installe. Installation...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"]
        )

    # Verifie fastmcp (extra mcp doit etre installe pour build)
    try:
        import fastmcp  # noqa: F401
    except ImportError:
        print(
            "[build_mcp] fastmcp manquant. Installe l'extra avant de build :\n"
            "    pip install -e .[mcp]"
        )
        return 1

    # ---------------------------------------------------------------------
    # Construit la commande PyInstaller
    # ---------------------------------------------------------------------
    cmd: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--name",
        "winboost-mcp",
        # OBLIGATOIRE — invariant 3 du verdict T072. Sans console, stdin/stdout
        # sont rediriges vers NUL en l'absence d'un parent process pipe.
        "--console",
        # Pas d'icone — c'est un serveur, pas une app graphique. Eventuel
        # ajout futur dans assets/icon-mcp.ico si on veut differencier.
    ]

    # Hidden imports
    for mod in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", mod])

    # Exclusions agressives
    for exc in EXCLUDED_MODULES:
        cmd.extend(["--exclude-module", exc])

    # Data files — les actions YAML sont chargees dynamiquement par
    # ActionRegistry, PyInstaller ne les detecte pas en analyse statique.
    actions_dir = root / "winboost" / "actions"
    if actions_dir.exists():
        for category_dir in sorted(actions_dir.iterdir()):
            if category_dir.is_dir() and not category_dir.name.startswith("_"):
                for yaml_file in category_dir.glob("*.yaml"):
                    dest = f"winboost/actions/{category_dir.name}"
                    # Sous Windows le separateur PyInstaller est `;`. Le module
                    # build est dedie Windows (cf. build.py) donc on assume.
                    cmd.extend(["--add-data", f"{yaml_file};{dest}"])

    # Entrypoint
    cmd.append(str(entry_point))

    # ---------------------------------------------------------------------
    # Run
    # ---------------------------------------------------------------------
    print(f"\n[build_mcp] Commande : {' '.join(cmd[:6])} ... [{len(cmd)} args]")
    result = subprocess.run(cmd, cwd=str(root))

    if result.returncode != 0:
        print(f"\n[build_mcp] Build echoue (code {result.returncode})")
        return result.returncode

    exe_path = root / "dist" / "winboost-mcp.exe"
    if not exe_path.exists():
        print("\n[build_mcp] Build termine mais .exe introuvable dans dist/")
        return 1

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"\n[build_mcp] OK : {exe_path} ({size_mb:.1f} Mo)")
    print(
        "[build_mcp] Cible : 10-15 Mo ideal, jusqu'a 25 Mo acceptable. "
        "Reference : WinBoost.exe = 62.5 Mo."
    )
    return 0


def main() -> int:
    """Alias public — utilise par les tests pour s'assurer que le module est
    callable sans deroulement complet PyInstaller. Equivalent a `build()`."""
    return build()


if __name__ == "__main__":
    sys.exit(build())
