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


## Qualité

* [ ] **P1** — Ajouter des cas de test pour les rapports complexes.

---

# 6. Scripts d'import et de traitement

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

* [ ] **P2** — Documenter les formats de données importants.

---

# 11. Git / gestion du projet


---

# 12. Améliorations fonctionnelles

* [ ] **P2** — Identifier les traitements manuels pouvant être automatisés.
* [ ] **P2** — Identifier les informations actuellement difficiles à consulter dans l'interface.

---

# 13. Dette technique / investigations

* [ ] **P1** — Déterminer si Python 3.14 doit devenir la version officiellement supportée hors Docker.
* [ ] **P1** — Déterminer si Python 3.12 doit également être utilisé pour le développement local afin d'assurer une parité stricte avec Docker.
* [ ] **P2** — Déterminer si le projet doit rester basé sur `requirements.txt` ou évoluer vers `pyproject.toml`.

---

# 14. UI
* [ ] **P1** - Réorganisation de la page "Ma journée"

  * Limité le contenu de la liste déroulante "Journée" à [-2, aujourd'hui, +5]
  * Retirer le selecteur "Niveau des rapport". Garder "Détaillé" comme valeur par défaut.
  * Remplacer la section "Préparation de la journée" par une section "Rafraîchir les données du jour"
    * Récupère les évènements pour les ligne restantes du jour.
      * si des changements sont détectés, regénère le rapport v2
  * Retirer les bouton "Carte annotée", "Rapport journlier" et "Rapport V2 standard"
  * Garder l'aperçu du dernier rapport v2
  * Garder la section "Pièces de travail" tel quel. 

* [ ] **P1** - Réorganisation de la section import pour devenir "Préparation d'une journée"

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
