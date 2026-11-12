#!/usr/bin/env python3
"""Ma journée : résumé des durées et notes, avec fichiers temporaires.

Usage : python3 tests/test_durees_app.py
Aucun accès aux comptes, journées, notes, PDF ou cookies personnels.
"""
from contextlib import ExitStack
from dataclasses import replace
from datetime import date
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
from app.components.resume_durees import TYPES_SEGMENTS, rendre_table_durees_html
from chauffeur import ca, depots, notes, portail
from chauffeur.durees import resumer_durees
from scripts.parse_journee import JourneeParser
from cas_durees import journee_443, journee_475


def tableau(at):
    return next((m.value for m in at.markdown if 'class="durees-table"' in m.value), "")


def indicateurs(at):
    return {m.label: m.value for m in at.metric}


class TestRendu(unittest.TestCase):
    def test_cellules_styles_et_echappement(self):
        r = resumer_durees(journee_475())
        html = rendre_table_durees_html(r.lignes)
        self.assertEqual(html.count('class="durees-nombre durees-max"'), 2)
        self.assertIn('class="durees-special durees-repere"', html)
        self.assertIn('class="durees-nombre" title="">0</td>', html)
        self.assertIn('class="durees-nombre" title="">—</td>', html)
        self.assertIn("overflow-x:auto", html)
        self.assertIn("26:33", html)
        ligne = replace(r.lignes[1], segment='<script>attaque</script>',
                        direction='"<b>est</b>', type_segment='" onclick="attaque')
        html = rendre_table_durees_html([ligne])
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>", html)
        self.assertNotIn('data-type="" onclick=', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&quot; onclick=&quot;", html)


class TestPage(unittest.TestCase):
    def setUp(self):
        self.contexte = ExitStack()
        self.addCleanup(self.contexte.close)
        base = Path(self.contexte.enter_context(tempfile.TemporaryDirectory()))
        self.journees = base / "journees"
        self.journees.mkdir()
        for j in (journee_475(), journee_443()):
            self.ecrire(j)
        self.fichiers = [(date.fromisoformat(j["date"]), self.chemin(j["date"]))
                         for j in (journee_443(), journee_475())]
        for cible, attribut, valeur in (
            (bootstrap, "initialiser_page", lambda: None),
            (bootstrap, "journees_dir", lambda: self.journees),
            (bootstrap, "rapports_dir", lambda: base / "rapports"),
            (depots, "lister_journees_fenetre", lambda reference: self.fichiers),
            (depots, "chemin_journee", self.chemin),
            (depots, "info_gtfs", lambda: {"rt_avail": False}),
            (ca, "resoudre_ca", lambda *args: {}),
            (notes, "_notes_dir", lambda: base / "notes"),
            (portail, "etat_session", lambda: portail.EtatSessionPortail("absente", "Session de test")),
        ):
            self.contexte.enter_context(patch.object(cible, attribut, valeur))

    def chemin(self, date_str):
        return self.journees / f"journee-{date_str}.json"

    def ecrire(self, journee):
        self.chemin(journee["date"]).write_text(
            json.dumps(journee, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def ouvrir(self, date_str="2026-09-10"):
        at = AppTest.from_file(str(ROOT / "app/pages/1_ma_journee.py"), default_timeout=30)
        at.session_state["journee_date"] = date_str
        at.run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        return at

    def test_page_emplacement_indicateurs_et_filtres(self):
        at = self.ouvrir()
        attendu = {"Prise début": "17:11", "Prise fin": "26:33", "Temps travaillé": "7:30"}
        for cle, valeur in attendu.items():
            self.assertEqual(indicateurs(at)[cle], valeur)
        section = next(e for e in at.expander if e.label == "Résumé des durées")
        self.assertFalse(section.proto.expanded)
        blocs = list(at.main.children.values())
        position = next(i for i, b in enumerate(blocs)
                        if b.type == "expander" and b.label == "Résumé des durées")
        self.assertEqual(blocs[position + 1].type, "subheader")
        self.assertEqual(blocs[position + 1].value, "Pièces de travail")
        self.assertEqual(at.multiselect(key="db_durees_types").value, list(TYPES_SEGMENTS))
        self.assertEqual(tableau(at).count('class="durees-nombre durees-max"'), 2)

        at.multiselect(key="db_durees_types").set_value(["hlp", "entrée"]).run()
        self.assertFalse(at.exception)
        html = tableau(at)
        self.assertNotIn('data-type="ligne"', html)
        self.assertNotIn('class="durees-nombre durees-max"', html)
        for total in (34, 25, 41):
            self.assertIn(f'>{total}</td>', html)
        for cle, valeur in attendu.items():
            self.assertEqual(indicateurs(at)[cle], valeur)

        at.multiselect(key="db_durees_types").set_value([]).run()
        self.assertFalse(tableau(at))
        self.assertTrue(any("Aucun type de segment sélectionné" in i.value for i in at.info))

        at.multiselect(key="db_durees_types").set_value(list(TYPES_SEGMENTS)).run()
        at.selectbox(key="journee_date").select("2026-08-23").run()
        self.assertFalse(at.exception)
        self.assertEqual(indicateurs(at)["Prise début"], "11:18")
        self.assertEqual(indicateurs(at)["Prise fin"], "20:04")
        self.assertEqual(indicateurs(at)["Temps travaillé"], "7:30")
        self.assertEqual(tableau(at).count('class="durees-nombre durees-max"'), 10)
        self.assertEqual(json.loads(self.chemin("2026-08-23").read_text()), journee_443())
        at.multiselect(key="db_durees_types").set_value(["entrée"]).run()
        self.assertFalse(tableau(at))
        self.assertTrue(any("Aucun segment ne correspond" in i.value for i in at.info))

    def test_page_incomplete(self):
        j = journee_475()
        j["pieces"][0]["prise"] = ""
        j["pieces"][0]["trajets"][1]["depart"]["heure"] = ""
        j["pieces"][1]["trajets"][-1]["arrivee"]["heure"] = ""
        self.ecrire(j)
        at = self.ouvrir()
        self.assertEqual(indicateurs(at)["Prise début"], "—")
        self.assertEqual(indicateurs(at)["Prise fin"], "—")
        self.assertIn('data-type="ligne"', tableau(at))
        self.assertNotIn('class="durees-nombre durees-max"', tableau(at))
        self.assertTrue(any("1 (185-62)" in w.value and "2 (136-28)" in w.value for w in at.warning))

    def test_page_piece_absence(self):
        texte = (ROOT / "tests/cas_journee/47-absence-repos.txt").read_text(encoding="utf-8")
        j = JourneeParser(texte).parse().to_dict()
        self.ecrire(j)
        self.fichiers.append((date.fromisoformat(j["date"]), self.chemin(j["date"])))
        at = self.ouvrir("2026-09-21")
        for cle, valeur in {"Prise début": "05:18", "Prise fin": "15:24", "Temps travaillé": "7:48"}.items():
            self.assertEqual(indicateurs(at)[cle], valeur)
        absence = next(e for e in at.expander if e.label.startswith("Pièce Absence"))
        self.assertIn("05:18 → 10:23", absence.label)
        self.assertIn("(5:05)", absence.label)
        self.assertTrue(any("P441 - REPO-Repos minimum 9 hrs manuel" in m.value for m in absence.markdown))
        self.assertFalse(absence.text_input)
        self.assertFalse(absence.button)
        self.assertFalse(any("Horaires incomplets" in w.value for w in at.warning))
        self.assertIn('data-type="absence"', tableau(at))
        self.assertIn('>305</td>', tableau(at))
        self.assertTrue(any(e.label.startswith("Pièce 85-07") for e in at.expander))
        self.assertEqual(len([c for c in at.text_input if c.label == "Numéro d'autobus"]), 1)
        self.assertEqual(json.loads(self.chemin(j["date"]).read_text()), j)

    def test_page_sans_piece(self):
        j = journee_475()
        j["pieces"] = []
        self.ecrire(j)
        at = self.ouvrir()
        self.assertEqual(indicateurs(at)["Prise début"], "—")
        self.assertEqual(indicateurs(at)["Prise fin"], "—")
        self.assertFalse(tableau(at))
        self.assertTrue(any("Aucune pièce de travail à résumer" in i.value for i in at.info))

    def test_note_bus_suit_changement_autobus(self):
        j = journee_475()
        j["pieces"][0]["numero_autobus"] = "38013"
        self.ecrire(j)

        for note_initiale in ("Note du bus B", ""):
            with self.subTest(bus_cible_avec_note=bool(note_initiale)):
                notes.sauvegarder_note_voiture("38013", "Note du bus A")
                notes.sauvegarder_note_voiture("39999", note_initiale)
                note_a = notes.note_voiture("38013")
                note_b = notes.note_voiture("39999")
                at = self.ouvrir()

                def champ_note(bus):
                    return next(c for c in at.text_area if c.label == f"Note — bus {bus}")

                def enregistrer_note():
                    next(b for b in at.button
                         if b.proto.help == "Enregistrer la note du bus").click().run()
                    self.assertFalse(at.exception)

                self.assertEqual(champ_note("38013").value, "Note du bus A")
                champ_note("38013").set_value("Brouillon du bus A").run()
                at.text_input(key="db_bus_edit_2026-09-10_0_185-62_38013").set_value("39999").run()
                self.assertFalse(at.exception)
                self.assertEqual(champ_note("39999").value, note_initiale)

                # Un clic sans édition ne doit pas copier la note de l'autre bus.
                enregistrer_note()
                self.assertEqual(notes.note_voiture("38013"), note_a)
                self.assertEqual(notes.note_voiture("39999"), note_b)

                champ_note("39999").set_value("Note mise à jour du bus B").run()
                enregistrer_note()
                self.assertEqual(notes.note_voiture("39999")["note"], "Note mise à jour du bus B")
                self.assertEqual(notes.note_voiture("38013"), note_a)

                at.text_input(key="db_bus_edit_2026-09-10_0_185-62_38013").set_value("38013").run()
                self.assertFalse(at.exception)
                self.assertEqual(champ_note("38013").value, "Note du bus A")
                at.text_input(key="db_bus_edit_2026-09-10_0_185-62_38013").set_value("39999").run()
                self.assertFalse(at.exception)
                self.assertEqual(champ_note("39999").value, "Note mise à jour du bus B")
                self.assertEqual(json.loads(self.chemin(j["date"]).read_text()), j)


if __name__ == "__main__":
    unittest.main()
