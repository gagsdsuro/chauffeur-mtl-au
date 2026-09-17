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

* [ ] **P2** — Migrer l'utilisation de l'API PyMuPDF `fitz` vers `pymupdf`.

  * Reclassé de P1 à P2 le 16 septembre 2026 : dépréciation confirmée, mais les cartes agent fonctionnent avec PyMuPDF 1.28.2 verrouillé. Effort faible ; à traiter avant une prochaine mise à jour de PyMuPDF. Voir l'[historique officiel](https://pymupdf.readthedocs.io/en/latest/changes.html).
  * Remplacer les imports et usages dans `scripts/carte_agent_stm.py`, `tests/test_carte_agent.py` et `tests/creer_cas_test.py`.
  * Actualiser les références dans `README.md` et `CLAUDE.md`.
  * Vérifier les cartes agent, l'absence d'avertissement lié à `fitz` et toute la suite de tests.

* [ ] **P2** — Vérifier la compatibilité Python 3.14 de toutes les dépendances.

  * Vérifier la possibilité de passer à la version 3.14 dans le Dokerfile

* [ ] **P3** — Réévaluer les contraintes des dépendances directes dans `requirements.in` ; `requirements.txt` est généré avec des versions exactes et des empreintes, sans édition manuelle. Suivre la [procédure de maintenance](docs/dependances.md).

* [ ] **P3** — Évaluer l'ajout d'un `pyproject.toml` pour moderniser la gestion du projet Python.

* [x] **P1** — Migrer les trois aperçus HTML de `components.html` vers `st.iframe`.

  * P1 maintenu : trois points d'affichage du workflow courant dépendent d'une API dépréciée. Effort faible à moyen, principalement lié à la validation visuelle. Voir l'[audit Streamlit](docs/audit-streamlit-1.50.md) et la [documentation de `st.iframe`](https://docs.streamlit.io/develop/api-reference/text/st.iframe).
  * Remplacer les deux appels de Ma journée et celui de Rapports ; retirer les imports devenus inutiles.
  * Conserver l'isolation CSS, la hauteur de 600 px et le défilement ; `st.iframe` accepte directement le HTML et ne prend pas le paramètre `scrolling`.
  * Migration et validation automatisée terminées le 16 septembre 2026 : aperçus complets et par trajet, contenu HTML transmis aux iframes, défilement et sorties HTML/PDF couverts par `tests/test_etat_streamlit.py` sur 1.64.0. La validation visuelle reste dans la recette navigateur/mobile ouverte en section 13.

## Code

* [ ] **P3** — Uniformiser progressivement le typage Python.
* [ ] **P3** — Évaluer l'utilisation de `ruff` pour le linting et le formatage.
* [ ] **P4** — Évaluer l'utilisation de `mypy` ou d'un autre type checker.

---

# 2. Tests et qualité

## Suite de tests

* [ ] **P3** — Vérifier que `python tests/run_all.py` passe complètement dans `.venv`.

## Automatisation

* [ ] **P3** — Évaluer l'intérêt de migrer tout ou partie de la suite actuelle vers `pytest`.

---

# 3. Application Streamlit

* [x] **P0** — Corriger les notes de relève associées au mauvais matricule.

  * Réévaluation de l'[audit Streamlit](docs/audit-streamlit-1.50.md), le 16 septembre 2026 : anomalie reproduite sur Python 3.14.4 / Streamlit 1.62.0 avec des fichiers temporaires. Si le matricule de relève change dans le fichier journée pendant que Ma journée reste ouverte, une relance affiche le nouveau nom avec l'ancienne note ; enregistrer écrase la note du nouveau matricule.
  * Inclure le matricule concerné dans les clés du champ et du bouton d'enregistrement de la note de relève.
  * Couvrir `je_releve` et `je_suis_releve_par`, une cible avec ou sans note, les brouillons et les allers-retours ; vérifier le texte affiché et les notes réellement sauvegardées, sans écraser celles d'un autre matricule.
  * Régression reproduite avant correction sur Python 3.12.14 / Streamlit 1.64.0, puis corrigée : les quatre combinaisons de rôle et de présence d'une note passent, avec vérification des fichiers sauvegardés (`tests/test_etat_streamlit.py`).

