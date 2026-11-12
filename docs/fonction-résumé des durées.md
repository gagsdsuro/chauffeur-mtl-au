# Fonction - Résumé des durées de la journée

## Objectif

Caractéristiques de la fonctionalité permettant d'afficher une grille sommaire des durées sur la page "Ma journée"

## Source des données - fichier journée

Par exemple, pour une journée fictive, les informations suivantes sont récupérées à partir du fichier journée (`data/<matricule>/journees/journee-AAAA-MM-JJ.json`).

|Description|Début|Fin|Durée|
|-----------|-----|---|-----|
| prise début de la première pièce de travail et premier départ de la première pièce de travail|17:11|17:13|00:02|
|segment 136 nord|17:13 | 17:55 | 00:42 |
| battement entre 136 nord et 136 sud| 17:55 | 18:03 | 00:08 |
| segment 136 sud | 18:03 | 18:40 | 00:37 |
| battement entre 136 sud et 136   nord| 18:40 | 18:54 | 00:14 |
| segment 136 nord | 18:54 | 19:29 | 00:35 |
| segment hlp| 19:29 | 19:52 | 00:23 |
| battement entre hlp et   prochain segment 136 nord | 19:52 | 20:03 | 00:11 |
| segment 136 nord | 20:03 | 20:36 | 00:33 |
| battement entre 136 nord et hlp | 20:36 | 20:36 | 00:00 |
| segment hlp | 20:36 | 20:59 | 00:23 |
| battement entre hlp et prise fin | 20:59 | 21:01 | 00:02 |
| pause entre prise fin de la première pièce de travail et prise début de la seconde pièce de travail | 21:01 | 22:43 | 01:42 |
| prise début de la seconde pièce de travail et premier départ de la seconde pièce de travail | 22:43 | 23:03 | 00:20 |
| segment 136 nord | 23:03 | 23:35 | 00:32 |
| battement entre 136 nord et   136 sud | 23:35 | 23:49 | 00:14 |
| segment 136 sud | 23:49 | 24:15 | 00:26 |
| battement entre 136 sud et 136   nord | 24:15 | 24:19 | 00:04 |
| segment 136 nord | 24:19 | 24:50 | 00:31 |
| battement entre 136 nord et   136 sud  | 24:50 | 24:54 | 00:04 |
| segment 136 sud | 24:54 | 25:19 | 00:25 |
| battement entre 136 sud et 136   nord | 25:19 | 25:25 | 00:06 |
| segment 136 nord | 25:25 | 25:52 | 00:27 |
| battement entre 136 nord et entrée (hlp) | 25:52 | 25:52 | 00:00 |
| segment entrée au garage (31 min) + temps de fin (10 min)  | 25:52 | 26:33 | 00:41 |


## Sortie attentue

Le tableau attendu ressemble à ceci:

Filtre segment: | x ligne | x prise | x hlp | x fin | x pause | x entrée | x sortie |

  |Heure|Segm.|Dir. |Durée (m)|Bat. (m)|Durée t. (m)|
  |:---:|:----|:---:|----:|---:|----------:|
  |***17:11***|***prise***|-|-|***2***|***2***|
  |17:13|136  |nord|42|8|50|
  |18:03|136  |sud|37| `14`|51|
  |18:54|136  |nord|35|0|35|
  |**19:29**|**hlp**|-|**23**|**11**|**34**|
  |20:03|136  |nord|33|0|33|
  |**20:36**|**hlp**|-|**23**|**2**|**25**|
  |***21:01***|***fin***|-|-|-|-|
  |***21:01***|***pause***|-|-|***102***|***102***|
  |***22:43***|***prise***|-|-|***20***|***20***|
  |23:03|136  |nord |32|`14`|46|
  |23:49|136  |sud  |26|4|30|
  |24:19|136  |nord |31|4|35|
  |24:54|136  |sud  |25|6|31|
  |25:25|136  |nord |27|0|27|
  |**25:52**|**entrée**|-|**31**|**10**|**41**|
  |***26:33***|***fin***|-|-|-|-|

### Caractéristique de la grille

