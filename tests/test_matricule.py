#!/usr/bin/env python3
"""
test_matricule.py — Tests unitaires chauffeur.matricule
+ validation/isolation par matricule de chauffeur.depots

Couvre la validation (plage 20000-99999, exactement 5 chiffres), l'extraction
d'un matricule depuis un texte libre, et le calcul des répertoires privés
(repertoire_utilisateur / repertoire_prive) avec et sans CHAUFFEUR_MATRICULE.
Hermétique : aucune écriture.

Usage : python3 tests/test_matricule.py   (code de sortie 0 si tout passe)
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VAR = "CHAUFFEUR_MATRICULE"
VAR_STRICT = "CHAUFFEUR_MODE_STRICT"
# Import hermétique : les constantes de chauffeur.depots sont figées à
# l'import ; on garantit un état legacy déterministe pour le processus.
os.environ.pop(VAR, None)
os.environ.pop(VAR_STRICT, None)

from chauffeur import depots  # noqa: E402
from chauffeur.depots import (  # noqa: E402
    DATA_DIR, SESSION_PATH, matricule_courant, mode_strict,
    repertoire_prive, repertoire_prive_contexte, repertoire_utilisateur,
)
from chauffeur.matricule import (  # noqa: E402
    MATRICULE_MAX, MATRICULE_MIN, matcher_matricule, matricule_valide,
)

VAR = "CHAUFFEUR_MATRICULE"
VAR_STRICT = "CHAUFFEUR_MODE_STRICT"


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    try:
        # ── Validation ──────────────────────────────────────────────────────
        for val in ["40001", "20000", "99999", "50000"]:
            v = matricule_valide(val)
            e_attendu = MATRICULE_MIN <= int(val) <= MATRICULE_MAX
            check(v == e_attendu, f"matricule_valide({val!r}) : attendu {e_attendu}")
        check(not matricule_valide("00000"),
              "matricule_valide('00000') : hors plage 20000-99999 → False attendu")

        for val in [None, "", "9", "1234", "123456", "abcd1", " 40001", "40001 ",
                    "9999a5", "19999", "4386", "438633"]:
            check(not matricule_valide(val),
                  f"matricule_valide({val!r}) : attendu False")

        # ── Extraction depuis un texte libre ────────────────────────────────
        check(matcher_matricule("Je suis relevé par - 40001") == "40001",
              "matcher_matricule: extraction 'Je suis relevé par - 40001'")
        check(matcher_matricule("") is None, "matcher_matricule: texte vide → None")
        check(matcher_matricule("matricule 12345 proposé") is None,
              "matcher_matricule: 12345 hors plage → None")
        check(matcher_matricule("deux 20000 et 99999") == "20000",
              "matcher_matricule: premier match → 20000")
        check(matcher_matricule("voiture #4412") is None,
              "matcher_matricule: 4412 hors plage → None")

        # ── Répertoires sans matricule (legacy) ─────────────────────────────
        os.environ.pop(VAR, None)
        check(repertoire_utilisateur() == DATA_DIR,
              "repertoire_utilisateur sans CHAUFFEUR_MATRICULE → DATA_DIR")
        check(repertoire_prive("journees") == DATA_DIR / "journees",
              "repertoire_prive legacy → data/journees")
        check(SESSION_PATH == DATA_DIR / "session" / "cookies.json",
              "SESSION_PATH legacy → data/session/cookies.json")

        # ── Répertoires avec matricule de l'environnement ───────────────────
        os.environ[VAR] = "40001"
        check(repertoire_utilisateur() == DATA_DIR / "40001",
              "repertoire_utilisateur → data/40001")
        check(repertoire_prive("ca") == DATA_DIR / "40001" / "ca",
              "repertoire_prive → data/40001/ca")
        check(depots.GD_DIR == DATA_DIR / "Gauche-Droite",
              "GD_DIR reste partagé (flotte)")

        # ── Matricule explicite (préférence sur le contexte) ────────────────
        os.environ.pop(VAR, None)
        check(repertoire_utilisateur("90001") == DATA_DIR / "90001",
              "repertoire_utilisateur(matricule explicite) → data/90001")
        check(repertoire_prive("log", "90001") == DATA_DIR / "90001" / "log",
              "repertoire_prive(matricule explicite) → data/90001/log")

        # ── Refus des valeurs invalides ─────────────────────────────────────
        os.environ[VAR] = "abcdef"
        try:
            matricule_courant()
            check(False, "matricule_courant: doit lever ValueError si invalide")
        except ValueError:
            pass
        os.environ.pop(VAR, None)
        try:
            repertoire_prive("journees", "123")
            check(False, "repertoire_prive: doit lever ValueError si matricule invalide")
        except ValueError:
            pass

        # ── Protection contre les chemins ∖ nom de dossier malicieux ────────
        try:
            repertoire_prive("a/b", "40001")
            check(False, "repertoire_prive: doit refuser un sous-dossier 'a/b'")
        except ValueError:
            pass

        # ── Contexte de session (par thread, app) ───────────────────────────
        depots.effacer_matricule_contexte()
        os.environ[VAR] = "40001"
        with depots.contexte_matricule("90001"):
            check(repertoire_prive("log") == DATA_DIR / "90001" / "log",
                  "contexte: le matricule de session prime sur l'environnement")
            os.environ.pop(VAR, None)
            check(repertoire_utilisateur() == DATA_DIR / "90001",
                  "contexte: repertoire_utilisateur suit la session")
        os.environ[VAR] = "40001"
        check(repertoire_prive("ca") == DATA_DIR / "40001" / "ca",
              "hors contexte: l'environnement reprend la main")
        check(repertoire_prive_contexte("notes") is None,
              "repertoire_prive_contexte sans session → None")
        depots.effacer_matricule_contexte()
        os.environ.pop(VAR, None)

        # ── Mode strict explicite (CHAUFFEUR_MODE_STRICT=1) ─────────────────
        check(not mode_strict(), "mode_strict: absent par défaut → False")
        os.environ[VAR_STRICT] = "1"
        check(mode_strict(), "mode_strict: CHAUFFEUR_MODE_STRICT=1 → True")
        try:
            repertoire_prive("journees")
            check(False, "mode strict: sans matricule doit lever ValueError")
        except ValueError:
            pass
        try:
            depots.chemin_journee("2026-06-18")
            check(False, "mode strict: chemin_journee doit lever ValueError")
        except ValueError:
            pass
        check(repertoire_prive("log", "90001") == DATA_DIR / "90001" / "log",
              "mode strict: matricule explicite toujours accepté")
        depots.definir_matricule_contexte("90001")
        check(repertoire_prive("journees") == DATA_DIR / "90001" / "journees",
              "mode strict: le contexte de session débloque la résolution")
        depots.effacer_matricule_contexte()
        os.environ.pop(VAR_STRICT, None)

    finally:
        os.environ.pop(VAR, None)
        os.environ.pop(VAR_STRICT, None)
        depots.effacer_matricule_contexte()

    if echecs:
        print("✗ test_matricule")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ validation + extraction matricule + isolation des répertoires privés")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())