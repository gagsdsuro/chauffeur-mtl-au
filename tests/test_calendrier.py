#!/usr/bin/env python3
"""
test_calendrier.py — Tests unitaires des fichiers .ics par pièce de travail

Couvre chauffeur.calendrier : titre « <pièce> · Lignes … », fin au-delà de
24 h, pièces ignorées (absence, sans heures), format RFC 5545 (CRLF, pliage à
75 octets, échappement, UID stable), écriture/remplacement des fichiers, et
l'accroche de JourneeParser.save (répertoire temporaire, hermétique).

Usage : python3 tests/test_calendrier.py   (code de sortie 0 si tout passe)
"""
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from chauffeur.calendrier import (  # noqa: E402
    dossier_calendrier, ecrire_calendrier, evenements_ics, lignes_de_piece,
    rendre_ics,
)

STAMP = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)


def service(ligne, direction="est"):
    return {"type": "service", "ligne": ligne, "direction": direction,
            "depart": {"heure": "11:09", "arret": "A"}, "arrivee": {"heure": "11:31", "arret": "B"}}


def piece(id_, debut="11:09", fin="12:56", trajets=(), **extra):
    return {"id": id_, "type_horaire": "horaire", "prise": "11:00", "lieu_prise": "E082",
            "debut": debut, "fin": fin, "lieu_fin": "FRT", "numero_autobus": None,
            "releve": None, "trajets": list(trajets), **extra}


def journee(*pieces, date="2026-10-23"):
    return {"date": date, "pieces": list(pieces)}


