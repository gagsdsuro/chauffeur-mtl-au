# Livraison — AAAA-MM-JJ

Les fiches de recette réelles (hôtes, comptes de test, chemins de déploiement) ne sont pas
versionnées dans ce dépôt public : les conserver dans un dépôt privé d'exploitation. Ce gabarit sert
de point de départ ; voir `docs/livraison.md`.

## Contenu du build

| Commit | Sujet |
|---|---|
| `<sha7>` | <sujet> |

## Image préparée

- Commit : `<sha7>` (tag `prod-AAAA-MM-JJ`).
- Image : `chauffeur-mtl-au:livraison-AAAA-MM-JJ-<sha7>`.
- ID Docker : `sha256:<id>`.
- Plateforme / utilisateur : `linux/amd64`, `app`, UID/GID `1000:1000`.
- Archive : `chauffeur-mtl-au-AAAA-MM-JJ-<sha7>.tar` et empreinte SHA-256.

## Vérifications exécutées

- [ ] `python3 tests/run_all.py`
- [ ] `python3 tests/test_dockerfile.py`
- [ ] Image démarrée sans port exposé ni donnée personnelle : état `healthy`
- [ ] Dépendances installées avec `--require-hashes`, puis `pip check`

## Recette navigateur

Compte de recette : matricule de test `<matricule>` et PIN de test.

| Parcours | Résultat | Remarques |
|---|---|---|
| <parcours> | À exécuter | |

## Installation après validation

- [ ] Sauvegarde des données et de la configuration
- [ ] Conservation de l'image précédente (retour arrière)
- [ ] Déploiement, contrôle `healthy`, vérification dans le navigateur

## Retour arrière

Procédure et image précédente : <à compléter>.
