#!/usr/bin/env python3
"""
test_page_detours.py — Test d'interface de la page Détours (AppTest).

Hermétique : G-D, évènements, détours enregistrés, journal commun et comptes
dans un répertoire temporaire ; GTFS remplacé par le cas figé
tests/cas_rapport_gd/gd-125-est-2026-07-17 via les caches de app.utils.
L'évènement de ce cas (détour de de Rouen, cinq arrêts ajoutés sur une même
étape) est expiré : la page le reconstruit depuis l'entrée enregistrée.

La page s'ouvre sans exception, liste le détour incertain avec son diagnostic,
et « Valider ce choix » enregistre un choix validé (auteur, version) qui sort
de la liste « À réviser ».

Usage : python3 tests/test_page_detours.py   (code de sortie 0 si tout passe)
"""
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap  # noqa: E402,F401
import app.utils as utils  # noqa: E402
from chauffeur import auth, depots, journal  # noqa: E402
from chauffeur import registre_detours as rd  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

CAS = ROOT / "tests" / "cas_rapport_gd" / "gd-125-est-2026-07-17"
GD = json.loads((CAS / "gd.json").read_text(encoding="utf-8"))
EVENTS = json.loads((CAS / "events.json").read_text(encoding="utf-8"))
GTFS = json.loads((CAS / "gtfs_stops.json").read_text(encoding="utf-8"))
STOPS = [tuple(x) for x in GTFS["stops"]]


class TestPageDetours(unittest.TestCase):
    def setUp(self):
        self.contexte = ExitStack()
        self.addCleanup(self.contexte.close)
        base = Path(self.contexte.enter_context(tempfile.TemporaryDirectory()))
        self.app = base / "app"
        shutil.copytree(ROOT / "app", self.app, ignore=shutil.ignore_patterns("__pycache__"))
        self.data = base / "data"
        gd_dir = self.data / "Gauche-Droite"
        gd_dir.mkdir(parents=True)
        (gd_dir / "gd125_est.json").write_text(json.dumps(GD, ensure_ascii=False), encoding="utf-8")
        (self.data / "Events").mkdir()
        (self.data / "Events" / "125_est.json").write_text(json.dumps(
            {"ligne": "125", "direction": "est", "detours": EVENTS}, ensure_ascii=False),
            encoding="utf-8")
        gtfs_dir = self.data / "gtfs" / "gtfs_stm"
        gtfs_dir.mkdir(parents=True)
        (gtfs_dir / "stops.txt").write_text("stop_id,stop_code,stop_name\n", encoding="utf-8")
        self.detours_dir = depots.repertoire_detours(gd_dir)

        for module, attribut, valeur in (
            (depots, "DATA_DIR", self.data),
            (depots, "GD_DIR", gd_dir),
            (depots, "GTFS_DIR", gtfs_dir),
            (bootstrap, "DATA_DIR", self.data),
            (auth, "DATA_DIR", self.data),
            (journal, "LOG_DIR_COMMUN", self.data / "log"),
            (utils, "_cached_noms_arrets", lambda *a: GTFS["stop_names"]),
            (utils, "_cached_sequence_parcours", lambda *a: STOPS),
        ):
            self.contexte.enter_context(patch.object(module, attribut, valeur))
        for cible, valeur in (("chauffeur.gtfs.stops_for_parcours", lambda *a, **k: STOPS),
                              ("chauffeur.gtfs.stop_names", lambda *a, **k: GTFS["stop_names"])):
            self.contexte.enter_context(patch(cible, valeur))
        rd.synchroniser_evenements_ligne("125", "est", base=self.data, jour=date(2026, 7, 17))

    def ouvrir_page(self):
        at = AppTest.from_file(str(self.app / "main.py"), default_timeout=30).run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        at.switch_page("pages/8_detours.py").run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        return at

    def test_revision_puis_validation(self):
        at = self.ouvrir_page()
        detour = next(s for s in at.selectbox if s.label == "Détour")
        ligne, direction, signature = detour.value
        self.assertEqual((ligne, direction), ("125", "est"))
        self.assertTrue(any("ordre à vérifier" in w.value for w in at.warning), [w.value for w in at.warning])

        at.session_state["auth_matricule"] = "40001"
        next(b for b in at.button if b.label == "✅ Valider ce choix").click().run()
        self.assertFalse(at.exception, [e.value for e in at.exception])

        contenu = rd.charger_detours("125", "est", self.detours_dir)
        entree = contenu["detours"][signature]
        self.assertEqual(entree["statut"], "valide")
        self.assertEqual(entree["valide_par"], "40001")
        self.assertEqual(contenu["version"], 2)
        self.assertEqual(len(entree["choix"]["arrets_ajoutes"]), 5)
        self.assertTrue(any("validé" in s.value for s in at.success))
        self.assertTrue(any("Aucun détour à réviser" in s.value for s in at.success))

    def test_vue_tous(self):
        at = self.ouvrir_page()
        at.segmented_control(key="det_vue").set_value("Tous").run()
        self.assertFalse(at.exception, [e.value for e in at.exception])


if __name__ == "__main__":
    unittest.main(verbosity=1)
