#!/usr/bin/env python3
"""Importe une journée depuis le portail employé."""

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from chauffeur.preparation import importer_journee_portail  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Importe une journée depuis une session valide du portail employé."
    )
    ap.add_argument(
        "--date", default=date.today().isoformat(), metavar="YYYY-MM-DD",
        help="Date à importer (défaut : aujourd'hui).",
    )
    ap.add_argument("--log", action="store_true", help="Écrit dans parse_journee.log.")
    args = ap.parse_args()

    resultat = importer_journee_portail(args.date, log=args.log)
    if resultat.message:
        print(resultat.message)
    if resultat.session_expiree:
        print("🔒 Session expirée — renouveler les cookies.", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(0 if resultat.succes else 1)


if __name__ == "__main__":
    main()
