#!/usr/bin/env python3
"""Tests de l'orchestrateur de préparation semi-automatique (sans réseau ni interface)."""

import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import chauffeur.preparation_auto as auto  # noqa: E402
from chauffeur.ca import ResultatCA  # noqa: E402
from chauffeur.portail import PortailError  # noqa: E402
from chauffeur.preparation import (  # noqa: E402
    ResultatImportationJournee, ResultatLigneEvenements, ResultatLigneGD,
    ResultatRafraichissement, ResultatRafraichissementGD, ResultatRapport,
)

DATE = "2026-11-09"
JOURNEE = {
    "date": DATE,
    "journee_numero": 461,
    "pieces": [{
        "id": "461-01", "debut": "05:00", "fin": "13:00",
        "trajets": [
            {"type": "service", "ligne": "24", "direction": "est", "id_parcours": 1},
            {"type": "service", "ligne": "24", "direction": "ouest", "id_parcours": 1},
        ],
    }],
}
JOURNEE_ABSENCE = {"date": DATE, "journee_numero": 461, "pieces": []}


class ClientFaux:
    def __init__(self, erreur=None):
        self.erreur = erreur
        self.appels = 0

    def fetch_carte_agent(self, _):
        self.appels += 1
        if self.erreur:
            raise self.erreur
        return b"%PDF-1.7"


class Scenario:
    """Fonctions du module patchées ; chaque réglage est modifiable par test."""

    def __init__(self, tmp: Path, journee=JOURNEE):
        self.chemin = tmp / f"journee-{DATE}.json"
        self.journee = journee
        self.import_journee = lambda: ResultatImportationJournee(
            True, DATE, modifie=True, message="résumé", chemin=self.chemin,
            calendrier=[tmp / "01-461-01.ics"],
        )
        self.ca_presente = False
        self.ca_resultat = ResultatCA("ok", "Carte annotée et rangée.")
        self.gd_existent = {"24": True}
        self.gd_frais = False
        self.gd_resultat = lambda: ResultatRafraichissementGD(
            lignes=[ResultatLigneGD("24", "est", True), ResultatLigneGD("24", "ouest", True)]
        )
        self.ev_resultat = lambda paires: ResultatRafraichissement(
            lignes=[ResultatLigneEvenements("24", "est", True), ResultatLigneEvenements("24", "ouest", True)]
        )
        self.rapport = ResultatRapport("v2", "genere", "ok")
        self.appels: list[str] = []
        self.paires_evenements = None
        self.variantes = None

    def installer(self):
        s = self

        def importer(date_str, client=None, log=True):
            s.appels.append("journee")
            res = s.import_journee()
            if res.succes:
                s.chemin.write_text(json.dumps(s.journee), encoding="utf-8")
            return res

        def resoudre(jour, numero):
            return {"annotee": Path("x.pdf") if s.ca_presente else None, "brute": None}

        def annoter(pdf, jour, **kw):
            s.appels.append("annoter")
            return s.ca_resultat

        def info(ligne, direction):
            return {"exists": s.gd_existent.get(ligne, False), "fresh": s.gd_frais}

        def gd(journee, client=None, **kw):
            s.appels.append("gd")
            res = s.gd_resultat()
            if not res.session_expiree:
                s.gd_frais = True
            return res

        def ev(journee, paires=None, client=None, **kw):
            s.appels.append("evenements")
            s.paires_evenements = paires
            return s.ev_resultat(paires)

        def finaliser(chemin, **kw):
            s.appels.append("rapport")
            s.variantes = kw.get("variantes")
            return [s.rapport]

        return {
            "importer_journee_portail": importer, "resoudre_ca": resoudre,
            "annoter_et_ranger_ca": annoter, "info_gd": info,
            "rafraichir_gd_journee": gd, "rafraichir_evenements_journee": ev,
            "finaliser_rapports": finaliser, "chemin_journee": lambda _: s.chemin,
            "ecrire_calendrier_sans_echec": lambda j, d: ([], "erreur d'écriture"),
        }


@contextmanager
def patcher(scenario):
    remplacements = scenario.installer()
    originaux = {nom: getattr(auto, nom) for nom in remplacements}
    for nom, valeur in remplacements.items():
        setattr(auto, nom, valeur)
    try:
        yield
    finally:
        for nom, valeur in originaux.items():
            setattr(auto, nom, valeur)


def lancer(scenario, **kw):
    kw.setdefault("client", ClientFaux())
    with patcher(scenario):
        return auto.executer_semi_auto(DATE, **kw)


