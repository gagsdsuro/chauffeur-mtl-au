#!/usr/bin/env python3
"""
creer_cas_test.py — Fige un cas de test de régression pour carte_agent.py

Capture, dans tests/cas/<nom>/ :
  • carte.pdf        copie du PDF source
  • horaires.json    horaires GTFS gelés (sortie de get_terminus_times)
  • attendu.json     métadonnées + plan d'annotations produits par le script

Le plan capturé devient la référence : VÉRIFIER MANUELLEMENT attendu.json
(ou le PDF annoté) avant de committer le cas. Ensuite, test_carte_agent.py
rejouera le cas à chaque itération sans dépendre du GTFS courant.

Usage :
    python3 tests/creer_cas_test.py --pdf data/ca/carte-agent-2026-06-09.pdf \
        --gtfs data/gtfs/gtfs_stm/ [--date 2026-06-09] [--nom carte-449]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pymupdf  # noqa: E402
import carte_agent as cas  # noqa: E402


def plan_sans_geometrie(plan: list) -> list:
    """Ne garde que les champs sémantiques (stables) du plan."""
    keep = ("type", "texte", "ligne", "heure", "prec")
    return [{k: a[k] for k in keep if k in a} for a in plan]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--gtfs", required=True)
    ap.add_argument("--date", help="AAAA-MM-JJ (défaut : extraite du nom du PDF)")
    ap.add_argument("--nom", help="nom du cas (défaut : carte-<numéro>)")
    args = ap.parse_args()

    src = Path(args.pdf).expanduser()
    date_str = cas.resolve_date(src, args.date)

    doc = pymupdf.open(str(src))
    page = doc[0]
    spans = cas.get_spans(page)
    meta = cas.extract_meta(spans)

    horaires = cas.get_terminus_times(Path(args.gtfs), meta["lignes"], date_str)
    plan = cas.plan_annotations(page, spans, horaires)
    doc.close()

    nom = args.nom or f"carte-{meta['carte']}"
    dossier = ROOT / "tests" / "cas" / nom
    dossier.mkdir(parents=True, exist_ok=True)

    shutil.copy2(src, dossier / "carte.pdf")
    (dossier / "horaires.json").write_text(
        json.dumps(horaires, ensure_ascii=False, indent=2), encoding="utf-8")
    attendu = {
        "date": date_str,
        "carte": meta["carte"], "debut": meta["debut"],
        "fin": meta["fin"], "lignes": meta["lignes"],
        "annotations": plan_sans_geometrie(plan),
    }
    (dossier / "attendu.json").write_text(
        json.dumps(attendu, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Cas de test créé : {dossier.relative_to(ROOT)}")
    print("VÉRIFIER attendu.json avant de committer — il fige le comportement actuel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
