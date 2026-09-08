# Réglage des unités affichées et de leur précision

Date : 2026-09-08
Statut : validé, prêt pour plan d'implémentation
Approche retenue : registre central dans un module dédié (`display_units.py`), les
helpers de formatage existants délèguent au registre.

## Objectif

Ajouter à ADViewer un menu **Paramètres > Unités et précision…** permettant de
choisir, par grandeur physique, l'unité d'affichage et le nombre de décimales.
Les réglages sont persistés dans `config.ini` (section `[units]`) et appliqués à
toutes les surfaces d'affichage numérique : onglet Propriétés, onglet Résultats,
diagrammes 3D + overlay coordonnées, export `.xlsx`.

Aujourd'hui, unités et décimales sont codées en dur dans ~30 sites répartis entre
`ad_model_data.py` (majorité), `viewer_widget.py` et `main_window.py`. Il n'existe
aucun point central.

## Périmètre

Inclus :

- Nouveau module `display_units.py` : registre des grandeurs, état runtime,
  fonctions de formatage / conversion.
- Persistance dans `config.ini` `[units]` (lecture + écriture via `MainWindow`).
- Dialogue `UnitsDialog` + entrée de menu.
- Réécriture des helpers de formatage de `ad_model_data.py` pour déléguer.
- Adaptation des sites de formatage de `viewer_widget.py` et `main_window.py`.
- Rafraîchissement de l'affichage courant au clic OK.

Exclu :

- Densité / masse volumique des matériaux : reste tel quel.
- Pentes (`slopeX`/`slopeY`) : ratios sans dimension, restent en `.6g`.
- Unités dans l'export IFC (`ad_ifc_exporter.py`) : non concerné, l'IFC écrit ses
  propres unités SI.
- Internationalisation des libellés d'unités (symboles fixes : `kN`, `m`, `°`…).

## Grandeurs configurables

| clé | unité d'entrée (API) | unités proposées (facteur depuis l'entrée) | défaut unité | défaut déc. |
|---|---|---|---|---|
| `length` | m | `mm` (1000), `cm` (100), `m` (1) | `m` | 2 |
| `section_length` | m | `mm` (1000), `cm` (100), `m` (1) | `cm` | 2 |
| `force` | N | `N` (1), `daN` (0.1), `kN` (1e-3) | `kN` | 2 |
| `moment` | N·m | `N.m` (1), `daN.m` (0.1), `kN.m` (1e-3) | `kN.m` | 2 |
| `stress` | Pa | `Pa` (1), `kPa` (1e-3), `MPa` (1e-6) | `MPa` | 2 |
| `angle` | rad | `deg` (180/π), `rad` (1) | `deg` | 2 |
| `area` | m² | `cm2` (1e4), `m2` (1) | `m2` | 2 |

Décimales : plage autorisée 0–6.

Affectation des grandeurs aux données :

