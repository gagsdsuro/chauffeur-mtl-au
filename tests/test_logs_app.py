#!/usr/bin/env python3
"""
test_logs_app.py — Page Logs (5_logs.py) : familles flotte/personnel réunies

Teste l'app Streamlit (AppTest) : après connexion, la page liste dans un même
sélecteur les journaux **communs** (Flotte) et **personnels** (Personnel),
affiche le contenu du journal choisi, et — dossier vide — un `st.info`
mentionnant les deux répertoires.

Les répertoires de journaux sont chauffés sur des répertoires temporaires
(`chauffeur.journal.LOG_DIR_COMMUN` et sa résolution du répertoire personnel),
donc le test n'écrit jamais dans `data/`.

Les comptes sont également créés dans le répertoire temporaire.
Exige streamlit installé.

Usage : python3 tests/test_logs_app.py   (code de sortie 0 si tout passe)
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

import chauffeur.journal as journal  # noqa: E402
from chauffeur import auth  # noqa: E402

MATRICULE = "41001"
PIN = "1111"


def champ(at, key):
    return next(x for x in at.text_input if x.key == key)


def bouton(at, label):
    return next(b for b in at.button if b.label == label)


def logue(at) -> None:
    champ(at, "login_matricule").set_value(MATRICULE)
    champ(at, "login_pin").set_value(PIN)
    bouton(at, "Se connecter").click().run()
    at.run()


def pointer(commun: Path, perso: Path) -> None:
    """Route les journaux de la page vers des répertoires temporaires."""
    journal.LOG_DIR_COMMUN = commun
    journal._log_dir_prive = lambda: perso  # type: ignore[assignment]


def suite(commun: Path, perso: Path, vide_commun: Path, vide_perso: Path) -> list[str]:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    # ── 1. Journaux des deux familles dans le même sélecteur ─────────────────
    pointer(commun, perso)
    at = AppTest.from_file(str(ROOT / "app/pages/5_logs.py"), default_timeout=30).run()
    logue(at)
    check(not at.exception,
          f"page: aucune exception ({[str(e.value)[:100] for e in at.exception]})")
    check("Logs" in [h.value for h in at.header], "page: en-tête Logs affiché")

    sel = at.selectbox(key="log_sel")
    n = len(sel.options)
    check(n == 3,
          f"page: 3 journaux réunis (2 flotte + 1 personnel), obtenu {n}")

    contenus = []
    for i in range(n):
        sel.select(i).run()
        contenus.extend(c.value or "" for c in at.code)
    tous = "\n".join(contenus)
    check("GTFS téléchargé" in tous or "rapport G-D" in tous,
          "page: un journal de la flotte est affiché")
    check("rapport journée" in tous,
          "page: le journal personnel est affiché dans le sélecteur")
    check(any("Modifié le" in (c.value or "") for c in at.caption),
          "page: l'en-tête du fichier montre sa dernière modification")

    # ── 2. Dossiers vides → message d'info mentionnant les deux familles ─────
    pointer(vide_commun, vide_perso)
    at2 = AppTest.from_file(str(ROOT / "app/pages/5_logs.py"), default_timeout=30).run()
    logue(at2)
    check(any("aucun fichier de log trouvé" in (i.value or "").lower()
              for i in at2.info),
          "vide: message 'aucun fichier de log' affiché")
    if any(at2.info):
        message = "\n".join(i.value or "" for i in at2.info)
        check("(flotte)" in message and "(personnel)" in message,
              "vide: le message cite les deux familles (flotte + personnel)")

    return echecs


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        commun = base / "commun"
        perso = base / "perso"
        for d in (commun, perso):
            d.mkdir()
        journal.ecrire_bloc("parse_gd", "rapport G-D", log_dir=commun)
        journal.ecrire_ligne("fetch_gtfs", "GTFS téléchargé", log_dir=commun)
        journal.ecrire_bloc("parse_journee", "rapport journée", log_dir=perso)

        vide_commun = base / "vide_commun"
        vide_perso = base / "vide_perso"
        for d in (vide_commun, vide_perso):
            d.mkdir()

        with patch.object(auth, "DATA_DIR", base):
            auth.creer_compte(MATRICULE, PIN, "Roxanne")
            echecs = suite(commun, perso, vide_commun, vide_perso)

    if echecs:
        print("✗ test_logs_app")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        sys.exit(1)

    print("✓ page Logs : familles flotte/personnel réunies + message d'info")
    print("\n1/1 cas réussis")
    sys.exit(0)
