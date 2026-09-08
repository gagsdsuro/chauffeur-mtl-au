# TODO — chauffeur-stm

Ce fichier centralise les améliorations, corrections, travaux futurs et investigations du projet.

## Priorités

* **P0 — Critique** : blocage, risque de perte/corruption de données, problème de sécurité ou impossibilité d'utiliser le projet.
* **P1 — Haute** : important pour la stabilité, la maintenabilité ou le workflow courant.
* **P2 — Moyenne** : amélioration utile, mais non bloquante.
* **P3 — Basse** : confort, optimisation ou idée à traiter lorsque le reste est stabilisé.

## États

* `[ ]` À faire
* `[-]` En cours
* `[x]` Terminé
* `[?]` À investiguer / décision à prendre

---

# 1. Maintenance technique

## Python / dépendances

* [ ] **P1** — Migrer l'utilisation de l'API PyMuPDF `fitz` vers `pymupdf`.

  * Vérifier tous les imports et usages de `fitz`.
  * Adapter le code concerné.
  * Adapter les tests.
  * Mettre à jour `README.md`.
  * Valider toute la suite de tests.

* [ ] **P1** — Vérifier la compatibilité Python 3.14 de toutes les dépendances.

  * Vérifier la possibilité de passer à la version 3.14 dans le Dokerfile

* [ ] **P2** — Vérifier si les versions minimales de `requirements.txt` sont encore appropriées.

* [ ] **P2** — Évaluer l'ajout d'un `pyproject.toml` pour moderniser la gestion du projet Python.

* [ ] **P3** - Évaluer le message au runtime: `st.components.v1.html` will be removed after 2026-06-01. ... Please replace `st.components.v1.html` with `st.iframe`.

## Code

* [ ] **P2** — Uniformiser progressivement le typage Python.
* [ ] **P2** — Évaluer l'utilisation de `ruff` pour le linting et le formatage.
* [ ] **P3** — Évaluer l'utilisation de `mypy` ou d'un autre type checker.

---

# 2. Tests et qualité

## Suite de tests

* [ ] **P1** — Vérifier que `python tests/run_all.py` passe complètement dans `.venv`.

## Automatisation

* [ ] **P2** — Évaluer l'intérêt de migrer tout ou partie de la suite actuelle vers `pytest`.

---

# 3. Application Streamlit

* [ ] **P1** — Améliorer les messages d'erreur affichés à l'utilisateur.
* [ ] **P2** — Vérifier les temps de chargement lorsque `data/` devient volumineux.
* [ ] **P2** — Évaluer la mise en cache des données calculées.

---

# 4. Données STM

## GTFS / GTFS-RT

* [ ] **P2** — Vérifier la conservation des données historiques.
* [ ] **P2** — Définir une politique de nettoyage et d'archivage des anciennes données.

## Données métier

* [ ] **P2** — Ajouter des validations automatiques des fichiers JSON importants.
* [ ] **P2** — Évaluer un schéma de validation JSON pour les formats stables.

---

# 5. Rapports

## Génération

* [x] **P1** — Normaliser le tableau « Détours & arrêts modifiés » du rapport journalier.

  * Conserver la page G-D en portrait et afficher les pages d'événements en paysage.
  * Présenter un événement par ligne avec les colonnes « Événement / titre », « Période », « Détour & commentaires », « Arrêts » et « Effectif ».
  * Afficher chaque instruction G-D sur une ligne distincte.
  * Séparer le commentaire, les arrêts annulés ou concernés et les arrêts ajoutés.
  * Répéter l'en-tête du tableau et permettre le fractionnement des événements longs.

