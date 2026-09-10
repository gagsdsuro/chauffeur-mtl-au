#!/usr/bin/env python3
"""
test_journal_commun.py — Routage des journaux : flotte (commun) vs personnel

Couvre chauffeur.journal : les sources de la flotte (SOURCES_COMMUNES :
parse_gd, parse_event, fetch_gtfs, fetch_gtfs_rt) écrivent dans le journal
commun (LOG_DIR_COMMUN, data/log/), les autres (parse_journee, carte_agent, …)
dans le journal personnel (LOG_DIR par défaut). Un répertoire fourni par
l'appelant l'emporte toujours (tests hermétiques existants).

Hermétique : chauffe journal.LOG_DIR_COMMUN et journal.LOG_DIR sur des
répertoires temporaires (aucun accès à data/).

Usage : python3 tests/test_journal_commun.py   (code de sortie 0 si tout passe)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import chauffeur.journal as journal  # noqa: E402

SOURCES_FLOTTE = sorted(journal.SOURCES_COMMUNES)
SOURCES_PERSO = ["parse_journee", "carte_agent"]


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        commun = Path(tmp) / "commun"
        perso = Path(tmp) / "perso"
        journal.LOG_DIR_COMMUN = commun
        journal.LOG_DIR = perso

        # ── Routage par source (aucun répertoire fourni) ─────────────────────
        for src in SOURCES_FLOTTE:
            check(journal.chemin_journal(src) == commun / f"{src}.log",
                  f"flotte: {src} doit être journalisé en commun ({commun})")
        for src in SOURCES_PERSO:
            check(journal.chemin_journal(src) == perso / f"{src}.log",
                  f"perso: {src} doit rester dans le journal personnel ({perso})")

        # ── Répertoire explicite : l'emporte sur le routage ──────────────────
        explicite = Path(tmp) / "explicite"
        check(journal.chemin_journal("parse_gd", explicite) == explicite / "parse_gd.log",
              "explicite: le répertoire fourni doit primer sur le routage")

        # ── Écriture réelle (ecrire_bloc / ecrire_ligne par défaut) ──────────
        journal.ecrire_bloc("parse_gd", "rapport G-D")
        journal.ecrire_ligne("fetch_gtfs", "Téléchargement GTFS")
        journal.ecrire_bloc("parse_journee", "rapport journée")
        check((commun / "parse_gd.log").exists() and (commun / "fetch_gtfs.log").exists(),
              "écriture: un import de flotte doit créer son journal en commun")
        check((perso / "parse_journee.log").exists(),
              "écriture: un import personnel doit créer son journal personnel")
        check(not (perso / "parse_gd.log").exists(),
              "écriture: rien de la flotte dans le journal personnel")

        # ── lister_journaux_communs / _personnels ─────────────────────────────
        noms_communs = {p.name for p in journal.lister_journaux_communs()}
        check(noms_communs == {"parse_gd.log", "fetch_gtfs.log"},
              f"liste: journaux communs attendus (obtenu {noms_communs})")
        noms_perso = {p.name for p in journal.lister_journaux_personnels()}
        check(noms_perso == {"parse_journee.log"},
              f"liste: journaux personnels attendus (obtenu {noms_perso})")

    if echecs:
        print("✗ test_journal_commun")
        for e in echecs:
            print(f"    {e}")
        print(f"\n0/1 cas réussis")
        return 1

    print("✓ routage flotte (commun) vs personnel + lister_journaux_communs/personnels")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())