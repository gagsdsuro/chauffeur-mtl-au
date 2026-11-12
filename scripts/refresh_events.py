#!/usr/bin/env python3
"""Rafraîchit les événements du portail depuis le portail employé.

Cas d'usage :
    refresh_events.py --ligne 10 --sens sud
    refresh_events.py --journee data/journees/journee-2026-06-25.json
    refresh_events.py --journee data/journees/journee-2026-06-25.json --restantes

Codes de sortie :
    0  succès
    1  erreur parse ou HTTP non-session
    2  session expirée ou absente (renouveler les cookies)
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from chauffeur.depots import charger_journee
from chauffeur.preparation import rafraichir_evenements_journee


def main():
    ap = argparse.ArgumentParser(
        description="Rafraîchit les événements du portail depuis le portail employé."
    )
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--journee", type=Path, metavar="FICHIER",
                       help="Fichier journée JSON — rafraîchit toutes les lignes de service.")
    group.add_argument("--ligne", metavar="LIGNE",
                       help="Numéro de ligne unique (ex. 10, 125). Requiert --sens.")
    ap.add_argument("--sens", metavar="DIRECTION",
                    help="Direction en minuscule : est | ouest | nord | sud. Requis avec --ligne.")
    ap.add_argument("--restantes", action="store_true",
                    help="Avec --journee : saute les pièces déjà terminées.")
    ap.add_argument("--log", action="store_true",
                    help="Sauvegarde la sortie dans data/log/parse_event.log (append).")
    args = ap.parse_args()

    if args.ligne:
        if not args.sens:
            ap.error("--sens est requis avec --ligne")
        journee_data = {"pieces": [{"trajets": [{
            "type": "service", "ligne": args.ligne, "direction": args.sens,
        }]}]}
        pairs = [(args.ligne, args.sens.lower())]
    else:
        if not args.journee.exists():
            print(f"❌ Fichier journée introuvable : {args.journee}", file=sys.stderr)
            sys.exit(1)
        journee_data = charger_journee(args.journee)
        pairs = None

    resultat = rafraichir_evenements_journee(
        journee_data,
        restantes_seulement=args.restantes,
        paires=pairs,
        log=args.log,
    )
    for ligne in resultat.lignes:
        print(f"⟳  {ligne.ligne} {ligne.direction}")
        print(ligne.message)
    if resultat.session_expiree:
        print("🔒 Session expirée — renouveler les cookies.", file=sys.stderr)
        sys.exit(2)
    if resultat.restantes:
        print("❌ Rafraîchissement interrompu avant toutes les lignes.", file=sys.stderr)
        sys.exit(1)
    if not resultat.lignes:
        print("Aucune ligne à rafraîchir.")
    sys.exit(0 if resultat.succes_complet else 1)


if __name__ == "__main__":
    main()
