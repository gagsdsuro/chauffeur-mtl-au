# AGENTS.md

Dépôt de données d'itinéraires d'autobus urbains (Montréal) + scripts d'import et rapports. **Langue de travail : français** — noms de champs JSON, messages, doc en français. Voir `CLAUDE.md` (à la racine) pour la spécification détaillée des formats et commandes ; ce fichier ne résume que ce qu'on rate facilement.

## Commandes

```bash
streamlit run app/main.py                   # app locale (pages dans app/pages/)
docker compose up --build                   # prod, port 8501, volume ./data

python3 tests/test_*.py                     # chaque suite = script direct, PAS pytest
python3 tests/run_all.py                    # toute la suite, avant déploiement
python3 tests/test_dockerfile.py            # garde-fou : Dockerfile copie tout package source

python3 scripts/parse_gd.py       < data/raw/new-gd.txt   # import G-D depuis stdin
python3 scripts/parse_event.py    < data/raw/new-events.txt
python3 scripts/parse_journee.py  --date 2026-06-18 < raw.txt
python3 scripts/migrer_logs_flotte.py [--dry-run]   # one-shot : journaux de flotte → data/log/
```

- Aucun framework de test/lint/typecheck configuré (pas de pyproject/pytest). Vérifier par `python3 -m py_compile <fichier>` + les suites de régression. `run_all.py` découvre toute suite nommée `test_*.py` dans `tests/` — un nouveau test suit juste cette convention.
- Les importeurs **lisent depuis stdin** (pas d'argument fichier). Options : `--json` (imprime le JSON), `--log` (écrit dans le journal de la source). Depuis l'app, `--log` est toujours actif. **Deux familles de journaux** (`chauffeur.journal`, `SOURCES_COMMUNES`) : imports de la flotte renouvelable (G-D/Événements/GTFS/GTFS-RT → `parse_gd`/`parse_event`/`fetch_gtfs`/`fetch_gtfs_rt`) → `data/log/` **commun** ; journaux personnels (journée, carte agent) → `data/<matricule>/log/`.
- Référence de déploiement : Python 3.12.16 / Streamlit 1.66.1. Dépendances directes dans `requirements.in` ; `requirements.txt` généré sous Python 3.12, avec versions exactes et empreintes (ne pas l'éditer à la main). Installer par `python -m pip install --require-hashes -r requirements.txt`, puis `python -m pip check`. Mises à jour : `docs/dependances.md`. Quelques suites requièrent `pymupdf` (cartes agent) ou `reportlab` (rapport v1) ; `requests` pour GTFS/GTFS-RT et le portail — **pas de dépendance protobuf pour le décodeur GTFS-RT**. Détail : `README.md` et section « Dépendances » de `CLAUDE.md`.

## Architecture (à ne pas se tromper)

- `chauffeur/` = noyau de domaine partagé (app + scripts) : `depots.py` (source unique des chemins/conventions de nommage), `gd.py`, `evenements.py`, `gtfs.py`, `periodes.py`, `ca.py`, `journal.py`, etc. **Toute logique va dans `chauffeur/`**, pas dans l'app.
- `app/` = couche Streamlit (multipages) : `main.py` (entrée), `pages/` (une page par écran), `components/` (sous-composants partagés, dont `connexion.py`), `state.py` (clés `session_state` transverses), `utils.py`, `bootstrap.py` (sys.path avant tout import ; `initialiser_page()` = connexion + contexte matricule de session ; accesseurs `journees_dir()`/`rapports_dir()`/…). Zéro logique métier.
- `scripts/*.py` = CLI autonomes.
- Les scripts résolvent les chemins via `Path(__file__).parent.parent` : ils fonctionnent **indépendamment du répertoire courant**. Ne pas supposer que cwd == racine ; ne jamais utiliser de chemins relatifs à cwd.

## Conventions de nommage des fichiers

- G-D : `data/Gauche-Droite/gd<ligne>_<direction>.json` (préfixe `gd`, direction **minuscule**, ligne avec `e` si applicable, ex. `gd85e_ouest.json`).
- Événements : `data/Events/<ligne>_<direction>.json` (**sans** préfixe).
- Journées : `data/<matricule>/journees/journee-YYYY-MM-DD.json` ; rapports v2 : `data/<matricule>/rapports/rapport-v2-DATE.*` (sans matricule configuré, les emplacements historiques `data/journees/…`, `data/rapports/…` s'appliquent).
- JSON écrit avec indentation 2 et `ensure_ascii=False` (accents préservés). Ne pas traduire/renommer les champs.

## Isolation par matricule

- `CHAUFFEUR_MATRICULE` (5 chiffres, 20000-99999, voir `chauffeur/matricule.py`) isole les données personnelles dans `data/<matricule>/` : **journées, cartes agent, notes, rapports, logs personnels, session portail**. Absente → emplacements historiques (legacy). L'app charge le fichier `/.env` de la racine au démarrage (Streamlit ne le fait pas) ; les scripts et tests lisent uniquement l'environnement réel.
- La **flotte, partagée par tous** : `data/Gauche-Droite/`, `data/Events/`, `data/gtfs/`, `data/gtfs_rt/`, et les **journaux de ses imports** dans `data/log/` (`chauffeur.journal.SOURCES_COMMUNES` : parse_gd/parse_event/fetch_gtfs/fetch_gtfs_rt) — rien ne bouge.
- Les répertoires sont résolus par `chauffeur.depots` au **chargement du module** (une lecture de l'env par processus) ; `repertoire_prive`/`repertoire_utilisateur` restent paramétrables (tests, migration). Dans l'app, le **matricule de session** (authentifié) prime via un contexte par thread (`definir_matricule_contexte`) posé en tête de page par `bootstrap.initialiser_page()` — les constantes du module restent figées à l'env pour le CLI.
- **Mode strict** (`CHAUFFEUR_MODE_STRICT=1`, opt-in explicite) : plus de repli legacy — résoudre un répertoire privé sans matricule (session ou env) lève `ValueError`. Les constantes du module, elles, n'appliquent pas le strict (permis pour ouvrir la page de connexion).
- Migration one-shot : `python3 scripts/migrate_data.py --matricule 40001 --dry-run` (puis sans `--dry-run`) déplace les dossiers privés historiques sous `data/40001/` (`--force` fusionne une cible déjà remplie, sans jamais écraser un fichier). **`data/log/` n'est pas déplacé** (journal commun de la flotte) : seuls les journaux **personnels** (`parse_journee.log`, `carte_agent.log`) qui s'y trouvent sont rapatriés vers `data/<matricule>/log/` (conflit → mis de côté en `<source>.N` avec `--force`). `scripts/migrer_logs_flotte.py [--dry-run]` rapatrie les journaux de flotte (`parse_gd`/`parse_event`/`fetch_gtfs`/`fetch_gtfs_rt`) déjà écrits dans `data/<matricule>/log/` vers `data/log/` (une cible existante passe en `<source>.N`, jamais d'écrasement).

## Authentification locale par PIN

- `data/users.json` (partagé, permissions `0600`, gitignoré) : comptes **matricule → {nom, rôle, sel, hash scrypt, tentatives, verrou}**. Le PIN (4-8 chiffres, `chauffeur.auth.pin_valide`) n'est jamais stocké en clair. Le **premier compte créé devient Chauffeur-admin**, les suivants Chauffeur.
- Verrouillage : 5 échecs consécutifs → 5 min de suspension. Un Chauffeur change son propre PIN (ancien requis, barre latérale) ; un Chauffeur-admin peut le **réinitialiser sans l'ancien** et **déverrouiller** un compte.
- **Rôles (auto-gestion stricte, phase 4)** : seul un Chauffeur-admin promouvoit un Chauffeur ; l'autorité d'un admin n'est modifiable **que par lui-même** (auto-destitution refusée pour le dernier admin) ; un compte admin n'est jamais révocable par autrui ni par soi. Toute la matrice vit dans `chauffeur/auth.py` (`changer_role`, `reinitialiser_pin`, `deverrouiller_compte`, `revoquer_compte`, `lister_comptes`).
- Dans l'app, la connexion est exigée dès qu'un compte existe dans `users.json` ; le **wizard de premier lancement** apparaît en mode strict sans compte. Sans compte et sans strict → comportement legacy (aucune page de connexion). Déconnexion dans la barre latérale ; le PIN est redemandé à chaque session navigateur.
- **Page Administration** (`app/pages/6_administration.py`) : liste des comptes, création (rôle au choix), promotion/destitution, réinitialisation du PIN, déverrouillage, révocation. Elle n'apparaît dans la navigation (`st.navigation` dans `main.py`) **que pour un Chauffeur-admin** ; garde-fou en page (st.stop) pour un accès direct par URL.

## Pièges opérationnels

- `data/` est **gitignoré** (seul `data/reference/` est versionné, sauf `points_de_releve_*.json`, `garages.json` et `stations_metro.json`, locaux — gabarits dans `docs/gabarits/reference/`) : ne pas committer de données, journaux, cookies de session (`data/<matricule>/session/cookies.json`).
- Les rafraîchissements portail (`refresh_events.py`, `refresh_gd.py`, `fetch_journee.py`) et l'app exigent une session `employe.stm.info` valide (cookies mode `0600` dans `data/<matricule>/session/cookies.json`) ; `refresh_events.py` sort `2` quand la session est expirée (renouveler les cookies).
- **Le Dockerfile ne copie que `app/`, `scripts/`, `chauffeur/`.** Ajouter un nouveau package de premier niveau sans le déclarer casse la prod (`ModuleNotFoundError`) — d'où `test_dockerfile.py`.
- Déploiement Docker : UID/GID alignés sur l'hôte via args pour que les fichiers écrits dans `./data` n'appartiennent pas à root.
- Les tests de régression (cartes agent, rapport, G-D) rejouent des **cas figés** dans `tests/cas*/<nom>/` (PDF/JSON gelés) — hermétiques, sans le gros GTFS. Un nouveau cas se fige via `tests/creer_cas_*.py` ; **vérifier `attendu.json` avant de committer**.
- GTFS statique volumineux ; `chauffeur.gtfs.stops_for_line()` lit `stops_index.json` (~80x plus rapide qu'un scan CSV), avec repli automatique si absent. Reconstruire l'index avec `python3 scripts/fetch_gtfs.py --index-only` (sans re-télécharger).
- Prendre comme source de vérité les scripts exécutables : si `CLAUDE.md` et le code divergent, le code l'emporte.

## Dépôt public : confidentialité et licence

Le dépôt est publié sous AGPL-3.0 (`LICENSE`, `NOTICE.md`, `THIRD_PARTY_NOTICES.md`). Règles pour tout ajout :
- **Jamais** de secret, clé API, cookie, hôte, adresse IP, compte, chemin de production, ni de vulnérabilité non corrigée dans un fichier versionné.
- **Jamais** de données réelles (journées, cartes agent, noms ou matricules de collègues, contenu du portail employé) : jeux d'essai **synthétiques ou anonymisés** (matricules fictifs 4xxxx). Les fiches de recette réelles vont dans un dépôt privé ; `docs/recettes/gabarit-build.md` sert de modèle.
- Nom du produit : « Chauffeur Mtl-AU ». Ne pas réintroduire « STM » comme marque ; les mentions de la STM se limitent aux URLs, à la désignation des sources de données ouvertes et à l'attribution CC BY (`chauffeur/avis.py`, source unique des textes d'avis).
- Notes personnelles locales : `CLAUDE.local.md` (ignoré par git).
