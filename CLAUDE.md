# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vue d'ensemble

`chauffeur-stm` est un dépôt de **données** d'itinéraires d'autobus de la STM (Montréal) destinées aux chauffeurs, accompagnées de scripts Python d'import et de génération de rapports. Le cœur du projet est un ensemble de fichiers JSON normalisés : parcours « Gauche-Droite » (instructions de conduite virage-par-virage) et événements affectant les arrêts.

La langue de travail est le **français** (noms de champs, messages, documentation).

## Commandes

**Import Gauche-Droite** — lit depuis stdin, écrit dans `data/Gauche-Droite/` :
```bash
python3 scripts/parse_gd.py < data/raw/new-gd.txt          # importe et écrit les fichiers
python3 scripts/parse_gd.py --json < data/raw/new-gd.txt   # idem + imprime le JSON complet sur stdout
```

**Import Événements** — lit depuis stdin, écrit dans `data/Events/` :
```bash
python3 scripts/parse_event.py < data/raw/new-events.txt
python3 scripts/parse_event.py --json < data/raw/new-events.txt
```

**Rapport journalier** — PDF recto-verso prêt à imprimer (G-D + détours filtrés) :
```bash
python3 scripts/gen_rapport.py                          # rapport du jour
python3 scripts/gen_rapport.py --date 2026-06-05        # date spécifique
python3 scripts/gen_rapport.py --output /tmp/out.pdf    # chemin de sortie
```

**Annotation carte agent** — annote le PDF de carte agent avec les horaires GTFS (requiert `PyMuPDF`) :
```bash
python3 scripts/carte_agent_stm.py --pdf data/ca/carte-agent-2026-06-04.pdf --out data/ca/annotée.pdf --gtfs data/gtfs/gtfs_stm/ --date 2026-06-04
```

**Téléchargement GTFS** — données statiques (hebdomadaire) et temps-réel (requiert `requests`) :
```bash
python3 scripts/fetch_gtfs.py
python3 scripts/fetch_gtfs_rt.py
```

- `parse_gd.py` et `parse_event.py` n'ont aucune dépendance externe (stdlib uniquement). Les autres scripts requièrent `requests` et/ou `PyMuPDF (fitz)`.
- Tous les scripts résolvent les chemins via `Path(__file__).parent.parent` ; ils fonctionnent peu importe le répertoire courant.
- Code de sortie : `0` si tout réussit, `1` si une section échoue (erreurs sur stderr).

## Architecture

### Flux de données

```
data/raw/*.txt  ──(parse_gd.py)────►  data/Gauche-Droite/gd<ligne>_<direction>.json
                ──(parse_event.py)──►  data/Events/<ligne>_<direction>.json
data/gtfs/      ──(fetch_gtfs.py)──►  data/gtfs/gtfs_stm/   (données statiques)
data/ca/*.pdf   ──(carte_agent_stm.py + GTFS)──►  PDF annoté
                ──(gen_rapport.py)──►  data/rapports/rapport-<date>.pdf
```

1. **`split_sections()`** découpe l'entrée brute en sections, une par en-tête `Gauche-Droite / <ligne> <direction>`. Un seul collage peut donc contenir plusieurs lignes/directions.
2. **`GDParser`** traite une section :
   - `_extract_header` : lit ligne (ex. `195`, `85e`) et direction (`est|ouest|nord|sud`).
   - `_parse_parcours` / `_parse_single_parcours` : découpe par blocs `Parcours <nom>ID <n>`. Les **stations** sont les lignes terminées par un code STM à 5 chiffres (première = départ, dernière = arrivée) ; les **directions** sont les lignes `Gauche|Droite|Via - <rue>`. Les lignes `Imprimer` et `Date de mise à jour` sont ignorées (`SKIP_PATTERNS`).
   - `_load_existing_file` + `_generate_summary` : **diff intelligent** contre le fichier existant. Les parcours sont appariés par couple `(start_code, end_code)`, pas par `id` — c'est ainsi que le rapport détecte les ajouts (`+NOUVEAU`), suppressions (`-SUPPRIME`) et modifications (nom, nombre/contenu des directions).
   - `_save_file` écrase le fichier cible ; `_print_report` imprime le rapport lisible.

### Format des fichiers de sortie

Racine : `{ ligne, direction, routes: [ { line_number, direction, parcours: [...] } ] }`. La `direction` à la racine est en **minuscule** (`est`) ; celle dans `routes[]` est **capitalisée** (`Est`). Chaque parcours a `id, name, start, start_code, end, end_code, direction[]`, où `direction[]` est une séquence d'instructions GPS `"Via - <rue>"`, `"Gauche - <rue>"`, `"Droite - <rue>"`.

### Documentation des formats de données

- `data/Gauche-Droite/CLAUDE.md` — spécification détaillée du format JSON G-D (nommage, sémantique, FAQ). Note : elle documente `{ligne}_{direction}.json` mais les fichiers réels utilisent le préfixe `gd` → `gd<ligne>_<direction>.json`.
- `data/Gauche-Droite/GABARIT_NOUVEAU_FICHIER.json` — gabarit pour créer un fichier G-D manuellement.
- `data/Events/CLAUDE.md` — spécification détaillée du format JSON des événements (champs `evenement_id`, `titre`, `motif`, `effectif`, `arrets_annules`, `arrets_ajoutes`, dates ISO 8601). Nommage : `{ligne}_{direction}.json` (sans préfixe, contrairement aux G-D).
- `data/Events/GABARIT_NOUVEAU_FICHIER.json` — gabarit pour créer un fichier d'événements manuellement.

## Conventions

- **Gauche-Droite** : `gd<ligne>_<direction>.json` (avec préfixe `gd`), direction en minuscule (`est|ouest|nord|sud`), ligne avec `e` minuscule si applicable (`85e`). Un fichier par direction.
- **Événements** : `<ligne>_<direction>.json` (sans préfixe), même convention de direction/ligne.
- **Cartes agent** : `data/ca/carte-agent-YYYY-MM-DD.pdf` (PDF source), rapports annotés dans le même dossier.
- **Rapports journaliers** : `data/rapports/rapport-YYYY-MM-DD.pdf`.
- JSON écrit avec indentation 2 espaces et accents préservés (`ensure_ascii=False`).
- Préférer l'import via les scripts à l'édition manuelle, pour garantir la normalisation et le rapport de changements.
