# Changelog ADViewer

**⚠ Pour l'affichage correct des combinaisons (ID et nom complet), la version 2027.1 beta est nécessaire**

## 2.05

### FR
- Nouvelle entrée « Fermer » dans le menu Fichier (après « Ouvrir ») : ferme le projet en cours côté API s'il est encore ouvert, décharge le fichier affiché dans le viewer et réinitialise l'interface (compteurs, filtres, résultats) à son état initial.
- Le logiciel est désormais disponible en anglais : nouveau sous-menu « Language » dans Paramètres (Français / English). Le changement de langue s'applique au redémarrage de l'application.

### EN
- New "Close" entry in the File menu (after "Open"): closes the current project on the API side if still open, unloads the currently displayed file in the viewer, and resets the interface (counts, filters, results) to its initial state.
- The software is now available in English: new "Language" submenu in Settings (Français / English). The language change takes effect on the next application restart.

## 2.04

### FR
- Export PNG (bouton caméra) : la boîte de dialogue permet désormais de choisir entre le multiplicateur existant (1 à 3) et des résolutions standard fixes (HD 1280×720, FHD 1920×1080, QHD 2560×1440, 4K UHD 3840×2160). Le choix (mode et valeur) est sauvegardé dans le fichier de configuration.
- Nouvelles icônes pour « Sélection par fenêtre » et « Zoom étendu ».
- Modes « Profilés + Faces cachées » et « Profilés + Rendu plein » : une barre de progression s'affiche désormais pendant la construction des solides (progression élément par élément, plus de gel de l'interface) ; le temps de construction a aussi été réduit pour les sections sans trou et les profils simples.
- Affichage des charges (ponctuelles/linéaires/surfaciques) : la barre de progression avance désormais élément par élément, comme pour les modes Profilés (au lieu de paliers fixes par étape).
- Affichage des charges : cocher/décocher un type de charge, changer son échelle ou son cas de charge ne reconstruit plus que ce qui a réellement changé, au lieu de systématiquement reconstruire tous les types actuellement affichés.
- Correction : après un changement de modèle, le type de charge « surfaciques » pouvait rester marqué comme affiché en interne (bien que la case soit décochée à l'écran), provoquant sa reconstruction inutile dès qu'un autre type de charge était affiché.

### EN
- PNG export (camera button): the dialog now lets you choose between the existing multiplier (1 to 3) and fixed standard resolutions (HD 1280×720, FHD 1920×1080, QHD 2560×1440, 4K UHD 3840×2160). The choice (mode and value) is now saved in the configuration file.
- New icons for "Window selection" and "Zoom to fit".
- "Profiles + Hidden faces" and "Profiles + Full render" modes: a progress bar is now shown while building the solids (progress per processed element, no more UI freeze); build time was also reduced for hole-free sections and simple profiles.
- Load display (point/linear/planar): the progress bar now advances element by element, like the Profiles modes (instead of fixed per-stage steps).
- Load display: toggling a load type, changing its scale, or changing its load case no longer rebuilds every currently displayed load type, only what actually changed.
- Fix: after switching models, the "planar" load type could stay internally marked as shown (even though its checkbox was unchecked), causing it to be needlessly rebuilt as soon as another load type was displayed.

## 2.03

### FR
- Le bouton « Démarrer/Arrêter API » est remplacé par trois icônes : On, Off et Redémarrer (infobulles dédiées). L'icône On ou Off est atténuée selon l'état de l'API ; Redémarrer n'est actif que si l'API tourne.
- Le bouton « Charger le modèle » devient une icône, placée sur la même ligne que le champ chemin et le bouton Parcourir. Il est désactivé tant que l'API n'est pas démarrée ou que le chemin est vide.
- Carte « Projet » réorganisée : ligne 1 = contrôles API, ligne 2 = chemin + Parcourir + Charger.

### EN
- The "Start/Stop API" button is replaced by three icons: On, Off and Restart (with dedicated tooltips). The On or Off icon is dimmed depending on the API state; Restart is enabled only while the API is running.
- The "Load model" button becomes an icon, on the same row as the path field and the Browse button. It is disabled while the API is not running or the path is empty.
- "Project" card reorganised: row 1 = API controls, row 2 = path + Browse + Load.

## 2.02

### FR
- Nouvelle fonction « Sélection par fenêtre » : icône dédiée et raccourci via Alt+S.
- Fenêtre tracée de gauche à droite : seules les entités entièrement comprises dans le rectangle sont sélectionnées. Tracée de droite à gauche : entités comprises et entités intersectées par le rectangle. Ctrl ajoute à la sélection courante. Clic droit ou Échap annule.
- Le journal affiche un récapitulatif après une sélection par fenêtre et après « Isoler » (nombre d'éléments par type : filaires, surfaciques, parois, appuis, charges).
- Nouvelle fonction « Zoom fenêtre » : icône dédiée (à côté de « Zoom étendu ») et raccourci Alt+W. Deux clics définissent un rectangle (comme la sélection par fenêtre) sur lequel la caméra se recadre. Clic droit ou Échap annule.
- Pendant le chargement d'un modèle, toutes les icônes de la section « Actions » sont maintenant grisées et désactivées ; les modes actifs (sélection par fenêtre, zoom fenêtre, isolation) sont annulés au démarrage du chargement.

### EN
- New "Window selection" tool: dedicated icon and Alt+S shortcut.
- Window drawn left to right: only entities fully enclosed in the rectangle are selected. Drawn right to left: enclosed entities plus entities crossed by the rectangle. Ctrl adds to the current selection. Right-click or Esc cancels.
- The log shows a summary after a window selection and after "Isolate" (element count per type: linear, planar, walls, supports, loads).
- New "Window zoom" tool: dedicated icon (next to "Zoom to fit") and Alt+W shortcut. Two clicks define a rectangle (like the window selection) the camera zooms to. Right-click or Esc cancels.
- While a model is loading, all icons in the "Actions" section are now greyed out and disabled; active modes (window selection, window zoom, isolation) are cancelled when loading starts.

## 2.01

### FR
- Poutres à section variable : l'onglet Propriétés affiche désormais deux lignes « Section début » et « Section fin » au lieu d'une seule.
- Nouveau curseur « Transparence profilés » (défaut 65 %), actif uniquement en mode « Profilés + Faces cachées » ; le curseur de transparence des surfaces n'agit plus sur les solides des filaires.
- Chargement d'un modèle : le retour au mode d'affichage par défaut (« Filaire + Faces cachées ») se fait maintenant avant le rendu du nouveau modèle, ce qui évite un premier rendu intermédiaire en mode Profilés (lent sur les gros modèles).
- Correction : `sectionOrientationAngle` (renvoyé en radians par l'API) était converti une seconde fois lors de la construction du repère local — le repère des diagrammes de résultats n'était quasiment pas tourné pour les barres à section orientée. Les diagrammes s'orientent maintenant dans le bon plan.
- Correction : après une multi-sélection de filaires et l'affichage d'un diagramme, une sélection unique ultérieure rechargeait les résultats de l'ancienne multi-sélection ; il est de nouveau possible d'obtenir les résultats d'un seul élément.

### EN
- Variable-section beams: the Properties tab now shows two rows, "Start section" and "End section", instead of a single one.
- New "Profiles transparency" slider (default 65%), active only in "Profiles + Hidden faces" mode; the surfaces transparency slider no longer affects the linear-element solids.
- Model load: the reset to the default render mode ("Wireframe + Hidden faces") now happens before the new model is rendered, avoiding an intermediate render in Profiles mode (slow on large models).
- Fix: `sectionOrientationAngle` (returned in radians by the API) was converted a second time when building the local frame — the results-diagram frame was barely rotated for beams with an oriented section. Diagrams now orient in the correct plane.
- Fix: after a multi-selection of linear elements and showing a diagram, a later single selection reloaded the results of the previous multi-selection; single-element results are available again.

## 2.00

### FR
- Vue graphique : deux nouveaux modes de visualisation, « Profilés + Faces cachées » et « Profilés + Rendu plein ». Les éléments filaires y sont dessinés avec leur section 3D réelle (solide extrudé) au lieu d'un simple trait.
- Sections gérées : I/H, U, L/cornière, T, T dissymétrique, rectangulaire et circulaire (pleines et tubes creux), Z, Oméga, Sigma ; profilés composés CS1 à CS7 ; poutres à section variable (interpolation section début → section fin) ; jarrets (goussets) début et/ou fin, en haut, en bas ou haut et bas.
- L'angle d'orientation de la section et l'excentrement sont pris en compte ; la géométrie affichée est identique à celle de l'export IFC.
- « Profilés + Rendu plein » : solide ombré avec arêtes visibles. « Profilés + Faces cachées » : solide lissé.
- La sélection colore directement le(s) solide(s) de l'élément sélectionné dans la couleur de sélection (échange de scalaires, sans reconstruction).
- Au chargement d'un modèle, le mode de visualisation revient au défaut « Filaire + Faces cachées ».
- Interne : toute la géométrie de section pure est extraite du module d'export IFC vers un module partagé (`section_geometry.py`), sans changement de comportement de l'export IFC.

### EN
- Graphic view: two new render modes, "Profiles + Hidden faces" and "Profiles + Full render". Linear elements are drawn with their real 3D cross-section (extruded solid) instead of a plain line.
- Supported sections: I/H, U, L/angle, T, unequal T, rectangular and circular (solid and hollow tubes), Z, Omega, Sigma; combined sections CS1 to CS7; variable-section beams (loft from start to end section); haunches at start and/or end, top, bottom or top-and-bottom.
- Section orientation angle and eccentricity are honoured; the displayed geometry matches the IFC export.
- "Profiles + Full render": shaded solid with visible edges. "Profiles + Hidden faces": smooth solid.
- Selection recolors the selected element's solid(s) directly in the selection color (scalar swap, no rebuild).
- On model load the render mode returns to the default "Wireframe + Hidden faces".
- Internal: all pure section geometry is moved from the IFC export module into a shared module (`section_geometry.py`), with no change to the IFC export behavior.

## 1.96

### FR
- Nouveau menu Paramètres > Unités et précision : choix de l'unité et du nombre de décimales par grandeur (longueurs éléments, longueurs sections, efforts, moments, contraintes, angles, aires). Réglages sauvés dans config.ini et appliqués aux onglets Propriétés et Résultats, aux diagrammes 3D, à l'overlay de coordonnées et à l'export .xlsx. À la validation, les onglets Propriétés et Mètre sont rafraîchis en mémoire, sans rechargement du modèle.
- L'affichage automatique cm/mm des épaisseurs est remplacé par l'unité fixe choisie (défaut cm). Angles et aires passent d'un affichage à 6 chiffres significatifs à un nombre de décimales fixe (défaut 2).
- Les très petites valeurs d'efforts/moments/longueurs s'affichent désormais en notation scientifique au lieu d'un arrondi à 0.

### EN
- New Settings > Units and precision menu: pick the unit and the number of decimals per quantity (element lengths, section lengths, forces, moments, stresses, angles, areas). Saved to config.ini and applied to the Properties and Results tabs, 3D diagrams, the coordinate overlay and the .xlsx export. On confirmation the Properties and Metre tabs refresh in memory, without reloading the model.
- The automatic cm/mm display of thicknesses is replaced by the fixed chosen unit (default cm). Angles and areas move from 6 significant figures to a fixed number of decimals (default 2).
- Very small force/moment/length values are now shown in scientific notation instead of being rounded to 0.

## 1.95

### FR
- Sélection : en modes Faces cachées et Filaire + faces cachées, le cycle de sélection (clic droit répété) atteint désormais les éléments situés derrière une face surfacique (ex. poteau derrière un voile). Modes Filaire et Rendu plein inchangés.

### EN
- Selection: in Hidden faces and Wireframe + hidden faces modes, the selection cycle (repeated right-click) now reaches elements located behind a surface face (e.g. a column behind a wall). Wireframe and Full render modes unchanged.

## 1.94

### FR
- Calcul éléments finis : nouvelle icône dans l'onglet Résultats qui lance le calcul via l'API (POST LaunchAnalysis). L'appel est bloquant ; un compteur de temps écoulé s'affiche dans la zone des barres de progression pendant l'attente.
- Le projet est ouvert automatiquement si nécessaire, ou la session déjà ouverte est réutilisée.
- Après un calcul réussi, le modèle est rechargé automatiquement : les résultats deviennent consultables (onglet Résultats actif, cas de charge peuplés) et le projet reste ouvert.
- Rechargement post-calcul : la détection des résultats est retentée pendant quelques secondes (le magasin de résultats d'Advance Design pouvant n'être interrogeable qu'avec un léger différé après LaunchAnalysis), ce qui évitait parfois un "Aucun résultat disponible" erroné.
- Paramètres > Calcul EF : délai maximum configurable (défaut 2 h, 0 = illimité). En cas de dépassement, le message indique d'augmenter le délai.
- Journal : message "Calcul élément fini en cours. Cette étape peut durer plusieurs minutes." au démarrage ; le cas où l'API répond HTTP 200 mais signale un échec (modèle non maillable, licence, etc.) est distingué du succès.
- Correction : la vue graphique ne démarrait plus avec certaines versions de VTK (AddActor2D absent du binding Python) ; remplacé par AddViewProp.

### EN
- Finite element analysis: new icon in the Results tab that launches the analysis through the API (POST LaunchAnalysis). The call is blocking; an elapsed-time counter is shown in the progress bar area while waiting.
- The project is opened automatically when needed, or the already-open session is reused.
- After a successful analysis the model is reloaded automatically: results become available (Results tab enabled, load cases populated) and the project stays open.
- Post-analysis reload: results detection is retried for a few seconds (Advance Design's result store may only become queryable with a slight delay after LaunchAnalysis), which sometimes caused a wrong "No results available".
- Settings > Calcul EF: configurable maximum timeout (default 2 h, 0 = unlimited). On timeout the message advises to raise the limit.
- Journal: "Finite element analysis running. This step may take several minutes." message at start; the case where the API returns HTTP 200 but reports a failure (non-meshable model, license, etc.) is distinguished from success.
- Fix: the graphic view failed to start with some VTK versions (AddActor2D missing from the Python binding); replaced with AddViewProp.

## 1.93

### FR
- Export résultats .xlsx : en sélection multiple de filaires, le classeur contient désormais un onglet par élément (auparavant seul le dernier élément était exporté).
- Export résultats .xlsx : ajout en tête de chaque onglet du numéro et du nom du cas de charge actif lors de l'export.
- Export IFC : sans sélection, le modèle complet est exporté ; avec une sélection d'éléments, seuls les éléments sélectionnés sont exportés.

### EN
- Results .xlsx export: with a multi-selection of linear elements, the workbook now contains one sheet per element (previously only the last element was exported).
- Results .xlsx export: each sheet now starts with the number and name of the load case active at export time.
- IFC export: with no selection the full model is exported; with an element selection only the selected elements are exported.

## 1.92

### FR
- Vue graphique : affichage dans le coin haut-gauche de la vue courante (Vue de face, de derrière, de gauche, de droite, de dessus, de dessous, isométrique, ou « Vue utilisateur ») et, en dessous, des coordonnées X, Y, Z de la position de la souris (deux décimales). Rien n'est affiché si aucun modèle n'est chargé.
- Boutons de vue : le premier clic affiche désormais la vue « de départ » (Vue de face, Vue de gauche, Vue de dessus) avant de basculer sur l'opposée.
- Nouvelle icône pour le bouton « Isoler ».
- Isolation : reclic sur « Isoler » avec une sélection différente → isole la nouvelle sélection ; avec une sélection identique ou vide → annule l'isolation.
- Correction : après isolation, les parois et les appuis redeviennent sélectionnables (mauvais index de picking sur les sous-ensembles isolés).

### EN
- Graphic view: top-left overlay showing the current view (Front, Back, Left, Right, Top, Bottom, Isometric, or "User view") and, below it, the X, Y, Z coordinates of the mouse position (two decimals). Nothing is shown when no model is loaded.
- View buttons: the first click now shows the "start" view (Front, Left, Top) before toggling to the opposite one.
- New icon for the "Isolate" button.
- Isolation: clicking "Isolate" again with a different selection now isolates the new selection; with an identical or empty selection it cancels isolation.
- Fix: after isolation, load areas and supports are selectable again (wrong picking index on isolated subsets).

## 1.91

### FR
- Bouton appareil photo : enregistre la vue graphique VTK en PNG (nommé d'après le fichier ouvert, indicé `_1`, `_2`, ... sans écrasement)
- Paramètres > Export PNG : échelle du rendu réglable (entier de 1 à 3, défaut 1)
- Correction : la vue graphique VTK suit désormais le thème sombre

### EN
- Camera button: saves the VTK graphic view as PNG (named after the opened file, suffixed `_1`, `_2`, ... without overwriting)
- Settings > PNG Export: adjustable render scale (integer from 1 to 3, default 1)
- Fix: the VTK graphic view now follows the dark theme

## 1.90

- Nouveaux icônes dans l'onglet résultats
- New icons in the result tab

## 1.89.3

- Correction de bugs & optimisation
- Bug fixes and optimisation

## 1.89

### Affichage des charges surfaciques & divers
- Choix des cas de charges et de l'échelle,
- Affichage graphique des efforts,
- Affichage des valeurs des charges dans l'onglet propriétés
- Ajouts d'icônes pour les fonctions `Parcourir` et `Effacer`
- Déplacement des barres de pourcentage en bas de la fenêtre

### Display of Planar Loads & misc.
- Select load cases and scale,
- Graphical display of forces,
- Display of load values in the properties tab
- Added icons for the `Browse` and `Delete` functions
- Moved the percentage bars to the bottom of the window

## 1.88

### URL API déplacée
URL Déplacée vers le menu Paramètres > Configuration

### API URL moved
URL moved to the Parameters > Configuration

## 1.87

### Mise à jour des icônes
Icônes plus simples et plus lisibles

### Icons update
More simple and more readable icons

## 1.86

### Affichage des charges linéaires
- Choix des cas de charges et de l'échelle,
- Affichage graphique des efforts et moments,
- Affichage des valeurs des charges dans l'onglet propriétés

### Display of Linear Loads
- Select load cases and scale,
- Graphical display of forces and moments,
- Display of load values in the properties tab

## 1.85

### Affichage des charges ponctuelles
- Choix des cas de charges et de l'échelle dans un onglet dédié,
- Affichage graphique des efforts et moments,
- Affichage des valeurs des charges dans l'onglet propriétés

### Display of Point Loads
- Select load cases and scale in a dedicated tab,
- Graphical display of forces and moments,
- Display of load values in the properties tab

## 1.84

### Sélection multiple
- Ajout d'une fonction de sélection multiple avec ctrl+clic gauche,
- Isolation sur sélection multiple,
- Visualisation des diagrammes sur une sélection multiple d'élement filaires.

### Multiple selection
- New multiple selection added via ctrl+left clic,
- Isolate function now supports multiple elements,
- Result visualisation for linear elements on a multime selection.

## 1.83

### Surfaciques
- Propriétés étendues : nombre de sommets, excentricité (et prise en compte de cette dernière dans les calculs), propriétés du maillage de l'élément,

### Planar elements
- New properties : number of vertex, excentricity (and considering it in FEM), mesh properties of the selected element.

## 1.82

### Amélioration de l'affichage des résultats sur les élément filaire
- Les diagrammes sont maintenant colorés,
- Correction de la position de l'affichage des valeurs min.

### Better result display for linear elements
- Diagramms are now colored,
- Bad min value display position fixed.

## 1.81

### Modification de la fonction Filtrer et ajout Parois
- Affichage du nombre d'éléments concernés par la sélection dans la boite de dialogue des filtres,
- Ajout de l'affichage des propriétés des parois.

### Changes to the Filter Function and Properties of loadareas
- Display of the number of elements affected by the selection in the filter dialog box,
- Addition of the display of loadarea properties.

## 1.80

### Affichage du maillage
- Publication du code,
- Ajout de l'affichage des mailles sur les éléments surfaciques si le modèle est déjà calculé.

### Diplay meshes on planar elements
- Code released,
- Added mesh display on planar elements if the model has already been calculated.

## v1.75

### Export IFC
- Ajout d'un menu pour Exporter le modèle en IFC.
- Inclu :
  - Éléments surfaciques (constants uniquement, les pentes ne sont pas prises en charge),
  - Appuis ponctuels/linéaires et surfaciques (Représentation uniquement),
  - Éléments filaires : Jarrets, sections constantes, variables, prise en charge des excentrements (standards, pas définis manuellement), sections composées, profilés minces (pour l'instant Z, Omega, Sigma)
- Manquant ou non pris en charge : Autres sections de profilés minces (C, L, Zeta, etc), certain catalogues de profilés métalliques peuvent avoir des dimensions incorrectes (utiliser de préférence le catalogue European profiles).

Si une section n'est pas prise en charge, elle sera affichée en tant que section rectangulaire.

### IFC Export
- Added a menu option to export the model to IFC.
- Includes:
  - Planar elements (constant cross-sections only; slopes are not supported),
  - Point/linear and planar supports (representation only),
  - Linear elements: Haunch, constant and variable cross-sections, support of eccentricities (standard, not manually defined), combined cross-sections, CF profiles (currently Z, Omega, Sigma)
- Missing or not supported: Other CF sections (C, L, Zeta, etc.); certain profile libraries may have incorrect dimensions (preferably use the European Profiles library).

If a section is not supported, it will be displayed as a rectangular section.

## v1.72

### Nouvelles fonctions
- Export des résultats **déplacements/efforts/contraintes** sur les éléments filaires au format **xlsx**
- Ajout d'une fonction afin d'afficher la vue 3D en perspective (fonctionnement d'origine, déforme légèrement la structure) ou 3D orthogonal (longueurs vraies)

## v1.72 (English version)

### New Features
- Export **displacements/forces/stresses** results for linear elements in **xlsx** format
- Added a feature to display the 3D view in perspective (default behavior, slightly distorts the structure) or orthogonal 3D (true lengths)

## v1.70g

### Hotfix
- Amélioration de la traduction

## v1.70

### Version anglaise / English version available
- Amélioration des dictionnaires (UI/Log/Error)
- Ajout d'une version anglaise

## v1.69

### Affichage des résultats sur les filaires
- Affichage des diagrammes de résultats (déplacements, efforts, contraintes),
- Affichage des valeurs min et max
- Ajout d'une fonction d'isolation des éléments

## v1.67

### Affichage des résultats sur les voiles
- Affichage des torseurs haut et bas
- Affichage des torseurs gauche et droite
- Affichage des dimensions du voile

## v1.66

### Affichage des résultats sur les appuis surfaciques
- Ajout de l'affichage des **torseurs** sur les appuis surfaciques
- Ajout de l'affichage de la position du centre de gravité de l'appui (graphique et texte)
- Correction d'un bug d'affichage en vue de dessus/dessous

## v1.65

### Affichage des résultats sur les appuis linéaires
- Ajout de l'affichage des **torseurs** sur les appuis linéaires.

## v1.64

### Optimisation graphique
- Ajout des de l'affichage **couleur par section**
- Ajout de raccourcis clavier pour les vues prédéfinies

## v1.63

### Optimisation #7
- Optimisation des fonctions de chargement.

## v1.62

### Optimisation #6
- UI : Découpage en blocs

## v1.61

### Optimisation #5
- Découpage extract_model_geometry(...) en une vraie pipeline lisible, avec des sous-fonctions dédiées pour les identifiants, les objets, la résolution des références, les cas/combinaisons, puis la construction de la géométrie finale.

## v1.60

### Optimisation #4
- Ajout de ResultsCaseEntry et ModelDataDict.
- Normalisation centralisée des listes, dictionnaires, booléens, compteurs et chemin du modèle via build_model_data(...).
- Construction plus homogène des entrées de cas/combinaisons via normalize_results_case_entry(...).

## v1.59

### Optimisation #3
- Ajout de ProjectSessionManager et de create_project_session(...).
- LoadModelWorker possède désormais sa propre session et la transmet à extract_model_geometry(...).
- LoadAnalysisResultsWorker ne reçoit plus seulement host, mais la session projet active, avec validation via can_read_results().
- MainWindow utilise self.project_session au lieu de manipuler directement current_open_project_path et current_open_project_has_results.

## v1.58

### Optimisation #2
- Ajout de AdvanceDesignApiClient.
- Centralisation de la logique HTTP dans ._post(...) avec gestion commune des erreurs.
- Conservation d’une compatibilité avec le code existant grâce à get_api_client(host) et aux wrappers historiques.

## v1.57

### Optimisation #1
- Suppression des installations automatiques de requests, PySide6, vtk et qt_material au runtime.
- Remplacement par des erreurs explicites si une dépendance manque, ce qui est plus propre pour un usage réel et pour PyInstaller.
- Ajustement de quelques except Exception vers des exceptions plus ciblées, notamment sur l’AppUserModelID Windows et l’arrêt du process serveur.

## v1.56

### Ajout d'un onglet Résultat
- Chargement des cas de charges et combinaisons,
- Vérification de la présence de résultats (et affichage de cette présence ou non dans le journal),
- Affichage des efforts et déplacement pour les appuis ponctuels.

## v1.53

### Passage vers qt-material
- Reconstruction de l'UI en qt-material pour un meilleur rendu.
- Correction de la boite de dialogue "Styles et épaisseurs"

## v1.52

### Filtre par épaisseur (éléments surfaciques)
- Ajout d'un troisième onglet **"Par épaisseur"** dans la boîte de dialogue de filtre, dédié aux éléments planaires.
- Correction visuelle : le trait barré de l'icône "Annuler filtre" est rendu avec un stylet de largeur 2 pour une meilleure lisibilité.

## v1.51

### Bouton "Annuler filtre"
- Ajout d'un bouton **Annuler filtre** (icône filtre barré) à côté du bouton Filtre existant.
- Un clic remet toutes les sections et tous les matériaux à l'état "tout sélectionné" et rafraîchit la vue.

### Mémorisation de l'onglet actif du dialogue de filtre
- Le dialogue `FilterDialog` rouvre sur le dernier onglet consulté (sections ou matériaux).

## v1.50

### Filtre structurel (sections / matériaux)
- Nouvelle boîte de dialogue **Filtre** avec deux onglets :
  - **Par section** — liste à cases à cocher affichée en grille 3 colonnes (éléments linéaires).
  - **Par matériaux** — liste à cases à cocher en colonne (éléments linéaires et planaires).
  - Boutons **Sélectionner tout / Désélectionner tout** sur chaque onglet.
- Nouveau bouton **Filtre** (icône entonnoir) dans la carte d'actions du panneau latéral.

## v1.49
### Modification de l'onglet métré
- Ajout d'un **ascenseur** quand la liste des sections ou des épaisseurs dépasse la taille de la fenêtre,
- Système de **repli/dépli** pour chaque bloc de métré

## v1.48
### Modification du menu Fichier
Ajout d'une entrée **"À propos"**
- Lien vers ce dépôt,
- Lien vers le dépôt de l'API,
- Lien vers le site de l'éditeur du logiciel Advance Design

---

## v1.47
### Métré par matériau
- Métré linéaire regroupé par matériau.
- Métré surfacique regroupé par matériau.
- Nouveaux tableaux de synthèse par matériau.

---

## v1.46
### Ergonomie
- Ajustements de l'interface.
- Optimisation de la navigation utilisateur.

---

## v1.45
### Refonte graphique
- Modernisation de l'interface.
- Amélioration de la lisibilité.
- Rationalisation des tableaux de métré.

---

## v1.44
### Métré avancé
- Métré des charges surfaciques.
- Gestion des densités matériaux.
- Amélioration du formatage des unités.
- Résolution d'objets via leurs identifiants API.

---

## v1.43
### Métré
- Introduction de l'onglet de métré.
- Calcul des longueurs cumulées.
- Calcul des surfaces cumulées.
- Calcul géométrique 3D des surfaces.
- Affichage des résultats dans des tableaux dédiés.

---

## v1.42
### Éléments surfaciques
- Affichage détaillé des propriétés des panneaux.
- Identification du type de panneau/paroi.
- Amélioration du formatage des dimensions.

---

## v1.41
### Interface
- Réorganisation interne des panneaux de propriétés.
- Optimisation de la mise en page.

---

## v1.40
### Relâchements
- Analyse détaillée des conditions de liaison aux extrémités.

---

## v1.39
### Angles
- Conversion automatique radians → degrés.
- Affichage plus lisible des orientations.

---

## v1.38
### Connexions et relâchements
- Identification des types d'éléments.
- Affichage des relâchements.
- Affichage des connexions.
- Conversion et normalisation des valeurs API.

---

## v1.37
### Éléments filaires
- Extraction des propriétés des barres.
- Récupération des matériaux.
- Récupération des sections.
- Affichage détaillé des informations techniques.

---

## v1.36
### Propriétés des appuis surfaciques
- Tableau détaillé des caractéristiques des appuis surfaciques.

---

## v1.35
### Propriétés des appuis linéaires
- Tableau détaillé des caractéristiques des appuis linéaires.

---

## v1.34
### Propriétés des appuis ponctuels
- Affichage détaillé des propriétés :
  - Nom
  - Type
  - Conditions de blocage
  - Paramètres techniques

---

## v1.33
### Sélection avancée
- Gestion des objets sélectionnables.
- Gestion des objets retirés/ajoutés dynamiquement.
- Amélioration du surlignage de sélection.

---

## v1.32
### Moteur graphique
- Refonte de la génération des acteurs VTK.
- Optimisation du rendu :
  - Lignes
  - Faces
  - Boucles
  - Appuis

---

## v1.31
### Sélection d'objets
- Introduction du système de sélection 3D.
- Sélection par clic.
- Mise en évidence des objets sélectionnés.
- Personnalisation du style de sélection.
- Sauvegarde de la configuration utilisateur.

---

## v1.29
### Ergonomie
- Ajustements du panneau auto-masquant.

---

## v1.28
### Interface
- Ajout d'un panneau auto-masquant.
- Gestion du verrouillage (pin) du panneau.
- Apparition/disparition automatique au survol.

---

## v1.27
### Journalisation
- Ajout du panneau de logs repliable.

---

## v1.26
### Thèmes
- Introduction d'un système de thèmes.
- Changement dynamique du thème.
- Amélioration du rendu des ouvertures dans les surfaces.

---

## v1.24
### Maintenance
- Corrections diverses.

---

## v1.23
### Serveur API
- Ajout d'une fenêtre de configuration du serveur API.
- Démarrage du serveur depuis l'application.
- Arrêt du serveur depuis l'application.
- Sélection du chemin de l'exécutable API.

---

## v1.21
### Ergonomie
- Barre de progression de chargement.
- Indication de l'avancement lors de l'ouverture du modèle.
- Icônes dédiées aux vues.
- Amélioration de la gestion de la transparence.

---

## v1.19
### Vues prédéfinies
- Vue avant.
- Vue arrière.
- Vue gauche.
- Vue droite.
- Vue dessus.
- Vue dessous.
- Compteurs dynamiques d'éléments affichés.

---

## v1.18
### Navigation
- Ajout du double-clic molette pour recentrage/navigation rapide.

---

## v1.17
### Stabilisation
- Corrections diverses.

---

## v1.16
### Personnalisation
- Personnalisation des couleurs :
  - Barres
  - Surfaces
  - Appuis
  - Charges
- Sélecteurs de couleurs intégrés.

---

## v1.15
### Rendu graphique
- Contrôle de la transparence des surfaces.
- Curseur de réglage de l'opacité.

---

## v1.14
### Journalisation
- Ajout d'un système de logs.
- Messages utilisateur structurés.
- Affichage/masquage des charges surfaciques.

---

## v1.13
### Charges
- Affichage des charges surfaciques.
- Outils de diagnostic API.
- Détection des projets déjà ouverts.
- Gestion améliorée des erreurs de connexion.

---

## v1.12
### Géométrie avancée
- Détection automatique des parois.
- Extraction des géométries planes.
- Contrôle individuel de l'affichage :
  - Parois
  - Appuis ponctuels
  - Appuis linéaires
  - Appuis surfaciques

---

## v1.11
### Appuis
- Affichage des appuis ponctuels.
- Affichage des appuis linéaires.
- Affichage des appuis surfaciques.
- Amélioration de l'identification des éléments du modèle.

---

## v1.10
### Paramétrage
- Ajout d'une fenêtre de configuration.
- Réglage des largeurs de lignes d'affichage.

---

## v1.09
### Interface
- Ajout d'un menu élargi facilitant l'accès aux commandes.

---

## v1.08
### Maintenance
- Corrections diverses.

---

## v1.07
### Visualisation
- Introduction de plusieurs modes d'affichage.
- Gestion centralisée de la visibilité des objets.
- Génération des faces pour les éléments surfaciques.

---

## v1.05
### Affichage
- Ajout d'un système d'affichage/masquage des marqueurs.

---

## v1.03
### Navigation 3D
- Nouveau mode de navigation orbitale contrainte.
- Amélioration du zoom.
- Amélioration du panoramique.
- Amélioration de la rotation de la caméra.
- Gestion plus fluide des événements souris.

---

## v1.02
### Maintenance
- Corrections et stabilisation générale.

---

## v1.01
### Première version
- Visualisation de modèles Advance Design.
- Affichage des éléments filaires et surfaciques.
- Navigation 3D de base.
