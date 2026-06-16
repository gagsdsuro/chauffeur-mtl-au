#!/usr/bin/env python3
"""
test_parse_gd.py — Régression du parseur Gauche-Droite (scripts/parse_gd.py)

Rejoue des collages bruts figés dans tests/cas_gd/*.txt.

Régression couverte (ligne 24 est, juin 2026) : l'export STM répète l'en-tête
« Gauche-Droite / <ligne> <direction> » devant CHAQUE parcours, même quand
plusieurs parcours appartiennent à la même ligne/direction (ex. Parcours
principal + Parcours secondaire collés l'un après l'autre). split_sections()
découpait alors en 2 sections distinctes qui s'écrasaient l'une l'autre →
1 seul parcours retenu au lieu de 2. Le correctif fusionne les sections d'un
même couple (ligne, direction), en retirant l'en-tête répété des sections
suivantes (sinon il se fait mal interpréter comme une instruction G-D, ex.
« Gauche-Droite / 24 Est » matche le pattern « Gauche - <rue> »).

Usage : python3 tests/test_parse_gd.py   (code de sortie 0 si tout passe)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from parse_gd import GDParser, split_sections  # noqa: E402


def main() -> int:
    echecs = []
    txt = (ROOT / "tests" / "cas_gd" / "24_est_multi_parcours.txt").read_text(encoding="utf-8")
    sections = split_sections(txt)

    if len(sections) != 1:
        echecs.append(f"24 est: {len(sections)} section(s) après fusion, attendu 1")
    else:
        # GDParser.parse() écrit dans data/Gauche-Droite/ (effet de bord réel) —
        # on appelle directement les étapes de parsing pour rester hermétique.
        parser = GDParser(sections[0])
        ok = parser._extract_header() and parser._parse_parcours()
        json_data = parser._generate_json() if ok else None
        if json_data is None:
            echecs.append(f"24 est: parsing échoué — {parser.errors}")
        else:
            parcours = json_data["routes"][0]["parcours"]
            if len(parcours) != 2:
                echecs.append(f"24 est: {len(parcours)} parcours, attendu 2")
            else:
                principal, secondaire = parcours[0], parcours[1]
                if principal["name"] != "Parcours principal":
                    echecs.append(f"parcours[0]: nom={principal['name']!r}, attendu 'Parcours principal'")
                if any("Gauche-Droite" in d or "Imprimer" in d for d in principal["direction"]):
                    echecs.append(f"parcours principal: en-tête répété mal capté: {principal['direction']}")
                if secondaire["name"] != "Parcours secondaire":
                    echecs.append(f"parcours[1]: nom={secondaire['name']!r}, attendu 'Parcours secondaire'")
                if secondaire["start"] != "Station Sherbrooke (Édicule Est )":
                    echecs.append(f"parcours secondaire: start={secondaire['start']!r}")
                if len(secondaire["direction"]) != 6:
                    echecs.append(f"parcours secondaire: {len(secondaire['direction'])} directions, attendu 6")

    if echecs:
        print("✗ test_parse_gd")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1
    print("✓ cas-24-est-multi-parcours (2 parcours fusionnés, en-tête répété sans pollution)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
