"""Tests pour core/config.py."""

import json

import pytest

from winboost.core.config import PROFILE_SETTINGS, Config


class TestConfig:
    def test_default_values(self, tmp_path):
        """La config par defaut charge les valeurs DEFAULT_CONFIG."""
        config = Config(config_dir=tmp_path)
        assert config.profile == "safe"
        assert config.max_risk == "low"
        assert config.dry_run_first is True
        assert "temp_cleaner" in config.modules_enabled

    def test_save_and_reload(self, tmp_path):
        """La config se sauvegarde et se recharge correctement."""
        config = Config(config_dir=tmp_path)
        config.set("language", "en")
        config.save()

        # Recharge depuis le fichier
        config2 = Config(config_dir=tmp_path)
        assert config2.get("language") == "en"

    def test_profile_setter_valid(self, tmp_path):
        """Changer de profil applique les contraintes correspondantes."""
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        assert config.profile == "expert"
        assert config.max_risk == "high"
        assert config.dry_run_first is False

    def test_profile_setter_invalid(self, tmp_path):
        """Un profil invalide leve ValueError."""
        config = Config(config_dir=tmp_path)
        with pytest.raises(ValueError, match="Profil invalide"):
            config.profile = "hacker"

    def test_get_missing_key(self, tmp_path):
        """get() retourne le default pour une cle absente."""
        config = Config(config_dir=tmp_path)
        assert config.get("inexistant") is None
        assert config.get("inexistant", 42) == 42

    def test_as_dict(self, tmp_path):
        """as_dict() retourne une copie complete."""
        config = Config(config_dir=tmp_path)
        d = config.as_dict()
        assert isinstance(d, dict)
        assert "profile" in d
        # Modification de la copie ne touche pas l'original
        d["profile"] = "modified"
        assert config.profile == "safe"

    def test_merge_missing_keys(self, tmp_path):
        """Les cles manquantes du fichier sont completees par les defauts."""
        # Ecrit un fichier partiel
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"profile": "expert"}))

        config = Config(config_dir=tmp_path)
        # La cle du fichier est preservee
        assert config.profile == "expert"
        # Les cles manquantes viennent des defauts
        assert "temp_cleaner" in config.modules_enabled

    def test_all_profiles_valid(self, tmp_path):
        """Tous les profils definis sont applicables."""
        config = Config(config_dir=tmp_path)
        for profile_name in PROFILE_SETTINGS:
            config.profile = profile_name
            assert config.profile == profile_name
