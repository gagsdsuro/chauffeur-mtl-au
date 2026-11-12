# Audit de compatibilité Streamlit — 16 septembre 2026

**Suivi :** la régression des notes a été corrigée et le déploiement est
désormais verrouillé sur Python 3.12.14 / Streamlit 1.64.0 ; voir les sections
de suivi en fin de document. Les résultats initiaux ci-dessous décrivent
l'état avant ces changements.

L'élargissement des tests a révélé une régression fonctionnelle des notes
d'autobus à partir de Streamlit 1.50. La suite habituelle ne couvre pas cette
transition, même lorsqu'elle passe entièrement. La migration ne doit donc pas
être considérée comme validée sur ce seul résultat.

## Versions réellement vérifiées

`requirements.txt` indique `streamlit>=1.50`, sans plafond ni verrouillage.
Ce changement de minimum n'installe pas précisément la version 1.50. L'ancienne
contrainte `>=1.35` autorisait déjà les versions plus récentes.

| Environnement | Vérification | Résultat |
| --- | --- | --- |
| Local : Python 3.14.4, Streamlit 1.62.0 | `python3 tests/run_all.py` | 32/32 suites réussies |
| Conteneur temporaire : Python 3.12.14, Streamlit 1.50.0 | Même suite sur une copie du dépôt | 31/32 ; échec de `test_logs_app.py` dans AppTest |
| Même conteneur, Streamlit 1.50.0 | Scénario Logs avec adaptation temporaire de la relance AppTest | Réussi |
| Python 3.12.14, Streamlit 1.49.1 puis 1.50.0 | Changement d'autobus et enregistrement de sa note | Correct en 1.49.1 ; mauvaise note en 1.50.0 |
| Python 3.14.4, Streamlit 1.62.0 | Même scénario de note | Même régression |
| Streamlit 1.49.1, 1.50.0 et 1.62.0 | Ouverture de `app/main.py` et des six pages avec AppTest, données absentes | Aucune exception ; Administration affiche son garde-fou sans connexion admin |

La compilation des modules `app/` réussit également.

L'image Docker locale `chauffeur-mtl-au-chauffeur-mtl-au:latest` contient Python 3.12.14
et Streamlit 1.64.0. Cela ne prouve pas la version d'un éventuel service déployé.
Les essais 1.49.1/1.50.0 utilisent un environnement virtuel temporaire dans un
conteneur issu de cette image, avec résolution des dépendances de chaque version.
Ce n'est pas une reconstruction intégrale de l'image de production.

Les essais Docker montent uniquement une copie du code, des tests et de
`data/reference/`. Aucun fichier personnel ni `.env` n'y est copié.
Les comptes et notes des scénarios sont synthétiques et temporaires.
Les modifications aux tests d'authentification et de journaux déjà présentes
dans le répertoire de travail au début de l'audit sont incluses dans la copie.

## Régression confirmée : note associée au mauvais autobus

Emplacement : `app/pages/1_ma_journee.py`, définition de `note_v_key` et
enregistrement via `sauvegarder_note_voiture`.

1. Le bus `38013` possède « Note du bus A » ; `39999` possède « Note du bus B ».
2. Ouvrir une journée dont une pièce utilise `38013`.
3. Remplacer le numéro d'autobus par `39999`.
4. Le libellé devient « Note — bus 39999 », mais le champ conserve « Note du bus A ».
5. Enregistrer la note écrase celle de `39999` avec « Note du bus A ».

Ces étapes, y compris l'écriture finale, ont été reproduites avec AppTest sur
des fichiers temporaires. En 1.49.1, le champ et la sauvegarde utilisent bien
« Note du bus B ».

