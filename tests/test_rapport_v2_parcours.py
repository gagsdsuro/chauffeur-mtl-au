#!/usr/bin/env python3
"""
test_rapport_v2_parcours.py — Rapport v2 : sélection par parcours, détours
évalués par départ, détails des évènements à avertissement.

Hermétique : G-D, GTFS et évènements sont substitués par des données
synthétiques (module `gen_rapport_v2` patché), la journée est écrite en
répertoire temporaire. Couvre :
  • évènements identiques à tous les départs → une seule section (format actuel) ;
  • évènement à plage horaire (commentaire « LUNDI AU VENDREDI 12H00 À 19H00 »)
    → parcours dupliqué, annotations distinctes sans fuite d'état ;
  • sélection : niveau par parcours, exclusion, tout exclu, parcours inconnu ;
  • sommaire : un évènement à avertissement détaille arrêts, commentaire et
    description G-D (HTML et PDF) ; un évènement sans avertissement reste compact ;
  • format CLI `--parcours`.

Usage : python3 tests/test_rapport_v2_parcours.py   (code de sortie 0 si tout passe)
"""
import argparse
import json
import sys
import tempfile
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gen_rapport_v2 as v2  # noqa: E402
from chauffeur.gd import build_rows  # noqa: E402

JOUR = "2026-11-09"   # lundi
INSTR = ["Via - Alpha", "Droite - Beta", "Gauche - Gamma"]
NOMS = {
    "1": {"code": "1", "name": "Alpha / Delta"},
    "2": {"code": "2", "name": "Beta / Epsilon"},
    "3": {"code": "3", "name": "Beta / Zeta"},
    "4": {"code": "4", "name": "Gamma / Eta"},
}
STOPS = [(1, "1"), (2, "2"), (3, "3"), (4, "4")]
PARCOURS = {"id": 1, "name": "Parcours test", "start": "Alpha", "end": "Gamma",
            "direction": INSTR}

# Annule l'arrêt 2 seulement de 12h à 19h, du lundi au vendredi (dans le commentaire).
EV_PLAGE = {
    "evenement_id": "100", "titre": "Annulation d'arrêts", "motif": "Travaux",
    "effectif": "En tout temps", "date_heure_debut": "2026-09-02T12:00:00",
    "date_heure_fin": "2026-12-31T19:00:00",
    "arrets_annules": [{"id": "2", "nom": "Beta / Epsilon"}],
    "arrets_ajoutes": [], "commentaire": "LUNDI AU VENDREDI 12H00 À 19H00",
    "description_gd": None,
}
# Texte libre illisible : le pipeline ne sait pas le placer → avertissement.
EV_ILLISIBLE = {
    "evenement_id": "200", "titre": "Détour sans annulation", "motif": "Travaux",
    "effectif": "En tout temps", "date_heure_debut": "2026-09-02T12:00:00",
    "date_heure_fin": None, "arrets_annules": [],
    "arrets_ajoutes": [{"id": "9", "nom": "Temporaire / X"}],
    "commentaire": "Attention au camion", "description_gd": "Faire demi-tour au bout",
}
# Évènement de plusieurs jours, bien placé, sans avertissement.
EV_SIMPLE = {
    "evenement_id": "300", "titre": "Annulation d'arrêts", "motif": "Travaux",
    "effectif": "En tout temps", "date_heure_debut": "2026-09-02T12:00:00",
    "date_heure_fin": None, "arrets_annules": [{"id": "3", "nom": "Beta / Zeta"}],
    "arrets_ajoutes": [], "commentaire": "Note", "description_gd": None,
}


def _trajet(ligne, direction, id_p, dep, arr):
    return {"type": "service", "ligne": ligne, "direction": direction,
            "id_parcours": id_p, "depart": {"heure": dep}, "arrivee": {"heure": arr}}


def _journee():
    return {"date": JOUR, "garage": "G", "garage_id": "1", "journee_numero": "1",
            "temps_travaille": "8:00", "pieces": [{"id": "p", "trajets": [
                _trajet("ZZ", "nord", 1, "9:37", "10:29"),
                _trajet("ZZ", "nord", 1, "16:55", "17:59"),
                _trajet("YY", "sud", 2, "11:00", "11:40"),
                _trajet("XX", "est", 3, "11:00", "11:40"),
            ]}]}


