#!/usr/bin/env python3
"""
test_effectif.py — Tests unitaires chauffeur.effectif

Couvre bornes_quart() : liste vide, tri par valeur réelle (pas lexicale) sur
des heures non zero-paddées, quart franchissant minuit, une seule heure.

Usage : python3 tests/test_effectif.py   (code de sortie 0 si tout passe)
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.effectif import bornes_quart  # noqa: E402

JOUR = date(2026, 6, 15)


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    check(bornes_quart([], JOUR) is None,
          "bornes_quart: liste vide devrait retourner None")

    check(bornes_quart(["10:00"], JOUR) == ("10:00", "10:00"),
          "bornes_quart: une seule heure devrait retourner (h, h)")

    # Tri par valeur réelle, pas lexical : "9:15" < "10:00" numériquement,
    # mais "9:15" > "10:00" en comparaison de chaînes (le '9' > '1').
    r = bornes_quart(["9:15", "10:00"], JOUR)
    check(r == ("9:15", "10:00"),
          f"bornes_quart: tri par valeur attendu ('9:15','10:00'), obtenu {r}")

    r = bornes_quart(["10:00", "9:15", "14:30"], JOUR)
    check(r == ("9:15", "14:30"),
          f"bornes_quart: min/max attendu ('9:15','14:30'), obtenu {r}")

    # Quart franchissant minuit : "25:15" (01:15 le lendemain) est après
    # "23:50" dans le temps réel, malgré un chiffre de dizaine plus petit.
    r = bornes_quart(["23:50", "25:15"], JOUR)
    check(r == ("23:50", "25:15"),
          f"bornes_quart: quart franchissant minuit, obtenu {r}")

    # L'ordre inverse dans la liste ne devrait rien changer.
    r = bornes_quart(["25:15", "23:50"], JOUR)
    check(r == ("23:50", "25:15"),
          f"bornes_quart: ordre d'entrée ne devrait pas influencer le résultat, obtenu {r}")

    if echecs:
        print("✗ test_effectif")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ bornes_quart (vide, unique, tri par valeur, franchissement de minuit)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
