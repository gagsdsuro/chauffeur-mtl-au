# chauffeur-stm

Dépôt de données d'itinéraires d'autobus de la STM (Montréal) + scripts d'import
et génération de rapports. Langue de travail : français.
Voir `CLAUDE.md` pour la spécification détaillée des formats et des commandes.

## Installation

L'image de production est basée sur Python 3.12 (`Dockerfile`). Les dépendances
sont listées dans `requirements.txt` (même liste qu'installe le Dockerfile) :

```bash
sudo apt install python3-pip
python3 -m venv .venv && source .venv/bin/activate   # venv recommandé
pip install -r requirements.txt
```

Sur Debian/Ubuntu avec le Python système, pip exige l'option
`--break-system-packages` (convention déjà reprise par les messages d'erreur du
dépôt, ex. `gen_rapport.py`) :

```bash
pip install --break-system-packages -r requirements.txt
```

| Paquet | Requis par |
|---|---|
| `streamlit` | l'app (`app/ui.py`) |
| `requests` | imports GTFS/GTFS-RT (`scripts/fetch_gtfs*.py`) et portail STM (`chauffeur/portail.py`) |
| `pymupdf` (importé sous le nom `fitz`) | annotation des cartes agent (`scripts/carte_agent_stm.py`), tests `test_carte_agent.py` et outil `creer_cas_test.py` |
| `reportlab` | PDF des rapports v1/v2 (`scripts/gen_rapport.py`, `gen_rapport_v2.py`) et test `test_rapport.py` |

Remarques :

- Le flux GTFS-RT est décodé par un analyseur wire-format minimal
  (`chauffeur/gtfs_rt.py`) : **aucune dépendance protobuf n'est requise**.
- `pandas` (utilisé ponctuellement par l'app) est installé transitivement via
  streamlit ; rien à faire.
- `openpyxl` n'est requis que par le script ponctuel
  `scripts/import_journees_historique.py`.

## Lancer

```bash
streamlit run app/ui.py      # développement local
docker compose up --build    # production (port 8501, volume ./data)
```

## Tests

```bash
python3 tests/run_all.py     # toute la suite — à lancer avant déploiement
python3 tests/test_depots.py # une suite isolée = script direct (PAS pytest)
```

Sans `pymupdf`/`reportlab`, les suites concernées échouent à l'import
(`test_carte_agent.py`, `test_rapport.py`) ; toutes les autres sont hermétiques
et ne requièrent aucune dépendance externe.
