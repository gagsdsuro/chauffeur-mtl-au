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

from chauffeur.effectif import bornes_quart, event_applies_to_shift, parse_shift_time  # noqa: E402

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

    # ── Repli sur le commentaire quand l'effectif ne restreint rien ────────
    lundi = date(2026, 11, 9)       # lundi
    samedi = date(2026, 11, 14)

    def actif(ev, jour, debut, fin):
        return event_applies_to_shift(ev, parse_shift_time(debut, jour),
                                      parse_shift_time(fin, jour))

    ev = {"effectif": "En tout temps", "date_heure_debut": "2026-09-02T12:00:00",
          "date_heure_fin": "2026-12-31T19:00:00",
          "commentaire": "LUNDI AU VENDREDI 12H00 À 19H00"}
    check(not actif(ev, lundi, "9:37", "10:29"),
          "commentaire 12h-19h : le trajet 9:37-10:29 ne devrait pas être touché")
    check(actif(ev, lundi, "16:55", "17:59"),
          "commentaire 12h-19h : le trajet 16:55-17:59 devrait être touché")
    check(not actif(ev, samedi, "16:55", "17:59"),
          "commentaire « lundi au vendredi » : un samedi ne devrait pas être touché")

    # L'effectif prime : plage de l'effectif, commentaire ignoré.
    ev_eff = dict(ev, effectif="Seulement entre 07:00 et 09:00 chaque jour")
    check(actif(ev_eff, lundi, "7:30", "8:00") and not actif(ev_eff, lundi, "16:55", "17:59"),
          "effectif restrictif : le commentaire ne devrait pas s'y substituer")

    # Commentaire sans jours ni heures : aucune restriction.
    ev_txt = dict(ev, commentaire="ARRÊT DÉPLACÉ SUR LE VIADUC")
    check(actif(ev_txt, lundi, "9:37", "10:29") and actif(ev_txt, samedi, "9:37", "10:29"),
          "commentaire libre : ne devrait rien restreindre")

    # « Fin de semaine » dans le commentaire. (Le regex historique des jours
    # ouvrables, `semaine(?!\s*de)`, ne doit pas la prendre pour « semaine ».)
    ev_fds = dict(ev, commentaire="SAMEDI ET DIMANCHE SEULEMENT")
    check(actif(ev_fds, samedi, "9:00", "10:00") and not actif(ev_fds, lundi, "9:00", "10:00"),
          "commentaire « samedi et dimanche » : seulement la fin de semaine")

    for eff in ("Fin de semaine", "Les fins de semaine"):
        e = {"effectif": eff}
        check(actif(e, samedi, "9:00", "10:00") and not actif(e, lundi, "9:00", "10:00"),
              f"effectif « {eff} » : seulement la fin de semaine")

    if echecs:
        print("✗ test_effectif")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ bornes_quart (vide, unique, tri par valeur, minuit) + repli commentaire de l'effectif")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
