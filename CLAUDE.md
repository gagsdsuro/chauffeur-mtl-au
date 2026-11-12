# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vue d'ensemble

Chauffeur Mtl-AU (`chauffeur-mtl-au`) est un dépôt de **données** d'itinéraires d'autobus urbains (Montréal) destinées aux chauffeurs, accompagnées de scripts Python d'import et de génération de rapports. Le cœur du projet est un ensemble de fichiers JSON normalisés : parcours « Gauche-Droite » (instructions de conduite virage-par-virage) et événements affectant les arrêts et/ou le parcours.

La langue de travail est le **français** (noms de champs, messages, documentation).

## Commandes

**Lancer l'application Streamlit** :
```bash
streamlit run app/main.py                   # développement local (pages dans app/pages/)
docker compose up --build                   # production (port 8501, volume ./data)
```
L'app expose 7 pages (navigation latérale, `st.navigation` dans `main.py`) : Ma journée (liste J−2/J+5 et saisie manuelle d'une date AAAA-MM-JJ pour consulter l'historique, rafraîchissement des lignes restantes, consultation par pièce/trajet) · Préparation d'une journée (proposition de **préparation semi-automatique** quand la journée n'est pas importée, état synthétique, imports manuels, fichiers .ics des pièces, récupération des événements et rapports conditionnels) · Rapports (2 sous-onglets) · Fichiers (5 catégories, liste paginée et aperçus, classement par liste, édition JSON selon le rôle et export CSV séparé ; voir `docs/fichiers.md`) · Logs · Appariement des arrêts (révision des appariements G-D ↔ arrêts, communs à tous : filtre À réviser/Ma journée/Tous, tableau éditable étape par arrêt, arrêts fixés, recalcul automatique autour des choix, validation) · Appariement des détours (appariement des évènements, communs : filtre À réviser/Ma journée/Tous, début du détour et fin du barrage, ordre et étape des arrêts ajoutés, aperçu du parcours, validation ; réutilisé quand le même détour revient sous un autre numéro). La page **Administration** (gestion des comptes) n'apparaît que pour un Chauffeur-admin ; garde-fou `st.stop` en page pour un accès direct par URL.

**Dépendances** — référence de déploiement : Python 3.12.16 / Streamlit 1.66.1. Dépendances directes dans `requirements.in` ; `requirements.txt` généré sous Python 3.12 avec versions exactes et empreintes, jamais édité manuellement. Installation : `python -m pip install --require-hashes -r requirements.txt`, puis `python -m pip check` (venv Python 3.12 recommandé). Le Dockerfile fixe aussi l'empreinte de l'image Python. Procédure de mise à jour : `docs/dependances.md` ; tableau paquet→usage dans le `README.md`. Points à savoir :
- `pymupdf` : annotation carte agent + tests `test_carte_agent.py`/`test_rapport_evenements.py`/`creer_cas_test.py`.
- `reportlab` : PDF des rapports v1/v2 + tests `test_rapport.py`/`test_rapport_evenements.py`.
- Pas de dépendance protobuf : le GTFS-RT est décodé en wire-format minimal par `chauffeur/gtfs_rt.py`.
- `openpyxl` (hors requirements) : uniquement pour `scripts/import_journees_historique.py`.

**Import Gauche-Droite** — lit depuis stdin, écrit dans `data/Gauche-Droite/` :
```bash
python3 scripts/parse_gd.py < data/raw/new-gd.txt          # importe et écrit les fichiers
python3 scripts/parse_gd.py --json < data/raw/new-gd.txt   # idem + imprime le JSON complet sur stdout
python3 scripts/parse_gd.py --log < data/raw/new-gd.txt    # idem + trace dans data/log/parse_gd.log (flotte, commun)
python3 scripts/parse_gd.py --fusionner < data/raw/un-parcours.txt   # les parcours collés remplacent ceux de même ID, les autres sont conservés
python3 scripts/parse_gd.py --remplacer < data/raw/new-gd.txt        # le fichier devient exactement le collage
```
**Fusion ou remplacement** (clé = **id de parcours**, partout y compris dans le résumé des changements) : un collage qui ne contient pas tous les parcours déjà présents du fichier `gd<ligne>_<direction>.json` en retirerait. Sans choix, l'import est refusé (CLI : code 1, aucun fichier modifié, relancer avec `--fusionner` ou `--remplacer`) ou demandé à l'écran (page Préparation : Fusionner / Remplacer / Annuler). Fusion : les parcours collés remplacent ceux de même id à leur place, les autres sont conservés, les ids nouveaux sont ajoutés à la fin. Un collage qui ne retire rien (fichier nouveau, ajout seul, ou tous les ids déjà présents) s'importe directement ; l'import du portail (`refresh_gd.py`, liste complète d'une ligne/direction) remplace toujours le fichier. Tests : `python3 tests/test_parse_gd_fusion.py`.
Depuis une session portail valide, `refresh_gd.py` récupère le HTML sémantique
de `/listeBus` (le bloc PDFMake caché est ignoré) :
```bash
python3 scripts/refresh_gd.py --journee data/journees/journee-2026-06-25.json
python3 scripts/refresh_gd.py --journee data/journees/journee-2026-06-25.json --tous
python3 scripts/refresh_gd.py --ligne 24 --sens est
```

**Import Événements** — lit depuis stdin, écrit dans `data/Events/` :
```bash
python3 scripts/parse_event.py < data/raw/new-events.txt
python3 scripts/parse_event.py --json < data/raw/new-events.txt
python3 scripts/parse_event.py --log < data/raw/new-events.txt   # trace dans data/log/parse_event.log (flotte, commun)
```

**Import Journée** — lit depuis stdin le texte brut « Détail de ma journée », écrit dans `data/journees/` :
```bash
python3 scripts/parse_journee.py --date 2026-06-18 < raw.txt   # date explicite
python3 scripts/parse_journee.py --json < raw.txt              # idem + JSON complet sur stdout
python3 scripts/parse_journee.py --log < raw.txt               # idem + trace dans data/<matricule>/log/parse_journee.log (personnel)
```
La date est auto-détectée depuis le champ « Mis à jour le » si `--date` est absent.
Les pièces `ContinuHoraire` sont conservées avec `type_horaire: "continu"`;
plusieurs pièces peuvent légitimement partager le même `id`.
Les sommaires `Absence` sont conservés avec `id: "Absence"`,
`type_horaire: "absence"`, leurs heures et durée, et `motif_absence`
(code et libellé du portail), sans autobus ni trajets. `temps_travaille`
reste la valeur déclarée par le portail, y compris lorsqu'elle inclut l'absence.
Import automatique depuis une session valide :
```bash
python3 scripts/fetch_journee.py                         # aujourd'hui
python3 scripts/fetch_journee.py --date 2026-08-22 --log
```

**Calendrier (.ics)** — un fichier iCalendar par pièce de travail (`chauffeur.calendrier`), pour créer l'évènement dans un calendrier : début → fin de la pièce, titre « 176-06 · Lignes 176 » (lignes de service dans l'ordre de passage, sans doublon), prise/lieux/autobus/relève en description. Heures **flottantes** (sans fuseau : l'image Docker slim n'a pas tzdata) ; une fin au-delà de 24 h (« 25:11 ») tombe le lendemain ; absences et pièces sans heures ignorées. UID stable (date, rang, id de pièce) : réimporter met l'évènement à jour au lieu de le dupliquer. Écrits **à chaque import de journée** (`importer_journee_portail`, `JourneeParser.save` — donc bouton portail, collage, `parse_journee.py`, `fetch_journee.py` ; ligne `📅` au rapport d'import ; un échec ne fait jamais échouer l'import) dans `data/<matricule>/calendrier/<date>/<rang>-<pièce>.ics` (les fichiers obsolètes d'une même date sont retirés) ; la page Préparation (section « 1b — Calendrier ») propose un bouton par pièce et un .zip, produits à la volée depuis la journée (pas de migration des journées déjà importées) :
```bash
python3 tests/test_calendrier.py
```

