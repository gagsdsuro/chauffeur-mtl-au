#!/usr/bin/env python3
"""
test_depots.py — Tests unitaires chauffeur.depots

Couvre les chemins canoniques (chemin_gd / chemin_evenements / chemin_journee)
et le chargement (charger_gd : sélection par id et replis ; charger_evenements ;
evenements_pour_date ; charger_journee) sur des fichiers synthétiques écrits
dans un répertoire temporaire (hermétique, aucune donnée live requise).

Usage : python3 tests/test_depots.py   (code de sortie 0 si tout passe)
"""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.depots import (  # noqa: E402
    charger_evenements, charger_gd, charger_journee,
    chemin_evenements, chemin_gd, chemin_journee, evenements_pour_date,
)

GD_104 = {
    "ligne": "104", "direction": "est",
    "routes": [{
        "line_number": "104", "direction": "Est",
        "parcours": [
            {"id": 1, "name": "Parcours principal",
             "direction": ["Via - Industriel", "Gauche - Lafleur"]},
            {"id": 3, "name": "École",
             "direction": ["Via - Victoria"]},
        ],
    }],
}

EV_104 = {
    "ligne": "104", "direction": "est",
    "detours": [
        {"evenement_id": "1", "titre": "Détour",
         "date_heure_debut": "2026-06-10T04:00:00",
         "date_heure_fin":   "2026-06-20T23:59:00"},
        {"evenement_id": "2", "titre": "Expiré",
         "date_heure_fin":   "2026-06-01T23:59:00"},
    ],
}

JOURNEE = {"date": "2026-06-15", "journee_numero": "439", "pieces": []}


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp)
        (rep / "gd104_est.json").write_text(
            json.dumps(GD_104, ensure_ascii=False), encoding="utf-8")
        (rep / "104_est.json").write_text(
            json.dumps(EV_104, ensure_ascii=False), encoding="utf-8")
        (rep / "journee-2026-06-15.json").write_text(
            json.dumps(JOURNEE, ensure_ascii=False), encoding="utf-8")

        # ── Chemins canoniques ───────────────────────────────────────────────
        check(chemin_gd("104", "Est", rep).name == "gd104_est.json",
              "chemin_gd: direction devrait être minusculisée (gd104_est.json)")
        check(chemin_evenements("104", "Est", rep).name == "104_est.json",
              "chemin_evenements: nom attendu 104_est.json")
        check(chemin_journee("2026-06-15", rep).name == "journee-2026-06-15.json",
              "chemin_journee: nom attendu journee-2026-06-15.json")

        # ── charger_gd ───────────────────────────────────────────────────────
        instr, parc = charger_gd("104", "est", 3, gd_dir=rep)
        check(instr == ["Via - Victoria"] and parc and parc["name"] == "École",
              f"charger_gd id=3: attendu parcours École, obtenu {parc}")

        instr, parc = charger_gd("104", "est", 99, gd_dir=rep)
        check(parc and parc["id"] == 1,
              "charger_gd id inconnu: repli sur le premier parcours attendu")

        instr, parc = charger_gd("104", "est", None, gd_dir=rep)
        check(parc and parc["id"] == 1 and instr[0] == "Via - Industriel",
              "charger_gd id=None: premier parcours attendu")

        instr, parc = charger_gd("999", "est", 1, gd_dir=rep)
        check(instr == [] and parc is None,
              "charger_gd fichier absent: ([], None) attendu")

        # ── charger_evenements ───────────────────────────────────────────────
        evts = charger_evenements("104", "est", events_dir=rep)
        check(len(evts) == 2, f"charger_evenements: 2 attendus, obtenu {len(evts)}")
        check(charger_evenements("999", "est", events_dir=rep) == [],
              "charger_evenements fichier absent: [] attendu")

        # ── evenements_pour_date ─────────────────────────────────────────────
        dans = evenements_pour_date("104", "est", date(2026, 6, 15), events_dir=rep)
        check([e["evenement_id"] for e in dans] == ["1"],
              f"evenements_pour_date 06-15: seul #1 attendu, obtenu {dans}")
        hors = evenements_pour_date("104", "est", date(2026, 7, 15), events_dir=rep)
        check(hors == [],
              f"evenements_pour_date 07-15: aucun attendu, obtenu {hors}")

        # ── charger_journee ──────────────────────────────────────────────────
        j = charger_journee(chemin_journee("2026-06-15", rep))
        check(j.get("journee_numero") == "439",
              "charger_journee: journee_numero attendu 439")

    # ── Résultat ──────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_depots")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ chemins canoniques + charger_gd/evenements/journee + filtre date")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
