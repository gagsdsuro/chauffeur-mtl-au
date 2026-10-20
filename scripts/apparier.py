#!/usr/bin/env python3
"""
apparier.py — État et synchronisation des appariements G-D ↔ GTFS (data/Appariements/).

Usage :
  python3 scripts/apparier.py                              # état de tous les appariements
  python3 scripts/apparier.py --sync                       # (re)calcule tout ce qui a changé
  python3 scripts/apparier.py --sync --ligne 811 --sens ouest --log

Le calcul est aussi déclenché automatiquement par parse_gd.py, refresh_gd.py
et fetch_gtfs.py. Un appariement validé n'est jamais écrasé : si sa source
change, il passe « à revalider » avec les choix humains reportés.
Code de sortie : 0, ou 1 si un appariement reste à réviser (incertain/à revalider).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.depots import repertoire_appariements  # noqa: E402
from chauffeur.registre_appariement import synchroniser_ligne, synchroniser_tout  # noqa: E402

_ICONES = {"auto": "✅", "valide": "✔️", "incertain": "⚠", "a_revalider": "🔁"}


def afficher_etat() -> int:
    a_reviser = 0
    fichiers = sorted(repertoire_appariements().glob("*.json"))
    if not fichiers:
        print("Aucun appariement — lancer avec --sync.")
        return 0
    for path in fichiers:
        try:
            c = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"❌ {path.name} illisible")
            a_reviser += 1
            continue
        statut = c.get("statut", "?")
        a_reviser += statut in ("incertain", "a_revalider")
        detail = ""
        if c.get("blocs"):
            detail = f" — {len(c['blocs'])} segment(s) à réviser"
        if statut == "valide":
            detail = f" — par {c.get('valide_par')} le {c.get('valide_le')}"
        print(f"{_ICONES.get(statut, '?')} {c.get('ligne')} {c.get('direction')} "
              f"id {c.get('id_parcours')} : {statut}{detail}")
    return 1 if a_reviser else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--sync", action="store_true", help="Calcule les appariements périmés ou absents.")
    ap.add_argument("--ligne")
    ap.add_argument("--sens", help="Requis avec --ligne : est, ouest, nord ou sud.")
    ap.add_argument("--log", action="store_true", help="Trace dans data/log/appariement.log.")
    args = ap.parse_args()

    if args.sync:
        if args.ligne:
            if not args.sens:
                ap.error("--sens est requis avec --ligne")
            messages = synchroniser_ligne(args.ligne, args.sens.lower(), log=args.log)
        else:
            messages = synchroniser_tout(log=args.log)
        for message in messages:
            print(message)
        if not messages:
            print("Appariements déjà à jour.")
        print()
    return afficher_etat()


if __name__ == "__main__":
    sys.exit(main())
