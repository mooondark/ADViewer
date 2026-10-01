# -*- coding: utf-8 -*-
"""
clip_box.py
Boite de coupe du viewer 3D : geometrie pure (emprise, decoupe segment/polygone,
deplacement de faces, projections souris), helpers VTK (plans, aretes de coupe)
et ClipBoxController (plans de clipping GPU, cadre et poignees en calque
superpose, aretes de coupe).

Meme pattern que minimap.py / flight_navigation.py : les fonctions pures sont
testables sans fenetre VTK. Boite = [xmin, xmax, ymin, ymax, zmin, zmax] ;
face i : axe i // 2, cote i % 2 (0 = min, 1 = max).
"""

import contextlib
import math
import time

import vtk
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def expand_bounds(bounds, margin_pct, min_size=0.1):
    dims = [float(bounds[2 * i + 1]) - float(bounds[2 * i]) for i in range(3)]
    floor = max(float(min_size), 0.01 * max(dims))
    out = []
    for i in range(3):
        lo, hi = float(bounds[2 * i]), float(bounds[2 * i + 1])
        pad = (hi - lo) * float(margin_pct) / 100.0
        lo, hi = lo - pad, hi + pad
        if hi - lo < floor:
            mid = (lo + hi) / 2.0
            lo, hi = mid - floor / 2.0, mid + floor / 2.0
        out += [lo, hi]
    return out


def point_in_box(point, box, tol=1e-6):
    for i in range(3):
        if point[i] < box[2 * i] - tol or point[i] > box[2 * i + 1] + tol:
            return False
    return True


def clip_segment(p0, p1, box):
    t0, t1 = 0.0, 1.0
    for i in range(3):
        d = p1[i] - p0[i]
        lo, hi = box[2 * i], box[2 * i + 1]
        if abs(d) < 1e-15:
            if p0[i] < lo or p0[i] > hi:
                return None
            continue
        ta, tb = (lo - p0[i]) / d, (hi - p0[i]) / d
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 > t1:
            return None
    q0 = tuple(float(p0[i] + t0 * (p1[i] - p0[i])) for i in range(3))
    q1 = tuple(float(p0[i] + t1 * (p1[i] - p0[i])) for i in range(3))
    return q0, q1


def clip_polygon(points, box):
    poly = [tuple(float(c) for c in p) for p in points]
    for axis in range(3):
        for side in (0, 1):
            if not poly:
                return []
            bound = box[2 * axis + side]
            sign = 1.0 if side == 0 else -1.0
            out = []
            prev = poly[-1]
            prev_in = sign * (prev[axis] - bound) >= 0.0
            for cur in poly:
                cur_in = sign * (cur[axis] - bound) >= 0.0
                if cur_in != prev_in:
                    t = (bound - prev[axis]) / (cur[axis] - prev[axis])
                    out.append(tuple(prev[k] + t * (cur[k] - prev[k]) for k in range(3)))
                if cur_in:
                    out.append(cur)
                prev, prev_in = cur, cur_in
            poly = out
    return poly


def clip_cell_points(points, box):
    n = len(points)
    if n == 0:
        return []
    if n == 1:
        return [tuple(points[0])] if point_in_box(points[0], box) else []
    if n == 2:
        seg = clip_segment(points[0], points[1], box)
        return list(seg) if seg else []
    return clip_polygon(points, box)


def move_face(box, face, value, min_size):
    out = list(box)
    if face % 2 == 0:
        out[face] = min(float(value), out[face + 1] - min_size)
    else:
        out[face] = max(float(value), out[face - 1] + min_size)
    return out