* [ ] **P3** - "Rapport journalier" et "Rapport V2": Remplacer le sélecteur de date par une liste [j-5, aujourd'hui, j+7], n'afficher que les date où un fichier journée json est présent. Par défaut, la date du jour ou la journée la plus proche valide.

## Qualité

* [x] **P1** — Ajouter un cas de test de rapport complexe couvrant les événements de la ligne 10, les arrêts ajoutés, une fin indéterminée et la pagination paysage.

---

# 6. Scripts d'import et de traitement

* [x] **P1** — Uniformiser le compte rendu des événements ajoutés, modifiés et retirés.

  * Utiliser la même comparaison structurée pour l'import manuel, le rafraîchissement portail, l'UI et les journaux.
  * Afficher l'ancien G-D, le commentaire et les arrêts de chaque événement retiré.
  * Afficher les versions avant et après du G-D, du commentaire et des arrêts de chaque événement modifié.
  * Trier les tableaux de plusieurs événements selon le premier arrêt annulé ou concerné, sinon le premier arrêt ajouté, dans l'ordre du parcours; conserver les événements sans ancre connue à la fin dans leur ordre d'origine.
  * Conserver les variantes légitimes partageant un même `evenement_id`.
  * Respecter l'option CLI qui masque les détails et l'encadrement historique des journaux.

* [x] **P1** — Préserver les retours à la ligne des G-D lors de l'import, avec repli compatible pour les anciennes chaînes aplaties.
* [ ] **P2** — Uniformiser les conventions de ligne de commande.
* [ ] **P1** — Ajouter une gestion d'erreur cohérente.
* [ ] **P3** — Adapter `parse_journee.py` au format multiligne produit par un copier-coller depuis Firefox, si ce navigateur devient officiellement pris en charge par `employe.stm.info`.

---

# 7. Gestion des données générées

* [ ] **P1** — Définir clairement quelles données sous `data/` sont des sources.
* [ ] **P1** — Définir quelles données sont générées par les scripts.
* [ ] **P2** — Documenter la stratégie d'archivage des données historiques.

---

# 8. Docker / déploiement

* [ ] **P1** — Vérifier le healthcheck Streamlit.
* [ ] **P1** — Documenter les variables d'environnement nécessaires.
* [ ] **P1** — Comparer le comportement local Python 3.14 avec Python 3.12 dans Docker.

---

# 9. Sécurité


---

# 10. Documentation


* [x] **P2** — Documenter le format réel des fichiers d'événements et les ID dupliqués légitimes.
* [ ] **P2** — Documenter les formats de données importants.

---

# 11. Git / gestion du projet


---

# 12. Améliorations fonctionnelles

* [-] **P2** — Identifier les traitements manuels pouvant être automatisés.
  * Préparation de la journée
    * Évaluer la faisabilité d'automatiser la lecture des G-D manquants ou expirés à partir d'une session valide. Garder la version manuel de la même manière que pour les évènements.
    * Évaluer la faisabilité d'automatiser la lecture d'une journée de travail à partir d'une session valide. Garder la version manuel de la même manière que pour les évènements. Prévoir les variantes pour aujourd'hui, demain, après-demain, Lundi le jj, Mardi le jj, etc. Prévoir la variante avec TS (temps supplémentaire) Voir le fichier ci-joint du 22 août
    * Repenser le workflow de l'import des CA
      * Récupérer, annoter, Imprimer
* [ ] **P2** — Identifier les informations actuellement difficiles à consulter dans l'interface.
  * "Fichiers"/"Gestion des fichiers"/"Journée" déplacer les sections "Aperçu" et "Export" devant la liste de fichier ou mettre la liste de fichier dans une section refermable.
* [ ] **P2** - Créer un tableau des durées de trajet, battement, pause à partir des informations de la journée et des données GTFS

---

# 13. Dette technique / investigations

* [ ] **P1** — Déterminer si Python 3.14 doit devenir la version officiellement supportée hors Docker.
* [ ] **P1** — Déterminer si Python 3.12 doit également être utilisé pour le développement local afin d'assurer une parité stricte avec Docker.
* [ ] **P2** — Déterminer si le projet doit rester basé sur `requirements.txt` ou évoluer vers `pyproject.toml`.

---

# 14. UI
* [x] **P1** - Réorganisation de la page "Ma journée"

  * Limité le contenu de la liste déroulante "Journée" à [-2, aujourd'hui, +5]
  * Retirer le selecteur "Niveau des rapport". Garder "Détaillé" comme valeur par défaut.
  * Remplacer la section "Préparation de la journée" par une section "Rafraîchir les données du jour"
    * Récupère les évènements pour les ligne restantes du jour.
      * si des changements sont détectés, regénère le rapport v2
  * Retirer les bouton "Carte annotée", "Rapport journlier" et "Rapport V2 standard"
  * Garder l'aperçu du dernier rapport v2
  * Garder la section "Pièces de travail" tel quel. 

* [x] **P1** - Réorganisation de la section import pour devenir "Préparation d'une journée"

  * Flux de travail typique:
    * Sélectionne une date 
    * (Tâches manuelles) 
      * 1- Importer la journée, 
      * 2- Importé la CA, 
      * 3- Importer les Gauche-Droite manquants, 
    * (Tâches déclanchés en série): 
      * 4a- Récupérer les événements des routes de la journée, 
      * 4b- Générer le rapport Journalier, 
      * 4c- Générer la version standard du rapport v2. 

* [x] **P1** — Réutiliser la présentation normalisée des événements dans « Pièces de travail ».

  * Remplacer les accordéons individuels par un tableau multiligne adapté à la largeur disponible.
  * Afficher tous les événements avec leur état applicable ou non applicable et la raison d'exclusion.
  * Conserver le filtrage par date, plage horaire et correspondance avec le parcours.
  * Afficher G-D, commentaire, arrêts concernés et ajoutés, identifiants, période et effectif.
  * Prévoir un défilement horizontal sur les écrans étroits.
