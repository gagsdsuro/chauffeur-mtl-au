# Préparation de la version Fichiers — 22 septembre 2026

> **Statut final — 23 septembre 2026 :** déploiement en production confirmé
> par l’utilisateur ; téléchargement PDF sous Firefox en HTTPS testé avec
> succès. Le dernier contrôle reporté est clôturé. Les étapes ci-dessous
> conservent l’historique de la recette.

## Note

Les commandes ci-dessous décrivent le lancement initial. Depuis le 23 septembre,
le conteneur de recette utilise `chauffeur-stm:candidate-20260923-csv` ; voir le
suivi en fin de fiche.

docker run -d --name chauffeur-stm-recette \
  --user "$(id -u):$(id -g)" \
  -p 8502:8501 \
  -e TZ=America/Toronto \
  -e CHAUFFEUR_MODE_STRICT=1 \
  -v /tmp/chauffeur-stm-recette-data:/app/data \
  chauffeur-stm:candidate-20260922

mkdir /tmp/chauffeur-stm-recette-data/reference
scp -r dockeradmin@gagsmicros5:/opt/docker/chauffeur-stm/data/50351/* /tmp/chauffeur-stm-recette-data/50351/.
scp -r dockeradmin@gagsmicros5:/opt/docker/chauffeur-stm/data/Gauche-Droite/* /tmp/chauffeur-stm-recette-data/Gauche-Droite/.
scp -r dockeradmin@gagsmicros5:/opt/docker/chauffeur-stm/data/Events/* /tmp/chauffeur-stm-recette-data/Events/.

cp data/reference/periodes_stm_2026.json /tmp/chauffeur-stm-recette-data/reference/.

## Périmètre

- Refonte Fichiers et modifications préexistantes conservées dans la copie testée.
- Six derniers usages `use_container_width` remplacés dans Administration.
- Imports et usages `fitz` migrés vers `pymupdf`, sans mise à jour de dépendance.
- Aperçu HTML commun à Fichiers, Ma journée et Rapports : palette claire explicite,
  y compris pour les anciens documents ; fichiers téléchargés inchangés.
- Tableau partagé des événements avec fond blanc et texte sombre explicites.
- README, CLAUDE, TODO et compléments de recette actualisés.

## Image candidate locale

- Tag : `chauffeur-stm:candidate-20260922`.
- ID relevé par Docker :
  `sha256:92710ae9ef9bbcf065c51a402b34551cb5cb4bb7c817ecd35453c1bab6286658`.
- Python 3.12.14, Streamlit 1.64.0 ; installation avec empreintes et `pip check`
  effectués par le Dockerfile.
- Code non committé copié dans un contexte isolé, sans `.env` ni données privées.
- Démarrage temporaire sans réseau ni port publié, références de test en lecture
  seule : état `healthy`, sonde Docker terminée avec code 0. Conteneur arrêté.
- Aucun déploiement effectué. La recette finale doit viser cette image ; toute
  modification ultérieure de code impose une nouvelle image et les contrôles
  affectés. Les modifications documentaires seules ne changent pas son code.

## Vérifications

- Suite complète dans l’environnement verrouillé existant : **37/37 réussies**.
- Confirmation sur l’image candidate, avec la même copie du code : **37/37 réussies**.
- Contrôles Chromium 153 ciblés : **réussis**. Dans Fichiers, ancien HTML sans
  styles et tableau d’événements vérifiés en clair/sombre par couleurs calculées
  et captures : fond blanc et texte sombre. Administration vérifiée en viewport
  390 × 844 : sélection d’un compte chauffeur, bouton de promotion accessible,
  absence de débordement global et d’exception. Aucun changement de rôle exécuté
  dans ce contrôle visuel. Le navigateur utilise la copie courante du code avec
  l’image d’outillage `chauffeur-stm:fichiers-browser`, pas l’image candidate.
  Plusieurs corrections du pilote ont été nécessaires : attente du thème,
  sélection conservée entre catégories, navigation avant réduction du viewport.
- Aucun usage `fitz` ni `use_container_width` restant dans `app/`, `scripts/`,
  `tests/`, README et CLAUDE.
- `git diff --check` réussi.

## Reste avant livraison

- Téléphone physique : portrait/paysage, clavier, aperçu et téléchargement de la
  carte annotée, administration et thèmes clair/sombre.
- Recette R08 : suppression/purge, changements de rôle et isolation dans un
  navigateur ; les contrôles serveur sont couverts par les suites automatisées.
- Vérifier visuellement les tableaux d’événements dans Pièces de travail et les
  résultats réels de rafraîchissement, ainsi que les aperçus de Ma journée et
  Rapports ; le composant de rendu est partagé avec Fichiers.
- Consigner les résultats dans la recette de livraison, sans assimiler une
  émulation mobile à un essai tactile ni le healthcheck à un test fonctionnel.

Les journaux et captures temporaires sont sous `/tmp/chauffeur-version-20260922*`.
Cette fiche constitue le suivi durable ; ces artefacts temporaires ne sont pas
versionnés.

## Confirmation utilisateur — aperçus sur téléphone

Sur Pixel 8 / Android 17, l’utilisateur confirme la lisibilité des aperçus
PDF, rapports HTML et événements en thèmes clair et sombre, en orientations
portrait et paysage : **réussi**. Cette confirmation porte sur les aperçus ;
elle ne clôt pas le défaut de téléchargement PDF observé avec Firefox en HTTP.

## Vérification des sauvegardes JSON — 23 septembre 2026

Contrôle en lecture seule dans `/tmp/chauffeur-stm-recette-data` : **réussi**
pour la présence et la lisibilité des sauvegardes issues des éditions testées.

- Deux sauvegardes horodatées distinctes de `journee-2026-09-21.json`,
  toutes deux valides et non vides (1 874 et 1 876 octets).
- Une sauvegarde horodatée de `Events/10_sud.json`, valide et non vide
  (2 181 octets).
- Comparaison avec les fichiers actuels : seul le nom de relève diffère pour
  la journée, et seul le titre du premier événement diffère pour les événements.
  Les autres champs sont conservés dans les sauvegardes examinées.
- Le code sauvegarde les octets de l’ancien fichier avant l’écriture atomique
  de la nouvelle version. Les copies PDF `.bak` préexistantes n’entrent pas dans
  ce contrôle des sauvegardes JSON de l’explorateur.

Aucune donnée de recette n’a été modifiée ni restaurée pendant cette vérification.
Ce contrôle ne constitue pas un essai de restauration.

## Confirmation utilisateur — suppression d’un fichier commun

**Réussi** : dans les données de recette, l’administrateur supprime un fichier
d’événements ; le fichier disparaît également de la liste consultée par le
compte Chauffeur. Cette confirmation porte sur la suppression individuelle,
pas sur la purge des fichiers communs.

## Confirmation utilisateur — purge des événements communs

**Réussi** : l’utilisateur confirme avoir testé avec succès la purge depuis
Événements → Entretien avec le compte administrateur dans l’instance de recette.

## Nouvelle image avec correctif CSV — 23 septembre 2026

- Image : `chauffeur-stm:candidate-20260923-csv`.
- ID : `sha256:194ffcf8bc751fee621d0fa76ac0cce2c608f731bb83261dc4b4f71f29baf50f`.
- Construction depuis une copie isolée du code courant, sans données personnelles
  ni `.env` dans le contexte ; changements existants du dépôt conservés.
- Correctif : une occurrence de chaque ligne d’autobus par pièce, dans l’ordre
  de première apparition, avant la limite de sept colonnes. Grille et CSV
  utilisent les mêmes valeurs.
- **37/37 suites réussies sur le code embarqué dans l’image** ; seuls les tests,
  le Dockerfile et les références de test étaient montés pour cette vérification.
  Le test de dédoublonnage fait partie de cette exécution.
- Python 3.12.14 / Streamlit 1.64.0 ; `pip check` réussi, healthcheck Docker
  `healthy` et réponse HTTP `ok`.
- Conteneur de recette `chauffeur-stm-recette` remplacé, port **8502** conservé,
  utilisateur `1000:1000`, mode strict et fuseau Montréal conservés.
  Même volume `/tmp/chauffeur-stm-recette-data:/app/data` ; données conservées.
- Ancien conteneur conservé arrêté sous
  `chauffeur-stm-recette-avant-csv-20260923` ; il partage le même volume et ne
  constitue pas une sauvegarde de ces données.
- Aucun déploiement de production effectué.

**Nouvel essai CSV : réussi, confirmé par l’utilisateur** sur
`chauffeur-stm:candidate-20260923-csv`. Après préparation d’un nouvel export,
les numéros de ligne apparaissent une seule fois par pièce dans la grille et
le CSV, dans l’ordre de première apparition ; les colonnes inutilisées restent
vides. Le défaut de doublons est clôturé pour cette image.

Le téléchargement PDF avec Firefox Android en HTTPS reste à vérifier séparément.
Les résultats de l’image précédente ne sont pas réattribués à cette nouvelle image.
Journaux temporaires : `/tmp/chauffeur-candidate-csv-build.log` et
`/tmp/chauffeur-candidate-csv-tests.log`.

## Décision utilisateur — contrôle Firefox Android en HTTPS

Le contrôle du téléchargement PDF avec Firefox Android en HTTPS est **reporté
à la production**, sur décision explicite de l’utilisateur. Il reste **non
exécuté** et devient **non bloquant pour la livraison** ; il ne doit pas être
présenté comme réussi ni le défaut observé en HTTP comme corrigé.

L’utilisateur ne souhaite pas mettre en place HTTPS en développement pour le
moment. Cette configuration sera réévaluée si le problème se manifeste en
production. Le téléchargement avec Chrome sur Pixel 8 / Android 17 a été
confirmé fonctionnel pendant la recette et constitue une solution de repli.

Cette décision documente l’exception de validation ; aucun déploiement n’est
réalisé par cette mise à jour de la fiche.

## Clôture de recette et préparation de livraison — 23 septembre 2026

Résultats confirmés par l’utilisateur pendant la recette : édition JSON avec
brouillon conservé, refus du JSON invalide, conflit concurrent, suppression avec
annulation puis confirmation, purge des rapports et événements, isolation des
comptes, restrictions Chauffeur, promotion et auto-destitution, édition d’un
événement commun par l’administrateur et consultation par le Chauffeur.
Les sauvegardes ont été examinées en lecture seule. Les aperçus sur téléphone
ont été validés dans les deux thèmes et orientations. Ces confirmations
complètent la liste initiale « Reste avant livraison », conservée pour historique.

Le correctif d’unicité des lignes du CSV a ensuite été validé par l’utilisateur
sur `candidate-20260923-csv`. Les 37 suites passent sur cette image. Le contrôle
Firefox Android en HTTPS est reporté explicitement à la production, sans
bloquer la livraison ; le défaut observé en HTTP n’est pas déclaré corrigé.

L’utilisateur autorise le commit et le déploiement. Image de livraison prévue :
`chauffeur-stm:livraison-2026-09-23`, identique à l’image candidate validée,
ID `sha256:194ffcf8bc751fee621d0fa76ac0cce2c608f731bb83261dc4b4f71f29baf50f`.
Code et tests comparés à la copie isolée validée : aucun écart.

Le déploiement n’est pas encore effectué : la tentative de connexion SSH à
`dockeradmin@gagsmicros5` a été refusée lors de l’autorisation d’exécution.
Ne pas confondre l’archive locale de livraison avec un déploiement réussi.

## Confirmation de production — 23 septembre 2026

L’utilisateur confirme avoir effectué le déploiement et testé avec succès le
téléchargement PDF sous Firefox en HTTPS. Ce résultat clôt le contrôle reporté
à la production. Le défaut observé dans l’environnement HTTP reste historique ;
aucune correction générale de Firefox ou du fonctionnement en HTTP n’est déduite
de cet essai.

Livraison préparée : `chauffeur-stm:livraison-2026-09-23`, commit applicatif
`f69a1f5`. Le déploiement et le résultat navigateur sont rapportés par
l’utilisateur ; aucune inspection distante supplémentaire n’a été réalisée.
Aucune mise en place de HTTPS en développement n’est prévue à ce stade.
