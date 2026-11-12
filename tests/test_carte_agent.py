#!/usr/bin/env python3
"""
test_carte_agent.py — Tests de régression de carte_agent.py

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

import pymupdf  # noqa: E402
import carte_agent as cas  # noqa: E402

KEEP = ("type", "texte", "ligne", "heure", "prec")


def jouer_cas(dossier: Path) -> list:
    """Rejoue un cas ; retourne la liste des écarts (vide = succès)."""
    attendu = json.loads((dossier / "attendu.json").read_text(encoding="utf-8"))
    horaires = json.loads((dossier / "horaires.json").read_text(encoding="utf-8"))

    doc = pymupdf.open(str(dossier / "carte.pdf"))
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


def verifier_extract_numero() -> list:
    """Identifiants de 1 à 9999, aux coordonnées d'en-tête de la carte 47."""
    ecarts = []
    for numero in ("1", "9", "10", "47", "99", "100", "999", "1000", "9999",
                   "0", "10000", "123456", "-1", "47A", ""):
        spans = [
            {"text": "Société de Transport de Montréal", "bbox": (158, 13, 442, 33)},
            {"text": numero, "bbox": (12.75, 72.13, 42, 86.60)},
            {"text": "21/09/2026", "bbox": (96, 72.99, 156, 86.39)},
            # Un numéro dans le corps ne doit pas servir de repli.
            {"text": "85", "bbox": (12.75, 150, 27, 164)},
        ]
        attendu = numero if numero.isdecimal() and 1 <= int(numero) <= 9999 else "?"
        obtenu = cas.extract_meta(spans)["carte"]
        if obtenu != attendu:
            ecarts.append(f"numéro {numero!r}: obtenu {obtenu!r}, attendu {attendu!r}")
    return ecarts


def verifier_extract_jour_type() -> list:
    """extract_jour_type() sur du texte synthétique : champ présent (BASE, REM),
    absent, et « En vigueur » indépendant de la date de la carte elle-même."""
    ecarts = []

    avec_base = (
        "Société de Transport de Montréal\n"
        "En vigueur: 15/06/2026\n"
        "453\n"
        "Voiture\n"
        "20/06/2026\n"
        "Samedi - BASE\n"
        "Voiture\n"
    )
    r = cas.extract_jour_type(avec_base)
    if r != {"jour_type_imprime": "samedi", "variante": "BASE", "en_vigueur": "2026-06-15"}:
        ecarts.append(f"avec_base: {r}")

    avec_rem = (
        "Société de Transport de Montréal\n"
        "En vigueur: 18/05/2026\n"
        "523\n"
        "Voiture\n"
        "01/06/2026\n"
        "Semaine - REM\n"
        "Voiture\n"
    )
    r = cas.extract_jour_type(avec_rem)
    if r != {"jour_type_imprime": "semaine", "variante": "REM", "en_vigueur": "2026-05-18"}:
        ecarts.append(f"avec_rem: {r}")

    sans_champ = (
        "Société de Transport de Montréal\n"
        "458\n"
        "Voiture\n"
        "03/07/2026\n"
        "Voiture\n"
    )
    r = cas.extract_jour_type(sans_champ)
    if r != {"jour_type_imprime": None, "variante": None, "en_vigueur": None}:
        ecarts.append(f"sans_champ: {r}")

    return ecarts


def main() -> int:
    echecs = 0

    ecarts = verifier_extract_numero()
    if ecarts:
        echecs += 1
        print("ECHEC  extract_numero:")
        for e in ecarts:
            print(f"       - {e}")
    else:
        print("OK     extract_numero")

    ecarts = verifier_extract_jour_type()
    if ecarts:
        echecs += 1
        print("ECHEC  extract_jour_type:")
        for e in ecarts:
            print(f"       - {e}")
    else:
        print("OK     extract_jour_type")

    base = ROOT / "tests" / "cas"
    noms = sys.argv[1:] or sorted(d.name for d in base.iterdir() if d.is_dir())
    if not noms:
        print("Aucun cas de test dans tests/cas/ — créer avec creer_cas_test.py")
        return 1

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

    total = len(noms) + 2  # numéro et jour-type
    print(f"\n{total - echecs}/{total} cas passent.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
