# -*- coding: utf-8 -*-
"""apply_vtk_font : Segoe UI (fichier systeme, gras ou non), Arial si le fichier est absent."""

import os
import sys

import vtk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import viewer_config


def _fonts_dir(tmp_path, monkeypatch, *names):
    for name in names:
        (tmp_path / name).write_text("")
    monkeypatch.setattr(viewer_config, "_FONTS_DIR", str(tmp_path))


def test_regular_text_uses_the_regular_font_file(tmp_path, monkeypatch):
    _fonts_dir(tmp_path, monkeypatch, "segoeui.ttf", "segoeuib.ttf")
    prop = vtk.vtkTextProperty()
    viewer_config.apply_vtk_font(prop)
    assert prop.GetFontFile() == str(tmp_path / "segoeui.ttf")
    assert prop.GetFontFamily() == 4      # VTK_FONT_FILE


def test_bold_text_uses_the_bold_font_file(tmp_path, monkeypatch):
    _fonts_dir(tmp_path, monkeypatch, "segoeui.ttf", "segoeuib.ttf")
    prop = vtk.vtkTextProperty()
    prop.BoldOn()
    viewer_config.apply_vtk_font(prop)
    assert prop.GetFontFile() == str(tmp_path / "segoeuib.ttf")


def test_falls_back_to_arial_when_the_font_file_is_missing(tmp_path, monkeypatch):
    _fonts_dir(tmp_path, monkeypatch)
    prop = vtk.vtkTextProperty()
    viewer_config.apply_vtk_font(prop)
    assert prop.GetFontFamilyAsString() == "Arial" and not prop.GetFontFile()
