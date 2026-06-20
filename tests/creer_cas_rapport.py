#!/usr/bin/env python3
"""
creer_cas_rapport.py — Fige un cas de test de régression pour gen_rapport.py

Capture, dans tests/cas_rapport/<nom>/ :
  • journee.json  copie du fichier journée JSON source
  • gd/           copie des fichiers Gauche-Droite des lignes détectées
  • events/       copie des fichiers d'évènements des lignes détectées
  • attendu.json  projection de build_rapport_data (méta, directions, évènements, HLP)

Le snapshot capturé devient la référence : VÉRIFIER MANUELLEMENT attendu.json
avant de committer le cas (s'assurer que chaque pièce de travail / ligne est
présente avec ses bonnes directions). Ensuite test_rapport.py rejoue le cas de
façon hermétique, sans dépendre des données live de data/Gauche-Droite/.

Usage :
    python3 tests/creer_cas_rapport.py --journee data/journees/journee-2026-06-11.json \
        [--nom journee-2026-06-11]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import gen_rapport as gr        # noqa: E402
from test_rapport import calculer_snapshot  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--journee", required=True,
                    help="Chemin vers journee-YYYY-MM-DD.json")
    ap.add_argument("--nom",
                    help="Nom du cas (défaut : journee-YYYY-MM-DD)")
    args = ap.parse_args()

    src = Path(args.journee).expanduser()
    if not src.is_file():
        sys.exit(f"Journée introuvable : {src}")

    journee = json.loads(src.read_text(encoding="utf-8"))
    groupes = gr.extract_groupes(journee)
    if not groupes:
        sys.exit("Aucun trajet de service dans la journée.")

    date_str = journee.get("date", "")
    nom = args.nom or f"journee-{date_str}"
    dossier = ROOT / "tests" / "cas_rapport" / nom
    (dossier / "gd").mkdir(parents=True, exist_ok=True)
    (dossier / "events").mkdir(parents=True, exist_ok=True)

    shutil.copy2(src, dossier / "journee.json")

    lignes = sorted({g["ligne"] for g in groupes})

    copies_gd = []
    for numero in lignes:
        for gd_file in sorted(gr.GD_DIR.glob(f"gd{numero}_*.json")):
            shutil.copy2(gd_file, dossier / "gd" / gd_file.name)
            copies_gd.append(gd_file.name)
    if not copies_gd:
        print("⚠️  Aucun fichier G-D trouvé pour les lignes détectées — "
              "directions vides dans attendu.json.")

    copies_ev = []
    for numero in lignes:
        for ev_file in sorted(gr.EVENTS_DIR.glob(f"{numero}_*.json")):
            shutil.copy2(ev_file, dossier / "events" / ev_file.name)
            copies_ev.append(ev_file.name)

    snapshot = calculer_snapshot(dossier)   # pointe GD_DIR / EVENTS_DIR sur les gelés
    (dossier / "attendu.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Cas de test créé : {dossier.relative_to(ROOT)}")
    print(f"  G-D copiés    : {', '.join(copies_gd) or '(aucun)'}")
    print(f"  Events copiés : {', '.join(copies_ev) or '(aucun)'}")
    print(f"  Lignes        : {', '.join(snapshot['lignes'])}")
    print("VÉRIFIER attendu.json avant de committer — il fige le comportement actuel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
