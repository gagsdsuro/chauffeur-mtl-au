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
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gen_rapport as gr  # noqa: E402


def _date_du_nom(nom: str) -> date:
    """Extrait la date cible du nom de cas (ex. « carte-455-2026-06-11 »)."""
    m = re.search(r"\d{4}-\d{2}-\d{2}", nom)
    return date.fromisoformat(m.group(0)) if m else date.today()


def calculer_snapshot(dossier: Path) -> dict:
    """Produit la projection de référence d'un cas à partir de build_rapport_data().

    Hermétique : GD_DIR et (si présent) EVENTS_DIR sont redirigés vers les
    fichiers gelés du cas. La projection couvre tout ce qu'un refactor pourrait
    altérer au niveau des données du rapport : méta, directions G-D appariées,
    classement applicable/non-applicable des évènements, et HLP.
    """
    gr.GD_DIR = dossier / "gd"          # redirige vers les G-D gelés du cas
    ev_dir = dossier / "events"
    if ev_dir.exists():
        gr.EVENTS_DIR = ev_dir          # redirige vers les évènements gelés du cas

    carte = gr.parse_carte_agent(dossier / "carte.pdf")
    data = gr.build_rapport_data(carte, _date_du_nom(dossier.name))

    directions, evenements = {}, {}
    for lg in data["lignes"]:
        num = lg["numero"]
        directions[num] = sorted(
            ({"sens": d["sens"], "parcours": d["parcours_nom"]} for d in lg["directions"]),
            key=lambda x: (x["sens"], x["parcours"]),
        )
        evenements[num] = {
            "applicables": sorted(
                ev.get("evenement_id", "") for ev in lg["detours_applicables"]),
            "non_applicables": sorted(
                ({"id": ev.get("evenement_id", ""),
                  "raison": ev.get("raison_exclusion", "")}
                 for ev in lg["detours_non_applicables"]),
                key=lambda x: x["id"],
            ),
        }

    return {
        "carte":  carte["assignation"],
        "lignes": carte["lignes"],
        "meta": {
            "date_travail": data["date_travail"],
            "jour_semaine": data["jour_semaine"],
            "heure_prise":  data["heure_prise"],
            "lieu_prise":   data["lieu_prise"],
            "heure_fin":    data["heure_fin"],
            "voiture":      data["voiture"],
            "garage":       data["agent"]["garage"],
        },
        "directions": directions,
        "evenements": evenements,
        "hlp": [{"id": h["id"], "instructions": h["instructions"]} for h in data["hlp"]],
    }


def _diff(obtenu, attendu, chemin: str = "") -> list:
    """Compare récursivement deux structures JSON ; retourne les écarts par chemin."""
    if isinstance(attendu, dict) and isinstance(obtenu, dict):
        ecarts = []
        for k in sorted(set(attendu) | set(obtenu)):
            sous = f"{chemin}.{k}" if chemin else k
            ecarts += _diff(obtenu.get(k, "(absent)"), attendu.get(k, "(absent)"), sous)
        return ecarts
    if isinstance(attendu, list) and isinstance(obtenu, list):
        if len(attendu) != len(obtenu):
            return [f"{chemin}: longueur obtenu {len(obtenu)} ≠ attendu {len(attendu)}"]
        ecarts = []
        for i, (o, a) in enumerate(zip(obtenu, attendu)):
            ecarts += _diff(o, a, f"{chemin}[{i}]")
        return ecarts
    return [] if obtenu == attendu else [f"{chemin}: obtenu {obtenu!r}, attendu {attendu!r}"]


def jouer_cas(dossier: Path) -> list:
    """Rejoue un cas ; retourne la liste des écarts (vide = succès)."""
    attendu = json.loads((dossier / "attendu.json").read_text(encoding="utf-8"))
    return _diff(calculer_snapshot(dossier), attendu)


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
