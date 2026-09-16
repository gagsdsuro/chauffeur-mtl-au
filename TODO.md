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

* [ ] **P3** — Vérifier si les versions minimales de `requirements.txt` sont encore appropriées.

* [ ] **P3** — Évaluer l'ajout d'un `pyproject.toml` pour moderniser la gestion du projet Python.

* [ ] **P2** - Évaluer le message au runtime: `st.components.v1.html` will be removed after 2026-06-01. ... Please replace `st.components.v1.html` with `st.iframe`.

## Code

* [ ] **P3** — Uniformiser progressivement le typage Python.
* [ ] **P3** — Évaluer l'utilisation de `ruff` pour le linting et le formatage.
* [ ] **P4** — Évaluer l'utilisation de `mypy` ou d'un autre type checker.

---

# 2. Tests et qualité

## Suite de tests

* [ ] **P2** — Vérifier que `python tests/run_all.py` passe complètement dans `.venv`.

## Automatisation

* [ ] **P3** — Évaluer l'intérêt de migrer tout ou partie de la suite actuelle vers `pytest`.

---

# 3. Application Streamlit

* [ ] **P2** — Améliorer les messages d'erreur affichés à l'utilisateur.
* [ ] **P3** — Vérifier les temps de chargement lorsque `data/` devient volumineux.
* [ ] **P3** — Évaluer la mise en cache des données calculées.

---

# 4. Données STM

## GTFS / GTFS-RT

* [ ] **P3** — Vérifier la conservation des données historiques.
* [ ] **P3** — Définir une politique de nettoyage et d'archivage des anciennes données.

## Données métier

* [ ] **P3** — Ajouter des validations automatiques des fichiers JSON importants.
* [ ] **P3** — Évaluer un schéma de validation JSON pour les formats stables.

---

# 5. Rapports

## Génération

* [x] **P1** — Normaliser le tableau « Détours & arrêts modifiés » du rapport journalier.

  * Conserver la page G-D en portrait et afficher les pages d'événements en paysage.
  * Présenter un événement par ligne avec les colonnes « Événement / titre », « Période », « Détour & commentaires », « Arrêts » et « Effectif ».
  * Afficher chaque instruction G-D sur une ligne distincte.
  * Séparer le commentaire, les arrêts annulés ou concernés et les arrêts ajoutés.
  * Répéter l'en-tête du tableau et permettre le fractionnement des événements longs.

