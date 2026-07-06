#!/usr/bin/env python3
"""
test_periodes.py — Tests unitaires chauffeur.periodes

Couvre identite_ca() sur le calendrier réel 2026 (data/reference/periodes_stm_2026.json) :
semaine normale, samedi/dimanche, férié isolé dans une semaine de liste, semaines de
variation (relâche, construction — une identité par semaine du bloc), et une date hors
couverture du calendrier.

Usage : python3 tests/test_periodes.py   (code de sortie 0 si tout passe)
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.periodes import identite_ca  # noqa: E402


def main() -> int:
    echecs = []

    def verifie(d, numero, attendu, label):
        obtenu = identite_ca(date.fromisoformat(d), numero)
        if obtenu != attendu:
            echecs.append(f"{label}: identite_ca({d!r}, {numero!r}) = {obtenu}, attendu {attendu}")

    # ── Semaine normale d'une liste (mardi 6 janvier, liste du 5 janvier) ──────
    verifie("2026-01-06", "458", ("458", "L2026-01-05", "semaine"), "mardi liste")

    # ── Samedi / dimanche, même liste ──────────────────────────────────────────
    verifie("2026-01-10", "458", ("458", "L2026-01-05", "samedi"), "samedi liste")
    verifie("2026-01-11", "458", ("458", "L2026-01-05", "dimanche"), "dimanche liste")

    # ── Férié isolé à l'intérieur d'une semaine de liste par ailleurs normale ──
    # 24 juin 2026 (mercredi) tombe dans la semaine de début de liste du 15 juin,
    # mais doit avoir sa propre identité (pas celle de la liste).
    verifie("2026-06-24", "458", ("458", "2026-06-24", "variation"), "férié dans semaine de liste")
    # Le jeudi suivant (25 juin), lui, reste dans la liste normale.
    verifie("2026-06-25", "458", ("458", "L2026-06-15", "semaine"), "jour normal après férié")

    # ── Semaines de variation : une identité par semaine, même dans un bloc ────
    verifie("2026-03-02", "458", ("458", "V2026-03-02", "variation"), "relâche (lundi)")
    verifie("2026-03-04", "458", ("458", "V2026-03-02", "variation"), "relâche (mercredi)")
    verifie("2026-07-20", "458", ("458", "V2026-07-20", "variation"), "construction sem. 29")
    verifie("2026-07-27", "458", ("458", "V2026-07-27", "variation"), "construction sem. 30")
    if identite_ca(date(2026, 7, 20), "458") == identite_ca(date(2026, 7, 27), "458"):
        echecs.append("construction: sem. 29 et 30 ne devraient PAS partager la même identité")

    # ── Numéro différent → identité différente, même date ─────────────────────
    a = identite_ca(date(2026, 1, 6), "458")
    b = identite_ca(date(2026, 1, 6), "999")
    if a == b:
        echecs.append("numéros différents: ne devraient pas donner la même identité")

    # ── Date hors couverture du calendrier (avant la 1ère liste de l'année) ────
    try:
        identite_ca(date(2026, 1, 3), "458")
        echecs.append("2026-01-03: devait lever ValueError (hors couverture calendrier)")
    except ValueError:
        pass

    # ── Résultat ────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_periodes")
        for e in echecs:
            print(f"    {e}")
        print(f"\n0/1 cas réussis")
        return 1

    print("✓ identite_ca (liste, samedi/dimanche, férié isolé, variations, numéro, hors-calendrier)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
