# -*- coding: utf-8 -*-
"""Temps de construction du solide des profils sur N filaires synthetiques.
`python scripts/bench_profiles.py [N]` (defaut 5000)."""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_widget import VTKViewerWidget
import ad_model_data as md

SECOBJ = {1: {"name": "IPE 300", "type": "I_SYMETRIC"}, 2: {"name": "HEA 200", "type": "I_SYMETRIC"},
          3: {"name": "R 30x50", "type": "RECTANGLE"}, 4: {"name": "TUBE 100x100x5", "type": "RECTANGULAR_TUBE"},
          5: {"name": "CHS 114.3x5", "type": "CIRCULAR_TUBE"}, 6: {"name": "UPN 200", "type": "U"}}

n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
random.seed(1)
lines, secs = [], []
for i in range(n):
    p1 = {"x": random.uniform(0, 50), "y": random.uniform(0, 50), "z": random.uniform(0, 20)}
    p2 = {"x": p1["x"] + random.uniform(1, 6), "y": p1["y"] + random.uniform(-3, 3), "z": p1["z"] + random.uniform(-1, 1)}
    el = {"generalBeamType": "Beam", "section": {"value": 1 + i % 6}, "sectionOrientationAngle": 0.0,
          "geomPtStart": p1, "geomPtEnd": p2}
    secs.append(md._build_line_section_render(el, p1, p2, SECOBJ))
    lines.append([(p1["x"], p1["y"], p1["z"]), (p2["x"], p2["y"], p2["z"])])

w = VTKViewerWidget.__new__(VTKViewerWidget)
w._color_by_section = False
t0 = time.perf_counter()
pd = w._build_profiles_polydata(lines, secs, element_indexes=list(range(n)))
print(f"total {time.perf_counter() - t0:.2f} s cells {pd.GetNumberOfCells()}")