Streamlit 1.50 introduit une identité fondée sur la clé pour plusieurs widgets,
dont `st.text_area` : changer le libellé ou la valeur par défaut ne réinitialise
plus nécessairement leur état. [Notes officielles 1.50](https://docs.streamlit.io/develop/quick-reference/release-notes/2025#version-1500).

Ici, la clé contient la date et l'indice de pièce, mais pas l'autobus.
Correction recommandée : inclure l'identité du bus dans la clé du champ et
de son bouton, puis ajouter une régression vérifiant le texte affiché et la
note réellement sauvegardée lors d'un changement de bus.

## Échec du test Logs sous 1.50

`tests/test_logs_app.py`, fonction `logue`, effectue un `at.run()` supplémentaire
après le clic de connexion. Pour le second scénario, Streamlit 1.50 lève
`KeyError: st.session_state has no key "login_matricule"` lors de la
reconstruction des états des widgets par AppTest.

Dans la copie temporaire seulement, remplacer cette seconde relance par
`at._run()` fait passer tout le scénario Logs. Cela situe l'échec observé dans
le pilote de test et ne démontre pas une panne du formulaire en navigateur.
`_run` reste une API privée : ce contournement de diagnostic n'est pas une
correction durable proposée pour le dépôt.

## Autres changements pertinents

| Changement | Usage dans le dépôt et conséquence |
| --- | --- |
| Nettoyage des clés de widgets au début d'un changement de page depuis 1.46 | Vérifier les allers-retours entre Ma journée, Préparation et Rapports ; une clé de widget ne constitue pas à elle seule un état persistant entre pages. [Cycle de vie des widgets](https://docs.streamlit.io/develop/concepts/architecture/widget-behavior). |
| `use_container_width` déprécié | 12 occurrences dans Connexion, dialogue de session, Administration et Préparation. Encore acceptées dans les essais ; remplacer `True` par `width="stretch"`. [Boutons 1.50](https://docs.streamlit.io/1.50.0/develop/api-reference/widgets/st.button), [tableaux 1.50](https://docs.streamlit.io/1.50.0/develop/api-reference/data/st.dataframe). |
| Évolutions des dispositions et du style | Les styles de `app/main.py` ciblent `.block-container` et des attributs internes `data-testid`. Risque visuel à vérifier sur mobile : marges, en-tête, colonnes et boutons. Les ouvertures AppTest ne valident pas le rendu CSS. [Évolutions 1.48](https://docs.streamlit.io/develop/quick-reference/release-notes/2025#version-1480). |
| Suppressions d'API anciennes | Aucun usage trouvé de `st.experimental_dialog`, `st.experimental_fragment`, `experimental_allow_widgets`, ni de paramètres nommés supprimés de `st.write`. Pas de rupture directe identifiée sur ces points. [Notes 2025](https://docs.streamlit.io/develop/quick-reference/release-notes/2025). |
| Versions ultérieures permises par `>=1.50` | `components.html`, utilisé trois fois dans Ma journée et Rapports, est déprécié depuis 1.56. Prévoir sa migration en vérifiant le besoin d'iframe et le rendu des rapports. [Documentation officielle](https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v1.html). |
| Différence de version Python | Le support officiel de Python 3.14 arrive en 1.52. Les essais 1.50 ont donc été faits avec Python 3.12, comme le Dockerfile. [Notes 1.52](https://docs.streamlit.io/develop/quick-reference/release-notes/2025#version-1520). |

Précision sur le sélecteur : la saisie libre apparaît en 1.45 et le correctif
de clavier mobile pour `selectbox` en 1.49. Celui de 1.50 concerne `multiselect`.
Le minimum 1.50 choisi précédemment n'était donc pas strictement imposé par la
saisie de dates. [Notes officielles](https://docs.streamlit.io/develop/quick-reference/release-notes/2025).

## Suite recommandée

1. Corriger la clé de la note d'autobus et couvrir le scénario reproduit — fait,
   voir le suivi ci-dessous.
2. Adapter durablement le test Logs pour la version de Streamlit retenue.
3. Remplacer les paramètres dépréciés et vérifier les champs dont les données
   changent alors que leur clé reste identique.
4. Choisir une version exacte pour le déploiement, tester avec Python 3.12 et
   verrouiller les dépendances résolues — fait pour Python 3.12.14 / Streamlit
   1.64.0 ; voir le suivi ci-dessous.
5. Compléter par des essais navigateur : connexion/déconnexion, navigation avec
   données saisies, date libre sur téléphone, import PDF, téléchargement et aperçu
   des rapports, renouvellement de session portail et reprise d'opération.

Les essais de navigateur, les appels au portail employé et la validation des
interactions mobiles n'ont pas été réalisés dans cet audit. Le passage des
tests de domaine ne remplace pas ces vérifications d'interface.

Les journaux et scripts de diagnostic de cette exécution se trouvent dans
`/tmp/chauffeur-audit-verifie-tns1pd3k/` ; la suite locale complète est consignée
dans `/tmp/chauffeur-tests-streamlit-local.log`. Ces chemins sont temporaires.
L'audit ne modifie ni le code applicatif ni les contraintes de dépendances.

## Correction des notes d'autobus

Le champ de note et son bouton d'enregistrement utilisent désormais une clé
incluant le numéro d'autobus, en plus de la date et de l'indice de pièce.
Changer de bus recharge ainsi sa propre note, ou un champ vide s'il n'en a pas.

Le test `TestPage.test_note_bus_suit_changement_autobus`, ajouté à
`tests/test_durees_app.py`, échouait avant correction dans les deux cas
(bus cible avec ou sans note) et passe après correction. Il vérifie qu'un
brouillon du bus A ne se retrouve pas sur le bus B, que l'enregistrement
préserve la note de A, et que les allers-retours affichent les notes sauvegardées.
Tous les fichiers utilisés sont temporaires.

Validation : les cinq tests de `tests/test_durees_app.py` et la suite
`tests/test_notes.py` passent avec Python 3.14.4 / Streamlit 1.62.0 en local,
ainsi qu'avec Python 3.12.14 / Streamlit 1.50.0 dans un conteneur temporaire.
La compilation des deux fichiers Python modifiés réussit également.

## Verrouillage Python 3.12.14 / Streamlit 1.64.0

`requirements.in` fixe Streamlit à 1.64.0. `requirements.txt`, généré sous
Python 3.12 avec pip 25.3 / pip-tools 7.5.2, verrouille 38 paquets et leurs
empreintes. Le Dockerfile fixe Python 3.12.14 par son tag et son digest,
installe avec `--require-hashes` et exécute `pip check`.

Une image propre a été construite depuis ce Dockerfile et ce verrouillage,
sans réutiliser les paquets d'une ancienne image applicative :

- Installation avec vérification des empreintes : réussie.
- `pip check` : aucune incompatibilité déclarée.
- Versions vérifiées à l'exécution : Python 3.12.14 et Streamlit 1.64.0.
- `tests/run_all.py` : **32/32 suites réussies**, dont les journaux sans
  adaptation du pilote AppTest et le test de changement d'autobus.
- AppTest : ouverture de l'entrée principale et des six pages sans exception
  sur une copie isolée sans données personnelles ; Administration affiche son
  garde-fou hors session admin.
- Démarrage Streamlit : réponse HTTP `ok` sur `/_stcore/health`.

Image locale : `chauffeur-mtl-au:validation-1.64.0`.
Identifiant relevé :
`sha256:de4491fb9dd84e89c9aab82b42ced87d3c63f8f29924c75fab9c8f72660e25c2`.
Journaux temporaires : `/tmp/chauffeur-verrouillage-164-_zced977/`.

Cette image n'a pas été déployée. La recette navigateur/mobile et les échanges
réels avec le portail restent à effectuer. Les dépréciations signalées dans
l'audit restent à traiter séparément.
Utiliser la [recette réutilisable](recette-navigateur-mobile.md) et sa fiche
d'exécution pour consigner ces vérifications.

La [procédure de maintenance](dependances.md) décrit les installations, les
mises à jour ciblées, la revue mensuelle et la conservation de l'image validée.

## Corrections des aperçus et des états de widgets

Suivi du 16 septembre 2026, fondé sur les références état de session,
navigation et API du skill `developing-with-streamlit`, puis sur les signatures
effectivement disponibles dans l'image Python 3.12.14 / Streamlit 1.64.0.

Les trois aperçus HTML utilisent maintenant `st.iframe`, avec une hauteur de
600 px et le défilement natif. Le HTML des rapports reste isolé dans l'iframe ;
les imports de `streamlit.components.v1` ont été retirés de ces pages.

Les essais ont reproduit avant correction, sur 1.64.0, quatre défauts : note
de relève conservée après changement de matricule, ancien brouillon de numéro
d'autobus conservé après réimport, dates perdues entre pages et texte d'import
conservé après changement de date. Les règles retenues sont désormais :

| État | Comportement |
| --- | --- |
| Dates de Ma journée, Préparation et des deux rapports | Chaque sélection reste indépendante et persiste entre pages pendant la session, avec `persist_state="session"`. |
| Notes de relève | Le champ et son bouton incluent le matricule ; une nouvelle personne recharge sa propre note, vide si absente. |
| Notes d'autobus, de journée et de carte agent | Les notes enregistrées sont relues pour la bonne identité ; les brouillons ne suivent pas une autre identité ni un changement de page. |
| Numéro d'autobus | Le brouillon reste sur les relances ordinaires ; un réimport modifiant la pièce ou son bus recharge le numéro enregistré. |
| Import de journée et de carte agent | Le texte est lié à la date ; le PDF et les cases autorisant son remplacement sont liés à la date et au numéro de journée. |
| Positions, états des trajets et rafraîchissements | Une position reste associée au bus et à la date ; les états des trajets sont liés à leur identité ; changer de date efface les résultats de rafraîchissement précédents. |
| Déconnexion | Tous les états de session sont effacés, y compris dates persistantes, brouillons et opérations en attente. |

Les champs communs d'import G-D/événements concernent la flotte et ne sont pas
rattachés à une date de journée. Les options générales de rapport et de
traitement GTFS gardent leur comportement existant.

`tests/test_etat_streamlit.py` ajoute dix tests sur une copie temporaire de
l'app et des données synthétiques. Ils couvrent les deux types de relève avec
ou sans note, les fichiers sauvegardés, les réimports, les dates, les notes de
journée/CA, la navigation réelle par `st.navigation`, la déconnexion, les
positions et rafraîchissements, ainsi que les trois aperçus et les sorties
HTML/PDF. La génération des rapports est exécutée sans GTFS de production.

Validation après correction :

- Python 3.14.4 / Streamlit 1.62.0 : les dix nouveaux tests et les cinq tests
  de `test_durees_app.py` passent.
- Python 3.12.14 / Streamlit 1.64.0 : **33/33 suites réussies**, dans l'image
  `chauffeur-mtl-au:validation-1.64.0` avec une copie isolée du code modifié,
  sans réseau, `.env`, cookies ni données personnelles.
- Compilation des fichiers Python modifiés et `git diff --check` réussis.

AppTest 1.64.0 ne sérialise pas une option libre absente de la liste du
sélecteur : le test de date libre amorce donc l'état public avant affichage,
puis vérifie le traitement des dates anciennes, absentes et invalides et le
retour à une date proposée. Cela ne valide pas la saisie au clavier dans un
navigateur. De même, les tests vérifient le HTML transmis aux iframes et les
sorties téléchargeables, pas leur rendu visuel ni le transfert navigateur.
La [recette navigateur/mobile](recette-navigateur-mobile.md) reste à exécuter.
Le service existant n'a pas été redéployé.

Quatre paramètres `use_container_width` ont aussi été remplacés par
`width="stretch"` dans Connexion et Préparation ; huit restent à migrer dans
Administration et le dialogue de session portail, suivis dans le TODO.
