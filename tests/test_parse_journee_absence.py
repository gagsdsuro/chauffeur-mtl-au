#!/usr/bin/env python3
"""Régression du 21 septembre : absence de 5:05 puis service de 2:43."""
from html import escape
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from chauffeur.durees import resumer_durees
from chauffeur.journee import lignes_de_service
from chauffeur.modeles import Journee
from parse_journee import JourneeParser

TEXTE = (ROOT / "tests/cas_journee/47-absence-repos.txt").read_text(encoding="utf-8")
MOTIF = "P441 - REPO-Repos minimum 9 hrs manuel"
ABSENCE = {
    "id": "Absence", "type_horaire": "absence", "motif_absence": MOTIF,
    "numero_autobus": None, "duree": "5:05", "prise": "05:18",
    "lieu_prise": None, "debut": "05:18", "fin": "10:23",
    "lieu_fin": None, "releve": None, "trajets": [],
}


class TestAbsence(unittest.TestCase):
    def lire(self, parser):
        journee = parser.parse()
        self.assertIsNotNone(journee, parser.errors)
        self.assertFalse(parser.errors)
        return journee

    def test_collage_et_sauvegarde(self):
        parser = JourneeParser(TEXTE)
        j = self.lire(parser)
        self.assertEqual((j.date, j.journee_numero, j.temps_travaille),
                         ("2026-09-21", 47, "7:48"))
        self.assertEqual(len(j.pieces), 2)
        self.assertEqual(j.pieces[0].to_dict(), ABSENCE)
        p = j.pieces[1]
        self.assertEqual((p.id, p.type_horaire, p.prise, p.debut, p.fin, p.duree, p.numero_autobus),
                         ("85-07", "horaire", "12:41", "12:41", "15:24", "2:43", "31209"))
        self.assertEqual([t.to_dict()["type"] for t in p.trajets],
                         ["haut_le_pied", "service", "service"])
        self.assertEqual([(t.ligne, t.direction, t.id_parcours) for t in p.trajets_service()],
                         [("85", "est", 13), ("85", "ouest", 15)])
        self.assertEqual(p.releve["je_releve"]["matricule"], "10001")
        self.assertEqual(p.releve["je_suis_releve_par"]["matricule"], "10002")
        with tempfile.TemporaryDirectory() as tmp, patch.object(JourneeParser, "JOURNEES_DIR", Path(tmp)):
            relu = json.loads(parser.save(j).read_text(encoding="utf-8"))
        self.assertEqual(relu, j.to_dict())
        self.assertEqual(Journee.from_dict(relu).to_dict(), relu)

    def test_html_et_ancres_details_inverses(self):
        entete, suite = TEXTE.split("SommaireAbsence", 1)
        absence, suite = suite.split("Sommaire85", 1)
        service, suite = suite.split("Détails Absence", 1)
        _, details_service = suite.split("Détails 85 - 07", 1)

        def html(texte):
            return "".join(f"<div>{escape(l)}</div>" for l in texte.splitlines() if l)

        # Balises séparées comme dans le portail, jusque dans l'horaire.
        absence_html = (
            '<a class="work-piece-summary-link" href="#absence">'
            '<span>Sommaire</span><span>Absence</span><span>En vigueur</span>'
            '<span>5:05</span><span>Horaire</span></a>'
            '<div><span>05:18</span> - <span>10:23</span> '
            f'<span>{MOTIF}</span></div>'
        )
        service_html = html("Sommaire85" + service).replace(
            "<div>Sommaire", '<a class="work-piece-summary-link" href="#service"></a><div>Sommaire', 1
        )
        for inverser in (False, True):
            with self.subTest(details_inverses=inverser):
                blocs = [
                    '<h2 class="trips-item-heading" id="absence">Détails Absence</h2>',
                    '<h2 class="trips-item-heading" id="service">Détails 85 - 07</h2>' + html(details_service),
                ]
                if inverser:
                    blocs.reverse()
                parser = JourneeParser.from_portal_json({
                    "date": "2026-09-21", "journeeHtml": html(entete) + absence_html + service_html,
                    "voyagesHtml": "".join(blocs),
                }, "2026-09-21")
                self.assertEqual(self.lire(parser).to_dict(), self.lire(JourneeParser(TEXTE)).to_dict())

    def test_absence_apres_service_et_absences_repetees(self):
        entete, suite = TEXTE.split("SommaireAbsence", 1)
        absence, suite = suite.split("Sommaire85", 1)
        service, details = suite.split("Détails Absence", 1)
        txt = (entete + "Sommaire85" + service + "SommaireAbsence" + absence
               + "SommaireAbsence" + absence + "Détails 85 - 07"
               + details.split("Détails 85 - 07", 1)[1] + "\nDétails Absence\nDétails Absence\n")
        j = self.lire(JourneeParser(txt))
        self.assertEqual([p.id for p in j.pieces], ["85-07", "Absence", "Absence"])
        self.assertEqual(len(j.pieces[0].trajets), 3)
        self.assertEqual([p.to_dict() for p in j.pieces[1:]], [ABSENCE, ABSENCE])

    def test_absence_seule_et_quart_apres_minuit(self):
        texte = ("59200 - Frontenac\nSommaireAbsenceEn vigueur5:05Horaire\n"
                 f"23:18 - 28:23 {MOTIF}\nDétails Absence\n")
        j = self.lire(JourneeParser(texte, "2026-09-21"))
        self.assertEqual(len(j.pieces), 1)
        r = resumer_durees(j)
        self.assertFalse(r.anomalies)
        self.assertEqual((r.prise_debut, r.prise_fin), ("23:18", "28:23"))
        self.assertEqual(r.lignes[0].duree, 305)
        self.assertFalse(lignes_de_service(j))

    def test_absence_incomplete_ne_disparait_pas_silencieusement(self):
        for txt in (TEXTE.replace("05:18 - 10:23 " + MOTIF, ""),
                    TEXTE.replace("5:05Horaire", "--Horaire")):
            parser = JourneeParser(txt)
            self.assertIsNone(parser.parse())
            self.assertTrue(any("absence" in e for e in parser.errors))

    def test_resume_durees(self):
        j = self.lire(JourneeParser(TEXTE))
        r = resumer_durees(j)
        self.assertFalse(r.anomalies)
        self.assertEqual((r.prise_debut, r.prise_fin), ("05:18", "15:24"))
        self.assertEqual([(l.type_segment, l.heure, l.duree_totale) for l in r.lignes[:3]],
                         [("absence", "05:18", 305), ("fin", "10:23", None), ("pause", "10:23", 138)])
        self.assertFalse(r.lignes[0].battement_maximal)
        self.assertEqual(sum(l.duree_totale or 0 for l in r.lignes if l.type_segment != "pause"), 468)


if __name__ == "__main__":
    unittest.main()