**Préparation semi-automatique** — `chauffeur/preparation_auto.py` (`executer_semi_auto`, sans Streamlit) enchaîne : journée → calendrier (.ics) → carte agent (PDF du bouton « Carte Agent » du portail, annotée et rangée par identité) → G-D manquants/périmés → évènements → rapport v2 niveau `standard`. Proposée par la page Préparation quand la journée de la date n'est pas importée ; la page s'affiche ensuite normalement (bilan repliable, rejeu manuel de chaque section). **Bloquant** (arrêt, bouton « Reprendre ») : journée non importée, session portail expirée (dialogue de cookie puis reprise à l'étape interrompue, `operation_portail` de type `semi_auto`), G-D requis toujours absents, rapport v2 impossible (GTFS absent). **Avertissement** (la chaîne continue) : calendrier, carte agent (introuvable, numéro ≠ journée), évènements en échec (rapport avec les évènements présents ; « Continuer sans les évènements du portail » si la session n'est pas renouvelée). Carte agent déjà présente pour l'identité → étape ignorée. `PortailClient.fetch_carte_agent(date)` lit le lien `#btnCarteAgent` dans `journeeHtml` (`lien_carte_agent`, jeton propre à la journée, hôte/date vérifiés) puis télécharge le PDF ; `chauffeur.ca.annoter_et_ranger_ca` (partagée avec le dépôt manuel de la page) annote et range. Tests : `tests/test_carte_agent_portail.py`, `tests/test_preparation_auto.py`, `tests/test_page_preparation_auto.py`.

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
**Niveau par parcours** : `--parcours LIGNE:DIR:ID=NIVEAU` (répétable ; `aucun` exclut le parcours, les autres prennent `--niveau`), ex. `--parcours 24:ouest:2=compact --parcours 445:ouest:19=aucun` ; page Rapports : un sélecteur par parcours (« (défaut) » suit le niveau par défaut). Une sélection qui s'écarte du niveau par défaut s'écrit dans `rapport-v2-DATE-personnalise.{fmt}` et ne marque jamais le rapport du niveau « à jour ». **Évènements évalués par départ** : chaque trajet est testé sur sa propre plage (départ → arrivée) ; si les évènements applicables diffèrent d'un départ à l'autre, le parcours est **dupliqué** (une section par ensemble d'évènements, note « Parcours dupliqué (k/n) »), sinon le format reste inchangé. Les jours/heures du `commentaire` servent de repli quand l'`effectif` ne restreint rien (« LUNDI AU VENDREDI 12H00 À 19H00 » avec effectif « En tout temps », `chauffeur.effectif`). Au sommaire des évènements, ceux qui génèrent un avertissement du pipeline détaillent leurs arrêts annulés/ajoutés, commentaire et description G-D.
```bash
python3 tests/test_rapport_v2_parcours.py   # sélection, duplication par départ, détails du sommaire
```

**Annotation carte agent** — annote le PDF de carte agent avec les horaires GTFS (requiert `PyMuPDF`) :
```bash
python3 scripts/carte_agent.py --pdf data/ca/carte-agent-2026-06-04.pdf --out data/ca/annotée.pdf --gtfs data/gtfs/gtfs_stm/ --date 2026-06-04
```

**Tests de régression carte agent** — rejoue des cas figés (PDF + horaires GTFS gelés dans `tests/cas/<nom>/`) et compare le plan d'annotations à `attendu.json` (requiert `PyMuPDF`) :
```bash
python3 tests/test_carte_agent.py              # tous les cas
python3 tests/test_carte_agent.py carte-449    # un cas précis
python3 tests/creer_cas_test.py --pdf data/ca/carte-agent-2026-06-09.pdf --gtfs data/gtfs/gtfs_stm/   # figer un nouveau cas (vérifier attendu.json avant de committer)
```

**Tests de régression rapport** — rejoue des cas figés (journée + G-D + évènements gelés, anonymisés, dans `tests/cas_rapport/<nom>/`) et compare les lignes reconnues et leurs directions G-D appariées à `attendu.json`. Hermétique : `GD_DIR` est redirigé vers le `gd/` du cas (requiert `reportlab`) :
```bash
python3 tests/test_rapport.py                          # tous les cas
python3 tests/test_rapport.py journee-2026-06-20     # un cas précis
python3 tests/creer_cas_rapport.py --pdf data/ca/carte-agent-2026-06-11.pdf   # figer un nouveau cas (vérifier attendu.json avant de committer)
```

**Suite complète + garde-fou Docker** — à lancer avant tout déploiement :
```bash
python3 tests/run_all.py        # exécute toutes les suites tests/test_*.py
python3 tests/test_dockerfile.py  # vérifie que le Dockerfile copie tout package source de premier niveau (app/scripts/chauffeur) — évite ModuleNotFoundError en prod
```

**Tests de régression domaine G-D** — rejoue le pipeline (build_rows → annotate → détours → placement des arrêts ajoutés) sur des entrées gelées dans `tests/cas_rapport_gd/<nom>/` (G-D + Events + arrêts GTFS, sans dépendre du GTFS volumineux) ; compare rows/added à `attendu.json`. Le cas `gd-445-est-2026-10-21` gèle le détour qui emprunte d'abord la rue de la manœuvre précédant l'arrêt annulé (« Droite - Beaubien » puis « VIA BEAUBIEN ») : il s'insère après elle, qui reste valide. Le cas `gd-10-*-2026-07-12` gèle l'ancrage des arrêts ajoutés par code d'arrêt (terminus temporaire Station Sherbrooke : départ en nord → l'arrêt précède, arrivée en sud → il suit) :
```bash
python3 tests/test_rapport_gd.py
python3 tests/creer_cas_rapport_gd.py --ligne 125 --direction ouest --date 2026-06-11   # figer un nouveau cas (vérifier attendu.json)
```

