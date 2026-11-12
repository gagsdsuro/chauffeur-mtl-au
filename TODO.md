# TODO — Chauffeur Mtl-AU

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

* [x] **P2** — Migrer l'utilisation de l'API PyMuPDF `fitz` vers `pymupdf`.

  * Reclassé de P1 à P2 le 16 septembre 2026 : dépréciation confirmée, mais les cartes agent fonctionnent avec PyMuPDF 1.28.2 verrouillé. Effort faible ; à traiter avant une prochaine mise à jour de PyMuPDF. Voir l'[historique officiel](https://pymupdf.readthedocs.io/en/latest/changes.html).
  * Remplacer les imports et usages dans `scripts/carte_agent_stm.py`, `tests/test_carte_agent.py` et `tests/creer_cas_test.py`.
  * Actualiser les références dans `README.md` et `CLAUDE.md`.
  * Migration réalisée le 22 septembre 2026, sans changement de version ; documentation actualisée et suite complète 37/37 réussie dans l’environnement verrouillé. La recette tactile de la carte annotée reste à rejouer pour cette livraison.

* [ ] **P2** — Vérifier la compatibilité Python 3.14 de toutes les dépendances.

  * Vérifier la possibilité de passer à la version 3.14 dans le Dockerfile

* [ ] **P3** — Réévaluer les contraintes des dépendances directes dans `requirements.in` ; `requirements.txt` est généré avec des versions exactes et des empreintes, sans édition manuelle. Suivre la [procédure de maintenance](docs/dependances.md).

* [ ] **P3** — Évaluer l'ajout d'un `pyproject.toml` pour moderniser la gestion du projet Python.

* [x] **P1** — Migrer les trois aperçus HTML de `components.html` vers `st.iframe`.

  * P1 maintenu : trois points d'affichage du workflow courant dépendent d'une API dépréciée. Effort faible à moyen, principalement lié à la validation visuelle. Voir l'[audit Streamlit](docs/audit-streamlit-1.50.md) et la [documentation de `st.iframe`](https://docs.streamlit.io/develop/api-reference/text/st.iframe).
  * Remplacer les deux appels de Ma journée et celui de Rapports ; retirer les imports devenus inutiles.
  * Conserver l'isolation CSS, la hauteur de 600 px et le défilement ; `st.iframe` accepte directement le HTML et ne prend pas le paramètre `scrolling`.
  * Migration et validation automatisée terminées le 16 septembre 2026 : aperçus complets et par trajet, contenu HTML transmis aux iframes, défilement et sorties HTML/PDF couverts par `tests/test_etat_streamlit.py` sur 1.64.0. La validation visuelle reste dans la recette navigateur/mobile ouverte en section 13.

## Code

* [ ] **P2** — Uniformiser progressivement le typage Python.
* [ ] **P3** — Évaluer l'utilisation de `ruff` pour le linting et le formatage.
* [ ] **P4** — Évaluer l'utilisation de `mypy` ou d'un autre type checker.

---

# 2. Tests et qualité

## Suite de tests

* [ ] **P3** — Vérifier que `python tests/run_all.py` passe complètement dans `.venv`.

## Automatisation

* [ ] **P1** — Créer une tâche VS Code pour exécuter toute la suite.
* [ ] **P2** — Créer des tâches VS Code pour les suites principales.
* [ ] **P2** — Ajouter éventuellement une commande unique de validation avant commit.
* [ ] **P2** — Évaluer l'ajout d'un script `check.sh` ou équivalent regroupant les validations.
* [ ] **P3** — Évaluer l'intérêt de migrer tout ou partie de la suite actuelle vers `pytest`.

---

# 3. VS Code / environnement de développement

* [x] **P1** — Créer le `.venv` du projet.
* [x] **P1** — Configurer `.vscode/settings.json`.
* [x] **P1** — Configurer `launch.json` pour l'application Streamlit.
* [ ] **P2** — Créer `.vscode/tasks.json`.
* [ ] **P2** — Ajouter une tâche « Tests complets ».
* [ ] **P2** — Ajouter une tâche « Lancer Streamlit ».
* [ ] **P2** — Ajouter une tâche « Docker Compose ».
* [ ] **P2** — Vérifier le débogage des modules `chauffeur`.
* [ ] **P2** — Documenter l'environnement de développement dans `README.md`.
* [ ] **P3** — Évaluer les améliorations possibles du workflow terminal / VS Code.

