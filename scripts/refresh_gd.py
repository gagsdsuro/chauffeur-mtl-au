#!/usr/bin/env python3
"""Rafraîchit les Gauche-Droite depuis le portail employé."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from chauffeur.depots import charger_journee  # noqa: E402
from chauffeur.preparation import rafraichir_gd_journee  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Rafraîchit les Gauche-Droite depuis une session valide du portail employé."
    )
    groupe = ap.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--journee", type=Path, metavar="FICHIER")
    groupe.add_argument("--ligne", metavar="LIGNE")
    ap.add_argument("--sens", help="Requis avec --ligne : est, ouest, nord ou sud.")
    ap.add_argument(
        "--tous", action="store_true",
        help="Avec --journee, rafraîchit aussi les G-D encore frais.",
    )
    ap.add_argument("--log", action="store_true", help="Écrit dans parse_gd.log.")
    args = ap.parse_args()

    if args.ligne:
        if not args.sens:
            ap.error("--sens est requis avec --ligne")
        journee = {"pieces": []}
        paires = [(args.ligne, args.sens.lower())]
    else:
        if not args.journee.exists():
            print(f"❌ Fichier journée introuvable : {args.journee}", file=sys.stderr)
            raise SystemExit(1)
        journee = charger_journee(args.journee)
        paires = None

    resultat = rafraichir_gd_journee(
        journee,
        paires=paires,
        manquants_ou_perimes_seulement=not args.tous,
        log=args.log,
    )
    for ligne in resultat.lignes:
        etat = "modifié" if ligne.modifie else "vérifié"
        print(f"{'✅' if ligne.succes else '❌'} {ligne.ligne} {ligne.direction} — {etat}")
        if not ligne.succes and ligne.message:
            print(ligne.message)
    if resultat.session_expiree:
        print("🔒 Session expirée — renouveler les cookies.", file=sys.stderr)
        raise SystemExit(2)
    if not resultat.lignes:
        print("Aucun G-D manquant ou périmé.")
    raise SystemExit(0 if resultat.succes_complet else 1)


if __name__ == "__main__":
    main()
