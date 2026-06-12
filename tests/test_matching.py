#!/usr/bin/env python3
"""
test_matching.py — Tests unitaires de chauffeur.matching

Couvre les cas réels d'appariement carte agent ↔ G-D rencontrés en production :
station vs rue (parenthèses), préfixe REM, troncature de mise en page, abréviations.

Usage : python3 tests/test_matching.py   (code de sortie 0 si tout passe)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chauffeur.matching import stop_tokens, stops_match, normalize_street  # noqa: E402

# (a, b, attendu)
CAS_MATCH = [
    # Station nommée vs rue entre parenthèses (le cœur des bugs juin 2026)
    ("Station McGill (De Maisonneuve / Robert-Bourassa)",
     "DE MAISONNEUVE / ROBERT-BOURASSA", True),
    ("Station McGill (R.-Bourassa / Président-Kennedy)",
     "ROBERT-BOURASSA / PRÉS.-KENNEDY", True),       # BOURASSA + PRES→PRESIDENT
    # Préfixe REM ignoré
    ("STATION REM ÎLE-DES-SOEURS", "Station Île-des-Soeurs", True),
    ("POINTE-SUD SUD", "de la Pointe-Sud / No 250", True),
    # Troncature de mise en page du PDF
    ("STATION VIAU(P.-DE-COUBERTIN O./TH", "Station Viau / P.-De Coubertin Est", True),
    # Pas de jeton distinctif commun → non
    ("Station Angrignon", "Terminus Dorval", False),
    ("Côte-Vertu", "Honoré-Beaugrand", False),
]


def main() -> int:
    echecs = 0

    for a, b, attendu in CAS_MATCH:
        obtenu = stops_match(a, b)
        if obtenu != attendu:
            echecs += 1
            print(f"✗ stops_match({a!r}, {b!r}) = {obtenu}, attendu {attendu}")

    # stop_tokens : retire bruit, accents, chiffres ; garde le distinctif
    toks = stop_tokens("Station Île-des-Soeurs (No 250)")
    for attendu_tok in ("ILE", "SOEURS"):
        if attendu_tok not in toks:
            echecs += 1
            print(f"✗ stop_tokens manque {attendu_tok!r} : {toks}")
    for absent in ("STATION", "DES", "250"):
        if absent in toks:
            echecs += 1
            print(f"✗ stop_tokens ne devrait pas contenir {absent!r} : {toks}")

    # normalize_street : minuscule, sans accents ni tirets
    cas_rue = [("Robert-Bourassa", "robert bourassa"),
               ("Saint-André", "saint andre"),
               ("de l'Église", "de l'eglise")]
    for brut, attendu in cas_rue:
        obtenu = normalize_street(brut)
        if obtenu != attendu:
            echecs += 1
            print(f"✗ normalize_street({brut!r}) = {obtenu!r}, attendu {attendu!r}")

    total = len(CAS_MATCH) + 5 + len(cas_rue)
    print(f"\n{total - echecs}/{total} assertions réussies")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
