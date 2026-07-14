# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vue d'ensemble

`chauffeur-stm` est un dépôt de **données** d'itinéraires d'autobus de la STM (Montréal) destinées aux chauffeurs, accompagnées de scripts Python d'import et de génération de rapports. Le cœur du projet est un ensemble de fichiers JSON normalisés : parcours « Gauche-Droite » (instructions de conduite virage-par-virage) et événements affectant les arrêts et/ou le parcours.

La langue de travail est le **français** (noms de champs, messages, documentation).

## Commandes

**Lancer l'application Streamlit** :
```bash
streamlit run app/ui.py                     # développement local
docker compose up --build                   # production (port 8501, volume ./data)
```
L'app expose 5 onglets : Ma journée (orchestrateur : sélection unique de journée, checklist de préparation, actions chaînées, consultation par pièce/trajet) · Importation (5 sous-onglets, dont GTFS) · Rapports (2 sous-onglets) · Fichiers (5 sous-onglets, avec purge des fichiers obsolètes) · Logs.

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

**Import Journée** — lit depuis stdin le texte brut « Détail de ma journée », écrit dans `data/journees/` :
```bash
python3 scripts/parse_journee.py --date 2026-06-18 < raw.txt   # date explicite
python3 scripts/parse_journee.py --json < raw.txt              # idem + JSON complet sur stdout
```
La date est auto-détectée depuis le champ « Mis à jour le » si `--date` est absent.

**Rapport journalier v1** — PDF recto-verso prêt à imprimer (G-D + détours filtrés) :
```bash
python3 scripts/gen_rapport.py                          # rapport du jour
python3 scripts/gen_rapport.py --date 2026-06-05        # date spécifique
python3 scripts/gen_rapport.py --output /tmp/out.pdf    # chemin de sortie
```

**Rapport journalier v2** — rapport depuis journée JSON (HTML ou PDF, filtrable par groupe) :
```bash
python3 scripts/gen_rapport_v2.py --journee data/journees/journee-2026-06-18.json
python3 scripts/gen_rapport_v2.py --journee data/journees/journee-2026-06-18.json --format html --niveau standard
python3 scripts/gen_rapport_v2.py --journee data/journees/journee-2026-06-18.json \
    --filtre-ligne 24 --filtre-direction est --filtre-id-parcours 3   # mono-groupe
```
Niveaux : `détaillé` (défaut) | `standard` | `compact`. Sortie par défaut : `data/rapports/rapport-v2-DATE.EXT`.

**Annotation carte agent** — annote le PDF de carte agent avec les horaires GTFS (requiert `PyMuPDF`) :
```bash
python3 scripts/carte_agent_stm.py --pdf data/ca/carte-agent-2026-06-04.pdf --out data/ca/annotée.pdf --gtfs data/gtfs/gtfs_stm/ --date 2026-06-04
```

**Tests de régression carte agent** — rejoue des cas figés (PDF + horaires GTFS gelés dans `tests/cas/<nom>/`) et compare le plan d'annotations à `attendu.json` (requiert `PyMuPDF`) :
```bash
python3 tests/test_carte_agent.py              # tous les cas
python3 tests/test_carte_agent.py carte-449    # un cas précis
python3 tests/creer_cas_test.py --pdf data/ca/carte-agent-2026-06-09.pdf --gtfs data/gtfs/gtfs_stm/   # figer un nouveau cas (vérifier attendu.json avant de committer)
```

**Tests de régression rapport** — rejoue des cas figés (PDF + G-D gelés dans `tests/cas_rapport/<nom>/`) et compare les lignes reconnues et leurs directions G-D appariées à `attendu.json`. Hermétique : `GD_DIR` est redirigé vers le `gd/` du cas (requiert `PyMuPDF`) :
```bash
python3 tests/test_rapport.py                          # tous les cas
python3 tests/test_rapport.py carte-455-2026-06-11     # un cas précis
python3 tests/creer_cas_rapport.py --pdf data/ca/carte-agent-2026-06-11.pdf   # figer un nouveau cas (vérifier attendu.json avant de committer)
```

**Suite complète + garde-fou Docker** — à lancer avant tout déploiement :
```bash
python3 tests/run_all.py        # exécute toutes les suites tests/test_*.py
python3 tests/test_dockerfile.py  # vérifie que le Dockerfile copie tout package source de premier niveau (app/scripts/chauffeur) — évite ModuleNotFoundError en prod
```

**Tests de régression domaine G-D** — rejoue le pipeline (build_rows → annotate → détours) sur des entrées gelées dans `tests/cas_rapport_gd/<nom>/` (G-D + Events + arrêts GTFS, sans dépendre du GTFS volumineux) ; compare rows/added à `attendu.json` :
```bash
python3 tests/test_rapport_gd.py
python3 tests/creer_cas_rapport_gd.py --ligne 125 --direction ouest --date 2026-06-11   # figer un nouveau cas (vérifier attendu.json)
```

