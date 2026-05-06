"""Build le serveur POC en .exe via PyInstaller.

Genere `dist/poc_mcp_server.exe` (depuis A:/dev/winboost/) en console mode +
onefile. Ce sont les flags qu'on utilisera pour le futur winboost-mcp si
le verdict est GO.

Le build est intentionnellement minimal : pas de hidden imports, pas de data
files, pas d'icone. On teste UNIQUEMENT la couche transport stdio.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_SCRIPT = REPO_ROOT / "tests" / "mcp_compat" / "poc_mcp_server.py"
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = REPO_ROOT / "build" / "poc_mcp_server"
SPEC_FILE = REPO_ROOT / "poc_mcp_server.spec"


def main() -> int:
    if not SERVER_SCRIPT.exists():
        print(f"Script serveur introuvable : {SERVER_SCRIPT}")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--console",  # IMPORTANT : sans console, stdin/stdout sont rediriges vers null
        "--name",
        "poc_mcp_server",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR.parent),
        "--specpath",
        str(REPO_ROOT),
        str(SERVER_SCRIPT),
    ]
    print(f"[build] cmd={cmd}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        print(f"[build] PyInstaller a echoue (code {result.returncode})")
        return result.returncode

    exe = DIST_DIR / "poc_mcp_server.exe"
    if not exe.exists():
        print(f"[build] .exe introuvable apres build : {exe}")
        return 1

    size_kb = exe.stat().st_size / 1024
    print(f"[build] OK : {exe} ({size_kb:.0f} Ko)")
    return 0


def cleanup() -> None:
    """Supprime les artefacts de build pour ne pas polluer le repo.

    Garde uniquement tests/mcp_compat/ et VERDICT.md. Supprime :
    - dist/poc_mcp_server.exe
    - build/poc_mcp_server/
    - poc_mcp_server.spec (a la racine)
    """
    exe = DIST_DIR / "poc_mcp_server.exe"
    if exe.exists():
        exe.unlink()
        print(f"[cleanup] supprime {exe}")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        print(f"[cleanup] supprime {BUILD_DIR}")
    if SPEC_FILE.exists():
        SPEC_FILE.unlink()
        print(f"[cleanup] supprime {SPEC_FILE}")


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        cleanup()
        sys.exit(0)
    sys.exit(main())
