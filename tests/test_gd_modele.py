#!/usr/bin/env python3
"""
test_gd_modele.py — Modèle de lignes de chauffeur.gd : séquence linéaire.

Instruction G-D et arrêt GTFS occupent chacun leur ligne (un arrêt vient après
sa manœuvre, il ne la partage pas) ; `rows_de_rendu` refait la mise en page à
deux colonnes en dernier. Couvre :
  • build_rows : une ligne par instruction puis une par arrêt ;
  • rows_de_rendu : fusion instruction + 1er arrêt, jamais à travers un détour,
    sans modifier l'entrée, états distincts (detour_removed / cancelled) ;
  • un détour avec annulation d'arrêt s'insère entre la manœuvre et l'arrêt
    quand la manœuvre est contournée (elle est alors barrée) ;
  • filter_rows_by_stop_range garde l'instruction qui mène à l'arrêt de début.

Usage : python3 tests/test_gd_modele.py   (code de sortie 0 si tout passe)
"""
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chauffeur.gd import (  # noqa: E402
    annotate_events, apply_gd_detours, build_rows, filter_rows_by_stop_range,
    rows_de_rendu,
)

INSTR = ["Via - Alpha", "Droite - Beta", "Gauche - Gamma"]
NOMS = {
    "1": {"code": "1", "name": "Alpha / Delta"},
    "2": {"code": "2", "name": "Beta / Epsilon"},
    "3": {"code": "3", "name": "Beta / Zeta"},
    "4": {"code": "4", "name": "Gamma / Eta"},
}
STOPS = [(1, "1"), (2, "2"), (3, "3"), (4, "4")]


def _seq(rows):
    return [(r["gd"], r.get("stop_id")) for r in rows]


def lignes_separees():
    rows = build_rows(INSTR, STOPS, NOMS)
    attendu = [("Via - Alpha", None), ("", "1"), ("Droite - Beta", None), ("", "2"),
               ("", "3"), ("Gauche - Gamma", None), ("", "4")]
    return [] if _seq(rows) == attendu else [f"build_rows : {_seq(rows)}"]


def fusion_de_rendu():
    erreurs = []
    rows = annotate_events(build_rows(INSTR, STOPS, NOMS), [])[0]
    rows[0]["detour_removed"] = True
    copie = deepcopy(rows)
    rendu = rows_de_rendu(rows)
    if rows != copie:
        erreurs.append("rows_de_rendu modifie son entrée")
    if _seq(rendu) != [("Via - Alpha", "1"), ("Droite - Beta", "2"), ("", "3"),
                       ("Gauche - Gamma", "4")]:
        erreurs.append(f"fusion : {_seq(rendu)}")
    elif not rendu[0].get("detour_removed") or rendu[0]["cancelled"] != []:
        erreurs.append("états de l'instruction et de l'arrêt à garder distincts")

    # Un détour entre l'instruction et l'arrêt empêche la fusion.
    rows = build_rows(INSTR, STOPS, NOMS)
    rows.insert(1, {"gd": "Via - X", "seq": None, "stop_id": None, "stop_code": "",
                    "stop_name": "", "detour_added": True})
    if _seq(rows_de_rendu(rows))[:3] != [("Via - Alpha", None), ("Via - X", None), ("", "1")]:
        erreurs.append(f"fusion à travers un détour : {_seq(rows_de_rendu(rows))[:3]}")
    return erreurs


def evenement(titre_rue_entree):
    return {"evenement_id": "9", "titre": "Détour avec annulation d'arrêt", "motif": "Travaux",
            "effectif": "En tout temps", "arrets_annules": [{"id": "2", "nom": "Beta / Epsilon"}],
            "description_gd": f"VIA {titre_rue_entree}\nG/ OMEGA\nVIA R.R."}


def detour_contourne_la_manoeuvre():
    """Entrée « Alpha » ≠ « Droite - Beta » : cette manœuvre est contournée."""
    ev = evenement("ALPHA")
    rows = annotate_events(build_rows(INSTR, STOPS, NOMS), [ev])[0]
    rendu = rows_de_rendu(apply_gd_detours(rows, [ev]))
    gd = [r["gd"] for r in rendu]
    if gd[:4] != ["Via - Alpha", "Via - ALPHA", "Gauche - OMEGA", "Via - R.R."]:
        return [f"détour mal placé : {gd}"]
    beta = next(r for r in rendu if r["gd"] == "Droite - Beta")
    return [] if beta.get("detour_removed") and beta["cancelled"] else \
        ["la manœuvre contournée doit être barrée avec son arrêt annulé"]


def plage_garde_instruction():
    rows = build_rows(INSTR, STOPS, NOMS)
    plage = filter_rows_by_stop_range(rows, "2", "4")
    return [] if plage[0]["gd"] == "Droite - Beta" and plage[1]["stop_id"] == "2" \
        else [f"plage : {_seq(plage)}"]


TESTS = [lignes_separees, fusion_de_rendu, detour_contourne_la_manoeuvre,
         plage_garde_instruction]


def main() -> int:
    echecs = 0
    for test in TESTS:
        erreurs = test()
        print(("✅" if not erreurs else "❌") + f" {test.__name__}")
        for e in erreurs:
            print("   ", e)
        echecs += bool(erreurs)
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
