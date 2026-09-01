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

* [ ] **P2** — Vérifier si les versions minimales de `requirements.txt` sont encore appropriées.

* [ ] **P2** — Décider si les dépendances doivent être figées (`requirements.lock` ou équivalent).

* [ ] **P2** — Vérifier les dépendances transitives utilisées implicitement par l'application.

  * Notamment `pandas`, actuellement fourni transitivement par Streamlit.

* [ ] **P2** — Évaluer l'ajout d'un `pyproject.toml` pour moderniser la gestion du projet Python.

## Code

* [ ] **P2** — Identifier et supprimer les éventuels fichiers ou modules obsolètes.
* [ ] **P2** — Rechercher les `TODO` / `FIXME` / `HACK` présents dans le code.
* [ ] **P2** — Vérifier les imports inutilisés.
* [ ] **P2** — Uniformiser progressivement le typage Python.
* [ ] **P2** — Évaluer l'utilisation de `ruff` pour le linting et le formatage.
* [ ] **P3** — Évaluer l'utilisation de `mypy` ou d'un autre type checker.

---

# 2. Tests et qualité

## Suite de tests

* [ ] **P1** — Vérifier que `python tests/run_all.py` passe complètement dans `.venv`.
* [ ] **P1** — Vérifier les tests avec la version Python utilisée par Docker.
* [ ] **P1** — Identifier les tests critiques couvrant les traitements métier principaux.
* [ ] **P1** — Identifier et documenter les tests les plus importants.
* [ ] **P1** — Ajouter un test de régression lorsqu'un bug est corrigé.
* [ ] **P1** — Vérifier la reproductibilité des tests sur une nouvelle installation.

## Automatisation

* [ ] **P1** — Créer une tâche VS Code pour exécuter toute la suite.
* [ ] **P2** — Créer des tâches VS Code pour les suites principales.
* [ ] **P2** — Ajouter éventuellement une commande unique de validation avant commit.
* [ ] **P2** — Évaluer l'ajout d'un script `check.sh` ou équivalent regroupant les validations.
* [ ] **P2** — Évaluer l'intérêt de migrer tout ou partie de la suite actuelle vers `pytest`.

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

* [ ] **P2** — Faire un état des lieux de `app/ui.py`.
* [ ] **P2** — Documenter l'architecture de `app/ui.py`.
* [ ] **P2** — Vérifier la séparation entre logique métier et interface utilisateur.
* [ ] **P2** — Identifier les parties de l'interface qui pourraient être extraites en composants/modules.
* [ ] **P1** — Améliorer les messages d'erreur affichés à l'utilisateur.
* [ ] **P2** — Vérifier les temps de chargement lorsque `data/` devient volumineux.
* [ ] **P2** — Évaluer la mise en cache des données calculées.
* [ ] **P1** — Vérifier le comportement lorsqu'une donnée attendue est absente ou invalide.
* [ ] **P2** — Identifier les améliorations prioritaires de l'interface Streamlit.

---

# 5. Données STM

## GTFS / GTFS-RT

* [ ] **P1** — Documenter précisément le flux d'import GTFS.
* [ ] **P1** — Documenter précisément le flux GTFS-RT.
* [ ] **P1** — Vérifier la gestion des erreurs réseau.
* [ ] **P1** — Vérifier la gestion des réponses invalides ou incomplètes.
* [ ] **P2** — Vérifier la conservation des données historiques.
* [ ] **P2** — Définir une politique de nettoyage et d'archivage des anciennes données.

## Données métier

* [ ] **P1** — Documenter les formats JSON utilisés dans `data/`.
* [ ] **P1** — Documenter les relations entre `Events`, `Gauche-Droite`, `journees`, `reference`, etc.
* [ ] **P1** — Vérifier la cohérence des fichiers de référence.
* [ ] **P2** — Ajouter des validations automatiques des fichiers JSON importants.
* [ ] **P2** — Évaluer un schéma de validation JSON pour les formats stables.

---

# 6. Rapports

## Génération

* [ ] **P2** — Documenter les différences entre les versions de rapports existantes.
* [ ] **P2** — Identifier les générateurs encore utilisés et ceux devenus historiques.
* [ ] **P2** — Uniformiser le nommage des rapports.
* [ ] **P2** — Vérifier la gestion des caractères accentués dans les noms de fichiers.
* [ ] **P1** — Vérifier la génération des PDF sur l'environnement Docker.

## Qualité

* [ ] **P1** — Ajouter des cas de test pour les rapports complexes.
* [ ] **P1** — Vérifier les cas limites concernant les parcours et horaires.
* [ ] **P2** — Comparer automatiquement certains rapports de référence avec les résultats attendus.

---

# 7. Scripts d'import et de traitement

* [ ] **P1** — Documenter les scripts sous `scripts/`.
* [ ] **P1** — Documenter l'ordre d'exécution des scripts lorsqu'un traitement complet est requis.
* [ ] **P1** — Vérifier les dépendances entre scripts.
* [ ] **P2** — Uniformiser les conventions de ligne de commande.
* [ ] **P1** — Ajouter une gestion d'erreur cohérente.
* [ ] **P2** — Vérifier les messages de log.
* [ ] **P3** — Évaluer l'ajout d'un point d'entrée CLI unique pour les opérations courantes.

