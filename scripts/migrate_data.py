#!/usr/bin/env python3
"""migrate_data.py — Migration one-shot vers l'isolation par matricule.

Déplace les données personnelles historiques (data/journees, data/ca,
data/notes, data/rapports, data/session) vers `data/<matricule>/<dossier>`,
emplacement désormais utilisé dès que la variable d'environnement
CHAUFFEUR_MATRICULE est définie.

Les dépôts partagés de la flotte (Gauche-Droite, Events, GTFS) ne sont pas
déplacés : ils restent à la racine de data/ pour tous les chauffeurs. Il en va
de même pour `data/log/`, le **journal commun** des imports de la flotte
(G-D, Événements, GTFS, GTFS-RT) : il n'est pas déplacé. Seuls les journaux
**personnels** (parse_journee.log, carte_agent.log) qui s'y trouvent encore
sont rapatriés vers `data/<matricule>/log/`.

Usage :
    python3 scripts/migrate_data.py --matricule 40001            # déplace
    python3 scripts/migrate_data.py --matricule 40001 --dry-run  # simule
    python3 scripts/migrate_data.py --matricule 40001 --force    # fusionne
"""
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chauffeur.matricule import matricule_valide  # noqa: E402

# Doit rester identique aux répertoires privés de chauffeur.depots.
# `log` n'y figure plus : data/log est le journal commun de la flotte,
# traité à part ci-dessous (seuls les journaux personnels en sont sortis).
SOUS_DOSSIERS_PRIVES = ["journees", "ca", "notes", "rapports", "session"]

# Journaux personnels (complément de chauffeur.journal.SOURCES_COMMUNES) :
# s'ils ont été écrits dans data/log (commun/legacy), on les rapatrie vers
# data/<matricule>/log/ sans toucher aux journaux de la flotte.
JOURNAUX_PERSONNELS = ("parse_journee", "carte_agent")


@dataclass
class ResultatMigration:
    """Bilan d'une migration : jamais de fichier écrasé silencieusement."""

    deplacements: list[tuple[Path, Path]] = field(default_factory=list)
    conflits:     list[tuple[Path, Path]] = field(default_factory=list)
    ignores:      list[Path] = field(default_factory=list)


def migrer(
    data_dir: Path,
    matricule: str,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> ResultatMigration:
    """Déplace les données privées de `data_dir/<dossier>` vers `data_dir/<matricule>/<dossier>`.

    `data_dir` peut être un emplacement quelconque (tests hermétiques).
    En cas de conflit (cible non vide), `force=True` fusionne entrée par
    entrée sans jamais écraser un fichier existant.
    """
    if not matricule_valide(matricule):
        raise ValueError(
            f"Matricule invalide : {matricule!r}"
            " (attendu : 5 chiffres entre 20000 et 99999)"
        )
    data_dir = Path(data_dir)
    resultat = ResultatMigration()

    for dossier in SOUS_DOSSIERS_PRIVES:
        source = data_dir / dossier
        cible = data_dir / matricule / dossier
        if not source.exists():
            resultat.ignores.append(source)
            continue

        if cible.exists():
            if any(cible.iterdir()):
                if force:
                    _fusionner(source, cible, resultat, dry_run=dry_run)
                else:
                    resultat.conflits.append((source, cible))
                continue
            if not dry_run:
                cible.rmdir()

        if not dry_run:
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(cible))
        resultat.deplacements.append((source, cible))

    _migrer_journaux_personnels(data_dir, matricule, resultat,
                                dry_run=dry_run, force=force)

    return resultat


def _renommer_de_cote(dest: Path) -> Path:
    """Premier `<source>.<N>` libre pour mettre une cible existante de côté."""
    i = 1
    while True:
        candidat = dest.with_name(f"{dest.stem}.{i}")
        if not candidat.exists():
            return candidat
        i += 1


def _migrer_journaux_personnels(
    data_dir: Path,
    matricule: str,
    resultat: ResultatMigration,
    *,
    dry_run: bool,
    force: bool,
) -> None:
    """Sort de `data/log/` les journaux personnels vers `data/<matricule>/log/`.

    `data/log/` est le journal commun de la flotte : il reste en place, et
    seuls les journaux personnels (parse_journee.log, carte_agent.log) qui s'y
    trouvent encore sont rapatriés. Jamais d'écrasement : une cible existante
    passe en conflit sans `--force` ; avec `--force`, elle est mise de côté en
    `<source>.N` et le journal source devient le fichier courant (les deux
    copies sont conservées).
    """
    source_log = data_dir / "log"
    cible_log = data_dir / matricule / "log"
    if not source_log.is_dir():
        resultat.ignores.append(source_log)
        return

    for source in sorted(source_log.glob("*.log")):
        if source.stem not in JOURNAUX_PERSONNELS:
            continue
        dest = cible_log / source.name
        if dest.exists():
            if force:
                de_cote = _renommer_de_cote(dest)
                if not dry_run:
                    dest.rename(de_cote)
                resultat.deplacements.append((dest, de_cote))
            else:
                resultat.conflits.append((source, dest))
                continue
        if not dry_run:
            cible_log.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(dest))
        resultat.deplacements.append((source, dest))


def _fusionner(
    source: Path, cible: Path, resultat: ResultatMigration, *, dry_run: bool
) -> None:
    """Fusionne le contenu de `source` dans `cible` (aucun écrasement)."""
    cible.mkdir(parents=True, exist_ok=True)
    for entree in source.iterdir():
        dest = cible / entree.name
        if dest.exists():
            resultat.conflits.append((entree, dest))
            continue
        if not dry_run:
            shutil.move(str(entree), str(dest))
        resultat.deplacements.append((entree, dest))
    if not dry_run and not any(source.iterdir()):
        source.rmdir()


def main() -> int:
    ap = argparse.ArgumentParser(description="Migration vers data/<matricule>/.")
    ap.add_argument("--matricule", required=True,
                    help="Matricule cible (5 chiffres, 20000-99999).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Simulation : affiche les déplacements sans rien bouger.")
    ap.add_argument("--force", action="store_true",
                    help="Fusionne dans une cible déjà remplie (jamais d'écrasement).")
    args = ap.parse_args()

    data_dir = Path(__file__).resolve().parent.parent / "data"
    try:
        resultat = migrer(data_dir, args.matricule,
                          dry_run=args.dry_run, force=args.force)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    for source, cible in resultat.deplacements:
        print(f"  → {source}  ⇒  {cible}")
    for source, cible in resultat.conflits:
        print(f"  ⚠ conflit : {source} ⇒ {cible} contient déjà un élément du même nom")
    for ignore in resultat.ignores:
        print(f"  - (rien à faire) {ignore} : absent")
    if resultat.conflits:
        print("Réessayer avec --force pour fusionner les cibles non vides "
              "(aucun fichier existant ne sera écrasé).")
        return 1
    if args.dry_run:
        print(f"✅ Simulation terminée : {len(resultat.deplacements)} déplacement(s).")
    else:
        print(f"✅ Migration terminée : {len(resultat.deplacements)} déplacement(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())