#!/usr/bin/env python3
"""États, navigation et aperçus : vrais scripts, données synthétiques isolées.

Usage : python3 tests/test_etat_streamlit.py
La copie temporaire de l'app n'emporte ni .env ni données personnelles.
"""
from contextlib import ExitStack
from datetime import date
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for variable in ("CHAUFFEUR_MATRICULE", "CHAUFFEUR_MODE_STRICT"):
    os.environ.pop(variable, None)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from streamlit.testing.v1 import AppTest
import bootstrap
from chauffeur import auth, ca, depots, gtfs_rt, notes, portail, preparation
import gen_rapport_v2
import parse_gd
from cas_durees import journee_443, journee_475


class TestInterface(unittest.TestCase):
    def setUp(self):
        self.contexte = ExitStack()
        self.addCleanup(self.contexte.close)
        self.base = Path(self.contexte.enter_context(tempfile.TemporaryDirectory()))
        self.app = self.base / "app"
        shutil.copytree(ROOT / "app", self.app, ignore=shutil.ignore_patterns("__pycache__"))
        self.data = self.base / "data"
        self.journees = self.data / "journees"
        self.rapports = self.data / "rapports"
        self.journees.mkdir(parents=True)
        self.rapports.mkdir()
        for j in (journee_443(), journee_475()):
            self.ecrire(j)
        fichiers = [(date.fromisoformat(j["date"]), self.chemin(j["date"]))
                    for j in (journee_443(), journee_475())]
        for module, attribut, valeur in (
            (depots, "DATA_DIR", self.data),
            (depots, "GD_DIR", self.data / "Gauche-Droite"),
            (depots, "EVENTS_DIR", self.data / "Events"),
            (depots, "GTFS_DIR", self.data / "gtfs" / "gtfs_stm"),
            (depots, "lister_journees_fenetre", lambda reference: fichiers),
            (bootstrap, "DATA_DIR", self.data),
            (auth, "DATA_DIR", self.data),
            (notes, "NOTES_DIR", self.data / "notes"),
            (preparation, "EVENTS_DIR", self.data / "Events"),
            (preparation, "GTFS_MANIFEST", self.data / "gtfs" / "manifest.json"),
            (gen_rapport_v2, "GTFS_DIR", self.data / "gtfs" / "gtfs_stm"),
            (gen_rapport_v2, "OUTPUT_DIR", self.rapports),
            (ca, "resoudre_ca", lambda *args: {}),
            (portail, "etat_session", lambda: portail.EtatSessionPortail("absente", "Session de test")),
        ):
            self.contexte.enter_context(patch.object(module, attribut, valeur))

    def chemin(self, jour):
        return self.journees / f"journee-{jour}.json"

    def ecrire(self, journee):
        self.chemin(journee["date"]).write_text(
            json.dumps(journee, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def ouvrir(self):
        at = AppTest.from_file(str(self.app / "main.py"), default_timeout=30).run()
        self.sans_exception(at)
        return at

    def sans_exception(self, at):
        self.assertFalse(at.exception, [e.value for e in at.exception])

    def changer_page(self, at, page):
        at.switch_page(f"pages/{page}.py").run()
        self.sans_exception(at)

    @staticmethod
    def champ(at, collection, label):
        return next(c for c in getattr(at, collection) if c.label == label)

    def test_note_releve_suit_matricule_reimporte(self):
        for role in ("je_releve", "je_suis_releve_par"):
            for texte_b in ("Note B", ""):
                with self.subTest(role=role, cible_avec_note=bool(texte_b)):
                    j = journee_475()
                    j["pieces"][0]["releve"] = {role: {"matricule": "41001", "nom": "Personne A"}}
                    self.ecrire(j)
                    notes.sauvegarder_note_matricule("41001", "Note A", nom="Personne A")
                    notes.sauvegarder_note_matricule("41002", texte_b, nom="Personne B")
                    note_a, note_b = notes.note_matricule("41001"), notes.note_matricule("41002")
                    at = self.ouvrir()
                    champ = lambda nom: self.champ(at, "text_area", f"Note — Personne {nom}")
                    self.assertEqual(champ("A").value, "Note A")
                    champ("A").set_value("Brouillon A").run()

                    def changer(matricule, nom):
                        j["pieces"][0]["releve"][role] = {"matricule": matricule, "nom": f"Personne {nom}"}
                        self.ecrire(j)
                        at.run()
                        self.sans_exception(at)

                    changer("41002", "B")
                    self.assertEqual(champ("B").value, texte_b)

                    def enregistrer():
                        next(b for b in at.button if b.key.startswith("db_note_mat_save_")).click().run()
                        self.sans_exception(at)

                    enregistrer()
                    self.assertEqual(notes.note_matricule("41001"), note_a)
                    self.assertEqual(notes.note_matricule("41002"), note_b)
                    champ("B").set_value("Note B modifiée").run()
                    enregistrer()
                    changer("41001", "A")
                    self.assertEqual(champ("A").value, "Note A")
                    changer("41002", "B")
                    self.assertEqual(champ("B").value, "Note B modifiée")
                    self.assertEqual(notes.note_matricule("41001"), note_a)
                    self.assertEqual(notes.note_matricule("41002")["note"], "Note B modifiée")

    def test_bus_reimporte_remplace_ancien_brouillon(self):
        j = journee_475()
        j["pieces"][0]["numero_autobus"] = "38013"
        self.ecrire(j)
        notes.sauvegarder_note_voiture("39999", "Note B")
        at = self.ouvrir()
        self.champ(at, "text_input", "Numéro d'autobus").set_value("38888").run()
        j["pieces"][0]["numero_autobus"] = "39999"
        self.ecrire(j)
        at.run()
        self.sans_exception(at)
        self.assertEqual(self.champ(at, "text_input", "Numéro d'autobus").value, "39999")
        self.assertEqual(self.champ(at, "text_area", "Note — bus 39999").value, "Note B")
        next(b for b in at.button if b.proto.help == "Enregistrer le numéro d'autobus").click().run()
        self.assertEqual(json.loads(self.chemin(j["date"]).read_text())["pieces"][0]["numero_autobus"], "39999")

    def test_navigation_dates_notes_et_brouillons(self):
        notes.sauvegarder_note_journee("2026-08-23", "Note enregistrée")
        at = self.ouvrir()
        at.selectbox(key="journee_date").select("2026-08-23").run()
        self.champ(at, "text_area", "📝 Note journée").set_value("Note modifiée").run()
        at.button(key="db_note_journee_save_2026-08-23").click().run()
        self.champ(at, "text_area", "📝 Note journée").set_value("Brouillon non enregistré").run()
        self.changer_page(at, "2_preparation")
        at.date_input(key="prep_date").set_value(date(2026, 8, 23)).run()
        self.champ(at, "text_area", "Texte brut").set_value("Brouillon import").run()
        self.changer_page(at, "3_rapports")
        at.date_input(key="rj_date").set_value(date(2026, 8, 23)).run()
        at.date_input(key="rpt_v2_date").set_value(date(2026, 9, 10)).run()
        self.changer_page(at, "1_ma_journee")
        self.assertEqual(at.selectbox(key="journee_date").value, "2026-08-23")
        self.assertEqual(self.champ(at, "text_area", "📝 Note journée").value, "Note modifiée")
        self.assertEqual(notes.note_journee("2026-08-23")["note"], "Note modifiée")
        self.changer_page(at, "2_preparation")
        self.assertEqual(at.date_input(key="prep_date").value, date(2026, 8, 23))
        self.assertEqual(self.champ(at, "text_area", "Texte brut").value, "")
        self.changer_page(at, "3_rapports")
        self.assertEqual(at.date_input(key="rj_date").value, date(2026, 8, 23))
        self.assertEqual(at.date_input(key="rpt_v2_date").value, date(2026, 9, 10))

    def test_preparation_brouillon_ne_change_pas_de_date(self):
        at = self.ouvrir()
        self.changer_page(at, "2_preparation")
        at.date_input(key="prep_date").set_value(date(2026, 8, 23)).run()
        self.champ(at, "text_area", "Texte brut").set_value("Journée A à importer").run()
        next(c for c in at.checkbox if c.key.startswith("ca_remplacer_")).check().run()
        ancien_upload = at.get("file_uploader")[0].proto.id
        at.date_input(key="prep_date").set_value(date(2026, 9, 10)).run()
        self.sans_exception(at)
        self.assertEqual(self.champ(at, "text_area", "Texte brut").value, "")
        self.assertFalse(next(c for c in at.checkbox if c.key.startswith("ca_remplacer_")).value)
        self.assertNotEqual(at.get("file_uploader")[0].proto.id, ancien_upload)

    def test_notes_journee_et_carte_suivent_identite(self):
        info = {"identite": ("475", "liste_test", "semaine")}
        with patch.object(ca, "resoudre_ca", lambda *args: info):
            notes.sauvegarder_note_carte("475_liste_test_semaine", "Carte A")
            notes.sauvegarder_note_carte("443_liste_test_semaine", "Carte B")
            notes.sauvegarder_note_journee("2026-09-10", "Journée A")
            notes.sauvegarder_note_journee("2026-08-23", "Journée B")
            at = self.ouvrir()
            self.champ(at, "text_area", "📝 Note carte agent").set_value("Brouillon carte A").run()
            info["identite"] = ("443", "liste_test", "semaine")
            at.run()
            self.assertEqual(self.champ(at, "text_area", "📝 Note carte agent").value, "Carte B")
            self.champ(at, "text_area", "📝 Note journée").set_value("Brouillon journée A").run()
            at.selectbox(key="journee_date").select("2026-08-23").run()
            self.assertEqual(self.champ(at, "text_area", "📝 Note journée").value, "Journée B")
            at.selectbox(key="journee_date").select("2026-09-10").run()
            self.assertEqual(self.champ(at, "text_area", "📝 Note journée").value, "Journée A")
            self.assertEqual(notes.note_carte("475_liste_test_semaine")["note"], "Carte A")
            self.sans_exception(at)

    def test_date_libre_et_erreurs_recuperables(self):
        j = journee_475()
        j["date"] = "2026-07-01"
        self.ecrire(j)
        # AppTest 1.64 ne sérialise pas une nouvelle option de selectbox.
        # Amorcer l'état public vérifie le traitement côté app ; la saisie
        # effective (dont clavier tactile) reste dans la recette navigateur.
        for valeur in (j["date"], "2026-02-30", "2026-07-02"):
            with self.subTest(date=valeur):
                at = AppTest.from_file(str(self.app / "main.py"), default_timeout=30)
                at.session_state["journee_date"] = valeur
                at.run()
                self.sans_exception(at)
                self.assertEqual(at.selectbox(key="journee_date").value, valeur)
                if valeur == "2026-02-30":
                    self.assertTrue(any("date valide" in w.value for w in at.warning))
                elif valeur == "2026-07-02":
                    self.assertTrue(any("Aucune journée enregistrée" in i.value for i in at.info))
                else:
                    self.assertTrue(any(m.label == "Temps travaillé" for m in at.metric))
                at.selectbox(key="journee_date").select("2026-09-10").run()
                self.sans_exception(at)
                self.assertTrue(any(m.label == "Temps travaillé" for m in at.metric))

    def test_resultat_rafraichissement_ne_change_pas_de_journee(self):
        at = self.ouvrir()
        at.session_state["db_refresh_result"] = {"lignes": [], "restantes": []}
        at.session_state["db_refresh_report"] = {"message": "Rapport du 10"}
        at.selectbox(key="journee_date").select("2026-08-23").run()
        self.sans_exception(at)
        self.assertNotIn("db_refresh_result", at.session_state)
        self.assertNotIn("db_refresh_report", at.session_state)

    def test_position_bus_ne_suit_pas_un_autre_bus_ou_jour(self):
        j = journee_475()
        j["pieces"][0]["numero_autobus"] = "38013"
        self.ecrire(j)
        pb = self.base / "positions.pb"
        pb.write_bytes(b"positions synthetiques")
        position = {"v_label": "38013", "lat": 45.5, "lon": -73.6}
        with patch.object(depots, "info_gtfs", lambda: {"rt_avail": True, "rt_pb": pb}), \
                patch.object(gtfs_rt, "parse_vehicle_positions", lambda contenu: []), \
                patch.object(gtfs_rt, "find_vehicle", lambda bus, vehicles: position):
            at = self.ouvrir()
            at.session_state["db_rt_last_fetch"] = time.time()
            self.champ(at, "button", "📍 Géolocaliser").click().run()
            self.assertTrue(any("Lat 45.50000" in s.value for s in at.success))
            self.champ(at, "text_input", "Numéro d'autobus").set_value("39999").run()
            self.assertFalse(any("Lat 45.50000" in s.value for s in at.success))
            at.selectbox(key="journee_date").select("2026-08-23").run()
            self.assertFalse(any("Lat 45.50000" in s.value for s in at.success))
            self.sans_exception(at)

    def test_deconnexion_efface_etats_personnels(self):
        auth.creer_compte("41001", "1111", "Personne A")
        at = self.ouvrir()
        at.text_input(key="login_matricule").set_value("41001")
        at.text_input(key="login_pin").set_value("1111")
        self.champ(at, "button", "Se connecter").click().run()
        at.run()
        for cle, valeur in {
            "prep_date": date(2026, 8, 23),
            "operation_portail": {"type": "import_journee", "date": "2026-08-23"},
            "db_geo_r_test": {"v_label": "38013"},
            "db_note_mat_edit_test": "Brouillon privé",
        }.items():
            at.session_state[cle] = valeur
        self.champ(at, "button", "Se déconnecter").click().run()
        self.sans_exception(at)
        for cle in ("auth_matricule", "prep_date", "operation_portail", "db_geo_r_test", "db_note_mat_edit_test"):
            self.assertNotIn(cle, at.session_state)
        self.assertTrue(any(c.key == "login_pin" for c in at.text_input))

    def test_import_gd_confirme_avant_de_retirer_des_parcours(self):
        def collage(id_, nom):
            return ("Gauche-Droite / 24 Est\n"
                    f"Parcours {nom}ID {id_}\nDépart {id_} 51{id_:03d}\n"
                    f"Via - Sherbrooke\nDroite - Peel\nArrivée {id_} 52{id_:03d}\n")

        gd_dir = self.data / "Gauche-Droite"

        def ids():
            d = json.loads((gd_dir / "gd24_est.json").read_text(encoding="utf-8"))
            return [p["id"] for p in d["routes"][0]["parcours"]]

        def importer(at, texte):
            at.text_area(key="gd_text").set_value(texte).run()
            at.button(key="gd_btn").click().run()
            self.sans_exception(at)

        with patch.object(parse_gd.GDParser, "GD_DIR", gd_dir):
            at = self.ouvrir()
            self.changer_page(at, "2_preparation")
            importer(at, collage(21, "Normal"))           # fichier nouveau : direct
            self.assertEqual(ids(), [21])
            self.assertFalse(any(b.key == "gd_fusionner" for b in at.button))

            importer(at, collage(24, "Court"))            # retirerait l'ID 21 : confirmation
            self.assertEqual(ids(), [21])
            self.assertTrue(any("ID 21" in w.value for w in at.warning))
            at.button(key="gd_fusionner").click().run()
            self.sans_exception(at)
            self.assertEqual(ids(), [21, 24])             # les deux co-existent

            importer(at, collage(22, "Ecole"))
            at.button(key="gd_annuler").click().run()
            self.assertEqual(ids(), [21, 24])             # annulé : rien d'écrit
            self.assertFalse(any(b.key == "gd_fusionner" for b in at.button))

            importer(at, collage(22, "Ecole"))
            at.text_area(key="gd_text").set_value(collage(24, "Court")).run()
            self.assertFalse(any(b.key == "gd_fusionner" for b in at.button))  # texte changé
            importer(at, collage(22, "Ecole"))
            at.button(key="gd_remplacer").click().run()
            self.sans_exception(at)
            self.assertEqual(ids(), [22])

    def test_rapport_v2_selection_par_parcours(self):
        jour = "2026-09-10"
        j = journee_475()
        for piece in j["pieces"]:
            for trajet in piece["trajets"]:
                if trajet["type"] == "service":
                    trajet["id_parcours"] = 1
        self.ecrire(j)
        at = self.ouvrir()
        self.changer_page(at, "3_rapports")
        at.date_input(key="rpt_v2_date").set_value(date.fromisoformat(jour)).run()
        self.sans_exception(at)
        cle_nord = f"rpt_v2_sel_{jour}_136_nord_1"
        cle_sud = f"rpt_v2_sel_{jour}_136_sud_1"
        self.assertEqual(at.selectbox(key=cle_nord).value, "(défaut)")
        at.selectbox(key=cle_sud).set_value("ne pas générer").run()
        at.selectbox(key=cle_nord).set_value("compact").run()
        at.button(key="rpt_v2_btn").click().run()
        self.sans_exception(at)
        self.assertFalse(at.error)
        # Sélection personnalisée : fichier à part, rapport standard jamais écrasé.
        perso = self.rapports / f"rapport-v2-{jour}-personnalise.html"
        self.assertTrue(perso.exists())
        self.assertFalse((self.rapports / f"rapport-v2-{jour}-détaillé.html").exists())
        html = perso.read_text(encoding="utf-8")
        self.assertIn("136 Nord", html)
        self.assertNotIn("136 Sud", html)
        # Tout exclure : erreur lisible, pas d'exception.
        at.selectbox(key=cle_nord).set_value("ne pas générer").run()
        self.assertTrue(any("Aucun parcours" in w.value for w in at.warning))

    def test_trois_apercus_et_telechargements(self):
        jour = "2026-09-10"
        j = journee_475()
        for piece in j["pieces"]:
            for trajet in piece["trajets"]:
                if trajet["type"] == "service":
                    trajet["id_parcours"] = 1
        self.ecrire(j)
        complet = gen_rapport_v2.generer_rapport(
            self.chemin(jour), output=self.rapports / f"rapport-v2-{jour}-détaillé.html"
        )
        trajet = gen_rapport_v2.generer_rapport(
            self.chemin(jour), output=self.rapports / f"rapport-v2-{jour}-136-nord-id1.html",
            filtre_ligne="136", filtre_direction="nord",
        )
        at = self.ouvrir()
        contenus = [i.proto.srcdoc for i in at.get("iframe")]
        self.assertTrue(any(complet.read_text(encoding="utf-8") in c for c in contenus))
        self.assertTrue(any(trajet.read_text(encoding="utf-8") in c for c in contenus))
        self.assertTrue(all(i.proto.scrolling for i in at.get("iframe")))
        self.changer_page(at, "3_rapports")
        at.date_input(key="rpt_v2_date").set_value(date.fromisoformat(jour)).run()
        at.button(key="rpt_v2_btn").click().run()
        self.sans_exception(at)
        self.assertFalse(at.error)
        self.assertIn(complet.read_text(encoding="utf-8"), at.get("iframe")[0].proto.srcdoc)
        self.assertTrue(at.get("iframe")[0].proto.scrolling)
        self.assertTrue(any(d.proto.label == "⬇️ Télécharger (HTML)" and d.proto.url
                            for d in at.get("download_button")))
        at.radio(key="rpt_v2_fmt").set_value("pdf").run()
        at.button(key="rpt_v2_btn").click().run()
        self.sans_exception(at)
        self.assertFalse(at.error)
        self.assertTrue((self.rapports / f"rapport-v2-{jour}-détaillé.pdf").read_bytes().startswith(b"%PDF"))
        self.assertTrue(any(d.proto.label == "⬇️ Télécharger (PDF)" and d.proto.url
                            for d in at.get("download_button")))

    def test_rapport_journalier_utilise_la_journee_du_compte(self):
        # Vrai sous-processus, dépôt isolé et journée homonyme dans le dossier
        # historique : le rapport doit choisir celle du compte connecté.
        for dossier in ("scripts", "chauffeur"):
            shutil.copytree(ROOT / dossier, self.base / dossier,
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.contexte.enter_context(patch.object(bootstrap, "SCRIPTS_DIR", self.base / "scripts"))
        for matricule in ("41001", "41002"):
            with self.subTest(matricule=matricule):
                auth.creer_compte(matricule, "1111", "Compte de recette")
                prive = self.data / matricule / "journees"
                prive.mkdir(parents=True)
                jour = journee_475()
                jour["garage"] = f"Garage du compte {matricule}"
                (prive / "journee-2026-09-10.json").write_text(json.dumps(jour))
                at = self.ouvrir()
                at.text_input(key="login_matricule").set_value(matricule)
                at.text_input(key="login_pin").set_value("1111")
                self.champ(at, "button", "Se connecter").click().run()
                at.run()
                self.changer_page(at, "3_rapports")
                at.date_input(key="rj_date").set_value(date(2026, 9, 10)).run()
                at.button(key="rj_btn").click().run()
                self.sans_exception(at)
                self.assertFalse(at.error)
                self.assertTrue(any(f"Garage du compte {matricule}" in c.value for c in at.code))
                pdf = self.data / matricule / "rapports/rapport-2026-09-10.pdf"
                self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))
                self.assertFalse((self.rapports / pdf.name).exists())


if __name__ == "__main__":
    unittest.main()
