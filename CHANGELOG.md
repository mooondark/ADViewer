# Changelog ADViewer

**⚠ Pour l'affichage correct des combinaisons (ID et nom complet), la version 2027.1 beta est nécessaire**

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
