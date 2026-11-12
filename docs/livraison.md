# Branches et livraisons

Guide de travail pour mener plusieurs sujets en parallèle, puis les livrer
ensemble en production. Il complète
[la procédure de maintenance des dépendances](dependances.md), la
[recette navigateur/mobile](recette-navigateur-mobile.md) et le
[gabarit de fiche de recette](recettes/gabarit-build.md).

## Les règles en bref

1. **`main` ne contient que du travail terminé.** On n'y commite pas
   directement : même une correction de documentation passe par une branche.
2. **Une branche = un sujet**, créée **depuis `main`**, jamais depuis une autre
   branche de sujet. Une branche qui part d'une autre en dépend ; on ne peut
   plus livrer l'une sans l'autre (c'est ce qui a mélangé les cinq sujets avant
   le build du 10 novembre 2026).
3. **Une branche de livraison éphémère** assemble les sujets prêts, et c'est
   *cette combinaison* qu'on teste et qu'on livre.
4. **Les tags `prod-AAAA-MM-JJ` disent ce qui tourne en production.** `main`
   peut avancer sans que ce soit ambigu.
5. **On livre l'image qu'on a testée**, sans la reconstruire.
6. **Les mises à jour de dépendances ont leur propre branche** (voir
   [dependances.md](dependances.md)) et se livrent seules ou en tête de
   livraison, jamais mêlées à un sujet fonctionnel.

## Nommage

| Élément | Forme | Exemple |
| --- | --- | --- |
| Fonction | `feat/<sujet>` | `feat/preparation-semi-auto` |
| Correctif | `fix/<sujet>` | `fix/import-gd-doublons` |
| Maintenance | `maintenance/<sujet>` | `maintenance/maj-streamlit` |
| Documentation | `docs/<sujet>` | `docs/guide-livraison` |
| Livraison | `release/AAAA-MM-JJ` | `release/2026-12-01` |
| Tag de production | `prod-AAAA-MM-JJ` | `prod-2026-11-10` |
| Image | `chauffeur-mtl-au:livraison-AAAA-MM-JJ-<sha7>` | `…livraison-2026-11-10-db9a6ca` |
| Archive | `chauffeur-mtl-au-AAAA-MM-JJ-<sha7>.tar` | |

`<sha7>` est le commit dont l'image a été construite.

## Au quotidien

**Commencer un sujet**

```bash
git switch main && git pull --ff-only
git switch -c feat/<sujet>
```

**Changer de sujet** : valider d'abord ce qui est en cours, même incomplet.

```bash
git add -A && git commit -m "wip: <ce qui est fait>"   # on nettoiera avant la livraison
git switch <autre-branche>
```

Ne pas laisser de modifications non commitées d'un jour à l'autre : c'est elles
qui se mélangent. Un commit `wip` se réécrit avant la livraison
(`git commit --amend`, ou plusieurs commits propres sur la branche).

**Séparer ce qui est mélangé** : `git add -p` (dans un terminal ou l'éditeur)
ne met en attente que certains blocs d'un fichier. Depuis Claude Code, où les
commandes interactives ne sont pas disponibles, demander de découper le diff
par bloc `@@` et de l'appliquer avec `git apply --cached` (c'est ainsi que les
trois commits du 10 novembre 2026 ont été séparés).

