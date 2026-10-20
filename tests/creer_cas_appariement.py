#!/usr/bin/env python3
"""
creer_cas_appariement.py — Fige un cas de régression pour chauffeur.appariement.

Gèle le parcours G-D et la séquence d'arrêts GTFS (avec leurs noms) dans
tests/cas_appariement/<ligne>-<direction>-<id>/, puis écrit attendu.json à
partir du résultat courant. VÉRIFIER attendu.json avant de committer : il
doit refléter le bon appariement, pas seulement celui que l'algorithme produit.

Usage :
  python3 tests/creer_cas_appariement.py --ligne 811 --direction ouest --id 13
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.appariement import apparier  # noqa: E402
from chauffeur.gtfs import stop_names, stops_for_parcours  # noqa: E402

GTFS_DIR = ROOT / "data" / "gtfs" / "gtfs_stm"
GD_DIR = ROOT / "data" / "Gauche-Droite"
CAS_DIR = ROOT / "tests" / "cas_appariement"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--ligne", required=True)
    ap.add_argument("--direction", required=True)
    ap.add_argument("--id", type=int, required=True, help="id du parcours G-D")
    args = ap.parse_args()

    gd = json.loads((GD_DIR / f"gd{args.ligne}_{args.direction}.json").read_text(encoding="utf-8"))
    parcours = next((p for p in gd["routes"][0]["parcours"] if p["id"] == args.id), None)
    if parcours is None:
        print(f"Parcours id {args.id} introuvable", file=sys.stderr)
        return 1

    stops = stops_for_parcours(GTFS_DIR, args.ligne, args.direction, args.id)
    noms = stop_names(GTFS_DIR)
    noms_cas = {sid: noms[sid] for _, sid in stops if sid in noms}

    dossier = CAS_DIR / f"{args.ligne}-{args.direction}-{args.id}"
    dossier.mkdir(parents=True, exist_ok=True)

    def ecrire(nom, data):
        (dossier / nom).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")

    ecrire("parcours.json", parcours)
    ecrire("gtfs_stops.json", {"stops": stops, "stop_names": noms_cas})
    resultat = apparier(parcours["direction"], stops, noms_cas)
    ecrire("attendu.json", {
        "etapes": {str(a["seq"]): a["etape"] for a in resultat["arrets"]},
        "blocs": [b["seqs"] for b in resultat["blocs"]],
    })
    print(f"Cas figé : {dossier.relative_to(ROOT)} — vérifier attendu.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
