# -*- coding: utf-8 -*-
"""
test_lang.py
Verifie que le paquet lang expose les dicts attendus et que viewer_config
les reexpose sans les alterer.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lang import lang_fr
from lang import lang_en
import viewer_config


def _placeholders(s):
    import re
    return set(re.findall(r"\{(\w+)\}", s)) if isinstance(s, str) else set()


def test_lang_fr_has_expected_dicts():
    assert isinstance(lang_fr.MSG_UI, dict) and len(lang_fr.MSG_UI) > 0
    assert isinstance(lang_fr.MSG_LOG, dict) and len(lang_fr.MSG_LOG) > 0
    assert isinstance(lang_fr.MSG_ERR, dict) and len(lang_fr.MSG_ERR) > 0


def test_viewer_config_reexports_lang_fr():
    assert viewer_config.MSG_UI is lang_fr.MSG_UI
    assert viewer_config.MSG_LOG is lang_fr.MSG_LOG
    assert viewer_config.MSG_ERR is lang_fr.MSG_ERR


def test_tr_ui_unchanged_behavior():
    assert viewer_config.tr_ui("project") == "Projet"
    assert viewer_config.tr_ui("missing_key_xyz") == "missing_key_xyz"


def test_lang_en_has_same_keys_as_lang_fr():
    for dict_name in ("MSG_UI", "MSG_LOG", "MSG_ERR"):
        fr_dict = getattr(lang_fr, dict_name)
        en_dict = getattr(lang_en, dict_name)
        missing = set(fr_dict) - set(en_dict)
        extra = set(en_dict) - set(fr_dict)
        assert not missing, f"{dict_name}: lang_en missing keys {sorted(missing)}"
        assert not extra, f"{dict_name}: lang_en has extra keys {sorted(extra)}"


def test_lang_en_placeholders_match_lang_fr():
    for dict_name in ("MSG_UI", "MSG_LOG", "MSG_ERR"):
        fr_dict = getattr(lang_fr, dict_name)
        en_dict = getattr(lang_en, dict_name)
        for key, fr_value in fr_dict.items():
            assert _placeholders(fr_value) == _placeholders(en_dict[key]), (
                f"{dict_name}[{key}]: placeholder mismatch"
            )


def test_set_language_switches_active_dict():
    viewer_config.set_language("en")
    try:
        assert viewer_config.tr_ui("project") == lang_en.MSG_UI["project"]
    finally:
        viewer_config.set_language("fr")


def test_set_language_unknown_code_falls_back_to_default():
    viewer_config.set_language("xx")
    try:
        assert viewer_config.get_language() == "fr"
        assert viewer_config.tr_ui("project") == "Projet"
    finally:
        viewer_config.set_language("fr")


def test_missing_key_in_active_language_falls_back_to_french():
    viewer_config.set_language("en")
    try:
        del lang_en.MSG_UI["project"]
        assert viewer_config.tr_ui("project") == "Projet"
    finally:
        lang_en.MSG_UI["project"] = "Project"
        viewer_config.set_language("fr")


if __name__ == "__main__":
    test_lang_fr_has_expected_dicts()
    test_viewer_config_reexports_lang_fr()
    test_tr_ui_unchanged_behavior()
    test_lang_en_has_same_keys_as_lang_fr()
    test_lang_en_placeholders_match_lang_fr()
    test_set_language_switches_active_dict()
    test_set_language_unknown_code_falls_back_to_default()
    test_missing_key_in_active_language_falls_back_to_french()
    print("OK")
