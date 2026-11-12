#!/usr/bin/env python3
"""Navigation des fichiers avec données temporaires et AppTest."""
from contextlib import ExitStack
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
from streamlit.testing.v1 import AppTest
import bootstrap
from chauffeur import depots, auth
from app.components import file_manager


class TestFichiersApp(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(depots, "DATA_DIR", self.base))
        self.stack.enter_context(patch.object(depots, "GD_DIR", self.base / "Gauche-Droite"))
        self.stack.enter_context(patch.object(depots, "EVENTS_DIR", self.base / "Events"))
        self.stack.enter_context(patch.object(auth, "comptes_configure", return_value=False))
        self.stack.enter_context(patch.object(bootstrap, "initialiser_page", lambda: depots.definir_matricule_contexte("40002")))
        self.stack.enter_context(patch.object(file_manager, "periode_pour_date", return_value=None))
        dossier = self.base / "40002/journees"
        dossier.mkdir(parents=True)
        for i in range(210):
            jour = date(2026, 1, 5) + timedelta(days=i)
            (dossier / f"journee-{jour}.json").write_text(json.dumps({"date": str(jour), "pieces": []}))
        self.at = AppTest.from_file(str(ROOT / "app/pages/4_fichiers.py"), default_timeout=20)
        self.at.session_state["fichiers_etat_40002"] = {"categorie": "journee"}
        self.at.run()
        self.verifier()

    def verifier(self):
        self.assertFalse(self.at.exception, [e.value for e in self.at.exception])

    def bouton(self, label):
        return next(b for b in self.at.button if b.label == label)

    def test_pagination_filtres_et_memoire(self):
        self.assertEqual(len(self.at.dataframe[0].value), 10)
        premiere = self.at.dataframe[0].value.iloc[0]["Fichier"]
        self.bouton("Suivant").click().run()
        self.verifier()
        self.assertNotEqual(self.at.dataframe[0].value.iloc[0]["Fichier"], premiere)
        self.at.text_input(key="fm_widget_journee_recherche").set_value("2026-02").run()
        self.verifier()
        self.assertTrue(all("2026-02" in n for n in self.at.dataframe[0].value["Fichier"]))
        self.at.selectbox(key="fm_widget_categorie").select("ca").run()
        self.at.selectbox(key="fm_widget_categorie").select("journee").run()
        self.assertEqual(self.at.text_input(key="fm_widget_journee_recherche").value, "2026-02")
        self.at.selectbox(key="fm_widget_journee_periode").select("2026-10-26").run()
        self.verifier()
        self.assertEqual(self.at.selectbox(key="fm_widget_journee_periode").value, "2026-10-26")
        self.assertTrue(any("Aucun fichier" in x.value for x in self.at.info))

    def test_periode_initiale_et_selection_hors_filtre(self):
        from chauffeur.periodes import PeriodeListe
        self.at.session_state["fichiers_etat_40002"] = {"categorie": "journee"}
        with patch.object(file_manager, "periode_pour_date", return_value=PeriodeListe(date(2026, 8, 24), date(2026, 10, 25))):
            self.at.run()
        self.verifier()
        self.assertEqual(self.at.selectbox(key="fm_widget_journee_periode").value, "2026-08-24")
        self.at.run()
        self.assertEqual(self.at.selectbox(key="fm_widget_journee_periode").value, "2026-08-24")
        self.at.selectbox(key="fm_widget_journee_periode").select("*").run()
        self.at.session_state["fichiers_etat_40002"]["journee_selection"] = "journee-2026-01-05.json"
        self.at.run()
        self.assertTrue(any(b.label == "Modifier" for b in self.at.button))
        self.at.text_input(key="fm_widget_journee_recherche").set_value("2026-02").run()
        self.verifier()
        self.assertFalse(any(b.label == "Modifier" for b in self.at.button))

    def test_edition_et_export_independant(self):
        nom = "journee-2026-01-05.json"
        etat = self.at.session_state["fichiers_etat_40002"]
        etat["journee_selection"] = nom
        self.at.run()
        self.bouton("Modifier").click().run()
        self.verifier()
        texte = json.dumps({"date": "2026-01-05", "pieces": [], "note": "Été"})
        self.at.text_area[0].set_value(texte).run()
        self.at.selectbox(key="fm_widget_categorie").select("ca").run()
        self.at.selectbox(key="fm_widget_categorie").select("journee").run()
        self.verifier()
        self.assertEqual(self.at.text_area[0].value, texte)
        self.bouton("Enregistrer").click().run()
        self.verifier()
        p = self.base / "40002/journees" / nom
        self.assertEqual(json.loads(p.read_text())["note"], "Été")
        self.assertEqual(len(list(p.parent.glob("*.bak"))), 1)
        self.bouton("Export des journées").click().run()
        self.bouton("Préparer l'export").click().run()
        self.verifier()
        self.assertIn("export", self.at.session_state["fichiers_etat_40002"])


if __name__ == "__main__":
    unittest.main()
