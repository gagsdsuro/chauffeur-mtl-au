#!/usr/bin/env python3
"""
test_reference.py — Tests unitaires chauffeur.reference

Couvre le choix du fichier points_de_releve_<année>.json selon la date de la
journée (année exacte, repli sur la dernière année antérieure, aucun fichier
applicable), la lecture d'un lieu (exact, préfixe de quai, garage inconnu) et
les fichiers réels 2026 et 2027.

Usage : python3 tests/test_reference.py   (code de sortie 0 si tout passe)
"""
import json
import sys
import shutil
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.reference import fichier_points_releve, lieu_point_releve  # noqa: E402


def _ecrire(dossier: Path, annee: int, lieu: str) -> None:
    (dossier / f"points_de_releve_{annee}.json").write_text(
        json.dumps({"garages": {"Frontenac": [
            {"ligne": "172", "code": "V070", "lieu": lieu}]}}), encoding="utf-8")


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        check(fichier_points_releve(date(2026, 6, 1), d) is None,
              "dossier vide : None attendu")
        _ecrire(d, 2026, "Lieu 2026")
        _ecrire(d, 2027, "Lieu 2027")
        (d / "points_de_releve.json").write_text("{}", encoding="utf-8")  # ancien nom, ignoré

        def nom(j):
            p = fichier_points_releve(j, d)
            return p.name if p else None

        check(nom(date(2026, 12, 31)) == "points_de_releve_2026.json", "31 déc. 2026 → 2026")
        check(nom(date(2027, 1, 1)) == "points_de_releve_2027.json", "1er janv. 2027 → 2027")
        check(nom("2027-03-15") == "points_de_releve_2027.json", "chaîne ISO acceptée")
        check(nom(date(2028, 5, 1)) == "points_de_releve_2027.json",
              "2028 sans fichier → repli sur 2027")
        check(nom(date(2025, 5, 1)) is None, "avant le premier fichier → None")

        p26 = fichier_points_releve(date(2026, 8, 1), d)
        p27 = fichier_points_releve(date(2027, 8, 1), d)
        check(lieu_point_releve("V070", "Frontenac", path=p26) == "Lieu 2026", "lieu exact 2026")
        check(lieu_point_releve("V07002", "Frontenac", path=p27) == "Lieu 2027",
              "suffixe de quai → préfixe de référence 2027")
        check(lieu_point_releve("V070", "Anjou", path=p27) is None, "garage inconnu → None")
        check(lieu_point_releve("", "Frontenac", path=p27) is None, "code vide → None")

        # Fichier modifié sur disque : relu au prochain appel
        _ecrire(d, 2027, "Lieu 2027 modifié")
        check(lieu_point_releve("V070", "Frontenac", path=p27) == "Lieu 2027 modifié",
              "fichier modifié doit être relu")

    # Gabarit fictif versionné (les fichiers réels ne le sont pas)
    gabarit = Path(__file__).resolve().parent.parent / "docs" / "gabarits" / "reference" / "points_de_releve_AAAA.json"
    with tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / "points_de_releve_2026.json"
        shutil.copy(gabarit, copie)
        check(lieu_point_releve("M001", "Garage A", path=copie) == "Station Exemple 1",
              "gabarit : code exact")
        check(lieu_point_releve("M00101", "Garage A", path=copie) == "Station Exemple 1",
              "gabarit : suffixe de quai → préfixe M001")
        check(lieu_point_releve("M002", "Garage A", path=copie) is None,
              "gabarit : portée limitée au garage")

    for e in echecs:
        print(f"❌ {e}")
    if not echecs:
        print("✅ test_reference : tous les tests passent")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
