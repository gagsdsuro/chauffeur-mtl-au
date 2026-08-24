# AGENTS.md

Dépôt de données d'itinéraires d'autobus de la STM (Montréal) + scripts d'import et rapports. **Langue de travail : français** — noms de champs JSON, messages, doc en français. Voir `CLAUDE.md` (à la racine) pour la spécification détaillée des formats et commandes ; ce fichier ne résume que ce qu'on rate facilement.

## Commandes

```bash
streamlit run app/ui.py                     # app locale
docker compose up --build                   # prod, port 8501, volume ./data

python3 tests/test_*.py                     # chaque suite = script direct, PAS pytest
python3 tests/run_all.py                    # toute la suite, avant déploiement
python3 tests/test_dockerfile.py            # garde-fou : Dockerfile copie tout package source

python3 scripts/parse_gd.py       < data/raw/new-gd.txt   # import G-D depuis stdin
python3 scripts/parse_event.py    < data/raw/new-events.txt
python3 scripts/parse_journee.py  --date 2026-06-18 < raw.txt
```

- Aucun framework de test/lint/typecheck configuré (pas de pyproject/pytest). Vérifier par `python3 -m py_compile <fichier>` + les suites de régression.
- Les importeurs **lisent depuis stdin** (pas d'argument fichier). Options : `--json` (imprime le JSON), `--log` (écrit dans `data/log/<source>.log`). Depuis l'app, `--log` est toujours actif.
- Dépendances dans `requirements.txt` (installées par le Dockerfile) : en local, `pip install -r requirements.txt` (ajouter `--break-system-packages` sur un Python système Debian/Ubuntu). Quelques suites requièrent `pymupdf` (cartes agent) ou `reportlab` (rapport v1) ; `requests` pour GTFS/GTFS-RT et le portail — **pas de dépendance protobuf**. Détail : `README.md` et section « Dépendances » de `CLAUDE.md`.

## Architecture (à ne pas se tromper)

- `chauffeur/` = noyau de domaine partagé (app + scripts) : `depots.py` (source unique des chemins/conventions de nommage), `gd.py`, `evenements.py`, `gtfs.py`, `periodes.py`, `ca.py`, `journal.py`, etc. **Toute logique va dans `chauffeur/`**, pas dans l'app.
- `app/ui.py` = un seul fichier de présentation Streamlit (5 onglets), sans logique.
- `scripts/*.py` = CLI autonomes.
- Les scripts résolvent les chemins via `Path(__file__).parent.parent` : ils fonctionnent **indépendamment du répertoire courant**. Ne pas supposer que cwd == racine ; ne jamais utiliser de chemins relatifs à cwd.

## Conventions de nommage des fichiers

- G-D : `data/Gauche-Droite/gd<ligne>_<direction>.json` (préfixe `gd`, direction **minuscule**, ligne avec `e` si applicable, ex. `gd85e_ouest.json`).
- Événements : `data/Events/<ligne>_<direction>.json` (**sans** préfixe).
- Journées : `data/journees/journee-YYYY-MM-DD.json` ; rapports v2 : `data/rapports/rapport-v2-DATE.*`.
- JSON écrit avec indentation 2 et `ensure_ascii=False` (accents préservés). Ne pas traduire/renommer les champs.

## Pièges opérationnels

- `data/` est **gitignoré** (seul `data/reference/` est versionné) : ne pas committer de données, journaux, cookies de session (`data/session/cookies.json`).
- **Le Dockerfile ne copie que `app/`, `scripts/`, `chauffeur/`.** Ajouter un nouveau package de premier niveau sans le déclarer casse la prod (`ModuleNotFoundError`) — d'où `test_dockerfile.py`.
- Déploiement Docker : UID/GID alignés sur l'hôte via args pour que les fichiers écrits dans `./data` n'appartiennent pas à root.
- Les tests de régression (cartes agent, rapport, G-D) rejouent des **cas figés** dans `tests/cas*/<nom>/` (PDF/JSON gelés) — hermétiques, sans le gros GTFS. Un nouveau cas se fige via `tests/creer_cas_*.py` ; **vérifier `attendu.json` avant de committer**.
- GTFS statique volumineux ; `chauffeur.gtfs.stops_for_line()` lit `stops_index.json` (~80x plus rapide qu'un scan CSV), avec repli automatique si absent.
- Prendre comme source de vérité les scripts exécutables : si `CLAUDE.md` et le code divergent, le code l'emporte.
