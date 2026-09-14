# -*- coding: utf-8 -*-
"""Verifie le primitive geometrique de la selection par fenetre."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_widget import _seg_intersects_rect

R = (0.0, 0.0, 10.0, 10.0)


def test_seg_intersects_rect():
    assert _seg_intersects_rect(-5, 5, 15, 5, *R)      # traverse de part en part
    assert _seg_intersects_rect(2, 2, 8, 8, *R)        # entierement dedans
    assert _seg_intersects_rect(-5, -5, 5, 5, *R)      # entre par un coin
    assert _seg_intersects_rect(10, 5, 20, 5, *R)      # demarre sur le bord
    assert not _seg_intersects_rect(-5, 5, -1, 5, *R)  # entierement a gauche
    assert not _seg_intersects_rect(-5, 20, 15, 20, *R)  # entierement au-dessus
    assert not _seg_intersects_rect(21, 0, 0, 21, *R)  # diagonale qui frole sans entrer


if __name__ == "__main__":
    test_seg_intersects_rect()
    print("ok")
