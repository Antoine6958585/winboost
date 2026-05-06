"""Tests pour le mode JSON de la commande `winboost chat` (T066).

Couvre :
- Validite du JSON retourne (parseable, schema attendu)
- Absence de codes ANSI Rich en stdout en mode --json
- Top-level keys : query, resolved_by, message, has_actions, actions, blocked
- Champs des actions et du verdict
- Backward compatibility : sans --json, output Rich classique
- Cas d'erreur : query vide en mode --json
"""

from __future__ import annotations

import json
import re

from click.testing import CliRunner

from winboost.cli.main import cli

# Pattern detectant les sequences d'echappement ANSI (codes couleurs Rich)
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _invoke_json(*args: str) -> tuple[int, str]:
    """Invoque `winboost chat --json <args>` et retourne (exit_code, stdout)."""
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "--json", *args])
    return result.exit_code, result.output


class TestChatJsonValidOutput:
    """Le mode --json produit un JSON valide et parseable."""

    def test_json_is_parseable(self):
        exit_code, output = _invoke_json("dark", "mode")
        assert exit_code == 0, f"exit code {exit_code}, output={output!r}"
        # Doit etre un seul objet JSON parseable
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_json_no_ansi_codes(self):
        """Aucun code couleur ANSI Rich ne doit etre dans stdout."""
        _, output = _invoke_json("dark", "mode")
        # Recherche de sequences ESC[...m (codes ANSI)
        ansi_matches = ANSI_ESCAPE_RE.findall(output)
        assert ansi_matches == [], (
            f"Codes ANSI detectes en mode --json (stdout doit etre du JSON pur): "
            f"{ansi_matches[:5]}"
        )

    def test_json_no_rich_markup(self):
        """Aucun markup Rich type [bold] [yellow] ne doit fuir en stdout."""
        _, output = _invoke_json("dark", "mode")
        # Les markups Rich sont entoures de crochets — on verifie qu'il n'y en a
        # pas en dehors des structures JSON (les crochets JSON sont [ et ] purs)
        assert "[bold]" not in output
        assert "[yellow]" not in output
        assert "[/bold]" not in output
        assert "[red]" not in output


