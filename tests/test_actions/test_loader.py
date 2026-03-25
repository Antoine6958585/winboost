"""Tests pour actions/loader.py."""

from pathlib import Path

import yaml

from winboost.actions.loader import Action, ActionRegistry


def _write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


class TestAction:
    def test_create_from_dict(self):
        data = {
            "id": "test_001",
            "name": "Test",
            "description": "Desc",
            "category": "privacy",
            "risk_level": "low",
            "execute": {"method": "registry_set", "params": {}},
            "keywords": {"fr": ["vie privee"], "en": ["privacy"]},
        }
        action = Action(data)
        assert action.id == "test_001"
        assert action.category == "privacy"
        assert action.requires_admin is False
        assert action.reversible is True

    def test_get_keywords_flat(self):
        data = {
            "id": "t", "name": "T", "description": "D",
            "category": "privacy", "risk_level": "low",
            "execute": {},
            "keywords": {"fr": ["Telemetrie", "Tracking"], "en": ["Telemetry"]},
        }
        action = Action(data)
        kw = action.get_keywords_flat()
        assert "telemetrie" in kw
        assert "tracking" in kw
        assert "telemetry" in kw

    def test_repr(self):
        data = {
            "id": "x", "name": "My Action", "description": "D",
            "category": "system", "risk_level": "high", "execute": {},
        }
        action = Action(data)
        assert "My Action" in repr(action)

    def test_to_dict(self):
        data = {
            "id": "x", "name": "T", "description": "D",
            "category": "system", "risk_level": "low", "execute": {},
        }
        action = Action(data)
        assert action.to_dict() == data


class TestActionRegistry:
    def test_load_single_action(self, tmp_path):
        """Charge un fichier YAML avec une seule action."""
        action_data = {
            "id": "test_001",
            "name": "Test Action",
            "description": "Description",
            "category": "privacy",
            "risk_level": "low",
            "execute": {"method": "registry_set", "params": {}},
            "keywords": {"fr": ["test"]},
        }
        _write_yaml(tmp_path / "privacy" / "test.yaml", action_data)

        registry = ActionRegistry(actions_dir=tmp_path)
        count = registry.load_all()
        assert count == 1
        assert registry.get("test_001") is not None

    def test_load_multiple_actions_in_file(self, tmp_path):
        """Charge un fichier avec plusieurs actions (liste)."""
        actions = [
            {
                "id": f"multi_{i}",
                "name": f"Action {i}",
                "description": f"Desc {i}",
                "category": "cleanup",
                "risk_level": "low",
                "execute": {"method": "clear_directory", "params": {}},
            }
            for i in range(5)
        ]
        _write_yaml(tmp_path / "cleanup" / "batch.yaml", actions)

        registry = ActionRegistry(actions_dir=tmp_path)
        count = registry.load_all()
        assert count == 5

    def test_load_invalid_yaml(self, tmp_path):
        """Les fichiers YAML invalides sont reportes en erreur."""
        (tmp_path / "bad" ).mkdir()
        (tmp_path / "bad" / "broken.yaml").write_text(": invalid: yaml: {[")

        registry = ActionRegistry(actions_dir=tmp_path)
        registry.load_all()
        assert len(registry.errors) > 0

    def test_load_invalid_action(self, tmp_path):
        """Les actions avec des champs manquants sont reportees."""
        _write_yaml(tmp_path / "privacy" / "bad.yaml", {"id": "incomplete"})

        registry = ActionRegistry(actions_dir=tmp_path)
        registry.load_all()
        assert registry.count == 0
        assert len(registry.errors) > 0

    def test_search(self, tmp_path):
        """La recherche par mots-cles fonctionne."""
        actions = [
            {
                "id": "priv_telemetry",
                "name": "Disable Telemetry",
                "description": "Desactive la telemetrie Windows",
                "category": "privacy",
                "risk_level": "low",
                "execute": {"method": "registry_set", "params": {}},
                "keywords": {"fr": ["telemetrie", "espionnage"], "en": ["telemetry"]},
            },
            {
                "id": "perf_superfetch",
                "name": "Disable Superfetch",
                "description": "Desactive SysMain",
                "category": "performance",
                "risk_level": "medium",
                "execute": {"method": "service_disable", "params": {}},
                "keywords": {"fr": ["performance"], "en": ["speed"]},
            },
        ]
        _write_yaml(tmp_path / "privacy" / "a.yaml", actions[0])
        _write_yaml(tmp_path / "performance" / "b.yaml", actions[1])

        registry = ActionRegistry(actions_dir=tmp_path)
        registry.load_all()

        results = registry.search("telemetrie")
        assert len(results) >= 1
        assert results[0].id == "priv_telemetry"

    def test_list_by_category(self, tmp_path):
        """Filtre par categorie fonctionne."""
        for i, cat in enumerate(["privacy", "privacy", "cleanup"]):
            _write_yaml(tmp_path / cat / f"a{i}.yaml", {
                "id": f"cat_{i}", "name": f"Action {i}", "description": "D",
                "category": cat, "risk_level": "low",
                "execute": {"method": "cmd", "params": {}},
            })

        registry = ActionRegistry(actions_dir=tmp_path)
        registry.load_all()

        assert len(registry.list_by_category("privacy")) == 2
        assert len(registry.list_by_category("cleanup")) == 1
        assert len(registry.list_by_category("gaming")) == 0

    def test_categories(self, tmp_path):
        """Retourne les categories chargees."""
        for cat in ["privacy", "cleanup"]:
            _write_yaml(tmp_path / cat / "a.yaml", {
                "id": f"{cat}_1", "name": "A", "description": "D",
                "category": cat, "risk_level": "low",
                "execute": {"method": "cmd", "params": {}},
            })

        registry = ActionRegistry(actions_dir=tmp_path)
        registry.load_all()
        assert "privacy" in registry.categories()
        assert "cleanup" in registry.categories()

    def test_stats(self, tmp_path):
        """Stats par categorie."""
        for i in range(3):
            _write_yaml(tmp_path / "privacy" / f"a{i}.yaml", {
                "id": f"p_{i}", "name": f"A{i}", "description": "D",
                "category": "privacy", "risk_level": "low",
                "execute": {"method": "cmd", "params": {}},
            })

        registry = ActionRegistry(actions_dir=tmp_path)
        registry.load_all()
        stats = registry.stats()
        assert stats["privacy"] == 3

    def test_empty_directory(self, tmp_path):
        """Registry vide = 0 actions."""
        registry = ActionRegistry(actions_dir=tmp_path)
        count = registry.load_all()
        assert count == 0