**Tests unitaires modèle G-D** — `chauffeur.gd` travaille sur une **séquence linéaire** : instruction et arrêt ont chacun leur ligne (un arrêt vient *après* sa manœuvre, il ne la partage pas), donc détours et arrêts ajoutés s'insèrent entre les deux sans ambiguïté ; `rows_de_rendu` refait la mise en page à deux colonnes (instruction + 1er arrêt sur une ligne) en dernier, pour les rendus. Les lignes passées à `annotate_events`/`apply_gd_detours`/`insert_added_stops_inline`/`filter_rows_by_stop_range` sont toujours non fusionnées. Ce que le pipeline ne peut pas décider seul (début ou retour de détour introuvable dans le G-D, description illisible, arrêt ajouté non placé ou plusieurs sur une même étape) ne passe plus en silence : `apply_gd_detours`/`insert_added_stops_inline` complètent une liste optionnelle `diagnostics`, que `message_diagnostic` met en texte et que le rapport v2 affiche en avertissement non bloquant (`avertissements_groupe`) :
```bash
python3 tests/test_gd_modele.py
```

**Tests de régression parseurs** — rejoue des collages bruts figés dans `tests/cas_event/`, `tests/cas_gd/` et `tests/cas_journee/` :
```bash
python3 tests/test_parse_event.py     # régression parse_event.py (cas : détour sans annulation, arrêts vides)
python3 tests/test_parse_gd.py        # régression parse_gd.py (cas : multi-parcours même ligne/direction, parcours en double → [AVERTISSEMENTS])
python3 tests/test_parse_journee.py   # régression parse_journee.py (cas : sommaire sans bus, placeholders "--"+"--")
```

**Tests appariement G-D ↔ GTFS** — couvre `chauffeur.appariement` (alignement global monotone par programmation dynamique, confiance par arrêt, blocs incertains, ancres manuelles) sur des cas gelés dans `tests/cas_appariement/<ligne>-<direction>-<id>/` (811 ouest : boucle ; 460 est : voies de desserte) + tests unitaires :
```bash
python3 tests/test_appariement.py
python3 tests/creer_cas_appariement.py --ligne 811 --direction ouest --id 13   # figer un cas (vérifier attendu.json)
```

**Tests unitaires appariement** — couvre `chauffeur.matching` (stations vs rues, parenthèses, REM, troncature) :
```bash
python3 tests/test_matching.py
```

**Tests unitaires journée** — couvre `chauffeur.journee` (`groupes_de_service`, `lignes_de_service`) sur des journées synthétiques inline :
```bash
python3 tests/test_journee.py
```

