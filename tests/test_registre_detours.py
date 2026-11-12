#!/usr/bin/env python3
"""
test_registre_detours.py — Tests de chauffeur.registre_detours (appariement des détours).

Hermétique : G-D, évènements et arrêts GTFS viennent du cas figé
tests/cas_rapport_gd/gd-125-est-2026-07-17 (détour de de Rouen : cinq arrêts
ajoutés sur une même étape) copiés dans un répertoire `data/` temporaire ;
le GTFS et le journal sont redirigés. Couvre :
  • signature : indépendante du numéro d'évènement, des dates, du motif et de
    l'ordre des arrêts ajoutés ; sensible aux arrêts et à la description ;
  • synchronisation : un détour que le pipeline ne sait pas trancher seul devient
    « incertain » (idempotente, jamais d'écrasement d'un choix validé) ; un détour
    résolu sans diagnostic n'est pas enregistré (445 est) ;
  • validation avec contrôle de version, choix mal formé refusé ;
  • réutilisation : un autre numéro d'évènement retrouve le choix validé ;
  • choix devenu inapplicable (G-D modifié) → « a_revalider ».

Usage : python3 tests/test_registre_detours.py   (code de sortie 0 si tout passe)
"""
import json
import shutil
import sys
import tempfile
from contextlib import ExitStack
from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur import depots, journal  # noqa: E402
from chauffeur import registre_detours as rd  # noqa: E402
from chauffeur.gd import (  # noqa: E402
    annotate_events, apply_gd_detours, build_rows, insert_added_stops_inline, rows_de_rendu,
)
from chauffeur.registre_appariement import ConflitAppariement  # noqa: E402

CAS = ROOT / "tests" / "cas_rapport_gd"
JOUR = date(2026, 7, 17)
DE_ROUEN = ("Temp. - de Rouen / Cuvillier", "Joliette / de Rouen",
            "Temp. - De Rouen /Bourbonnière (S/O)", "Temp. - DE ROUEN / PIE IX")
MORGAN = "Temp. - Ontario /Morgan (S/O)"


def _cas(nom):
    d = CAS / nom
    lire = lambda f: json.loads((d / f).read_text(encoding="utf-8"))  # noqa: E731
    return lire("gd.json"), lire("events.json"), lire("gtfs_stops.json")


class Monde:
    """data/ temporaire avec un cas figé, GTFS et journal redirigés."""

    def __init__(self, nom, ligne, direction):
        self.ligne, self.direction = ligne, direction
        self.gd, self.events, self.gtfs = _cas(nom)
        self.stack = ExitStack()
        self.base = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        (self.base / "gtfs" / "gtfs_stm").mkdir(parents=True)
        (self.base / "gtfs" / "gtfs_stm" / "stops.txt").write_text("stop_id\n", encoding="utf-8")
        (self.base / "Events").mkdir()
        (self.base / "Gauche-Droite").mkdir()
        self.ecrire()
        stops = [tuple(x) for x in self.gtfs["stops"]]
        for cible, valeur in (
            ("chauffeur.gtfs.stops_for_parcours", lambda *a, **k: stops),
            ("chauffeur.gtfs.stop_names", lambda *a, **k: self.gtfs["stop_names"]),
        ):
            self.stack.enter_context(patch(cible, valeur))
        self.stack.enter_context(patch.object(journal, "LOG_DIR_COMMUN", self.base / "log"))
        self.dir = depots.repertoire_detours(self.base / "Gauche-Droite")

    def ecrire(self):
        (self.base / "Events" / f"{self.ligne}_{self.direction}.json").write_text(
            json.dumps({"ligne": self.ligne, "direction": self.direction,
                        "detours": self.events}, ensure_ascii=False), encoding="utf-8")
        (self.base / "Gauche-Droite" / f"gd{self.ligne}_{self.direction}.json").write_text(
            json.dumps(self.gd, ensure_ascii=False), encoding="utf-8")

    def sync(self):
        return rd.synchroniser_evenements_ligne(self.ligne, self.direction, base=self.base,
                                                jour=JOUR)

    def charger(self):
        return rd.charger_detours(self.ligne, self.direction, self.dir)

    def evenement(self, evenement_id="11190151", titre="Détour avec annulation d'arrêt"):
        return next(e for e in self.events
                    if e["evenement_id"] == evenement_id and e["titre"] == titre)

    def noms_ajoutes(self, evenement=None, par_defaut=True):
        """Noms des arrêts ajoutés tels que le rapport les place (rows de rendu)."""
        e = evenement or self.evenement()
        choix, choix_arrets = rd.fournisseurs(self.ligne, self.direction, self.dir,
                                              self.base / "Events")
        stops = [tuple(x) for x in self.gtfs["stops"]]
        rows, added, _ = annotate_events(
            build_rows(self.gd["routes"][0]["parcours"][0]["direction"], stops,
                       self.gtfs["stop_names"]), [e])
        rows = apply_gd_detours(rows, [e], None, choix)
        rows, _ = insert_added_stops_inline(rows, added, None, choix_arrets)
        return [r["stop_name"] for r in rows_de_rendu(rows) if r.get("added_inline")]

    def cle(self, nom):
        """Clé d'un arrêt ajouté de l'évènement (son code s'il en a un)."""
        a = next(a for a in self.evenement()["arrets_ajoutes"] if a["nom"] == nom)
        return rd.cle_arret_ajoute({"id": a.get("id", ""), "name": nom})

    def fermer(self):
        self.stack.close()