* [ ] **P4** - "Rapport journalier" et "Rapport V2": Remplacer le sélecteur de date par une liste [j-5, aujourd'hui, j+7], n'afficher que les date où un fichier journée json est présent. Par défaut, la date du jour ou la journée la plus proche valide.

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
* [ ] **P3** — Uniformiser les conventions de ligne de commande.
* [ ] **P2** — Ajouter une gestion d'erreur cohérente.
* [ ] **P4** — Adapter `parse_journee.py` au format multiligne produit par un copier-coller depuis Firefox, si ce navigateur devient officiellement pris en charge par `employe.stm.info`.

---

# 7. Gestion des données générées

* [ ] **P2** — Définir clairement quelles données sous `data/` sont des sources.
* [ ] **P2** — Définir quelles données sont générées par les scripts.
* [ ] **P3** — Documenter la stratégie d'archivage des données historiques.

---

# 8. Docker / déploiement

* [ ] **P2** — Vérifier le healthcheck Streamlit.
* [ ] **P2** — Documenter les variables d'environnement nécessaires.
* [ ] **P2** — Comparer le comportement local Python 3.14 avec Python 3.12 dans Docker.

---

# 9. Sécurité


---

# 10. Documentation


* [x] **P3** — Documenter le format réel des fichiers d'événements et les ID dupliqués légitimes.
* [ ] **P3** — Documenter les formats de données importants.

---

# 11. Git / gestion du projet


---

# 12. Améliorations fonctionnelles

* [-] **P3** — Identifier les traitements manuels pouvant être automatisés.
  * Préparation de la journée
    * Évaluer la faisabilité d'automatiser la lecture des G-D manquants ou expirés à partir d'une session valide. Garder la version manuel de la même manière que pour les évènements.
    * Évaluer la faisabilité d'automatiser la lecture d'une journée de travail à partir d'une session valide. Garder la version manuel de la même manière que pour les évènements. Prévoir les variantes pour aujourd'hui, demain, après-demain, Lundi le jj, Mardi le jj, etc. Prévoir la variante avec TS (temps supplémentaire) Voir le fichier ci-joint du 22 août
    * Repenser le workflow de l'import des CA
      * Récupérer, annoter, Imprimer
* [ ] **P3** — Identifier les informations actuellement difficiles à consulter dans l'interface.
  * "Fichiers"/"Gestion des fichiers"/"Journée" déplacer les sections "Aperçu" et "Export" devant la liste de fichier ou mettre la liste de fichier dans une section refermable.
* [x] **P1** - Créer un tableau résumé des durées à partir des informations de la journée. Voir le fichier [fonction-résumé des durées.md](<docs/fonction-résumé des durées.md>)
* [ ] **P2** - [Ma journée](app/pages/1_ma_journee.py) ajuster le sélecteur de date de manière à permettre la saisie d'une date autres que ceux de la liste déroulante. Ceci permettant de visualiser des journées antérieurs.

# 13. Dette technique / investigations

* [ ] **P2** — Déterminer si Python 3.14 doit devenir la version officiellement supportée hors Docker.
* [ ] **P2** — Déterminer si Python 3.12 doit également être utilisé pour le développement local afin d'assurer une parité stricte avec Docker.
* [ ] **P3** — Déterminer si le projet doit rester basé sur `requirements.txt` ou évoluer vers `pyproject.toml`.

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

---

# 15. Authentification locale par PIN (phase 3)

* [x] **P1** — Verrouiller l'app par un PIN au démarrage de chaque session navigateur.

  * Comptes dans `data/users.json` (0600, gitignoré, `matricule → {nom, rôle, sel, hash scrypt, tentatives, verrou}`) via `chauffeur/auth.py`.
  * Premier compte créé = Chauffeur-admin, suivants = Chauffeur (rôles exploités à la phase 4).
  * Verrouillage 5 échecs → 5 min ; `changer_pin`/`revoquer_compte`.
  * Page de connexion + wizard de premier lancement + déconnexion dans la barre latérale (`app/components/connexion.py`).

* [x] **P1** — Routage des données privées sur le matricule authentifié (contexte par thread dans `chauffeur.depots`).

  * `bootstrap.initialiser_page()` pose le matricule de session ; modules de domaine et `depots` le consultent à l'usage.
  * Accès privés via accesseurs `bootstrap.journees_dir()`/`ca_dir()`/`notes_dir()`/`rapports_dir()`/`log_dir()`/`session_path()`.

* [x] **P1** — Mode strict `CHAUFFEUR_MODE_STRICT=1` (opt-in explicite, jamais par défaut) : plus de repli legacy, erreur claire sans matricule.

* [x] **P3** — Phase 4 : page d'administration et rôles (auto-gestion stricte).

  * Auto-gestion stricte retenue : seul un Chauffeur-admin promeut un Chauffeur ; l'autorité d'un admin n'est modifiable que par lui-même (auto-destitution refusée pour le dernier admin) ; un admin n'est jamais révocable par autrui ni par soi. (`chauffeur.auth.changer_role`/`revoquer_compte`.)
  * Chauffeur : changement de son propre PIN en autonomie (ancien requis, barre latérale) ; l'admin réinitialise sans l'ancien (`reinitialiser_pin`) et déverrouille (`deverrouiller_compte`).
  * Page `app/pages/6_administration.py` : liste, création (rôle au choix), promotion/destitution, réinitialisation de PIN, déverrouillage, révocation — visible uniquement aux Chauffeur-admin (`st.navigation` filtré dans `main.py` + garde-fou en page).
  * Tests : `tests/test_auth_roles.py` (matrice d'autorisations) et `tests/test_administration_app.py` (AppTest : garde-fou Chauffeur + gestion par l'admin).
