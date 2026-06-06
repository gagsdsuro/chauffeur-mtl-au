# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vue d'ensemble

`chauffeur-stm` est un dépôt de **données** d'itinéraires d'autobus de la STM (Montréal) destinées aux chauffeurs, accompagnées d'un script Python d'import. Le cœur du projet n'est pas du code applicatif mais un ensemble de fichiers JSON normalisés représentant les parcours « Gauche-Droite » (instructions de conduite virage-par-virage), un par ligne et par direction.

La langue de travail est le **français** (noms de champs, messages, documentation).

## Commandes

Le script d'import lit les données brutes depuis **stdin** et écrit/met à jour les fichiers JSON correspondants dans `data/Gauche-Droite/` :

```bash
python3 scripts/parse_gd.py < data/raw/new-gd.txt          # importe et écrit les fichiers
python3 scripts/parse_gd.py --json < data/raw/new-gd.txt   # idem + imprime le JSON complet sur stdout
```

- Aucune dépendance externe (stdlib uniquement : `re`, `json`, `argparse`, `pathlib`). Pas de build, pas de lint configuré, pas de suite de tests.
- Le script résout les chemins via `Path(__file__).parent.parent` ; il fonctionne donc peu importe le répertoire courant. La sortie va toujours dans `data/Gauche-Droite/` à la racine du dépôt.
- Code de sortie : `0` si tout réussit, `1` si une section échoue (erreurs imprimées sur stderr).

## Architecture

### Flux de données

```
data/raw/*.txt  ──(parse_gd.py)──►  data/Gauche-Droite/gd<ligne>_<direction>.json
   (collé depuis              (normalisé, indent=2, ensure_ascii=False)
    l'interface STM)
```

1. **`split_sections()`** découpe l'entrée brute en sections, une par en-tête `Gauche-Droite / <ligne> <direction>`. Un seul collage peut donc contenir plusieurs lignes/directions.
2. **`GDParser`** traite une section :
   - `_extract_header` : lit ligne (ex. `195`, `85e`) et direction (`est|ouest|nord|sud`).
   - `_parse_parcours` / `_parse_single_parcours` : découpe par blocs `Parcours <nom>ID <n>`. Les **stations** sont les lignes terminées par un code STM à 5 chiffres (première = départ, dernière = arrivée) ; les **directions** sont les lignes `Gauche|Droite|Via - <rue>`. Les lignes `Imprimer` et `Date de mise à jour` sont ignorées (`SKIP_PATTERNS`).
   - `_load_existing_file` + `_generate_summary` : **diff intelligent** contre le fichier existant. Les parcours sont appariés par couple `(start_code, end_code)`, pas par `id` — c'est ainsi que le rapport détecte les ajouts (`+NOUVEAU`), suppressions (`-SUPPRIME`) et modifications (nom, nombre/contenu des directions).
   - `_save_file` écrase le fichier cible ; `_print_report` imprime le rapport lisible.

### Format des fichiers de sortie

Racine : `{ ligne, direction, routes: [ { line_number, direction, parcours: [...] } ] }`. La `direction` à la racine est en **minuscule** (`est`) ; celle dans `routes[]` est **capitalisée** (`Est`). Chaque parcours a `id, name, start, start_code, end, end_code, direction[]`, où `direction[]` est une séquence d'instructions GPS `"Via - <rue>"`, `"Gauche - <rue>"`, `"Droite - <rue>"`.

### Documentation du format de données

`data/Gauche-Droite/CLAUDE.md` est la **spécification détaillée** du format JSON (convention de nommage, sémantique des champs, règles de normalisation, FAQ, exemples). La consulter avant d'éditer manuellement un fichier de données. Note : elle documente le nom de fichier comme `{ligne}_{direction}.json` alors que le script et les fichiers réels utilisent le préfixe `gd` → `gd<ligne>_<direction>.json`.

`data/Gauche-Droite/GABARIT_NOUVEAU_FICHIER.json` est le gabarit pour créer un fichier à la main.

## Conventions

- Noms de fichiers de données : `gd<ligne>_<direction>.json`, direction en minuscule (`est|ouest|nord|sud`), ligne avec `e` minuscule si applicable (`85e`). Un fichier par direction (jamais combiner deux directions).
- JSON écrit avec indentation 2 espaces et accents préservés (`ensure_ascii=False`).
- Préférer l'import via `parse_gd.py` à l'édition manuelle, pour garantir la normalisation et le rapport de changements.