* [x] **P1** — Vérifier les widgets à contenu variable et la navigation entre pages, conformément à l'[audit Streamlit](docs/audit-streamlit-1.50.md).

  * Examiner les changements de journée, les réimports et les notes dont les données changent alors que la clé du widget reste identique ; traiter le cas confirmé des notes de relève dans le P0 ci-dessus.
  * Vérifier les allers-retours Ma journée → Préparation → Rapports avec des données saisies ; distinguer notes enregistrées, brouillons et dates sélectionnées.
  * Corrections : dates conservées entre pages par `persist_state="session"`, numéro d'autobus réinitialisé après réimport changeant la pièce ou son bus, texte d'import et dépôt PDF liés à leur journée/CA, états des trajets et positions liés à leur contexte, résultats de rafraîchissement effacés au changement de date et états personnels purgés à la déconnexion.
  * Les notes enregistrées sont relues ; les brouillons ne sont pas conservés lors d'un changement de page ou d'identité. Comportements et limites consignés dans le [suivi de l'audit](docs/audit-streamlit-1.50.md#corrections-des-aperçus-et-des-états-de-widgets).
  * Validation : dix nouveaux tests AppTest réussis sur 1.64.0, suite complète **33/33**. La saisie tactile, les vrais téléversements/téléchargements navigateur et le rendu restent dans la recette manuelle.

* [-] **P2** — Remplacer les douze `use_container_width=True` par `width="stretch"`, signalés dans l'[audit Streamlit](docs/audit-streamlit-1.50.md).

  * Quatre usages migrés dans Connexion et Préparation lors des corrections d'état ; huit restent dans le dialogue de session portail et Administration.
  * Vérifier les boutons, formulaires et le tableau d'administration sur 1.64.0, notamment leur disposition et leur accessibilité sur téléphone.

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

* [x] **P4** - "Rapport journalier" et "Rapport V2": Remplacer le sélecteur de date par une liste [j-5, aujourd'hui, j+7], n'afficher que les date où un fichier journée json est présent. Par défaut, la date du jour ou la journée la plus proche valide.

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
* [x] **P2** - [Ma journée](app/pages/1_ma_journee.py) ajuster le sélecteur de date de manière à permettre la saisie manuelle d'une date différente que ceux de la liste déroulante. Ceci permettant de visualiser des journées antérieurs.
* [ ] **P4** - ajusté l'affichage dans le cas du mode "Dark"

# 13. Dette technique / investigations

**Bilan de réévaluation de l'[audit Streamlit](docs/audit-streamlit-1.50.md) — 16 septembre 2026 :** la correction des notes d'autobus et le verrouillage des versions sont présents. Les vérifications ciblées de cette réévaluation passent sous Python 3.14.4 / Streamlit 1.62.0 : cinq tests de `test_durees_app.py`, le scénario Logs de `test_logs_app.py` et trois cas de `test_carte_agent.py`. L'import `fitz` émet encore un avertissement de dépréciation. L'anomalie des notes de relève a été reproduite séparément sur fichiers temporaires ; elle est suivie en P0 dans « Application Streamlit ».

L'audit consigne déjà 32/32 suites réussies sous Python 3.12.14 / Streamlit 1.64.0, dont Logs sans adaptation du pilote AppTest : aucune tâche spécifique à Streamlit 1.50 n'est retenue. Ces résultats Docker n'ont pas été rejoués lors de cette réévaluation. La recette navigateur/mobile reste à exécuter ; la rédaction de sa fiche ne vaut pas validation.

* [x] **P2** — Verrouiller le déploiement sur Python 3.12.14 / Streamlit 1.64.0, avec dépendances transitives et empreintes ; 32/32 suites réussies en conteneur. Voir [la procédure de maintenance](docs/dependances.md).
* [ ] **P1** — Exécuter la [recette navigateur/mobile](docs/recette-navigateur-mobile.md) de l'image Streamlit 1.64.0 avant déploiement.

  * Entrée réouverte après confirmation que la recette n'a pas été exécutée ; priorité relevée pour valider les interactions et le rendu que les tests automatisés ne couvrent pas.
  * Couvrir R01–R07 : connexion/déconnexion, isolation des comptes, navigation, date libre et clavier tactile, notes d'autobus, imports de journée et de PDF, aperçus et téléchargements des rapports, renouvellement de session portail et reprise d'opération.
  * Vérifier le rendu CSS sur ordinateur et téléphone : marges, en-tête, colonnes, boutons, thèmes clair/sombre et orientations portrait/paysage.
  * Conserver un compte rendu daté avec l'image, les versions et les appareils testés ; distinguer les statuts non exécuté, réussi, échoué et bloqué. Sans accès au portail, déclarer le scénario concerné bloqué ; aucune vérification non exécutée ou bloquée ne vaut réussite.

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