---

# 4. Application Streamlit

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

* [x] **P2** — Remplacer les douze `use_container_width=True` par `width="stretch"`, signalés dans l'[audit Streamlit](docs/audit-streamlit-1.50.md).

  * Les six derniers usages, dans Administration, ont été migrés le 22 septembre 2026 ; aucun usage ne reste dans `app/`. Tests AppTest réussis ; vérification sur téléphone physique à compléter.
  * Vérifier les boutons, formulaires et le tableau d'administration sur 1.64.0, notamment leur disposition et leur accessibilité sur téléphone.

* [ ] **P2** — Améliorer les messages d'erreur affichés à l'utilisateur.
* [ ] **P3** — Vérifier les temps de chargement lorsque `data/` devient volumineux.
* [ ] **P3** — Évaluer la mise en cache des données calculées.
* [ ] **P1** — Vérifier le comportement lorsqu'une donnée attendue est absente ou invalide.
* [ ] **P2** — Identifier les améliorations prioritaires de l'interface Streamlit.

---

# 5. Données

## GTFS / GTFS-RT

* [ ] **P1** — Documenter précisément le flux d'import GTFS.
* [ ] **P1** — Documenter précisément le flux GTFS-RT.
* [ ] **P1** — Vérifier la gestion des erreurs réseau.
* [ ] **P1** — Vérifier la gestion des réponses invalides ou incomplètes.
* [ ] **P3** — Vérifier la conservation des données historiques.
* [ ] **P3** — Définir une politique de nettoyage et d'archivage des anciennes données.

## Données métier

* [ ] **P3** — Ajouter des validations automatiques des fichiers JSON importants.
* [ ] **P3** — Évaluer un schéma de validation JSON pour les formats stables.

---

# 6. Rapports

## Génération

* [x] **P1** — Normaliser le tableau « Détours & arrêts modifiés » du rapport journalier.

  * Conserver la page G-D en portrait et afficher les pages d'événements en paysage.
  * Présenter un événement par ligne avec les colonnes « Événement / titre », « Période », « Détour & commentaires », « Arrêts » et « Effectif ».
  * Afficher chaque instruction G-D sur une ligne distincte.
  * Séparer le commentaire, les arrêts annulés ou concernés et les arrêts ajoutés.
  * Répéter l'en-tête du tableau et permettre le fractionnement des événements longs.