class TestCalendrier(unittest.TestCase):
    def test_titre_lignes_ordre_sans_doublon(self):
        j = journee(
            piece("34-05", trajets=[service("34"), service("34", "ouest")]),
            piece("10-02", trajets=[service("10"), service("125"), service("10")]),
            piece("176-06", trajets=[{"type": "sortie", "ligne": None}, service("176")]),
        )
        self.assertEqual([e["titre"] for e in evenements_ics(j)],
                         ["34-05 · Lignes 34", "10-02 · Lignes 10, 125", "176-06 · Lignes 176"])
        self.assertEqual(lignes_de_piece(j["pieces"][1]), ["10", "125"])

    def test_piece_sans_service_garde_son_id(self):
        j = journee(piece("HLP-1", trajets=[{"type": "haut_le_pied", "ligne": None}]))
        self.assertEqual(evenements_ics(j)[0]["titre"], "HLP-1")

    def test_fin_apres_minuit_tombe_le_lendemain(self):
        ev = evenements_ics(journee(piece("777-02", "21:50", "26:10", [service("777")]),
                                    date="2026-06-27"))[0]
        self.assertEqual(ev["debut"], datetime(2026, 6, 27, 21, 50))
        self.assertEqual(ev["fin"], datetime(2026, 6, 28, 2, 10))

    def test_ignore_absence_sans_heures_et_date_invalide(self):
        j = journee(
            {"id": "Absence", "type_horaire": "absence", "debut": "05:18", "fin": "10:23"},
            piece("112-33", debut="", fin=""),
            piece("OK-1", trajets=[service("24")]),
        )
        self.assertEqual([e["piece_id"] for e in evenements_ics(j)], ["OK-1"])
        self.assertEqual(evenements_ics({"date": "n/a", "pieces": [piece("X")]}), [])

    def test_id_duplique_donne_deux_fichiers_et_deux_uid(self):
        evs = evenements_ics(journee(piece("440-01", "06:00", "09:00"), piece("440-01", "10:00", "12:00")))
        self.assertEqual(len({e["nom_fichier"] for e in evs}), 2)
        self.assertEqual(len({e["uid"] for e in evs}), 2)

    def test_format_rfc5545(self):
        longue = "É" * 80 + ", point-virgule; et\nligne"
        ev = evenements_ics(journee(piece("34-05", trajets=[service("34")],
                                          releve={"je_releve": {"nom": longue, "matricule": "40105"}})))[0]
        ics = rendre_ics(ev, maintenant=STAMP)
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n\n", ics.replace("\r\n", "\n"))
        for ligne in ics.split("\r\n")[:-1]:
            self.assertLessEqual(len(ligne.encode("utf-8")), 75, ligne)
        depliee = ics.replace("\r\n ", "")
        self.assertIn("DTSTART:20261023T110900", depliee)
        self.assertIn("DTEND:20261023T125600", depliee)
        self.assertIn("DTSTAMP:20261030T120000Z", depliee)
        self.assertIn("SUMMARY:34-05 · Lignes 34", depliee)
        self.assertIn("LOCATION:E082", depliee)
        self.assertIn("\\;", depliee)
        self.assertIn("\\,", depliee)
        self.assertIn("\\n", depliee)
        self.assertEqual(depliee.count("BEGIN:VEVENT"), 1)
        # Aucune coupure au milieu d'un caractère multi-octets : relecture UTF-8 saine.
        ics.encode("utf-8").decode("utf-8")

    def test_uid_stable_entre_deux_rendus(self):
        j = journee(piece("34-05", trajets=[service("34")]))
        a = rendre_ics(evenements_ics(j)[0], maintenant=STAMP)
        b = rendre_ics(evenements_ics(j)[0], maintenant=datetime(2027, 1, 1, tzinfo=timezone.utc))
        uid = lambda s: next(l for l in s.split("\r\n") if l.startswith("UID:"))
        self.assertEqual(uid(a), uid(b))

    def test_description_prise_autobus_et_releve(self):
        ev = evenements_ics(journee(piece(
            "34-05", numero_autobus="40078", trajets=[service("34"), service("34", "ouest")],
            releve={"je_suis_releve_par": {"nom": "Bouchard Marie", "matricule": "40104"}})))[0]
        d = ev["description"]
        for attendu in ("Prise : 11:00 (E082)", "Fin : 12:56 (FRT)", "Autobus : 40078",
                        "Relevé par : Bouchard Marie (40104)", "Lignes : 34 est/ouest"):
            self.assertIn(attendu, d)

    def test_ecriture_remplacement_et_nettoyage(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp) / "calendrier"
            j1 = journee(piece("A-1", trajets=[service("24")]), piece("B-2", "13:00", "15:00"))
            ecrits = ecrire_calendrier(j1, dossier, maintenant=STAMP)
            self.assertEqual(sorted(p.name for p in ecrits), ["01-A-1.ics", "02-B-2.ics"])
            self.assertTrue(all(p.parent == dossier / "2026-10-23" for p in ecrits))
            # Réimport : la 2e pièce disparaît, la 1re est réécrite.
            j2 = journee(piece("A-1", "11:30", "12:56", [service("24")]))
            ecrits = ecrire_calendrier(j2, dossier, maintenant=STAMP)
            self.assertEqual([p.name for p in ecrits], ["01-A-1.ics"])
            self.assertEqual(sorted(p.name for p in (dossier / "2026-10-23").glob("*.ics")), ["01-A-1.ics"])
            self.assertIn("DTSTART:20261023T113000", ecrits[0].read_text(encoding="utf-8"))
            self.assertEqual(list((dossier / "2026-10-23").glob("*.tmp")), [])

    def test_dossier_voisin_de_journees(self):
        self.assertEqual(dossier_calendrier(Path("/d/40002/journees/journee-2026-10-23.json")),
                         Path("/d/40002/calendrier"))
        self.assertEqual(dossier_calendrier(Path("/tmp/x/journee-2026-10-23.json")),
                         Path("/tmp/x/calendrier"))

    def test_accroche_parser_save(self):
        from parse_journee import JourneeParser
        brut = (ROOT / "tests" / "cas_journee" / "440-continu-id-duplique.txt").read_text(encoding="utf-8")
        parser = JourneeParser(brut, date_str="2026-08-22")
        journee_ = parser.parse()
        with tempfile.TemporaryDirectory() as tmp:
            ancien, JourneeParser.JOURNEES_DIR = JourneeParser.JOURNEES_DIR, Path(tmp)
            try:
                parser.save(journee_)
            finally:
                JourneeParser.JOURNEES_DIR = ancien
            ics = sorted((Path(tmp) / "calendrier" / "2026-08-22").glob("*.ics"))
            self.assertEqual(len(ics), len(evenements_ics(journee_)))
            self.assertGreaterEqual(len(ics), 1)
            self.assertIn("📅", parser.get_summary(journee_, Path(tmp) / "journee-2026-08-22.json"))
            self.assertEqual(parser.erreur_calendrier, "")


if __name__ == "__main__":
    resultat = unittest.main(exit=False, verbosity=0).result
    sys.exit(0 if resultat.wasSuccessful() else 1)
