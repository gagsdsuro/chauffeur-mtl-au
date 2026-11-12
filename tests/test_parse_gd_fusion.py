#!/usr/bin/env python3
"""
test_parse_gd_fusion.py — Import G-D : fusion ou remplacement par id de parcours.

Régression (ligne 24 est, novembre 2026) : importer le parcours ID 21 puis, dans
un second collage, le parcours ID 24 faisait disparaître le premier — le fichier
devenait exactement le dernier collage. Désormais, un collage qui retirerait des
parcours du fichier existant exige un choix : « fusionner » (les parcours collés
remplacent ceux de même id, les autres sont conservés) ou « remplacer » (le
fichier devient le collage, comme l'import complet du portail). L'id est la clé
partout, y compris dans le résumé des changements.

Hermétique : répertoire G-D temporaire.

Usage : python3 tests/test_parse_gd_fusion.py   (code de sortie 0 si tout passe)
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import parse_gd  # noqa: E402
from parse_gd import GDParser  # noqa: E402


def collage(*parcours):
    """Collage brut « Gauche-Droite / 24 Est » : (id, nom, rue) par parcours."""
    texte = ["Gauche-Droite / 24 Est"]
    for id_, nom, rue in parcours:
        texte += [f"Parcours {nom}ID {id_}", f"Départ {id_} 51{id_:03d}",
                  f"Via - {rue}", "Droite - Peel", f"Arrivée {id_} 52{id_:03d}"]
    return "\n".join(texte) + "\n"


P21 = (21, "Normal", "Sherbrooke")
P24 = (24, "Court", "Cherrier")
P22 = (22, "Ecole", "Rachel")


class TestFusionGD(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Les synchronisations (appariements, détours) écrivent à côté du répertoire
        # G-D : l'isoler dans un sous-dossier garde tout dans le répertoire temporaire.
        self.dir = Path(self._tmp.name) / "Gauche-Droite"
        self.dir.mkdir()

    def importer(self, texte, mode=None):
        parser = GDParser(texte, gd_dir=self.dir)
        resultat = parser.parse(mode) if mode else parser.parse()
        self.assertIsNotNone(resultat, parser.errors)
        return parser

    def ids(self):
        d = json.loads((self.dir / "gd24_est.json").read_text(encoding="utf-8"))
        return [p["id"] for p in d["routes"][0]["parcours"]]

    def retires(self, texte):
        return [p["id"] for p in GDParser(texte, gd_dir=self.dir).parcours_retires()]

    def test_deux_imports_successifs_sans_confirmation_ecrasent(self):
        """Comportement historique conservé (mode par défaut = remplacer)."""
        self.importer(collage(P21))
        self.importer(collage(P24))
        self.assertEqual(self.ids(), [24])

    def test_retraits_detectes_par_id(self):
        self.assertEqual(self.retires(collage(P21)), [])         # fichier nouveau
        self.importer(collage(P21, P22))
        self.assertEqual(self.retires(collage(P24)), [21, 22])
        self.assertEqual(self.retires(collage(P21)), [22])
        self.assertEqual(self.retires(collage(P22, P21, P24)), [])  # ajout seul
        self.assertEqual(self.ids(), [21, 22])                   # l'analyse n'écrit rien

    def test_fusion_conserve_et_ajoute(self):
        self.importer(collage(P21))
        parser = self.importer(collage(P24), "fusionner")
        self.assertEqual(self.ids(), [21, 24])
        self.assertIn("ID 21", parser.report)          # conservé, signalé
        self.assertIn("Total parcours: 2", parser.report)
        self.assertNotIn("SUPPRIME", parser.report)
        self.assertIn("+NOUVEAU", parser.report)

    def test_fusion_remplace_par_id_a_sa_place(self):
        self.importer(collage(P21, P22, P24))
        self.importer(collage((22, "Ecole", "Nouvelle-Rue")), "fusionner")
        d = json.loads((self.dir / "gd24_est.json").read_text(encoding="utf-8"))
        parcours = d["routes"][0]["parcours"]
        self.assertEqual([p["id"] for p in parcours], [21, 22, 24])   # ordre gardé
        self.assertIn("Via - Nouvelle-Rue", parcours[1]["direction"])
        self.assertIn("Via - Sherbrooke", parcours[0]["direction"])   # 21 intact

    def test_remplacer_retire_les_absents(self):
        self.importer(collage(P21, P22))
        parser = self.importer(collage(P24), "remplacer")
        self.assertEqual(self.ids(), [24])
        self.assertIn("Parcours 21", parser.report)
        self.assertIn("-SUPPRIME", parser.report)

    def test_resume_par_id_pas_par_codes_d_arret(self):
        self.importer(collage(P21))
        # Même id, autres arrêts de début/fin : une modification, pas -SUPPRIME/+NOUVEAU.
        modifie = collage(P21).replace("51021", "59999")
        parser = self.importer(modifie, "fusionner")
        self.assertIn("trajet", parser.report)
        self.assertNotIn("+NOUVEAU", parser.report)
        self.assertNotIn("-SUPPRIME", parser.report)
        # Réimport identique : aucun changement.
        parser = self.importer(modifie, "fusionner")
        self.assertIn("Aucun changement", parser.report)

    def test_mode_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            GDParser(collage(P21), gd_dir=self.dir).parse("ecraser")

    def cli(self, texte, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with patch.object(GDParser, "GD_DIR", self.dir), \
             patch.object(sys, "stdin", io.StringIO(texte)), \
             patch.object(sys, "argv", ["parse_gd.py", *args]), \
             redirect_stdout(sortie), redirect_stderr(erreur):
            with self.assertRaises(SystemExit) as sortie_code:
                parse_gd.main()
        return sortie_code.exception.code, erreur.getvalue()

    def test_cli_exige_un_choix_quand_des_parcours_seraient_retires(self):
        self.assertEqual(self.cli(collage(P21))[0], 0)      # fichier nouveau : direct
        code, erreur = self.cli(collage(P24))
        self.assertEqual(code, 1)
        self.assertIn("ID 21", erreur)
        self.assertIn("--fusionner", erreur)
        self.assertEqual(self.ids(), [21])                  # rien d'écrit
        self.assertEqual(self.cli(collage(P24), "--fusionner")[0], 0)
        self.assertEqual(self.ids(), [21, 24])
        self.assertEqual(self.cli(collage(P22), "--remplacer")[0], 0)
        self.assertEqual(self.ids(), [22])
        self.assertEqual(self.cli(collage(P22, P21))[0], 0)  # ajout seul : direct
        self.assertEqual(self.ids(), [22, 21])


if __name__ == "__main__":
    unittest.main()
