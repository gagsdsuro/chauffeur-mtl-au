#!/usr/bin/env python3
"""
creer_cas_rapport.py — Fige un cas de test de régression pour gen_rapport.py

Capture, dans tests/cas_rapport/<nom>/ :
  • carte.pdf      copie du PDF source
  • gd/            copie des fichiers Gauche-Droite des lignes détectées
  • events/        copie des fichiers d'évènements des lignes détectées
  • attendu.json   projection de build_rapport_data (méta, directions, évènements, HLP)

Le snapshot capturé devient la référence : VÉRIFIER MANUELLEMENT attendu.json
avant de committer le cas (s'assurer que chaque pièce de travail / ligne est
présente avec ses bonnes directions). Ensuite test_rapport.py rejoue le cas de
façon hermétique, sans dépendre des données live de data/Gauche-Droite/.

Usage :
    python3 tests/creer_cas_rapport.py --pdf data/ca/carte-agent-2026-06-11.pdf \
        [--nom carte-455-2026-06-11]
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
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--nom", help="nom du cas (défaut : carte-<numéro>-<date du nom de fichier>)")
    args = ap.parse_args()

    src = Path(args.pdf).expanduser()
    if not src.is_file():
        sys.exit(f"PDF introuvable : {src}")

    # Lignes détectées (depuis les données live) pour savoir quels G-D copier.
    carte = gr.parse_carte_agent(src)
    if not carte["lignes"]:
        sys.exit("Aucune ligne détectée dans la carte agent.")

    import re
    m = re.search(r"\d{4}-\d{2}-\d{2}", src.name)
    suffixe = f"-{m.group(0)}" if m else ""
    nom = args.nom or f"carte-{carte['assignation']}{suffixe}"
    dossier = ROOT / "tests" / "cas_rapport" / nom
    (dossier / "gd").mkdir(parents=True, exist_ok=True)

    shutil.copy2(src, dossier / "carte.pdf")

    copies = []
    for numero in carte["lignes"]:
        for gd_file in sorted(gr.GD_DIR.glob(f"gd{numero}_*.json")):
            shutil.copy2(gd_file, dossier / "gd" / gd_file.name)
            copies.append(gd_file.name)
    if not copies:
        print("⚠️  Aucun fichier G-D trouvé pour les lignes détectées — "
              "directions vides dans attendu.json.")

    # Gèle aussi les évènements des lignes détectées (depuis les données live),
    # pour que le snapshot d'applicabilité soit hermétique.
    (dossier / "events").mkdir(parents=True, exist_ok=True)
    ev_copies = []
    for numero in carte["lignes"]:
        for ev_file in sorted(gr.EVENTS_DIR.glob(f"{numero}_*.json")):
            shutil.copy2(ev_file, dossier / "events" / ev_file.name)
            ev_copies.append(ev_file.name)

    snapshot = calculer_snapshot(dossier)   # pointe GD_DIR sur le gd/ gelé
    (dossier / "attendu.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Cas de test créé : {dossier.relative_to(ROOT)}")
    print(f"  G-D copiés    : {', '.join(copies) or '(aucun)'}")
    print(f"  Events copiés : {', '.join(ev_copies) or '(aucun)'}")
    print(f"  Lignes        : {', '.join(snapshot['lignes'])}")
    print("VÉRIFIER attendu.json avant de committer — il fige le comportement actuel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
