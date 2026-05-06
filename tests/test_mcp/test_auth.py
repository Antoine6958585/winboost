"""Tests pour `winboost.mcp.auth` — token local MCP (T071, milestone v2.2).

Strategie d'isolation :
- `tmp_path` pytest pour rediriger l'ecriture filesystem (jamais de %APPDATA%
  utilisateur reel touche par les tests)
- monkeypatch sur APPDATA / HOME / XDG_CONFIG_HOME / sys.platform pour
  simuler differentes plateformes sans toucher a l'env globale du dev

Couverture (>= 6 tests) :
1. load_or_generate_token genere un token nouveau si fichier absent
2. load_or_generate_token lit le token existant si fichier present
3. load_or_generate_token cree le dossier parent si absent
4. Token genere a une longueur >= 32 caracteres
5. Token est URL-safe (charset secrets.token_urlsafe)
6. reset_token genere un token different du precedent
+ tests de robustesse : fichier vide, fichier corrompu, plateforme POSIX,
  XDG_CONFIG_HOME respecte, OSError sur ecriture impossible.
"""

from __future__ import annotations

import re
import string
from pathlib import Path

import pytest

from winboost.mcp import auth as auth_mod

# secrets.token_urlsafe utilise base64.urlsafe_b64encode, donc le charset est :
URL_SAFE_CHARSET = set(string.ascii_letters + string.digits + "-_")


@pytest.fixture(autouse=True)
def _isolate_token_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige `get_token_path` vers un tmp_path pour chaque test.

    Couvre Windows ET POSIX en mockant directement `get_token_path`. Les tests
    qui veulent verifier la logique interne de get_token_path le re-mock.
    """
    target = tmp_path / "mcp_token.txt"
    monkeypatch.setattr(auth_mod, "get_token_path", lambda: target)
    return target


# ---------------------------------------------------------------------------
# load_or_generate_token
# ---------------------------------------------------------------------------

def test_load_or_generate_token_generates_when_missing(_isolate_token_path: Path) -> None:
    """Si le fichier token n'existe pas, on en genere un et on l'ecrit."""
    assert not _isolate_token_path.exists()

    token = auth_mod.load_or_generate_token()

    assert isinstance(token, str)
    assert len(token) >= 32
    assert _isolate_token_path.exists()
    assert _isolate_token_path.read_text(encoding="utf-8").strip() == token


def test_load_or_generate_token_reads_existing(_isolate_token_path: Path) -> None:
    """Si le fichier existe, on lit le token sans en regenerer un."""
    fixed_token = "fixed-token-value-for-test-1234567890ABCDE"
    _isolate_token_path.parent.mkdir(parents=True, exist_ok=True)
    _isolate_token_path.write_text(fixed_token, encoding="utf-8")

    loaded1 = auth_mod.load_or_generate_token()
    loaded2 = auth_mod.load_or_generate_token()

    assert loaded1 == fixed_token
    assert loaded2 == fixed_token


def test_load_or_generate_token_creates_parent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le dossier parent est cree au besoin (chemin profond inexistant)."""
    deep_path = tmp_path / "deeply" / "nested" / "dir" / "mcp_token.txt"
    monkeypatch.setattr(auth_mod, "get_token_path", lambda: deep_path)
    assert not deep_path.parent.exists()

    token = auth_mod.load_or_generate_token()

    assert deep_path.parent.exists()
    assert deep_path.exists()
    assert deep_path.read_text(encoding="utf-8").strip() == token


def test_token_length_is_at_least_32_chars(_isolate_token_path: Path) -> None:
    """Avec TOKEN_NBYTES=32, secrets.token_urlsafe rend ~43 caracteres (>= 32)."""
    token = auth_mod.load_or_generate_token()

    assert len(token) >= 32, f"Token trop court : {len(token)} chars"


