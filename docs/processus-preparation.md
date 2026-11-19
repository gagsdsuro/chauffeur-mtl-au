# Processus de préparation d'une journée

La préparation d'une journée combine une **chaîne semi-automatique**
(`chauffeur/preparation_auto.py`, sans Streamlit) et une **page de repli
manuel** (`app/pages/2_preparation.py`) qui permet de réitérer chaque étape
individuellement : réimporter une donnée spécifique, régénérer une sortie
(rapports, calendrier), ou intervenir sur les appariements.

Le **GTFS temps réel n'a pas sa place dans ce processus** : il sert au
repérage d'autobus dans « Ma journée », qui a son propre mécanisme de
récupération.

## Les 9 étapes

Ordre d'exécution de la chaîne semi-automatique (`ETAPES`) :

| # | Clé | Libellé | Bloquante ? | Produit / met à jour |
|---|-----|---------|-------------|----------------------|
| 1 | `journee` | Importer la journée | **oui** | `data/<matricule>/journees/journee-YYYY-MM-DD.json` |
| 2 | `calendrier` | Générer le calendrier (.ics) | non | `data/<matricule>/calendrier/<date>/<rang>-<pièce>.ics` |
| 3 | `gtfs_statique` | Mettre à jour les données GTFS statiques | non | `data/gtfs/gtfs_stm/` + manifeste (contextuel, voir plus bas) |
| 4 | `carte_agent` | Importer et annoter la carte agent | non | `data/<matricule>/ca/<numéro>_<groupe_id>_<jour_type>-annotee.pdf` |
| 5 | `gauche_droite` | Importer les G-D manquants ou périmés | **oui** si toujours absents | `data/Gauche-Droite/gd<ligne>_<direction>.json` |
| 6 | `evenements` | Importer les évènements | non | `data/Events/<ligne>_<direction>.json` |
| 7 | `appariement_arrets` | Apparier les arrêts G-D ↔ GTFS | non (intervention) | `data/Appariements/<ligne>_<dir>_<id>.json` |
| 8 | `appariement_evenements` | Apparier les évènements ↔ arrêts GTFS | non (intervention) | `data/Appariements/detours/<ligne>_<dir>.json` |
| 9 | `rapport_v2` | Générer le rapport journalier v2 | **oui** | `data/<matricule>/rapports/rapport-v2-YYYY-MM-DD.html` |

Une étape **bloquante** arrête la chaîne ; les autres problèmes sont des
**avertissements** et la chaîne continue. Les étapes 7-8 peuvent aussi
s'arrêter sur `intervention_requise` (voir « Appariements »).

## Disposition de la page

Le haut de page est inchangé quel que soit l'état : bandeau contexte
(session portail · liste active · GTFS statique — source unique de ces
informations), sélecteur de date, bouton « Lancer la préparation
semi-automatique » + bilan repliable, puis « État de la préparation »
(journée, carte agent, G-D, évènements, rapports).

Le reste de la page est le **repli manuel**, organisé en trois groupes :

```
Imports                      Appariements        Rapports et calendrier
  1 — Journée                  6 — Arrêts          8 — Événements calendrier
  2 — Arrêts et horaires       7 — Événements      9 — Rapports
  3 — Carte agent
  4 — Gauche-Droite
  5 — Évènements
```

- Le calendrier (.ics) est généré tôt dans la chaîne (étape 2, dès l'import
  de la journée) mais présenté en fin de page avec les autres **sorties**
  (étape 8 de la page), avec téléchargement par pièce ou en .zip.
- La section « 2 — Arrêts et horaires » ne couvre que le **GTFS statique**
  (fraîcheur contextuelle + bouton de téléchargement).
- Les sections 4 et 5 suivent le même modèle : bouton de récupération
  portail (avec reprise après renouvellement de session) puis import manuel
  de secours (texte brut collé, parseurs `parse_gd` / `parse_event`).
- « 9 — Rapports » : cases à cocher **rapport journalier (PDF), décoché par
  défaut** et **rapport v2 (HTML), coché par défaut**, puis « Générer les
  rapports sélectionnés ». La chaîne semi-automatique, elle, ne génère que
  le v2 (niveau `standard`).

## Statuts d'une étape

`ResultatEtape.statut` (`chauffeur/preparation_auto.py`) :

| Statut | Signification | Effet sur la chaîne |
|--------|---------------|---------------------|
| `ok` | Étape réussie | continue |
| `ignore` | Rien à faire (déjà présent/à jour, aucune ligne de service, hors fenêtre…) | continue |
| `avertissement` | Échec non bloquant (étape de `NON_BLOQUANTES`) | continue |
| `bloque` | Erreur bloquante (journée invalide, G-D requis absents, rapport v2 impossible) | **arrêt** |
| `session_expiree` | Session portail expirée | **arrêt**, dialogue de cookie puis reprise |
| `intervention_requise` | Appariements à réviser manuellement | **arrêt**, reprise après intervention |

`STATUTS_ARRET = ("bloque", "session_expiree", "intervention_requise")`.
Toute exception inattendue d'une étape est convertie en `avertissement`
(étape non bloquante) ou `bloque` (étape bloquante) — une étape ne fait
jamais planter la page.

## GTFS statique : mise à jour contextuelle

Le GTFS statique n'est **pas** rafraîchi à chaque préparation ni sur un
rythme hebdomadaire : il suit le **calendrier de publication de la STM**,
environ **10 jours avant chaque début de liste**
(`DELAI_PUBLICATION_GTFS_JOURS = 10`, `chauffeur/periodes.py`).

