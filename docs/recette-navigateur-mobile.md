# Recette navigateur et mobile

Cette recette manuelle complète les tests automatisés avant une livraison,
notamment après une mise à jour de Streamlit ou de l'interface. Elle vérifie les
interactions dans un vrai navigateur et sur un téléphone. Sa rédaction ne vaut
pas exécution : les résultats de chaque image sont consignés séparément dans
`docs/recettes/` et ne valent pas validation d’une image ultérieure.

## Préparer l'essai

- Utiliser l'image candidate ayant passé les vérifications de
  [la procédure de maintenance](dependances.md), puis relever son identifiant.
  Pour la mise à jour actuelle : Python 3.12.16 / Streamlit 1.66.1, image locale
  `chauffeur-mtl-au:validation-1.66.1` si elle est encore disponible.
- Lancer une instance distincte avec un volume de données d'essai, sans monter
  le `data/` de production ni le `.env` personnel. Utiliser un port distinct si
  l'application habituelle fonctionne déjà.
- Préparer deux comptes locaux de test, une journée dans la fenêtre J−2/J+5,
  une journée plus ancienne, deux numéros d'autobus avec des notes distinctes,
  un texte de journée importable et un PDF de carte agent compatible avec la
  journée choisie. Prévoir les G-D, événements et données GTFS nécessaires aux
  rapports. Les cas figés de `tests/` peuvent servir de point de départ.
- Tester avec le navigateur habituel sur ordinateur et sur un vrai téléphone.
  Consigner leurs versions et le thème. La réduction d'une fenêtre sur ordinateur
  ne remplace pas le test du clavier tactile.
- Le scénario portail demande une session réelle du portail employé utilisable par la personne
  qui fait l'essai. Enregistrer ses cookies uniquement dans l'instance d'essai ;
  ne jamais les mettre dans le compte rendu, une capture ou Git. Sans accès au
  portail, inscrire « bloqué » pour ce scénario.

## Scénarios réutilisables

### R01 — Connexion et navigation

1. Se connecter au premier compte de test.
2. Ouvrir Ma journée, Préparation d'une journée, Rapports, Fichiers et Logs,
   puis revenir à Ma journée.
3. Enregistrer une note de journée, changer de page puis revenir à cette date.
4. Se déconnecter et se connecter au second compte.

**Attendu :** pages accessibles sans exception, note enregistrée retrouvée pour
le premier compte, aucune donnée personnelle du premier compte affichée au
second. La déconnexion redemande l'authentification. Administration apparaît
uniquement pour un compte administrateur.

### R02 — Choix et saisie d'une date

1. Dans Ma journée, sélectionner une date proposée.
2. Saisir la date ancienne préparée au format `AAAA-MM-JJ`, puis valider avec
   Entrée (ou la touche correspondante du clavier tactile).
3. Saisir une date valide sans journée enregistrée, puis `2026-02-30`.
4. Revenir à une date enregistrée.

**Attendu :** la bonne journée s'affiche pour les deux premières étapes ; la
date absente donne une information explicite et la date invalide un avertissement.
Il reste possible de sélectionner une journée après ces messages.

### R03 — Notes lors d'un changement d'autobus

1. Dans une pièce de Ma journée, sélectionner l'autobus A et vérifier sa note.
2. Saisir un brouillon distinct dans sa note sans l'enregistrer, puis passer à B.
3. Vérifier la note de B, la modifier et enregistrer avec le bouton de la note.
4. Revenir à A, puis à B ; changer de page et revenir pour relire les notes.
5. Refaire le changement depuis A vers un autobus sans note et enregistrer sa
   note vide, sans y saisir le brouillon de A.

**Attendu :** B affiche sa propre note et conserve la modification enregistrée ;
la note enregistrée de A reste intacte. Le brouillon de A ne passe jamais à un
autre autobus ; un autobus sans note présente un champ vide. Ne pas confondre
le bouton d'enregistrement du numéro d'autobus et celui de sa note.

### R04 — Imports de journée et de carte agent

