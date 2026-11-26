# -*- coding: utf-8 -*-
"""Refus d'une version d'API trop ancienne : journal, boite de dialogue et branchements."""

import os
import sys
import types
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("PySide6")

import main_window as mw
from viewer_config import tr_ui


def test_refusal_is_logged_and_shown_in_a_dialog(monkeypatch):
    shown, logs = [], []
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda parent, title, text: shown.append((title, text)))
    host = types.SimpleNamespace(log=lambda text, level="info": logs.append((level, text)))
    mw.MainWindow._on_api_version_refused(host, "ligne 1\nligne 2")
    assert logs == [("error", "ligne 1"), ("error", "ligne 2")]
    assert shown == [(tr_ui("api_version_title"), "ligne 1\nligne 2")]


def test_refused_load_resets_the_state_like_other_load_errors():
    host = MagicMock()
    mw.MainWindow.on_model_version_refused(host, "refus")
    host._reset_after_load_failure.assert_called_once_with()
    host._on_api_version_refused.assert_called_once_with("refus")


def test_load_model_connects_the_refusal(monkeypatch, tmp_path):
    fto = tmp_path / "m.fto"
    fto.write_bytes(b"")
    host = MagicMock(cmb_display_mode=None, viewer=None)
    host.fto_edit.text.return_value = str(fto)
    host.host_edit.text.return_value = "http://h"
    factory = MagicMock()
    monkeypatch.setattr(mw, "LoadModelWorker", factory)
    mw.MainWindow.load_model(host)
    factory.return_value.version_refused.connect.assert_called_once_with(host.on_model_version_refused)
