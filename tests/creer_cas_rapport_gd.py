#!/usr/bin/env python3
"""
creer_cas_rapport_gd.py — Fige un cas de régression du domaine de rapport_gd.py

Extrait depuis les données live (GTFS + G-D + Events) les ENTRÉES du pipeline
domaine et les gèle dans tests/cas_rapport_gd/<nom>/ (gd.json, events.json,
gtfs_stops.json, params.json, attendu.json). VÉRIFIER attendu.json avant commit.

Usage :
    python3 tests/creer_cas_rapport_gd.py --ligne 125 --direction ouest --date 2026-06-11
        [--parcours principal] [--arret-debut 54112] [--arret-fin 57365] [--nom ...]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import rapport_gd as rg                       # noqa: E402
from test_rapport_gd import domaine_snapshot  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ligne", required=True)
    ap.add_argument("--direction", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--parcours", default=None)
    ap.add_argument("--arret-debut", default=None)
    ap.add_argument("--arret-fin", default=None)
    ap.add_argument("--nom", default=None)
    args = ap.parse_args()

    rg.GTFS = ROOT / "data" / "gtfs" / "gtfs_stm"
    nom = args.nom or f"gd-{args.ligne}-{args.direction}-{args.date}"
    dossier = ROOT / "tests" / "cas_rapport_gd" / nom
    dossier.mkdir(parents=True, exist_ok=True)

    # G-D
    gd_path = ROOT / f"data/Gauche-Droite/gd{args.ligne}_{args.direction}.json"
    gd_data = json.loads(gd_path.read_text(encoding="utf-8"))
    (dossier / "gd.json").write_text(
        json.dumps(gd_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Arrêts GTFS ordonnés + noms (restreints aux arrêts du trajet)
    rid = rg.get_route_id(args.ligne)
    did = rg.get_direction_id(rid, args.direction)
    stops = rg.get_stops_for_line(rid, did)
    all_names = rg.load_stop_names()
    stop_names = {sid: all_names[sid] for _, sid in stops if sid in all_names}
    (dossier / "gtfs_stops.json").write_text(
        json.dumps({"stops": [[seq, sid] for seq, sid in stops],
                    "stop_names": stop_names}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # Évènements filtrés (date-seule, comme le rapport journée complète)
    events = rg.load_events(args.ligne, args.direction, ROOT, date_str=args.date)
    (dossier / "events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")

    params = {"parcours": args.parcours,
              "arret_debut": args.arret_debut, "arret_fin": args.arret_fin}
    (dossier / "params.json").write_text(
        json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")

    snap = domaine_snapshot(dossier)
    (dossier / "attendu.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Cas créé : {dossier.relative_to(ROOT)}")
    print(f"  {len(stops)} arrêts, {len(events)} évènements, {len(snap['rows'])} lignes de rapport")
    print("VÉRIFIER attendu.json avant de committer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
