#!/usr/bin/env python3
"""Isolation du cookie lors d'une validation du dialogue sur un autre thread."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.components import session_dialog as dialogue
from chauffeur import depots, portail


class TestDialogueSession(unittest.TestCase):
    def test_validation_sans_contexte_thread_conserve_le_compte(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for matricule in ("41001", "41002"):
                with self.subTest(matricule=matricule):
                    ui = MagicMock()
                    ui.session_state = {
                        dialogue.OUVRIR_DIALOG_SESSION: True,
                        dialogue.OPERATION_PORTAIL: {"reprendre": False},
                    }
                    ui.text_input.return_value = "cookie=factice"
                    confirmer, annuler = MagicMock(), MagicMock()
                    confirmer.button.return_value = True
                    annuler.button.return_value = False
                    ui.columns.return_value = (confirmer, annuler)
                    fonction = dialogue._dialog_session_portail.__wrapped__
                    with patch.object(depots, "DATA_DIR", base), \
                         patch.object(dialogue, "st", ui), \
                         patch.object(dialogue, "_dialog_session_portail") as ouvrir:
                        with depots.contexte_matricule(matricule):
                            dialogue.declencher_dialog_si_requis()
                        args = ouvrir.call_args.args

                    def valider(cookie, session_path=None):
                        self.assertIsNone(depots.matricule_contexte())
                        self.assertEqual(session_path, base / matricule / "session/cookies.json")
                        portail.save_session(cookie, session_path)
                        return True, "Session validée"

                    with patch.object(dialogue, "st", ui), \
                         patch.object(dialogue, "valider_et_sauvegarder_session", side_effect=valider), \
                         ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(fonction, *args).result()
                    self.assertTrue((base / matricule / "session/cookies.json").exists())
                    self.assertFalse((base / "session/cookies.json").exists())
                    self.assertTrue(ui.session_state[dialogue.OPERATION_PORTAIL]["reprendre"])
                    ui.rerun.assert_called_once()


if __name__ == "__main__":
    unittest.main()