* [x] **P4** - "Rapport journalier" et "Rapport V2": Remplacer le sélecteur de date par une liste [j-5, aujourd'hui, j+7], n'afficher que les date où un fichier journée json est présent. Par défaut, la date du jour ou la journée la plus proche valide.
* [ ] **P2** — Documenter les différences entre les versions de rapports existantes.
* [ ] **P2** — Identifier les générateurs encore utilisés et ceux devenus historiques.
* [ ] **P2** — Uniformiser le nommage des rapports.
* [ ] **P2** — Vérifier la gestion des caractères accentués dans les noms de fichiers.
* [ ] **P1** — Vérifier la génération des PDF sur l'environnement Docker.

## Qualité

* [x] **P1** — Ajouter un cas de test de rapport complexe couvrant les événements de la ligne 10, les arrêts ajoutés, une fin indéterminée et la pagination paysage.
* [ ] **P1** — Vérifier les cas limites concernant les parcours et horaires.
* [ ] **P2** — Comparer automatiquement certains rapports de référence avec les résultats attendus.

---

# 7. Scripts d'import et de traitement

* [ ] **P1** — Documenter les scripts sous `scripts/`.
* [ ] **P1** — Documenter l'ordre d'exécution des scripts lorsqu'un traitement complet est requis.
* [ ] **P1** — Vérifier les dépendances entre scripts.
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
* [ ] **P2** — Vérifier les messages de log.
* [ ] **P3** — Évaluer l'ajout d'un point d'entrée CLI unique pour les opérations courantes.
* [ ] **P4** — Adapter `parse_journee.py` au format multiligne produit par un copier-coller depuis Firefox, si ce navigateur devient officiellement pris en charge par `employe.stm.info`.

---

# 8. Gestion des données générées

* [ ] **P2** — Définir clairement quelles données sous `data/` sont des sources.
* [ ] **P2** — Définir quelles données sont générées par les scripts.
* [ ] **P1** — Définir ce qui doit être versionné dans Git.
* [ ] **P1** — Définir ce qui doit rester uniquement sur l'environnement local.
* [ ] **P2** — Examiner les fichiers `.bak`, logs et autres artefacts 
* [ ] **P3** — Documenter la stratégie d'archivage des données historiques.
* [ ] **P1** — Séparer, lorsque pertinent, les données de développement des données de production.

---

# 9. Docker / déploiement

* [ ] **P1** — Tester `docker compose up --build` sur une installation propre.
* [ ] **P1** — Vérifier que l'UID/GID du conteneur correspond bien à l'utilisateur de l'hôte.
* [ ] **P1** — Vérifier les permissions des fichiers générés dans `data/`.
* [x] **P2** — Vérifier le healthcheck Streamlit.

  * Image `chauffeur-mtl-au:candidate-20260922` démarrée sans port exposé ni données personnelles : état Docker `healthy`, sonde terminée avec code 0.
* [ ] **P2** — Documenter les variables d'environnement nécessaires.
* [ ] **P0** — Vérifier le traitement sécurisé de `Installation/config/secrets.*`.
* [ ] **P2** — Évaluer une stratégie de versionnement des images Docker.
* [ ] **P2** — Comparer le comportement local Python 3.14 avec Python 3.12 dans Docker.

---

# 10. Sécurité

* [x] **P0** — Vérifier qu'aucun secret ou identifiant sensible n'est actuellement suivi par Git (audit de publication, novembre 2026 ; `gitleaks` à l'étape finale).
* [ ] **P0** — Vérifier les permissions des fichiers de session et cookies.
* [ ] **P0** — Vérifier le contenu de `Installation/config/`.
* [ ] **P0** — Vérifier que les données sensibles restent exclues du dépôt.
* [ ] **P2** — Évaluer un scan automatique des secrets avant commit.

---

# 11. Documentation

* [ ] **P2** — Mettre à jour `README.md` au fur et à mesure des changements.
* [ ] **P2** — Documenter l'installation complète sur Ubuntu.
* [ ] **P2** — Documenter l'installation avec Docker.
* [ ] **P2** — Documenter le workflow de développement VS Code.
* [ ] **P2** — Documenter l'exécution des tests.
* [ ] **P2** — Documenter le workflow de mise à jour des données STM.
* [ ] **P1** — Vérifier la cohérence entre `README.md`, `AGENTS.md`, `CLAUDE.md` et les scripts.
* [ ] **P2** — Documenter les principaux modules du package `chauffeur`.
* [x] **P3** — Documenter le format réel des fichiers d'événements et les ID dupliqués légitimes.
* [ ] **P2** — Documenter les formats de données importants.

---

# 12. Git / gestion du projet

* [ ] **P1** — Vérifier que `.gitignore` correspond effectivement aux données qui doivent être versionnées.
* [ ] **P2** — Établir les conventions de commit.
* [ ] **P2** — Vérifier les branches et le workflow Git.
* [ ] **P3** — Évaluer l'ajout de hooks Git pour les vérifications automatiques.
* [ ] **P2** — Vérifier régulièrement `git status` avant commit.
* [ ] **P1** — Documenter la procédure de sauvegarde/restauration du dépôt.
---

# 13. Améliorations fonctionnelles

* [-] **P3** — Identifier les traitements manuels pouvant être automatisés.
  * Préparation de la journée
    * Évaluer la faisabilité d'automatiser la lecture des G-D manquants ou expirés à partir d'une session valide. Garder la version manuel de la même manière que pour les évènements.
    * Évaluer la faisabilité d'automatiser la lecture d'une journée de travail à partir d'une session valide. Garder la version manuel de la même manière que pour les évènements. Prévoir les variantes pour aujourd'hui, demain, après-demain, Lundi le jj, Mardi le jj, etc. Prévoir la variante avec TS (temps supplémentaire) Voir le fichier ci-joint du 22 août
    * Repenser le workflow de l'import des CA
      * Récupérer, annoter, Imprimer
* [x] **P3** — Faciliter l’accès aux aperçus et à l’export dans Fichiers.
  * Explorateur paginé avec aperçu et actions accessibles ; export des journées séparé en haut de page. Implémentation terminée ; recette R08 partielle.
* [x] **P1** - Créer un tableau résumé des durées à partir des informations de la journée. Voir le fichier [fonction-résumé des durées.md](<docs/fonction-résumé des durées.md>)
* [x] **P2** - [Ma journée](app/pages/1_ma_journee.py) ajuster le sélecteur de date de manière à permettre la saisie manuelle d'une date différente que ceux de la liste déroulante. Ceci permettant de visualiser des journées antérieurs.
* [-] **P4** — Ajuster l’affichage en mode sombre.
  * Palette claire explicite des tableaux d’événements partagés et des aperçus HTML dans Fichiers, Ma journée et Rapports, y compris les anciens rapports. Contrôles navigateur ciblés et recette sur téléphone physique suivis dans. Ne vaut pas audit complet de tous les écrans.
* [ ] **P2** — Publier à la demande l’horaire de travail dans un agenda Google déjà partagé avec l’entourage, dès que la journée est chargée lors de sa préparation. Voir le [cas d’utilisation](USECASES.md#chauffeur--partage-de-lhoraire-de-travail).
  * Un événement par pièce de travail, y compris sans ligne et en temps supplémentaire, hors absences ; bornes de prise début et prise fin, titre avec les lignes distinctes et les heures, passage à minuit dans le fuseau `America/Toronto`.
  * À chaque nouvelle publication, synchroniser uniquement les événements de cette journée gérés par l’application : ajouts, modifications et retraits sans doublons. Signaler les bornes invalides et les échecs sans bloquer la préparation ; permettre une nouvelle tentative.
  * Cas d’utilisation formalisé ; implémentation et choix techniques de connexion Google à réaliser.
* [x] **P2** - Automatiser le téléchargement de la carte agent PDF au moment de la préparation de la journée.
  * `PortailClient.fetch_carte_agent` (lien `#btnCarteAgent` de la page journée) ; utilisé par la préparation semi-automatique.
* [ ] **P3** - Prévoir un mode manuel, semi-automatique et automatique pour la préparation de la journée
  * en mode manuel les étapes sont exécutées à la demande et permet l'utilisation des import manuel de secours.
  * en mode semi automatique, les étapes de préparation sont déclanché en bloc à la demande. **Réalisé** (page Préparation, `chauffeur/preparation_auto.py`) ; manuel et automatique restent à faire.
  * en mode automatique, la préparation se fait de façon autonome à une heure spécifiée dans la mesure où la session est valide.
* [ ] **P3** - Fonction permettant de garder vivante une session active.
* Revoir la présentation de la page ma journée afin de combiner le tableau des durées avec la section Pièces de travail.
* [x] **P4** - Rebranding de l'application : « Chauffeur Mtl-AU » (retrait de la marque STM ; la mention d'attribution CC BY des données ouvertes est conservée, voir `NOTICE.md`).
* [ ] **P4** - Rebranding du rapport V2
  * idée: Rapport Gauche-Droite
  * idée: Rapport GD+
* [ ] **P4** - Rebranding de la section Fichier
  * idée: Plutôt que de mettre l'emphase sur les contenants (fichiers), présenter les éléments comme des entités ou objets. Ajouter une couche d'abstraction moins technique. 
* [ ] **P2** - Rapport V2, ajouter un mode de fonctionnement sans fichier journée
  * En option, passer une liste de ligne/id-parcours/direction/heure de départ
    * ajout du filtre heure de départ
    * générer chaque groupe ligne/id-parcours/direction
      * si le résultat pour un groupe est identique, indiquer l'heure applicable, sinon garder le résultat 
        * par exemple si un détour est applicable pour les trajets de 12:30 et 14:18 mais pas pour celui 15:12, les 2 résultats seront conserver.
  * Ajuster la page Rapports/Rapport V2 (journée) afin de sélectionner les lignes/directions souhaités
    * Afficher une liste des lignes/directions/id-parcours avec un checkbox ou équivalent
      * par défaut toutes les lignes sont sélectionnées
* [ ] **P2** - Recherche croisée CA/journée et journée/CA
* [ ] **P3** _ Profil chauffeur épurer
  * Réduire au minimum l'exposition des éléments techniques (fichier, json, GTFS, etc)  
* [ ] **P3** - Affichage des check point  
---

# 14. Dette technique / investigations

**Bilan de réévaluation de l'[audit Streamlit](docs/audit-streamlit-1.50.md) — 16 septembre 2026 :** la correction des notes d'autobus et le verrouillage des versions sont présents. Les vérifications ciblées de cette réévaluation passent sous Python 3.14.4 / Streamlit 1.62.0 : cinq tests de `test_durees_app.py`, le scénario Logs de `test_logs_app.py` et trois cas de `test_carte_agent.py`. L'import `fitz` émet encore un avertissement de dépréciation. L'anomalie des notes de relève a été reproduite séparément sur fichiers temporaires ; elle est suivie en P0 dans « Application Streamlit ».

L'audit consigne déjà 32/32 suites réussies sous Python 3.12.14 / Streamlit 1.64.0, dont Logs sans adaptation du pilote AppTest : aucune tâche spécifique à Streamlit 1.50 n'est retenue. Ces résultats Docker n'ont pas été rejoués lors de cette réévaluation. La recette navigateur/mobile reste à exécuter ; la rédaction de sa fiche ne vaut pas validation.

* [x] **P2** — Verrouiller le déploiement sur Python 3.12.14 / Streamlit 1.64.0, avec dépendances transitives et empreintes ; 32/32 suites réussies en conteneur. Voir [la procédure de maintenance](docs/dependances.md).
* [x] **P1** — Exécuter la [recette navigateur/mobile](docs/recette-navigateur-mobile.md) de l'image Streamlit 1.64.0 avant déploiement.

  * Entrée réouverte après confirmation que la recette n'a pas été exécutée ; priorité relevée pour valider les interactions et le rendu que les tests automatisés ne couvrent pas.
  * Première exécution les 16–17 septembre : R01–R04 et R06 réussis sur les deux appareils. R05/R07 rejoués avec succès le 17 septembre après correction du chemin personnel du rapport journalier et du fond des rapports HTML ; recette validée sur `chauffeur-stm:recette-rapports` (code `d49224e`). Voir le.
  * Couvrir R01–R07 : connexion/déconnexion, isolation des comptes, navigation, date libre et clavier tactile, notes d'autobus, imports de journée et de PDF, aperçus et téléchargements des rapports, renouvellement de session portail et reprise d'opération.
  * Vérifier le rendu CSS sur ordinateur et téléphone : marges, en-tête, colonnes, boutons, thèmes clair/sombre et orientations portrait/paysage.
  * Conserver un compte rendu daté avec l'image, les versions et les appareils testés ; distinguer les statuts non exécuté, réussi, échoué et bloqué. Sans accès au portail, déclarer le scénario concerné bloqué ; aucune vérification non exécutée ou bloquée ne vaut réussite.

* [ ] **P2** — Déterminer si Python 3.14 doit devenir la version officiellement supportée hors Docker.
* [ ] **P2** — Déterminer si Python 3.12 doit également être utilisé pour le développement local afin d'assurer une parité stricte avec Docker.
* [ ] **P3** — Déterminer si le projet doit rester basé sur `requirements.txt` ou évoluer vers `pyproject.toml`.
* [ ] **P2** — Déterminer si pytest est pertinent ou si `tests/run_all.py` doit rester la référence.
* [ ] **P2** — Évaluer l'intérêt d'une CI Git pour automatiser les tests.
* [ ] **P1** — Évaluer une stratégie de séparation entre données de développement et données de production.

---

# 15. UI
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
# 16. Backlog initial

Ce backlog constitue le point de départ opérationnel au **30 août 2026**. Les tâches doivent être déplacées dans les sections appropriées lorsqu'elles deviennent suffisamment définies.

## Environnement et outillage

* [ ] **P1** — Vérifier que toutes les dépendances de `requirements.txt` s'installent correctement dans `.venv`.
* [ ] **P1** — Exécuter `python tests/run_all.py` et établir l'état initial de la suite de tests.
* [ ] **P1** — Tester le lancement de l'application avec `streamlit run app/ui.py`.
* [ ] **P1** — Tester le lancement avec `docker compose up --build`.
* [ ] **P2** — Créer `.vscode/tasks.json`.
* [ ] **P2** — Documenter dans `README.md` le workflow de développement local avec `.venv` et VS Code.

## Maintenance immédiate

* [ ] **P1** — Investiguer l'avertissement de dépréciation de l'API `fitz`.
* [ ] **P1** — Vérifier tous les usages de `fitz` avant d'effectuer la migration vers `pymupdf`.
* [ ] **P1** — Vérifier la compatibilité Python 3.14 de l'application et de ses dépendances.
* [ ] **P1** — Comparer le comportement Python 3.14 local avec Python 3.12 dans Docker.
* [ ] **P2** — Déterminer si `requirements.txt` doit rester la méthode de gestion des dépendances ou évoluer vers `pyproject.toml`.

## Tests / qualité

* [ ] **P1** — Identifier les tests critiques couvrant les traitements métier principaux.
* [ ] **P1** — Ajouter un test de régression pour chaque anomalie fonctionnelle rencontrée.
* [ ] **P2** — Évaluer l'intérêt de migrer tout ou partie de la suite actuelle vers `pytest`.
* [ ] **P2** — Évaluer l'ajout de `ruff` pour le linting et le formatage.

## Données et dépôt

* [x] **P0** — Vérifier qu'aucun secret ou identifiant sensible n'est actuellement suivi par Git (audit de publication, novembre 2026 ; `gitleaks` à l'étape finale).
* [ ] **P1** — Vérifier que le `.gitignore` correspond effectivement aux données qui doivent être versionnées.
* [ ] **P1** — Examiner les fichiers `.bak`, logs et autres artefacts présents ou générés sous `data/`.
* [ ] **P1** — Documenter clairement quelles données de `data/` sont des sources et lesquelles sont générées.
* [ ] **P2** — Définir une stratégie d'archivage des anciennes données.

## Application et architecture

* [ ] **P2** — Documenter les principaux modules du package `chauffeur`.
* [ ] **P2** — Documenter les dépendances et l'ordre d'exécution des scripts sous `scripts/`.
* [ ] **P3** — Évaluer la création d'un point d'entrée CLI unique pour les traitements courants.

## Fonctionnel

* [ ] **P1** — Recenser les améliorations fonctionnelles déjà envisagées mais non documentées.
* [ ] **P1** — Classer les besoins fonctionnels selon leur valeur métier.
* [ ] **P2** — Identifier les traitements manuels qui pourraient être automatisés.
* [ ] **P2** — Identifier les améliorations prioritaires de l'interface Streamlit.

---

# 17. Backlog — idées

Cette section contient les idées qui ne sont pas encore suffisamment définies pour devenir des tâches.

* [ ] **P3** — ...
* [ ] **P3** — ...
* [ ] **P3** — ...

---

# 18. Historique des décisions

## 2026-08-30

* L'environnement Python local est basé sur le `.venv` du projet.
* Docker conserve Python 3.12 comme environnement de production.
* VS Code doit utiliser l'interpréteur `.venv` propre au projet.
* L'application Streamlit est lancée par VS Code via `python -m streamlit`.
* Le serveur Streamlit du mode debug VS Code est lié à `127.0.0.1`.
* L'avertissement concernant `fitz` est suivi dans le TODO plutôt que corrigé immédiatement.
* `.vscode/` et `.venv/` restent des éléments locaux exclus du dépôt Git.
