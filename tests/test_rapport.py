#!/usr/bin/env python3
"""
test_rapport.py — Tests de régression de gen_rapport.py

Rejoue chaque cas figé dans tests/cas_rapport/<nom>/ :
  • carte.pdf      copie du PDF de carte agent
  • gd/            fichiers Gauche-Droite gelés (gd<ligne>_<direction>.json)
  • attendu.json   lignes reconnues + directions G-D appariées

Le cas est hermétique : on redirige gen_rapport.GD_DIR vers le dossier gd/ gelé,
donc le test ne dépend pas des données live de data/Gauche-Droite/.

Couvre les régressions connues :
  • reconnaissance des lignes sans « - P » (ex. « 125 / - / Régulier »)
  • appariement des terminus par jetons (« Station McGill (De Maisonneuve /
    Robert-Bourassa) » ↔ « DE MAISONNEUVE / ROBERT-BOURASSA »)

Usage :
    python3 tests/test_rapport.py                 # tous les cas
    python3 tests/test_rapport.py carte-455       # un cas précis

Code de sortie : 0 si tous les cas passent, 1 sinon.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gen_rapport as gr  # noqa: E402


def calculer_snapshot(dossier: Path) -> dict:
    """Produit la structure de référence d'un cas (lignes + directions appariées)."""
    gr.GD_DIR = dossier / "gd"          # redirige vers les G-D gelés du cas
    carte = gr.parse_carte_agent(dossier / "carte.pdf")

    directions = {}
    for numero in carte["lignes"]:
        segments = carte["segments"].get(numero, [])
        dirs = gr.load_gd_directions(numero, segments)
        directions[numero] = sorted(
            ({"sens": d["sens"], "parcours": d["parcours_nom"]} for d in dirs),
            key=lambda x: (x["sens"], x["parcours"]),
        )

    return {
        "carte":      carte["assignation"],
        "lignes":     carte["lignes"],
        "directions": directions,
    }


def jouer_cas(dossier: Path) -> list:
    """Rejoue un cas ; retourne la liste des écarts (vide = succès)."""
    attendu = json.loads((dossier / "attendu.json").read_text(encoding="utf-8"))
    obtenu = calculer_snapshot(dossier)

    ecarts = []
    if obtenu["carte"] != attendu["carte"]:
        ecarts.append(f"carte: obtenu {obtenu['carte']!r}, attendu {attendu['carte']!r}")
    if obtenu["lignes"] != attendu["lignes"]:
        ecarts.append(f"lignes: obtenu {obtenu['lignes']!r}, attendu {attendu['lignes']!r}")

    for ligne in sorted(set(obtenu["directions"]) | set(attendu["directions"])):
        o = obtenu["directions"].get(ligne, "(absente)")
        a = attendu["directions"].get(ligne, "(absente)")
        if o != a:
            ecarts.append(f"directions[{ligne}]: obtenu {o}, attendu {a}")
    return ecarts


def main() -> int:
    base = ROOT / "tests" / "cas_rapport"
    if not base.exists():
        print("Aucun cas dans tests/cas_rapport/ — créer avec creer_cas_rapport.py")
        return 1
    noms = sys.argv[1:] or sorted(d.name for d in base.iterdir() if d.is_dir())
    if not noms:
        print("Aucun cas dans tests/cas_rapport/ — créer avec creer_cas_rapport.py")
        return 1

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
