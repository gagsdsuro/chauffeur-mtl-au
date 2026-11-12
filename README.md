# Chauffeur Mtl-AU

## Présentation de l'application

**Chauffeur Mtl-AU** (Chauffeur Montréal Autobus Urbain) accompagne les chauffeurs d'autobus urbain à Montréal dans la préparation
et le suivi de leur journée de travail. Elle répond au besoin de regrouper des
informations dispersées, de repérer les changements touchant les parcours et de
disposer de documents pratiques, à jour et faciles à consulter.

Ses principales fonctions sont :

- **Préparer la journée** : récupérer les affectations, les itinéraires
  Gauche-Droite et les événements pertinents.
- **Obtenir un itinéraire adapté à la journée** : produire à la demande un parcours
  intégrant les événements applicables, pour repérer directement les perturbations
  aux endroits concernés et préparer son trajet plus rapidement.
- **Produire les documents de travail** : annoter la carte agent et générer des
  rapports consultables ou imprimables.
- **Suivre les changements** : actualiser les événements avant le départ et pendant
  les pauses, puis consulter les informations utiles aux lignes à effectuer.
- **Faciliter les prises de relève** : localiser le prochain autobus à récupérer
  lorsque les données sont accessibles.
- **Entretenir les données** : vérifier leur ancienneté, retirer les fichiers
  obsolètes et consulter les journaux d'activité.

Pour le chauffeur, les bénéfices attendus sont un **gain de temps de préparation**,
moins de recherches et de manipulations manuelles, ainsi qu'une **meilleure
anticipation des perturbations**. L'itinéraire intégrant les événements évite de
croiser soi-même plusieurs sources pour comprendre leur incidence sur le parcours.
L'accès sur téléphone et les documents imprimables permettent d'adapter la
consultation aux différents moments de la journée.

Une **fonction future** vise également à faciliter la sélection des journées selon
les préférences des chauffeurs Réserve et RFLEX et à produire la note spécifique de
réserve.

