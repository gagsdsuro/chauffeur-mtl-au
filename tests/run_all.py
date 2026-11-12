#!/usr/bin/env python3
"""
run_all.py — Lance toute la suite de tests d'un coup (à exécuter avant déploiement).

Découvre et exécute chaque tests/test_*.py en sous-processus, agrège les
résultats. Code de sortie 0 si tout passe, 1 si au moins un échoue.

Usage : python3 tests/run_all.py
"""
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def main() -> int:
    suites = sorted(TESTS_DIR.glob("test_*.py"))
    echecs = []
    for suite in suites:
        print(f"\n━━━ {suite.name} " + "━" * (50 - len(suite.name)))
        r = subprocess.run([sys.executable, str(suite)])
        if r.returncode != 0:
            echecs.append(suite.name)

    print("\n" + "═" * 60)
    if echecs:
        print(f"❌ {len(echecs)}/{len(suites)} suite(s) en échec : {', '.join(echecs)}")
        return 1
    print(f"✅ {len(suites)}/{len(suites)} suites réussies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
