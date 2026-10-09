#!/usr/bin/env python3
"""
test_depots.py — Tests unitaires chauffeur.depots

Couvre les chemins canoniques (chemin_gd / chemin_evenements / chemin_journee),
le chargement (charger_gd : sélection par id et replis ; charger_evenements ;
evenements_pour_date ; charger_journee), l'écriture (sauvegarder_journee) et
la fraîcheur (info_gd par mtime, info_gtfs par manifestes) sur des fichiers
synthétiques écrits dans un répertoire temporaire (hermétique, aucune donnée
live requise).

Usage : python3 tests/test_depots.py   (code de sortie 0 si tout passe)
"""
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.depots import (  # noqa: E402
    charger_evenements, charger_gd, charger_journee, sauvegarder_journee,
    chemin_evenements, chemin_gd, chemin_journee, evenements_pour_date,
    info_gd, info_gtfs,
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

GD_24E = {
    "ligne": "24e", "direction": "ouest",
    "routes": [{
        "line_number": "24e", "direction": "Ouest",
        "parcours": [{
            "id": 9, "name": "Parcours secondaire",
            "direction": ["Via - Sherbrooke", "Droite - Décarie"],
        }],
    }],
}


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp)
        (rep / "gd104_est.json").write_text(
            json.dumps(GD_104, ensure_ascii=False), encoding="utf-8")
        (rep / "gd24e_ouest.json").write_text(
            json.dumps(GD_24E, ensure_ascii=False), encoding="utf-8")
        (rep / "104_est.json").write_text(
            json.dumps(EV_104, ensure_ascii=False), encoding="utf-8")
        (rep / "journee-2026-06-15.json").write_text(
            json.dumps(JOURNEE, ensure_ascii=False), encoding="utf-8")

        # ── Chemins canoniques ───────────────────────────────────────────────
        check(chemin_gd("104", "Est", rep).name == "gd104_est.json",
              "chemin_gd: direction devrait être minusculisée (gd104_est.json)")
        check(chemin_gd("24E", "Ouest", rep).name == "gd24e_ouest.json",
              "chemin_gd: suffixe de ligne et direction attendus en minuscules")
        check(chemin_evenements("104", "Est", rep).name == "104_est.json",
              "chemin_evenements: nom attendu 104_est.json")
        check(chemin_journee("2026-06-15", rep).name == "journee-2026-06-15.json",
              "chemin_journee: nom attendu journee-2026-06-15.json")

        # ── charger_gd ───────────────────────────────────────────────────────
        for ligne in ("24E", "24e"):
            instr, parc = charger_gd(ligne, "ouest", 9, gd_dir=rep)
            check(parc and parc["id"] == 9
                  and instr == ["Via - Sherbrooke", "Droite - Décarie"],
                  f"charger_gd {ligne}: parcours 9 du fichier gd24e_ouest attendu")

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

        # ── sauvegarder_journee ──────────────────────────────────────────────
        dest = rep / "journee-2026-06-16.json"
        sauvegarder_journee(dest, {"date": "2026-06-16", "note": "été à Montréal"})
        contenu = dest.read_text(encoding="utf-8")
        check(contenu.endswith("\n") and not contenu.endswith("\n\n"),
              "sauvegarder_journee: un seul saut de ligne final attendu")
        check("  \"date\"" in contenu,
              "sauvegarder_journee: indentation 2 espaces attendue")
        check("été à Montréal" in contenu,
              "sauvegarder_journee: accents devraient être préservés (ensure_ascii=False)")
        relu = charger_journee(dest)
        check(relu == {"date": "2026-06-16", "note": "été à Montréal"},
              f"sauvegarder_journee: relecture inattendue : {relu}")

        # ── info_gd (fraîcheur par mtime) ────────────────────────────────────
        i = info_gd("24E", "ouest", gd_dir=rep)
        check(i["exists"] and i["fresh"] and i["path"] == rep / "gd24e_ouest.json",
              f"info_gd 24E: fichier gd24e_ouest présent et frais attendu, obtenu {i}")

        i = info_gd("999", "est", gd_dir=rep)
        check(not i["exists"] and i["path"] is None and not i["fresh"],
              "info_gd: fichier absent → exists=False attendu")

        i = info_gd("104", "est", gd_dir=rep)   # écrit à l'instant
        check(i["exists"] and i["fresh"] and i["age_days"] == 0,
              f"info_gd: fichier frais attendu (age 0), obtenu {i}")

        vieux = (datetime.now() - timedelta(days=200)).timestamp()
        os.utime(chemin_gd("104", "est", rep), (vieux, vieux))
        i = info_gd("104", "est", gd_dir=rep)
        check(i["exists"] and not i["fresh"] and i["age_days"] >= 199,
              f"info_gd: fichier de 200 j devrait être périmé, obtenu {i}")

    # ── info_gtfs (manifestes synthétiques) ──────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        i = info_gtfs(data_dir)
        check(i["static_age_days"] is None and i["static_ts"] == "–"
              and not i["rt_avail"] and i["rt_ts"] == "–",
              f"info_gtfs: répertoire vide → tout inconnu attendu, obtenu {i}")

        (data_dir / "gtfs").mkdir()
        (data_dir / "gtfs_rt").mkdir()
        il_y_a_3j = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        (data_dir / "gtfs" / "gtfs_manifest.json").write_text(
            json.dumps({"last_update": il_y_a_3j}), encoding="utf-8")
        (data_dir / "gtfs_rt" / "response_vehiclePositions.pb").write_bytes(b"")
        i = info_gtfs(data_dir)
        check(i["static_age_days"] == 3,
              f"info_gtfs: âge statique attendu 3 j, obtenu {i['static_age_days']}")
        check(i["rt_avail"] and i["rt_pb"].name == "response_vehiclePositions.pb",
              "info_gtfs: fichier RT présent → rt_avail=True attendu")

    # ── Résultat ──────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_depots")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ chemins canoniques + charger/sauvegarder_journee + evenements + info_gd/info_gtfs")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