- `length` : longueur de barre, hauteur/largeur de voile, coordonnées X/Y/Z
  (overlay souris, centroïde d'appui planaire), abscisse le long de la barre
  (colonne `abscissa` du xlsx).
- `section_length` : épaisseur, excentrement, translations de déplacement
  (`dx`/`dy`/`dz`/`d`).
- `force` : efforts `fx`/`fy`/`fz`, torseurs (`Fx…`, `N`, `Txy`, `Tyz`),
  réactions d'appui, effort tranchant.
- `moment` : moments `mx`/`my`/`mz`, torseurs (`Mx…`, `Mz`, `Mf`).
- `stress` : contraintes `sx`/`sy`/`sz`/`s`, `sxxMin/Max`, `sv`.
- `angle` : angle d'orientation de section, rotations `rx`/`ry`/`rz`/`r`.
- `area` : aires de métré, `area_text` des sections/matériaux.

## Module `display_units.py`

Aucune dépendance Qt ni vers les autres modules du projet.

### Registre statique

Structure interne (non exposée) : pour chaque clé, un descripteur
`{input_unit, units: {label: factor}, default_unit, default_decimals}`.
`factor` = valeur à multiplier à l'entrée API pour obtenir l'unité affichée.
Pour `angle`, le facteur `deg` est `180/math.pi`.

### État runtime

Module-level : `_state = {kind: {"unit": <label>, "decimals": <int>}}`, initialisé
aux défauts du registre à l'import.

- `set_unit(kind, unit)` — ignore silencieusement une unité inconnue pour la
  grandeur (garde l'ancienne).
- `set_decimals(kind, n)` — borne à `[0, 6]`.
- `reset()` — réinitialise aux défauts.
- `units_for(kind) -> list[str]` — liste ordonnée des unités proposées (pour la
  combo du dialogue).
- `state_for(kind) -> (unit, decimals)`.

### Persistance

- `get_state_ini() -> dict[str, str]` — produit les paires plates
  `{"length_unit": "m", "length_decimals": "2", …}` pour toutes les grandeurs.
- `load_state_ini(mapping)` — lit ces paires (tolérant : clés absentes →
  défaut ; unité invalide → défaut ; décimales non entières ou hors bornes →
  défaut de la grandeur). N'échoue jamais.

### Formatage / conversion

- `scale(kind) -> float` — facteur de l'unité courante.
- `unit(kind) -> str` — libellé d'affichage de l'unité courante. Table de rendu :
  `cm2` → `"cm²"`, `m2` → `"m²"`, `deg` → `"°"` ; toutes les autres unités
  s'affichent telles quelles (`"kN"`, `"kN.m"`, `"MPa"`, `"m"`, `"rad"`…).
- `decimals(kind) -> int`.
- `conv(value_api, kind) -> float | None` — `value_api * scale`, `None` si
  `value_api` non convertible.
- `fmt(value_api, kind) -> str` — `"<nombre> <unité>"`. Règles préservées depuis
  le code actuel :
  - entrée `None` / non numérique → `"N/A"` ;
  - `decimals >= 1`, valeur convertie non nulle et `abs < 10**(-decimals)` →
    notation scientifique `"{:.2e}"` (reprend le garde-fou de `_fmt_result_value`,
    qui utilisait `< 0.01`, généralisé aux décimales choisies) ; à `decimals = 0`
    la règle ne s'applique pas (arrondi entier normal) ;
  - sinon `f"{v:.{decimals}f}"`.

Les labels de diagramme n'appellent pas `fmt` (leur série est déjà convertie via
`scale`) : le builder de `viewer_widget.py` formate le nombre lui-même avec le
`decimals` reçu dans le payload, en conservant la règle `±0` existante (cf.
câblage `viewer_widget.py`).

## Persistance `config.ini`

Nouvelle section `[units]` :

```ini
[units]
length_unit = m
length_decimals = 2
section_length_unit = cm
section_length_decimals = 2
force_unit = kN
force_decimals = 2
moment_unit = kN.m
moment_decimals = 2
stress_unit = MPa
stress_decimals = 2
angle_unit = deg
angle_decimals = 2
area_unit = m2
area_decimals = 2
```

- **Écriture** : `MainWindow.save_config()` (`main_window.py:998`) ajoute
  `cfg["units"] = display_units.get_state_ini()` à côté de `general` / `styles` /
  `colors`.
- **Lecture** : `MainWindow._load_or_create_config()` (`main_window.py:1044`),
  après le bloc `png_export_scale` :
  `display_units.load_state_ini(cfg["units"] if cfg.has_section("units") else {})`.
  Fait dans la fenêtre `_suspend_config_save = True` déjà en place.
- Fichier absent / section absente → défauts, puis `save_config()` réécrit la
  section (chemin `_load_or_create_config` existant qui recrée le fichier).

Aucun autre module ne touche `config.ini`.

## Dialogue et menu

### Menu

`_build_menu()` (`main_window.py:1676`, menu Paramètres) : nouvelle `QAction`
`tr_ui("menu_units")` après « Export PNG », connectée à `self.open_units_dialog`.

### `UnitsDialog(QDialog)`

Nouvelle classe dans `main_window.py`, calquée sur `SettingsDialog`.

- `QGridLayout`, une ligne par grandeur (ordre : `length`, `section_length`,
  `force`, `moment`, `stress`, `angle`, `area`) :
  `[libellé]  [QComboBox unité]  [libellé "décimales"]  [QSpinBox 0–6]`.
- Combo alimentée par `display_units.units_for(kind)` ; sélection initiale =
  `state_for(kind)[0]`.
- Spin initial = `state_for(kind)[1]`.
- `QDialogButtonBox(Ok | Cancel)`.
- `get_values() -> {kind: (unit, decimals)}`.

### `open_units_dialog()`

```
dlg = UnitsDialog(self)
if dlg.exec() != QDialog.Accepted: return
for kind, (unit, dec) in dlg.get_values().items():
    display_units.set_unit(kind, unit)
    display_units.set_decimals(kind, dec)
self.save_config()
self._refresh_after_units_change()
```

### Traductions (`viewer_config.py`, `MSG_UI`)

`menu_units` = « Unités et précision… », `units_dialog_title` = « Unités et
précision », `units_label_decimals` = « décimales », et un libellé par grandeur :
`units_label_length` (« Longueurs (éléments) »), `units_label_section_length`
(« Longueurs (sections) »), `units_label_force` (« Efforts »),
`units_label_moment` (« Moments »), `units_label_stress` (« Contraintes »),
`units_label_angle` (« Angles »), `units_label_area` (« Aires »).

## Câblage

Import : `import display_units as du` dans `ad_model_data.py`,
`viewer_widget.py`, `main_window.py`.

### `ad_model_data.py` — helpers réécrits (signatures inchangées)

Helpers **avec site d'appel vivant** — réécrits, signature inchangée :

| helper | nouveau corps | grandeur |
|---|---|---|
| `_format_force_kn(v)` | `return du.fmt(v, "force")` | force |
| `_format_moment_knm(v)` | `return du.fmt(v, "moment")` | moment |
| `_format_length_m(v)` | `return du.fmt(v, "length")` | length |
| `_format_length_cm_fixed(v, decimals=2)` | `return du.fmt(v, "section_length")` (param `decimals` ignoré, gardé pour compat de signature) | section_length |
| `_format_thickness_smart(v)` | `return du.fmt(v, "section_length")` | section_length |
| `_format_eccentricity_cm(v)` | `return du.fmt(v, "section_length")` | section_length |
| `_format_angle_degrees(v)` | `return du.fmt(v, "angle")` (entrée rad) | angle |

`_format_numeric`, `_format_release_connection` : inchangés.

Helpers **morts** (aucun site d'appel dans le dépôt) : `_format_length_cm`
(ligne 778), `_format_area_m2` (ligne 620), `_format_fixed_unit` (ligne 634,
après remplacement de ses 3 appels ci-dessous). Les **supprimer** dans la même
tâche (nettoyage adjacent au périmètre).

Sites `_format_fixed_unit(...)` (3 occurrences) :

- ligne ~671 `_build_linear_length_takeoff` : `_format_fixed_unit(value, "m", 2)`
  → `du.fmt(value, "length")` ;
- lignes ~730 et ~745 (métré aire, `area_text`) :
  `_format_fixed_unit(area, "m²", 2)` → `du.fmt(area, "area")`.

Ligne ~720 `_build_planar_takeoff` : `_format_length_cm_fixed(thickness_value, 2)`
reste tel quel (le helper est réécrit). `sort_value` (tri) reste calculé en cm en
dur — c'est une clé de tri interne, pas de l'affichage, on n'y touche pas.

### `ad_model_data.py` — tableau de résultats d'appui (`_fmt_result_value`, lignes 1206-1232)

Chaque paire `("<key>", f"{_fmt_result_value(_dict_get_ci(payload,'<key>'), <factor>)} <unit>")`
devient `("<key>", du.fmt(_dict_get_ci(payload, '<key>'), "<kind>"))` avec :

- `dx`/`dy`/`dz`/`d` → `"section_length"`
- `rx`/`ry`/`rz`/`r` → `"angle"` (supprimer l'appel explicite `_radians_to_degrees`, la conversion passe dans le registre)
- `fx`/`fy`/`fz` → `"force"`
- `mx`/`my`/`mz` → `"moment"`
- `sx`/`sy`/`sz`/`s` → `"stress"`

`_fmt_result_value` devient inutilisé → supprimé (son garde-fou petite valeur est
repris dans `du.fmt`).

### `ad_model_data.py` — pipeline diagramme + xlsx

`_linear_result_scale_and_unit(family_key, value_key)` :

```
kind = _result_kind(family_key, value_key)   # nouvelle petite fonction
return du.scale(kind), du.unit(kind)
```

`_result_kind` : `deplacements` → `section_length` ; `efforts` avec
`value_key in ("mx","my","mz")` → `moment`, sinon `force` ; `contraintes` →
`stress`. Le cas par défaut (aucune famille reconnue) reste géré **hors `du`** :
`_linear_result_scale_and_unit` renvoie directement `(1.0, "")` comme
aujourd'hui, sans passer par le registre.

Conséquence : `_coerce_abscissa_value_series`, `_extract_linear_diagram_series`,
`read_linear_element_diagram_results`, `read_linear_element_family_export`
suivent sans autre modification (ils consomment déjà `scale` / `unit`).

`read_linear_element_diagram_results` : ajouter `"decimals": du.decimals(kind)`
au dict renvoyé (à côté de `"unit"`).

### `ad_model_data.py` — torseurs planaires / murs (1344-1400)

Déjà couverts : passent par `_format_force_kn` / `_format_moment_knm` /
`_format_length_m` réécrits. Aucun changement local.

### `viewer_widget.py`

- `_build_linear_diagram_actors(..., unit="")` → accepter aussi
  `decimals: int | None = None`. `_format_diagram_label_value` :
  `formatted = du.fmt_value_only(value, kind)` — mais le builder n'a pas `kind`,
  seulement `unit`/`decimals` ; on formate donc directement :
  `f"{value:.{decimals}f}"` avec `decimals` reçu (fallback 3 si `None`), en
  gardant la règle `±0` pour `abs(value) < 10**(-decimals)`. `unit_str` inchangé.
- `set_linear_result_diagram` / `add_linear_result_diagram` : propager `decimals`
  depuis le payload.
- Overlay coordonnées (`_overlay_mouse_world_txt`, ligne ~1895) :
  `f"X : {du.fmt(wx,'length')}   Y : {du.fmt(wy,'length')}   Z : {du.fmt(wz,'length')}"`
  — ou, pour éviter l'unité répétée 3×, formater les valeurs seules via
  `du.conv` + `du.decimals` et suffixer l'unité une fois. Choix retenu : unité
  une seule fois en fin de ligne.

### `main_window.py`

- Centroïde appui planaire (lignes ~3951-3953,
  `{"name": "X", "value": f"{...:.3f} m"}`) → `du.fmt(<val>, "length")`.
- Diagramme : là où le payload est passé au viewer, transmettre
  `payload["decimals"]`.
- xlsx (`export_analysis_results_csv`, ~3606-3626) :
  - `abscissa` : `ws.append([du.conv(row.get("abscissa", 0.0), "length"), …])` ;
  - en-têtes de composantes : `ws.append(["abscissa (" + du.unit("length") + ")",
    *[f"{c} ({du.unit(_result_kind_for_component(c))})" for c in components]])`.
    `_result_kind_for_component` : petite table locale
    `dx/dy/dz/d→section_length`, `fx/fy/fz→force`, `mx/my/mz→moment`,
    `sxx*/sv→stress`.

### Rafraîchissement — `_refresh_after_units_change()`

Constat de câblage : l'onglet **Propriétés** et l'onglet **Métré** sont formatés
**au chargement du modèle** (les `_format_*` tournent dans
`extract_model_geometry`, le résultat est mis en cache dans
`current_model_data["line_properties"]`, `["…_support_properties"]`,
`["takeoff_*"]`). Re-déclencher `on_viewer_selection_changed` ré-afficherait les
mêmes chaînes déjà formatées avec les anciennes unités. En revanche l'onglet
**Résultats** (tableau de réactions), les **diagrammes** et l'**overlay** sont
calculés à la volée (fetch API par sélection / par mouvement souris) et suivent
donc automatiquement le nouvel état de `display_units`.

Comportement v1 (livré en 1.96 initial) : `self.load_model()` — rechargement
complet. Correct mais lent sur les gros modèles.

**Révision (1.96) : rafraîchissement en mémoire, sans API ni VTK.** Les
extracteurs de propriétés et les `_build_*_takeoff` sont des fonctions pures de
`(objet_élément, maps par eid)`. `_build_geometry_payload` conserve désormais les
objets bruts nécessaires dans `current_model_data["_unit_refresh_cache"]` (6
listes d'éléments + 4 listes d'ids + 3 maps ; coût : maintien en RAM des dicts
éléments pour la session). `recompute_unit_dependent_fields(cache)` rejoue les 6
boucles de propriétés (mêmes filtres / `zip(ids, elements)` que
`_build_geometry_payload`, pour garder l'alignement d'index avec
`lines` / `planars` / `*_eids` non reconstruits) et les 5 métrés, avec l'état
`display_units` courant. `rebuild_properties_and_takeoff(model_data)` applique ça
en place et renvoie `False` si le cache est absent (modèle chargé par une version
antérieure).

```
def _refresh_after_units_change(self):
    md = self.current_model_data
    if not isinstance(md, dict):
        return
    if not rebuild_properties_and_takeoff(md):
        if self.fto_edit is not None and self.fto_edit.text().strip():
            self.load_model()          # repli
        return
    (self.current_sections, self.current_thicknesses, self.current_materials,
     self.current_section_counts, self.current_thickness_counts,
     self.current_material_counts) = self._extract_filter_choices(md)
    self.selected_sections = set(self.current_sections)
    self.selected_thicknesses = set(self.current_thicknesses)
    self.selected_materials = set(self.current_materials)
    self._render_results(md)                       # onglet Métré
    if self.viewer is not None:
        self.viewer.set_structural_filters(self.selected_sections,
                                           self.selected_thicknesses,
                                           self.selected_materials)
        sel = self.viewer.get_selected_items()
        if sel:
            self.on_viewer_selection_changed(sel)  # onglet Propriétés
```

Les choix de filtres (section / épaisseur / matériau) sont ré-extraits et la
sélection remise à « tout » — comme le faisait `on_model_loaded` — car les
libellés d'épaisseur changent avec l'unité. Si aucun modèle n'est chargé : rien.
Overlay : effet au prochain mouvement souris.

## Gestion d'erreurs

- `du.fmt` / `du.conv` : jamais d'exception ; entrée invalide → `"N/A"` /
  `None`, comme le code actuel.
- `load_state_ini` : tolérant, jamais d'exception, valeurs douteuses → défauts.
- `UnitsDialog` : bornes UI (combo fermée, spin 0–6) rendent l'état invalide
  impossible ; `set_unit` / `set_decimals` re-valident par sécurité.
- `du.fmt` / `du.scale` / `du.unit` appelés avec une clé de grandeur inconnue :
  lèvent `KeyError` (bug de câblage, pas une entrée utilisateur) — les clés sont
  toutes littérales dans le code appelant, donc acceptable. Le cas « pas de
  conversion » du pipeline diagramme est géré hors `du` (voir 4).

## Tests

Pas de harnais de test dans le repo. Ajout d'un auto-test minimal dans
`display_units.py` (`if __name__ == "__main__":` avec `assert`) couvrant :

- défauts = comportement historique : `fmt(1234.0, "force")` == `"1.23 kN"`,
  `fmt(0.05, "section_length")` == `"5.00 cm"`, `fmt(1_000_000.0, "stress")`
  == `"1.00 MPa"`, `fmt(math.pi, "angle")` == `"180.00 °"`,
  `fmt(2.0, "length")` == `"2.00 m"` ;
- changement d'unité : après `set_unit("force", "N")`,
  `fmt(1234.0, "force")` == `"1234.00 N"` ; après `set_unit("length", "mm")`,
  `fmt(2.0, "length")` == `"2000.00 mm"` ;
- décimales : après `set_decimals("force", 0)`,
  `fmt(1234.0, "force")` == `"1 kN"` ;
- petite valeur → scientifique ;
- `load_state_ini` : clé absente → défaut ; unité invalide → défaut ;
  `decimals = "abc"` → défaut ; round-trip `get_state_ini` → `load_state_ini`
  stable ;
- `None` → `"N/A"`.

Vérification manuelle dans l'app : ouvrir un modèle calculé, changer chaque
grandeur dans le dialogue, contrôler Propriétés, Résultats, diagramme 3D,
overlay, puis export `.xlsx` ; rouvrir l'app et vérifier la persistance.

## Changements de comportement assumés (défauts ≈ historique, sauf) :

- `_format_thickness_smart` : bascule automatique cm (≥ 1 cm) / mm (< 1 cm)
  supprimée → `section_length` fixe (défaut cm, 2 décimales).
- Angle d'orientation de section et aires : `.6g` (6 chiffres significatifs) →
  décimales fixes (défaut 2).
- `_fmt_result_value` : seuil de bascule en notation scientifique passe de
  `abs < 0.01` à `abs < 10**(-decimals)`.
- Overlay coordonnées : unité `m` affichée une fois en fin de ligne au lieu
  d'être implicite.

## Fichiers touchés

- `display_units.py` — nouveau.
- `ad_model_data.py` — helpers de formatage, tableau de résultats,
  `_linear_result_scale_and_unit` + `_result_kind`, payload diagramme.
- `viewer_widget.py` — labels de diagramme (+ `decimals`), overlay coordonnées.
- `main_window.py` — `UnitsDialog`, `open_units_dialog`,
  `_refresh_after_units_change`, entrée de menu, `save_config` /
  `_load_or_create_config`, centroïde, xlsx.
- `viewer_config.py` — clés `MSG_UI` (menu + libellés dialogue).
- `CHANGELOG.md` — entrée de version.
