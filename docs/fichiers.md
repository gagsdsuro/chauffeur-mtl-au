# Consulter et gérer les fichiers

La page **Fichiers** propose une liste de dix fichiers par page et l'aperçu du
fichier sélectionné. Sur un écran étroit, l'aperçu passe sous la liste. La
recherche porte sur le nom du fichier (dont le numéro de carte), sans distinction
de casse. Les filtres, le tri et la sélection sont conservés par catégorie pendant
la session. Les filtres de dates portent sur la date du document, pas sa date de
modification.

## Périodes

Pour les journées et cartes agent, la liste en cours à Montréal est proposée
à la première ouverture. Les semaines de variation et les fériés appartiennent
à la liste couvrant leur date ; le filtre Régime permet de les distinguer.
Une période vide reste sélectionnée. Choisir **Toutes les périodes** pour
consulter tout l'historique, ou **Période indéterminée** pour les noms et dates
qui ne peuvent pas être classés.

Le classement lit les noms de fichiers et les calendriers annuels de
`data/reference/`, sans ouvrir les JSON personnels ni les PDF. Il reconnaît les
identités de cartes L/V/férié et les noms historiques, y compris `-surligné`.
Le calendrier suivant permet de prolonger une liste au début de l'année suivante.
Une année sans calendrier n'est jamais couverte par extrapolation. Le cache des
calendriers est invalidé à leur modification ; les noms et contenus existants ne
sont pas migrés.

## Aperçu et édition

Les PDF sont affichés dans le lecteur Streamlit ; les HTML conservent leur rendu.
Les G-D présentent leurs parcours et instructions ; les événements réutilisent
la présentation de l'application sans supposer l'applicabilité à un trajet.
Les JSON peuvent aussi être consultés intégralement.

Un chauffeur peut modifier ses journées et supprimer ses fichiers personnels.
Seul un administrateur peut modifier, supprimer ou purger les fichiers G-D et
événements communs. Sans connexion en mode historique, les mutations des
fichiers communs sont désactivées.

**Modifier** ouvre un éditeur JSON. Les brouillons sont conservés par fichier
pendant la navigation dans la page ; ils ne sont pas des sauvegardes persistantes.
**Enregistrer** valide le document et son identité, conserve les champs inconnus,
écrit une copie `.bak` horodatée, puis remplace atomiquement le fichier. Si une
modification extérieure est détectée, le brouillon est conservé. On peut le
télécharger avant de recharger la version actuelle. Les sauvegardes ne sont pas
incluses dans les listes ni les purges ordinaires. Les imports ultérieurs peuvent
remplacer les corrections manuelles.

La purge conserve les seuils précédents : 90 jours pour événements/rapports,
365 jours pour cartes/G-D/journées, selon la **dernière modification**. Elle porte
sur toute la catégorie, indépendamment des filtres, et demande une confirmation
présentant les noms concernés.

## Export des journées

**Export des journées** ouvre un espace distinct. Choisir un intervalle et
**Préparer l'export** pour voir les pièces qui seront exportées. Le bouton CSV
porte sur tout cet intervalle, indépendamment des filtres et de la pagination.
La date de l'export préparé reste indiquée au-dessus de l'aperçu.

Le format reste inchangé : CSV UTF-8, une ligne par pièce, colonnes `date`,
`garage_id`, `journee_numero`, `piece_id`, `type_horaire`, puis
`trajet1_ligne` à `trajet7_ligne`. Ces sept colonnes contiennent les lignes
d’autobus distinctes des trajets de service de chaque pièce, dans leur ordre
de première apparition. Le dédoublonnage précède la limite de sept lignes ;
les colonnes inutilisées restent vides. La grille et le CSV utilisent les mêmes
valeurs. Les journées illisibles sont signalées et exclues de l'export.
Aucun export Excel n'est ajouté.
