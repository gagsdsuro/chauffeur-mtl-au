#!/usr/bin/env python3
"""
test_appariement.py — Tests de chauffeur.appariement (alignement G-D ↔ GTFS)

1. Cas figés tests/cas_appariement/<ligne>-<direction>-<id>/ (parcours.json,
   gtfs_stops.json, attendu.json : étape par seq + blocs incertains) :
     • 811-ouest-13 — boucle Radisson ; attendu = recette manuelle corrigée
       (tmp/recette-appariement-811o.md, 52164 inclus, 52234 une seule fois).
       L'ancien glouton collait 19 arrêts à « Droite - Sherbrooke ».
     • 460-est-24  — voies de desserte : Métropolitain / Viau, Lacordaire,
       Langelier rangés après leur « vers X ». Les blocs Côte-de-Liesse et
       Crémazie restent signalés : ce sont de vraies ambiguïtés (rue répétée
       sans indice), à trancher par un humain.
2. Tests unitaires : invariants (monotonie, chaque seq une fois), ancres,
   rejet d'ancres non monotones, format des lignes, normalisation.

Usage : python3 tests/test_appariement.py [nom]   (code de sortie 0 si tout passe)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.appariement import (  # noqa: E402
    apparier, blocs_incertains, cle_rue, rows_depuis_appariement,
)

CAS_DIR = ROOT / "tests" / "cas_appariement"


def _invariants(resultat, stops) -> list:
    erreurs = []
    seqs = [a["seq"] for a in resultat["arrets"]]
    if seqs != [s for s, _ in stops]:
        erreurs.append("chaque seq GTFS doit apparaître une fois, dans l'ordre")
    etapes = [a["etape"] for a in resultat["arrets"]]
    if etapes != sorted(etapes):
        erreurs.append(f"étapes non monotones : {etapes}")
    return erreurs


def tester_cas(dossier: Path) -> list:
    parcours = json.loads((dossier / "parcours.json").read_text(encoding="utf-8"))
    gtfs = json.loads((dossier / "gtfs_stops.json").read_text(encoding="utf-8"))
    attendu = json.loads((dossier / "attendu.json").read_text(encoding="utf-8"))
    stops = [tuple(x) for x in gtfs["stops"]]

    resultat = apparier(parcours["direction"], stops, gtfs["stop_names"])
    erreurs = _invariants(resultat, stops)
    for a in resultat["arrets"]:
        voulu = attendu["etapes"].get(str(a["seq"]))
        if a["etape"] != voulu:
            nom = gtfs["stop_names"].get(a["stop_id"], {}).get("name", "")
            erreurs.append(f"seq {a['seq']} {nom} : étape {a['etape']}, attendu {voulu}")
    blocs = [b["seqs"] for b in resultat["blocs"]]
    if blocs != attendu["blocs"]:
        erreurs.append(f"blocs incertains {blocs}, attendu {attendu['blocs']}")
    return erreurs


# ── Tests unitaires ───────────────────────────────────────────────────────────

INSTR = ["Via - Terminus Exemple", "Droite - Alpha", "Gauche - Beta",
         "Via - vers Gamma", "Via - Beta", "Gauche - Terminus Exemple"]
NOMS = {
    "1": {"code": "1", "name": "Alpha / Joseph (Terminus Exemple"},
    "2": {"code": "2", "name": "Alpha / Delta"},
    "3": {"code": "3", "name": "Beta / Epsilon"},
    "4": {"code": "4", "name": "Beta / Gamma"},
}
STOPS = [(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "1")]   # boucle : stop 1 deux fois


def unitaires() -> list:
    erreurs = []

    r = apparier(INSTR, STOPS, NOMS)
    erreurs += _invariants(r, STOPS)
    obtenu = [a["etape"] for a in r["arrets"]]
    if obtenu != [0, 1, 2, 4, 5]:
        erreurs.append(f"synthétique : {obtenu} (attendu [0, 1, 2, 4, 5] — "
                       "terminus en boucle par seq, « vers Gamma » oriente Beta / Gamma)")

    # Ancre : forcer seq 3 sur la 2e « Beta » entraîne le reste.
    r = apparier(INSTR, STOPS, NOMS, ancres={3: 4})
    obtenu = [a["etape"] for a in r["arrets"]]
    if obtenu[2] != 4 or r["arrets"][2]["source"] != "manuel" or obtenu != sorted(obtenu):
        erreurs.append(f"ancre {{3: 4}} non respectée : {obtenu}")

    for ancres in ({2: 4, 3: 2}, {1: 99}):
        try:
            apparier(INSTR, STOPS, NOMS, ancres=ancres)
            erreurs.append(f"ancres invalides acceptées : {ancres}")
        except ValueError:
            pass

    rows = rows_depuis_appariement(INSTR, apparier(INSTR, STOPS, NOMS), NOMS)
    if [r["gd"] for r in rows if r["gd"]] != INSTR:
        erreurs.append("rows : chaque instruction doit être émise une fois, dans l'ordre")
    if not all({"gd", "seq", "stop_id", "stop_code", "stop_name"} <= set(r) for r in rows):
        erreurs.append("rows : format build_rows attendu")

    for brut, voulu in (("de l'Assomption", "assomption"),
                        ("de la Côte-de-Liesse", "cote de liesse"),
                        ("St-Laurent", "saint laurent"),
                        ("Métropolitain", "metropolitain")):
        if cle_rue(brut) != voulu:
            erreurs.append(f"cle_rue({brut!r}) = {cle_rue(brut)!r}, attendu {voulu!r}")

    # Régressions relevées sur la flotte complète (78 parcours).
    cas = [
        # « Terminus Dorval » n'attire pas les arrêts plantés sur la rue Dorval.
        (["Via - Terminus Dorval", "Via - Dorval"],
         {"a": {"name": "Terminus Dorval"}, "b": {"name": "Dorval / Carson"}}, [0, 1]),
        # Deux noms d'une même rue ; « (desserte) » ignoré.
        (["Via - Herron", "Gauche - du Bord-du-Lac - Lakeshore", "Via - Berri (desserte)"],
         {"a": {"name": "Bord-du-Lac / Decary"}, "b": {"name": "Berri / Cherrier"}}, [1, 2]),
        # Une sortie d'autoroute est une bretelle : pas d'arrêt dessus.
        (["Via - Bonaventure", "Via - sortie 5 - Île-des-Soeurs", "Via - de l'Île-des-Soeurs"],
         {"a": {"name": "Robert-Bourassa / Wellington"}, "b": {"name": "Station Île-des-Soeurs"}}, [0, 2]),
    ]
    for instr, noms, voulu in cas:
        stops = [(i + 1, sid) for i, sid in enumerate(noms)]
        obtenu = [a["etape"] for a in apparier(instr, stops, noms)["arrets"]]
        if obtenu != voulu:
            erreurs.append(f"{instr} : {obtenu}, attendu {voulu}")

    incs = [{"seq": 1, "etapes_possibles": [7, 10], "raison": "ambigu"},
            {"seq": 2, "etapes_possibles": [7, 10], "raison": "ambigu"},
            {"seq": 3, "etapes_possibles": [11, 13], "raison": "ambigu"}]
    blocs = [b["seqs"] for b in blocs_incertains(incs, [(1, "a"), (2, "b"), (3, "c")])]
    if blocs != [[1, 2], [3]]:
        erreurs.append(f"blocs : {blocs} (voisins sans étape commune non fusionnés)")
    return erreurs


def main() -> int:
    filtre = sys.argv[1] if len(sys.argv) > 1 else None
    echecs = 0
    if not filtre:
        erreurs = unitaires()
        print(("✅" if not erreurs else "❌") + " unitaires")
        for e in erreurs:
            print("   ", e)
        echecs += bool(erreurs)
    for dossier in sorted(p for p in CAS_DIR.iterdir() if p.is_dir()):
        if filtre and dossier.name != filtre:
            continue
        erreurs = tester_cas(dossier)
        print(("✅" if not erreurs else "❌") + f" {dossier.name}")
        for e in erreurs:
            print("   ", e)
        echecs += bool(erreurs)
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
