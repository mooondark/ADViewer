# -*- coding: utf-8 -*-
"""Ecriture de config.ini : atomique, un echec ne detruit jamais l'ancien fichier."""

import configparser
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_config import write_ini_atomic


def _cfg(value):
    cfg = configparser.ConfigParser()
    cfg["general"] = {"theme": value}
    return cfg


def _read(path):
    cfg = configparser.ConfigParser()
    cfg.read(path, encoding="utf-8")
    return cfg["general"]["theme"]


def test_creates_the_file_and_leaves_no_temp_file(tmp_path):
    path = str(tmp_path / "config.ini")
    write_ini_atomic(_cfg("dark"), path)
    assert _read(path) == "dark"
    assert os.listdir(tmp_path) == ["config.ini"]


def test_replaces_an_existing_file(tmp_path):
    path = str(tmp_path / "config.ini")
    write_ini_atomic(_cfg("dark"), path)
    write_ini_atomic(_cfg("light"), path)
    assert _read(path) == "light"


def test_a_failed_write_keeps_the_previous_file_and_cleans_up(tmp_path):
    path = str(tmp_path / "config.ini")
    write_ini_atomic(_cfg("dark"), path)

    class Broken(configparser.ConfigParser):
        def write(self, fp, *args, **kwargs):
            fp.write("[general]\ntheme = hal")   # coupure en plein milieu
            raise OSError("disk full")

    with pytest.raises(OSError):
        write_ini_atomic(Broken(), path)
    assert _read(path) == "dark"
    assert os.listdir(tmp_path) == ["config.ini"]