1. Dans Préparation d'une journée, importer le texte de journée préparé.
2. Ouvrir cette date dans Ma journée et vérifier les pièces et horaires.
3. Dans Préparation, déposer le PDF brut dans « Fichier carte agent (PDF) »,
   puis choisir « Annoter la carte ».
4. Ouvrir et télécharger le PDF produit.

**Attendu :** confirmation d'import, journée lisible, carte rangée et PDF
ouvrable avec les annotations attendues. Si l'essai utilise « Sans GTFS
(surlignage seulement) », le noter : cet essai ne valide pas les horaires GTFS.

### R05 — Aperçu et téléchargement des rapports

1. Pour la journée préparée, générer les rapports v1 et v2 depuis Rapports,
   en essayant les sorties HTML et PDF proposées pour le v2.
2. Lire les aperçus, puis télécharger et ouvrir les fichiers.
3. Depuis Ma journée, ouvrir aussi un rapport de trajet.

**Attendu :** contenu correspondant à la journée ou au trajet choisi,
accents et tableaux lisibles, aperçu utilisable et téléchargements non vides
qui s'ouvrent dans leur lecteur. Les commandes restent accessibles sur téléphone.

### R06 — Session portail et reprise

1. Dans l'instance d'essai, partir sans session portail valide et lancer une
   récupération de journée depuis Préparation.
2. Dans le dialogue de renouvellement, essayer un champ Cookie vide, puis Annuler.
3. Relancer l'opération, saisir un cookie valide du portail employé et choisir
   « Valider et reprendre ».

**Attendu :** ouverture du dialogue, avertissement pour le champ vide, annulation
sans blocage. Après validation, le dialogue se ferme, l'opération reprend et la
journée récupérée s'affiche. Distinguer une indisponibilité du portail d'une
erreur de l'application dans le compte rendu.

### R07 — Utilisation sur téléphone

1. Refaire R01 à R05 sur téléphone ; tester aussi le dialogue R06 si la session
   nécessaire est disponible.
2. Ouvrir le menu latéral, les listes et les sections repliables ; saisir une
   date et une note avec le clavier tactile.
3. Vérifier le défilement, les boutons et les aperçus en portrait puis en paysage.
4. Vérifier la lisibilité en thèmes clair et sombre, en consignant les défauts
   connus comme les nouveaux.

**Attendu :** texte lisible, clavier utilisable, validation possible, boutons
atteignables et aucun contenu indispensable inaccessible. Un tableau large
peut défiler horizontalement si tout son contenu reste consultable.

## Fiche d'exécution à recopier pour chaque livraison

Conserver un compte rendu daté, par exemple dans
`docs/recettes/AAAA-MM-JJ-version.md`. Garder les résultats précédents pour
l'historique. Ne joindre que des observations et captures sans données privées.

- Date et personne ayant effectué l'essai : à renseigner
- Commit du code testé et modifications locales éventuelles : à renseigner
- Image Docker (tag et identifiant/digest) : à renseigner
- Versions Python / Streamlit : à renseigner
- Ordinateur : système, navigateur et version : à renseigner
- Téléphone : modèle, système, navigateur et version : à renseigner
- Jeux de données d'essai et options (GTFS, thèmes) : à renseigner

Statuts : **non exécuté**, **réussi**, **échoué**, **bloqué**. Documenter tout
blocage ; un essai non exécuté ou bloqué ne constitue pas une réussite.

| Scénario | Ordinateur | Téléphone | Observations / anomalie |
| --- | --- | --- | --- |
| R01 — Connexion et navigation | non exécuté | non exécuté | |
| R02 — Dates | non exécuté | non exécuté | |
| R03 — Notes d'autobus | non exécuté | non exécuté | |
| R04 — Imports | non exécuté | non exécuté | |
| R05 — Rapports | non exécuté | non exécuté | |
| R06 — Portail | non exécuté | non exécuté | |
| R07 — Ergonomie mobile | sans objet | non exécuté | |

Pour chaque anomalie : indiquer le scénario et l'étape, le résultat attendu,
le résultat observé, l'appareil concerné et le commit correctif le cas échéant.

