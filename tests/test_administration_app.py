#!/usr/bin/env python3
"""
test_administration_app.py — Page Administration et verrouillage des rôles (phase 4)

Teste l'app Streamlit (AppTest) :
* un simple Chauffeur ne peut pas ouvrir la page (garde-fou) ;
* un Chauffeur-admin peut créer un compte, le promouvoir, réinitialiser son PIN
  et le révoquer ;
* la barre latérale permet la déconnexion et le changement de son PIN.

Hermétique : comptes et données personnelles dans un répertoire temporaire.
Exige streamlit installé.

Usage : python3 tests/test_administration_app.py   (code de sortie 0 si tout passe)
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for _var in ("CHAUFFEUR_MATRICULE", "CHAUFFEUR_MODE_STRICT"):
    os.environ.pop(_var, None)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from streamlit.testing.v1 import AppTest  # noqa: E402

from chauffeur import auth, depots  # noqa: E402

ADMIN, CHA1, CHA2 = "40001", "20002", "30003"


def champ(at, key):
    return next(x for x in at.text_input if x.key == key)


def bouton(at, label):
    return next(b for b in at.button if b.label == label)


def suite() -> list[str]:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    def logue(at, matricule, pin) -> None:
        champ(at, "login_matricule").set_value(matricule)
        champ(at, "login_pin").set_value(pin)
        bouton(at, "Se connecter").click().run()
        at.run()

    # ── 1. Un simple Chauffeur est bloqué sur la page Administration ─────────
    at = AppTest.from_file(str(ROOT / "app/pages/6_administration.py"), default_timeout=30).run()
    logue(at, CHA1, "2222")
    check(not at.exception, f"chauffeur: aucune exception ({[str(e.value)[:100] for e in at.exception]})")
    check("⚙️ Administration" not in [h.value for h in at.header],
          "chauffeur: en-tête Administration absent")
    check(any("réservée" in (i.value or "") for i in at.info),
          "chauffeur: message d'accès restreint affiché")
    atlas = [c.value for c in at.caption]
    check(not any("Chauffeur-admin" in c for c in atlas),
          "chauffeur: aucun contenu d'administration")

    # ── 2. Un Chauffeur-admin gère les comptes ───────────────────────────────
    at = AppTest.from_file(str(ROOT / "app/pages/6_administration.py"), default_timeout=30).run()
    logue(at, ADMIN, "1234")
    check("⚙️ Administration" in [h.value for h in at.header],
          "admin: en-tête Administration affiché")

    # ── 2a. Création d'un compte Chauffeur ────────────────────────────────────
    champ(at, "admin_nouveau_matricule").set_value(CHA2)
    champ(at, "admin_nouveau_pin").set_value("6666")
    bouton(at, "Créer le compte").click().run()
    at.run()
    check(auth.role(CHA2) == auth.ROLE_CHAUFFEUR,
          f"admin: création → Chauffeur ({auth.role(CHA2)})")

    # ── 2b. Promotion en Chauffeur-admin ──────────────────────────────────────
    at.selectbox(key="admin_cible").select(CHA2).run()
    bouton(at, "Promouvoir en Chauffeur-admin").click().run()
    at.run()
    check(auth.role(CHA2) == auth.ROLE_ADMIN,
          f"admin: promotion → Chauffeur-admin ({auth.role(CHA2)})")

    # ── 2c. Réinitialisation du PIN (sans l'ancien) ───────────────────────────
    champ(at, "admin_pin_nouveau").set_value("7777")
    champ(at, "admin_pin_confirmation").set_value("7777")
    bouton(at, "Réinitialiser le PIN").click().run()
    at.run()
    ok, _ = auth.verifier_pin(CHA2, "7777")
    check(ok, "admin: PIN réinitialisé → accepté sans l'ancien")

    # ── 2d. Auto-destitution visible pour soi-même ────────────────────────────
    at.selectbox(key="admin_cible").select(ADMIN).run()
    check(any(b.label == "Se destituer (revenir Chauffeur)" for b in at.button),
          "admin: bouton d'auto-destitution présent pour son propre compte")

    # ── 3. Déconnexion depuis la barre latérale ───────────────────────────────
    at = AppTest.from_file(str(ROOT / "app/pages/1_ma_journee.py"), default_timeout=30).run()
    logue(at, ADMIN, "1234")
    bouton(at, "Se déconnecter").click().run()
    check("auth_matricule" not in at.session_state,
          "déconnexion: la clé auth_matricule est retirée de la session")

    return echecs


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(auth, "DATA_DIR", Path(tmp)), \
                patch.object(depots, "DATA_DIR", Path(tmp)):
            auth.creer_compte(ADMIN, "1234", "Denis")
            auth.creer_compte(CHA1, "2222", "Geneviève")
            echecs = suite()

    if echecs:
        print("✗ test_administration_app")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ page Administration : garde-fou Chauffeur, gestion des comptes par l'admin")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
