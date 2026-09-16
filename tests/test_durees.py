#!/usr/bin/env python3
"""Régressions du résumé des durées : python3 tests/test_durees.py."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.durees import resumer_durees
from chauffeur.modeles import Journee
from cas_durees import ATTENDU_443, ATTENDU_475, journee_443, journee_475, piece, trajet


class TestDurees(unittest.TestCase):
    def test_exemples_complets(self):
        for construire, attendu, bornes, amplitude, maxima in (
            (journee_475, ATTENDU_475, ("17:11", "26:33"), 562, (1, 1)),
            (journee_443, ATTENDU_443, ("11:18", "20:04"), 526, (7, 3)),
        ):
            with self.subTest(journee=construire.__name__):
                j = construire()
                avant = deepcopy(j)
                r = resumer_durees(j)
                obtenu = [(l.heure, l.segment, l.direction, l.duree, l.battement,
                           l.duree_totale, l.battement_maximal) for l in r.lignes]
                self.assertEqual(obtenu, attendu)
                self.assertEqual((r.prise_debut, r.prise_fin), bornes)
                self.assertFalse(r.anomalies)
                self.assertEqual(sum(l.duree_totale or 0 for l in r.lignes), amplitude)
                self.assertEqual(sum(l.duree_totale or 0 for l in r.lignes
                                     if l.type_segment != "pause"), 460)
                self.assertEqual(tuple(sum(l.battement_maximal for l in r.lignes
                                           if l.index_piece == i) for i in (0, 1)), maxima)
                self.assertEqual(j, avant, "Les données sources restent intactes")
                self.assertEqual(resumer_durees(Journee.from_dict(j)), r)

    def test_pieces_contigues_id_repetes_et_ts(self):
        j = {"pieces": [
            piece("A", "9:00", "10:00", [
                trajet("service", "9:00", "9:20", "1", "est"),
                trajet("service", "9:25", "10:00", "1", "ouest"),
            ]),
            piece("A", "10:00", "11:00", [
                trajet("service", "10:00", "10:20", "1", "est"),
                trajet("service", "10:30", "11:00", "1", "ouest"),
            ], type_horaire="continu"),
        ]}
        r = resumer_durees(j)
        self.assertFalse(r.anomalies)
        self.assertEqual(r.prise_debut, "09:00")
        self.assertNotIn("pause", [l.type_segment for l in r.lignes])
        self.assertEqual([(l.index_piece, l.battement) for l in r.lignes
                          if l.battement_maximal], [(0, 5), (1, 10)])
        self.assertEqual([(l.type_segment, l.heure) for l in r.lignes[3:5]],
                         [("fin", "10:00"), ("prise", "10:00")])
        self.assertEqual([l.battement for l in r.lignes if l.type_segment == "prise"], [0, 0])

    def test_entree_avant_pause_et_borne_arrivee(self):
        j = {"pieces": [
            piece("A", "08:00", "09:05", [trajet("entree", "08:00", "09:00")]),
            piece("B", "09:30", "10:00", [trajet("service", "09:30", "10:00", "1")]),
        ]}
        r = resumer_durees(j)
        self.assertEqual(r.lignes[1].battement, 10)
        self.assertTrue(r.lignes[1].battement_maximal)
        self.assertEqual(r.lignes[2].heure, "09:10")
        self.assertEqual(r.lignes[3].battement, 20)
        self.assertEqual(r.prise_fin, "10:00")

    def test_zero_est_une_valeur_connue(self):
        r = resumer_durees({"pieces": [piece("A", "24:00", "24:00", [
            trajet("haut_le_pied", "24:00", "24:00"),
        ])]})
        self.assertFalse(r.anomalies)
        self.assertEqual(r.lignes[1].duree_totale, 0)
        self.assertTrue(r.lignes[1].battement_maximal)

    def test_heures_absentes_invalides_et_valeurs_partielles(self):
        for heure in (None, "", "--", "12:60", "-1:00", "10:5", "abc", 123):
            with self.subTest(heure=heure):
                j = journee_475()
                j["pieces"][0]["trajets"][1]["depart"]["heure"] = heure
                r = resumer_durees(j)
                self.assertTrue(r.anomalies)
                self.assertEqual(r.lignes[1].duree, 42)
                self.assertIsNone(r.lignes[1].battement)
                self.assertIsNone(r.lignes[1].duree_totale)
                self.assertIsNone(r.lignes[2].duree)
                self.assertEqual(r.lignes[2].battement, 14)
                self.assertFalse(any(l.battement_maximal for l in r.lignes if l.index_piece == 0))
                self.assertTrue(any(l.battement_maximal for l in r.lignes if l.index_piece == 1))

    def test_durees_negatives_sans_correction_de_minuit(self):
        j = {"pieces": [piece("A", "23:50", "25:00", [
            trajet("service", "23:50", "00:10", "1"),
        ])]}
        r = resumer_durees(j)
        self.assertIsNone(r.lignes[1].duree)
        self.assertIsNone(r.lignes[1].duree_totale)
        self.assertTrue(any("négative" in a.message for a in r.anomalies))
        j["pieces"][0]["trajets"][0]["arrivee"]["heure"] = "25:10"
        r = resumer_durees(j)
        self.assertEqual(r.lignes[1].duree, 80)
        self.assertIsNone(r.lignes[1].battement)
        self.assertFalse(r.lignes[1].battement_maximal)

    def test_pause_negative_ou_inconnue_reste_visible(self):
        for prise in ("20:00", None):
            j = journee_475()
            j["pieces"][1]["prise"] = prise
            r = resumer_durees(j)
            pause = next(l for l in r.lignes if l.type_segment == "pause")
            self.assertIsNone(pause.battement)
            self.assertIsNone(pause.duree_totale)
            self.assertTrue(r.anomalies)

    def test_bornes_inconnues_sans_repli(self):
        j = journee_475()
        j["pieces"][0]["prise"] = None
        j["pieces"][1]["trajets"][-1]["arrivee"] = None
        r = resumer_durees(j)
        self.assertIsNone(r.prise_debut)
        self.assertIsNone(r.prise_fin)
        self.assertIsNone(r.lignes[-1].heure)
        self.assertIsNone(r.lignes[-2].battement)
        j = journee_443()
        j["pieces"][-1]["fin"] = ""
        self.assertIsNone(resumer_durees(j).prise_fin)

    def test_journee_vide_et_piece_sans_trajet(self):
        for j in ({}, {"pieces": []}, {"pieces": None}):
            r = resumer_durees(j)
            self.assertEqual(r.lignes, [])
            self.assertFalse(r.anomalies)
            self.assertIsNone(r.prise_debut)
            self.assertIsNone(r.prise_fin)
        r = resumer_durees({"pieces": [piece("A", "08:00", "09:00", [])]})
        self.assertEqual([l.type_segment for l in r.lignes], ["prise", "fin"])
        self.assertIsNone(r.lignes[0].battement)
        self.assertTrue(r.anomalies)

    def test_type_inconnu_conserve(self):
        r = resumer_durees({"pieces": [piece("A", "08:00", "09:00", [
            trajet("autre", "08:00", "09:00"),
        ])]})
        self.assertEqual(r.lignes[1].type_segment, "inconnu")
        self.assertEqual(r.lignes[1].duree, 60)
        self.assertTrue(r.anomalies)


if __name__ == "__main__":
    unittest.main()
