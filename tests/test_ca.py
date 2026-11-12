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

import json  # noqa: E402
import chauffeur.ca as ca_mod  # noqa: E402
from chauffeur.ca import annoter_et_ranger_ca, ranger_ca, resoudre_ca  # noqa: E402
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


    # ── annoter_et_ranger_ca (sous-processus factice, journal neutralisé) ────
    class Sortie:
        def __init__(self, code=0, out="", err=""):
            self.returncode, self.stdout, self.stderr = code, out, err

    def faux_traitement(carte="461", code=0, err=""):
        appels = []

        def executer(cmd, **kwargs):
            appels.append(cmd)
            if code != 0:
                return Sortie(code, "", err)
            if "--out" in cmd:
                Path(cmd[cmd.index("--out") + 1]).write_bytes(b"annotee")
            return Sortie(0, "[INFO]\n" + json.dumps({"carte": carte, "lignes": []}))

        executer.appels = appels
        return executer

    journal = []
    original_bloc = ca_mod.ecrire_bloc
    ca_mod.ecrire_bloc = lambda source, texte: journal.append((source, texte))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rep = Path(tmp)
            gtfs = rep / "gtfs_absent"

            ex = faux_traitement()
            res = annoter_et_ranger_ca(b"%PDF-brut", JOUR, nom_source="carte.pdf",
                                       journee_numero=461, ca_dir=rep, gtfs_dir=gtfs, executer=ex)
            check(res.succes and res.numero == NUMERO, f"annoter: succès attendu, obtenu {res}")
            check(res.chemin_annotee == rep / nom_ca(n, g, j, annotee=True)
                  and res.chemin_annotee.read_bytes() == b"annotee",
                  "annoter: annotée rangée sous l'identité attendue")
            check((rep / nom_ca(n, g, j)).read_bytes() == b"%PDF-brut", "annoter: brute rangée")
            check(not list(rep.glob("_tmp_*")), "annoter: fichiers _tmp_* à nettoyer")
            check("--gtfs" not in ex.appels[0] and "--no-gtfs" not in ex.appels[0],
                  "annoter: ni --gtfs ni --no-gtfs quand le GTFS est absent et non refusé")
            check(any(src == "carte_agent" and "✅" in txt for src, txt in journal),
                  "annoter: trace de succès attendue dans le journal carte_agent")

            # Identité déjà présente → « existe », rien d'écrasé, tmp nettoyés
            res = annoter_et_ranger_ca(b"autre", JOUR, ca_dir=rep, gtfs_dir=gtfs,
                                       executer=faux_traitement())
            check(res.statut == "existe", f"annoter: statut « existe » attendu, obtenu {res.statut}")
            check((rep / nom_ca(n, g, j)).read_bytes() == b"%PDF-brut",
                  "annoter: la brute existante ne doit pas être écrasée")
            check(not list(rep.glob("_tmp_*")), "annoter: tmp nettoyés après « existe »")

            # …sauf remplacement explicite
            res = annoter_et_ranger_ca(b"autre", JOUR, ca_dir=rep, gtfs_dir=gtfs,
                                       remplacer=True, executer=faux_traitement())
            check(res.succes and (rep / nom_ca(n, g, j)).read_bytes() == b"autre",
                  "annoter: remplacement explicite attendu")

        with tempfile.TemporaryDirectory() as tmp:
            rep = Path(tmp)
            gtfs = rep / "gtfs"
            gtfs.mkdir()

            ex = faux_traitement()
            annoter_et_ranger_ca(b"x", JOUR, ca_dir=rep, gtfs_dir=gtfs, executer=ex)
            check("--gtfs" in ex.appels[0], "annoter: --gtfs attendu quand le dossier existe")
            ex = faux_traitement()
            annoter_et_ranger_ca(b"x", JOUR, ca_dir=rep / "autre", gtfs_dir=gtfs,
                                 avec_gtfs=False, executer=ex)
            check("--no-gtfs" in ex.appels[0] and "--gtfs" not in ex.appels[0],
                  "annoter: --no-gtfs attendu quand avec_gtfs=False")

            # Échec du sous-processus
            res = annoter_et_ranger_ca(b"x", JOUR, ca_dir=rep / "e1", gtfs_dir=gtfs,
                                       executer=faux_traitement(code=1, err="boum"))
            check(res.statut == "erreur" and "boum" in res.detail,
                  f"annoter: échec du traitement mal rapporté : {res}")
            check(not list((rep / "e1").glob("_tmp_*")), "annoter: tmp nettoyés après échec")

            # Numéro illisible, numéro différent de la journée, sortie illisible
            res = annoter_et_ranger_ca(b"x", JOUR, ca_dir=rep / "e2", gtfs_dir=gtfs,
                                       executer=faux_traitement(carte="?"))
            check(res.statut == "erreur" and not list((rep / "e2").glob("[0-9]*")),
                  "annoter: numéro « ? » doit être refusé sans rangement")
            res = annoter_et_ranger_ca(b"x", JOUR, ca_dir=rep / "e3", gtfs_dir=gtfs,
                                       journee_numero=999, executer=faux_traitement())
            check(res.statut == "erreur" and "999" in res.message
                  and not list((rep / "e3").glob("[0-9]*")),
                  f"annoter: numéro différent de la journée à refuser : {res}")
            res = annoter_et_ranger_ca(
                b"x", JOUR, ca_dir=rep / "e4", gtfs_dir=gtfs,
                executer=lambda cmd, **kw: Sortie(0, "pas du json"),
            )
            check(res.statut == "erreur" and "inattendue" in res.message,
                  "annoter: sortie illisible à signaler")

            # Mode « déjà annotée » : --meta-only, seule l'annotée est rangée
            ex = faux_traitement()
            res = annoter_et_ranger_ca(b"deja", JOUR, ca_dir=rep / "e5", gtfs_dir=gtfs,
                                       deja_annotee=True, executer=ex)
            check(res.succes and "--meta-only" in ex.appels[0] and res.chemin_brute is None,
                  f"annoter: mode déjà annotée inattendu : {res}")
    finally:
        ca_mod.ecrire_bloc = original_bloc

    # ── Résultat ──────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_ca")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ resoudre_ca (identité, legacy, numero=None) + ranger_ca (collision, .bak, déjà-annotée) + annoter_et_ranger_ca")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
