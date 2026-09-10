#!/usr/bin/env python3
"""migrer_logs_flotte.py — One-shot : journalise les imports de la flotte en commun.

Suite au réajustement de `chauffeur.journal` : les sources de la flotte
(G-D, Événements, GTFS, GTFS-RT → SOURCES_COMMUNES) sont désormais journalisées
dans `data/log/` (commun à tous), et plus dans `data/<matricule>/log/`
(personnel). Ce script rapatrie les journaux des sources communes déjà écrits
dans les dossiers privés.

En cas de conflit (un `data/log/<source>.log` existe déjà), le journal existant
est déplacé en `<source>.N` avant d'accueillir le journal privé : aucun fichier
n'est jamais écrasé ni fusionné.

Usage :
    python3 scripts/migrer_logs_flotte.py            # déplace
    python3 scripts/migrer_logs_flotte.py --dry-run  # simule
"""
import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chauffeur.journal import SOURCES_COMMUNES  # noqa: E402
from chauffeur.matricule import matricule_valide  # noqa: E402


def plan_deplacements(
    data_dir: Path, sources: frozenset[str] = SOURCES_COMMUNES,
) -> list[tuple[Path, Path]]:
    """(journal privé, cible commune) pour chaque source de la flotte trouvée."""
    commun = Path(data_dir) / "log"
    deplacements: list[tuple[Path, Path]] = []
    for mat_dir in sorted(Path(data_dir).iterdir()):
        if not mat_dir.is_dir() or not matricule_valide(mat_dir.name):
            continue
        log_prive = mat_dir / "log"
        if not log_prive.is_dir():
            continue
        for journal in sorted(log_prive.glob("*.log")):
            if journal.stem in sources:
                deplacements.append((journal, commun / journal.name))
    return deplacements


def _nom_libre(cible: Path) -> Path:
    """Premier `<source>.<N>` libre pour mettre une cible existante de côté."""
    i = 1
    while True:
        candidat = cible.with_name(f"{cible.stem}.{i}")
        if not candidat.exists():
            return candidat
        i += 1


@dataclass
class ResultatMigration:
    deplacements: list[tuple[Path, Path]] = field(default_factory=list)
    mises_de_cote: list[tuple[Path, Path]] = field(default_factory=list)
    ignores: list[Path] = field(default_factory=list)


def migrer(
    data_dir: Path,
    *,
    dry_run: bool = False,
    sources: frozenset[str] = SOURCES_COMMUNES,
) -> ResultatMigration:
    """Déplace les journaux de la flotte vers `data_dir/log/`.

    `data_dir` peut être un emplacement quelconque (tests hermétiques).
    Sans `dry_run`, un journal privé existant ne remplace jamais la cible :
    celle-ci est d'abord mise de côté en `<source>.N`.
    """
    data_dir = Path(data_dir)
    commun = data_dir / "log"
    resultat = ResultatMigration()

    for origine, cible in plan_deplacements(data_dir, sources):
        mise_de_cote = _nom_libre(cible) if cible.exists() else None
        if mise_de_cote is not None:
            resultat.mises_de_cote.append((cible, mise_de_cote))
            if not dry_run:
                cible.rename(mise_de_cote)
        if not dry_run:
            commun.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origine), str(cible))
        resultat.deplacements.append((origine, cible))

    return resultat


def main() -> None:
    argparse_desc = "Déplace les journaux des imports de la flotte vers data/log/ (commun)."
    arg_parser = argparse.ArgumentParser(description=argparse_desc)
    arg_parser.add_argument(
        "--dry-run", action="store_true",
        help="simule la migration sans rien déplacer",
    )
    args = arg_parser.parse_args()

    data_dir = Path(__file__).resolve().parent.parent / "data"
    resultat = migrer(data_dir, dry_run=args.dry_run)

    if not resultat.deplacements:
        print("Rien à déplacer : aucun journal de la flotte dans les dossiers privés.")
        return

    verbal = "Simulation" if args.dry_run else "Déplacement"
    for origine, cible in resultat.deplacements:
        print(f"{verbal} : {origine} → {cible}")
    for cible, mise_de_cote in resultat.mises_de_cote:
        action = "déplacerait" if args.dry_run else "déplacé"
        print(f"  cible existante {action} de côté : {cible} → {mise_de_cote}")
    if not args.dry_run:
        print(f"Terminé : {len(resultat.deplacements)} journal(aux) rapatriés.")


if __name__ == "__main__":
    main()