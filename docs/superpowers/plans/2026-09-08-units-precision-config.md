# Réglage des unités affichées et de leur précision — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un menu Paramètres > Unités et précision permettant de choisir, par grandeur, l'unité d'affichage et le nombre de décimales, persistés dans `config.ini`.

**Architecture:** Un module dédié `display_units.py` tient un registre des grandeurs (unité d'entrée API, unités proposées + facteurs, défauts) et un état runtime (unité + décimales par grandeur). Les helpers de formatage de `ad_model_data.py` sont réécrits pour déléguer à ce module ; `viewer_widget.py` et `main_window.py` consultent le module pour les quelques sites de formatage restants. Un dialogue Qt règle l'état, `MainWindow` le charge/sauve dans `config.ini` et recharge le modèle après changement.

**Tech Stack:** Python 3, PySide6, openpyxl, VTK. Pas de framework de test dans le dépôt — vérification par auto-test `assert` sous `if __name__ == "__main__":` exécuté avec `python <module>.py`, plus `python -m py_compile` et essais manuels dans l'app.

**Spec:** `docs/superpowers/specs/2026-09-08-units-precision-config-design.md`

## Global Constraints

- Style (CLAUDE.md) : code d'abord, explication après. Solution la plus simple qui marche, pas de sur-ingénierie. Pas d'abstraction pour un usage unique. Lire le fichier avant de le modifier. Pas de docstring / annotation de type sur du code non modifié. Pas de gestion d'erreur pour des cas impossibles.
- Formatage : trait d'union simple, guillemets droits, pas de tiret cadratin ni de symbole Unicode décoratif. Les caractères naturels requis par le contenu (`²`, `°`, lettres accentuées) sont autorisés. Sortie code copiable-collable.
- `display_units.py` : aucune dépendance vers Qt ni vers les autres modules du projet.
- Décimales : bornées `[0, 6]` partout.
- Défauts du registre = comportement historique (aux exceptions listées dans la spec : `_format_thickness_smart`, `.6g` angle/aire, seuil scientifique, unité overlay).
- `config.ini` : section `[units]`, deux clés par grandeur (`<kind>_unit`, `<kind>_decimals`). Aucun module autre que `MainWindow` ne touche `config.ini`.
- Grandeurs (clés) : `length`, `section_length`, `force`, `moment`, `stress`, `angle`, `area`.
- Version courante `APP_VERSION` dans `viewer_config.py` (à incrémenter en dernière tâche).

---

### Task 1 : Module `display_units.py`

**Files:**
- Create: `display_units.py`

**Interfaces:**
- Consumes: rien (module racine).
- Produces :
  - `reset() -> None`
  - `units_for(kind: str) -> list[str]`
  - `state_for(kind: str) -> tuple[str, int]`
  - `set_unit(kind: str, unit: str) -> None`
  - `set_decimals(kind: str, n) -> None`
  - `scale(kind: str) -> float`
  - `unit(kind: str) -> str` (libellé d'affichage : `cm2`->`cm²`, `m2`->`m²`, `deg`->`°`, sinon tel quel)
  - `decimals(kind: str) -> int`
  - `conv(value_api, kind: str) -> float | None`
  - `fmt(value_api, kind: str) -> str` (`"<nombre> <unité>"`, `"N/A"` si non numérique)
  - `get_state_ini() -> dict[str, str]`
  - `load_state_ini(mapping: dict | None) -> None`

- [ ] **Step 1 : Écrire le module avec son auto-test**

Create `display_units.py` :

```python
# -*- coding: utf-8 -*-
"""display_units.py
Registre central des unites d'affichage et de leur precision.
Sans dependance Qt ni vers les autres modules du projet.
Importe par ad_model_data, viewer_widget, main_window.
"""

import math

_DEG_PER_RAD = 180.0 / math.pi

_DECIMALS_MIN = 0
_DECIMALS_MAX = 6

# kind -> {units: {label: facteur depuis l'unite d'entree API}, default_unit, default_decimals}
_REGISTRY = {
    "length":         {"units": {"mm": 1000.0, "cm": 100.0, "m": 1.0},        "default_unit": "m",    "default_decimals": 2},
    "section_length": {"units": {"mm": 1000.0, "cm": 100.0, "m": 1.0},        "default_unit": "cm",   "default_decimals": 2},
    "force":          {"units": {"N": 1.0, "daN": 0.1, "kN": 1.0e-3},         "default_unit": "kN",   "default_decimals": 2},
    "moment":         {"units": {"N.m": 1.0, "daN.m": 0.1, "kN.m": 1.0e-3},   "default_unit": "kN.m", "default_decimals": 2},
    "stress":         {"units": {"Pa": 1.0, "kPa": 1.0e-3, "MPa": 1.0e-6},    "default_unit": "MPa",  "default_decimals": 2},
    "angle":          {"units": {"deg": _DEG_PER_RAD, "rad": 1.0},            "default_unit": "deg",  "default_decimals": 2},
    "area":           {"units": {"cm2": 1.0e4, "m2": 1.0},                    "default_unit": "m2",   "default_decimals": 2},
}

_DISPLAY_LABEL = {"cm2": "cm²", "m2": "m²", "deg": "°"}

_state = {}


def reset():
    _state.clear()
    for kind, desc in _REGISTRY.items():
        _state[kind] = {"unit": desc["default_unit"], "decimals": desc["default_decimals"]}


reset()


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def units_for(kind):
    return list(_REGISTRY[kind]["units"].keys())


def state_for(kind):
    s = _state[kind]
    return s["unit"], s["decimals"]


def set_unit(kind, unit_label):
    if kind in _REGISTRY and unit_label in _REGISTRY[kind]["units"]:
        _state[kind]["unit"] = unit_label


def set_decimals(kind, n):
    if kind not in _REGISTRY:
        return
    try:
        n = int(n)
    except (TypeError, ValueError):
        return
    _state[kind]["decimals"] = max(_DECIMALS_MIN, min(_DECIMALS_MAX, n))


def scale(kind):
    return _REGISTRY[kind]["units"][_state[kind]["unit"]]


def unit(kind):
    u = _state[kind]["unit"]
    return _DISPLAY_LABEL.get(u, u)


def decimals(kind):
    return _state[kind]["decimals"]


def conv(value_api, kind):
    v = _to_float(value_api)
    if v is None:
        return None
    return v * scale(kind)


def _format_number(value, dec):
    if dec >= 1 and value != 0.0 and abs(value) < 10.0 ** (-dec):
        return f"{value:.2e}"
    return f"{value:.{dec}f}"


def fmt(value_api, kind):
    v = conv(value_api, kind)
    if v is None:
        return "N/A"
    label = unit(kind)
    text = _format_number(v, decimals(kind))
    return f"{text} {label}" if label else text


def get_state_ini():
    out = {}
    for kind in _REGISTRY:
        out[f"{kind}_unit"] = _state[kind]["unit"]
        out[f"{kind}_decimals"] = str(_state[kind]["decimals"])
    return out


def load_state_ini(mapping):
    mapping = mapping or {}
    for kind in _REGISTRY:
        u = mapping.get(f"{kind}_unit")
        if u in _REGISTRY[kind]["units"]:
            _state[kind]["unit"] = u
        d = mapping.get(f"{kind}_decimals")
        try:
            _state[kind]["decimals"] = max(_DECIMALS_MIN, min(_DECIMALS_MAX, int(d)))
        except (TypeError, ValueError):
            pass


if __name__ == "__main__":
    reset()
    assert fmt(1234.0, "force") == "1.23 kN", fmt(1234.0, "force")
    assert fmt(0.05, "section_length") == "5.00 cm", fmt(0.05, "section_length")
    assert fmt(1_000_000.0, "stress") == "1.00 MPa", fmt(1_000_000.0, "stress")
    assert fmt(math.pi, "angle") == "180.00 °", fmt(math.pi, "angle")
    assert fmt(2.0, "length") == "2.00 m", fmt(2.0, "length")
    assert fmt(4.0, "area") == "4.00 m²", fmt(4.0, "area")
    assert fmt(None, "force") == "N/A"
    assert fmt("x", "force") == "N/A"

    set_unit("force", "N")
    assert fmt(1234.0, "force") == "1234.00 N", fmt(1234.0, "force")
    set_unit("length", "mm")
    assert fmt(2.0, "length") == "2000.00 mm", fmt(2.0, "length")
    set_decimals("force", 0)
    assert fmt(1234.0, "force") == "1234 N", fmt(1234.0, "force")
    set_decimals("force", 99)
    assert state_for("force")[1] == 6
    set_decimals("force", -3)
    assert state_for("force")[1] == 0

    reset()
    assert fmt(1.0, "force") == "1.00e-03 kN", fmt(1.0, "force")  # 1 N -> 0.001 kN -> scientifique

    reset()
    ini = get_state_ini()
    assert ini["length_unit"] == "m" and ini["length_decimals"] == "2", ini
    load_state_ini({"length_unit": "cm", "length_decimals": "1"})
    assert state_for("length") == ("cm", 1), state_for("length")
    load_state_ini({"length_unit": "bogus", "length_decimals": "abc"})
    assert state_for("length") == ("cm", 1), state_for("length")  # invalides ignores
    reset()
    load_state_ini(get_state_ini())
    assert state_for("force") == ("kN", 2), state_for("force")  # round-trip stable
    assert conv(None, "length") is None
    assert abs(conv(2.0, "length") - 2.0) < 1e-9

    print("display_units self-check OK")
```

- [ ] **Step 2 : Lancer l'auto-test, vérifier l'échec attendu absent (le fichier n'existe pas encore avant Step 1 ; ici on exécute après création)**

Run: `python display_units.py`
Expected: `display_units self-check OK` sur stdout, code retour 0. Si un `assert` casse, corriger le corps du module (pas l'assert).

- [ ] **Step 3 : Commit**

```bash
git add display_units.py
git commit -m "feat: module display_units (registre unites + precision)"
```

---

### Task 2 : Persistance `config.ini` dans `MainWindow`

**Files:**
- Modify: `main_window.py` (imports ; `save_config` ~ligne 998 ; `_load_or_create_config` ~ligne 1044)

**Interfaces:**
- Consumes: `display_units.get_state_ini()`, `display_units.load_state_ini(mapping)` (Task 1).
- Produces: section `[units]` dans `config.ini` ; état `display_units` initialisé au démarrage depuis le fichier.

- [ ] **Step 1 : Importer le module**

Dans `main_window.py`, à côté des autres imports projet (`import viewer_config`, `from ad_model_data import *`), ajouter :

```python
import display_units
```

- [ ] **Step 2 : Écrire la section `[units]` dans `save_config`**

Dans `MainWindow.save_config()`, après le bloc `cfg["colors"] = { ... }` et avant `with open(self._config_path(), "w", ...)` :

```python
        cfg["units"] = display_units.get_state_ini()
```

- [ ] **Step 3 : Lire la section `[units]` dans `_load_or_create_config`**

Dans `_load_or_create_config()`, dans le `try:` sous `self._suspend_config_save = True`, juste après le bloc qui calcule `self.png_export_scale` :

```python
            display_units.load_state_ini(
                dict(cfg["units"]) if cfg.has_section("units") else {}
            )
```

- [ ] **Step 4 : Compiler**

Run: `python -m py_compile main_window.py`
Expected: aucun message, code retour 0.

- [ ] **Step 5 : Vérifier le round-trip config.ini**

Run (dans un répertoire de travail jetable, sans lancer l'UI complète) :

```bash
python -c "import configparser, display_units as du; du.set_unit('force','N'); du.set_decimals('length',1); c=configparser.ConfigParser(); c['units']=du.get_state_ini(); import io; s=io.StringIO(); c.write(s); print(s.getvalue())"
```
Expected: la sortie contient `[units]` avec `force_unit = N` et `length_decimals = 1`.

- [ ] **Step 6 : Commit**

```bash
git add main_window.py
git commit -m "feat: persistance des reglages d'unites dans config.ini"
```

---

### Task 3 : Délégation dans `ad_model_data.py`

**Files:**
- Modify: `ad_model_data.py` (imports ; helpers `_format_*` ~lignes 620-800, 1300-1320 ; table de résultats `_fmt_result_value` ~1193-1232 ; `_linear_result_scale_and_unit` + `read_linear_element_diagram_results` ~1476-1578 ; métrés ~660-747)

**Interfaces:**
- Consumes: `display_units` — `fmt(value_api, kind)`, `scale(kind)`, `unit(kind)`, `decimals(kind)` (Task 1).
- Produces:
  - Helpers `_format_force_kn`, `_format_moment_knm`, `_format_length_m`, `_format_length_cm_fixed`, `_format_thickness_smart`, `_format_eccentricity_cm`, `_format_angle_degrees` : mêmes signatures, délèguent à `display_units`.
  - Nouvelle fonction `_result_kind(family_key: str, value_key: str) -> str` (renvoie `"section_length"|"force"|"moment"|"stress"` ou `""` si famille inconnue).
  - `read_linear_element_diagram_results(...)` renvoie en plus la clé `"decimals": int` dans son dict.
  - Suppression des helpers morts `_format_length_cm`, `_format_area_m2`, `_format_fixed_unit`, `_fmt_result_value`.

- [ ] **Step 1 : Importer le module**

Dans `ad_model_data.py`, après `from ad_api_client import *` :

```python
import display_units as du
```

- [ ] **Step 2 : Réécrire les helpers vivants**

Remplacer les corps (signatures inchangées) :

```python
def _format_force_kn(value) -> str:
    return du.fmt(value, "force")


def _format_moment_knm(value) -> str:
    return du.fmt(value, "moment")


def _format_length_m(value) -> str:
    return du.fmt(value, "length")
```

```python
def _format_length_cm_fixed(value, decimals: int = 2) -> str:
    return du.fmt(value, "section_length")
```

```python
def _format_thickness_smart(value) -> str:
    return du.fmt(value, "section_length")
```

```python
def _format_eccentricity_cm(value) -> str:
    return du.fmt(value, "section_length")
```

```python
def _format_angle_degrees(value) -> str:
    return du.fmt(value, "angle")
```

- [ ] **Step 3 : Remplacer les 3 appels à `_format_fixed_unit` puis supprimer les helpers morts**

Dans `_build_linear_length_takeoff` (~ligne 671) :

```python
    return [
        {"name": name, "value": value, "value_text": du.fmt(value, "length")}
        for name, value in sorted(totals.items(), key=lambda item: str(item[0]).lower())
    ]
```

Dans `_build_planar_takeoff` (~ligne 730) :

```python
    return [
        {"name": name, "area": data["area"], "area_text": du.fmt(data["area"], "area")}
        for name, data in ordered
    ]
```

Dans `_build_planar_material_takeoff` (~ligne 745) :

```python
    return [
        {"name": name, "area": area, "area_text": du.fmt(area, "area")}
        for name, area in sorted(totals.items(), key=lambda item: str(item[0]).lower())
    ]
```

Supprimer entièrement les définitions de `_format_fixed_unit` (~634), `_format_length_cm` (~778), `_format_area_m2` (~620). Laisser `_format_numeric` et `_format_length_cm_fixed` en place.

- [ ] **Step 4 : Table de résultats d'appui — remplacer `_fmt_result_value`**

Dans le bloc de lignes `("<key>", f"{_fmt_result_value(...)} <unit>")` (~1206-1232), remplacer chaque paire :

```python
            ("dx", du.fmt(_dict_get_ci(payload, "dx"), "section_length")),
            ("dy", du.fmt(_dict_get_ci(payload, "dy"), "section_length")),
            ("dz", du.fmt(_dict_get_ci(payload, "dz"), "section_length")),
            ("d",  du.fmt(_dict_get_ci(payload, "d"),  "section_length")),
            ("rx", du.fmt(_dict_get_ci(payload, "rx"), "angle")),
            ("ry", du.fmt(_dict_get_ci(payload, "ry"), "angle")),
            ("rz", du.fmt(_dict_get_ci(payload, "rz"), "angle")),
            ("r",  du.fmt(_dict_get_ci(payload, "r"),  "angle")),
```

```python
            ("fx", du.fmt(_dict_get_ci(payload, "fx"), "force")),
            ("fy", du.fmt(_dict_get_ci(payload, "fy"), "force")),
            ("fz", du.fmt(_dict_get_ci(payload, "fz"), "force")),
            ("mx", du.fmt(_dict_get_ci(payload, "mx"), "moment")),
            ("my", du.fmt(_dict_get_ci(payload, "my"), "moment")),
            ("mz", du.fmt(_dict_get_ci(payload, "mz"), "moment")),
```

```python
            ("sx", du.fmt(_dict_get_ci(payload, "sx"), "stress")),
            ("sy", du.fmt(_dict_get_ci(payload, "sy"), "stress")),
            ("sz", du.fmt(_dict_get_ci(payload, "sz"), "stress")),
            ("s",  du.fmt(_dict_get_ci(payload, "s"),  "stress")),
```

Le `_radians_to_degrees` explicite sur `rx..r` disparait (la conversion rad -> deg est dans `du`, grandeur `angle`, unité d'entrée rad). Supprimer ensuite la définition de `_fmt_result_value` (~1193), plus aucun appelant.

- [ ] **Step 5 : `_result_kind` + `_linear_result_scale_and_unit` + payload `decimals`**

Ajouter, juste avant `_linear_result_scale_and_unit` :

```python
def _result_kind(family_key: str, value_key: str) -> str:
    family = _normalize_result_family_key(family_key)
    value_key = str(value_key or "").strip().lower()
    if family == "deplacements":
        return "section_length"
    if family == "efforts":
        return "moment" if value_key in ("mx", "my", "mz") else "force"
    if family == "contraintes":
        return "stress"
    return ""
```

Réécrire `_linear_result_scale_and_unit` :

```python
def _linear_result_scale_and_unit(family_key: str, value_key: str):
    kind = _result_kind(family_key, value_key)
    if not kind:
        return 1.0, ""
    return du.scale(kind), du.unit(kind)
```

Dans `read_linear_element_diagram_results`, dans le dict de retour, à côté de `"unit": _linear_result_unit(family_label, value_label),` ajouter :

```python
        "decimals": (lambda k: du.decimals(k) if k else 3)(_result_kind(family_label, value_label)),
```

(3 = valeur de repli historique des labels de diagramme.)

- [ ] **Step 6 : Compiler + smoke**

Run: `python -m py_compile ad_model_data.py`
Expected: OK.

Run:
```bash
python -c "import display_units as du; import ad_model_data as m; print(m._format_force_kn(1234.0), '|', m._format_angle_degrees(0.7853981633974483), '|', m._format_thickness_smart(0.2)); du.set_unit('force','N'); print(m._format_force_kn(1234.0)); print(m._linear_result_scale_and_unit('efforts','fx'), m._linear_result_scale_and_unit('efforts','mx'), m._linear_result_scale_and_unit('contraintes','sx'), m._linear_result_scale_and_unit('autre','x'))"
```
Expected (état par défaut puis `force`->N) :
`1.23 kN | 45.00 ° | 20.00 cm`
`1234.00 N`
`(0.001, 'kN') (0.001, 'kN.m') (1e-06, 'MPa') (1.0, '')`

- [ ] **Step 7 : Vérifier qu'aucun appelant orphelin ne reste**

Run: `grep -n "_fmt_result_value\|_format_fixed_unit\|_format_length_cm(\|_format_area_m2" ad_model_data.py`
Expected: aucune ligne (ni def, ni appel).

- [ ] **Step 8 : Commit**

```bash
git add ad_model_data.py
git commit -m "feat: ad_model_data delegue le formatage a display_units"
```

---

### Task 4 : Sites de formatage `viewer_widget.py` et `main_window.py`

**Files:**
- Modify: `viewer_widget.py` (`_build_linear_diagram_actors` ~1429 et son `_format_diagram_label_value` ~1599 ; `set_linear_result_diagram` ~1691 ; `add_linear_result_diagram` ~1698 ; overlay `_overlay_mouse_world_txt` ~1895)
- Modify: `main_window.py` (3 appels diagramme ~3900 / ~3928 / ~4366 ; centroïde ~3951 ; `export_analysis_results_csv` ~3606-3626)

**Interfaces:**
- Consumes: `display_units` — `fmt`, `conv`, `unit` (Task 1) ; clé `"decimals"` du payload diagramme (Task 3).
- Produces:
  - `set_linear_result_diagram(..., unit="", decimals=None)` et `add_linear_result_diagram(..., unit="", decimals=None)` (nouveau paramètre optionnel).
  - `_build_linear_diagram_actors(..., unit="", decimals=None)`.

- [ ] **Step 1 : `viewer_widget.py` — importer le module**

À côté de `import viewer_config` / `from viewer_config import *` en tête de `viewer_widget.py` :

```python
import display_units as du
```

- [ ] **Step 2 : `viewer_widget.py` — propager `decimals` au builder**

`_build_linear_diagram_actors` : ajouter le paramètre `decimals=None` à la signature (après `unit: str = ""`).

Dans `_format_diagram_label_value` (~1599), remplacer :

```python
            if abs(value) < 0.001:
                formatted = "+0" if value >= 0.0 else "-0"
            else:
                formatted = f"{value:.3f}"
```

par :

```python
            dec = 3 if decimals is None else int(decimals)
            if dec >= 1 and abs(value) < 10.0 ** (-dec):
                formatted = "+0" if value >= 0.0 else "-0"
            else:
                formatted = f"{value:.{dec}f}"
```

`set_linear_result_diagram` et `add_linear_result_diagram` : ajouter `decimals=None` à la signature et le passer à `_build_linear_diagram_actors(..., unit=unit, decimals=decimals)`.

- [ ] **Step 3 : `viewer_widget.py` — overlay coordonnées**

Repérer la ligne (~1895) :

```python
            self._overlay_mouse_world_txt = f"X : {wx:.2f}   Y : {wy:.2f}   Z : {wz:.2f}"
```

Remplacer par (unité affichée une seule fois en fin de ligne) :

```python
            _n = du.decimals("length")
            _u = du.unit("length")
            self._overlay_mouse_world_txt = (
                f"X : {du.conv(wx, 'length'):.{_n}f}   "
                f"Y : {du.conv(wy, 'length'):.{_n}f}   "
                f"Z : {du.conv(wz, 'length'):.{_n}f} {_u}"
            )
```

(`wx/wy/wz` sont toujours numériques ici — pas de garde `None` nécessaire.)

- [ ] **Step 4 : `viewer_widget.py` — compiler**

Run: `python -m py_compile viewer_widget.py`
Expected: OK.

- [ ] **Step 5 : `main_window.py` — propager `decimals` aux 3 appels diagramme**

Aux 3 endroits qui appellent `set_linear_result_diagram` / `add_linear_result_diagram` (`_on_multi_linear_result_*` ~3900, `_on_analysis_results_loaded` ~3928, `_refresh_current_linear_diagram` ~4366), là où `unit = str(payload.get("unit") or "").strip()` est calculé, ajouter juste après :

```python
        diagram_decimals = payload.get("decimals", 3)
```

et passer `decimals=diagram_decimals` à l'appel correspondant.

- [ ] **Step 6 : `main_window.py` — centroïde appui planaire**

Repérer (~3951) :

```python
                        {"name": "X", "value": f"{float(centroid_info.get('x')):.3f} m"},
                        {"name": "Y", "value": f"{float(centroid_info.get('y')):.3f} m"},
                        {"name": "Z", "value": f"{float(centroid_info.get('z')):.3f} m"},
```

Remplacer par :

```python
                        {"name": "X", "value": display_units.fmt(centroid_info.get("x"), "length")},
                        {"name": "Y", "value": display_units.fmt(centroid_info.get("y"), "length")},
                        {"name": "Z", "value": display_units.fmt(centroid_info.get("z"), "length")},
```

- [ ] **Step 7 : `main_window.py` — export xlsx**

Dans `export_analysis_results_csv`, sur le chemin mono-élément (~3623-3625) :

```python
                ws.append(["abscissa", *components])
                for row in rows:
                    ws.append([row.get("abscissa", ""), *[row.get(key, "") for key in components]])
```

Remplacer par :

```python
                comp_kind = {
                    "dx": "section_length", "dy": "section_length", "dz": "section_length", "d": "section_length",
                    "fx": "force", "fy": "force", "fz": "force",
                    "mx": "moment", "my": "moment", "mz": "moment",
                    "sxxMin": "stress", "sxxMax": "stress", "sxyMin": "stress", "sxyMax": "stress",
                    "sxzMin": "stress", "sxzMax": "stress", "sv": "stress",
                }
                ws.append([
                    f"abscissa ({display_units.unit('length')})",
                    *[f"{c} ({display_units.unit(comp_kind[c])})" if c in comp_kind else c for c in components],
                ])
                for row in rows:
                    absc = display_units.conv(row.get("abscissa"), "length")
                    ws.append([absc if absc is not None else "", *[row.get(key, "") for key in components]])
```

Le chemin multi-éléments passe par `_write_linear_families_to_sheet` : si cette fonction fait le même `ws.append(["abscissa", ...])`, appliquer la même transformation à cet endroit. Sinon, la laisser (hors périmètre confirmé à la lecture).

- [ ] **Step 8 : `main_window.py` — compiler**

Run: `python -m py_compile main_window.py`
Expected: OK.

- [ ] **Step 9 : Commit**

```bash
git add viewer_widget.py main_window.py
git commit -m "feat: diagrammes, overlay, centroide et xlsx suivent display_units"
```

---

### Task 5 : Dialogue de réglage + menu + rafraîchissement

**Files:**
- Modify: `viewer_config.py` (`MSG_UI`)
- Modify: `main_window.py` (imports PySide6 ; nouvelle classe `UnitsDialog` ; `_build_menu` ~1683 ; nouvelles méthodes `open_units_dialog` et `_refresh_after_units_change`)

**Interfaces:**
- Consumes: `display_units` — `units_for`, `state_for`, `set_unit`, `set_decimals` (Task 1) ; `MainWindow.load_model()` (existant) ; `tr_ui` (existant).
- Produces: entrée de menu Paramètres > « Unités et précision… » ouvrant `UnitsDialog` ; `config.ini` sauvé et modèle rechargé au clic OK.

- [ ] **Step 1 : Traductions dans `viewer_config.py`**

Dans `MSG_UI`, près de `"menu_png_export"` / `"png_export_dialog_*"` :

```python
    "menu_units": "Unites et precision...",
    "units_dialog_title": "Unites et precision",
    "units_label_decimals": "decimales",
    "units_label_length": "Longueurs (elements)",
    "units_label_section_length": "Longueurs (sections)",
    "units_label_force": "Efforts",
    "units_label_moment": "Moments",
    "units_label_stress": "Contraintes",
    "units_label_angle": "Angles",
    "units_label_area": "Aires",
```

(Accents conformes au reste du fichier : si `MSG_UI` utilise déjà des accents ailleurs, écrire « Unités et précision… », « décimales », etc.)

- [ ] **Step 2 : Importer `QSpinBox`**

Dans `main_window.py`, dans le `from PySide6.QtWidgets import (...)`, ajouter `QSpinBox` à la liste (à côté de `QDoubleSpinBox`).

- [ ] **Step 3 : Classe `UnitsDialog`**

Après la classe `SettingsDialog` dans `main_window.py` :

```python
class UnitsDialog(QDialog):
    KINDS = [
        ("length", "units_label_length"),
        ("section_length", "units_label_section_length"),
        ("force", "units_label_force"),
        ("moment", "units_label_moment"),
        ("stress", "units_label_stress"),
        ("angle", "units_label_angle"),
        ("area", "units_label_area"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr_ui("units_dialog_title"))
        self.setModal(True)

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        layout.addLayout(grid)

        self._rows = {}
        for row, (kind, label_key) in enumerate(self.KINDS):
            cur_unit, cur_dec = display_units.state_for(kind)
            combo = QComboBox()
            combo.setView(QListView())
            for u in display_units.units_for(kind):
                combo.addItem(u, u)
            idx = combo.findData(cur_unit)
            combo.setCurrentIndex(idx if idx >= 0 else 0)

            spin = QSpinBox()
            spin.setRange(0, 6)
            spin.setValue(int(cur_dec))

            grid.addWidget(QLabel(tr_ui(label_key)), row, 0, Qt.AlignVCenter)
            grid.addWidget(combo, row, 1)
            grid.addWidget(QLabel(tr_ui("units_label_decimals")), row, 2, Qt.AlignVCenter)
            grid.addWidget(spin, row, 3)
            self._rows[kind] = (combo, spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self):
        out = {}
        for kind, (combo, spin) in self._rows.items():
            out[kind] = (combo.currentData(), int(spin.value()))
        return out
```

Le combo affiche le label brut de l'unité (`kN`, `mm`, `deg`, `m2`…) ; la
`data` de chaque item est ce même label, c'est ce que renvoie `get_values()` et
ce qu'attend `display_units.set_unit`.

- [ ] **Step 4 : Entrée de menu**

Dans `_build_menu()`, juste après l'ajout de `act_png_export` au `settings_menu` (~1685) :

```python
        act_units = QAction(tr_ui("menu_units"), self)
        act_units.triggered.connect(self.open_units_dialog)
        settings_menu.addAction(act_units)
```

- [ ] **Step 5 : `open_units_dialog` et `_refresh_after_units_change`**

Ajouter dans `MainWindow` (près de `open_png_export_dialog`) :

```python
    def open_units_dialog(self):
        dlg = UnitsDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        for kind, (unit_label, dec) in dlg.get_values().items():
            display_units.set_unit(kind, unit_label)
            display_units.set_decimals(kind, dec)
        self.save_config()
        self._refresh_after_units_change()

    def _refresh_after_units_change(self):
        if (self.current_model_data is not None
                and self.fto_edit is not None
                and self.fto_edit.text().strip()):
            self.load_model()
```

- [ ] **Step 6 : Compiler**

Run: `python -m py_compile main_window.py viewer_config.py`
Expected: OK.

- [ ] **Step 7 : Essai manuel**

Lancer l'app (`python viewer.py`), ouvrir un modèle calculé.
1. Paramètres > Unités et précision… : le dialogue s'ouvre, 7 lignes, valeurs = défauts.
2. Passer `Efforts` de `kN` à `N`, `Efforts décimales` à 1, OK.
3. Le modèle se recharge ; onglet Propriétés d'un mur : hauteur/largeur inchangées (length), aucune erreur.
4. Sélectionner un appui avec résultats : les réactions s'affichent en `N` avec 1 décimale.
5. Rouvrir le dialogue : `Efforts` = `N`, décimales = 1 (persistance en session).
6. Fermer l'app, rouvrir : le dialogue montre toujours `N` / 1 (persistance `config.ini`).
7. Vérifier `config.ini` : section `[units]` présente avec `force_unit = N`, `force_decimals = 1`.

- [ ] **Step 8 : Commit**

```bash
git add main_window.py viewer_config.py
git commit -m "feat: dialogue Unites et precision + rechargement apres changement"
```

---

### Task 6 : CHANGELOG et version

**Files:**
- Modify: `viewer_config.py` (`APP_VERSION`)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: rien.
- Produces: rien de code.

- [ ] **Step 1 : Incrémenter `APP_VERSION`**

Dans `viewer_config.py`, passer `APP_VERSION` à la valeur suivante (ex. si `"1.95"` -> `"1.96"` ; vérifier la valeur courante avant d'écrire).

- [ ] **Step 2 : Entrée CHANGELOG**

En tête de `CHANGELOG.md`, sous le bandeau, ajouter une section pour la nouvelle version, au-dessus de la précédente :

```markdown
## 1.96

### FR
- Nouveau menu Parametres > Unites et precision : choix de l'unite et du nombre de decimales par grandeur (longueurs elements, longueurs sections, efforts, moments, contraintes, angles, aires). Reglages sauves dans config.ini et appliques aux onglets Proprietes et Resultats, aux diagrammes 3D, a l'overlay de coordonnees et a l'export .xlsx. Le modele est recharge apres validation.
- L'affichage automatique cm/mm des epaisseurs est remplace par l'unite fixe choisie (defaut cm). Angles et aires passent d'un affichage a 6 chiffres significatifs a un nombre de decimales fixe (defaut 2).

### EN
- New Settings > Units and precision menu: pick the unit and the number of decimals per quantity (element lengths, section lengths, forces, moments, stresses, angles, areas). Saved to config.ini and applied to the Properties and Results tabs, 3D diagrams, the coordinate overlay and the .xlsx export. The model reloads after confirmation.
- The automatic cm/mm display of thicknesses is replaced by the fixed chosen unit (default cm). Angles and areas move from 6 significant figures to a fixed number of decimals (default 2).
```

(Adapter le numéro de version à celui écrit au Step 1 ; respecter les accents si le fichier en utilise.)

- [ ] **Step 3 : Commit**

```bash
git add viewer_config.py CHANGELOG.md
git commit -m "chore: version + changelog reglage des unites"
```

---

## Auto-revue

**1. Couverture de la spec**
- Module `display_units.py` (registre, état, persistance, format/conv) -> Task 1.
- Section `[units]` de `config.ini`, lecture/écriture par `MainWindow` -> Task 2.
- Helpers `ad_model_data.py` délégués + table de résultats + pipeline diagramme/xlsx + `_result_kind` + payload `decimals` -> Task 3.
- `viewer_widget.py` labels de diagramme (+ `decimals`) + overlay -> Task 4.
- `main_window.py` centroïde + xlsx (en-têtes unité, abscisse convertie) -> Task 4.
- Dialogue `UnitsDialog` + entrée de menu + traductions -> Task 5.
- `_refresh_after_units_change` (rechargement modèle) -> Task 5.
- Suppression helpers morts + `_fmt_result_value` -> Task 3 (Step 3, Step 4, Step 7).
- CHANGELOG + version -> Task 6.
- Changements de comportement assumés (thickness_smart, .6g, seuil scientifique, overlay) : portés par Task 1 (défauts + `_format_number`) et Task 4 (overlay), documentés Task 6.

**2. Placeholders** : aucun « TBD/TODO ». La seule conditionnelle (« si `_write_linear_families_to_sheet` fait le même append… sinon laisser ») est une instruction de lecture précise, pas un trou : la transformation à appliquer est donnée mot pour mot au Step 7 de Task 4.

**3. Cohérence des types**
- `display_units.fmt/conv/scale/unit/decimals/units_for/state_for/set_unit/set_decimals/get_state_ini/load_state_ini/reset` : signatures définies Task 1, utilisées à l'identique Tasks 2-5.
- `_result_kind(family_key, value_key) -> str` : défini Task 3 Step 5, réutilisé dans le même Step pour `read_linear_element_diagram_results`.
- `set_linear_result_diagram` / `add_linear_result_diagram` / `_build_linear_diagram_actors` : paramètre `decimals=None` ajouté Task 4 Step 2, fourni par `main_window` Task 4 Step 5.
- Clé payload `"decimals"` : produite Task 3 Step 5, consommée Task 4 Step 5.
- `import display_units` (nom complet) dans `main_window.py` (Task 2) vs `import display_units as du` dans `ad_model_data.py` (Task 3) et `viewer_widget.py` (Task 4) : cohérent avec l'usage réel dans chaque fichier (`display_units.fmt` en clair dans `main_window`, `du.fmt` ailleurs). Vérifié : Task 4 Step 6 et Task 5 utilisent bien `display_units.` (nom complet) dans `main_window.py`.
