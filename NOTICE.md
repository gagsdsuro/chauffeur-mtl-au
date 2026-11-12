# Avis, attributions et limitation de responsabilité

## Projet indépendant

**Chauffeur Mtl-AU** (Chauffeur Montréal Autobus Urbain) est un projet indépendant.
Il n'est **ni affilié à la Société de transport de Montréal (STM), ni approuvé, commandité ou
cautionné par elle**, ni par aucun employeur. Les noms et marques de tiers appartiennent à
leurs propriétaires et ne sont cités que pour désigner les sources de données.

## Attribution des données ouvertes

Contient des données de la Société de transport de Montréal (STM), offertes sous licence CC BY 4.0 (https://www.stm.info/a-propos/documents-donnees/donnees-ouvertes). Projet indépendant, non officiel et non cautionné par la STM.

Licence : Creative Commons Attribution 4.0 International.

Cela couvre les données GTFS (horaires et arrêts) et GTFS temps réel utilisées par l'application,
ainsi que les extraits gelés qui en dérivent dans les jeux d'essai (`tests/`).
L'outil vise l'autobus urbain : il ne fournit pas d'horaires de métro.

## Aucune garantie sur l'information

Les informations produites ou affichées (itinéraires Gauche-Droite, événements et détours, horaires,
positions, rapports, cartes annotées, appariements) proviennent de sources tierces, sont transformées
automatiquement et peuvent être **inexactes, incomplètes, périmées ou indisponibles**.
Elles **ne remplacent pas** les consignes, avis et documents officiels de l'organisation : en cas de
doute, ces derniers prévalent. La qualité et la disponibilité des sources (dont `employe.stm.info`,
`api.stm.info` et `www.stm.info`) ne sont pas garanties par ce projet et peuvent changer ou
cesser sans préavis.

Le logiciel est fourni « tel quel », sans garantie d'aucune sorte, dans les limites de la licence
([GNU AGPL-3.0](LICENSE), articles 15 et 16). Les auteurs ne sont pas responsables des dommages
résultant de son utilisation.

## Responsabilité de l'utilisateur

- **Chaque utilisateur est seul responsable de sa connexion au portail employé
  (`employe.stm.info`)** : ses identifiants, sa session et ses cookies lui appartiennent et ne
  doivent pas être partagés.
- Chaque utilisateur doit **se conformer aux politiques, règles et conditions d'utilisation de son
  organisation** (accès au portail, usage des technologies de l'information, confidentialité de
  l'information interne) et s'assurer que l'usage de cet outil y est permis.
- Ce projet ne fournit **aucune donnée du portail employé**. Les données qu'un utilisateur y
  récupère lui sont destinées ; leur conservation et leur partage relèvent de sa responsabilité.
- **Clé API** : les flux GTFS temps réel exigent une clé obtenue avec un compte personnel du portail
  des développeurs de la STM (<https://portail.developpeurs.stm.info>). Chaque utilisateur ou
  déploiement doit utiliser **sa propre clé** et en accepter les conditions.

## Données personnelles

Les journées, cartes agent, notes, rapports et sessions sont rangés par matricule dans `data/`
(exclu du dépôt). Ne publiez jamais ces fichiers (tickets, correctifs, captures d'écran).