class TestChatJsonSchema:
    """Le JSON respecte le schema documente."""

    def test_top_level_keys(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        expected_keys = {
            "query", "resolved_by", "message", "has_actions", "actions", "blocked"
        }
        assert set(data.keys()) == expected_keys, (
            f"Cles manquantes ou supplementaires : {set(data.keys()) ^ expected_keys}"
        )

    def test_query_field_echoes_input(self):
        _, output = _invoke_json("nettoie", "les", "temp")
        data = json.loads(output)
        assert data["query"] == "nettoie les temp"

    def test_top_level_types(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        assert isinstance(data["query"], str)
        assert isinstance(data["resolved_by"], str)
        assert isinstance(data["message"], str)
        assert isinstance(data["has_actions"], bool)
        assert isinstance(data["actions"], list)
        assert isinstance(data["blocked"], list)


class TestChatJsonActionsFound:
    """Quand des actions matchent : has_actions=true, actions non vide."""

    def test_has_actions_true_when_match(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        assert data["has_actions"] is True
        assert len(data["actions"]) > 0

    def test_action_fields_present(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        action = data["actions"][0]
        required_fields = {
            "id", "name", "description", "category", "risk_level",
            "requires_admin", "reversible", "verdict",
        }
        assert set(action.keys()) == required_fields, (
            f"Champs manquants/extras : {set(action.keys()) ^ required_fields}"
        )

    def test_action_field_types(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        action = data["actions"][0]
        assert isinstance(action["id"], str)
        assert isinstance(action["name"], str)
        assert isinstance(action["description"], str)
        assert isinstance(action["category"], str)
        assert isinstance(action["risk_level"], str)
        assert isinstance(action["requires_admin"], bool)
        assert isinstance(action["reversible"], bool)
        assert isinstance(action["verdict"], dict)

    def test_risk_level_is_valid_enum(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        valid_levels = {"info", "low", "medium", "high", "critical"}
        for action in data["actions"]:
            assert action["risk_level"] in valid_levels


class TestChatJsonVerdict:
    """Le champ verdict est correctement serialise."""

    def test_verdict_fields(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        verdict = data["actions"][0]["verdict"]
        expected = {"allowed", "requires_dry_run", "requires_confirmation", "reason"}
        assert set(verdict.keys()) == expected

    def test_verdict_field_types(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        verdict = data["actions"][0]["verdict"]
        assert isinstance(verdict["allowed"], bool)
        assert isinstance(verdict["requires_dry_run"], bool)
        assert isinstance(verdict["requires_confirmation"], bool)
        # reason peut etre str ou None
        assert verdict["reason"] is None or isinstance(verdict["reason"], str)

    def test_allowed_actions_have_allowed_true(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        for action in data["actions"]:
            assert action["verdict"]["allowed"] is True


class TestChatJsonNoMatch:
    """Quand rien ne matche : has_actions=false, actions vide."""

    def test_no_match_returns_empty_actions(self):
        # Requete deliberement absurde pour ne rien matcher
        _, output = _invoke_json("xyzzyx", "qwzlpfm", "vbnxyz")
        data = json.loads(output)
        assert data["has_actions"] is False
        assert data["actions"] == []

    def test_no_match_resolved_by_none(self):
        _, output = _invoke_json("xyzzyx", "qwzlpfm", "vbnxyz")
        data = json.loads(output)
        # Quand aucun cache hit ni categorie, resolved_by = "none"
        assert data["resolved_by"] == "none"

    def test_no_match_has_message(self):
        _, output = _invoke_json("xyzzyx", "qwzlpfm", "vbnxyz")
        data = json.loads(output)
        # Le message d'erreur du router est preserve
        assert isinstance(data["message"], str)
        assert len(data["message"]) > 0


class TestChatJsonBlockedActions:
    """Les actions bloquees par le profil sont serialisees dans `blocked`."""

    def test_blocked_field_is_list(self):
        _, output = _invoke_json("dark", "mode")
        data = json.loads(output)
        assert isinstance(data["blocked"], list)

    def test_blocked_actions_have_same_schema(self):
        # On cherche une requete qui peut declencher des actions bloquees
        # (en profil safe, les actions medium+ sont bloquees)
        _, output = _invoke_json("desactive", "windows", "defender")
        data = json.loads(output)
        # Si des actions sont bloquees, verifier leur schema
        for blocked in data["blocked"]:
            assert "id" in blocked
            assert "name" in blocked
            assert "verdict" in blocked
            assert blocked["verdict"]["allowed"] is False


class TestChatJsonBackwardCompat:
    """Sans --json, l'output Rich classique reste intact (regression)."""

    def test_rich_output_without_json_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "dark", "mode"])
        assert result.exit_code == 0
        # Output Rich contient le marqueur "Requete :" lisible humain
        assert "Requete" in result.output
        # Pas de structure JSON dans la sortie Rich
        assert not result.output.strip().startswith("{")

    def test_rich_output_no_json_keys_leaking(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "dark", "mode"])
        assert result.exit_code == 0
        # Les cles JSON ne doivent pas apparaitre comme texte brut
        # (elles existent dans le JSON mais pas dans l'output Rich)
        assert '"resolved_by"' not in result.output
        assert '"has_actions"' not in result.output


class TestChatJsonEmptyQuery:
    """Cas d'erreur : query vide ou whitespace en mode --json."""

    def test_empty_string_query_exits_1(self):
        runner = CliRunner()
        # Click exige au moins un argument (nargs=-1, required=True)
        # mais si on passe une chaine vide, le strip() la rend vide et on retourne erreur
        result = runner.invoke(cli, ["chat", "--json", ""])
        # query="" passe le `required=True` de Click (token present)
        # mais notre code retourne {"error": ...} avec exit 1
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data
        assert data["error"] == "query is required"

    def test_whitespace_only_query_exits_1(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--json", "   "])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data


class TestChatJsonHelpDocsSchema:
    """L'aide de la commande chat documente bien le schema JSON."""

    def test_help_mentions_json_schema(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--help"])
        assert result.exit_code == 0
        # Verifie que la docstring du schema est exposee dans --help
        assert "--json" in result.output
        assert "resolved_by" in result.output
        assert "has_actions" in result.output