**Tests unitaires évènements** — couvre `chauffeur.evenements` (`applicable_a_la_date`, `applicable_a_la_plage` : bornes ouvertes, quart franchissant minuit, effectif horaire, replis fail-safe ; `titre_annule_l_arret`/`arret_reellement_annule` : les 5 titres réels du portail, fail-safe sur titre inconnu, agrégation « le plus grave l'emporte » quand un arrêt cumule des évènements de sémantiques opposées) et la convention `stop_ids=None` de `chauffeur.gd.event_applicable_to_parcours` :
```bash
python3 tests/test_evenements.py
```

**Tests unitaires journaux** — couvre `chauffeur.journal` (`chemin_journal`, `ecrire_bloc` — dont le format historique de `parse_event.log`, préservé octet pour octet —, `ecrire_ligne`, `lister_journaux`) en répertoire temporaire ; `test_journal_commun.py` le routage flotte (commun) vs personnel ; `test_migrer_logs_flotte.py` le rapatriement vers `data/log/` :
```bash
python3 tests/test_journal.py
python3 tests/test_journal_commun.py
python3 tests/test_migrer_logs_flotte.py
```

**Tests unitaires dépôts** — couvre `chauffeur.depots` (chemins canoniques, `charger_gd` avec sélection par id et replis, `charger_evenements`, `evenements_pour_date`, `charger_journee`, `sauvegarder_journee`, fraîcheur `info_gd`/`info_gtfs`) sur fichiers synthétiques en répertoire temporaire :
```bash
python3 tests/test_depots.py
```

**Tests unitaires effectif** — couvre `chauffeur.effectif.bornes_quart` (liste vide, heure unique, tri par valeur réelle plutôt que lexicale, quart franchissant minuit) :
```bash
python3 tests/test_effectif.py
```

**Tests unitaires GTFS statique** — couvre le cache mémoire de `stops_index.json` (`chauffeur.gtfs`) : un index modifié sur disque par un autre processus (`fetch_gtfs.py`) est relu au prochain appel (régression 51281 « Décarie / Duquette » du 24 est, octobre 2026 : ancienne séquence servie avec les nouveaux noms) :
```bash
python3 tests/test_gtfs.py
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

**Test de régression portail** — rejoue un fragment HTML figé (`tests/cas_portail/`) et vérifie la normalisation des événements par `PortailEventParser.from_portal_json()`, y compris un `evenement_id` dupliqué sans faux avertissement :
```bash
python3 tests/test_portail.py
python3 tests/test_session_portail.py   # validation, rotation et protection des cookies
```

**Rapport détaillé G-D / Arrêts** — rapport HTML ou Markdown pour une ligne/direction (requiert GTFS) :
```bash
python3 scripts/rapport_gd.py --ligne 195 --direction ouest --date 2026-06-05 --base .
python3 scripts/rapport_gd.py --ligne 24 --direction est --heure-debut 06:00 --heure-fin 14:30
python3 scripts/rapport_gd.py --ligne 125 --direction est --arret-debut 54112 --arret-fin 57365
```
Options clés : `--format html|md`, `--heure-debut`/`--heure-fin` (peut dépasser 24h ex. `25:19`), `--parcours principal|secondaire|école|weekend`, `--arret-debut`/`--arret-fin`. Sortie : `scripts/rapport_<ligne>_<dir>_<date>.html`.

**Rafraîchissements depuis le portail employé** — journées, G-D et événements lisent
`employe.stm.info` avec le même client et la même session persistante. Pour les événements :
```bash
python3 scripts/refresh_events.py --journee data/journees/journee-2026-06-25.json
python3 scripts/refresh_events.py --journee data/journees/journee-2026-06-25.json --restantes
python3 scripts/refresh_events.py --ligne 10 --sens sud
```
Codes de sortie : `0` succès, `1` erreur HTTP/parse, `2` session expirée (renouveler les cookies).
Session : lors d'une récupération, l'app valide d'abord la session par `/listeBus`. Si elle est expirée, une boîte de dialogue permet de coller la chaîne de cookies et reprend automatiquement les lignes non traitées. La session HTTP et le jeton CSRF sont réutilisés pour tout le lot. Les cookies sont stockés avec permissions `0600` dans `data/<matricule>/session/cookies.json` (gitignorée via `data/`) ; `chauffeur.portail.save_session()` reste disponible en Python.

**Appariement G-D ↔ arrêts GTFS** — un fichier commun par parcours, `data/Appariements/<ligne>_<direction>_<id>.json` (`chauffeur.registre_appariement`). Calculé automatiquement par `GDParser.parse()` (donc `parse_gd.py`, `refresh_gd.py`/Préparation et collage dans l'app ; messages ajoutés au rapport d'import sous `[APPARIEMENT]`) et après `fetch_gtfs.py` ; révisé dans la page **Appariement** (Préparation signale les parcours de la journée à réviser) ; utilisé par le rapport v2 (avertissement si `incertain`/`a_revalider`, jamais bloquant) :
```bash
python3 scripts/apparier.py                                  # état (code 1 si un parcours reste à réviser)
python3 scripts/apparier.py --sync [--ligne 811 --sens ouest] [--log]
python3 tests/test_registre_appariement.py
python3 tests/test_page_appariement.py      # interface (AppTest) : liste, validation
```
Statuts : `auto` · `incertain` (blocs à réviser) · `valide` (révisé par un chauffeur, jamais écrasé) · `a_revalider` (empreinte G-D ou GTFS changée depuis un choix humain : choix reportés, à reconfirmer). Validité = empreintes `empreinte_gd` (terminus + instructions) et `empreinte_gtfs` (séquence des stop_id) ; `VERSION_ALGO` incrémenté → appariements automatiques recalculés. Écriture avec contrôle de version optimiste (`ConflitAppariement`) et `.bak`. Parcours retiré du G-D → appariement **archivé** dans `data/Appariements/orphelins/` (jamais supprimé) ; parcours **renuméroté** (même `empreinte_gd`, nouvel id) → ses choix humains sont repris (`herite_de`) et il passe `a_revalider`.

**Appariement des détours (évènements)** — un même détour revient dans l'année sous un autre numéro d'évènement ; son ancrage dans le parcours reste le même. `chauffeur.registre_detours` garde les décisions humaines, **communes**, sous une **signature de détour** (hash de ligne, direction, description G-D normalisée — R/R, R.R. et « route régulière » équivalents —, arrêts annulés et ajoutés ; ignore numéro d'évènement, dates, motif, effectif et ordre des arrêts) : `data/Appariements/detours/<ligne>_<direction>.json`. Un détour que le pipeline G-D place sans rien signaler n'est pas enregistré ; sinon entrée `incertain` (diagnostics), `valide` (choix humain, **imposé** au pipeline et jamais écrasé), `a_revalider` (choix devenu inapplicable après un changement du G-D, calcul automatique en attendant), `auto` (choix retiré). Le **choix** (`chauffeur.gd`, « Choix humains imposés ») fixe le début du détour (`debut` : avant tel élément de la séquence — instruction ou arrêt + occurrence), la fin du barrage (`fin`, `None` = rien de barré) et, pour les arrêts ajoutés, leur ordre et l'étape du détour où chacun se pose. Recalculé à l'import des évènements (`parse_event.py`, section `[APPARIEMENT DÉTOURS]`) et du G-D ; même écriture sûre que les appariements de parcours (`ConflitAppariement`, `.bak`). Révisé dans la page **Détours** (Préparation signale les détours de la journée à réviser) ; le rapport v2 applique les choix validés et avertit pour le reste (jamais bloquant) :
```bash
python3 scripts/apparier_detours.py                          # état (code 1 s'il reste un détour à réviser)
python3 scripts/apparier_detours.py --sync [--ligne 445 --sens est] [--log]
python3 tests/test_registre_detours.py
python3 tests/test_page_detours.py          # interface (AppTest) : liste, diagnostic, validation
```

**Téléchargement GTFS** — données statiques (hebdomadaire) et temps-réel (requiert `requests`) :
```bash
python3 scripts/fetch_gtfs.py
python3 scripts/fetch_gtfs.py --index-only   # reconstruit stops_index.json sans re-télécharger
python3 scripts/fetch_gtfs_rt.py
```
`fetch_gtfs.py` construit `stops_index.json` après extraction (scan unique de `stop_times.txt`) ; `chauffeur.gtfs.stops_for_line()` lit cet index (~80x plus rapide qu'un scan CSV) avec repli automatique si l'index est absent.

- `parse_gd.py`, `parse_event.py` et `parse_journee.py` importent `chauffeur` (`journal`, `modeles`, `depots` — stdlib, pas de package externe). Les autres scripts requièrent `requests` et/ou `PyMuPDF (`pymupdf`)`.
- Les trois parseurs acceptent `--log` : la sortie est ajoutée au journal de la source (**roulage par nature des données**, `chauffeur.journal.SOURCES_COMMUNES`) — imports de la flotte (G-D/Événements/GTFS/GTFS-RT) → `data/log/<source>.log` **commun** ; journaux personnels (journée, carte agent) → `data/<matricule>/log/<source>.log`. Opt-in en CLI (un import de test ne salit pas le journal) ; **toujours actif** pour les imports faits depuis l'app, où chaque import est une action à tracer.
- Tous les scripts résolvent les chemins via `Path(__file__).parent.parent` ; ils fonctionnent peu importe le répertoire courant.
- Code de sortie : `0` si tout réussit, `1` si une section échoue (erreurs sur stderr).

## Isolation par matricule

`CHAUFFEUR_MATRICULE` (5 chiffres, 20000-99999 — cf. `chauffeur/matricule.py`) route les données **personnelles** (journées, cartes agent, notes, rapports, journaux personnels — journée, carte agent, session portail) vers `data/<matricule>/<dossier>/` ; la **flotte partagée** (G-D `data/Gauche-Droite/`, événements `data/Events/`, GTFS `data/gtfs/`, GTFS-RT `data/gtfs_rt/`, et les journaux de leurs imports `data/log/`) reste à la racine de `data/`. Absente, les emplacements historiques `data/<dossier>/` s'appliquent (legacy). Une valeur d'env invalide lève `ValueError`. L'app (et elle seule) charge le `.env` de la racine au démarrage (`app/main.py`) ; les scripts et tests sont hermétiques : ils lisent uniquement l'environnement réel du process.

Résolution du matricule **à l'usage**, dans l'ordre : contexte par thread (app : matricule de session) puis environnement. Les constantes du module (`JOURNEES_DIR`, `CA_DIR`, …) restent figées à l'import pour le CLI ; les modules de domaine (`journal`, `notes`, `ca`, `portail`, `preparation`) et les fonctions de `depots` (**`repertoire_prive`**, `chemin_journee`, `lister_journees_fenetre`) consultent le contexte courant à l'usage — dans l'app, passer par les accesseurs `bootstrap.journees_dir()`/`rapports_dir()`/… après `initialiser_page()`.

**Mode strict** (`CHAUFFEUR_MODE_STRICT=1`, opt-in explicite) : plus de repli legacy — résoudre un répertoire privé sans matricule (session ou env) lève `ValueError`. Les constantes du module n'appliquent pas le strict (l'app doit pouvoir ouvrir sa page de connexion).

Migration one-shot : `python3 scripts/migrate_data.py --matricule 40001 [--dry-run] [--force]` (fusion sans jamais écraser un fichier) déplace les dossiers privés historiques. **`data/log/` reste commun (flotte)** : seuls les journaux personnels (`parse_journee.log`, `carte_agent.log`) qui s'y trouvent sont rapatriés vers `data/<matricule>/log/` (conflit → mis de côté `<source>.N` avec `--force`) ; `python3 scripts/migrer_logs_flotte.py [--dry-run]` fait l'inverse pour les journaux de flotte restés dans des dossiers privés.

## Authentification locale par PIN

`data/users.json` (partagé, permissions `0600`, gitignoré) : comptes `matricule → {nom, rôle, sel, hash scrypt, tentatives, verrou}`. Le PIN (4-8 chiffres, `chauffeur.auth.pin_valide`) n'est jamais stocké en clair ; hash `hashlib.scrypt` + sel 16 octets (protocole figé dans `auth._N/_R/_P/_DKLEN`). Premier compte créé → **Chauffeur-admin**, suivants → Chauffeur. Verrouillage : `TENTATIVES_MAX`=5 échecs → `VERROU_SECONDES`=300 s ; un PIN correct réinitialise le compteur. API : `creer_compte` (rôle optionnel, admin requis pour créer un admin), `verifier_pin`, `changer_pin` (autonomie, ancien requis), `reinitialiser_pin` (admin, sans ancien), `deverrouiller_compte`, `changer_role`, `revoquer_compte` (tous deux opérateur admin obligatoire), `lister_comptes`/`est_verrouille` — écritures atomiques sous verrou (`threading.Lock`).

**Matrice d'autorités — auto-gestion stricte :** un Chauffeur-admin promeut un Chauffeur (`changer_role`), mais l'autorité d'un admin n'est modifiable **que par lui-même** (promotion/destitution d'un autre admin refusées) ; l'**auto-destitution** est permise sauf pour le **dernier** admin (anti-verrouillage) ; pas de révocation d'un admin par autrui ni par soi. Un simple Chauffeur ne change pas de rôle, ne révoque pas, ne réinitialise pas un PIN.

Dans l'app (`app/components/connexion.py`), la connexion est exigée dès qu'un compte existe dans `users.json` ; sans compte, le **wizard de premier lancement** n'apparaît qu'en mode strict — sans compte et sans strict, l'app garde son comportement legacy (auth = choix explicite). Le PIN est redemandé à chaque session navigateur (pas de cookie « rester connecté ») ; un Chauffeur change son PIN dans la barre latérale (ancien requis) ; la **page Administration** (réservée Chauffeur-admin) gère comptes, rôles, réinitialisation de PIN, déverrouillage et révocation.

## Architecture

### Flux de données

```
data/raw/*.txt        ──(parse_gd.py)────────►  data/Gauche-Droite/gd<ligne>_<direction>.json
                      ──(parse_event.py)──────►  data/Events/<ligne>_<direction>.json
                      ──(parse_journee.py)────►  data/<matricule>/journees/journee-YYYY-MM-DD.json
employe.stm.info      ──(refresh_events.py)──►  data/Events/<ligne>_<direction>.json
data/gtfs/            ──(fetch_gtfs.py)──────►  data/gtfs/gtfs_stm/   (données statiques)
data/<matricule>/ca/*.pdf  ──(carte_agent.py + GTFS)──►  PDF annoté
                      ──(gen_rapport.py)──────►  data/<matricule>/rapports/rapport-YYYY-MM-DD.pdf
data/<matricule>/journees/ ──(gen_rapport_v2.py)──►  data/<matricule>/rapports/rapport-v2-YYYY-MM-DD.{html,pdf}
data/<matricule>/journees/ ──(chauffeur.calendrier, à l'import de la journée)──►  data/<matricule>/calendrier/<date>/<rang>-<pièce>.ics
data/Gauche-Droite/ + GTFS  ──(registre_appariement, à l'import G-D / GTFS)──►  data/Appariements/<ligne>_<dir>_<id>.json
data/Events/ + G-D + GTFS  ──(registre_detours, à l'import d'évènements / G-D)──►  data/Appariements/detours/<ligne>_<dir>.json
data/Gauche-Droite/ + data/Events/ + GTFS  ──(rapport_gd.py)──►  scripts/rapport_<ligne>_<dir>_<date>.html

import de la flotte (CLI --log ou app, parse_gd/parse_event/fetch_gtfs/fetch_gtfs_rt)  ──(chauffeur.journal)──►  data/log/<source>.log   (commun)
import personnel (CLI --log ou app, journée/carte agent)  ──(chauffeur.journal)──►  data/<matricule>/log/<source>.log   (privé)
```

Le package **`chauffeur/`** centralise le noyau de domaine partagé entre les scripts et l'app Streamlit : `matching` (appariement noms d'arrêts), `modeles` (dataclasses), `ca` (cartes agent : résolution par identité `resoudre_ca` avec repli legacy par date, rangement `ranger_ca` — collision refusée sauf remplacement, sauvegarde `.bak`), `depots` (chemins canoniques — isolation par matricule via `repertoire_utilisateur`/`repertoire_prive`, flotte partagée vs. données personnelles `data/<matricule>/` ; chargement et sauvegarde des fichiers G-D/évènements/journées de `data/` et fraîcheur `info_gd`/`info_gtfs` avec seuils `FRAICHEUR_*` — source unique des conventions de nommage), `effectif` (horaires, dont `bornes_quart` — min/max d'une liste d'heures de quart par valeur réelle plutôt que par tri lexical), `evenements` (applicabilité au quart, à une date, à une plage de quart — source unique du marqueur ✅/⬜ de l'UI et du filtre date des rapports ; sémantique des arrêts touchés via `titre_annule_l_arret`/`arret_reellement_annule` — source unique de la teinte rouge/ambre des rapports), `journal` (journaux d'importation — deux familles routées par `SOURCES_COMMUNES` : flotte `parse_gd`/`parse_event`/`fetch_gtfs`/`fetch_gtfs_rt`/`appariement` → `data/log/` commun, personnel → `data/<matricule>/log/` ; `ecrire_bloc` pour les rapports de parseur, `ecrire_ligne` pour la progression des téléchargements, `lister_journaux`/`lister_journaux_communs`/`lister_journaux_personnels` pour l'onglet Logs), `appariement` (alignement G-D ↔ arrêts GTFS : fonction monotone `seq → étape` par programmation dynamique, confiance, blocs incertains, ancres manuelles, empreintes — pur, sans I/O), `registre_appariement` (persistance commune, statuts, synchronisation à l'import, lecture par le rapport), `registre_detours` (appariement des détours : signature indépendante du numéro d'évènement, choix humains imposés au pipeline G-D), `gd` (build_rows — adaptateur de `appariement` —, détours, applicabilité par parcours — `stop_ids=None` = arrêts GTFS inconnus → évènement présumé applicable, fail-safe ; placement des arrêts ajoutés via `insert_added_stops_inline` — source unique de la règle d'ancrage code/parenthèses), `gtfs` (lookup arrêts GTFS, `stops_for_parcours`, index `stops_index.json`), `gtfs_rt` (décodeur protobuf minimal du flux vehiclePositions, `parse_vehicle_positions`/`find_vehicle`), `journee` (groupes/lignes de service à partir d'une journée), `calendrier` (fichiers .ics par pièce de travail, écrits à l'import de la journée), `periodes` (calendrier de référence — listes/variations/fériés — et dérivation de l'identité d'une carte agent via `identite_ca(date, numero)`), `portail` (client HTTP persistant, validation et stockage sécurisé de session), `preparation` (rafraîchissement structuré, reprise des lignes et empreintes de rapports). La lecture des cartes agent PDF se fait directement dans `scripts/carte_agent.py` (parsing géométrique bbox via PyMuPDF).

L'application Streamlit est **multipages** : entrée `app/main.py`, une page par écran dans `app/pages/` (1 Ma journée · 2 Préparation · 3 Rapports · 4 Fichiers · 5 Logs · 6 Administration · 7 Appariement · 8 Détours), composants partagés dans `app/components/`. Zéro logique : la fraîcheur `info_gtfs`/`info_gd`, la résolution/rangement des cartes agent, le décodage GTFS-RT vivent tous dans le package `chauffeur/`. `app/main.py` déclare la navigation `st.navigation(_pages).run()` — l'entrée « Administration » n'est ajoutée qu'à un Chauffeur-admin — puis pose la configuration globale et le style ; chaque page appelle `bootstrap.initialiser_page()` qui applique la connexion (`app/components/connexion.py` : login, wizard premier lancement, déconnexion et changement de PIN dans la barre latérale) puis pose le **matricule de session** dans le contexte par thread de `chauffeur.depots`. Les pages obtiennent leurs emplacements via les accesseurs `bootstrap.journees_dir()`/`ca_dir()`/`notes_dir()`/`rapports_dir()`/`log_dir()`/`session_path()` — jamais les constantes de module.

1. **`split_sections()`** découpe l'entrée brute en sections, une par en-tête `Gauche-Droite / <ligne> <direction>`. Un seul collage peut donc contenir plusieurs lignes/directions.
2. **`GDParser`** traite une section :
   - `_extract_header` : lit ligne (ex. `195`, `85e`) et direction (`est|ouest|nord|sud`).
   - `_parse_parcours` / `_parse_single_parcours` : découpe par blocs `Parcours <nom>ID <n>`. Les **stations** sont les lignes terminées par un code d'arrêt à 5 chiffres (première = départ, dernière = arrivée) ; les **directions** sont les lignes `Gauche|Droite|Via - <rue>`. Les lignes `Imprimer` et `Date de mise à jour` sont ignorées (`SKIP_PATTERNS`).
   - `_load_existing_file` + `_generate_summary` : **diff intelligent** contre le fichier existant. Les parcours sont appariés par couple `(start_code, end_code)`, pas par `id` — c'est ainsi que le rapport détecte les ajouts (`+NOUVEAU`), suppressions (`-SUPPRIME`) et modifications (nom, nombre/contenu des directions).
   - `_save_file` écrase le fichier cible ; `_print_report` imprime le rapport lisible.

### Format des fichiers de sortie

Racine : `{ ligne, direction, routes: [ { line_number, direction, parcours: [...] } ] }`. La `direction` à la racine est en **minuscule** (`est`) ; celle dans `routes[]` est **capitalisée** (`Est`). Chaque parcours a `id, name, start, start_code, end, end_code, direction[]`, où `direction[]` est une séquence d'instructions GPS `"Via - <rue>"`, `"Gauche - <rue>"`, `"Droite - <rue>"`.

### Documentation des formats de données

- `data/Gauche-Droite/CLAUDE.md` — spécification détaillée du format JSON G-D (nommage, sémantique, FAQ). Note : elle documente `{ligne}_{direction}.json` mais les fichiers réels utilisent le préfixe `gd` → `gd<ligne>_<direction>.json`.
- `docs/gabarits/gauche-droite.json` — gabarit versionné pour créer un fichier G-D manuellement.
- `docs/format-evenements.md` — spécification versionnée du format JSON des événements (champs `evenement_id`, `titre`, `motif`, `effectif`, `arrets_annules`, `arrets_ajoutes`, `description_gd`, dates ISO 8601 et variantes d'un même ID). Nommage : `{ligne}_{direction}.json` (sans préfixe, contrairement aux G-D).
- `docs/gabarits/evenements.json` — gabarit versionné pour créer un fichier d'événements manuellement.
- `docs/livraison.md` — branches, livraisons et déploiement : une branche par sujet depuis `main`, branche `release/` éphémère, validation de l'image, tags `prod-AAAA-MM-JJ`, retour arrière, correctif urgent. À suivre pour toute livraison.

## Conventions

- **Gauche-Droite** : `gd<ligne>_<direction>.json` (avec préfixe `gd`), direction en minuscule (`est|ouest|nord|sud`), ligne avec `e` minuscule si applicable (`85e`). Un fichier par direction.
- **Événements** : `<ligne>_<direction>.json` (sans préfixe), même convention de direction/ligne.
- **Journées** : `data/<matricule>/journees/journee-YYYY-MM-DD.json` (sortie de `parse_journee.py` ; legacy : `data/journees/`).
- **Cartes agent** : identifiées par `(numéro, liste/variation, jour-type)` via `chauffeur.periodes.identite_ca()`, pas par leur seule date — un même numéro peut désigner des cartes différentes selon la liste et le jour-type (semaine/samedi/dimanche/variation). Nommage `data/<matricule>/ca/<numéro>_<groupe_id>_<jour_type>.pdf` (+ `-annotee.pdf`), les deux copies conservées ; une identité déjà présente est refusée à l'écrasement sauf action explicite « remplacer » (sauvegarde `.bak`). Les fichiers `carte-agent-YYYY-MM-DD.pdf` restent le nommage des imports antérieurs à cette refonte (non migrés, lus en repli par `get_ca_info()` ; legacy : `data/ca/`).
- **Journaux d'importation** : un fichier par type d'import, nommé d'après le parseur qui le produit — `parse_event.log` (y compris pour `refresh_events.py`, même parseur), `parse_gd.log`, `parse_journee.log`, `carte_agent.log`, `fetch_gtfs.log`, `fetch_gtfs_rt.log`, `appariement.log`. En ajout, sans rotation. **Deux familles** : `data/log/` (commun, flotte — G-D, Événements, GTFS, GTFS-RT, appariements, `SOURCES_COMMUNES`) et `data/<matricule>/log/` (personnel — journée, carte agent ; legacy : `data/log/`). Écrits uniquement via `chauffeur.journal` ; consultables dans la page Logs (journaux communs et personnels réunis, étiquetés). `scripts/migrer_logs_flotte.py [--dry-run]` rapatrie les journaux de flotte restés dans `data/<matricule>/log/` (cible existante → `<source>.N`, jamais d'écrasement).
- **Placement des arrêts ajoutés** (`arrets_ajoutes` → ligne verte du rapport) : ancrer par ordre de fiabilité décroissante — (1) le **code d'arrêt** cité par une étape du détour (« TERMINUS TEMPORAIRE STATION SHERBROOKE (52506) », « ... ARRÊT 53016 ») est une ancre exacte et l'emporte sur tout ; cité par la 1re étape le terminus est le **départ** → l'arrêt la précède, cité plus loin c'est l'**arrivée** → l'arrêt la suit ; (2) sinon les rues **entre parenthèses** du nom (« Station Papineau (Cartier / Sainte-Catherine) ») ; (3) sinon le nom lui-même. Pour un nom « A / B », c'est d'ordinaire la 1re rue qu'emprunte la ligne, mais un détour peut réquisitionner un arrêt situé sur la rue **perpendiculaire** à son parcours régulier (« Joliette / de Rouen » desservi par un détour circulant sur de Rouen) : si la 1re rue n'ancre sur aucune étape du détour, on **réessaie avec la rue transversale** comme rue empruntée (rôles échangés) avant d'abandonner. Ne jamais se fier au nom d'une **station** : il nomme la station, pas la rue où l'arrêt est planté (« Station Sherbrooke » est sur Berri) — et comme une station porte le nom d'une rue que la ligne emprunte, s'y fier place l'arrêt au mauvais coin sans signal d'erreur. Nom de lieu sans intersection exploitable → arrêt **non placé** (il ressort dans les alertes) plutôt que deviné.
- **Teinte des arrêts touchés** : rouge barré = l'arrêt disparaît (« Détour avec annulation d'arrêt », « Annulation d'arrêts ») ; ambre non barré = l'arrêt reste desservi (« Arrêt déplacé », « Information chauffeur » — le portail employé les liste dans `arrets_annules` alors que le chauffeur doit s'y arrêter). Titre inconnu → rouge (fail-safe).
- **Calendrier de référence** : `data/reference/periodes_<AAAA>.json` (un fichier par année : listes, variations, fériés), lu par `chauffeur.periodes`. Les fériés relèvent de l'année de la date, mais une **semaine** (lundi → dimanche) relève du calendrier de l'année de son **lundi** (le dimanche 2027-01-03 appartient à la semaine « Jour de l'an » du calendrier 2026) ; un calendrier de l'année du lundi absent est ignoré. Nouvelle année = déposer le fichier, aucun code à modifier ; le fichier de l'année de la date est obligatoire (`FileNotFoundError` sinon).
- **Points de relève** : `data/reference/points_de_releve_<AAAA>.json` (**non versionné**, ignoré par git : gabarit fictif dans `docs/gabarits/reference/` ; de même `garages.json` et `stations_metro.json` ; sans eux l'app fonctionne et affiche les codes ; un fichier par année, garage → lignes/code/lieu), lu par `chauffeur.reference.lieu_point_releve(code, garage, jour=...)` : le fichier de l'année de la journée s'applique, sinon le plus récent d'une année antérieure (reconduction). Nouvelle année = déposer le fichier, aucun code à modifier. Test : `python3 tests/test_reference.py`.
- **Rapports journaliers v1** : `data/<matricule>/rapports/rapport-YYYY-MM-DD.pdf`.
- **Rapports journaliers v2** : `data/<matricule>/rapports/rapport-v2-YYYY-MM-DD.{html,pdf}` (ou `rapport-v2-DATE-LIGNE-DIR-idN.html` pour un rapport mono-groupe).
- **Notes** (`chauffeur.notes`) : fichiers indexés par clé → `{"note": str, "maj": "YYYY-MM-DD"}` (entrée retirée si texte vide) — `data/<matricule>/notes/carte_agent.json` (clé = identité de la carte `numero_groupe_id_jour_type` via `chauffeur.ca.cle_note_carte()` ; la note suit la carte réutilisée d'une journée à l'autre, listes/variations/fériés donnant des identités distinctes ; repli sur le nom legacy `carte-agent-YYYY-MM-DD` si l'identité n'est pas calculable) et `data/<matricule>/notes/journee.json` (clé = date ISO, note propre à la journée). Éditées dans la page Ma journée (legacy : `data/notes/`).
- JSON écrit avec indentation 2 espaces et accents préservés (`ensure_ascii=False`).
- Préférer l'import via les scripts à l'édition manuelle, pour garantir la normalisation et le rapport de changements.

## Dépôt public : confidentialité et licence

Le dépôt est publié sous AGPL-3.0 (`LICENSE`, `NOTICE.md`, `THIRD_PARTY_NOTICES.md`). Règles pour tout ajout :
- **Jamais** de secret, clé API, cookie, hôte, adresse IP, compte, chemin de production, ni de vulnérabilité non corrigée dans un fichier versionné.
- **Jamais** de données réelles (journées, cartes agent, noms ou matricules de collègues, contenu du portail employé) : jeux d'essai **synthétiques ou anonymisés** (matricules fictifs 4xxxx). Les fiches de recette réelles vont dans un dépôt privé ; `docs/recettes/gabarit-build.md` sert de modèle.
- Nom du produit : « Chauffeur Mtl-AU ». Ne pas réintroduire « STM » comme marque ; les mentions de la STM se limitent aux URLs, à la désignation des sources de données ouvertes et à l'attribution CC BY (`chauffeur/avis.py`, source unique des textes d'avis).
- Notes personnelles locales : `CLAUDE.local.md` (ignoré par git).