**Tests de régression parseurs** — rejoue des collages bruts figés dans `tests/cas_event/`, `tests/cas_gd/` et `tests/cas_journee/` :
```bash
python3 tests/test_parse_event.py     # régression parse_event.py (cas : détour sans annulation, arrêts vides)
python3 tests/test_parse_gd.py        # régression parse_gd.py (cas : multi-parcours même ligne/direction)
python3 tests/test_parse_journee.py   # régression parse_journee.py (cas : sommaire sans bus, placeholders "--"+"--")
```

**Tests unitaires appariement** — couvre `chauffeur.matching` (stations vs rues, parenthèses, REM, troncature) :
```bash
python3 tests/test_matching.py
```

**Tests unitaires journée** — couvre `chauffeur.journee` (`groupes_de_service`, `lignes_de_service`) sur des journées synthétiques inline :
```bash
python3 tests/test_journee.py
```

**Tests unitaires évènements** — couvre `chauffeur.evenements` (`applicable_a_la_date`, `applicable_a_la_plage` : bornes ouvertes, quart franchissant minuit, effectif horaire, replis fail-safe) et la convention `stop_ids=None` de `chauffeur.gd.event_applicable_to_parcours` :
```bash
python3 tests/test_evenements.py
```

**Tests unitaires dépôts** — couvre `chauffeur.depots` (chemins canoniques, `charger_gd` avec sélection par id et replis, `charger_evenements`, `evenements_pour_date`, `charger_journee`, `sauvegarder_journee`, fraîcheur `info_gd`/`info_gtfs`) sur fichiers synthétiques en répertoire temporaire :
```bash
python3 tests/test_depots.py
```

**Tests unitaires effectif** — couvre `chauffeur.effectif.bornes_quart` (liste vide, heure unique, tri par valeur réelle plutôt que lexicale, quart franchissant minuit) :
```bash
python3 tests/test_effectif.py
```

**Tests unitaires GTFS-RT** — couvre `chauffeur.gtfs_rt` (décodage wire-format sur messages synthétiques encodés dans le test, robustesse aux octets invalides, `find_vehicle` avec normalisation xx-xxx) :
```bash
python3 tests/test_gtfs_rt.py
```

**Tests unitaires cartes agent** — couvre `chauffeur.ca` (`resoudre_ca` : identité + repli legacy par date ; `ranger_ca` : collision refusée, remplacement avec `.bak`, mode déjà-annotée) dans un répertoire temporaire :
```bash
python3 tests/test_ca.py
```

**Tests unitaires périodes** — couvre `chauffeur.periodes` (`identite_ca` : liste/semaine/samedi/dimanche, férié isolé dans une semaine de liste, variations multi-semaines, date hors calendrier) :
```bash
python3 tests/test_periodes.py
```

**Test de régression portail** — rejoue un fragment HTML figé (`tests/cas_portail/`) et vérifie la normalisation des événements par `STMEventParser.from_portal_json()`, y compris un `evenement_id` dupliqué sans faux avertissement :
```bash
python3 tests/test_portail.py
```

**Rapport détaillé G-D / Arrêts** — rapport HTML ou Markdown pour une ligne/direction (requiert GTFS) :
```bash
python3 scripts/rapport_gd.py --ligne 195 --direction ouest --date 2026-06-05 --base .
python3 scripts/rapport_gd.py --ligne 24 --direction est --heure-debut 06:00 --heure-fin 14:30
python3 scripts/rapport_gd.py --ligne 125 --direction est --arret-debut 54112 --arret-fin 57365
```
Options clés : `--format html|md`, `--heure-debut`/`--heure-fin` (peut dépasser 24h ex. `25:19`), `--parcours principal|secondaire|école|weekend`, `--arret-debut`/`--arret-fin`. Sortie : `scripts/rapport_<ligne>_<dir>_<date>.html`.

**Rafraîchissement événements depuis le portail STM** — lit depuis `employe.stm.info`, écrit dans `data/Events/` :
```bash
python3 scripts/refresh_events.py --journee data/journees/journee-2026-06-25.json
python3 scripts/refresh_events.py --journee data/journees/journee-2026-06-25.json --restantes
python3 scripts/refresh_events.py --ligne 10 --sens sud
```
Codes de sortie : `0` succès, `1` erreur HTTP/parse, `2` session expirée (renouveler les cookies).
Session : coller la chaîne de cookies (DevTools → Application → Cookies) dans l'UI onglet Importation > Évènements, ou via `chauffeur.portail.save_session()`. Stockée dans `data/session/cookies.json` (gitignorée via `data/`).

