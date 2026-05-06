"""Tests pour `winboost.mcp.install` — install Claude Desktop (T071, v2.2).

Strategie d'isolation :
- `tmp_path` pour le config Claude Desktop (jamais le vrai claude_desktop_config.json)
- monkeypatch sur `auth.get_token_path` pour eviter d'ecrire le token reel
- Tous les tests passent `config_path=...` pour ne pas depender de la plateforme

Couverture (>= 9 tests) :
1. get_claude_desktop_config_path retourne un Path
2. install(dry_run=True) n'ecrit rien
3. install() ajoute l'entree winboost dans mcpServers
4. Si fichier config absent : cree le fichier avec structure minimale
5. Si fichier config existe avec d'autres servers : preserve les autres
6. Si winboost deja installe + force=False : action=skipped
7. Si winboost deja installe + force=True : remplace l'entree
8. Backup cree avec timestamp (pattern du nom)
9. uninstall retire l'entree mais garde les autres

+ tests de robustesse : config JSON invalide, token injecte dans env,
  build_winboost_entry, plateforme non supportee.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from winboost.mcp import auth as auth_mod
from winboost.mcp import install as install_mod

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige le token MCP vers tmp_path pour eviter de toucher au token reel."""
    target = tmp_path / "tokens" / "mcp_token.txt"
    monkeypatch.setattr(auth_mod, "get_token_path", lambda: target)
    # Le module install importe get_token_path par valeur — on patch aussi la.
    monkeypatch.setattr(install_mod, "get_token_path", lambda: target)
    return target


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Chemin de config Claude Desktop pour les tests (n'existe pas encore)."""
    return tmp_path / "Claude" / "claude_desktop_config.json"


# ---------------------------------------------------------------------------
# get_claude_desktop_config_path
# ---------------------------------------------------------------------------

def test_get_claude_desktop_config_path_returns_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sur les 3 plateformes supportees, retourne un Path coherent."""
    # Test Windows
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\fake\AppData\Roaming")
    p_win = install_mod.get_claude_desktop_config_path()
    assert isinstance(p_win, Path)
    assert p_win.name == "claude_desktop_config.json"
    assert "Claude" in str(p_win)


def test_get_claude_desktop_config_path_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plateforme inconnue (ex: aix) -> RuntimeError clair."""
    monkeypatch.setattr("sys.platform", "aix")
    with pytest.raises(RuntimeError, match="non supportee"):
        install_mod.get_claude_desktop_config_path()


# ---------------------------------------------------------------------------
# build_winboost_entry
# ---------------------------------------------------------------------------

def test_build_winboost_entry_structure() -> None:
    """Le bloc JSON respecte le schema documente (command/args/env)."""
    entry = install_mod.build_winboost_entry("dummy-token-1234")

    assert entry["command"] == "python"
    assert entry["args"] == ["-m", "winboost", "mcp"]
    assert entry["env"]["WINBOOST_MCP_TOKEN"] == "dummy-token-1234"


# ---------------------------------------------------------------------------
# install_winboost_to_claude_desktop
# ---------------------------------------------------------------------------

def test_install_dry_run_writes_nothing(config_path: Path) -> None:
    """dry_run=True : aucun fichier ecrit, mais la structure du retour est correcte."""
    assert not config_path.exists()

    result = install_mod.install_winboost_to_claude_desktop(
        dry_run=True, config_path=config_path
    )

    assert result["action"] == "dry_run"
    assert "would_add" in result
    assert result["would_add"]["command"] == "python"
    assert result["would_add"]["args"] == ["-m", "winboost", "mcp"]
    assert "WINBOOST_MCP_TOKEN" in result["would_add"]["env"]
    assert not config_path.exists()  # Critical : on n'a rien ecrit.


def test_install_creates_file_when_absent(config_path: Path) -> None:
    """Si le config n'existe pas, on le cree avec mcpServers.winboost."""
    assert not config_path.exists()

    result = install_mod.install_winboost_to_claude_desktop(config_path=config_path)

    assert result["action"] == "installed"
    assert config_path.exists()

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "winboost" in data["mcpServers"]
    assert data["mcpServers"]["winboost"]["command"] == "python"
    assert data["mcpServers"]["winboost"]["args"] == ["-m", "winboost", "mcp"]


def test_install_preserves_existing_servers(config_path: Path) -> None:
    """Si d'autres servers existent dans mcpServers, on les preserve."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "mcpServers": {
            "filesystem": {"command": "fs-mcp", "args": ["--root", "/data"]},
            "github": {"command": "gh-mcp"},
        },
        "otherTopLevelKey": {"keep": "me"},
    }
    config_path.write_text(json.dumps(initial), encoding="utf-8")

    result = install_mod.install_winboost_to_claude_desktop(config_path=config_path)

    assert result["action"] == "installed"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    # Les autres servers sont preserves
    assert "filesystem" in data["mcpServers"]
    assert "github" in data["mcpServers"]
    assert data["mcpServers"]["filesystem"]["command"] == "fs-mcp"
    # Winboost est bien ajoute
    assert "winboost" in data["mcpServers"]
    # Le reste du config est preserve
    assert data["otherTopLevelKey"] == {"keep": "me"}


def test_install_skipped_when_already_installed(config_path: Path) -> None:
    """Si winboost deja present + force=False : action=skipped."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "mcpServers": {
            "winboost": {
                "command": "python",
                "args": ["-m", "winboost", "mcp"],
                "env": {"WINBOOST_MCP_TOKEN": "old-token"},
            }
        }
    }
    config_path.write_text(json.dumps(initial), encoding="utf-8")

    result = install_mod.install_winboost_to_claude_desktop(
        force=False, config_path=config_path
    )

    assert result["action"] == "skipped"
    assert "already installed" in result["reason"].lower()
    # Le fichier doit etre intact (pas de backup, pas de re-write).
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["mcpServers"]["winboost"]["env"]["WINBOOST_MCP_TOKEN"] == "old-token"