Les scénarios détaillés sont décrits dans les [cas d'utilisation](USECASES.md).

## Avis important

Projet **indépendant**, non affilié à la STM ni approuvé par elle ni par aucun employeur.
L'information produite (G-D, événements, horaires, rapports) provient de sources tierces,
**sans garantie d'exactitude ni de disponibilité** : elle ne remplace pas les consignes
officielles. **Chaque utilisateur est responsable de sa connexion à `employe.stm.info`
et doit se conformer aux règles de son organisation.** Détails, attribution des données
ouvertes et limitation de responsabilité : [NOTICE.md](NOTICE.md).

> Contient des données de la Société de transport de Montréal (STM), offertes sous licence
> CC BY 4.0 (<https://www.stm.info/a-propos/documents-donnees/donnees-ouvertes>).
> Projet indépendant, non officiel et non cautionné par la STM.

## Données requises (non fournies)

Le dépôt ne contient aucune donnée d'exploitation :

- **GTFS statique** : `python3 scripts/fetch_gtfs.py` (données ouvertes, sans clé).
- **GTFS temps réel** (optionnel) : clé personnelle du portail des développeurs de la STM, à placer
  dans `Installation/config/secrets.json` (clé `stm_api_key_rt`, gabarit : `docs/gabarits/secrets.json`, à copier vers `Installation/config/secrets.json`)
  ou dans la variable `STM_API_KEY_RT`. Chaque utilisateur utilise sa propre clé.
- **Références locales** (optionnelles) : points de relève, garages et stations de métro, à créer dans
  `data/reference/` à partir des gabarits fictifs de `docs/gabarits/reference/` (fichiers non versionnés).
- **Journées, G-D, événements, cartes agent** : récupérés par chaque utilisateur depuis le portail
  employé avec sa propre session, ou collés manuellement (voir « Préparation d'une journée »).

## Documentation technique

Dépôt de données d'itinéraires d'autobus urbains (Montréal) + scripts d'import
et génération de rapports. Langue de travail : français.
Voir `CLAUDE.md` pour la spécification détaillée des formats et des commandes.
Le format JSON des événements est documenté dans
[`docs/format-evenements.md`](docs/format-evenements.md); les exemples prêts à
adapter se trouvent dans [`docs/gabarits/`](docs/gabarits/).

## Installation

La référence de déploiement est **Python 3.12.16 et Streamlit 1.66.1**.
Le Dockerfile fixe l'image Python par son empreinte. Les dépendances directes
sont déclarées dans `requirements.in` ; `requirements.txt` est généré sous
Python 3.12 et verrouille toutes les dépendances avec leurs empreintes.
Utiliser Python 3.12 pour reproduire cet environnement en développement :

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.txt
python -m pip check
```

Sur Debian/Ubuntu avec le Python système, pip exige l'option
`--break-system-packages` (convention déjà reprise par les messages d'erreur du
dépôt, ex. `gen_rapport.py`) :

```bash
python3.12 -m pip install --break-system-packages --require-hashes -r requirements.txt
```

| Paquet | Requis par |
|---|---|
| `streamlit` | l'app (`app/main.py` + pages dans `app/pages/`) |
| `requests` | imports GTFS/GTFS-RT et imports automatiques journée/G-D/événements depuis le portail employé |
| `pymupdf` | annotation des cartes agent (`scripts/carte_agent.py`), tests `test_carte_agent.py`/`test_rapport_evenements.py` et outil `creer_cas_test.py` |
| `reportlab` | PDF des rapports v1/v2 (`scripts/gen_rapport.py`, `gen_rapport_v2.py`) et tests `test_rapport.py`/`test_rapport_evenements.py` |

Remarques :

- Ne pas modifier `requirements.txt` à la main. La [procédure de mise à jour](docs/dependances.md)
  décrit la génération, les tests et la revue mensuelle des nouvelles versions.
- Le flux GTFS-RT est décodé par un analyseur wire-format minimal
  (`chauffeur/gtfs_rt.py`) : **aucune dépendance protobuf n'est requise**.
- `pandas` (utilisé ponctuellement par l'app) est installé transitivement via
  streamlit ; rien à faire.
- `openpyxl` n'est requis que par le script ponctuel
  `scripts/import_journees_historique.py`.

## Lancer

```bash
streamlit run app/main.py      # développement local
docker compose up --build    # production (port 8501, volume ./data)
```

Dans « Préparation d'une journée », une session du portail employé valide permet de
récupérer automatiquement la journée sélectionnée, ses G-D manquants ou périmés
et ses événements. Les trois imports manuels restent disponibles en secours.

### Authentification locale (PIN) et matricule

Dès qu'un compte existe dans `data/users.json` (créé par l'app ou
`chauffeur.auth`), l'app demande un **PIN** (4-8 chiffres) au démarrage de
chaque session navigateur. Sans compte, l'app garde son comportement legacy.

Chaque compte a un rôle : **Chauffeur** ou **Chauffeur-admin** (le premier
compte créé est Chauffeur-admin). Un Chauffeur change son propre PIN depuis la
barre latérale ; le menu **Administration** (réservé aux Chauffeur-admin)
permet de créer des comptes, promouvoir/destituer, réinitialiser un PIN et
déverrouiller ou révoquer un compte.

Par défaut, les données personnelles sont isolées dans `data/<matricule>/` dès
que `CHAUFFEUR_MATRICULE` (5 chiffres) est défini — sinon dans `data/`. En
mode strict (`CHAUFFEUR_MODE_STRICT=1`), le matricule est **obligatoire** :
l'app exige la connexion (assistant de premier lancement sans compte) et les
scripts échouent avec une erreur claire s'il manque. La flotte (G-D, événements,
GTFS) reste partagée, hors de ces répertoires.

## Tests

```bash
python3 tests/run_all.py     # toute la suite — à lancer avant déploiement
python3 tests/test_depots.py # une suite isolée = script direct (PAS pytest)
```

Sans `pymupdf`/`reportlab`, les suites concernées échouent à l'import
(`test_carte_agent.py`, `test_rapport.py`) ; toutes les autres sont hermétiques
et ne requièrent aucune dépendance externe.

La page [Fichiers](docs/fichiers.md) permet la recherche par période (liste), les aperçus,
l’édition des JSON autorisés et l’export CSV des journées.

## Licence

Code publié sous [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0). Si vous modifiez
l'application et la mettez à disposition d'autres personnes sur un réseau, vous devez leur offrir
le code source de votre version. Licences des dépendances : [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Contributions : [CONTRIBUTING.md](CONTRIBUTING.md) · Sécurité : [SECURITY.md](SECURITY.md).
