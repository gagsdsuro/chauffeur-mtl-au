#!/usr/bin/env python3
"""Rafraîchit les événements STM depuis le portail employé.

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
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from chauffeur.portail import fetch_detours, SessionExpiredError, PortailError
from scripts.parse_event import STMEventParser


def _lignes_journee(journee_path: Path, restantes: bool) -> list:
    """Retourne les paires (ligne, direction) uniques à rafraîchir.

    Avec restantes=True, exclut les pièces dont l'heure de fin est dépassée.
    """
    data = json.loads(journee_path.read_text(encoding="utf-8"))
    now_hm = datetime.now().strftime("%H:%M")
    pairs, seen = [], set()

    for piece in data.get("pieces", []):
        if restantes and piece.get("fin", "99:99") <= now_hm:
            continue
        for trajet in piece.get("trajets", []):
            if trajet.get("type") != "service":
                continue
            ligne = trajet.get("ligne")
            direction = trajet.get("direction")
            if not ligne or not direction:
                continue
            key = (ligne, direction)
            if key not in seen:
                seen.add(key)
                pairs.append(key)

    return pairs


def _refresh_one(ligne: str, sens: str, log: bool = False) -> bool:
    """Rafraîchit une ligne/direction. Retourne True si succès.

    Sort avec code 2 si la session est expirée (propager à tout le batch).
    """
    print(f"⟳  {ligne} {sens}...", end=" ", flush=True)
    try:
        raw = fetch_detours(ligne, sens)
    except SessionExpiredError as exc:
        print(f"\n🔒 Session expirée : {exc}", file=sys.stderr)
        sys.exit(2)
    except PortailError as exc:
        print(f"\n❌ Erreur portail ({ligne} {sens}) : {exc}", file=sys.stderr)
        return False

    parser = STMEventParser.from_portal_json(json.dumps(raw), ligne, sens)

    if parser.errors:
        print()
        summary = parser.get_summary()
        print(summary)
        if log:
            parser.append_log(summary)
        return False

    success, _ = parser.save_json()
    print()
    summary = parser.get_summary()
    print(summary)
    if log:
        parser.append_log(summary)
    return success


def main():
    ap = argparse.ArgumentParser(
        description="Rafraîchit les événements STM depuis le portail employé."
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
        ok = _refresh_one(args.ligne, args.sens, log=args.log)
        sys.exit(0 if ok else 1)

    # Mode journée
    if not args.journee.exists():
        print(f"❌ Fichier journée introuvable : {args.journee}", file=sys.stderr)
        sys.exit(1)

    pairs = _lignes_journee(args.journee, args.restantes)
    if not pairs:
        label = "restantes" if args.restantes else "de la journée"
        print(f"Aucune ligne {label} à rafraîchir.")
        sys.exit(0)

    label = "restantes" if args.restantes else "journée"
    print(f"🔄 {len(pairs)} ligne(s) à rafraîchir ({label}) :\n")

    failed = False
    for ligne, sens in pairs:
        if not _refresh_one(ligne, sens, log=args.log):
            failed = True

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
