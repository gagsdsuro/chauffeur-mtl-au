#!/usr/bin/env python3
"""
test_auth.py — Tests unitaires chauffeur.auth (PIN, registre users.json)

Couvre la création de comptes (premier = Chauffeur-admin, suivants =
Chauffeur), la validation matricule/PIN, la vérification correcte/incorrecte,
le changement de PIN, la révocation, le verrouillage temporaire après trop de
tentatives, les permissions 0600 du registre, et un registre corrompu.
Hermétique : écrit dans un répertoire temporaire.

Usage : python3 tests/test_auth.py   (code de sortie 0 si tout passe)
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur import auth  # noqa: E402


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        users_path = Path(tmp) / "users.json"

        # ── Aucun compte → non configuré ─────────────────────────────────────
        check(auth.charger_comptes(users_path) == {},
              "comptes: fichier absent → {} attendu")
        check(not auth.comptes_configure(users_path),
              "comptes_configure: aucun compte → False")

        # ── Validation PIN ───────────────────────────────────────────────────
        check(auth.pin_valide("1234") and auth.pin_valide("12345678"),
              "pin_valide: 4 à 8 chiffres acceptés")
        for mauvais in ["", "123", "123456789", "12a4"]:
            check(not auth.pin_valide(mauvais),
                  f"pin_valide({mauvais!r}) → False attendu")

        # ── Validation matricule reprise du module matricule ─────────────────
        try:
            auth.creer_compte("123", "1111", users_path=users_path)
            check(False, "creer_compte: matricule invalide doit lever ValueError")
        except ValueError:
            pass
        try:
            auth.creer_compte("40001", "aze", users_path=users_path)
            check(False, "creer_compte: PIN invalide doit lever ValueError")
        except ValueError:
            pass

        # ── Premier compte = Chauffeur-admin ────────────────────────────────
        compte = auth.creer_compte("40001", "1234", "Denis", users_path=users_path)
        check(compte["role"] == auth.ROLE_ADMIN,
              "creer_compte: premier compte → Chauffeur-admin")
        check(auth.role("40001", users_path) == auth.ROLE_ADMIN,
              "role: 40001 → Chauffeur-admin")
        check(auth.compte_info("40001", users_path)["nom"] == "Denis",
              "compte_info: nom conservé")
        check(auth.comptes_configure(users_path),
              "comptes_configure: un compte → True")

        registre = json.loads(users_path.read_text(encoding="utf-8"))
        check("1234" not in json.dumps(registre),
              "users.json: le PIN ne doit jamais apparaître en clair")
        check("sel" in registre["40001"] and len(registre["40001"]["sel"]) == 32,
              "users.json: sel hexadécimal (16 octets) présent")
        check(registre["40001"].get("role") == auth.ROLE_ADMIN,
              "users.json: rôle admin persisté")

        # ── Duplicata refusé ; second compte = Chauffeur ────────────────────
        try:
            auth.creer_compte("40001", "5678", users_path=users_path)
            check(False, "creer_compte: doublon doit lever ValueError")
        except ValueError:
            pass
        auth.creer_compte("20001", "9999", users_path=users_path)
        check(auth.role("20001", users_path) == auth.ROLE_CHAUFFEUR,
              "creer_compte: second compte → Chauffeur")

        # ── Permissions 0600 du registre ────────────────────────────────────
        mode = users_path.stat().st_mode & 0o777
        check(mode == 0o600, f"users.json: permissions 0600 attendues, obtenu {oct(mode)}")

        # ── Vérification de PIN ─────────────────────────────────────────────
        ok, msg = auth.verifier_pin("40001", "1234", users_path)
        check(ok and msg, "verifier_pin: bon PIN → (True, message)")
        ok, msg = auth.verifier_pin("40001", "9999", users_path)
        check(not ok and "incorrect" in msg,
              "verifier_pin: mauvais PIN → (False, 'PIN incorrect…')")
        ok, msg = auth.verifier_pin("71000", "1234", users_path)
        check(not ok and "inconnu" in msg,
              "verifier_pin: matricule inconnu → '… inconnu'")
        ok, msg = auth.verifier_pin("20001", "9999", users_path)
        check(ok, "verifier_pin: second compte se connecte aussi")

        # ── Verrouillage après TENTATIVES_MAX échecs ────────────────────────
        for _ in range(auth.TENTATIVES_MAX):
            auth.verifier_pin("20001", "0000", users_path)
        ok, msg = auth.verifier_pin("20001", "0000", users_path)
        check(not ok and "verrouillé" in msg,
              f"verrouillage: 5 échecs → compteur verrouillé ({msg!r})")
        ok, msg = auth.verifier_pin("20001", "9999", users_path)
        check(not ok and "verrouillé" in msg,
              "verrouillage: PIN correct refusé pendant le verrou")

        # ── Changement de PIN ───────────────────────────────────────────────
        auth.changer_pin("40001", "1234", "7777", users_path)
        ok, _ = auth.verifier_pin("40001", "7777", users_path)
        check(ok, "changer_pin: le nouveau PIN est accepté")
        ok, _ = auth.verifier_pin("40001", "1234", users_path)
        check(not ok, "changer_pin: l'ancien PIN est refusé")
        try:
            auth.changer_pin("40001", "7777", "12", users_path)
            check(False, "changer_pin: nouveau PIN invalide doit lever ValueError")
        except ValueError:
            pass

        # ── Révocation (administrée) ────────────────────────────────────────
        check(auth.revoquer_compte("20001", "40001", users_path),
              "revoquer_compte: compte présent → True")
        check(auth.role("20001", users_path) is None,
              "revoquer_compte: matricule révoqué → None")
        check(auth.lister_matricules(users_path) == ["40001"],
              "lister_matricules: seul 40001 reste")

        # ── Registre corrompu → ValueError explicite ────────────────────────
        users_path.write_text("{invalide", encoding="utf-8")
        try:
            auth.charger_comptes(users_path)
            check(False, "charger_comptes: JSON corrompu doit lever ValueError")
        except ValueError:
            pass

    if echecs:
        print("✗ test_auth")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ authentification par PIN : comptes, hash scrypt, verrouillage, révocation")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())