**Téléchargement GTFS** — données statiques (hebdomadaire) et temps-réel (requiert `requests`) :
```bash
python3 scripts/fetch_gtfs.py
python3 scripts/fetch_gtfs.py --index-only   # reconstruit stops_index.json sans re-télécharger
python3 scripts/fetch_gtfs_rt.py
```
`fetch_gtfs.py` construit `stops_index.json` après extraction (scan unique de `stop_times.txt`) ; `chauffeur.gtfs.stops_for_line()` lit cet index (~80x plus rapide qu'un scan CSV) avec repli automatique si l'index est absent.

- `parse_gd.py` est stdlib pur. `parse_event.py` et `parse_journee.py` importent `chauffeur.modeles` (stdlib, pas de package externe). Les autres scripts requièrent `requests` et/ou `PyMuPDF (fitz)`.
- Tous les scripts résolvent les chemins via `Path(__file__).parent.parent` ; ils fonctionnent peu importe le répertoire courant.
- Code de sortie : `0` si tout réussit, `1` si une section échoue (erreurs sur stderr).

## Architecture

### Flux de données

```
data/raw/*.txt        ──(parse_gd.py)────────►  data/Gauche-Droite/gd<ligne>_<direction>.json
                      ──(parse_event.py)──────►  data/Events/<ligne>_<direction>.json
                      ──(parse_journee.py)────►  data/journees/journee-YYYY-MM-DD.json
employe.stm.info      ──(refresh_events.py)──►  data/Events/<ligne>_<direction>.json
data/gtfs/            ──(fetch_gtfs.py)──────►  data/gtfs/gtfs_stm/   (données statiques)
data/ca/*.pdf         ──(carte_agent_stm.py + GTFS)──►  PDF annoté
                      ──(gen_rapport.py)──────►  data/rapports/rapport-YYYY-MM-DD.pdf
data/journees/        ──(gen_rapport_v2.py)──►  data/rapports/rapport-v2-YYYY-MM-DD.{html,pdf}
data/Gauche-Droite/ + data/Events/ + GTFS  ──(rapport_gd.py)──►  scripts/rapport_<ligne>_<dir>_<date>.html
```

Le package **`chauffeur/`** centralise le noyau de domaine partagé entre les scripts et l'app Streamlit : `matching` (appariement noms d'arrêts), `modeles` (dataclasses), `ca` (cartes agent : résolution par identité `resoudre_ca` avec repli legacy par date, rangement `ranger_ca` — collision refusée sauf remplacement, sauvegarde `.bak`), `depots` (chemins canoniques, chargement et sauvegarde des fichiers G-D/évènements/journées de `data/` et fraîcheur `info_gd`/`info_gtfs` avec seuils `FRAICHEUR_*` — source unique des conventions de nommage), `effectif` (horaires, dont `bornes_quart` — min/max d'une liste d'heures de quart par valeur réelle plutôt que par tri lexical), `evenements` (applicabilité au quart, à une date, à une plage de quart — source unique du marqueur ✅/⬜ de l'UI et du filtre date des rapports), `gd` (build_rows, détours, applicabilité par parcours — `stop_ids=None` = arrêts GTFS inconnus → évènement présumé applicable, fail-safe), `gtfs` (lookup arrêts GTFS, `stops_for_parcours`, index `stops_index.json`), `gtfs_rt` (décodeur protobuf minimal du flux vehiclePositions, `parse_vehicle_positions`/`find_vehicle`), `journee` (groupes/lignes de service à partir d'une journée), `periodes` (calendrier de référence STM — listes/variations/fériés — et dérivation de l'identité d'une carte agent via `identite_ca(date, numero)`), `portail` (session + appels HTTP portail employé STM). La lecture des cartes agent PDF se fait directement dans `scripts/carte_agent_stm.py` (parsing géométrique bbox via PyMuPDF).

L'application Streamlit tient dans un seul fichier de présentation, `app/ui.py` (5 onglets) : toute la logique (fraîcheur `info_gtfs`/`info_gd`, résolution/rangement des cartes agent, décodage GTFS-RT) vit dans le package `chauffeur/`.

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
- **Journées** : `data/journees/journee-YYYY-MM-DD.json` (sortie de `parse_journee.py`).
- **Cartes agent** : identifiées par `(numéro, liste/variation, jour-type)` via `chauffeur.periodes.identite_ca()`, pas par leur seule date — un même numéro peut désigner des cartes différentes selon la liste et le jour-type (semaine/samedi/dimanche/variation). Nommage `data/ca/<numéro>_<groupe_id>_<jour_type>.pdf` (+ `-annotee.pdf`), les deux copies conservées ; une identité déjà présente est refusée à l'écrasement sauf action explicite « remplacer » (sauvegarde `.bak`). Les fichiers `carte-agent-YYYY-MM-DD.pdf` restent le nommage des imports antérieurs à cette refonte (non migrés, lus en repli par `get_ca_info()`).
- **Rapports journaliers v1** : `data/rapports/rapport-YYYY-MM-DD.pdf`.
- **Rapports journaliers v2** : `data/rapports/rapport-v2-YYYY-MM-DD.{html,pdf}` (ou `rapport-v2-DATE-LIGNE-DIR-idN.html` pour un rapport mono-groupe).
- JSON écrit avec indentation 2 espaces et accents préservés (`ensure_ascii=False`).
- Préférer l'import via les scripts à l'édition manuelle, pour garantir la normalisation et le rapport de changements.