**Deux sujets réellement simultanés** (l'app tourne sur l'un pendant qu'on code
l'autre) : un dossier de travail par branche.

```bash
git worktree add ../chauffeur-mtl-au-<sujet> -b feat/<sujet> main
```

Ce dossier n'a ni `.venv`, ni `.env`, ni `data/` (ignorés par git) : utiliser
l'interpréteur du dépôt principal (`../chauffeur-mtl-au/.venv/bin/python`). Pour
essayer l'app sur de vraies données, il est plus simple de basculer la branche
dans le dépôt principal. Retirer le dossier à la fin :
`git worktree remove ../chauffeur-mtl-au-<sujet>`.

**Tableau de bord** (à lancer en cas de doute)

```bash
git status -sb                       # rien de non commité ?
git branch -vv                       # branches et retard/avance sur le distant
git branch --no-merged main          # sujets pas encore intégrés
git worktree list
git tag -l 'prod-*'                  # livraisons
git log --oneline prod-AAAA-MM-JJ..main   # ce que main a de plus que la production
```

## Préparer une livraison

Choisir les sujets prêts (suite verte, relus). Ceux qui ne le sont pas restent
sur leur branche.

```bash
git switch main && git pull --ff-only
git switch -c release/AAAA-MM-JJ
git merge --no-ff feat/<sujet-1> -m "Merge branch 'feat/<sujet-1>' : <résumé>"
git merge --no-ff fix/<sujet-2>  -m "Merge branch 'fix/<sujet-2>' : <résumé>"
```

Écrire le message avec `-m` (`git merge -F -` n'existe pas) et terminer par la
ligne d'attribution demandée par le projet. Les conflits viennent presque
toujours de `CLAUDE.md` et de `TODO.md`, où chaque sujet ajoute sa doc : les
résoudre en gardant les deux versions.

Si `main` a avancé entre-temps (correctif urgent), y fusionner `main` avant de
valider : `git merge main`.

Créer la fiche de recette à partir de `docs/recettes/gabarit-build.md` (contenu du build,
image, vérifications, parcours de recette, résultats vides). Les fiches réelles contiennent des
détails d'exploitation : les conserver dans un dépôt privé, pas dans ce dépôt public.

## Valider l'image

Toujours depuis une **extraction propre du commit** : pas de `.env`,
`Installation/` ni données personnelles. Remplacer `AAAA-MM-JJ`, `AAAAMMJJ` et
`<sha7>`.

```bash
SHA=$(git rev-parse --short HEAD)
W=$(mktemp -d /tmp/chauffeur-livraison-AAAAMMJJ-XXXXXXXX); mkdir "$W/src"
git archive HEAD | tar -x -C "$W/src"
IMG=chauffeur-mtl-au:livraison-AAAA-MM-JJ-$SHA
docker build --build-arg UID=1000 --build-arg GID=1000 -t "$IMG" "$W/src" > "$W/build.log" 2>&1
```

**Tests dans l'image**, sans réseau, avec un volume de données *distinct* de
celui de la recette (les tests y laissent des fichiers) :

```bash
mkdir -p "$W/data-suite" && cp -r "$W/src/data/reference" "$W/data-suite/"
docker run --rm --network none -e TZ=America/Toronto \
  -v "$W/src/tests:/app/tests" -v "$W/src/Dockerfile:/app/Dockerfile:ro" \
  -v "$W/data-suite:/app/data" "$IMG" python3 tests/run_all.py > "$W/tests.log" 2>&1
docker run --rm --network none "$IMG" sh -c 'python --version; python -m pip check'
```

Attendu : toutes les suites réussies, Python 3.12.16, Streamlit conforme à
`requirements.in`, `pip check` sans erreur.

**Recette navigateur** : conteneur en mode strict sur le port 8502, volume isolé.

```bash
mkdir -p "$W/data-recette" && cp -r "$W/src/data/reference" "$W/data-recette/"
docker run -d --name chauffeur-mtl-au-recette-AAAAMMJJ -p 8502:8501 \
  -e TZ=America/Toronto -e CHAUFFEUR_MODE_STRICT=1 \
  -v "$W/data-recette:/app/data" "$IMG"
docker inspect -f '{{.State.Health.Status}}' chauffeur-mtl-au-recette-AAAAMMJJ   # healthy
```

Remplir `data-recette/` avec : une ou deux journées copiées de
`data/<matricule>/journees/` (**noms et matricules de relève remplacés** par
« Collègue de recette » / `20001`), les dossiers `Gauche-Droite`, `Events`,
`Appariements` et `gtfs`. Ne pas copier de compte (`users.json`), de cookies
portail, de cartes agent personnelles ni de rapports. Si une nouvelle année de
référence est livrée, ajouter une journée synthétique de cette année.
Créer le compte de recette (matricule 40002, PIN de test), dérouler le
parcours de la fiche et la
[recette mobile](recette-navigateur-mobile.md), puis consigner les résultats
dans la fiche, avec le navigateur et l'appareil.

Un test qui échoue ou une anomalie de recette se corrige **sur la branche du
sujet** (commit dédié), puis on refait la livraison depuis l'étape de fusion.

## Intégrer, tagger, archiver

Seulement après validation. Les commits qui ne touchent que la documentation
(fiche remplie) ne changent pas l'image ; vérifier :

```bash
git diff --quiet <sha7> HEAD -- app chauffeur scripts requirements.txt requirements.in Dockerfile \
  && echo "code identique à l'image validée"
```

Puis :

```bash
git switch main
git merge --ff-only release/AAAA-MM-JJ      # main reçoit les fusions des sujets
git tag -a prod-AAAA-MM-JJ -m "Livraison du … (image livraison-AAAA-MM-JJ-<sha7>)"
git push origin main --tags                  # publie : à ne faire qu'après validation
git branch -d release/AAAA-MM-JJ feat/<sujet-1> fix/<sujet-2>
```

`git branch -d` refuse de supprimer une branche non fusionnée : c'est le
garde-fou.

Archive à transférer :

```bash
docker save -o /tmp/chauffeur-mtl-au-AAAA-MM-JJ-<sha7>.tar "$IMG"
cd /tmp && sha256sum chauffeur-mtl-au-AAAA-MM-JJ-<sha7>.tar > chauffeur-mtl-au-AAAA-MM-JJ-<sha7>.tar.sha256
```

Reporter le SHA-256 et l'ID de l'image dans la fiche de recette.

## Déployer

Suivre la section « Installation après validation » de la fiche (transfert de
l'archive par le moyen de votre choix, puis) :
`sha256sum -c`, `docker load`, sauvegarde de `data/`, `image:` pointée vers
la nouvelle image, `docker compose up -d --no-build`.

**Le dossier `data/` de la production n'est pas dans l'image.** Tout fichier de
`data/reference/` ajouté, renommé ou retiré par la livraison doit être mis à
jour à la main sur le serveur. Sans cela l'application démarre quand même, mais
des données disparaissent sans message (cas du 10 novembre 2026 :
`points_de_releve.json` renommé en `points_de_releve_2026.json` ; les lieux de
relève auraient disparu). Lister ces fichiers dans la fiche à chaque livraison.

Après le déploiement : vérifier un écran concret touché par la livraison,
régénérer les rapports v2 concernés (leur empreinte dépend des données, pas du
code), puis noter le déploiement dans la fiche.

## Retour arrière

Garder l'image précédente (`chauffeur-mtl-au:livraison-<ancienne>`) et la
sauvegarde de `data/` (surtout `data/reference/`). Remettre l'ancien tag
d'image dans Compose, restaurer `data/reference/` si la livraison l'a modifié,
puis `docker compose up -d --no-build`.

## Correctif urgent

Partir de ce qui tourne, pas de `main` :

```bash
git switch -c fix/<sujet> prod-AAAA-MM-JJ
# corriger, tester, commiter
git switch main && git merge --no-ff fix/<sujet>   # le correctif rejoint aussi main
```

Livrer ensuite le correctif seul : construire l'image depuis le commit de la
branche `fix/` (validation et recette ciblées), taguer
`prod-AAAA-MM-JJ` sur la fusion correspondante.

## Après la livraison

- Supprimer le conteneur et les dossiers temporaires de recette
  (`docker rm -f chauffeur-mtl-au-recette-AAAAMMJJ`, `rm -rf "$W"`) : ils
  contiennent des copies de données personnelles. Garder l'image livrée et
  l'image précédente.
- Retirer de `TODO.md` ce que la livraison a réglé.
- Les journaux de build et de tests sont dans `$W` : y copier ce qu'on veut
  conserver *avant* de supprimer, ou en consigner le résultat dans la fiche.