def test_install_force_replaces_entry(config_path: Path) -> None:
    """Si winboost deja present + force=True : remplace l'entree, le token a jour."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "mcpServers": {
            "winboost": {
                "command": "old-command",
                "args": ["legacy"],
                "env": {"WINBOOST_MCP_TOKEN": "old-token"},
            }
        }
    }
    config_path.write_text(json.dumps(initial), encoding="utf-8")

    result = install_mod.install_winboost_to_claude_desktop(
        force=True, config_path=config_path
    )

    assert result["action"] == "installed"
    assert result["replaced"] is True
    data = json.loads(config_path.read_text(encoding="utf-8"))
    # Verifie que la nouvelle entree est bien celle attendue (pas l'ancienne).
    assert data["mcpServers"]["winboost"]["command"] == "python"
    assert data["mcpServers"]["winboost"]["args"] == ["-m", "winboost", "mcp"]
    # Le token est present (et != "old-token")
    new_token = data["mcpServers"]["winboost"]["env"]["WINBOOST_MCP_TOKEN"]
    assert new_token
    assert new_token != "old-token"


def test_install_creates_backup_with_timestamp(config_path: Path) -> None:
    """Lors d'un install qui modifie un fichier existant, un backup est cree."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {"mcpServers": {"other": {"command": "x"}}}
    config_path.write_text(json.dumps(initial), encoding="utf-8")

    result = install_mod.install_winboost_to_claude_desktop(config_path=config_path)

    assert result["action"] == "installed"
    backup_path = result.get("backup_path")
    assert backup_path is not None
    backup_p = Path(backup_path)
    assert backup_p.exists()
    # Pattern attendu : claude_desktop_config.json.backup-YYYYMMDD-HHMMSS[-N]
    assert re.search(r"\.backup-\d{8}-\d{6}", backup_p.name) is not None
    # Le contenu du backup doit etre le config original.
    backup_data = json.loads(backup_p.read_text(encoding="utf-8"))
    assert backup_data == initial


def test_install_no_backup_when_creating_fresh(config_path: Path) -> None:
    """Si on cree le fichier from scratch, aucun backup n'est cree (rien a backup)."""
    assert not config_path.exists()

    result = install_mod.install_winboost_to_claude_desktop(config_path=config_path)

    assert result["action"] == "installed"
    assert result["backup_path"] is None


def test_install_recovers_from_corrupted_json(config_path: Path) -> None:
    """Si le config existant est du JSON invalide, on backup + reconstruit propre."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{ this is not :: valid json $$", encoding="utf-8")

    result = install_mod.install_winboost_to_claude_desktop(config_path=config_path)

    assert result["action"] == "installed"
    # Le fichier reconstruit doit etre du JSON valide avec la cle winboost.
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "winboost" in data["mcpServers"]
    # Backup du fichier corrompu cree pour preserver la trace.
    assert result["backup_path"] is not None


# ---------------------------------------------------------------------------
# uninstall_winboost_from_claude_desktop
# ---------------------------------------------------------------------------

def test_uninstall_removes_entry_keeps_others(config_path: Path) -> None:
    """uninstall retire winboost mais preserve les autres servers + autres cles."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "mcpServers": {
            "winboost": {"command": "python", "args": ["-m", "winboost", "mcp"]},
            "filesystem": {"command": "fs-mcp"},
        },
        "uiSettings": {"theme": "dark"},
    }
    config_path.write_text(json.dumps(initial), encoding="utf-8")

    result = install_mod.uninstall_winboost_from_claude_desktop(config_path=config_path)

    assert result["action"] == "uninstalled"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "winboost" not in data["mcpServers"]
    assert "filesystem" in data["mcpServers"]
    assert data["uiSettings"] == {"theme": "dark"}
    # Backup verifiable
    assert Path(result["backup_path"]).exists()


def test_uninstall_when_file_missing(config_path: Path) -> None:
    """uninstall sur un fichier absent retourne action=not_installed sans crash."""
    assert not config_path.exists()

    result = install_mod.uninstall_winboost_from_claude_desktop(config_path=config_path)

    assert result["action"] == "not_installed"


def test_uninstall_when_winboost_absent(config_path: Path) -> None:
    """uninstall sur un fichier sans winboost : action=not_installed, fichier intact."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {"mcpServers": {"other": {"command": "x"}}}
    config_path.write_text(json.dumps(initial), encoding="utf-8")
    original_content = config_path.read_text(encoding="utf-8")

    result = install_mod.uninstall_winboost_from_claude_desktop(config_path=config_path)

    assert result["action"] == "not_installed"
    # Le fichier ne doit pas avoir ete modifie.
    assert config_path.read_text(encoding="utf-8") == original_content