def signature():
    erreurs = []
    e = {"evenement_id": "1", "titre": "T", "motif": "Travaux", "effectif": "En tout temps",
         "date_heure_debut": "2026-01-01T00:00:00", "arrets_annules": [{"id": "5", "nom": "a"}],
         "arrets_ajoutes": [{"id": "", "nom": "Temp. - A / B"}, {"id": "", "nom": "Temp. - C / D"}],
         "description_gd": "VIA ALPHA\nG/ BETA\nVIA R/R"}
    base = rd.signature_detour("10", "Sud", e)
    autre = dict(e, evenement_id="2", motif="Autre", effectif="Seulement le soir",
                 date_heure_debut="2027-05-05T00:00:00",
                 arrets_ajoutes=list(reversed(e["arrets_ajoutes"])),
                 description_gd="via alpha\nG/ BETA\nVIA R.R.")
    if rd.signature_detour("10", "sud", autre) != base:
        erreurs.append("la signature doit ignorer évènement, dates, motif, effectif, ordre et R/R")
    if rd.signature_detour("10", "sud", dict(e, arrets_annules=[{"id": "6"}])) == base:
        erreurs.append("arrêt annulé différent : même signature")
    if rd.signature_detour("10", "sud", dict(e, description_gd="VIA ALPHA\nD/ BETA\nVIA R.R.")) == base:
        erreurs.append("description différente : même signature")
    if rd.signature_detour("10", "nord", e) == base:
        erreurs.append("direction différente : même signature")
    return erreurs


def synchronisation():
    erreurs = []
    m = Monde("gd-125-est-2026-07-17", "125", "est")
    try:
        messages = m.sync()
        contenu = m.charger()
        sig = rd.signature_detour("125", "est", m.evenement())
        entree = (contenu or {}).get("detours", {}).get(sig)
        if not (entree and entree["statut"] == "incertain" and messages):
            return [f"détour de Rouen non signalé : {messages} {contenu}"]
        if not any("ordre à vérifier" in d for d in entree["diagnostics"]):
            erreurs.append(f"diagnostics : {entree['diagnostics']}")
        if entree["evenement_ids"] != ["11190151"] or entree["parcours"] != [2]:
            erreurs.append(f"métadonnées : {entree['evenement_ids']} {entree['parcours']}")
        version = contenu["version"]
        if m.sync() != [] or m.charger()["version"] != version:
            erreurs.append("synchronisation non idempotente")
    finally:
        m.fermer()

    # 445 est : résolu sans diagnostic → rien à enregistrer.
    m = Monde("gd-445-est-2026-10-21", "445", "est")
    try:
        if m.sync() != [] or m.charger() is not None:
            erreurs.append("445 est : un détour résolu ne doit pas être enregistré")
    finally:
        m.fermer()
    return erreurs


