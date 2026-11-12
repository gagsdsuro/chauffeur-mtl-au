#!/usr/bin/env python3
"""Explorateur : calendriers, édition, isolation et contrat CSV, sans données privées."""
from contextlib import ExitStack
from datetime import date
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chauffeur import fichiers as f, periodes, depots, auth


class TestFichiers(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.ref = self.base / "reference"
        self.ref.mkdir()
        self.stack.enter_context(patch.object(periodes, "REFERENCE_DIR", self.ref))
        self.stack.enter_context(patch.object(depots, "DATA_DIR", self.base))
        self.stack.enter_context(patch.object(depots, "GD_DIR", self.base / "Gauche-Droite"))
        self.stack.enter_context(patch.object(depots, "EVENTS_DIR", self.base / "Events"))
        self.stack.enter_context(patch.object(auth, "comptes_configure", return_value=False))
        self.stack.enter_context(depots.contexte_matricule("40002"))
        self.cal(2026, ["2026-01-05", "2026-08-24", "2026-10-26"],
                 variations=[{"debut": "2026-12-21"}], feries=["2026-12-25"])

    def cal(self, annee, debuts, **autres):
        (self.ref / f"periodes_{annee}.json").write_text(json.dumps(
            {"annee": annee, "listes": [{"debut": d} for d in debuts], **autres}))

    def ecrire(self, cat, nom, contenu):
        p = f.chemin(cat, nom)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
        return p

    def test_bornes_et_cache(self):
        self.assertIsNone(periodes.periode_pour_date(date(2026, 1, 4)))
        self.assertEqual(periodes.periode_pour_date(date(2026, 10, 25)).cle, "2026-08-24")
        self.assertEqual(periodes.periode_pour_date(date(2026, 10, 26)).cle, "2026-10-26")
        self.assertIsNone(periodes.periode_pour_date(date(2027, 1, 1)))
        self.cal(2027, ["2027-01-04"])
        self.assertEqual(periodes.periode_pour_date(date(2027, 1, 2)).cle, "2026-10-26")
        self.assertEqual(periodes.periode_pour_date(date(2027, 1, 4)).cle, "2027-01-04")
        (self.ref / "periodes_2027.json").unlink()
        self.assertIsNone(periodes.periode_pour_date(date(2027, 1, 1)))
        self.cal(2028, ["2028-01-03"])
        self.assertIsNone(periodes.periode_pour_date(date(2027, 9, 1)))
        self.cal(2026, ["2026-08-25"])
        self.assertIsNone(periodes.periode_pour_date(date(2026, 8, 24)))

    def test_regime_semaine_a_cheval_sur_deux_annees(self):
        self.cal(2026, ["2026-10-26"], variations=[{"debut": "2026-12-28"}])
        self.cal(2027, ["2027-01-04"])
        self.assertEqual(periodes.regime_pour_date(date(2027, 1, 3)), "variation")
        self.assertEqual(periodes.regime_pour_date(date(2027, 1, 4)), "normal")

    def test_noms_et_regimes(self):
        for nom, regime in [("123_L2026-10-26_semaine.pdf", "normal"),
                            ("123_V2026-12-21_variation-annotee.pdf", "variation"),
                            ("123_2026-12-25_variation.pdf", "ferie"),
                            ("carte-agent-2026-12-25-annotee.pdf", "ferie"),
                            ("carte-agent-2026-12-25-surligné.pdf", "ferie")]:
            item = f.decrire("ca", nom)
            self.assertEqual(item.periode, "2026-10-26")
            self.assertEqual(item.regime, regime)
        self.assertEqual(f.decrire("journee", "journee-2026-12-25.json").regime, "ferie")
        self.assertEqual(f.decrire("ca", "123_L2026-10-27_semaine.pdf").periode, "?")
        self.assertEqual(f.decrire("ca", "inconnu.pdf").periode, "?")
        self.assertEqual(f.decrire("journee", "journee-2026-02-30.json").periode, "?")

    def test_filtres_et_inventaire_sans_lecture(self):
        dossier = f.repertoire("journee")
        dossier.mkdir(parents=True)
        for n in range(1, 29):
            (dossier / f"journee-2026-09-{n:02}.json").write_text("illisible")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("lecture inutile")):
            items = f.inventorier("journee")
            self.assertEqual(len(items), 28)
            self.assertEqual(len(f.filtrer(items, periode="2026-08-24", recherche="09-2")), 9)
            self.assertEqual(f.filtrer(items, tri="Date décroissante")[0].nom, "journee-2026-09-28.json")
            self.assertEqual(f.filtrer(items, periode="2026-10-26"), [])
        gd = [f.decrire("gd", f"gd{n}_est.json") for n in (100, 9, 24)]
        self.assertEqual([x.ligne for x in f.filtrer(gd, tri="Ligne")], ["9", "24", "100"])

    def test_edition_sauvegarde_conflit(self):
        nom = "journee-2026-09-21.json"
        contenu = {"date": "2026-09-21", "pieces": [], "inconnu": "préservé"}
        p = self.ecrire("journee", nom, contenu)
        avant = p.read_bytes()
        contenu["garage"] = "École"
        sauvegarde = f.enregistrer("journee", nom, json.dumps(contenu), f.empreinte(avant))
        self.assertEqual(sauvegarde.read_bytes(), avant)
        self.assertEqual(json.loads(p.read_bytes())["inconnu"], "préservé")
        self.assertEqual(len(f.inventorier("journee")), 1)
        with self.assertRaisesRegex(ValueError, "changé"):
            f.enregistrer("journee", nom, json.dumps(contenu), f.empreinte(avant))
        for texte in ('[]', '{', '{"date":"2026-09-20","pieces":[]}', '{"date":"2026-09-21","pieces":{}}'):
            with self.assertRaises(ValueError):
                f.enregistrer("journee", nom, texte, f.empreinte(p.read_bytes()))
        self.assertEqual(len(list(p.parent.glob("*.bak"))), 1)

    def test_droits_et_chemins(self):
        p = self.ecrire("gd", "gd24_est.json", {"ligne": "24", "direction": "est", "routes": []})
        with patch.object(auth, "role", return_value=auth.ROLE_CHAUFFEUR):
            with self.assertRaises(PermissionError):
                f.supprimer("gd", p.name, f.empreinte(p.read_bytes()))
        with patch.object(auth, "role", return_value=auth.ROLE_ADMIN):
            f.enregistrer("gd", p.name, p.read_text(), f.empreinte(p.read_bytes()))
            f.supprimer("gd", p.name, f.empreinte(p.read_bytes()))
        with self.assertRaises(ValueError):
            f.chemin("journee", "../50352/journee-2026-09-21.json")
        j = self.ecrire("journee", "journee-2026-09-21.json", {})
        with depots.contexte_matricule("50352"):
            self.assertEqual(f.inventorier("journee"), [])
            with self.assertRaises(FileNotFoundError):
                f.lire("journee", j.name)
        lien = j.parent / "journee-lien.json"
        lien.symlink_to(j)
        with self.assertRaises(ValueError):
            f.lire("journee", lien.name)
        with depots.contexte_matricule(None):
            self.assertFalse(f.peut_modifier("gd"))

    def test_csv_lignes_uniques_par_piece(self):
        sequences = [["24", "24", "24", "185", "185", "24"],
                     ["185", "24"],
                     ["24"] * 8 + ["185", "10", "85e", "125", "136", "150", "999"]]
        self.ecrire("journee", "journee-2026-09-21.json", {
            "date": "2026-09-21", "pieces": [
                {"id": str(i), "trajets": [{"type": "hlp", "ligne": "777"}] + [
                    {"type": "service", "ligne": ligne} for ligne in sequence]}
                for i, sequence in enumerate(sequences)]})
        lignes, brut, erreurs = f.exporter_journees(date(2026, 9, 21), date(2026, 9, 21))
        self.assertEqual(erreurs, [])
        self.assertEqual(list(csv.DictReader(io.StringIO(brut.decode("utf-8")))), lignes)
        attendus = [["24", "185", "", "", "", "", ""],
                    ["185", "24", "", "", "", "", ""],
                    ["24", "185", "10", "85e", "125", "136", "150"]]
        for ligne, attendu in zip(lignes, attendus):
            self.assertEqual([ligne[f"trajet{i}_ligne"] for i in range(1, 8)], attendu)

    def test_csv_contrat(self):
        self.ecrire("journee", "journee-2026-09-21.json", {
            "date": "2026-09-21", "garage_id": "01", "journee_numero": 123,
            "pieces": [{"id": "A", "trajets": [{"type": "service", "ligne": str(i)} for i in range(9)]},
                       {"id": "B", "type_horaire": "absence", "trajets": []}]})
        self.ecrire("journee", "journee-2026-09-20.json", {"pieces": [{"id": "hors intervalle"}]})
        lignes, brut, erreurs = f.exporter_journees(date(2026, 9, 21), date(2026, 9, 21))
        lecteur = csv.DictReader(io.StringIO(brut.decode()))
        self.assertEqual(lecteur.fieldnames, f.COLONNES_CSV)
        self.assertEqual(len(list(lecteur)), 2)
        self.assertEqual(lignes[0]["trajet7_ligne"], "6")
        self.assertEqual(lignes[0]["type_horaire"], "horaire")
        self.assertEqual(lignes[1]["trajet1_ligne"], "")
        self.assertEqual(erreurs, [])
        with self.assertRaises(ValueError):
            f.exporter_journees(date(2026, 9, 22), date(2026, 9, 21))


if __name__ == "__main__":
    unittest.main()
