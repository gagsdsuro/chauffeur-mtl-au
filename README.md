# chauffeur-stm

Dépôt de données d'itinéraires d'autobus de la STM (Montréal) + scripts d'import
et génération de rapports. Langue de travail : français.
Voir `CLAUDE.md` pour la spécification détaillée des formats et des commandes.
Le format JSON des événements est documenté dans
[`docs/format-evenements.md`](docs/format-evenements.md); les exemples prêts à
adapter se trouvent dans [`docs/gabarits/`](docs/gabarits/).

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
| `requests` | imports GTFS/GTFS-RT et imports automatiques journée/G-D/événements depuis le portail STM |
| `pymupdf` (importé sous le nom `fitz`) | annotation des cartes agent (`scripts/carte_agent_stm.py`), tests `test_carte_agent.py`/`test_rapport_evenements.py` et outil `creer_cas_test.py` |
| `reportlab` | PDF des rapports v1/v2 (`scripts/gen_rapport.py`, `gen_rapport_v2.py`) et tests `test_rapport.py`/`test_rapport_evenements.py` |

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

Dans « Préparation d'une journée », une session employé STM valide permet de
récupérer automatiquement la journée sélectionnée, ses G-D manquants ou périmés
et ses événements. Les trois imports manuels restent disponibles en secours.

## Tests

```bash
python3 tests/run_all.py     # toute la suite — à lancer avant déploiement
python3 tests/test_depots.py # une suite isolée = script direct (PAS pytest)
```

Sans `pymupdf`/`reportlab`, les suites concernées échouent à l'import
(`test_carte_agent.py`, `test_rapport.py`) ; toutes les autres sont hermétiques
et ne requièrent aucune dépendance externe.
