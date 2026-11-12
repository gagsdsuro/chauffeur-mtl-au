#!/usr/bin/env python3
"""Page Préparation — proposition, exécution, bilan et reprise du mode semi-automatique.

`executer_semi_auto` est remplacé par un double : l'orchestrateur a ses propres
tests (tests/test_preparation_auto.py). Ici on vérifie l'interface (AppTest).

Usage : python3 tests/test_page_preparation_auto.py
"""
from contextlib import ExitStack
from datetime import date
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for variable in ("CHAUFFEUR_MATRICULE", "CHAUFFEUR_MODE_STRICT"):
    os.environ.pop(variable, None)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from streamlit.testing.v1 import AppTest
import bootstrap
from chauffeur import auth, ca, depots, notes, portail, preparation, preparation_auto
from chauffeur.preparation_auto import ResultatEtape, ResultatSemiAuto
from cas_durees import journee_443

SANS_JOURNEE = date(2026, 11, 9)
AVEC_JOURNEE = date.fromisoformat(journee_443()["date"])


def etapes_ok(*noms):
    return [ResultatEtape(nom, "ok", f"{nom} fait") for nom in noms]


class Double:
    """Remplace executer_semi_auto : rend les résultats dans l'ordre et note les appels."""

    def __init__(self, *resultats):
        self.resultats = list(resultats)
        self.appels = []

    def __call__(self, date_cible, **kw):
        self.appels.append({"date": str(date_cible), **kw})
        return self.resultats.pop(0)