**Décision de livraison :** à renseigner avec les problèmes restant ouverts.
La recette est complète quand les essais requis ont réussi. Toute exception
doit être explicitement documentée dans la décision, sans marquer l'essai réussi.
Après correction, rejouer le scénario en échec et les parcours affectés sur la
nouvelle image ; déployer l'image finalement validée sans la reconstruire.

## Transformer une anomalie en test de régression

Lorsqu'un défaut reproductible est découvert, ajouter si pertinent un test
automatisé qui échoue avant correction et réussit après. Utiliser les suites
existantes (domaine ou AppTest) lorsque cela suffit ; conserver l'essai manuel
pour le rendu, le tactile et les échanges réels avec le portail employé. Les notes d'autobus
sont déjà couvertes dans `tests/test_durees_app.py`.

L'automatisation de parcours navigateur pourra être ajoutée progressivement ;
cette recette n'introduit pas de nouvel outil ni de dépendance de test.

## R08 — Explorateur Fichiers et périodes

Préparer au moins 200 fichiers synthétiques répartis entre plusieurs périodes,
avec une journée sans service, une carte normale, une variation, un férié, une
ancienne carte `carte-agent-DATE-surligné.pdf`, un nom non reconnu et des PDF/HTML.
Utiliser deux comptes de test (administrateur et chauffeur).

- Ouvrir Cartes agent puis Journées : la période en cours à Montréal est
  sélectionnée. Changer de période, puis de catégorie et revenir : le choix est
  conservé. Une période vide ne provoque aucun changement automatique.
- Vérifier les variations et fériés dans leur liste et via le filtre Régime.
  Vérifier Toutes les périodes et Période indéterminée.
- Rechercher, trier et parcourir plusieurs pages de dix fichiers. Sélectionner un
  fichier puis modifier les filtres : aucun aperçu ne doit désigner un autre
  fichier par erreur. Les aperçus PDF, HTML, journées, G-D et événements sont
  disponibles sans télécharger chaque document au préalable.
- Modifier une journée, changer de catégorie puis revenir : le brouillon est
  conservé. Enregistrer, vérifier la sauvegarde et le contenu. Essayer un JSON
  invalide et une modification concurrente : l'enregistrement doit être refusé.
- Vérifier la suppression avec annulation puis confirmation, et la purge avec
  liste explicite des fichiers. Le compte chauffeur ne peut pas modifier,
  supprimer ou purger les fichiers communs ; le compte admin le peut.
- Préparer un export couvrant plusieurs périodes : la grille présente toutes les
  pièces de l'intervalle ; le CSV ne dépend ni de la page ni des filtres de période.
- Répéter sur téléphone physique, en portrait/paysage et thèmes clair/sombre :
  liste au-dessus de l'aperçu, boutons accessibles, clavier et lecteur PDF
  utilisables. Un viewport mobile émulé ne remplace pas cet essai tactile.

Reporter R08 dans la fiche de recette de la livraison. La présence de ce scénario
ne signifie pas qu'il a été exécuté.

## Compléments pour la livraison Fichiers du 22 septembre 2026

- R04 puis R08 : annoter une carte avec PyMuPDF, la retrouver dans Fichiers,
  la lire et la télécharger ; vérifier les annotations dans le PDF téléchargé.
- R05/R07/R08 : vérifier un ancien rapport HTML au fond initialement transparent
  et un rapport nouvellement généré, dans Fichiers et Ma journée, ainsi que
  l’aperçu de Rapports. Répéter en clair/sombre.
- Vérifier les tableaux d’événements dans Fichiers, Pièces de travail et les
  résultats de rafraîchissement : texte, lignes alternées, états et instructions
  doivent rester lisibles en clair/sombre.
- R01/R08 : ouvrir Administration avec le compte administrateur, vérifier
  tableau, sélection de compte et boutons en portrait/paysage ; vérifier
  l’absence d’accès pour le compte chauffeur.
- Vérifier le healthcheck Docker sur l’image candidate et consigner son ID.
  Un état sain confirme la réponse du serveur, pas la réussite des parcours.
