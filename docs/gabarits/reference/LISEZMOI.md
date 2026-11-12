# Gabarits des fichiers de référence

Les fichiers de référence propres à une organisation ne sont **pas versionnés** (ils sont ignorés
par git) : ils décrivent des points de relève, des garages et des codes de lieux internes.
Chaque installation les fournit elle-même dans `data/reference/` :

| Gabarit (fictif) | Copier vers | Rôle |
|---|---|---|
| `points_de_releve_AAAA.json` | `data/reference/points_de_releve_<AAAA>.json` | lieu lisible d'un code de point de relève (un fichier par année, reconduction automatique) |
| `garages.json` | `data/reference/garages.json` | correspondance garage_id → nom du garage |
| `stations_metro.json` | `data/reference/stations_metro.json` | codes de station de métro → nom |

Sans ces fichiers, l'application fonctionne : les lieux de relève restent affichés par leur code.
Le calendrier des périodes (`data/reference/periodes_<AAAA>.json`) reste, lui, versionné.
