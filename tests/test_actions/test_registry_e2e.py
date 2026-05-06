"""Tests E2E — Validation du registre complet des 150 actions."""

from pathlib import Path

from winboost.actions.loader import ActionRegistry
from winboost.actions.schema import VALID_CATEGORIES

ACTIONS_DIR = Path(__file__).parent.parent.parent / "winboost" / "actions"


class TestRegistryE2E:
    """Valide l'ensemble du registre d'actions."""

    def _registry(self) -> ActionRegistry:
        r = ActionRegistry(actions_dir=ACTIONS_DIR)
        r.load_all()
        return r

    def test_load_185_actions(self):
        """Le registre charge exactement 185 actions (150 v2.0 + 30 v2.1 native + 5 v2.4 audio native)."""
        r = self._registry()
        assert r.count == 185, f"Attendu 185, obtenu {r.count}"

    def test_zero_errors(self):
        """Aucune erreur de validation."""
        r = self._registry()
        assert len(r.errors) == 0, f"Erreurs : {r.errors}"

    def test_all_categories_present(self):
        """Toutes les categories ont au moins une action."""
        r = self._registry()
        for cat in VALID_CATEGORIES:
            actions = r.list_by_category(cat)
            assert len(actions) > 0, f"Categorie vide : {cat}"

    def test_unique_ids(self):
        """Tous les IDs sont uniques."""
        r = self._registry()
        ids = [a.id for a in r.list_all()]
        assert len(ids) == len(set(ids)), f"IDs en double : {[i for i in ids if ids.count(i) > 1]}"

    def test_all_have_keywords(self):
        """Toutes les actions ont des mots-cles."""
        r = self._registry()
        for action in r.list_all():
            kw = action.get_keywords_flat()
            assert len(kw) > 0, f"Action sans keywords : {action.id}"

    def test_search_telemetrie(self):
        """La recherche 'telemetrie' retourne des resultats."""
        r = self._registry()
        results = r.search("telemetrie")
        assert len(results) > 0

    def test_search_performance(self):
        """La recherche 'performance' retourne des resultats."""
        r = self._registry()
        results = r.search("performance")
        assert len(results) > 0

    def test_category_counts(self):
        """Les categories ont le bon nombre d'actions."""
        r = self._registry()
        stats = r.stats()
        assert stats["privacy"] == 30
        assert stats["performance"] == 30
        assert stats["cleanup"] == 20
        assert stats["dev_tools"] == 20
        assert stats["network"] == 20  # 10 v2.0 + 10 v2.1 native
        assert stats["security"] == 10
        assert stats["appearance"] == 25  # 10 v2.0 + 10 v2.1 native + 5 v2.4 audio native
        assert stats["gaming"] == 10
        assert stats["system"] == 20  # 10 v2.0 + 10 v2.1 native
