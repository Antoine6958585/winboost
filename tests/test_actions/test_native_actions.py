"""Tests pour les actions Windows-natives v2.1 (sys_011 -> sys_020).

Ces tests verifient :
- Que les nouveaux YAML chargent et passent la validation schema
- Que les keywords FR/EN sont corrects (matchables par le NL parser)
- Que les commandes powercfg utilisent les bons GUIDs Microsoft officiels
- Que les actions risk-elevees ont bien `requires_admin: true`

Pas de test "execute reel" ici (ca tomberait dans test_e2e). Ces tests sont
purement structurels et tournent sur Linux CI sans WMI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from winboost.actions.schema import validate_action

SYSTEM_YAML = Path(__file__).resolve().parent.parent.parent / "winboost" / "actions" / "system" / "actions.yaml"

# IDs des nouvelles actions v2.1
V2_1_NATIVE_IDS = [
    "sys_011",  # Enable Dark Mode
    "sys_012",  # Enable Light Mode
    "sys_013",  # Brightness 30%
    "sys_014",  # Brightness 60%
    "sys_015",  # Brightness 100%
    "sys_016",  # Focus Assist on
    "sys_017",  # Focus Assist off
    "sys_018",  # Night Light
    "sys_019",  # Power Plan High Perf
    "sys_020",  # Power Plan Balanced
]


@pytest.fixture(scope="module")
def system_actions() -> dict[str, dict]:
    """Charge le YAML system et indexe par id."""
    with SYSTEM_YAML.open(encoding="utf-8") as f:
        actions = yaml.safe_load(f)
    return {a["id"]: a for a in actions}


# --- Existence et validation schema ---


class TestNewActionsLoaded:
    def test_all_v2_1_actions_present(self, system_actions):
        missing = [aid for aid in V2_1_NATIVE_IDS if aid not in system_actions]
        assert missing == [], f"Actions manquantes : {missing}"

    @pytest.mark.parametrize("action_id", V2_1_NATIVE_IDS)
    def test_each_action_passes_schema_validation(self, system_actions, action_id):
        action = system_actions[action_id]
        errors = validate_action(action, filename=action_id)
        assert errors == [], f"Erreurs schema pour {action_id}: {errors}"

    def test_total_count_at_least_20(self, system_actions):
        # 10 originales + 10 nouvelles = 20 minimum
        assert len(system_actions) >= 20


# --- Keywords matchables par le NL parser ---


class TestKeywords:
    @pytest.mark.parametrize("action_id", V2_1_NATIVE_IDS)
    def test_action_has_fr_and_en_keywords(self, system_actions, action_id):
        kw = system_actions[action_id].get("keywords", {})
        assert "fr" in kw and "en" in kw, f"{action_id} manque fr/en"
        assert len(kw["fr"]) >= 2 and len(kw["en"]) >= 2

    def test_dark_mode_matches_user_query(self, system_actions):
        kws = system_actions["sys_011"]["keywords"]["fr"]
        assert any("sombre" in k.lower() or "dark" in k.lower() for k in kws)

    def test_brightness_low_matches_baisse(self, system_actions):
        kws = system_actions["sys_013"]["keywords"]["fr"]
        assert any("baisse" in k.lower() or "faible" in k.lower() for k in kws)

    def test_focus_matches_concentration(self, system_actions):
        kws = system_actions["sys_016"]["keywords"]["fr"]
        joined = " ".join(kws).lower()
        assert "focus" in joined or "concentration" in joined or "deranger" in joined


# --- Risk levels coherents ---


class TestRiskLevels:
    def test_dark_mode_is_low_risk(self, system_actions):
        assert system_actions["sys_011"]["risk_level"] == "low"

    def test_brightness_actions_are_low_risk(self, system_actions):
        for aid in ("sys_013", "sys_014", "sys_015"):
            assert system_actions[aid]["risk_level"] == "low"

    def test_power_plan_high_perf_is_medium_risk(self, system_actions):
        # High performance plan vide la batterie -> medium pour avertir l'utilisateur
        assert system_actions["sys_019"]["risk_level"] == "medium"

    def test_night_light_is_info(self, system_actions):
        # Ouvre juste les settings, lecture/launcher seul
        assert system_actions["sys_018"]["risk_level"] == "info"


# --- Admin requirements ---


class TestAdminRequirements:
    def test_hkcu_actions_dont_require_admin(self, system_actions):
        # Toutes les actions HKCU et brightness-WMI tournent en user
        for aid in ("sys_011", "sys_012", "sys_013", "sys_014", "sys_015", "sys_016", "sys_017", "sys_018"):
            assert system_actions[aid]["requires_admin"] is False, (
                f"{aid} ne devrait pas requerir admin (HKCU/WMI user)"
            )

    def test_power_plan_actions_require_admin(self, system_actions):
        # powercfg /setactive necessite admin
        assert system_actions["sys_019"]["requires_admin"] is True
        assert system_actions["sys_020"]["requires_admin"] is True


# --- Reversibilite ---


class TestReversibility:
    @pytest.mark.parametrize("action_id", V2_1_NATIVE_IDS)
    def test_all_v2_1_actions_are_reversible(self, system_actions, action_id):
        # Night Light (sys_018) lance juste les settings -> reversible (user ferme)
        assert system_actions[action_id]["reversible"] is True

    @pytest.mark.parametrize(
        "action_id",
        [a for a in V2_1_NATIVE_IDS if a != "sys_018"],  # Night Light n'a pas de rollback (juste un launcher)
    )
    def test_actions_with_state_have_rollback(self, system_actions, action_id):
        rollback = system_actions[action_id].get("rollback", {})
        assert rollback != {}, f"{action_id} doit avoir un rollback non vide"
        assert "method" in rollback


# --- GUIDs power plans Microsoft officiels ---


class TestPowerPlanGuids:
    HIGH_PERF_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
    BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"

    def test_high_perf_uses_microsoft_guid(self, system_actions):
        cmd = system_actions["sys_019"]["execute"]["params"]["command"]
        assert self.HIGH_PERF_GUID in cmd

    def test_balanced_uses_microsoft_guid(self, system_actions):
        cmd = system_actions["sys_020"]["execute"]["params"]["command"]
        assert self.BALANCED_GUID in cmd

    def test_high_perf_rollback_to_balanced(self, system_actions):
        # Si on quitte high perf, on revient a balanced (defaut Windows)
        rollback_cmd = system_actions["sys_019"]["rollback"]["params"]["command"]
        assert self.BALANCED_GUID in rollback_cmd


# --- Brightness levels ---


class TestBrightnessLevels:
    def test_brightness_low_is_30(self, system_actions):
        cmd = system_actions["sys_013"]["execute"]["params"]["command"]
        assert ", 30)" in cmd

    def test_brightness_medium_is_60(self, system_actions):
        cmd = system_actions["sys_014"]["execute"]["params"]["command"]
        assert ", 60)" in cmd

    def test_brightness_max_is_100(self, system_actions):
        cmd = system_actions["sys_015"]["execute"]["params"]["command"]
        assert ", 100)" in cmd

    @pytest.mark.parametrize("action_id", ("sys_013", "sys_014", "sys_015"))
    def test_brightness_uses_wmi_namespace(self, system_actions, action_id):
        cmd = system_actions[action_id]["execute"]["params"]["command"]
        assert "WmiMonitorBrightnessMethods" in cmd
        assert "root/WMI" in cmd
