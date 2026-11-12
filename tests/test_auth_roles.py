#!/usr/bin/env python3
"""
test_auth_roles.py — Tests unitaires de la matrice d'autorisations (phase 4)

Auto-gestion stricte : « Chauffeur-admin … seul à changer sa propre autorité ».
Couvre la promotion/destitution (avec garde du dernier admin), la
réinitialisation de PIN et le déverrouillage administrés, la révocation, et la
création de compte avec rôle. Hermétique (tempdir). Complète tests/test_auth.py
(primitives de base : comptes, scrypt, verrouillage).

Usage : python3 tests/test_auth_roles.py   (code de sortie 0 si tout passe)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur import auth  # noqa: E402

# Rôles du scénario :
ADMIN1, CHA2, CHA3, ADMIN5 = "40001", "20001", "30001", "50001"


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    def attend_erreur(msg: str, fn) -> None:
        try:
            fn()
            check(False, msg)
        except ValueError:
            pass

    with tempfile.TemporaryDirectory() as tmp:
        users = Path(tmp) / "users.json"

        # ── Premier compte = Chauffeur-admin, quoi qu'on demande ──────────
        auth.creer_compte(ADMIN1, "1234", role=auth.ROLE_CHAUFFEUR,
                          users_path=users)
        check(auth.role(ADMIN1, users) == auth.ROLE_ADMIN,
              "premier compte: rôle Chauffeur demandé → Chauffeur-admin imposé")

        # ── Créations : sans rôle = Chauffeur ; admin par un admin ────────
        auth.creer_compte(CHA2, "9999", users_path=users)
        auth.creer_compte(CHA3, "1111", users_path=users)
        auth.creer_compte(ADMIN5, "2222", role=auth.ROLE_ADMIN,
                          operateur=ADMIN1, users_path=users)
        check(auth.role(CHA2, users) == auth.ROLE_CHAUFFEUR,
              "création sans rôle → Chauffeur")
        check(auth.role(ADMIN5, users) == auth.ROLE_ADMIN,
              "création d'un admin par un admin → Chauffeur-admin")
        attend_erreur("création admin sans opérateur : ValueError attendu",
                      lambda: auth.creer_compte("60001", "3333",
                                                role=auth.ROLE_ADMIN,
                                                users_path=users))

        # ── Promotion ─────────────────────────────────────────────────────
        auth.changer_role(CHA2, ADMIN1, auth.ROLE_ADMIN, users)
        check(auth.role(CHA2, users) == auth.ROLE_ADMIN,
              "changer_role: un admin promeut un Chauffeur → Chauffeur-admin")
        attend_erreur("changer_role: re-promotion d'un admin : ValueError attendu",
                      lambda: auth.changer_role(CHA2, ADMIN1, auth.ROLE_ADMIN, users))
        attend_erreur("changer_role: un non-admin est refusé",
                      lambda: auth.changer_role(CHA2, CHA3,
                                                auth.ROLE_CHAUFFEUR, users))

        # ── Auto-gestion stricte : un admin ne touche pas à l'autre ───────
        attend_erreur("changer_role: destitution d'un autre admin refusée",
                      lambda: auth.changer_role(ADMIN5, ADMIN1,
                                                auth.ROLE_CHAUFFEUR, users))
        attend_erreur("changer_role: promotion d'un autre admin refusée",
                      lambda: auth.changer_role(ADMIN5, ADMIN1,
                                                auth.ROLE_ADMIN, users))

        # ── Réinitialisation de PIN (admin, sans l'ancien) ────────────────
        auth.reinitialiser_pin(CHA2, "5555", ADMIN1, users)
        ok, _ = auth.verifier_pin(CHA2, "5555", users)
        check(ok, "reinitialiser_pin: nouveau PIN accepté sans l'ancien")
        ok, _ = auth.verifier_pin(CHA2, "9999", users)
        check(not ok, "reinitialiser_pin: l'ancien PIN est invalidé")
        attend_erreur("reinitialiser_pin: un non-admin est refusé",
                      lambda: auth.reinitialiser_pin(CHA2, "7777", CHA3, users))

        # ── Déverrouillage (admin) ────────────────────────────────────────
        for _ in range(auth.TENTATIVES_MAX):
            auth.verifier_pin(CHA3, "0000", users)
        check(auth.est_verrouille(CHA3, users),
              "est_verrouille: 5 échecs → compte verrouillé")
        auth.deverrouiller_compte(CHA3, ADMIN1, users)
        check(not auth.est_verrouille(CHA3, users),
              "deverrouiller_compte: compte déverrouillé")
        ok, _ = auth.verifier_pin(CHA3, "1111", users)
        check(ok, "deverrouiller_compte: PIN correct redevenu accepté")

        # ── Révocation ────────────────────────────────────────────────────
        attend_erreur("revoquer_compte: un non-admin est refusé",
                      lambda: auth.revoquer_compte(CHA2, CHA3, users))
        check(auth.revoquer_compte(CHA3, ADMIN1, users),
              "revoquer_compte: chauffeur révoqué par un admin → True")
        check(auth.role(CHA3, users) is None,
              "revoquer_compte: rôle → None après")
        attend_erreur("revoquer_compte: révocation d'un autre admin refusée",
                      lambda: auth.revoquer_compte(ADMIN5, ADMIN1, users))
        attend_erreur("revoquer_compte: auto-révocation refusée",
                      lambda: auth.revoquer_compte(ADMIN1, ADMIN1, users))
        check(not auth.revoquer_compte("71000", ADMIN1, users),
              "revoquer_compte: matricule inconnu → False")
        check(not auth.est_verrouille("71000", users),
              "est_verrouille: matricule inconnue → False")

        # ── Auto-destitution et garde du dernier admin ────────────────────
        # admins en place : ADMIN1, CHA2 (promu), ADMIN5 → auto-destitution OK
        auth.changer_role(CHA2, CHA2, auth.ROLE_CHAUFFEUR, users)
        check(auth.role(CHA2, users) == auth.ROLE_CHAUFFEUR,
              "auto-destitution permise tant qu'un autre admin reste")
        auth.changer_role(ADMIN5, ADMIN5, auth.ROLE_CHAUFFEUR, users)
        check(auth.role(ADMIN5, users) == auth.ROLE_CHAUFFEUR,
              "auto-destitution permise quand deux admins restent")
        attend_erreur("auto-destitution du dernier admin refusée",
                      lambda: auth.changer_role(ADMIN1, ADMIN1,
                                                auth.ROLE_CHAUFFEUR, users))
        check(auth.role(ADMIN1, users) == auth.ROLE_ADMIN,
              "le dernier admin conserve son rôle après refus")

        # ── Liste des comptes ─────────────────────────────────────────────
        infos = auth.lister_comptes(users)
        check(isinstance(infos, list)
              and infos == sorted(infos, key=lambda c: c["matricule"]),
              "lister_comptes: tri par matricule")
        check(all({"matricule", "nom", "role", "creer_le", "verrouille"} <= set(c)
                  for c in infos),
              "lister_comptes: clés publiques complètes")
        check(any(c["matricule"] == ADMIN1 and c["role"] == auth.ROLE_ADMIN
                  for c in infos),
              "lister_comptes: ADMIN1 reste Chauffeur-admin")

    if echecs:
        print("✗ test_auth_roles")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ matrice d'autorisations : promotion/destitution stricte, PIN admin, révocation")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())