- `liste_active_pour_date(jour)` — début de liste applicable (même logique
  que `identite_ca` : la semaine relève du calendrier de l'année de son
  lundi ; en semaine de variation, le GTFS de la liste précédente reste
  valide).
- `publication_gtfs_pour_liste(debut)` / `publication_gtfs_pour_date(jour)`
  — date de publication = début de liste − 10 jours.
- `gtfs_disponible_pour_date(jour, date_ref)` — le GTFS de la liste active
  est-il téléchargeable à `date_ref` (aujourd'hui par défaut) ?

**Transition** : pendant les 10 jours précédant un début de liste, deux
versions du GTFS coexistent (l'ancienne en vigueur, la nouvelle à venir).
On utilise toujours celui de la **liste active pour la date cible**, pas
celui de la liste à venir.

Exemple 2026 (débuts de liste → publication GTFS) :

| Début de liste | Publication GTFS (J−10) |
|----------------|-------------------------|
| 2026-01-05 | 2025-12-26 |
| 2026-03-23 | 2026-03-13 |
| 2026-06-15 | 2026-06-05 |
| 2026-08-24 | 2026-08-14 |
| 2026-10-26 | 2026-10-16 |

`info_gtfs(date_cible=...)` (`chauffeur/depots.py`) ajoute au contexte de
fraîcheur : `liste_active`, `publication_cible`, `fenetre_ouverte`
(publication atteinte), `gtfs_a_jour` (le manifeste couvre la liste active),
`mise_a_jour_requise` (fenêtre ouverte **et** pas à jour).
`scripts/fetch_gtfs.py` inscrit `liste_cible` au manifeste.

Décision de l'étape `gtfs_statique` :

1. Calendrier de référence introuvable → `ignore`.
2. Hors fenêtre de publication → `ignore`.
3. GTFS déjà à jour pour la liste active → `ignore`.
4. Sinon téléchargement (`fetch_gtfs.py`) ; échec → `avertissement`,
   succès → `ok`.

`FRAICHEUR_GTFS_JOURS = 7` est conservé pour compatibilité (affichage
historique) mais **n'est plus utilisé** pour décider la mise à jour.

La carte agent utilise le GTFS statique pour l'annotation « départ
précédent » (rouge) ; sans GTFS, l'annotation se limite au surlignage
(option « Sans GTFS » du dépôt manuel). L'absence de GTFS ne bloque donc
pas la carte agent, mais bloque le rapport v2.

## Appariements et intervention manuelle

Les appariements sont **synchronisés automatiquement** à chaque préparation
(`registre_appariement.synchroniser_ligne`,
`registre_detours.synchroniser_evenements_ligne`) pour les lignes de
service de la journée.

- Si des parcours restent « incertain » / « à revalider »
  (`parcours_a_reviser`) ou des détours à réviser (`detours_a_reviser`),
  l'étape retourne `intervention_requise` : la chaîne s'arrête, le bilan
  liste les éléments à réviser.
- L'intervention se fait dans les pages **Appariement des arrêts** et
  **Appariement des détours** (choix humains, validation), puis
  « Reprendre » relance la chaîne à l'étape interrompue.
- L'appariement des évènements **dépend de celui des arrêts** : la chaîne
  s'arrêtant à `appariement_arrets` en cas d'intervention, les détours ne
  sont appariés qu'une fois les arrêts révisés ; le pipeline des détours
  s'appuie d'ailleurs sur les appariements G-D ↔ GTFS (choix humains imposés).
- GTFS statique absent → `appariement_arrets` est `ignore` (appariements
  non calculés), pas une erreur.

## Reprise après interruption

Le résultat `ResultatSemiAuto` est sérialisable (`to_dict` / `from_dict`) :

- `reprise_a` — clé de l'étape où la chaîne s'est arrêtée (`None` =
  terminée). À la reprise (`executer_semi_auto(..., precedent=...)`), les
  étapes antérieures sont conservées telles quelles et l'exécution repart
  de `reprise_a`. Si le fichier journée a disparu entre-temps, on repart de
  `journee`.
- Dans l'app, le bilan est stocké dans `st.session_state[PREP_SEMI_AUTO]` ;
  le bouton **« Reprendre »** rejoue la chaîne avec le résultat précédent.
- **Session expirée** : `operation_portail` de type `semi_auto` mémorise le
  résultat ; le dialogue de cookie demande le renouvellement, puis
  `reprise_en_attente("semi_auto", date)` relance automatiquement à l'étape
  interrompue. Les évènements déjà récupérés sont conservés
  (`ResultatRafraichissement.restantes` dans `donnees`) et ne sont pas
  re-téléchargés.
- **« Continuer sans les évènements du portail »** (bouton visible si
  `reprise_a == "evenements"`) : `sans_portail=True` — l'étape évènements
  devient un avertissement et la chaîne poursuit avec les fichiers présents.

## Tests

- `tests/test_preparation_auto.py` — chaîne complète, blocages,
  avertissements, reprises, `sans_portail`, appariements (scénarios patchés,
  hermétiques).
- `tests/test_page_preparation_auto.py` — rendu de la page et bilan.
- `tests/test_periodes_gtfs.py` — liste active, publication J−10, fenêtres
  de transition.

Lancer `python3 tests/run_all.py` (et `python3 tests/test_dockerfile.py`)
avant toute demande de fusion.