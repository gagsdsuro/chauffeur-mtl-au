#!/usr/bin/env python3
"""
test_rapport_gd.py — Tests de régression du DOMAINE de rapport_gd.py

Le pipeline domaine (build_rows → annotate_events → apply_gd_detours →
insert_added_stops_inline → filtrage) est pur : il ne dépend que de
(instructions G-D, arrêts ordonnés, noms d'arrêts, évènements). On gèle ces
entrées — pas les fichiers GTFS volumineux — dans tests/cas_rapport_gd/<nom>/ :
  • gd.json          fichier Gauche-Droite gelé
  • events.json      liste d'évènements déjà filtrés à fournir au domaine
  • gtfs_stops.json  {stops: [[seq, stop_id], …], stop_names: {id: {code,name}}}
  • params.json      {parcours, arret_debut, arret_fin}
  • attendu.json     snapshot de rows / added / orphan_events / parcours

Le test appelle les fonctions via rapport_gd (rg.*) ; après l'extraction du
domaine vers chauffeur/gd.py, rapport_gd les ré-exporte → le test reste valide.

Usage : python3 tests/test_rapport_gd.py [nom]   (code de sortie 0 si tout passe)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import rapport_gd as rg  # noqa: E402


def domaine_snapshot(dossier: Path) -> dict:
    """Rejoue le pipeline domaine sur les entrées gelées du cas."""
    gd_data = json.loads((dossier / "gd.json").read_text(encoding="utf-8"))
    events  = json.loads((dossier / "events.json").read_text(encoding="utf-8"))
    gtfs    = json.loads((dossier / "gtfs_stops.json").read_text(encoding="utf-8"))
    params  = json.loads((dossier / "params.json").read_text(encoding="utf-8"))

    all_parcours    = gd_data.get("routes", [{}])[0].get("parcours", [])
    parcours        = rg._select_parcours(all_parcours, params.get("parcours"))
    gd_instructions = parcours.get("direction", [])

    stops      = [tuple(x) for x in gtfs["stops"]]
    stop_names = gtfs["stop_names"]

    rows = rg.build_rows(gd_instructions, stops, stop_names)
    rows, added, orphan_events = rg.annotate_events(rows, events)
    rows = rg.apply_gd_detours(rows, events)
    rows, added = rg.insert_added_stops_inline(rows, added)
    if params.get("arret_debut") or params.get("arret_fin"):
        rows = rg.filter_rows_by_stop_range(
            rows, params.get("arret_debut"), params.get("arret_fin"))
    rows = rg.rows_de_rendu(rows)

    return {
        "parcours": {"name": parcours.get("name", ""),
                     "start": parcours.get("start", ""),
                     "end": parcours.get("end", "")},
        "rows": rows,
        "added": added,
        "orphan_events": [e.get("evenement_id", "") for e in orphan_events],
    }


def jouer_cas(dossier: Path) -> list:
    attendu = json.loads((dossier / "attendu.json").read_text(encoding="utf-8"))
    obtenu = domaine_snapshot(dossier)
    # Comparaison via JSON canonique (les rows contiennent des types simples).
    a = json.dumps(attendu, ensure_ascii=False, sort_keys=True)
    o = json.dumps(obtenu,  ensure_ascii=False, sort_keys=True)
    if a == o:
        return []
    # Diff grossier : signaler les premières lignes divergentes.
    ecarts = []
    if attendu.get("parcours") != obtenu.get("parcours"):
        ecarts.append(f"parcours: {obtenu.get('parcours')} != {attendu.get('parcours')}")
    ra, ro = attendu.get("rows", []), obtenu.get("rows", [])
    if len(ra) != len(ro):
        ecarts.append(f"rows: longueur {len(ro)} != {len(ra)}")
    for i, (x, y) in enumerate(zip(ro, ra)):
        if x != y:
            ecarts.append(f"rows[{i}]: {x} != {y}")
            if len(ecarts) > 5:
                break
    if attendu.get("added") != obtenu.get("added"):
        ecarts.append(f"added: {obtenu.get('added')} != {attendu.get('added')}")
    if attendu.get("orphan_events") != obtenu.get("orphan_events"):
        ecarts.append(f"orphan_events: {obtenu.get('orphan_events')} != {attendu.get('orphan_events')}")
    return ecarts or ["snapshot différent (diff JSON)"]


def main() -> int:
    base = ROOT / "tests" / "cas_rapport_gd"
    if not base.exists():
        print("Aucun cas dans tests/cas_rapport_gd/ — créer avec creer_cas_rapport_gd.py")
        return 1
    noms = sys.argv[1:] or sorted(d.name for d in base.iterdir() if d.is_dir())
    echecs = 0
    for nom in noms:
        ecarts = jouer_cas(base / nom)
        if ecarts:
            echecs += 1
            print(f"✗ {nom}")
            for e in ecarts:
                print(f"    {e}")
        else:
            print(f"✓ {nom}")
    print(f"\n{len(noms) - echecs}/{len(noms)} cas réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