- Les lignes "prise", "pause", "entrée", "sortie", "fin" et "hlp" sont mise en évidence
- En excluant la durée de "prise" et "pause", surligner tous les battements ex æquo au maximum de leur pièce.
- Les lignes spéciales sont en gras ; "prise", "pause" et "fin" sont aussi en italique. Le surlignage des maxima porte sur la cellule "Bat. (m)".
- Conserver les pièces dans leur ordre, même si elles partagent le même identifiant ou correspondent à du TS continu. Les maxima sont propres à chaque occurrence de pièce.

#### La durée totale (Durée t. (m)) correspond à la durée plus le battement soit:

  - la durée entre l'heure de prise et le départ du premier segment. Peut être égale à 0.
  - durée du parcours, du départ à l’arrivée, plus le battement suivant.
  - la durée d'un hlp d'une sortie de garage ou d'une entrée au garage plus le temps de battement suivant.
  - la temps de pause entre deux pièces de travail.

#### Le temps de battement peut notament correspondre à:

  - le temps entre la prise fin d'une pièce de travail et la prise début de la prochaine pièce de travail (pause).
  - le temps entre l’arrivée d’un segment et le départ du suivant, dans une même pièce
  - le temps de battement peut être égal à zéro
  - si deux pièces se suivent sans interruption, omettre la ligne "pause" de zéro minute et conserver les lignes "fin" et "prise".

#### Prise début et prise fin

  - La "prise début" est renseignée dans le fichier journée. Si la prise début précède une sortie de garage, l'heure de prise inclut déjà 10 minutes avant la sortie (hlp). Sinon, "prise début" et "début" devraient être égaux.
  - La "prise fin" n'est pas renseignée dans le fichier journée. Si une pièce de travail se termine avec une entrée, sa prise fin correspond à l'arrivée de cette entrée (hlp) plus un battement forfaitaire de 10 minutes. Sinon, elle correspond au champ "fin" de la pièce.
  - Les minutes de prise avant une sortie et les 10 minutes de fin après une entrée peuvent expliquer un écart normal avec le temps travaillé du JSON. Les minutes avant la sortie sont calculées par différence avec "prise", sans ajout supplémentaire.
  - Les indicateurs "Prise début" et "Prise fin" en haut de la page utilisent les mêmes bornes que la grille : prise de la première pièce et fin calculée de la dernière. L'indicateur "Temps travaillé" conserve la valeur du JSON.

#### Données incomplètes ou incohérentes

- Conserver les lignes et les valeurs calculables ; afficher "—" pour les heures ou durées inconnues et un message identifiant les pièces concernées.
- Une durée négative est signalée et affichée comme incalculable, sans correction automatique de passage à minuit. Les heures après minuit restent exprimées en heures de quart (24:15, 26:33, etc.).
- Si un battement de trajet est inconnu, aucun maximum n'est surligné pour cette pièce. Les prises et pauses ne participent pas à ce calcul.
- Une pause inconnue ou incohérente reste visible avec "—" ; seules les pauses connues de zéro minute sont omises.
- Une borne de prise inconnue apparaît comme "—" dans les indicateurs, sans repli sur une autre pièce.

#### Filtre

- Une sélection permet de filtrer les segments affichés. Tous les types de segments sont affichés par défaut.
- Les types proposés sont : ligne, prise, hlp, fin, pause, entrée et sortie. Une sélection vide affiche un message explicite.
- Le filtre masque uniquement les lignes : il ne recalcule ni les durées ni les maxima, et ne modifie pas les indicateurs de la journée.

## Positionnement de la grille

La grille se trouve sur la page "Ma journée" juste avant la section "Pièces de travail".

Positionner la grille dans une section "expander" fermée par défaut.

## Note générale

- Un segment entrée ou sortie (au garage) se fait en mode hlp (haut le pied).
- Le résumé est calculé à partir du JSON uniquement, sans lire de PDF ni accéder au portail, et sans modifier les fichiers de journée.

## Cas de validation complémentaire — CA 443, 23 août 2026

- Première prise à 11:18, sortie de 11:28 à 11:38, fin de pièce à 15:43 : 4 h 25 prise comprise.
- Pause de 15:43 à 16:49 : 66 minutes. Seconde pièce de 16:49 à 20:04 : 3 h 15.
- Total hors pause : 7 h 40 ; amplitude : 8 h 46. L'écart de 10 minutes avec les 7 h 30 du JSON provient ici de la prise avant la sortie.
- Maxima : sept battements de 3 minutes dans la première pièce, trois de 5 minutes dans la seconde.
