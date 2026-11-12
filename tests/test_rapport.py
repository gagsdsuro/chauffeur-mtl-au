#!/usr/bin/env python3
"""
test_rapport.py — Tests de régression de gen_rapport.py

Rejoue chaque cas figé dans tests/cas_rapport/<nom>/ :
  • journee.json  copie du fichier journée JSON
  • gd/           fichiers Gauche-Droite gelés (gd<ligne>_<direction>.json)
  • events/       fichiers d'évènements gelés (<ligne>_<direction>.json)
  • attendu.json  projection de build_rapport_data (méta, directions, évènements, HLP)

Le cas est hermétique : on redirige gen_rapport.GD_DIR vers le dossier gd/ gelé,
donc le test ne dépend pas des données live de data/Gauche-Droite/.

Couvre les régressions connues :
  • sélection de parcours par id_parcours (pas par appariement de noms)
  • filtrage des évènements par plage de quart (chauffeur.evenements)

Usage :
    python3 tests/test_rapport.py                 # tous les cas
    python3 tests/test_rapport.py journee-2026-06-20   # un cas précis

Code de sortie : 0 si tous les cas passent, 1 sinon.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gen_rapport as gr  # noqa: E402


def calculer_snapshot(dossier: Path) -> dict:
    """Produit la projection de référence d'un cas à partir de build_rapport_data().

    Hermétique : GD_DIR et EVENTS_DIR sont redirigés vers les fichiers gelés du cas.
    La projection couvre tout ce qu'un refactor pourrait altérer au niveau des données
    du rapport : méta, directions G-D, classement applicable/non-applicable des
    évènements, et HLP.
    """
    gr.GD_DIR = dossier / "gd"
    ev_dir = dossier / "events"
    if ev_dir.exists():
        gr.EVENTS_DIR = ev_dir

    journee = json.loads((dossier / "journee.json").read_text(encoding="utf-8"))
    from datetime import date
    target_date = date.fromisoformat(journee["date"])
    data = gr.build_rapport_data(journee, target_date)

    groupes = gr.extract_groupes(journee)
    lignes_uniques = sorted({g["ligne"] for g in groupes})

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
        "garage_id": journee.get("garage_id", ""),
        "lignes": lignes_uniques,
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


def jouer_cas(dossier: Path) -> list | None:
    """Rejoue un cas ; retourne la liste des écarts (vide = succès), ou None si ignoré."""
    if not (dossier / "journee.json").exists():
        return None   # ancien cas PDF — ignoré
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
    joues  = 0
    for nom in noms:
        ecarts = jouer_cas(base / nom)
        if ecarts is None:
            print(f"⏭  {nom}  (ancien cas PDF — non applicable)")
            continue
        joues += 1
        if ecarts:
            echecs += 1
            print(f"✗ {nom}")
            for e in ecarts:
                print(f"    {e}")
        else:
            print(f"✓ {nom}")

    if joues == 0:
        print("Aucun cas journée JSON — créer avec creer_cas_rapport.py --journee ...")
        return 1

    print(f"\n{joues - echecs}/{joues} cas réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
