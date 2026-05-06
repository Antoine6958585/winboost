"""Themes de diagnostic — un fichier par theme.

Chaque theme expose une fonction `get_checks() -> list[Check]` que le runner
appelle pour materialiser les checks. Pour ajouter un theme :

1. Creer `winboost/diagnose/themes/{nom}.py`
2. Implementer `get_checks() -> list[Check]`
3. Enregistrer dans `winboost.diagnose.runner.THEME_REGISTRY` + THEME_KEYWORDS
4. Ajouter les tests dans `tests/test_diagnose/`
"""

from __future__ import annotations

from winboost.diagnose.themes import audio, bluetooth, display, gaming, network

__all__ = ["audio", "bluetooth", "display", "gaming", "network"]
