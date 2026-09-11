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
import viewer_config


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


if __name__ == "__main__":
    test_lang_fr_has_expected_dicts()
    test_viewer_config_reexports_lang_fr()
    test_tr_ui_unchanged_behavior()
    print("OK")
