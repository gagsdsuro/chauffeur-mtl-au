# Recette du 16 septembre 2026 — renouvellement de session

## Notes exécution

```bash
docker build -t chauffeur-stm:recette-7db57ea .
docker image inspect chauffeur-stm:recette-7db57ea --format '{{.Id}}'

mkdir -p /tmp/chauffeur-stm-recette-data

docker run -d --name chauffeur-stm-recette \
  --user "$(id -u):$(id -g)" \
  -p 8502:8501 \
  -e TZ=America/Toronto \
  -e CHAUFFEUR_MODE_STRICT=1 \
  -v /tmp/chauffeur-stm-recette-data:/app/data \
  chauffeur-stm:recette-7db57ea

mkdir /tmp/chauffeur-stm-recette-data/reference

cp data/reference/periodes_stm_2026.json /tmp/chauffeur-stm-recette-data/reference/.
```

Sur ordinateur : http://localhost:8502 si Docker tourne sur cet ordinateur. Avec VS Code connecté en SSH, transfère le port 8502 depuis l’onglet Ports.
Sur téléphone : http://<adresse-IP-du-serveur>:8502, si le téléphone peut joindre ce serveur. localhost sur le téléphone désigne le téléphone lui-même.

## Anomalie signalée pendant la préparation

Les comptes de test ont été créés. Après validation du cookie STM, la
récupération de journée reste bloquée. Le cookie a été retrouvé dans
`data/session/cookies.json`, alors que la page authentifiée utilise
`data/<matricule>/session/cookies.json`. Aucune journée ni journal d’import
n’était présent dans le volume d’essai au diagnostic.

Le dialogue Streamlit se réexécute indépendamment de la page : le contexte
matricule stocké par thread n’est pas garanti lors de sa validation.
Le correctif transmet au dialogue le chemin personnel résolu par la page.
Un test simule deux comptes et une validation sur un autre thread, puis
vérifie les fichiers sauvegardés et la demande de reprise.

## Version corrective

- Base : commit `7db57ea`, avec correctif local du dialogue et test associé.
- Image : `chauffeur-stm:recette-dialogue`.
- Identifiant : `sha256:b0bb2326916658b05ec28c78638d9145d4fb72d11d1e095a06f572604547ef9f`.
- Python / Streamlit : 3.12.14 / 1.64.0.
- Volume d’essai conservé : `/tmp/chauffeur-stm-recette-data`.
- Port : 8502.
- Navigateur et téléphone : à renseigner par la personne réalisant l’essai.
- Vérifications automatisées : 34/34 suites réussies dans l’image corrigée,
  sur copie isolée du dépôt ; sonde HTTP de l’instance remplacée : `ok`.

## Résultats manuels

- Création des comptes : réalisée par l’utilisateur.
- R06 : échec de la validation/reprise signalé pendant la préparation.

La recette est validée après reprise de R05 et R07 le 17 septembre 2026 par GD.
Le cookie du dossier commun n’a pas été réattribué automatiquement.

| Scénario | Ordinateur | Téléphone | Observations / anomalie |
| --- | --- | --- | --- |
| R01 — Connexion et navigation | **réussi** | **réussi** | |
| R02 — Dates | **réussi** | **réussi** | |
| R03 — Notes d'autobus | **réussi** | **réussi** | |
| R04 — Imports | **réussi** | **réussi** | |
| R05 — Rapports | **réussi** | **réussi** |Rapport journalier Erreur : Aucune journée trouvée dans /app/data/journees Fichier attendu : journee-2026-09-17.json. La section détour du rapport V2 (Rapport v2 — Aperçu(rapport-v2-2026-09-17-standard.html)) avec le thème "Dark" est pratiquement invisible (noir sur noir).  Même chose avec le rapport journalier (Aperçu — 94 Sud ID 7) par exemple et la colonne "Arrêt/Détour". C'est ok par contre avec le thème "Light". Anomalies de la première exécution : toutes deux corrigées et retestées avec succès le 17 septembre. |
| R06 — Portail | **réussi** | **réussi** | |
| R07 — Ergonomie mobile | sans objet | **réussi** |  |

- Date et personne ayant effectué l'essai : 16 et 17 septembre 2026 - GD
- Commit du code testé : `d49224e` (correctifs présents dans l’image avant leur commit)
- Image Docker finale : `chauffeur-stm:recette-rapports` ; identifiant consigné ci-dessous
- Versions Python / Streamlit : Streamlit 1.64.0 Python 3.12.14
- Ordinateur : système, navigateur et version : Windows 11, Chrome 152.0.7977.84
- Téléphone : modèle, système, navigateur et version : Pixel 8, Android 17, Firefox 155.0.1
- Jeux de données d'essai et options (GTFS, thèmes) : GTFS du 16 septembre 2026, Thème StreamLit "Dark" et "Light"
Données de référence: data/reference/periodes_stm_2026.json

## Correctifs après la première exécution — 17 septembre 2026

Le tableau ci-dessus présente les résultats finaux après reprise. R05 et R07
étaient en échec lors de la première exécution ; les anomalies sont conservées
dans les observations pour l’historique.

- Rapport journalier : la page transmet désormais explicitement le chemin de
  la journée du compte connecté au sous-processus de génération. Le test
  d'interface génère réellement un PDF pour chacun de deux comptes, avec une
  journée homonyme présente dans le dossier historique, et vérifie le compte
  sélectionné ainsi que l'emplacement personnel du PDF.
- Rapports HTML : fond blanc opaque et palette claire explicite dans les
  documents v2 (complets et par trajet) et G-D. Le fond sombre de l'application
  ne doit plus apparaître derrière leur texte sombre. La palette imprimable
  est conservée, quel que soit le thème de l'application.
- Nouvelle image : `chauffeur-stm:recette-rapports`, base `7db57ea` avec les
  correctifs locaux du dialogue et des rapports.
- Identifiant : `sha256:b7c98af541f75a1656d82b7b05101114cd661f3a21bf32cc9f841dd48648216d`.
- Validation : 34/34 suites réussies sous Python 3.12.14 / Streamlit 1.64.0,
  dont 11 tests d'interface. Instance remplacée sur le port 8502, données
  conservées et sonde HTTP `ok`.

**Reprise terminée : R05 et R07 réussis**, selon les essais manuels de GD
consignés le 17 septembre 2026. Les deux anomalies de R05 sont confirmées
corrigées ; R07 est réussi sur téléphone.

**Décision de recette :** validée pour l’image `chauffeur-stm:recette-rapports`
identifiée ci-dessus. Aucun blocage ne reste signalé dans cette recette.
Déployer cette même image sans reconstruction, après sauvegarde des données
et conservation de l’image précédente. Cette validation ne constitue pas
un déploiement en production.
