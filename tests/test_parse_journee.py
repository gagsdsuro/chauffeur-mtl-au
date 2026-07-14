#!/usr/bin/env python3
"""
test_parse_journee.py — Régression du parseur de journée (scripts/parse_journee.py)

Rejoue des collages bruts figés dans tests/cas_journee/*.txt.

Régression couverte (juillet 2026) : le format STM du texte « Sommaire…Horaire »
a changé pour les pièces sans bus assigné. L'ancien format compressait
l'absence de bus ET d'emplacement en un seul « -- » littéral
(ex. « Sommaire24 - 02--4:12Horaire »). Le nouveau format affiche deux
placeholders distincts « -- » (bus) + « -- » (emplacement)
(ex. « Sommaire769 - 01----7:02Horaire »). La regex ne reconnaissait que
l'ancien format à un seul « -- » → aucun sommaire trouvé, échec total du parsing.

Usage : python3 tests/test_parse_journee.py   (code de sortie 0 si tout passe)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from chauffeur.depots import charger_journee  # noqa: E402
from parse_journee import JourneeParser  # noqa: E402


def main() -> int:
    echecs = []
    txt = (ROOT / "tests" / "cas_journee" / "769-sans-bus-double-tiret.txt").read_text(encoding="utf-8")
    parser = JourneeParser(txt, date_str="2026-07-10")
    journee = parser.parse()

    if journee is None:
        echecs.append(f"parsing échoué — {parser.errors}")
    else:
        if len(journee.pieces) != 1:
            echecs.append(f"{len(journee.pieces)} pièce(s), attendu 1")
        else:
            p = journee.pieces[0]
            if p.id != "769-01":
                echecs.append(f"id={p.id!r}, attendu '769-01'")
            if p.numero_autobus is not None:
                echecs.append(f"numero_autobus={p.numero_autobus!r}, attendu None (bus non assigné)")
            if p.duree != "7:02":
                echecs.append(f"duree={p.duree!r}, attendu '7:02'")
            if p.debut != "17:30" or p.fin != "24:32":
                echecs.append(f"debut/fin={p.debut!r}/{p.fin!r}, attendu '17:30'/'24:32'")

        if journee.garage_id != "59200":
            echecs.append(f"garage_id={journee.garage_id!r}, attendu '59200'")

        # save() délègue à chauffeur.depots.sauvegarder_journee : vérifie que
        # le fichier écrit reste relisible et au bon format (répertoire
        # temporaire, hermétique).
        with tempfile.TemporaryDirectory() as tmp:
            original_dir = JourneeParser.JOURNEES_DIR
            JourneeParser.JOURNEES_DIR = Path(tmp)
            try:
                out = parser.save(journee)
            finally:
                JourneeParser.JOURNEES_DIR = original_dir

            contenu = out.read_text(encoding="utf-8")
            if not contenu.endswith("\n") or contenu.endswith("\n\n"):
                echecs.append("save(): un seul saut de ligne final attendu")
            relu = charger_journee(out)
            if relu.get("garage_id") != "59200":
                echecs.append(f"save()+charger_journee: garage_id={relu.get('garage_id')!r}")

    if echecs:
        print("✗ test_parse_journee")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1
    print("✓ cas-769-sans-bus-double-tiret (sommaire avec placeholders '--'+'--' reconnu)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
