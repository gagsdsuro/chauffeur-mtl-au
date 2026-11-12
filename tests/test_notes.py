#!/usr/bin/env python3
"""
test_notes.py — Tests unitaires chauffeur.notes + chauffeur.ca.cle_note_carte

Couvre les notes de carte agent et de journée (data/notes/carte_agent.json,
journee.json) : lecture sur fichier absent, écriture {"note","maj"}, coexistence
de clés, suppression si texte vide, préservation des accents ; et la clé de
note carte dérivée d'un résultat de resoudre_ca() (identité ou repli legacy).
Hermétique : écrit dans un répertoire temporaire (le calendrier de référence
versionné est utilisé pour l'identité, sans GTFS).

Usage : python3 tests/test_notes.py   (code de sortie 0 si tout passe)
"""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import chauffeur.notes as notes  # noqa: E402
from chauffeur.ca import cle_note_carte, resoudre_ca  # noqa: E402


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    NOTES_DIR_REEL = notes.NOTES_DIR
    try:
        with tempfile.TemporaryDirectory() as tmp:
            notes.NOTES_DIR = Path(tmp)

            # ── Fichiers absents ─────────────────────────────────────────────
            check(notes.note_journee("2026-06-15") is None,
                  "note_journee: fichier absent → None attendu")
            check(notes.note_carte("443_L2026-06-15_semaine") is None,
                  "note_carte: fichier absent → None attendu")

            # ── Écriture / relecture note journée ────────────────────────────
            notes.sauvegarder_note_journee("2026-06-15",
                                           "Tempête de neige — Ste-Catherine fermée")
            n = notes.note_journee("2026-06-15")
            check(n == {"note": "Tempête de neige — Ste-Catherine fermée",
                        "maj": date.today().isoformat()},
                  f"note_journee: contenu inattendu après écriture : {n}")

            brut = (notes.NOTES_DIR / "journee.json").read_text(encoding="utf-8")
            check("Tempête de neige — Ste-Catherine fermée" in brut,
                  "journee.json: accents devraient être préservés (ensure_ascii=False)")
            check('  "2026-06-15"' in brut,
                  "journee.json: indentation 2 espaces attendue")

            # Coexistence de deux dates
            notes.sauvegarder_note_journee("2026-06-16", "Autre journée")
            check(notes.note_journee("2026-06-15") is not None
                  and notes.note_journee("2026-06-16")["note"] == "Autre journée",
                  "note_journee: les deux dates devraient coexister")

            # Suppression si texte vide
            notes.sauvegarder_note_journee("2026-06-16", "   ")
            check(notes.note_journee("2026-06-16") is None,
                  "note_journee: texte vide devrait retirer l'entrée")
            check(notes.note_journee("2026-06-15") is not None,
                  "note_journee: la note de l'autre date devrait survivre")

            # ── Écriture / relecture note carte agent ────────────────────────
            cle_juin = "443_L2026-06-15_semaine"
            cle_sept = "443_L2026-08-24_semaine"
            notes.sauvegarder_note_carte(
                cle_juin, "Départ de la maison à 16h, repas pour la pause de 90 min")
            c = notes.note_carte(cle_juin)
            check(c == {"note": "Départ de la maison à 16h, repas pour la pause de 90 min",
                        "maj": date.today().isoformat()},
                  f"note_carte: contenu inattendu après écriture : {c}")
            check(notes.note_carte(cle_sept) is None,
                  "note_carte: une autre identité (autre liste) ne doit rien voir")

            notes.sauvegarder_note_carte(cle_sept, "Note liste de septembre")
            check(notes.note_carte(cle_juin) is not None,
                  "note_carte: la note juin devrait survivre à l'écriture septembre")
            notes.sauvegarder_note_carte(cle_sept, "")
            check(notes.note_carte(cle_sept) is None,
                  "note_carte: texte vide devrait retirer l'entrée")

            # ── cle_note_carte : identité puis replis legacy ─────────────────
            check(cle_note_carte({"identite": ("443", "L2026-06-15", "semaine"),
                                  "annotee": None}) == cle_juin,
                  "cle_note_carte: identité → 'numero_groupeid_jourtype' attendu")

            rep_ca = notes.NOTES_DIR / "_ca"
            rep_ca.mkdir()
            legacy_annotee = rep_ca / "carte-agent-2026-06-18-annotee.pdf"
            legacy_annotee.write_bytes(b"x")
            info = resoudre_ca(date(2026, 6, 18), None, ca_dir=rep_ca)
            check(cle_note_carte(info) == "carte-agent-2026-06-18",
                  f"cle_note_carte: repli legacy -annotee attendu, obtenu "
                  f"{cle_note_carte(info)}")

            legacy_surl = rep_ca / "carte-agent-2026-06-19-surligné.pdf"
            legacy_surl.write_bytes(b"x")
            info = resoudre_ca(date(2026, 6, 19), None, ca_dir=rep_ca)
            check(cle_note_carte(info) == "carte-agent-2026-06-19",
                  f"cle_note_carte: repli legacy -surligné attendu, obtenu "
                  f"{cle_note_carte(info)}")

            check(cle_note_carte({}) is None,
                  "cle_note_carte: aucune CA résolue → None attendu")

            # Identité calculée par le calendrier versionné (bout en bout)
            info = resoudre_ca(date(2026, 6, 17), "443", ca_dir=rep_ca)
            check(info["identite"] == ("443", "L2026-06-15", "semaine")
                  and cle_note_carte(info) == cle_juin,
                  f"cle_note_carte/resoudre_ca: identité calendrier attendue, "
                  f"obtenu {info.get('identite')}")

    finally:
        notes.NOTES_DIR = NOTES_DIR_REEL

    if echecs:
        print("✗ test_notes")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ notes carte agent/journée (écriture, lecture, suppression, accents)"
          " + clé de note depuis resoudre_ca (identité et replis legacy)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