class Contexte:
    """Substitue G-D, GTFS et évènements de gen_rapport_v2."""

    def __init__(self, evenements):
        self.evenements = evenements
        self.pile = ExitStack()

    def __enter__(self):
        self.tmp = Path(self.pile.enter_context(tempfile.TemporaryDirectory()))
        (self.tmp / "rapports").mkdir()
        self.chemin = self.tmp / f"journee-{JOUR}.json"
        self.chemin.write_text(json.dumps(_journee()), encoding="utf-8")
        for attr, val in (
            ("charger_gd", lambda l, d, i=None: (INSTR, PARCOURS)),
            ("_load_gtfs_stops", lambda l, d, i=None: (STOPS, NOMS)),
            ("appariement_pour_rapport",
             lambda l, d, p, s, n: (build_rows(INSTR, s, n),
                                    {"statut": "auto", "blocs": 0, "a_jour": True})),
            ("evenements_pour_date", lambda l, d, j: list(self.evenements)),
            ("fournisseurs_detours", lambda l, d: (lambda e: None, lambda e: None)),
            ("OUTPUT_DIR", self.tmp / "rapports"),
        ):
            self.pile.enter_context(patch.object(v2, attr, val))
        return self

    def __exit__(self, *exc):
        self.pile.close()

    def rapport(self, fmt="html", **kw):
        out = self.tmp / f"r.{fmt}"
        v2.generer_rapport(self.chemin, fmt=fmt, output=out, **kw)
        return out.read_bytes() if fmt == "pdf" else out.read_text(encoding="utf-8")


def _groupe(trips):
    return {"ligne": "ZZ", "direction": "nord", "id_parcours": 1, "trips": trips}


def _annules(gd):
    return [r["stop_id"] for r in gd["rows"] if r.get("cancelled")]


def un_seul_parcours_si_memes_evenements():
    erreurs = []
    with Contexte([EV_SIMPLE]) as c:
        res = v2.process_groupe(_groupe([
            {"depart_heure": "9:37", "arrivee_heure": "10:29"},
            {"depart_heure": "16:55", "arrivee_heure": "17:59"}]), JOUR, {})
        if len(res) != 1 or "variante" in res[0]["groupe"]:
            erreurs.append(f"évènements identiques : {len(res)} sections, variante={res[0]['groupe'].get('variante')}")
        html = c.rapport()
        if "Parcours dupliqué" in html:
            erreurs.append("note de duplication affichée sans duplication")
    return erreurs


def parcours_duplique_selon_l_heure():
    erreurs = []
    trips = [{"depart_heure": "9:37", "arrivee_heure": "10:29"},
             {"depart_heure": "16:55", "arrivee_heure": "17:59"}]
    with Contexte([EV_PLAGE]) as c:
        res = v2.process_groupe(_groupe(trips), JOUR, {})
        if len(res) != 2:
            return [f"2 variantes attendues, obtenu {len(res)}"]
        tot, tard = res
        if [t["depart_heure"] for t in tot["groupe"]["trips"]] != ["9:37"] or \
           [t["depart_heure"] for t in tard["groupe"]["trips"]] != ["16:55"]:
            erreurs.append("trajets mal répartis entre variantes")
        if (tot["groupe"]["variante"], tard["groupe"]["variante"]) != ((1, 2), (2, 2)):
            erreurs.append("numérotation des variantes")
        if _annules(tot) != [] or _annules(tard) != ["2"]:
            erreurs.append(f"annotations : matin {_annules(tot)}, après-midi {_annules(tard)}")
        if tot["events"] or [e["evenement_id"] for e in tard["events"]] != ["100"]:
            erreurs.append("évènements applicables par variante")
        # Le tableau des évènements est commun, le marqueur ✅/⬜ ne l'est pas.
        if tot["events_all"] != tard["events_all"]:
            erreurs.append("events_all devrait être commun")
        html = c.rapport()
        if html.count("Parcours dupliqué") != 2 or "(1/2)" not in html or "(2/2)" not in html:
            erreurs.append("note de duplication absente du HTML")
        if html.count("<h2>") != 4:   # ZZ ×2 + YY + XX
            erreurs.append(f"{html.count('<h2>')} sections <h2>, attendu 4")
        if not c.rapport("pdf").startswith(b"%PDF"):
            erreurs.append("PDF invalide")
    return erreurs


