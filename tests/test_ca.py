#!/usr/bin/env python3
"""
test_ca.py — Tests unitaires chauffeur.ca

Couvre resoudre_ca (résolution par identité, repli legacy par date, numero
absent) et ranger_ca (rangement normal, collision refusée, remplacement avec
.bak, mode « déjà annotée ») dans un ca_dir temporaire. L'identité s'appuie
sur le calendrier réel 2026 (même précédent que tests/test_periodes.py).

Usage : python3 tests/test_ca.py   (code de sortie 0 si tout passe)
"""
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.ca import ranger_ca, resoudre_ca  # noqa: E402
from chauffeur.periodes import identite_ca, nom_ca  # noqa: E402

JOUR   = date(2026, 1, 6)   # mardi d'une semaine de liste (calendrier 2026)
NUMERO = "461"


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    ident = identite_ca(JOUR, NUMERO)   # (numero, groupe_id, jour_type)
    n, g, j = ident

    # ── resoudre_ca ───────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp)

        # Aucun fichier → identité calculée mais aucun PDF résolu
        r = resoudre_ca(JOUR, NUMERO, ca_dir=rep)
        check(r["identite"] == ident, f"resoudre: identite attendue {ident}, obtenu {r['identite']}")
        check(r["brute"] is None and r["annotee"] is None and not r["legacy"],
              "resoudre: sans fichier, brute/annotee=None et legacy=False attendus")

        # Fichiers par identité → résolus, legacy=False
        (rep / nom_ca(n, g, j)).write_bytes(b"brute")
        (rep / nom_ca(n, g, j, annotee=True)).write_bytes(b"annotee")
        r = resoudre_ca(JOUR, NUMERO, ca_dir=rep)
        check(r["brute"] is not None and r["annotee"] is not None and not r["legacy"],
              "resoudre: fichiers par identité non résolus")

        # numero=None → identité None, mais repli legacy par date fonctionne
        (rep / f"carte-agent-{JOUR}-annotee.pdf").write_bytes(b"legacy-annotee")
        (rep / f"carte-agent-{JOUR}.pdf").write_bytes(b"legacy-brute")
        r = resoudre_ca(JOUR, None, ca_dir=rep)
        check(r["identite"] is None, "resoudre: numero=None devrait donner identite=None")
        check(r["legacy"] and r["annotee"] is not None and r["brute"] is not None,
              "resoudre: repli legacy par date attendu quand numero=None")

    # Repli legacy « -surligné » (identité présente mais sans PDF par identité)
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp)
        (rep / f"carte-agent-{JOUR}-surligné.pdf").write_bytes(b"legacy")
        r = resoudre_ca(JOUR, NUMERO, ca_dir=rep)
        check(r["legacy"] and r["annotee"] is not None and r["annotee"].name.endswith("-surligné.pdf"),
              "resoudre: repli legacy -surligné attendu")

    # ── ranger_ca ─────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp)

        # Rangement normal : brute + annotée déplacées, tmp disparus
        t_brute   = rep / "_tmp_brute.pdf";   t_brute.write_bytes(b"b1")
        t_annotee = rep / "_tmp_annotee.pdf"; t_annotee.write_bytes(b"a1")
        dest = ranger_ca(n, g, j, annotee_tmp=t_annotee, brute_tmp=t_brute, ca_dir=rep)
        check(dest["annotee"].name == nom_ca(n, g, j, annotee=True)
              and dest["brute"].name == nom_ca(n, g, j),
              f"ranger: destinations inattendues : {dest}")
        check(dest["annotee"].read_bytes() == b"a1" and dest["brute"].read_bytes() == b"b1",
              "ranger: contenus déplacés inattendus")
        check(not t_brute.exists() and not t_annotee.exists(),
              "ranger: les fichiers temporaires devraient avoir été déplacés")

        # Collision sans remplacer → FileExistsError, destinations intactes
        t2 = rep / "_tmp2.pdf"; t2.write_bytes(b"a2")
        try:
            ranger_ca(n, g, j, annotee_tmp=t2, ca_dir=rep)
            echecs.append("ranger: collision sans remplacer aurait dû lever FileExistsError")
        except FileExistsError:
            pass
        check(dest["annotee"].read_bytes() == b"a1",
              "ranger: la destination ne devrait pas changer sur collision refusée")
        check(t2.exists(), "ranger: le tmp devrait rester au caller sur collision refusée")

        # Mode « déjà annotée » + remplacer : .bak de l'annotée, brute intacte
        dest2 = ranger_ca(n, g, j, annotee_tmp=t2, remplacer=True, ca_dir=rep)
        check(dest2["brute"] is None, "ranger: mode déjà-annotée devrait retourner brute=None")
        check(dest2["annotee"].read_bytes() == b"a2",
              "ranger: la nouvelle version annotée devrait être en place")
        bak = dest2["annotee"].with_name(dest2["annotee"].name + ".bak")
        check(bak.exists() and bak.read_bytes() == b"a1",
              "ranger: l'ancienne annotée devrait être sauvegardée en .bak")
        check(dest["brute"].read_bytes() == b"b1",
              "ranger: la brute existante ne devrait pas être touchée en mode déjà-annotée")

        # Remplacement complet : .bak des deux destinations
        t3b = rep / "_tmp3b.pdf"; t3b.write_bytes(b"b3")
        t3a = rep / "_tmp3a.pdf"; t3a.write_bytes(b"a3")
        dest3 = ranger_ca(n, g, j, annotee_tmp=t3a, brute_tmp=t3b, remplacer=True, ca_dir=rep)
        bak_b = dest3["brute"].with_name(dest3["brute"].name + ".bak")
        check(dest3["brute"].read_bytes() == b"b3" and bak_b.read_bytes() == b"b1",
              "ranger: remplacement complet — brute remplacée avec .bak attendu")
        check(dest3["annotee"].read_bytes() == b"a3",
              "ranger: remplacement complet — annotée remplacée attendue")

    # ── Résultat ──────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_ca")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ resoudre_ca (identité, legacy, numero=None) + ranger_ca (collision, .bak, déjà-annotée)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