def validation_et_reutilisation():
    erreurs = []
    m = Monde("gd-125-est-2026-07-17", "125", "est")
    try:
        m.sync()
        e = m.evenement()
        defaut = m.noms_ajoutes()
        voulu = [DE_ROUEN[3], DE_ROUEN[2], DE_ROUEN[1], DE_ROUEN[0]]   # ordre inverse
        if defaut != [*DE_ROUEN, MORGAN]:
            erreurs.append(f"ordre de l'évènement par défaut : {defaut}")
        choix = {"arrets_ajoutes": [{"cle": m.cle(n), "etape": 2} for n in voulu]}
        version = m.charger()["version"]
        contenu = rd.valider_detour("125", "est", e, choix, "40001", version, m.dir)
        sig = rd.signature_detour("125", "est", e)
        if contenu["detours"][sig]["statut"] != "valide" or contenu["detours"][sig]["valide_par"] != "40001":
            erreurs.append(f"validation : {contenu['detours'][sig]}")
        try:
            rd.valider_detour("125", "est", e, choix, "99999", version, m.dir)
            erreurs.append("validation sur une version périmée acceptée")
        except ConflitAppariement:
            pass
        for mauvais in ({}, {"debut": {"type": "x", "cle": "a", "occurrence": 1}},
                        {"arrets_ajoutes": [{"cle": "", "etape": 0}]}):
            try:
                rd.verifier_choix(mauvais)
                erreurs.append(f"choix invalide accepté : {mauvais}")
            except ValueError:
                pass

        if m.noms_ajoutes() != [*voulu, MORGAN]:
            erreurs.append(f"le choix validé n'est pas imposé : {m.noms_ajoutes()}")

        # Même détour, autre numéro, autres dates : le choix est retrouvé.
        autre = deepcopy(e)
        autre.update(evenement_id="11999999", date_heure_debut="2027-03-01T00:00:00",
                     date_heure_fin=None, motif="Autre motif")
        m.events.append(autre)
        m.ecrire()
        if m.noms_ajoutes(autre) != [*voulu, MORGAN]:
            erreurs.append("le choix validé n'est pas réutilisé sous un autre numéro d'évènement")

        # Une resynchronisation n'écrase jamais un choix validé.
        m.sync()
        if m.charger()["detours"][sig]["statut"] != "valide":
            erreurs.append("choix validé écrasé par la synchronisation")
        if rd.detours_a_reviser([{"ligne": "125", "direction": "est"}], date(2026, 7, 17), m.base):
            erreurs.append("un détour validé ne doit pas être à réviser")

        # Retrait : plus rien n'est imposé.
        rd.retirer_choix("125", "est", sig, "40001", m.charger()["version"], m.dir)
        if m.noms_ajoutes() != [*DE_ROUEN, MORGAN]:
            erreurs.append("choix retiré mais toujours imposé")
    finally:
        m.fermer()
    return erreurs


def choix_devenu_inapplicable():
    erreurs = []
    m = Monde("gd-125-est-2026-07-17", "125", "est")
    try:
        m.sync()
        e = m.evenement()
        introuvable = {"type": "instruction", "cle": "Droite - Disparue", "occurrence": 1}
        rd.valider_detour("125", "est", e, {"debut": introuvable, "fin": None}, "40001",
                          m.charger()["version"], m.dir)
        messages = m.sync()
        sig = rd.signature_detour("125", "est", e)
        entree = m.charger()["detours"][sig]
        if entree["statut"] != "a_revalider" or not any("revalider" in x for x in messages):
            erreurs.append(f"choix inapplicable : {entree['statut']} {messages}")
        if entree["choix"] is None:
            erreurs.append("le choix doit être conservé pour être reconfirmé")
        if rd.detours_a_reviser([{"ligne": "125", "direction": "est"}], JOUR, m.base) != \
                ["125 est — évènement 11190151"]:
            erreurs.append("detours_a_reviser devrait lister le détour à revalider")
    finally:
        m.fermer()
    return erreurs


TESTS = [signature, synchronisation, validation_et_reutilisation, choix_devenu_inapplicable]


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
