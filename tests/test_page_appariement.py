#!/usr/bin/env python3
"""
test_page_appariement.py — Test d'interface de la page Appariement (AppTest).

Hermétique : données dans un répertoire temporaire (G-D, appariements,
journal commun, comptes) ; GTFS remplacé par le cas figé 460-est-24 via les
caches de app.utils. Parcours : la page s'ouvre sans exception, liste le
parcours incertain, affiche ses segments, et « Valider » enregistre un
appariement validé (auteur, version) qui sort de la liste « À réviser ».

Usage : python3 tests/test_page_appariement.py   (code de sortie 0 si tout passe)
"""
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap  # noqa: E402,F401
import app.utils as utils  # noqa: E402
from chauffeur import auth, depots, journal  # noqa: E402
from chauffeur import registre_appariement as reg  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

CAS = ROOT / "tests" / "cas_appariement" / "460-est-24"
PARCOURS = json.loads((CAS / "parcours.json").read_text(encoding="utf-8"))
GTFS = json.loads((CAS / "gtfs_stops.json").read_text(encoding="utf-8"))
STOPS = [tuple(x) for x in GTFS["stops"]]


class TestPageAppariement(unittest.TestCase):
    def setUp(self):
        self.contexte = ExitStack()
        self.addCleanup(self.contexte.close)
        base = Path(self.contexte.enter_context(tempfile.TemporaryDirectory()))
        self.app = base / "app"
        shutil.copytree(ROOT / "app", self.app, ignore=shutil.ignore_patterns("__pycache__"))
        data = base / "data"
        gd_dir = data / "Gauche-Droite"
        gd_dir.mkdir(parents=True)
        (gd_dir / "gd460_est.json").write_text(json.dumps(
            {"ligne": "460", "direction": "est", "routes": [{"parcours": [PARCOURS]}]},
            ensure_ascii=False), encoding="utf-8")
        gtfs_dir = data / "gtfs" / "gtfs_stm"
        gtfs_dir.mkdir(parents=True)
        (gtfs_dir / "stops.txt").write_text("stop_id,stop_code,stop_name\n", encoding="utf-8")
        self.app_dir = data / "Appariements"

        for module, attribut, valeur in (
            (depots, "DATA_DIR", data),
            (depots, "GD_DIR", gd_dir),
            (depots, "GTFS_DIR", gtfs_dir),
            (bootstrap, "DATA_DIR", data),
            (auth, "DATA_DIR", data),
            (journal, "LOG_DIR_COMMUN", data / "log"),
            (utils, "_cached_noms_arrets", lambda *a: GTFS["stop_names"]),
            (utils, "_cached_sequence_parcours", lambda *a: STOPS),
        ):
            self.contexte.enter_context(patch.object(module, attribut, valeur))
        reg.synchroniser_parcours("460", "est", PARCOURS, STOPS, GTFS["stop_names"], self.app_dir)

    def ouvrir_page(self):
        at = AppTest.from_file(str(self.app / "main.py"), default_timeout=30).run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        at.switch_page("pages/7_appariement.py").run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        return at

    def test_revision_puis_validation(self):
        at = self.ouvrir_page()
        parcours = next(s for s in at.selectbox if s.label == "Parcours")
        self.assertEqual(parcours.value, ("460", "est", 24))
        segments = next(m for m in at.metric if m.label == "Segments à réviser")
        self.assertEqual(segments.value, "6")

        at.session_state["auth_matricule"] = "40001"
        next(b for b in at.button if b.label == "✅ Valider l'appariement").click().run()
        self.assertFalse(at.exception, [e.value for e in at.exception])

        contenu = reg.charger_appariement("460", "est", 24, self.app_dir)
        self.assertEqual(contenu["statut"], "valide")
        self.assertEqual(contenu["valide_par"], "40001")
        self.assertEqual(contenu["version"], 2)
        self.assertTrue(any("validé" in s.value for s in at.success))
        self.assertTrue(any("Aucun parcours à réviser" in s.value for s in at.success))

    def test_vue_tous_et_apercu(self):
        at = self.ouvrir_page()
        at.segmented_control(key="app_vue").set_value("Tous").run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        # AppTest compte le tableau éditable comme un dataframe : éditeur + aperçu G-D.
        self.assertEqual(len(at.dataframe), 2)
        self.assertTrue(any("Tous" == s.value for s in at.segmented_control))


if __name__ == "__main__":
    unittest.main(verbosity=1)
