"""Tests pour l'AI engine (NL Parser, Cache, Safety, Router)."""

from pathlib import Path

import yaml

from winboost.actions.loader import Action, ActionRegistry
from winboost.ai.action_router import ActionRouter, RouteResult
from winboost.ai.cache import KeywordCache, _tokenize
from winboost.ai.nl_parser import Intent, NLParser
from winboost.ai.safety_engine import SafetyEngine
from winboost.core.config import Config

ACTIONS_DIR = Path(__file__).parent.parent.parent / "winboost" / "actions"


# --- Helpers ---

def _make_action(action_id: str, risk: str = "low", category: str = "privacy") -> Action:
    return Action({
        "id": action_id,
        "name": f"Test {action_id}",
        "description": f"Description for {action_id}",
        "category": category,
        "risk_level": risk,
        "execute": {"method": "registry_set", "params": {}},
        "keywords": {"fr": ["test"], "en": ["test"]},
    })


def _write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


# --- Tests NLParser ---

class TestNLParser:
    def test_parse_disable_telemetry(self):
        intent = NLParser().parse("desactive la telemetrie")
        assert intent.action == "disable"
        assert intent.category == "privacy"
        assert intent.confidence > 0

    def test_parse_clean_temp(self):
        intent = NLParser().parse("nettoyer les fichiers temporaires")
        assert intent.action == "clean"

    def test_parse_optimize_performance(self):
        intent = NLParser().parse("optimise les performances")
        assert intent.action == "optimize"
        assert intent.category == "performance"

    def test_parse_gaming(self):
        intent = NLParser().parse("optimise pour les jeux")
        assert intent.category == "gaming"

    def test_parse_empty(self):
        intent = NLParser().parse("")
        assert isinstance(intent, Intent)

    def test_parse_info(self):
        intent = NLParser().parse("montre les informations systeme")
        assert intent.action == "info"


# --- Tests Tokenizer ---

class TestTokenizer:
    def test_basic(self):
        tokens = _tokenize("desactive la telemetrie")
        assert "telemetry" in tokens  # synonym applied
        assert "la" not in tokens  # stop word removed

    def test_synonyms(self):
        tokens = _tokenize("nettoyer les temp")
        assert "cleanup" in tokens
        assert "temporaire" in tokens

    def test_empty(self):
        assert _tokenize("") == []


# --- Tests KeywordCache ---

class TestKeywordCache:
    def test_resolve_finds_actions(self, tmp_path):
        actions_data = {
            "id": "test_tel", "name": "Disable Telemetry",
            "description": "Desactive la telemetrie",
            "category": "privacy", "risk_level": "low",
            "execute": {"method": "registry_set", "params": {}},
            "keywords": {"fr": ["telemetrie", "espionnage"], "en": ["telemetry"]},
        }
        _write_yaml(tmp_path / "privacy" / "a.yaml", actions_data)

        registry = ActionRegistry(actions_dir=tmp_path)
        registry.load_all()
        cache = KeywordCache(registry)

        results = cache.resolve("desactive la telemetrie")
        assert len(results) > 0
        assert results[0][0].id == "test_tel"

    def test_can_resolve(self, tmp_path):
        _write_yaml(tmp_path / "privacy" / "a.yaml", {
            "id": "x", "name": "Test", "description": "Telemetrie",
            "category": "privacy", "risk_level": "low",
            "execute": {"method": "cmd", "params": {}},
            "keywords": {"fr": ["telemetrie"]},
        })
        registry = ActionRegistry(actions_dir=tmp_path)
        registry.load_all()
        cache = KeywordCache(registry)

        assert cache.can_resolve("telemetrie") is True
        assert cache.can_resolve("xyzabc123") is False

    def test_resolve_empty_query(self, tmp_path):
        registry = ActionRegistry(actions_dir=tmp_path)
        registry.load_all()
        cache = KeywordCache(registry)
        assert cache.resolve("") == []


# --- Tests SafetyEngine ---

class TestSafetyEngine:
    def test_safe_profile_allows_low(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "safe"
        safety = SafetyEngine(config)
        verdict = safety.check_action(_make_action("a", "low"))
        assert verdict.allowed is True

    def test_safe_profile_blocks_medium(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "safe"
        safety = SafetyEngine(config)
        verdict = safety.check_action(_make_action("a", "medium"))
        assert verdict.allowed is False

    def test_expert_allows_high(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        safety = SafetyEngine(config)
        verdict = safety.check_action(_make_action("a", "high"))
        assert verdict.allowed is True

    def test_critical_blocked_for_non_expert(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "power_user"
        safety = SafetyEngine(config)
        verdict = safety.check_action(_make_action("a", "critical"))
        assert verdict.allowed is False
        assert "expert" in verdict.reason

    def test_critical_allowed_for_expert(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        safety = SafetyEngine(config)
        verdict = safety.check_action(_make_action("a", "critical"))
        assert verdict.allowed is True

    def test_filter_actions(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "safe"
        safety = SafetyEngine(config)
        actions = [
            _make_action("low", "low"),
            _make_action("med", "medium"),
            _make_action("high", "high"),
        ]
        allowed = safety.get_allowed_actions(actions)
        assert len(allowed) == 1
        assert allowed[0].id == "low"

    def test_medium_requires_confirmation(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        safety = SafetyEngine(config)
        verdict = safety.check_action(_make_action("a", "medium"))
        assert verdict.requires_confirmation is True

    def test_high_requires_dry_run(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        safety = SafetyEngine(config)
        verdict = safety.check_action(_make_action("a", "high"))
        assert verdict.requires_dry_run is True


# --- Tests ActionRouter (integration) ---

class TestActionRouter:
    def test_route_telemetry(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "expert"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")
        assert result.has_actions
        assert result.resolved_by in ("cache", "category_fallback")

    def test_route_cleanup(self, tmp_path):
        config = Config(config_dir=tmp_path)
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("nettoie les fichiers temporaires")
        assert result.has_actions

    def test_route_unknown(self, tmp_path):
        config = Config(config_dir=tmp_path)
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("xyzabc123noaction")
        # Peut retourner des actions par matching partiel ou aucune
        assert isinstance(result, RouteResult)

    def test_route_respects_profile(self, tmp_path):
        config = Config(config_dir=tmp_path)
        config.profile = "safe"
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        result = router.route("desactive la telemetrie")
        # Le profil safe bloque les actions medium+
        for routed in result.actions:
            assert routed.verdict.allowed is True

    def test_action_count(self, tmp_path):
        config = Config(config_dir=tmp_path)
        router = ActionRouter(config=config, actions_dir=ACTIONS_DIR)
        assert router.action_count == 180  # 150 v2.0 + 30 v2.1 native


# --- Tests CLI Chat ---

class TestCLIChat:
    def test_chat_command(self):
        from click.testing import CliRunner

        from winboost.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "desactive", "la", "telemetrie"])
        assert result.exit_code == 0
        assert "action(s)" in result.output

    def test_chat_cleanup(self):
        from click.testing import CliRunner

        from winboost.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "nettoie", "les", "temp"])
        assert result.exit_code == 0
