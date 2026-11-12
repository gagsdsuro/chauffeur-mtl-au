# Dépendances et mises à jour

La référence de déploiement est **Python 3.12.16 / Streamlit 1.66.1**.
Le verrouillage fixe les dépendances d'une livraison ; il est mis à jour
explicitement pour profiter des nouvelles versions.

## Fichiers de référence

| Fichier | Rôle |
| --- | --- |
| `requirements.in` | Dépendances directes ; version exacte de Streamlit et contraintes des autres paquets |
| `requirements.txt` | Généré par pip-tools sous Linux / Python 3.12 ; versions exactes et empreintes SHA-256 de toutes les dépendances Python |
| `Dockerfile` | Python 3.12.16 et empreinte de l'image de base ; installation avec `--require-hashes`, puis `pip check` |

Versionner les deux fichiers de dépendances ensemble. Ne pas modifier le fichier
généré à la main. Les paquets de maintenance (`pip-tools`, etc.) ne sont pas
ajoutés aux dépendances de l'application.

Le décodeur GTFS-RT n'a pas besoin de protobuf ; celui-ci apparaît toutefois
dans le verrouillage comme dépendance de Streamlit.

## Installer l'environnement de développement

Depuis la racine du dépôt, avec Python 3.12 installé :

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python tests/run_all.py
.venv/bin/python -m streamlit run app/main.py
```

La référence est Linux / Python 3.12, comme Docker. Ne pas régénérer le
verrouillage de production depuis Python 3.14 ou depuis un autre système.
Un poste sans Python 3.12 peut utiliser Docker. L'installation verrouillée ne
modifie pas automatiquement le Python ou les paquets déjà installés sur l'hôte.

## Mettre à jour les dépendances

Créer une branche dédiée, par exemple `maintenance/maj-streamlit`, puis travailler
depuis la racine dans un environnement Linux / Python 3.12.
Préparer l'outil de génération dans un environnement séparé :

```bash
python3.12 -m venv .venv-outils
.venv-outils/bin/python -m pip install pip==25.3 pip-tools==7.5.2
```

Pour changer Streamlit, modifier d'abord sa version exacte dans
`requirements.in`. Générer ensuite le nouveau verrouillage :

```bash
.venv-outils/bin/python -m piptools compile \
  --generate-hashes --strip-extras \
  --no-emit-index-url --no-emit-trusted-host \
  --output-file requirements.txt requirements.in
```

Le fichier existant sert de référence : les versions compatibles sont conservées.
Pour demander une mise à jour ciblée, ajouter par exemple
`--upgrade-package requests`. Pour une revue de toutes les dépendances, ajouter
`--upgrade` ; la version exacte de Streamlit reste contrainte par
`requirements.in`. Les dépendances indirectes peuvent également changer si la
résolution l'exige. [Fonctionnement de pip-tools](https://pip-tools.readthedocs.io/en/latest/#updating-requirements).

Lire le diff de `requirements.txt`, les notes de version des paquets modifiés
et les avertissements de dépréciation. Tester la nouvelle résolution dans un
environnement vierge : installer par-dessus des paquets existants ne vérifie
pas l'absence de dépendances manquantes.

Une mise à jour de Python nécessite aussi de modifier le tag et l'empreinte
`FROM` du Dockerfile, puis de régénérer et tester les dépendances avec cette
version. Les mises à jour des outils de génération sont explicites également.

## Valider une livraison

Construire une image avec le Dockerfile et le verrouillage candidats, sans
monter les données personnelles pour les tests. Le Dockerfile de production
ne copie pas `tests/` : monter une copie isolée du dépôt pour y lancer
`python tests/run_all.py` avec le Python de l'image. Inclure uniquement le code,
les tests, le Dockerfile et `data/reference/`, sans `.env`, `Installation/`
ni données privées.

Critères de validation :

- Installation avec vérification des empreintes et `python -m pip check` réussis.
- Versions Python et Streamlit conformes ; toutes les suites de régression passent.
- Démarrage Streamlit et réponse `ok` de `/_stcore/health`.
- Essais navigateur sur données de test : connexion/déconnexion, navigation,
  saisie d'une date historique, changement d'autobus avec sa note, imports,
  aperçu et téléchargement des rapports, dialogue de session et reprise.
- Vérification sur téléphone du clavier, des menus et de la disposition.

Une sonde HTTP ou une ouverture de page par AppTest ne valide pas à elle seule
les interactions navigateur, les cookies du portail employé ou le rendu mobile.
Les étapes et la fiche de résultats réutilisable sont dans la
[recette navigateur/mobile](recette-navigateur-mobile.md).

Attribuer à l'image validée un tag de livraison distinct et conserver son
identifiant ou son digest. Déployer cette même image sans la reconstruire entre
les tests et le déploiement. Conserver l'image précédente pour revenir en arrière.
Ce verrouillage couvre Python et ses paquets ; les paquets système installés par
`apt` restent résolus au moment de la construction, d'où l'intérêt de conserver
l'image finale testée.

## Rythme de maintenance

- Revue mensuelle des dépendances et de l'image Python.
- Mise à jour ciblée dès qu'une nouveauté devient utile au développement.
- Correctif de sécurité pertinent traité rapidement.
- En cas de blocage, inscrire dans `TODO.md` la version essayée, le problème et
  la condition pour réessayer ; conserver le verrouillage fonctionnel.

Les versions évoluent par une modification revue des fichiers de dépendances,
suivie des validations. Une reconstruction ordinaire n'effectue pas de mise à
jour Python implicite.