class TestPageSemiAuto(unittest.TestCase):
    def setUp(self):
        self.contexte = ExitStack()
        self.addCleanup(self.contexte.close)
        self.base = Path(self.contexte.enter_context(tempfile.TemporaryDirectory()))
        self.app = self.base / "app"
        shutil.copytree(ROOT / "app", self.app, ignore=shutil.ignore_patterns("__pycache__"))
        self.data = self.base / "data"
        (self.data / "journees").mkdir(parents=True)
        (self.data / "rapports").mkdir()
        j = journee_443()
        (self.data / "journees" / f"journee-{j['date']}.json").write_text(
            json.dumps(j, ensure_ascii=False), encoding="utf-8"
        )
        for module, attribut, valeur in (
            (depots, "DATA_DIR", self.data),
            (depots, "GD_DIR", self.data / "Gauche-Droite"),
            (depots, "EVENTS_DIR", self.data / "Events"),
            (depots, "GTFS_DIR", self.data / "gtfs" / "gtfs_stm"),
            (bootstrap, "DATA_DIR", self.data),
            (auth, "DATA_DIR", self.data),
            (notes, "NOTES_DIR", self.data / "notes"),
            (preparation, "EVENTS_DIR", self.data / "Events"),
            (preparation, "GTFS_MANIFEST", self.data / "gtfs" / "manifest.json"),
            (ca, "resoudre_ca", lambda *args: {}),
            (portail, "etat_session", lambda: portail.EtatSessionPortail("valide", "Session de test")),
        ):
            self.contexte.enter_context(patch.object(module, attribut, valeur))

    def ouvrir(self, jour, double):
        self.contexte.enter_context(patch.object(preparation_auto, "executer_semi_auto", double))
        at = AppTest.from_file(str(self.app / "main.py"), default_timeout=30).run()
        self.sans_exception(at)
        at.switch_page("pages/2_preparation.py").run()
        self.sans_exception(at)
        at.date_input(key="prep_date").set_value(jour).run()
        self.sans_exception(at)
        return at

    def sans_exception(self, at):
        self.assertFalse(at.exception, [e.value for e in at.exception])

    @staticmethod
    def cles(at):
        return {b.key for b in at.button}

    def test_proposition_seulement_sans_journee(self):
        at = self.ouvrir(SANS_JOURNEE, Double())
        self.assertIn("semi_auto_btn", self.cles(at))
        at = self.ouvrir(AVEC_JOURNEE, Double())
        self.assertNotIn("semi_auto_btn", self.cles(at))

    def test_execution_terminee_affiche_flash_et_bilan(self):
        termine = ResultatSemiAuto(
            SANS_JOURNEE.isoformat(),
            etapes=etapes_ok("journee", "calendrier") + [
                ResultatEtape("carte_agent", "avertissement", "Aucune carte agent publiée"),
            ],
        )
        double = Double(termine)
        at = self.ouvrir(SANS_JOURNEE, double)
        at.button(key="semi_auto_btn").click().run()
        self.sans_exception(at)
        self.assertEqual(len(double.appels), 1)
        self.assertEqual(double.appels[0]["date"], SANS_JOURNEE.isoformat())
        self.assertIsNone(double.appels[0]["precedent"])
        self.assertFalse(double.appels[0]["sans_portail"])
        self.assertTrue(any("terminée" in s.value and "1 avertissement" in s.value
                            for s in at.success), [s.value for s in at.success])
        self.assertNotIn("semi_auto_btn", self.cles(at))   # le bilan remplace la proposition
        self.assertIn("semi_auto_fermer", self.cles(at))
        self.assertNotIn("semi_auto_reprendre", self.cles(at))   # chaîne terminée
        self.assertIsNone(at.session_state["operation_portail"]
                          if "operation_portail" in at.session_state else None)

    def test_session_expiree_demande_le_renouvellement(self):
        interrompu = ResultatSemiAuto(
            SANS_JOURNEE.isoformat(),
            etapes=[ResultatEtape("journee", "session_expiree", "Session expirée")],
            reprise_a="journee",
        )
        at = self.ouvrir(SANS_JOURNEE, Double(interrompu))
        at.button(key="semi_auto_btn").click().run()
        self.sans_exception(at)
        operation = at.session_state["operation_portail"]
        self.assertEqual(operation["type"], "semi_auto")
        self.assertEqual(operation["date"], SANS_JOURNEE.isoformat())
        self.assertFalse(operation["reprendre"])
        self.assertEqual(operation["resultat"]["reprise_a"], "journee")
        self.assertTrue(at.session_state["ouvrir_dialog_session"])

    def test_reprise_apres_renouvellement_de_session(self):
        interrompu = ResultatSemiAuto(
            SANS_JOURNEE.isoformat(),
            etapes=[ResultatEtape("journee", "session_expiree", "Session expirée")],
            reprise_a="journee",
        )
        fin = ResultatSemiAuto(SANS_JOURNEE.isoformat(), etapes=etapes_ok("journee"))
        double = Double(fin)
        at = self.ouvrir(SANS_JOURNEE, double)
        at.session_state["operation_portail"] = {
            "type": "semi_auto", "date": SANS_JOURNEE.isoformat(),
            "resultat": interrompu.to_dict(), "reprendre": True,
        }
        at.run()
        self.sans_exception(at)
        self.assertEqual(len(double.appels), 1)
        self.assertEqual(double.appels[0]["precedent"], interrompu)

    def test_arret_bloquant_reprendre_puis_fermer(self):
        bloque = ResultatSemiAuto(
            SANS_JOURNEE.isoformat(),
            etapes=etapes_ok("journee", "calendrier", "carte_agent") + [
                ResultatEtape("gauche_droite", "bloque", "G-D manquants : 24 est"),
            ],
            reprise_a="gauche_droite",
        )
        fin = ResultatSemiAuto(SANS_JOURNEE.isoformat(), etapes=etapes_ok("journee"))
        double = Double(bloque, fin)
        at = self.ouvrir(SANS_JOURNEE, double)
        at.button(key="semi_auto_btn").click().run()
        self.sans_exception(at)
        self.assertIn("semi_auto_reprendre", self.cles(at))
        self.assertNotIn("semi_auto_sans_portail", self.cles(at))   # seulement à l'étape évènements
        at.button(key="semi_auto_reprendre").click().run()
        self.sans_exception(at)
        self.assertEqual(len(double.appels), 2)
        self.assertEqual(double.appels[1]["precedent"], bloque)
        at.button(key="semi_auto_fermer").click().run()
        self.sans_exception(at)
        self.assertIn("semi_auto_btn", self.cles(at))   # bilan fermé : la proposition revient

    def test_continuer_sans_les_evenements_du_portail(self):
        interrompu = ResultatSemiAuto(
            SANS_JOURNEE.isoformat(),
            etapes=etapes_ok("journee", "calendrier", "carte_agent", "gauche_droite") + [
                ResultatEtape("evenements", "session_expiree", "Session expirée"),
            ],
            reprise_a="evenements",
        )
        fin = ResultatSemiAuto(SANS_JOURNEE.isoformat(), etapes=etapes_ok("journee"))
        double = Double(interrompu, fin)
        at = self.ouvrir(SANS_JOURNEE, double)
        at.button(key="semi_auto_btn").click().run()
        self.assertEqual(at.session_state["operation_portail"]["type"], "semi_auto")
        # « Annuler » dans le dialogue de session : l'opération est effacée, le bilan reste.
        del at.session_state["operation_portail"]
        at.session_state["ouvrir_dialog_session"] = False
        at.run()
        self.sans_exception(at)
        at.button(key="semi_auto_sans_portail").click().run()
        self.sans_exception(at)
        self.assertTrue(double.appels[1]["sans_portail"])
        self.assertEqual(double.appels[1]["precedent"], interrompu)

    def test_bilan_limite_a_sa_date(self):
        termine = ResultatSemiAuto(SANS_JOURNEE.isoformat(), etapes=etapes_ok("journee"))
        at = self.ouvrir(SANS_JOURNEE, Double(termine))
        at.button(key="semi_auto_btn").click().run()
        at.date_input(key="prep_date").set_value(date(2026, 11, 10)).run()
        self.sans_exception(at)
        self.assertIn("semi_auto_btn", self.cles(at))   # autre date : proposition, pas le bilan
        self.assertNotIn("semi_auto_fermer", self.cles(at))


if __name__ == "__main__":
    unittest.main()