def selection_par_parcours():
    erreurs = []
    with Contexte([EV_SIMPLE]) as c:
        html = c.rapport(niveau="détaillé", selection={
            ("zz", "nord", 1): "compact", ("YY", "sud", 2): None})
        noms = [t.split("</h2>")[0] for t in html.split("<h2>")[1:]]
        if noms != ["ZZ Nord — ID 1 — compact", "XX Est — ID 3 — détaillé"]:
            erreurs.append(f"sections : {noms}")
        if "Niveau : par parcours" not in html:
            erreurs.append("en-tête « par parcours » absent")
        # Niveau uniforme : en-tête inchangé, pas de niveau dans les titres.
        html = c.rapport(niveau="standard")
        if "Niveau : standard" not in html or " — standard</h2>" in html:
            erreurs.append("rapport uniforme : en-tête modifié")
        for sel, attendu in (
            ({k: None for k in (("ZZ", "nord", 1), ("YY", "sud", 2), ("XX", "est", 3))},
             "Aucun parcours"),
            ({("ZZ", "nord", 99): "compact"}, "absent de la journée"),
            ({("ZZ", "nord", 1): "bavard"}, "Niveau inconnu"),
        ):
            try:
                c.rapport(selection=sel)
                erreurs.append(f"ValueError attendue ({attendu})")
            except ValueError as e:
                if attendu not in str(e):
                    erreurs.append(f"message {e!r}, attendu « {attendu} »")
        # Sélection personnalisée ou non (nom de fichier / marquage « à jour »).
        g = v2.groupes_de_service(_journee(), avec_trips=True)
        if v2.selection_est_personnalisee(g, "détaillé", {("zz", "nord", 1): "détaillé"}):
            erreurs.append("niveau explicite égal au défaut ≠ personnalisé")
        if not v2.selection_est_personnalisee(g, "détaillé", {("ZZ", "nord", 1): "compact"}):
            erreurs.append("niveau distinct → personnalisé")
        if not v2.selection_est_personnalisee(g, "détaillé", {("ZZ", "nord", 1): None}):
            erreurs.append("exclusion → personnalisé")
    return erreurs


def sommaire_detaille_les_evenements_a_avertissement():
    erreurs = []
    with Contexte([EV_ILLISIBLE, EV_SIMPLE]) as c:
        res = v2.process_groupe(_groupe([{"depart_heure": "9:37",
                                          "arrivee_heure": "10:29"}]), JOUR, {})[0]
        if not any(str(d["evenement_id"]) == "200" for d in res["diagnostics"]):
            return [f"diagnostic attendu pour 200, obtenu {res['diagnostics']}"]
        html = v2._render_events_table_html(res["events_all"], res["events"],
                                            res["diagnostics"])
        for attendu in ("Commentaire : Attention au camion",
                        "Description G-D : Faire demi-tour au bout",
                        "Arrêts ajoutés : 9 — Temporaire / X", "description G-D illisible"):
            if attendu not in html:
                erreurs.append(f"HTML : « {attendu} » absent")
        # L'évènement sans avertissement reste compact.
        ligne_300 = next(l for l in html.split("<tr") if ">300<" in l)
        if "ev-detail" in ligne_300:
            erreurs.append("évènement 300 : détails affichés sans avertissement")
        # Évènement sans info exploitable : aucune ligne vide.
        vide = dict(EV_ILLISIBLE, commentaire=None, description_gd=None, arrets_ajoutes=[])
        lignes = v2._details_evenement(vide, [{"evenement_id": "200", "type": "x"}])
        if any(not l.strip() or l.endswith(": ") for l in lignes):
            erreurs.append(f"lignes vides : {lignes}")
        # PDF : mêmes données, sans exception (texte échappé, « ⚠ » retiré).
        if not c.rapport("pdf").startswith(b"%PDF"):
            erreurs.append("PDF invalide")
    return erreurs


def format_cli_parcours():
    erreurs = []
    if v2._parser_parcours("24:ouest:2=compact") != (("24", "ouest", 2), "compact"):
        erreurs.append("24:ouest:2=compact")
    if v2._parser_parcours("445:ouest:19=aucun") != (("445", "ouest", 19), None):
        erreurs.append("aucun → None")
    for mauvais in ("24:ouest=compact", "24:ouest:x=compact", "24:ouest:2=bavard", "24:ouest:2"):
        try:
            v2._parser_parcours(mauvais)
            erreurs.append(f"{mauvais!r} devrait être refusé")
        except argparse.ArgumentTypeError:
            pass
    return erreurs


TESTS = [un_seul_parcours_si_memes_evenements, parcours_duplique_selon_l_heure,
         selection_par_parcours, sommaire_detaille_les_evenements_a_avertissement,
         format_cli_parcours]


def main() -> int:
    echecs = 0
    for test in TESTS:
        erreurs = test()
        print(("✅" if not erreurs else "❌") + f" {test.__name__}")
        for e in erreurs:
            print("   ", e)
        echecs += bool(erreurs)
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
