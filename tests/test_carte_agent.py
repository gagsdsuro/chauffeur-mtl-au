#!/usr/bin/env python3
"""
test_carte_agent.py — Tests de régression de carte_agent_stm.py

Rejoue chaque cas figé dans tests/cas/<nom>/ (carte.pdf + horaires.json)
et compare métadonnées et plan d'annotations à attendu.json. Aucune
dépendance au GTFS courant : les horaires sont gelés dans le cas.

Usage :
    python3 tests/test_carte_agent.py            # tous les cas
    python3 tests/test_carte_agent.py carte-449  # un cas précis

Code de sortie : 0 si tous les cas passent, 1 sinon.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fitz  # noqa: E402
import carte_agent_stm as cas  # noqa: E402

KEEP = ("type", "texte", "ligne", "heure", "prec")


def jouer_cas(dossier: Path) -> list:
    """Rejoue un cas ; retourne la liste des écarts (vide = succès)."""
    attendu = json.loads((dossier / "attendu.json").read_text(encoding="utf-8"))
    horaires = json.loads((dossier / "horaires.json").read_text(encoding="utf-8"))

    doc = fitz.open(str(dossier / "carte.pdf"))
    page = doc[0]
    spans = cas.get_spans(page)
    meta = cas.extract_meta(spans)
    plan = [{k: a[k] for k in KEEP if k in a}
            for a in cas.plan_annotations(page, spans, horaires)]
    doc.close()

    ecarts = []
    for champ in ("carte", "debut", "fin", "lignes"):
        if meta[champ] != attendu[champ]:
            ecarts.append(f"{champ}: obtenu {meta[champ]!r}, attendu {attendu[champ]!r}")

    att = attendu["annotations"]
    if plan != att:
        for i in range(max(len(plan), len(att))):
            o = plan[i] if i < len(plan) else "(absent)"
            a = att[i] if i < len(att) else "(absent)"
            if o != a:
                ecarts.append(f"annotation {i}: obtenu {o}, attendu {a}")
    return ecarts


def main() -> int:
    base = ROOT / "tests" / "cas"
    noms = sys.argv[1:] or sorted(d.name for d in base.iterdir() if d.is_dir())
    if not noms:
        print("Aucun cas de test dans tests/cas/ — créer avec creer_cas_test.py")
        return 1

    echecs = 0
    for nom in noms:
        dossier = base / nom
        if not (dossier / "attendu.json").exists():
            print(f"ECHEC  {nom}: cas incomplet (attendu.json manquant)")
            echecs += 1
            continue
        ecarts = jouer_cas(dossier)
        if ecarts:
            echecs += 1
            print(f"ECHEC  {nom}:")
            for e in ecarts:
                print(f"       - {e}")
        else:
            print(f"OK     {nom}")

    print(f"\n{len(noms) - echecs}/{len(noms)} cas passent.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
