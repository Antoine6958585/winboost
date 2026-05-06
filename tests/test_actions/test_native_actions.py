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

_ACTIONS_ROOT = Path(__file__).resolve().parent.parent.parent / "winboost" / "actions"
SYSTEM_YAML = _ACTIONS_ROOT / "system" / "actions.yaml"
NETWORK_YAML = _ACTIONS_ROOT / "network" / "actions.yaml"
APPEARANCE_YAML = _ACTIONS_ROOT / "appearance" / "actions.yaml"

# IDs des nouvelles actions v2.1 par categorie
V2_1_SYSTEM_IDS = [f"sys_{i:03d}" for i in range(11, 21)]
V2_1_NETWORK_IDS = [f"net_{i:03d}" for i in range(11, 21)]
V2_1_APPEARANCE_IDS = [f"app_{i:03d}" for i in range(11, 21)]
V2_1_NATIVE_IDS = V2_1_SYSTEM_IDS  # alias historique pour les tests system existants


def _load(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8") as f:
        return {a["id"]: a for a in yaml.safe_load(f)}


@pytest.fixture(scope="module")
def system_actions() -> dict[str, dict]:
    return _load(SYSTEM_YAML)


@pytest.fixture(scope="module")
def network_actions() -> dict[str, dict]:
    return _load(NETWORK_YAML)


@pytest.fixture(scope="module")
def appearance_actions() -> dict[str, dict]:
    return _load(APPEARANCE_YAML)


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


# =============================================================================
# v2.1 — Network actions (net_011 -> net_020)
# =============================================================================


class TestNetworkV21:
    @pytest.mark.parametrize("action_id", V2_1_NETWORK_IDS)
    def test_each_action_loaded(self, network_actions, action_id):
        assert action_id in network_actions

    @pytest.mark.parametrize("action_id", V2_1_NETWORK_IDS)
    def test_each_action_passes_schema(self, network_actions, action_id):
        errors = validate_action(network_actions[action_id], filename=action_id)
        assert errors == [], f"Erreurs schema pour {action_id}: {errors}"

    @pytest.mark.parametrize("action_id", V2_1_NETWORK_IDS)
    def test_each_action_has_bilingual_keywords(self, network_actions, action_id):
        kw = network_actions[action_id].get("keywords", {})
        assert "fr" in kw and "en" in kw
        assert len(kw["fr"]) >= 2 and len(kw["en"]) >= 2

    @pytest.mark.parametrize("action_id", V2_1_NETWORK_IDS)
    def test_each_action_has_category_network(self, network_actions, action_id):
        assert network_actions[action_id]["category"] == "network"

    def test_winsock_reset_is_not_reversible(self, network_actions):
        # Winsock reset = repair, pas de retour arriere meaningful
        assert network_actions["net_017"]["reversible"] is False
        assert network_actions["net_017"]["rollback"] == {}

    def test_winsock_reset_requires_admin(self, network_actions):
        assert network_actions["net_017"]["requires_admin"] is True

    def test_ipv6_disable_uses_disabled_components_ff(self, network_actions):
        # 0xFF = 255 = desactive tunnels + IPv6 sur toutes interfaces (Microsoft KB)
        params = network_actions["net_018"]["execute"]["params"]
        assert "Tcpip6" in params.get("path", "")
        # tolerance : data peut etre 255 (decimal) ou 0xff (hex string)
        values_str = str(params)
        assert "255" in values_str or "0xff" in values_str.lower() or "0xFF" in values_str

    def test_dns_cloudflare_targets_1_1_1_1(self, network_actions):
        cmd = network_actions["net_015"]["execute"]["params"]["command"]
        assert "1.1.1.1" in cmd

    def test_flush_dns_uses_ipconfig(self, network_actions):
        params = network_actions["net_014"]["execute"]["params"]
        cmd = params.get("command", "")
        assert "flushdns" in cmd.lower() or "ipconfig" in cmd.lower()


# =============================================================================
# v2.1 — Appearance actions (app_011 -> app_020)
# =============================================================================


class TestAppearanceV21:
    @pytest.mark.parametrize("action_id", V2_1_APPEARANCE_IDS)
    def test_each_action_loaded(self, appearance_actions, action_id):
        assert action_id in appearance_actions

    @pytest.mark.parametrize("action_id", V2_1_APPEARANCE_IDS)
    def test_each_action_passes_schema(self, appearance_actions, action_id):
        errors = validate_action(appearance_actions[action_id], filename=action_id)
        assert errors == [], f"Erreurs schema pour {action_id}: {errors}"

    @pytest.mark.parametrize("action_id", V2_1_APPEARANCE_IDS)
    def test_each_action_has_bilingual_keywords(self, appearance_actions, action_id):
        kw = appearance_actions[action_id].get("keywords", {})
        assert "fr" in kw and "en" in kw
        assert len(kw["fr"]) >= 2 and len(kw["en"]) >= 2

    @pytest.mark.parametrize("action_id", V2_1_APPEARANCE_IDS)
    def test_each_action_has_category_appearance(self, appearance_actions, action_id):
        assert appearance_actions[action_id]["category"] == "appearance"

    @pytest.mark.parametrize("action_id", V2_1_APPEARANCE_IDS)
    def test_no_appearance_action_requires_admin(self, appearance_actions, action_id):
        # Toutes les actions appearance v2.1 sont en HKCU ou SendKeys utilisateur
        assert appearance_actions[action_id]["requires_admin"] is False

    def test_mute_keywords_match_silence(self, appearance_actions):
        kws = appearance_actions["app_011"]["keywords"]["fr"]
        joined = " ".join(kws).lower()
        assert "mute" in joined or "silence" in joined or "couper" in joined

    def test_animations_disable_keywords(self, appearance_actions):
        kws = appearance_actions["app_018"]["keywords"]["fr"]
        joined = " ".join(kws).lower()
        assert "animation" in joined

    def test_transparency_disable_targets_correct_registry(self, appearance_actions):
        params = appearance_actions["app_020"]["execute"]["params"]
        path = params.get("path", "")
        assert "Personalize" in path or "EnableTransparency" in str(params)


# =============================================================================
# v2.1 — Total compte global (toutes categories confondues)
# =============================================================================


class TestV21Totals:
    def test_thirty_v21_native_actions_total(self, system_actions, network_actions, appearance_actions):
        n_sys = sum(1 for aid in V2_1_SYSTEM_IDS if aid in system_actions)
        n_net = sum(1 for aid in V2_1_NETWORK_IDS if aid in network_actions)
        n_app = sum(1 for aid in V2_1_APPEARANCE_IDS if aid in appearance_actions)
        assert n_sys + n_net + n_app == 30, (
            f"30 actions v2.1 attendues, trouvees : sys={n_sys}, net={n_net}, app={n_app}"
        )


# =============================================================================
# v2.4 — Audio Native Actions (app_021 -> app_025) via pycaw / Core Audio
# Strict mute + volume precis. Complementaires aux app_011-015 (SendKeys = fallback).
# =============================================================================

V2_4_AUDIO_NATIVE_IDS = [f"app_{i:03d}" for i in range(21, 26)]


class TestAudioNativeV24:
    @pytest.mark.parametrize("action_id", V2_4_AUDIO_NATIVE_IDS)
    def test_each_action_loaded(self, appearance_actions, action_id):
        assert action_id in appearance_actions, f"Action {action_id} manquante"

    @pytest.mark.parametrize("action_id", V2_4_AUDIO_NATIVE_IDS)
    def test_each_action_passes_schema(self, appearance_actions, action_id):
        errors = validate_action(appearance_actions[action_id], filename=action_id)
        assert errors == [], f"Erreurs schema pour {action_id}: {errors}"

    @pytest.mark.parametrize("action_id", V2_4_AUDIO_NATIVE_IDS)
    def test_each_action_has_bilingual_keywords(self, appearance_actions, action_id):
        kw = appearance_actions[action_id].get("keywords", {})
        assert "fr" in kw and "en" in kw
        assert len(kw["fr"]) >= 2 and len(kw["en"]) >= 2

    @pytest.mark.parametrize("action_id", V2_4_AUDIO_NATIVE_IDS)
    def test_each_action_is_low_risk_no_admin(self, appearance_actions, action_id):
        action = appearance_actions[action_id]
        assert action["risk_level"] == "low"
        assert action["requires_admin"] is False

    @pytest.mark.parametrize("action_id", V2_4_AUDIO_NATIVE_IDS)
    def test_each_action_calls_audio_native_module(self, appearance_actions, action_id):
        cmd = appearance_actions[action_id]["execute"]["params"]["command"]
        assert "winboost.utils.audio_native" in cmd, (
            f"{action_id} doit invoquer winboost.utils.audio_native, recu : {cmd!r}"
        )

    def test_audio_native_keywords_distinct_from_sendkeys(self, appearance_actions):
        """Les keywords app_021-025 ne doivent pas etre identiques aux app_011-015.

        Sinon le NL parser cree des doublons de matching cache et ne sait pas
        choisir entre fallback SendKeys et version precise pycaw.
        """
        # On verifie au moins qu'un keyword distinctif "strict" / "precis" / "audio native"
        # apparait sur chaque action v2.4 — pas sur les v2.1
        for aid in V2_4_AUDIO_NATIVE_IDS:
            kws = appearance_actions[aid]["keywords"]["fr"] + appearance_actions[aid]["keywords"]["en"]
            joined = " ".join(kws).lower()
            distinctive = any(
                marker in joined
                for marker in ("strict", "precis", "precise", "audio native", "30", "60", "100")
            )
            assert distinctive, (
                f"{aid} doit avoir un keyword distinctif (strict/precis/audio native/30/60/100), "
                f"recu : {kws}"
            )

    def test_mute_strict_uses_set_mute_true(self, appearance_actions):
        cmd = appearance_actions["app_021"]["execute"]["params"]["command"]
        assert "set_mute(True)" in cmd

    def test_unmute_strict_uses_set_mute_false(self, appearance_actions):
        cmd = appearance_actions["app_022"]["execute"]["params"]["command"]
        assert "set_mute(False)" in cmd

    def test_volume_actions_use_correct_levels(self, appearance_actions):
        assert "set_volume(30)" in appearance_actions["app_023"]["execute"]["params"]["command"]
        assert "set_volume(60)" in appearance_actions["app_024"]["execute"]["params"]["command"]
        assert "set_volume(100)" in appearance_actions["app_025"]["execute"]["params"]["command"]

    @pytest.mark.parametrize("action_id", V2_4_AUDIO_NATIVE_IDS)
    def test_each_action_is_reversible_with_rollback(self, appearance_actions, action_id):
        action = appearance_actions[action_id]
        assert action["reversible"] is True
        rollback = action.get("rollback", {})
        assert rollback != {}, f"{action_id} doit avoir un rollback non-vide"
        assert "method" in rollback


class TestAppearanceTotalCountWithAudioNative:
    def test_appearance_has_25_actions(self, appearance_actions):
        # 10 v2.0 + 10 v2.1 native + 5 v2.4 audio native
        assert len(appearance_actions) == 25, (
            f"25 actions appearance attendues, trouvees : {len(appearance_actions)}"
        )
