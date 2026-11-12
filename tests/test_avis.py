#!/usr/bin/env python3
"""Tests des mentions d'avis et d'attribution (chauffeur.avis, rapport v2, NOTICE)."""
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

from chauffeur import avis  # noqa: E402
import gen_rapport_v2 as v2  # noqa: E402


class TestAvis(unittest.TestCase):
    def test_attribution_cc_by_exigee(self):
        self.assertIn("Société de transport de Montréal", avis.ATTRIBUTION)
        self.assertIn("CC BY 4.0", avis.ATTRIBUTION)
        self.assertIn(avis.URL_DONNEES_OUVERTES, avis.ATTRIBUTION)
        self.assertIn("non cautionné", avis.ATTRIBUTION)

    def test_responsabilite_portail(self):
        self.assertIn("employe.stm.info", avis.AVIS_PORTAIL)
        self.assertIn("responsable", avis.AVIS_PORTAIL)

    def test_rapport_html_porte_l_avis(self):
        page = v2.render_html([], {"date": "2026-01-05"}, "standard", False)
        self.assertIn(v2._h(avis.AVIS_RAPPORT), page)

    def test_notice_reprend_l_attribution(self):
        notice = (RACINE / "NOTICE.md").read_text(encoding="utf-8")
        self.assertIn(avis.ATTRIBUTION, notice)


if __name__ == "__main__":
    unittest.main()