def statuts(res):
    return {e.etape: e.statut for e in res.etapes}


def main() -> int:
    echecs = []

    def check(cond, msg):
        if not cond:
            echecs.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # ── 1. enchaînement nominal ──────────────────────────────────────────
        s = Scenario(tmp)
        evts = []
        res = lancer(s, progression=lambda e, st, m: evts.append((e, st)))
        check(res.termine and res.reprise_a is None, f"nominal: chaîne terminée attendue : {res}")
        check([e.etape for e in res.etapes] == list(auto.ETAPES),
              f"nominal: ordre des étapes inattendu : {[e.etape for e in res.etapes]}")
        check(statuts(res) == {
            "journee": "ok", "calendrier": "ok", "carte_agent": "ok",
            "gauche_droite": "ok", "evenements": "ok", "rapport_v2": "ok",
        }, f"nominal: statuts inattendus : {statuts(res)}")
        check(s.appels == ["journee", "annoter", "gd", "evenements", "rapport"],
              f"nominal: appels dans le mauvais ordre : {s.appels}")
        check(s.variantes == ("v2",), f"nominal: seul le rapport v2 doit être demandé : {s.variantes}")
        check(evts[0] == ("journee", "demarre") and evts[-1] == ("rapport_v2", "ok"),
              f"nominal: rappels de progression inattendus : {evts}")
        check(not res.avertissements and not res.bloque, "nominal: ni avertissement ni blocage")

        # ── 2. échec de la journée : arrêt immédiat ─────────────────────────
        s = Scenario(tmp)
        s.import_journee = lambda: ResultatImportationJournee(False, DATE, message="Échec du parsing\ndétail")
        res = lancer(s)
        check(res.reprise_a == "journee" and res.bloque and len(res.etapes) == 1,
              f"journée KO: arrêt à la première étape attendu : {res}")
        check(s.appels == ["journee"], f"journée KO: aucune étape suivante : {s.appels}")

        # ── 3. session expirée à l'étape G-D, puis reprise ───────────────────
        s = Scenario(tmp)
        s.gd_resultat = lambda: ResultatRafraichissementGD(
            restantes=[("24", "est"), ("24", "ouest")], session_expiree=True
        )
        res = lancer(s)
        check(res.reprise_a == "gauche_droite" and res.session_expiree,
              f"session G-D: reprise à gauche_droite attendue : {res.reprise_a}")
        check(statuts(res).get("gauche_droite") == "session_expiree", "session G-D: statut attendu")
        check("evenements" not in statuts(res), "session G-D: les étapes suivantes ne doivent pas tourner")
        copie = auto.ResultatSemiAuto.from_dict(json.loads(json.dumps(res.to_dict())))
        check(copie == res, "sérialisation: from_dict(to_dict) doit redonner le même résultat")
        s.gd_resultat = lambda: ResultatRafraichissementGD(
            lignes=[ResultatLigneGD("24", "est", True), ResultatLigneGD("24", "ouest", True)]
        )
        s.appels.clear()
        res2 = lancer(s, precedent=copie)
        check(res2.termine and "journee" not in s.appels,
              f"reprise G-D: la journée ne doit pas être réimportée : {s.appels}")
        check([e.etape for e in res2.etapes] == list(auto.ETAPES), "reprise G-D: toutes les étapes attendues")

        # ── 4. G-D toujours manquants : bloquant ─────────────────────────────
        s = Scenario(tmp)
        s.gd_existent = {}
        s.gd_resultat = lambda: ResultatRafraichissementGD(
            lignes=[ResultatLigneGD("24", "est", False, message="❌ erreur")]
        )
        res = lancer(s)
        check(res.bloque and res.reprise_a == "gauche_droite" and "evenements" not in statuts(res),
              f"G-D manquants: blocage attendu : {statuts(res)}")

        # ── 5. G-D déjà frais : étape ignorée sans appel réseau ──────────────
        s = Scenario(tmp)
        s.gd_frais = True
        res = lancer(s)
        check(statuts(res)["gauche_droite"] == "ignore" and "gd" not in s.appels,
              f"G-D frais: étape ignorée attendue : {statuts(res)}")

        # ── 6. carte agent : déjà présente / échec portail / échec annotation ─
        s = Scenario(tmp)
        s.ca_presente = True
        client = ClientFaux()
        res = lancer(s, client=client)
        check(statuts(res)["carte_agent"] == "ignore" and client.appels == 0,
              "carte présente: aucune récupération attendue")

        s = Scenario(tmp)
        client = ClientFaux(PortailError("Aucune carte agent publiée"))
        res = lancer(s, client=client)
        check(statuts(res)["carte_agent"] == "avertissement" and res.termine,
              f"carte introuvable: avertissement et suite attendus : {statuts(res)}")

        s = Scenario(tmp)
        s.ca_resultat = ResultatCA("erreur", "Numéro de carte illisible.")
        res = lancer(s)
        check(statuts(res)["carte_agent"] == "avertissement" and res.termine
              and statuts(res)["rapport_v2"] == "ok",
              "annotation KO: avertissement et suite attendus")

        s = Scenario(tmp)
        s.ca_resultat = None   # provoque une exception inattendue dans l'étape
        res = lancer(s)
        check(statuts(res)["carte_agent"] == "avertissement" and res.termine,
              f"exception inattendue en carte agent: avertissement et suite attendus : {statuts(res)}")

        # ── 7. évènements en échec : avertissement, rapport quand même généré ─
        s = Scenario(tmp)
        s.ev_resultat = lambda p: ResultatRafraichissement(
            lignes=[ResultatLigneEvenements("24", "est", False, message="HTTP 500")]
        )
        res = lancer(s)
        check(statuts(res)["evenements"] == "avertissement" and statuts(res)["rapport_v2"] == "ok"
              and res.termine, f"évènements KO: avertissement et rapport attendus : {statuts(res)}")
        check(len(res.avertissements) == 1, "évènements KO: un seul avertissement attendu")

        # ── 8. évènements : session expirée, reprise fusionnée, sans_portail ─
        s = Scenario(tmp)
        s.ev_resultat = lambda p: ResultatRafraichissement(
            lignes=[ResultatLigneEvenements("24", "est", True)],
            restantes=[("24", "ouest")], session_expiree=True,
        )
        res = lancer(s)
        check(res.reprise_a == "evenements" and res.etape("evenements").restantes == [("24", "ouest")],
              "évènements: reprise sur les lignes restantes attendue")
        precedent = auto.ResultatSemiAuto.from_dict(json.loads(json.dumps(res.to_dict())))

        s2 = Scenario(tmp)
        s2.ev_resultat = lambda p: ResultatRafraichissement(
            lignes=[ResultatLigneEvenements("24", "ouest", True)]
        )
        res2 = lancer(s2, precedent=precedent)
        check(s2.paires_evenements == [("24", "ouest")],
              f"reprise évènements: seules les lignes restantes attendues : {s2.paires_evenements}")
        check(res2.termine and statuts(res2)["evenements"] == "ok"
              and len(res2.etape("evenements").details) == 2,
              f"reprise évènements: résultats fusionnés attendus : {res2.etape('evenements')}")

        s3 = Scenario(tmp)
        s3.appels.clear()
        res3 = lancer(s3, precedent=precedent, sans_portail=True)
        check(statuts(res3)["evenements"] == "avertissement" and res3.termine
              and "evenements" not in s3.appels,
              "sans_portail: avertissement sans appel au portail, chaîne terminée")

        # ── 9. rapport v2 impossible : bloquant ──────────────────────────────
        s = Scenario(tmp)
        s.rapport = ResultatRapport("v2", "bloque", "GTFS statique absent")
        res = lancer(s)
        check(res.bloque and res.reprise_a == "rapport_v2", f"GTFS absent: blocage attendu : {statuts(res)}")

        # ── 10. journée sans pièce de travail ────────────────────────────────
        s = Scenario(tmp, journee=JOURNEE_ABSENCE)
        client = ClientFaux()
        res = lancer(s, client=client)
        check(res.termine and statuts(res) == {
            "journee": "ok", "calendrier": "ignore", "carte_agent": "ignore",
            "gauche_droite": "ignore", "evenements": "ignore", "rapport_v2": "ignore",
        }, f"absence: étapes ignorées attendues : {statuts(res)}")
        check(client.appels == 0 and s.appels == ["journee"], "absence: aucun appel superflu")

        # ── 11. calendrier de rattrapage en échec : avertissement ────────────
        s = Scenario(tmp)
        s.import_journee = lambda: ResultatImportationJournee(
            True, DATE, modifie=False, message="résumé", chemin=s.chemin, calendrier=[]
        )
        res = lancer(s)
        check(statuts(res)["calendrier"] == "avertissement" and res.termine,
              f"calendrier KO: avertissement attendu : {statuts(res)}")

    if echecs:
        print("✗ test_preparation_auto")
        for erreur in echecs:
            print(f"    {erreur}")
        return 1
    print("✓ préparation semi-automatique (ordre, arrêts, reprises, avertissements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
