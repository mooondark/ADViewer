# Advance Design 3D Viewer

🇫🇷 [🇬🇧](README_EN.md)

Visualiseur 3D pour les modèles Advance Design.

<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/4dbed5cd-0409-4682-af07-7274bd203eae" />

## Fonctionnalités

- Visualisation 3D : 7 modes d'affichage (filaire, faces cachées, plein, profilés avec faces cachées ou rendu plein, Filaire 3D), projection perspective ou orthogonale
- Sélection d'objets (clic, sélection par fenêtre, inversion de la sélection)
- Contrôle modèle : détection des anomalies avant calcul (connexions manquantes, doublons, chevauchements, éléments quasi colinéaires ou trop courts, surfaces dégénérées, appuis manquants ou superposés), rapport filtrable et exportable (CSV, Markdown), symboles 3D semi-transparents par gravité, seuils réglables
- Boîte de coupe : isole une zone du modèle avec une boîte déplaçable à la souris, trace de la coupe en couleur
- Zoom fenêtre, vues standard (face, côté, dessus, isométrique)
- Extraction des propriétés
- Métré automatique
- Métré par matériau
- Résultats sur appuis (ponctuels, linéaires et surfaciques), résultats sur les voiles (torseurs) et sur les éléments filaires (diagrammes)
- Export des résultats des filaires au format .xlsx
- Export au format IFC
- Filtrage / Isolation des élements
- Enregistrement au format .PNG (HD, Full HD, QHD, 4K ou multiplicateur de la taille de la vue)
- Arborescence des systèmes structuraux, avec sélection/isolation par système
- Statut du modèle (maillage, calcul éléments finis, expertise)
- Réglage de l'éclairage de la scène 3D
- Mode Navigation : caméra libre au clavier/souris
- Minicarte : vue 2D en incrustation avec indicateur de position/orientation de la caméra (flèche en bord de carte quand la caméra en sort) et emprise de la boîte de coupe
- Application en français et en anglais, thèmes clair et sombre
- Aide intégrée (menu « Aide ») : liste des contrôles et raccourcis, vérification des mises à jour

## Documentation

- [Historique des versions](CHANGELOG.md)

## Dernière version

[![GitHub release](https://img.shields.io/github/v/release/mooondark/ADViewer)](https://github.com/mooondark/ADViewer/releases)

**Attention, ce visualiseur nécessite l'utilisation de l'[API](https://github.com/Graitec-Group/advance-design-api) d'Advance Design**

**Une licence est également nécessaire afin de l'utiliser, et le logiciel AD2027 ou supérieur doit être installé**
