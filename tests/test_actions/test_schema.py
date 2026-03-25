"""Tests pour actions/schema.py."""

from winboost.actions.schema import validate_action, VALID_CATEGORIES, VALID_RISK_LEVELS


class TestValidateAction:
    def _valid_action(self):
        return {
            "id": "test_001",
            "name": "Test Action",
            "description": "A test action",
            "category": "privacy",
            "risk_level": "low",
            "requires_admin": False,
            "reversible": True,
            "execute": {"method": "registry_set", "params": {}},
            "rollback": {"method": "registry_set", "params": {}},
            "keywords": {"fr": ["test"], "en": ["test"]},
        }

    def test_valid_action(self):
        errors = validate_action(self._valid_action())
        assert errors == []

    def test_missing_required_field(self):
        data = self._valid_action()
        del data["id"]
        errors = validate_action(data)
        assert len(errors) > 0
        assert "id" in errors[0]

    def test_invalid_category(self):
        data = self._valid_action()
        data["category"] = "invalid"
        errors = validate_action(data)
        assert any("Categorie" in e for e in errors)

    def test_invalid_risk_level(self):
        data = self._valid_action()
        data["risk_level"] = "extreme"
        errors = validate_action(data)
        assert any("Risk level" in e for e in errors)

    def test_invalid_execute_method(self):
        data = self._valid_action()
        data["execute"]["method"] = "nuke_system"
        errors = validate_action(data)
        assert any("Methode" in e for e in errors)

    def test_execute_not_dict(self):
        data = self._valid_action()
        data["execute"] = "bad"
        errors = validate_action(data)
        assert any("dictionnaire" in e for e in errors)

    def test_invalid_requires_admin_type(self):
        data = self._valid_action()
        data["requires_admin"] = "yes"
        errors = validate_action(data)
        assert any("booleen" in e for e in errors)

    def test_keywords_not_dict(self):
        data = self._valid_action()
        data["keywords"] = ["bad"]
        errors = validate_action(data)
        assert any("keywords" in e for e in errors)

    def test_all_valid_categories(self):
        for cat in VALID_CATEGORIES:
            data = self._valid_action()
            data["category"] = cat
            assert validate_action(data) == []

    def test_all_valid_risk_levels(self):
        for risk in VALID_RISK_LEVELS:
            data = self._valid_action()
            data["risk_level"] = risk
            assert validate_action(data) == []

    def test_filename_in_error(self):
        data = {"id": "x"}  # missing fields
        errors = validate_action(data, filename="test.yaml")
        assert any("[test.yaml]" in e for e in errors)
