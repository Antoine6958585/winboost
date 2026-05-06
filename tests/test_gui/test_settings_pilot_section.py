"""Tests pour la section Lab Mode (Pilot Anthropic) dans SettingsPage.

Ces tests verifient T080 (opt-in RGPD granulaire) et T081 (integration GUI
de la section Lab Mode dans Settings) sans necessiter de display reel.

Pattern : on construit l'instance via `__new__` puis on monkey-patche les
widgets Tk avec des MagicMock. Le contrat principal verifie est que les
callbacks ecrivent dans Config aux bons endroits (`profile`, `pilot.api_key`,
`pilot.budget_eur`, `pilot.sandbox_mode`, `pilot.rgpd`).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from winboost.core.config import Config
from winboost.gui.settings_page import (
    DEFAULT_PILOT_BUDGET_EUR,
    MAX_PILOT_BUDGET_EUR,
    MIN_PILOT_BUDGET_EUR,
    PILOT_RGPD_KEYS,
    PILOT_SANDBOX_MODES,
    SettingsPage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings_skeleton(config: Config) -> SettingsPage:
    """Cree une SettingsPage sans GUI reelle.

    On bypasse __init__ et on injecte directement les attributs minimaux
    necessaires aux methodes Lab Mode.
    """
    page = SettingsPage.__new__(SettingsPage)
    page._config = config
    page._on_profile_change = None

    # Widgets mockes pour les sous-sections Lab Mode
    page._lab_mode_var = MagicMock()
    page._lab_mode_var.get.return_value = False
    page._lab_mode_status = MagicMock()
    page._rgpd_vars = {
        "screenshots": MagicMock(),
        "ocr_text": MagicMock(),
        "system_info": MagicMock(),
    }
    for v in page._rgpd_vars.values():
        v.get.return_value = False
    page._rgpd_confirm_btn = MagicMock()
    page._rgpd_status = MagicMock()
    page._pilot_api_entry = MagicMock()
    page._pilot_api_entry.get.return_value = ""
    page._pilot_budget_var = MagicMock()
    page._pilot_budget_var.get.return_value = "5.0"
    page._pilot_sandbox_var = MagicMock()
    page._pilot_sandbox_var.get.return_value = "winboost_window"
    page._pilot_status = MagicMock()
    page.after = lambda _delay, fn, *args: fn(*args)
    page.clipboard_get = MagicMock(return_value="")
    return page


# ---------------------------------------------------------------------------
# Tests : section presente, constantes correctes
# ---------------------------------------------------------------------------


class TestLabModeSectionStructure:
    """T1 : la section Lab Mode est integree a la page Settings."""

    def test_module_exposes_lab_mode_constants(self):
        """La page Settings expose les constantes Lab Mode publiques."""
        # Constants RGPD
        assert PILOT_RGPD_KEYS == ("screenshots", "ocr_text", "system_info")
        # Sandbox modes : 4 modes, full_screen marque NON recommande
        assert len(PILOT_SANDBOX_MODES) == 4
        modes = [m[0] for m in PILOT_SANDBOX_MODES]
        assert "winboost_window" in modes
        assert "application" in modes
        assert "screen_region" in modes
        assert "full_screen" in modes
        # Budget defaults
        assert MIN_PILOT_BUDGET_EUR > 0
        assert DEFAULT_PILOT_BUDGET_EUR >= MIN_PILOT_BUDGET_EUR
        assert MAX_PILOT_BUDGET_EUR >= DEFAULT_PILOT_BUDGET_EUR

    def test_settings_page_has_build_lab_mode_section_method(self):
        """La methode `_build_lab_mode_section` existe et est callable."""
        assert hasattr(SettingsPage, "_build_lab_mode_section")
        assert callable(SettingsPage._build_lab_mode_section)

    def test_settings_page_lab_mode_callbacks_exist(self):
        """Les callbacks Lab Mode sont definis sur la classe."""
        for name in (
            "_on_lab_mode_toggle",
            "_refresh_rgpd_button_state",
            "_on_rgpd_confirm",
            "_on_paste_api_key",
            "_on_sandbox_change",
            "_save_pilot_config",
        ):
            assert hasattr(SettingsPage, name), f"Methode manquante : {name}"


# ---------------------------------------------------------------------------
# Tests : Toggle Lab Mode -> ecrit dans Config
# ---------------------------------------------------------------------------


class TestLabModeToggle:
    """T2 : Activer Lab Mode ecrit profile='lab' dans Config."""

    def test_lab_mode_toggle_activates_lab_profile(self, tmp_path: Path):
        """Click 'Activer' -> Config.profile = 'lab' + save()."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)
        page._lab_mode_var.get.return_value = True

        page._on_lab_mode_toggle()

        # Profile ecrit en 'lab' (via Config.set, pas via setter qui rejette)
        assert config.get("profile") == "lab"
        # Persiste sur disque
        reloaded = Config(config_dir=tmp_path)
        assert reloaded.get("profile") == "lab"

    def test_lab_mode_toggle_deactivates_back_to_safe(self, tmp_path: Path):
        """Click pour desactiver -> profile = 'safe'."""
        config = Config(config_dir=tmp_path)
        config.set("profile", "lab")
        config.save()

        page = _make_settings_skeleton(config)
        page._lab_mode_var.get.return_value = False

        page._on_lab_mode_toggle()

        assert config.get("profile") == "safe"

    def test_lab_mode_toggle_invokes_profile_change_callback(self, tmp_path: Path):
        """Le callback `on_profile_change` est appele apres le toggle."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        callback = MagicMock()
        page._on_profile_change = callback
        page._lab_mode_var.get.return_value = True

        page._on_lab_mode_toggle()

        callback.assert_called_once_with("lab")


# ---------------------------------------------------------------------------
# Tests : Bouton RGPD desactive tant que les 3 cases ne sont pas cochees
# ---------------------------------------------------------------------------


class TestRGPDOptIn:
    """T3 + T4 : Bouton RGPD desactive si pas toutes les cases ; ecrit dans Config."""

    def test_rgpd_button_disabled_when_some_boxes_unchecked(self, tmp_path: Path):
        """Si au moins une case decochee -> bouton disabled."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        # 2 cochees sur 3
        page._rgpd_vars["screenshots"].get.return_value = True
        page._rgpd_vars["ocr_text"].get.return_value = True
        page._rgpd_vars["system_info"].get.return_value = False

        page._refresh_rgpd_button_state()

        page._rgpd_confirm_btn.configure.assert_called_with(state="disabled")

    def test_rgpd_button_enabled_when_all_boxes_checked(self, tmp_path: Path):
        """Si toutes les cases cochees -> bouton enabled."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        for v in page._rgpd_vars.values():
            v.get.return_value = True

        page._refresh_rgpd_button_state()

        page._rgpd_confirm_btn.configure.assert_called_with(state="normal")

    def test_rgpd_confirm_writes_optin_to_config(self, tmp_path: Path):
        """Click 'Accepter' apres 3 cases cochees -> ecrit dans Config['pilot']['rgpd']."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        for v in page._rgpd_vars.values():
            v.get.return_value = True

        page._on_rgpd_confirm()

        pilot_cfg = config.get("pilot", {})
        rgpd = pilot_cfg.get("rgpd", {})
        # Les 3 keys RGPD sont a True
        for k in PILOT_RGPD_KEYS:
            assert rgpd.get(k) is True, f"Cle RGPD manquante : {k}"
        # Timestamp present
        assert "accepted_at" in rgpd
        assert isinstance(rgpd["accepted_at"], str)
        assert len(rgpd["accepted_at"]) > 0

        # Persiste sur disque
        reloaded = Config(config_dir=tmp_path)
        assert reloaded.get("pilot", {}).get("rgpd", {}).get("screenshots") is True

    def test_rgpd_confirm_with_missing_box_does_not_write(self, tmp_path: Path):
        """Click sur 'Accepter' avec une case manquante -> pas d'ecriture."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        # Seulement 2 cases cochees sur 3
        page._rgpd_vars["screenshots"].get.return_value = True
        page._rgpd_vars["ocr_text"].get.return_value = True
        page._rgpd_vars["system_info"].get.return_value = False

        page._on_rgpd_confirm()

        # Rien ecrit dans pilot.rgpd
        pilot_cfg = config.get("pilot", {})
        assert "rgpd" not in pilot_cfg or not pilot_cfg["rgpd"]


# ---------------------------------------------------------------------------
# Tests : API key field, save pilot config, sandbox change
# ---------------------------------------------------------------------------


class TestPilotConfigSave:
    """T5 + T6 : sauvegarde API key + budget + sandbox + popup full_screen."""

    def test_save_pilot_config_writes_api_key_budget_sandbox(self, tmp_path: Path):
        """Click 'Sauvegarder' -> ecrit api_key, budget_eur, sandbox_mode dans Config."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        page._pilot_api_entry.get.return_value = "sk-ant-test123"
        page._pilot_budget_var.get.return_value = "10.0"
        page._pilot_sandbox_var.get.return_value = "application"

        page._save_pilot_config()

        pilot_cfg = config.get("pilot", {})
        assert pilot_cfg.get("api_key") == "sk-ant-test123"
        assert pilot_cfg.get("budget_eur") == 10.0
        assert pilot_cfg.get("sandbox_mode") == "application"

    def test_save_pilot_config_rejects_invalid_budget(self, tmp_path: Path):
        """Budget invalide (chaine non-numerique) -> message d'erreur, pas d'ecriture."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        page._pilot_api_entry.get.return_value = "sk-ant-x"
        page._pilot_budget_var.get.return_value = "abc"
        page._pilot_sandbox_var.get.return_value = "winboost_window"

        page._save_pilot_config()

        # Pas d'ecriture
        pilot_cfg = config.get("pilot", {})
        assert "budget_eur" not in pilot_cfg

        # Message d'erreur affiche
        page._pilot_status.configure.assert_any_call(
            text="Plafond invalide : entre un nombre.",
            text_color="#e74c3c",  # COLORS["error"]
        )

    def test_save_pilot_config_rejects_budget_out_of_range(self, tmp_path: Path):
        """Budget hors bornes [1, 50] -> message d'erreur, pas d'ecriture."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        # Budget trop bas
        page._pilot_budget_var.get.return_value = "0.5"
        page._save_pilot_config()
        assert "budget_eur" not in config.get("pilot", {}) or \
            config.get("pilot", {}).get("budget_eur") != 0.5

        # Budget trop haut
        page._pilot_budget_var.get.return_value = "999"
        page._save_pilot_config()
        # Pas accepte
        assert config.get("pilot", {}).get("budget_eur") != 999

    def test_full_screen_sandbox_triggers_confirmation_popup(self, tmp_path: Path):
        """Selection 'full_screen' -> popup messagebox.askyesno."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        # Patch tkinter.messagebox.askyesno pour qu'il retourne False
        with patch("tkinter.messagebox.askyesno", return_value=False) as mock_box:
            page._on_sandbox_change("full_screen")

        # Le popup a bien ete affiche
        mock_box.assert_called_once()
        # L'user a dit non -> revert au mode default
        page._pilot_sandbox_var.set.assert_called_with("winboost_window")

    def test_full_screen_sandbox_confirmed_keeps_choice(self, tmp_path: Path):
        """Si user confirme le full_screen -> on ne revert pas."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        with patch("tkinter.messagebox.askyesno", return_value=True):
            page._on_sandbox_change("full_screen")

        # Pas de revert
        page._pilot_sandbox_var.set.assert_not_called()

    def test_other_sandbox_modes_no_popup(self, tmp_path: Path):
        """Selection 'window'/'application'/'region' -> pas de popup."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        with patch("tkinter.messagebox.askyesno") as mock_box:
            page._on_sandbox_change("winboost_window")
            page._on_sandbox_change("application")
            page._on_sandbox_change("screen_region")

        mock_box.assert_not_called()


# ---------------------------------------------------------------------------
# Tests : API key paste from clipboard
# ---------------------------------------------------------------------------


class TestPasteApiKey:
    """T7 : bouton 'Coller' lit le clipboard et insert dans le champ."""

    def test_paste_api_key_inserts_clipboard_text(self, tmp_path: Path):
        """clipboard='sk-ant-xyz' -> entry.insert(...)."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        page.clipboard_get = MagicMock(return_value="  sk-ant-fromclip  ")

        page._on_paste_api_key()

        page._pilot_api_entry.delete.assert_called_with(0, "end")
        page._pilot_api_entry.insert.assert_called_with(0, "sk-ant-fromclip")

    def test_paste_api_key_handles_empty_clipboard(self, tmp_path: Path):
        """Clipboard vide -> pas d'ecriture."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        page.clipboard_get = MagicMock(return_value="")

        page._on_paste_api_key()

        page._pilot_api_entry.delete.assert_not_called()
        page._pilot_api_entry.insert.assert_not_called()

    def test_paste_api_key_handles_clipboard_failure(self, tmp_path: Path):
        """Clipboard inaccessible -> pas de crash."""
        config = Config(config_dir=tmp_path)
        page = _make_settings_skeleton(config)

        page.clipboard_get = MagicMock(side_effect=RuntimeError("no clipboard"))

        # Ne doit pas crasher
        page._on_paste_api_key()

        page._pilot_api_entry.insert.assert_not_called()
