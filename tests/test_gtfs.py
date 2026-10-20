#!/usr/bin/env python3
"""
test_gtfs.py — Tests unitaires de chauffeur.gtfs (cache de stops_index.json)

Régression du 19 octobre 2026 : le GTFS a été mis à jour par un autre
processus (fetch_gtfs.py) pendant que l'app tournait ; le cache mémoire de
l'index, jamais invalidé, servait encore l'ancienne séquence du 24 est
(arrêt 51281 « Décarie / Duquette », retiré) avec les nouveaux noms
d'arrêts — l'arrêt s'affichait vide et a été validé tel quel.

Usage : python3 tests/test_gtfs.py   (code de sortie 0 si tout passe)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chauffeur import gtfs  # noqa: E402


def main() -> int:
    erreurs = []
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        index = d / "stops_index.json"
        index.write_text(json.dumps({"24|1": [[1, "51241"], [2, "51281"]]}), encoding="utf-8")
        avant = gtfs.stops_for_line(d, "24", "1")

        # Mise à jour par un autre processus : contenu et date de modification changent.
        index.write_text(json.dumps({"24|1": [[1, "51241"], [2, "51326"]]}), encoding="utf-8")
        st = index.stat()
        os.utime(index, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        apres = gtfs.stops_for_line(d, "24", "1")

        if avant != [(1, "51241"), (2, "51281")]:
            erreurs.append(f"lecture initiale : {avant}")
        if apres != [(1, "51241"), (2, "51326")]:
            erreurs.append(f"index modifié sur disque non rechargé : {apres}")

        index.unlink()
        if gtfs._load_index(d) is not None:
            erreurs.append("index supprimé : le cache ne doit plus être servi")

    print(("✅" if not erreurs else "❌") + " cache stops_index.json invalidé par date de modification")
    for e in erreurs:
        print("   ", e)
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
