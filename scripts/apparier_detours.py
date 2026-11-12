#!/usr/bin/env python3
"""
apparier_detours.py — État et synchronisation des appariements de détours
(data/Appariements/detours/).

Usage :
  python3 scripts/apparier_detours.py                              # état
  python3 scripts/apparier_detours.py --sync                       # revérifie tous les détours
  python3 scripts/apparier_detours.py --sync --ligne 445 --sens est --log

Un détour que le pipeline G-D ne sait pas ancrer seul (début ou retour introuvable,
arrêts ajoutés sur une même étape…) est « incertain » ; un choix validé devenu
inapplicable est « à revalider ». Les choix validés ne sont jamais écrasés.
Code de sortie : 0, ou 1 s'il reste un détour à réviser.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.registre_detours import (  # noqa: E402
    ETAT_A_REVISER, lister_detours, synchroniser_evenements_ligne, synchroniser_tout_detours,
)

_ICONES = {"auto": "✅", "valide": "✔️", "incertain": "⚠", "a_revalider": "🔁"}


def afficher_etat() -> int:
    a_reviser = 0
    fichiers = lister_detours()
    if not fichiers:
        print("Aucun détour enregistré — rien à réviser.")
        return 0
    for (ligne, direction), contenu in fichiers.items():
        for signature, e in contenu.get("detours", {}).items():
            statut = e.get("statut", "?")
            a_reviser += statut in ETAT_A_REVISER
            evt = ", ".join(e.get("evenement_ids", [])[:3])
            detail = f" — par {e.get('valide_par')} le {e.get('valide_le')}" if statut == "valide" \
                else (" — " + " ; ".join(e.get("diagnostics", [])[:1]) if e.get("diagnostics") else "")
            print(f"{_ICONES.get(statut, '?')} {ligne} {direction} {signature} "
                  f"(évènement {evt}) : {statut}{detail}")
    return 1 if a_reviser else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--sync", action="store_true", help="Revérifie les détours non expirés.")
    ap.add_argument("--ligne")
    ap.add_argument("--sens", help="Requis avec --ligne : est, ouest, nord ou sud.")
    ap.add_argument("--log", action="store_true", help="Trace dans data/log/appariement.log.")
    args = ap.parse_args()

    if args.sync:
        if args.ligne:
            if not args.sens:
                ap.error("--sens est requis avec --ligne")
            messages = synchroniser_evenements_ligne(args.ligne, args.sens.lower(), log=args.log)
        else:
            messages = synchroniser_tout_detours(log=args.log)
        for message in messages:
            print(message)
        if not messages:
            print("Détours déjà à jour.")
        print()
    return afficher_etat()


if __name__ == "__main__":
    sys.exit(main())