---

# 8. Gestion des données générées

* [ ] **P1** — Définir clairement quelles données sous `data/` sont des sources.
* [ ] **P1** — Définir quelles données sont générées par les scripts.
* [ ] **P1** — Définir ce qui doit être versionné dans Git.
* [ ] **P1** — Définir ce qui doit rester uniquement sur l'environnement local.
* [ ] **P2** — Examiner les fichiers `.bak`, logs et autres artefacts temporaires.
* [ ] **P2** — Documenter la stratégie d'archivage des données historiques.
* [ ] **P1** — Séparer, lorsque pertinent, les données de développement des données de production.

---

# 9. Docker / déploiement

* [ ] **P1** — Tester `docker compose up --build` sur une installation propre.
* [ ] **P1** — Vérifier que l'UID/GID du conteneur correspond bien à l'utilisateur de l'hôte.
* [ ] **P1** — Vérifier les permissions des fichiers générés dans `data/`.
* [ ] **P1** — Vérifier le healthcheck Streamlit.
* [ ] **P1** — Documenter les variables d'environnement nécessaires.
* [ ] **P0** — Vérifier le traitement sécurisé de `Installation/config/secrets.*`.
* [ ] **P2** — Évaluer une stratégie de versionnement des images Docker.
* [ ] **P1** — Comparer le comportement local Python 3.14 avec Python 3.12 dans Docker.

---

# 10. Sécurité

* [ ] **P0** — Vérifier qu'aucun secret ou identifiant sensible n'est actuellement suivi par Git.
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

* [ ] **P1** — Recenser les fonctionnalités souhaitées mais non encore implémentées.
* [ ] **P1** — Prioriser les améliorations selon leur valeur métier.
* [ ] **P2** — Identifier les traitements manuels pouvant être automatisés.
* [ ] **P2** — Identifier les informations actuellement difficiles à consulter dans l'interface.
* [ ] **P3** — Évaluer les besoins futurs de recherche, filtrage et export.

---

# 14. Dette technique / investigations

* [ ] **P1** — Déterminer si Python 3.14 doit devenir la version officiellement supportée hors Docker.
* [ ] **P1** — Déterminer si Python 3.12 doit également être utilisé pour le développement local afin d'assurer une parité stricte avec Docker.
* [ ] **P2** — Déterminer si le projet doit rester basé sur `requirements.txt` ou évoluer vers `pyproject.toml`.
* [ ] **P2** — Déterminer si pytest est pertinent ou si `tests/run_all.py` doit rester la référence.
* [ ] **P2** — Évaluer l'intérêt d'une CI Git pour automatiser les tests.
* [ ] **P1** — Évaluer une stratégie de séparation entre données de développement et données de production.

---

# 15. Backlog initial

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

* [ ] **P0** — Vérifier qu'aucun secret ou identifiant sensible n'est actuellement suivi par Git.
* [ ] **P1** — Vérifier que le `.gitignore` correspond effectivement aux données qui doivent être versionnées.
* [ ] **P1** — Examiner les fichiers `.bak`, logs et autres artefacts présents ou générés sous `data/`.
* [ ] **P1** — Documenter clairement quelles données de `data/` sont des sources et lesquelles sont générées.
* [ ] **P2** — Définir une stratégie d'archivage des anciennes données.

## Application et architecture

* [ ] **P2** — Faire un état des lieux de `app/ui.py` et des responsabilités qui pourraient être déplacées hors de l'interface.
* [ ] **P2** — Documenter les principaux modules du package `chauffeur`.
* [ ] **P2** — Documenter les dépendances et l'ordre d'exécution des scripts sous `scripts/`.
* [ ] **P3** — Évaluer la création d'un point d'entrée CLI unique pour les traitements courants.

## Fonctionnel

* [ ] **P1** — Recenser les améliorations fonctionnelles déjà envisagées mais non documentées.
* [ ] **P1** — Classer les besoins fonctionnels selon leur valeur métier.
* [ ] **P2** — Identifier les traitements manuels qui pourraient être automatisés.
* [ ] **P2** — Identifier les améliorations prioritaires de l'interface Streamlit.

---

# 16. Backlog — idées

Cette section contient les idées qui ne sont pas encore suffisamment définies pour devenir des tâches.

* [ ] **P3** — ...
* [ ] **P3** — ...
* [ ] **P3** — ...

---

# 17. Historique des décisions

## 2026-08-30

* L'environnement Python local est basé sur le `.venv` du projet.
* Docker conserve Python 3.12 comme environnement de production.
* VS Code doit utiliser l'interpréteur `.venv` propre au projet.
* L'application Streamlit est lancée par VS Code via `python -m streamlit`.
* Le serveur Streamlit du mode debug VS Code est lié à `127.0.0.1`.
* L'avertissement concernant `fitz` est suivi dans le TODO plutôt que corrigé immédiatement.
* `.vscode/` et `.venv/` restent des éléments locaux exclus du dépôt Git.
