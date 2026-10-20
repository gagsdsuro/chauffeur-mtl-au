#!/usr/bin/env python3
"""chauffeur.journal — journaux d'importation (<répertoire du journal>/<source>.log).

Garde une trace des importations : un fichier par type d'import, nommé d'après
le parseur qui le produit (parse_event.log, parse_gd.log, parse_journee.log,
carte_agent.log, fetch_gtfs.log, fetch_gtfs_rt.log). Consultables dans la page
Logs de l'app.

Deux familles, suivant la nature des données importées :
  • **flotte (commune à tous)** — G-D, Événements, GTFS, GTFS-RT, appariements :
    les sources `parse_gd`, `parse_event`, `fetch_gtfs`, `fetch_gtfs_rt`,
    `appariement` (SOURCES_COMMUNES)
    sont journalisées dans `data/log/` (LOG_DIR_COMMUN), partagé. C'est la
    piste d'audit des données communes.
  • **personnel** — journée, carte agent : les autres sources vont dans
    `data/<matricule>/log/` (session, sinon LOG_DIR historique).

Deux formats, selon la nature de la trace :
  • `ecrire_bloc`  — rapport de fin d'exécution (parseurs) : un bloc horodaté.
  • `ecrire_ligne` — progression au fil de l'eau (téléchargements GTFS) :
    une ligne `[horodatage] [NIVEAU] message`.

Chaque fonction accepte un répertoire optionnel (défaut = routage par source)
pour permettre des tests hermétiques.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import depots
from .depots import LOG_DIR, LOG_DIR_COMMUN

SEPARATEUR = "=" * 60

# Sources dont les imports touchent la flotte partagée → journal commun.
SOURCES_COMMUNES = frozenset({
    "parse_gd", "parse_event", "fetch_gtfs", "fetch_gtfs_rt", "appariement",
})


def _log_dir_prive() -> Path:
    """Répertoire des journaux personnels : session (thread) si active, sinon constant."""
    return depots.repertoire_prive_contexte("log") or LOG_DIR


def _log_dir(source: str) -> Path:
    """Répertoire du journal de `source` : commun (flotte) ou privé (personnel)."""
    if source in SOURCES_COMMUNES:
        return LOG_DIR_COMMUN
    return _log_dir_prive()


def chemin_journal(source: str, log_dir: Path | None = None) -> Path:
    """<source>.log — journal d'importation, en ajout.

    `log_dir` explicite l'emporte sur le routage par source ; `None` (défaut)
    route les sources de la flotte vers le journal commun et les autres vers
    le journal personnel de la session.
    """
    return (log_dir or _log_dir(source)) / f"{source}.log"


def ecrire_bloc(source: str, rapport: str, log_dir: Path | None = None) -> Path:
    """Ajoute un bloc horodaté au journal et retourne son chemin.

    Format historique de parse_event.log, préservé tel quel : l'ancien et le
    nouveau doivent rester indiscernables dans un même fichier.
    """
    chemin = chemin_journal(source, log_dir)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(chemin, "a", encoding="utf-8") as f:
        f.write(f"\n{SEPARATEUR}\n{horodatage}\n{SEPARATEUR}\n")
        f.write(rapport + "\n")
    return chemin


def ecrire_ligne(source: str, message: str, niveau: str = "INFO",
                 log_dir: Path | None = None) -> str:
    """Ajoute une ligne de progression au journal et retourne la ligne écrite.

    La valeur de retour permet à l'appelant de l'imprimer aussi (les scripts de
    téléchargement affichent leur progression en plus de la journaliser).
    """
    chemin = chemin_journal(source, log_dir)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ligne = f"[{horodatage}] [{niveau}] {message}"
    with open(chemin, "a", encoding="utf-8") as f:
        f.write(ligne + "\n")
    return ligne


def lister_journaux(log_dir: Path | None = None) -> list[Path]:
    """Journaux présents, du plus récemment écrit au plus ancien."""
    repertoire = log_dir or _log_dir_prive()
    if not repertoire.exists():
        return []
    return sorted(repertoire.glob("*.log"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def lister_journaux_communs() -> list[Path]:
    """Journaux de la flotte (`data/log/`), du plus récent au plus ancien."""
    return lister_journaux(LOG_DIR_COMMUN)


def lister_journaux_personnels() -> list[Path]:
    """Journaux personnels du compte connecté (session), sinon du constant."""
    return lister_journaux(_log_dir_prive())