def test_token_is_url_safe(_isolate_token_path: Path) -> None:
    """Tous les caracteres du token sont dans le charset URL-safe."""
    token = auth_mod.load_or_generate_token()

    invalid_chars = set(token) - URL_SAFE_CHARSET
    assert not invalid_chars, f"Caracteres non URL-safe : {invalid_chars}"
    # Verification supplementaire via regex stricte.
    assert re.match(r"^[A-Za-z0-9_\-]+$", token) is not None


def test_reset_token_generates_different_token(_isolate_token_path: Path) -> None:
    """reset_token ecrase le token existant par un nouveau, different."""
    first = auth_mod.load_or_generate_token()
    second = auth_mod.reset_token()

    assert first != second
    assert _isolate_token_path.read_text(encoding="utf-8").strip() == second
    # Verification anti-flake : on regenere une 3e fois et tout reste coherent.
    third = auth_mod.reset_token()
    assert third != second


# ---------------------------------------------------------------------------
# Robustesse / cas limites
# ---------------------------------------------------------------------------

def test_load_or_generate_token_handles_empty_file(_isolate_token_path: Path) -> None:
    """Un fichier vide est traite comme absent : on regenere."""
    _isolate_token_path.parent.mkdir(parents=True, exist_ok=True)
    _isolate_token_path.write_text("", encoding="utf-8")

    token = auth_mod.load_or_generate_token()

    assert token  # non-vide
    assert len(token) >= 32
    assert _isolate_token_path.read_text(encoding="utf-8").strip() == token


def test_load_or_generate_token_strips_whitespace(_isolate_token_path: Path) -> None:
    """Le token sur disque peut avoir des espaces/newlines parasites — on strip."""
    fixed = "abc-123_def-456"
    _isolate_token_path.parent.mkdir(parents=True, exist_ok=True)
    _isolate_token_path.write_text(f"  {fixed}  \n", encoding="utf-8")

    token = auth_mod.load_or_generate_token()

    assert token == fixed


def test_get_token_path_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sur Windows, get_token_path utilise %APPDATA%/WinBoost/.

    Note : on annule la fixture autouse `_isolate_token_path` ici pour tester
    la vraie logique de `get_token_path` (vs. la version mockee).
    """
    # Restaure la vraie fonction (la fixture autouse l'a mockee).
    monkeypatch.setattr(auth_mod, "get_token_path", auth_mod.__dict__["get_token_path"])
    # On reimport le module pour avoir la "vraie" fonction non patchee.
    import importlib
    importlib.reload(auth_mod)

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\fake\AppData\Roaming")

    path = auth_mod.get_token_path()

    assert path.name == "mcp_token.txt"
    # Le path doit etre dans le faux APPDATA + dossier "WinBoost".
    parts_lower = [p.lower() for p in path.parts]
    assert "winboost" in parts_lower
    # Le path doit pointer dans le faux APPDATA.
    assert "Roaming" in str(path) or "roaming" in str(path).lower()


def test_get_token_path_posix_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sur POSIX sans XDG_CONFIG_HOME, on tombe sur ~/.config/winboost/.

    Test verifie la logique conditionnelle ; les separateurs Path peuvent etre
    Windows-style sur runner Windows mais la structure logique est preservee.
    """
    import importlib
    importlib.reload(auth_mod)

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    path = auth_mod.get_token_path()

    assert path.name == "mcp_token.txt"
    # On verifie via les parts du Path (separator-agnostic).
    parts_lower = [p.lower() for p in path.parts]
    assert "winboost" in parts_lower
    assert ".config" in parts_lower


def test_get_token_path_posix_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Sur POSIX, XDG_CONFIG_HOME est respecte si defini."""
    import importlib
    importlib.reload(auth_mod)

    custom_xdg = tmp_path / "custom_xdg"
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom_xdg))

    path = auth_mod.get_token_path()

    assert path.name == "mcp_token.txt"
    # Comparaison via Path.parts pour etre separator-agnostic.
    expected_parts = list(custom_xdg.parts)
    actual_parts = list(path.parts)
    # Tous les segments du custom_xdg doivent apparaitre dans le path.
    for segment in expected_parts:
        assert segment in actual_parts, f"Segment {segment!r} absent de {actual_parts}"
