#!/usr/bin/env python3
"""Tests de la préparation, de la reprise et des empreintes de rapports."""

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import chauffeur.preparation as preparation  # noqa: E402
from chauffeur.depots import lister_journees_fenetre  # noqa: E402
from chauffeur.portail import SessionExpiredError  # noqa: E402


JOURNEE = {
    "date": "2026-09-02",
    "pieces": [{
        "fin": "18:00",
        "trajets": [
            {"type": "service", "ligne": "24", "direction": "est", "id_parcours": 1},
            {"type": "service", "ligne": "24", "direction": "ouest", "id_parcours": 1},
        ],
    }],
}


class ClientFaux:
    def verifier(self):
        return None


class ClientImportFaux(ClientFaux):
    def __init__(self, *, journee=None, gd=None):
        self.journee = journee
        self.gd = gd

    def fetch_journee(self, _):
        return self.journee

    def fetch_gd(self, _, __):
        return self.gd


def main() -> int:
    echecs = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jours = root / "journees"
        jours.mkdir()
        for valeur in ("2026-08-30", "2026-08-31", "2026-09-01", "2026-09-06", "2026-09-07"):
            (jours / f"journee-{valeur}.json").write_text("{}", encoding="utf-8")
        fenetre = [jour.isoformat() for jour, _ in lister_journees_fenetre(
            date(2026, 9, 1), journees_dir=jours
        )]
        if fenetre != ["2026-08-30", "2026-08-31", "2026-09-01", "2026-09-06"]:
            echecs.append(f"fenêtre J-2/J+5 incorrecte: {fenetre}")
        changements = preparation._decrire_changements(
            [
                {"evenement_id": "1", "titre": "Retiré"},
                {"evenement_id": "2", "titre": "Avant"},
            ],
            [
                {"evenement_id": "2", "titre": "Après"},
                {"evenement_id": "3", "titre": "Nouveau"},
            ],
        )
        if changements != [
            "Nouveau #3 — Nouveau", "Retiré #1 — Retiré", "Modifié #2"
        ]:
            echecs.append(f"résumé des changements incorrect: {changements}")

        journee_path = root / "journee-2026-09-02.json"
        journee_path.write_text(json.dumps(JOURNEE), encoding="utf-8")
        gd = root / "gd"
        ev = root / "events"
        gtfs = root / "gtfs" / "gtfs_stm"
        rapports = root / "rapports"
        gd.mkdir(); ev.mkdir(); gtfs.mkdir(parents=True)
        for direction in ("est", "ouest"):
            (gd / f"gd24_{direction}.json").write_text(
                json.dumps({"direction": direction}), encoding="utf-8"
            )
            (ev / f"24_{direction}.json").write_text(
                json.dumps({"detours": []}), encoding="utf-8"
            )
        manifeste_gtfs = root / "gtfs" / "gtfs_manifest.json"
        manifeste_gtfs.write_text('{"gtfs_sha256":"abc"}', encoding="utf-8")

        originaux = (
            preparation.EVENTS_DIR, preparation.GTFS_DIR, preparation.GTFS_MANIFEST,
            preparation.chemin_gd, preparation.chemin_evenements,
        )
        preparation.EVENTS_DIR = ev
        preparation.GTFS_DIR = gtfs
        preparation.GTFS_MANIFEST = manifeste_gtfs
        preparation.chemin_gd = lambda l, d: gd / f"gd{l}_{d}.json"
        preparation.chemin_evenements = lambda l, d: ev / f"{l}_{d}.json"
        appels = {"journalier": 0, "v2": 0}

        def gen_j(_, output):
            appels["journalier"] += 1
            output.write_bytes(b"pdf")
            return True, "ok"

        def gen_v2(_, output, niveau):
            appels["v2"] += 1
            output.write_text(niveau, encoding="utf-8")
            return True, "ok"

        try:
            preparation.finaliser_rapports(
                journee_path, rapports_dir=rapports,
                generateur_journalier=gen_j, generateur_v2=gen_v2,
            )
            preparation.finaliser_rapports(
                journee_path, rapports_dir=rapports,
                generateur_journalier=gen_j, generateur_v2=gen_v2,
            )
            if appels != {"journalier": 1, "v2": 1}:
                echecs.append(f"rapports inchangés régénérés: {appels}")

            # Une réécriture byte-identique ne change pas l'empreinte.
            contenu = json.loads(journee_path.read_text(encoding="utf-8"))
            journee_path.write_text(
                json.dumps(contenu, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            preparation.finaliser_rapports(
                journee_path, rapports_dir=rapports,
                generateur_journalier=gen_j, generateur_v2=gen_v2,
            )
            if appels != {"journalier": 1, "v2": 1}:
                echecs.append("réimport identique considéré comme une modification")

            data = json.loads(journee_path.read_text(encoding="utf-8"))
            data["garage"] = "Frontenac"
            journee_path.write_text(json.dumps(data), encoding="utf-8")
            preparation.finaliser_rapports(
                journee_path, rapports_dir=rapports,
                generateur_journalier=gen_j, generateur_v2=gen_v2,
            )
            if appels != {"journalier": 2, "v2": 2}:
                echecs.append("modification de journée non détectée")
        finally:
            (
                preparation.EVENTS_DIR, preparation.GTFS_DIR, preparation.GTFS_MANIFEST,
                preparation.chemin_gd, preparation.chemin_evenements,
            ) = originaux

        # Expiration au milieu du lot puis reprise des seules lignes restantes.
        original_traiter = preparation._traiter_ligne
        vus = []
        expiration = {"faite": False}

        def traiter(_, ligne, direction, log):
            vus.append((ligne, direction))
            if direction == "ouest" and not expiration["faite"]:
                expiration["faite"] = True
                raise SessionExpiredError("expirée")
            return preparation.ResultatLigneEvenements(ligne, direction, True, direction == "est")

        preparation._traiter_ligne = traiter
        try:
            premier = preparation.rafraichir_evenements_journee(
                JOURNEE, client=ClientFaux(), log=False
            )
            second = preparation.rafraichir_evenements_journee(
                JOURNEE, paires=premier.restantes, client=ClientFaux(), log=False
            )
            total = preparation.fusionner_rafraichissements(premier, second)
            if not total.succes_complet or not total.modifie:
                echecs.append("reprise partielle non agrégée")
            if vus != [("24", "est"), ("24", "ouest"), ("24", "ouest")]:
                echecs.append(f"lignes retraitées pendant la reprise: {vus}")
        finally:
            preparation._traiter_ligne = original_traiter

        # Import automatique d'une journée HTML puis d'un G-D HTML.
        brut = (ROOT / "tests" / "cas_journee" / "440-continu-id-duplique.txt").read_text(
            encoding="utf-8"
        )
        sommaire, details = brut.split("Détails 136 - 01", 1)
        en_html = lambda texte: "".join(
            f"<div>{ligne}</div>" for ligne in texte.splitlines() if ligne
        )
        payload_journee = {
            "date": "2026-08-22",
            "journeeHtml": en_html(sommaire),
            "voyagesHtml": en_html("Détails 136 - 01\n" + details),
        }
        original_chemin_journee = preparation.chemin_journee
        preparation.chemin_journee = lambda d: root / f"journee-{d}.json"
        try:
            imp = preparation.importer_journee_portail(
                "2026-08-22", client=ClientImportFaux(journee=payload_journee), log=False
            )
            if not imp.succes or not imp.modifie or imp.chemin is None:
                echecs.append(f"import journée portail échoué: {imp}")
            else:
                chargee = json.loads(imp.chemin.read_text(encoding="utf-8"))
                if [p.get("type_horaire") for p in chargee["pieces"]] != [
                    "horaire", "horaire", "continu"
                ]:
                    echecs.append("import journée: pièce continue non conservée")
                if not imp.calendrier or not all(c.exists() for c in imp.calendrier):
                    echecs.append("import journée: fichiers .ics non générés")
                if "📅" not in imp.message:
                    echecs.append("import journée: résumé sans ligne calendrier")
        finally:
            preparation.chemin_journee = original_chemin_journee

        payload_gd = {"html": """
          <h2>Gauche-Droite / 24 Est</h2>
          <div id="leftright-panel">{"content":[{"text":"G - pollution"}]}</div>
          <ol><li>
            <span>Parcours principal</span><span>ID 24</span>
            <span>Date de mise à jour: 2026-09-03 12:45:15</span>
            <span>Station Villa-Maria</span><span>51241</span>
            <span>Via - Terminus Villa-Maria</span><span>Gauche - Décarie</span>
            <span>Montgomery / Sherbrooke</span><span>52819</span>
          </li></ol>
        """}
        original_gd_dir = preparation.GD_DIR
        preparation.GD_DIR = root / "gd-auto"
        try:
            resultat_gd = preparation.rafraichir_gd_journee(
                JOURNEE,
                paires=[("24", "est")],
                client=ClientImportFaux(gd=payload_gd),
                log=False,
            )
            if not resultat_gd.succes_complet or not resultat_gd.modifie:
                echecs.append(f"import G-D portail échoué: {resultat_gd}")
            elif not (preparation.GD_DIR / "gd24_est.json").exists():
                echecs.append("import G-D: fichier attendu absent")
        finally:
            preparation.GD_DIR = original_gd_dir

    if echecs:
        print("✗ test_preparation")
        for erreur in echecs:
            print(f"    {erreur}")
        return 1
    print("✓ préparation (fenêtre, imports portail, empreintes, reprise)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