def move_box(box, delta):
    return [box[i] + delta[i // 2] for i in range(6)]


def box_center(box):
    return tuple((box[2 * i] + box[2 * i + 1]) / 2.0 for i in range(3))


def handle_positions(box):
    center = box_center(box)
    out = {"center": center}
    for face in range(6):
        p = list(center)
        p[face // 2] = box[face]
        out[face] = tuple(p)
    return out


def face_axis_dir(face):
    d = [0.0, 0.0, 0.0]
    d[face // 2] = 1.0
    return tuple(d)


def pick_handle(screen_points, mouse, radius_px):
    best, best_d2 = None, radius_px * radius_px
    for key, sp in screen_points.items():
        if sp is None:
            continue
        d2 = (sp[0] - mouse[0]) ** 2 + (sp[1] - mouse[1]) ** 2
        if d2 <= best_d2:
            best, best_d2 = key, d2
    return best


def world_per_pixel(distance, view_angle_deg, parallel, parallel_scale, viewport_height_px):
    h = max(1.0, float(viewport_height_px))
    if parallel:
        return 2.0 * float(parallel_scale) / h
    return 2.0 * max(float(distance), 1e-9) * math.tan(math.radians(float(view_angle_deg)) / 2.0) / h


def line_param_closest_to_ray(ray_o, ray_d, line_p, line_d):
    w0 = tuple(ray_o[i] - line_p[i] for i in range(3))
    a, b, c = _dot(ray_d, ray_d), _dot(ray_d, line_d), _dot(line_d, line_d)
    d, e = _dot(ray_d, w0), _dot(line_d, w0)
    denom = a * c - b * b
    if abs(denom) <= 1e-9 * a * c:
        return None
    return (a * e - b * d) / denom


def ray_plane_intersection(ray_o, ray_d, plane_p, plane_n):
    denom = _dot(ray_d, plane_n)
    if abs(denom) < 1e-12:
        return None
    t = _dot(tuple(plane_p[i] - ray_o[i] for i in range(3)), plane_n) / denom
    return tuple(ray_o[i] + t * ray_d[i] for i in range(3))


def make_planes(box):
    planes = [vtk.vtkPlane() for _ in range(6)]
    update_planes(planes, box)
    return planes


def update_planes(planes, box):
    for face, plane in enumerate(planes):
        axis, side = divmod(face, 2)
        origin = [0.0, 0.0, 0.0]
        origin[axis] = box[face]
        normal = [0.0, 0.0, 0.0]
        normal[axis] = 1.0 if side == 0 else -1.0
        plane.SetOrigin(*origin)
        plane.SetNormal(*normal)


def _inside_points_polydata(cut, box, eps):
    verts = cut.GetVerts()
    pts = cut.GetPoints()
    out_pts = vtk.vtkPoints()
    out_cells = vtk.vtkCellArray()
    ids = vtk.vtkIdList()
    verts.InitTraversal()
    while verts.GetNextCell(ids):
        for k in range(ids.GetNumberOfIds()):
            p = pts.GetPoint(ids.GetId(k))
            if point_in_box(p, box, eps):
                pid = out_pts.InsertNextPoint(*p)
                out_cells.InsertNextCell(1)
                out_cells.InsertCellPoint(pid)
    if out_pts.GetNumberOfPoints() == 0:
        return None
    pd = vtk.vtkPolyData()
    pd.SetPoints(out_pts)
    pd.SetVerts(out_cells)
    return pd


def compute_cut_edges(polydata, box, eps=None):
    """Traces de coupe de `polydata` par les 6 faces de `box` : (lignes, points).
    Une surface donne des lignes (contour de section), une ligne donne des
    points. Chaque trace est rognee a l'emprise de la boite."""
    if polydata is None or polydata.GetNumberOfCells() == 0:
        return None, None
    if eps is None:
        eps = 1e-4 * max(box[1] - box[0], box[3] - box[2], box[5] - box[4])
    bounds_box = vtk.vtkBox()
    bounds_box.SetBounds(box[0] - eps, box[1] + eps, box[2] - eps, box[3] + eps, box[4] - eps, box[5] + eps)
    lines_app = vtk.vtkAppendPolyData()
    points_app = vtk.vtkAppendPolyData()
    n_lines = n_points = 0
    for plane in make_planes(box):
        cutter = vtk.vtkCutter()
        cutter.SetCutFunction(plane)
        cutter.SetInputData(polydata)
        cutter.Update()
        cut = cutter.GetOutput()
        if cut.GetNumberOfLines() > 0:
            lines_only = vtk.vtkPolyData()
            lines_only.SetPoints(cut.GetPoints())
            lines_only.SetLines(cut.GetLines())
            clipper = vtk.vtkClipPolyData()
            clipper.SetInputData(lines_only)
            clipper.SetClipFunction(bounds_box)
            clipper.InsideOutOn()
            clipper.Update()
            if clipper.GetOutput().GetNumberOfCells() > 0:
                part = vtk.vtkPolyData()
                part.DeepCopy(clipper.GetOutput())
                lines_app.AddInputData(part)
                n_lines += 1
        if cut.GetNumberOfVerts() > 0:
            pts_pd = _inside_points_polydata(cut, box, eps)
            if pts_pd is not None:
                points_app.AddInputData(pts_pd)
                n_points += 1
    lines_pd = points_pd = None
    if n_lines:
        lines_app.Update()
        lines_pd = vtk.vtkPolyData()
        lines_pd.DeepCopy(lines_app.GetOutput())
    if n_points:
        points_app.Update()
        points_pd = vtk.vtkPolyData()
        points_pd.DeepCopy(points_app.GetOutput())
    return lines_pd, points_pd


class ClipBoxController:
    """Boite de coupe. `host` est le VTKViewerWidget qui le possede."""

    MIN_SIZE_RATIO = 0.01
    HANDLE_RADIUS_PX = 7.0
    CENTER_HANDLE_RADIUS_PX = 10.0
    PICK_RADIUS_PX = 14.0
    HOVER_SCALE = 1.4
    _FACE_COLORS = {
        0: (1.0, 0.25, 0.25), 1: (1.0, 0.25, 0.25),
        2: (0.25, 0.8, 0.25), 3: (0.25, 0.8, 0.25),
        4: (0.3, 0.5, 1.0), 5: (0.3, 0.5, 1.0),
        "center": (0.92, 0.92, 0.92),
    }

    def __init__(self, host):
        import viewer_config as _cfg

        self.host = host
        self.active = False
        self.frame_visible = True
        self.margin_pct = _cfg.CLIP_BOX_DEFAULT_MARGIN_PCT
        self.box_color = tuple(_cfg.CLIP_BOX_COLOR)
        self.edge_color = tuple(_cfg.CLIP_EDGE_COLOR)
        self.box = None
        self.planes = []
        self.collection = None
        self.on_box_changed = None
        self._min_sizes = [0.0, 0.0, 0.0]
        self._overlay = None
        self._outline = None
        self._frame_actor = None
        self._handle_actors = {}
        self._camera_tag = None
        self._gizmos_hidden = False
        self._hover = None
        self._drag = None
        self._edge_actor = None
        self._edge_points_actor = None
        self._edge_signature = None
        self._last_edge_ms = 0.0
        self.edge_budget_ms = _cfg.CLIP_EDGE_BUDGET_MS

    def _tol(self):
        return 1e-4 * max(self.box[1] - self.box[0], self.box[3] - self.box[2], self.box[5] - self.box[4])

    def _render(self):
        rw = self.host.render_window
        if rw is not None:
            rw.Render()

    def _notify(self):
        if self.on_box_changed is not None:
            self.on_box_changed(list(self.box) if self.active else None)

    def activate(self, bounds):
        if self.active or bounds is None:
            return False
        self.box = expand_bounds(bounds, self.margin_pct)
        dims = [self.box[2 * i + 1] - self.box[2 * i] for i in range(3)]
        self._min_sizes = [max(self.MIN_SIZE_RATIO * d, 1e-6) for d in dims]
        self.planes = make_planes(self.box)
        self.collection = vtk.vtkPlaneCollection()
        for plane in self.planes:
            self.collection.AddItem(plane)
        self.active = True
        for actor in self.host._clippable_actors():
            self.apply_to_actor(actor)
        self._build_gizmos()
        self._build_edges()
        self.refresh_edges(force=True)
        self._notify()
        self._render()
        return True

    def deactivate(self):
        if not self.active:
            return False
        self.active = False
        for actor in self.host._clippable_actors():
            mapper = self._mapper_of(actor)
            if mapper is not None:
                mapper.RemoveAllClippingPlanes()
            elif isinstance(actor, vtkBillboardTextActor3D) and getattr(actor, "_clip_hidden", False):
                actor.SetVisibility(1)
                actor._clip_hidden = False
        self._end_drag()
        self._destroy_gizmos()
        self._destroy_edges()
        self.box = None
        self.planes = []
        self.collection = None
        self._notify()
        self._render()
        return True

    @staticmethod
    def _mapper_of(actor):
        get_mapper = getattr(actor, "GetMapper", None)
        mapper = get_mapper() if get_mapper is not None else None
        return mapper if mapper is not None and hasattr(mapper, "SetClippingPlanes") else None

    def apply_to_actor(self, actor):
        if not self.active or actor is None or getattr(actor, "_clip_exempt", False):
            return
        mapper = self._mapper_of(actor)
        if mapper is not None:
            mapper.SetClippingPlanes(self.collection)
        elif isinstance(actor, vtkBillboardTextActor3D):
            self._apply_label_visibility(actor)

    def _apply_label_visibility(self, actor):
        if point_in_box(actor.GetPosition(), self.box, self._tol()):
            if getattr(actor, "_clip_hidden", False):
                actor.SetVisibility(1)
                actor._clip_hidden = False
        elif actor.GetVisibility():
            actor.SetVisibility(0)
            actor._clip_hidden = True

    def refresh_labels(self):
        if not self.active:
            return
        for actor in self.host._clippable_actors():
            if isinstance(actor, vtkBillboardTextActor3D):
                self._apply_label_visibility(actor)

    def _build_edges(self):
        for attr, is_points in (("_edge_actor", False), ("_edge_points_actor", True)):
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(vtk.vtkPolyData())
            actor = self._make_gizmo_actor(mapper)
            prop = actor.GetProperty()
            prop.SetColor(*self.edge_color)
            prop.LightingOff()
            if is_points:
                prop.SetPointSize(8.0)
                prop.RenderPointsAsSpheresOn()
            else:
                prop.SetLineWidth(3.0)
            mapper.SetResolveCoincidentTopologyToPolygonOffset()
            mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-1.0, -1.0)
            actor.SetVisibility(0)
            self.host.renderer.AddActor(actor)
            setattr(self, attr, actor)
        self._edge_signature = None

    def _destroy_edges(self):
        for attr in ("_edge_actor", "_edge_points_actor"):
            actor = getattr(self, attr)
            if actor is not None:
                self.host.renderer.RemoveActor(actor)
            setattr(self, attr, None)
        self._edge_signature = None

    @staticmethod
    def _fill_edge_actor(actor, append, count):
        if count == 0:
            actor.SetVisibility(0)
            return
        append.Update()
        out = vtk.vtkPolyData()
        out.DeepCopy(append.GetOutput())
        actor.GetMapper().SetInputData(out)
        actor.SetVisibility(1)

    def refresh_edges(self, force=False):
        if not self.active or self._edge_actor is None:
            return
        sources = self.host._clip_edge_sources()
        signature = (tuple(self.box), tuple((id(pd), pd.GetMTime()) for pd in sources))
        if not force and signature == self._edge_signature:
            return
        start = time.perf_counter()
        lines_app = vtk.vtkAppendPolyData()
        points_app = vtk.vtkAppendPolyData()
        n_lines = n_points = 0
        for pd in sources:
            lines_pd, points_pd = compute_cut_edges(pd, self.box)
            if lines_pd is not None:
                lines_app.AddInputData(lines_pd)
                n_lines += 1
            if points_pd is not None:
                points_app.AddInputData(points_pd)
                n_points += 1
        self._fill_edge_actor(self._edge_actor, lines_app, n_lines)
        self._fill_edge_actor(self._edge_points_actor, points_app, n_points)
        self._edge_signature = signature
        self._last_edge_ms = (time.perf_counter() - start) * 1000.0

    def set_style(self, box_color, edge_color):
        self.box_color = tuple(box_color)
        self.edge_color = tuple(edge_color)
        if self._frame_actor is not None:
            self._frame_actor.GetProperty().SetColor(*self.box_color)
        for actor in (self._edge_actor, self._edge_points_actor):
            if actor is not None:
                actor.GetProperty().SetColor(*self.edge_color)
        self._render()

    def accepts_point(self, point):
        return (not self.active) or point_in_box(point, self.box, self._tol())

    def visible_part(self, points):
        if not self.active:
            return list(points)
        return clip_cell_points(points, self.box)

    @property
    def hover_key(self):
        return self._hover

    def _make_gizmo_actor(self, mapper):
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.PickableOff()
        actor._clip_exempt = True
        return actor

    def _ensure_overlay(self):
        rw = self.host.render_window
        if rw is None:
            return None
        if self._overlay is None:
            ren = vtk.vtkRenderer()
            ren.SetLayer(1)
            ren.InteractiveOff()
            ren.SetActiveCamera(self.host.renderer.GetActiveCamera())
            if rw.GetNumberOfLayers() < 2:
                rw.SetNumberOfLayers(2)
            rw.AddRenderer(ren)
            self._overlay = ren
        return self._overlay

    def _build_gizmos(self):
        self._outline = vtk.vtkOutlineSource()
        self._outline.SetBounds(*self.box)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(self._outline.GetOutputPort())
        self._frame_actor = self._make_gizmo_actor(mapper)
        prop = self._frame_actor.GetProperty()
        prop.SetColor(*self.box_color)
        prop.SetLineWidth(2.0)
        prop.LightingOff()
        for key, color in self._FACE_COLORS.items():
            src = vtk.vtkSphereSource()
            src.SetRadius(1.0)
            src.SetThetaResolution(20)
            src.SetPhiResolution(20)
            m = vtk.vtkPolyDataMapper()
            m.SetInputConnection(src.GetOutputPort())
            actor = self._make_gizmo_actor(m)
            actor.GetProperty().SetColor(*color)
            self._handle_actors[key] = actor
        overlay = self._ensure_overlay()
        if overlay is not None:
            overlay.AddActor(self._frame_actor)
            for actor in self._handle_actors.values():
                overlay.AddActor(actor)
        camera = self.host.renderer.GetActiveCamera()
        self._camera_tag = camera.AddObserver("ModifiedEvent", self._on_camera_modified)
        self._update_gizmo_geometry()
        self._apply_gizmo_visibility()

    def _destroy_gizmos(self):
        if self._camera_tag is not None:
            self.host.renderer.GetActiveCamera().RemoveObserver(self._camera_tag)
            self._camera_tag = None
        if self._overlay is not None:
            if self._frame_actor is not None:
                self._overlay.RemoveActor(self._frame_actor)
            for actor in self._handle_actors.values():
                self._overlay.RemoveActor(actor)
        self._frame_actor = None
        self._handle_actors = {}
        self._outline = None
        self._hover = None

    def _on_camera_modified(self, obj, event):
        self._update_gizmo_geometry()

    def _update_gizmo_geometry(self):
        if not self.active or self._outline is None:
            return
        self._outline.SetBounds(*self.box)
        renderer = self.host.renderer
        camera = renderer.GetActiveCamera()
        height = renderer.GetSize()[1] or 1
        cam_pos = camera.GetPosition()
        for key, position in handle_positions(self.box).items():
            actor = self._handle_actors[key]
            distance = math.dist(cam_pos, position)
            wpp = world_per_pixel(
                distance, camera.GetViewAngle(), camera.GetParallelProjection(),
                camera.GetParallelScale(), height,
            )
            radius_px = self.CENTER_HANDLE_RADIUS_PX if key == "center" else self.HANDLE_RADIUS_PX
            if key == self._hover:
                radius_px *= self.HOVER_SCALE
            actor.SetPosition(*position)
            scale = wpp * radius_px
            actor.SetScale(scale, scale, scale)

    def _apply_gizmo_visibility(self):
        visible = 1 if (self.active and self.frame_visible and not self._gizmos_hidden) else 0
        if self._frame_actor is not None:
            self._frame_actor.SetVisibility(visible)
        for actor in self._handle_actors.values():
            actor.SetVisibility(visible)

    def set_frame_visible(self, visible):
        self.frame_visible = bool(visible)
        self._apply_gizmo_visibility()
        self._render()

    @contextlib.contextmanager
    def gizmos_hidden(self):
        previous = self._gizmos_hidden
        self._gizmos_hidden = True
        self._apply_gizmo_visibility()
        try:
            yield
        finally:
            self._gizmos_hidden = previous
            self._apply_gizmo_visibility()

    def handles_enabled(self):
        host = self.host
        return (
            self.active and self.frame_visible and not self._gizmos_hidden
            and not host._window_select_mode and not host._zoom_window_mode
            and not host._flight.active
        )

    def _screen_points(self):
        renderer = self.host.renderer
        view_dir = renderer.GetActiveCamera().GetDirectionOfProjection()
        out = {}
        for key, p in handle_positions(self.box).items():
            if key != "center" and abs(_dot(face_axis_dir(key), view_dir)) > 0.95:
                out[key] = None
                continue
            renderer.SetWorldPoint(p[0], p[1], p[2], 1.0)
            renderer.WorldToDisplay()
            d = renderer.GetDisplayPoint()
            out[key] = (d[0], d[1]) if 0.0 <= d[2] <= 1.0 else None
        return out

    def _mouse_ray(self, x, y):
        renderer = self.host.renderer
        pts = []
        for z in (0.0, 1.0):
            renderer.SetDisplayPoint(float(x), float(y), z)
            renderer.DisplayToWorld()
            w = renderer.GetWorldPoint()
            pts.append((w[0] / w[3], w[1] / w[3], w[2] / w[3]))
        return pts[0], tuple(pts[1][i] - pts[0][i] for i in range(3))

    def _set_hover(self, key):
        if key != self._hover:
            self._hover = key
            self._update_gizmo_geometry()
            self._render()

    def on_left_press(self, x, y):
        if not self.handles_enabled():
            return False
        key = pick_handle(self._screen_points(), (x, y), self.PICK_RADIUS_PX)
        if key is None:
            return False
        ray_o, ray_d = self._mouse_ray(x, y)
        drag = {"key": key}
        if key == "center":
            normal = self.host.renderer.GetActiveCamera().GetDirectionOfProjection()
            center = box_center(self.box)
            hit = ray_plane_intersection(ray_o, ray_d, center, normal)
            if hit is None:
                return False
            drag.update(plane_p=center, plane_n=normal, last_hit=hit)
        else:
            origin = handle_positions(self.box)[key]
            axis = face_axis_dir(key)
            t0 = line_param_closest_to_ray(ray_o, ray_d, origin, axis)
            if t0 is None:
                return False
            drag.update(origin=origin, axis=axis, t0=t0, start_value=self.box[key])
        self._drag = drag
        self._set_hover(key)
        return True

    def on_mouse_move(self, x, y):
        if self._drag is not None:
            self._drag_to(x, y)
            return True
        if not self.handles_enabled():
            self._set_hover(None)
            return False
        self._set_hover(pick_handle(self._screen_points(), (x, y), self.PICK_RADIUS_PX))
        return False

    def _drag_to(self, x, y):
        drag = self._drag
        ray_o, ray_d = self._mouse_ray(x, y)
        if drag["key"] == "center":
            hit = ray_plane_intersection(ray_o, ray_d, drag["plane_p"], drag["plane_n"])
            if hit is None:
                return
            delta = tuple(hit[i] - drag["last_hit"][i] for i in range(3))
            drag["last_hit"] = hit
            self._set_box(move_box(self.box, delta), final=False)
            return
        face = drag["key"]
        t = line_param_closest_to_ray(ray_o, ray_d, drag["origin"], drag["axis"])
        if t is None:
            return
        value = drag["start_value"] + (t - drag["t0"])
        self._set_box(move_face(self.box, face, value, self._min_sizes[face // 2]), final=False)

    def _end_drag(self):
        self._drag = None

    def on_left_release(self):
        if self._drag is None:
            return False
        self._drag = None
        self._set_box(self.box, final=True)
        return True

    def _set_box(self, box, final):
        self.box = box
        update_planes(self.planes, box)
        self.collection.Modified()
        self._update_gizmo_geometry()
        self.refresh_labels()
        if final or self._last_edge_ms <= self.edge_budget_ms:
            self.refresh_edges(force=final)
        self._notify()
        self._render()
