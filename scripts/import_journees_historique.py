#!/usr/bin/env python3
"""
import_journees_historique.py — Importation unique de l'historique des journées
                                  depuis data/import/CMTL_journee_historique.xlsx
                                  vers data/journees/journee-YYYY-MM-DD.json

Le fichier source est un export large (une ligne = une pièce, jusqu'à 4 trajets
en colonnes) qui ne conserve que certains champs réels ; le reste (heures,
lieux, arrêts, direction, id_parcours, detour) est du remplissage de gabarit
non représentatif et n'est donc pas importé tel quel.

Champs réels importés : date, garage_id, garage, journee_numero, id de pièce,
numero_autobus, matricules de relève, ligne de chaque trajet de service.

Ne modifie jamais un fichier journee-*.json déjà présent (importation unique).

Usage :
    python3 scripts/import_journees_historique.py             # importe
    python3 scripts/import_journees_historique.py --dry-run   # simulation, aucune écriture
"""
import argparse
import json
import string
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parent.parent
XLSX_PATH    = PROJECT_ROOT / "data" / "import" / "CMTL_journee_historique.xlsx"

sys.path.insert(0, str(PROJECT_ROOT))
from chauffeur.depots import JOURNEES_DIR  # noqa: E402  (répertoire privé du matricule courant)

N_TRAJET_SLOTS  = 4
BASE_COLS       = 15   # nb de colonnes avant le 1er slot de trajet
COLS_PER_TRAJET = 9


def _row_to_piece(row: tuple, suffix: str = "") -> dict:
    piece_id = f"{row[5]}{suffix}"
    numero_autobus = row[6]

    releve: dict = {}
    je_releve_mat = row[13] or ""
    je_suis_releve_par_mat = row[14] or ""
    if je_releve_mat:
        releve["je_releve"] = {"nom": "", "matricule": str(je_releve_mat)}
    if je_suis_releve_par_mat:
        releve["je_suis_releve_par"] = {"nom": "", "matricule": str(je_suis_releve_par_mat)}

    trajets = []
    for slot in range(N_TRAJET_SLOTS):
        base = BASE_COLS + slot * COLS_PER_TRAJET
        if row[base] is None:   # slot vide
            continue
        ligne = row[base + 1]
        trajets.append({
            "type": "service",
            "ligne": str(ligne) if ligne is not None else None,
            "direction": "",
            "id_parcours": None,
            "detour": False,
            "depart": {},
            "arrivee": {},
        })

    return {
        "id": piece_id,
        "numero_autobus": str(numero_autobus) if numero_autobus is not None else None,
        "duree": "",
        "prise": "",
        "lieu_prise": "",
        "debut": "",
        "fin": "",
        "lieu_fin": "",
        "releve": releve or None,
        "trajets": trajets,
    }


def _build_journee(date_str: str, rows: list[tuple]) -> dict:
    first = rows[0]

    by_piece_id: dict[str, list[tuple]] = defaultdict(list)
    for r in rows:
        by_piece_id[r[5]].append(r)

    pieces = []
    for group in by_piece_id.values():
        if len(group) == 1:
            pieces.append(_row_to_piece(group[0]))
        else:
            # Doublon (date, piece_id) = remplacement de bus en cours de pièce
            # → deux pièces distinctes, suffixées a/b/c...
            for i, r in enumerate(group):
                pieces.append(_row_to_piece(r, suffix=string.ascii_lowercase[i]))

    return {
        "date": date_str,
        "garage_id": str(first[1]) if first[1] is not None else "",
        "garage": first[2] or "",
        "journee_numero": first[3],
        "temps_travaille": "",
        "temps_supplementaire": "",
        "mis_a_jour": "",
        "pieces": pieces,
    }


def load_rows(xlsx_path: Path) -> list[tuple]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Journée"]
    return [r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] is not None]


def main():
    ap = argparse.ArgumentParser(
        description="Importe une fois l'historique des journées depuis "
                     "data/import/CMTL_journee_historique.xlsx vers data/journees/."
    )
    ap.add_argument("--xlsx", default=str(XLSX_PATH), help="Chemin du fichier xlsx source.")
    ap.add_argument("--dry-run", action="store_true",
                     help="N'écrit aucun fichier, affiche seulement ce qui serait fait.")
    args = ap.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        print(f"ERREUR: fichier introuvable : {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    rows = load_rows(xlsx_path)
    by_date: dict[str, list[tuple]] = defaultdict(list)
    for r in rows:
        by_date[r[0].date().isoformat()].append(r)

    JOURNEES_DIR.mkdir(parents=True, exist_ok=True)

    created, skipped = 0, 0
    for date_str in sorted(by_date):
        out_path = JOURNEES_DIR / f"journee-{date_str}.json"
        if out_path.exists():
            skipped += 1
            continue

        journee = _build_journee(date_str, by_date[date_str])
        if args.dry_run:
            print(f"[dry-run] créerait {out_path.name} ({len(journee['pieces'])} pièce(s))")
        else:
            out_path.write_text(
                json.dumps(journee, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(f"créé {out_path.name} ({len(journee['pieces'])} pièce(s))")
        created += 1

    print(f"\n{created} fichier(s) {'à créer' if args.dry_run else 'créé(s)'}, "
          f"{skipped} ignoré(s) (déjà présents).")


if __name__ == "__main__":
    main()
