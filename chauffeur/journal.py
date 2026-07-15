#!/usr/bin/env python3
"""chauffeur.journal — journaux d'importation (data/log/<source>.log).

Garde une trace des importations : un fichier par type d'import, nommé d'après
le parseur qui le produit (parse_event.log, parse_gd.log, parse_journee.log,
carte_agent.log, fetch_gtfs.log, fetch_gtfs_rt.log). Consultables dans l'onglet
Logs de l'app.

Deux formats, selon la nature de la trace :
  • `ecrire_bloc`  — rapport de fin d'exécution (parseurs) : un bloc horodaté.
  • `ecrire_ligne` — progression au fil de l'eau (téléchargements GTFS) :
    une ligne `[horodatage] [NIVEAU] message`.

Chaque fonction accepte un répertoire optionnel (défaut = LOG_DIR) pour
permettre des tests hermétiques.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "log"

SEPARATEUR = "=" * 60


def chemin_journal(source: str, log_dir: Path | None = None) -> Path:
    """<source>.log — journal d'importation, en ajout."""
    return (log_dir or LOG_DIR) / f"{source}.log"


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
    repertoire = log_dir or LOG_DIR
    if not repertoire.exists():
        return []
    return sorted(repertoire.glob("*.log"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
