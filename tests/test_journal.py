#!/usr/bin/env python3
"""
test_journal.py — Tests unitaires journaux d'importation

Couvre chauffeur.journal (chemin_journal, ecrire_bloc, ecrire_ligne,
lister_journaux) sur un répertoire temporaire (hermétique via log_dir=).

Le test le plus important est celui du format du bloc : parse_event.log
accumule un historique depuis 2026-06, et les blocs écrits après la
centralisation doivent y rester indiscernables des anciens.

Usage : python3 tests/test_journal.py   (code de sortie 0 si tout passe)
"""
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.journal import (  # noqa: E402
    chemin_journal,
    ecrire_bloc,
    ecrire_ligne,
    lister_journaux,
)

# Format historique : ligne vide, 60 « = », horodatage, 60 « = », rapport.
MOTIF_BLOC = re.compile(
    r"\n={60}\n\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\n={60}\n(.*)\n", re.S
)
MOTIF_LIGNE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] \[(\w+)\] (.*)$"
)


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    tmp = Path(tempfile.mkdtemp())

    # ── chemin_journal ────────────────────────────────────────────────────────
    check(chemin_journal("parse_gd", tmp) == tmp / "parse_gd.log",
          "chemin: <source>.log dans le répertoire fourni")

    # ── ecrire_bloc : répertoire créé à la demande ────────────────────────────
    absent = tmp / "sous" / "dossier"
    ecrire_bloc("essai", "rapport", log_dir=absent)
    check((absent / "essai.log").exists(),
          "bloc: le répertoire manquant doit être créé")

    # ── ecrire_bloc : format identique à l'historique ─────────────────────────
    ecrire_bloc("fmt", "✅ Ligne 168 Nord - 1 événement(s) traité(s)", log_dir=tmp)
    contenu = chemin_journal("fmt", tmp).read_text(encoding="utf-8")
    m = MOTIF_BLOC.search(contenu)
    check(m is not None, "bloc: format attendu (=×60 / horodatage / =×60 / rapport)")
    check(m and m.group(1) == "✅ Ligne 168 Nord - 1 événement(s) traité(s)",
          "bloc: le rapport doit être restitué tel quel (accents et émojis)")

    # Le même motif doit reconnaître l'historique réel, s'il est présent.
    reel = ROOT / "data" / "log" / "parse_event.log"
    if reel.exists():
        check(MOTIF_BLOC.search(reel.read_text(encoding="utf-8")) is not None,
              "bloc: le format doit reconnaître l'historique de parse_event.log")

    # ── ecrire_bloc : ajout sans écrasement ───────────────────────────────────
    ecrire_bloc("ajout", "premier", log_dir=tmp)
    ecrire_bloc("ajout", "second", log_dir=tmp)
    contenu = chemin_journal("ajout", tmp).read_text(encoding="utf-8")
    check("premier" in contenu and "second" in contenu,
          "bloc: le second écrit ne doit pas effacer le premier")
    check(contenu.count("=" * 60) == 4,
          "bloc: deux blocs = quatre séparateurs")
    check(contenu.index("premier") < contenu.index("second"),
          "bloc: ordre chronologique conservé")

    # ── ecrire_ligne ──────────────────────────────────────────────────────────
    retour = ecrire_ligne("fetch", "Téléchargement GTFS", log_dir=tmp)
    m = MOTIF_LIGNE.match(retour)
    check(m is not None, "ligne: format [horodatage] [NIVEAU] message")
    check(m and m.group(1) == "INFO", "ligne: niveau INFO par défaut")
    check(m and m.group(2) == "Téléchargement GTFS", "ligne: message restitué")
    check(retour + "\n" == chemin_journal("fetch", tmp).read_text(encoding="utf-8"),
          "ligne: la valeur retournée doit être exactement la ligne écrite "
          "(les scripts GTFS l'impriment aussi)")

    ecrire_ligne("fetch", "Échec réseau", niveau="ERROR", log_dir=tmp)
    lignes = chemin_journal("fetch", tmp).read_text(encoding="utf-8").splitlines()
    check(len(lignes) == 2, "ligne: ajout sans écrasement")
    check("[ERROR]" in lignes[1], "ligne: niveau personnalisé respecté")

    # ── lister_journaux ───────────────────────────────────────────────────────
    noms = [p.name for p in lister_journaux(tmp)]
    check(set(noms) == {"fmt.log", "ajout.log", "fetch.log"},
          f"liste: les journaux du répertoire, sans autre fichier (obtenu {noms})")
    check(lister_journaux(tmp / "inexistant") == [],
          "liste: répertoire absent → liste vide (pas d'exception)")

    # ── Résultat ──────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_journal")
        for e in echecs:
            print(f"    {e}")
        print(f"\n0/1 cas réussis")
        return 1

    print("✓ chemin_journal + ecrire_bloc (format historique) + ecrire_ligne "
          "+ lister_journaux")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
