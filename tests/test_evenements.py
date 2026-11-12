#!/usr/bin/env python3
"""
test_evenements.py — Tests unitaires applicabilité des évènements

Couvre chauffeur.evenements (applicable_a_la_date, applicable_a_la_plage,
titre_annule_l_arret, arret_reellement_annule) et la règle 1 de
chauffeur.gd.event_applicable_to_parcours, y compris la convention
stop_ids=None (arrêts GTFS inconnus → fail-safe) sur des évènements
synthétiques inline (pas de fichier externe requis).

Usage : python3 tests/test_evenements.py   (code de sortie 0 si tout passe)
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.evenements import (  # noqa: E402
    applicable_a_la_date,
    applicable_a_la_plage,
    arret_reellement_annule,
    titre_annule_l_arret,
    trier_evenements_par_arrets,
)
from chauffeur.gd import event_applicable_to_parcours  # noqa: E402


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    # ── applicable_a_la_date ──────────────────────────────────────────────────
    fenetre = {"date_heure_debut": "2026-06-10T04:00:00",
               "date_heure_fin":   "2026-06-20T23:59:00"}
    check(not applicable_a_la_date(fenetre, date(2026, 6, 9)),
          "date: jour avant la fenêtre devrait être non applicable")
    check(applicable_a_la_date(fenetre, date(2026, 6, 10)),
          "date: borne début incluse")
    check(applicable_a_la_date(fenetre, date(2026, 6, 15)),
          "date: jour dans la fenêtre")
    check(applicable_a_la_date(fenetre, date(2026, 6, 20)),
          "date: borne fin incluse")
    check(not applicable_a_la_date(fenetre, date(2026, 6, 21)),
          "date: jour après la fenêtre devrait être non applicable")

    debut_seul = {"date_heure_debut": "2026-06-10T04:00:00"}
    check(not applicable_a_la_date(debut_seul, date(2026, 6, 9)),
          "date: début seul, jour avant → non applicable")
    check(applicable_a_la_date(debut_seul, date(2026, 7, 1)),
          "date: début seul, jour après → applicable (borne fin ouverte)")

    # Correctif : fin seule dans le passé → non applicable (l'ancienne UI
    # retournait True dès que date_heure_debut manquait).
    fin_passee = {"date_heure_fin": "2026-06-01T23:59:00"}
    check(not applicable_a_la_date(fin_passee, date(2026, 6, 15)),
          "date: fin seule dans le passé devrait être non applicable")
    check(applicable_a_la_date(fin_passee, date(2026, 5, 15)),
          "date: fin seule future → applicable (borne début ouverte)")

    check(applicable_a_la_date({}, date(2026, 6, 15)),
          "date: aucune borne → applicable")
    check(applicable_a_la_date({"date_heure_debut": "pas-une-date"}, date(2026, 6, 15)),
          "date: ISO invalide → présumé applicable (fail-safe)")

    # ── applicable_a_la_plage ─────────────────────────────────────────────────
    jour = date(2026, 6, 15)

    # plage=None → repli sur le filtre date
    check(applicable_a_la_plage(fenetre, jour, None),
          "plage: None → repli date (fenêtre couvrante)")
    check(not applicable_a_la_plage(fenetre, date(2026, 7, 1), None),
          "plage: None → repli date (hors fenêtre)")

    # Plage franchissant minuit (quart de soir) : évènement actif seulement
    # tôt le lendemain — chevauche 17:27 → 01:21 (+1 j).
    nuit = {"date_heure_debut": "2026-06-16T00:30:00",
            "date_heure_fin":   "2026-06-16T02:00:00"}
    check(applicable_a_la_plage(nuit, jour, ("17:27", "25:21")),
          "plage: quart franchissant minuit devrait couvrir l'évènement du lendemain")
    check(not applicable_a_la_plage(nuit, jour, ("08:00", "10:00")),
          "plage: quart du matin ne devrait pas couvrir l'évènement de nuit")

    # Restriction d'effectif horaire quotidienne
    midi = {"effectif": "Seulement entre 12:00 et 19:00 chaque jour"}
    check(applicable_a_la_plage(midi, jour, ("13:00", "14:00")),
          "plage: quart dans la fenêtre d'effectif → applicable")
    check(not applicable_a_la_plage(midi, jour, ("20:00", "22:00")),
          "plage: quart hors fenêtre d'effectif → non applicable")

    # Plage non parseable → repli date (fail-safe)
    check(applicable_a_la_plage(fenetre, jour, ("??", "!!")),
          "plage: plage non parseable → repli date")

    # ── event_applicable_to_parcours — règle 1 + convention None ─────────────
    annule = {"arrets_annules": [{"id": "54321", "nom": "Lafleur / Clément"}]}
    check(event_applicable_to_parcours(annule, None, []),
          "parcours: stop_ids=None (GTFS inconnu) → présumé applicable")
    check(not event_applicable_to_parcours(annule, set(), []),
          "parcours: set() vide (GTFS a parlé) → non applicable")
    check(event_applicable_to_parcours(annule, {"54321", "11111"}, []),
          "parcours: arrêt annulé présent dans le parcours → applicable")
    check(not event_applicable_to_parcours(annule, {"99999"}, []),
          "parcours: arrêt annulé absent du parcours → non applicable")

    # ── event_applicable_to_parcours — règle 2 inchangée avec stop_ids=None ──
    gd_instr = ["Via - Industriel", "Gauche - Lafleur",
                "Droite - Clément", "Via - Victoria"]
    detour = {"description_gd": "VIA Lafleur\nD/ Clément\nR.R."}
    check(event_applicable_to_parcours(detour, None, gd_instr),
          "parcours: détour dont les bornes figurent dans les G-D → applicable")
    check(not event_applicable_to_parcours(detour, None, ["Via - Sherbrooke", "Droite - Peel"]),
          "parcours: détour dont les rues ne figurent pas dans les G-D → non applicable")
    check(event_applicable_to_parcours({"description_gd": ""}, None, gd_instr),
          "parcours: sans arrêt annulé ni description → applicable")

    # ── tri des tableaux d'évènements selon le parcours ─────────────────────
    par_300 = {"evenement_id": "300", "arrets_annules": [{"id": "30000"}]}
    par_100 = {"evenement_id": "100", "arrets_annules": [{"id": "10000"}]}
    ajout_200 = {"evenement_id": "200", "arrets_ajoutes": ["20000 - Temporaire"]}
    inconnu_a = {"evenement_id": "x", "arrets_annules": [{"id": "99999"}]}
    inconnu_b = {"evenement_id": "y"}
    source = [par_300, inconnu_a, ajout_200, par_100, inconnu_b]
    tries = trier_evenements_par_arrets(
        source, [(1, "10000"), (2, "20000"), (3, "30000")]
    )
    check([e["evenement_id"] for e in tries] == ["100", "200", "300", "x", "y"],
          "tri: ordre du premier arrêt, puis inconnus en ordre stable")
    check(source[0] is par_300, "tri: la liste source ne doit pas être modifiée")

    # ── titre_annule_l_arret ──────────────────────────────────────────────────
    # Les 5 titres réellement produits par le portail employé.
    check(titre_annule_l_arret("détour avec annulation d'arrêt"),
          "titre: « Détour avec annulation d'arrêt » supprime l'arrêt")
    check(titre_annule_l_arret("annulation d'arrêts"),
          "titre: « Annulation d'arrêts » supprime l'arrêt")
    check(not titre_annule_l_arret("arrêt déplacé"),
          "titre: « Arrêt déplacé » maintient l'arrêt (desservi ailleurs)")
    check(not titre_annule_l_arret("information chauffeur"),
          "titre: « Information chauffeur » maintient l'arrêt")

    # Fail-safe : ne jamais faire manquer une annulation réelle.
    check(titre_annule_l_arret("titre inédit du portail"),
          "titre: inconnu → présumé annulant")
    check(titre_annule_l_arret(""), "titre: vide → présumé annulant")
    check(titre_annule_l_arret(None), "titre: None → présumé annulant")

    # Normalisation (type_evenement vient de titre.lower(), mais restons robustes).
    check(not titre_annule_l_arret("  Arrêt Déplacé  "),
          "titre: casse et espaces parasites ne doivent pas changer le verdict")

    # ── arret_reellement_annule (agrégation) ──────────────────────────────────
    depl = {"type_evenement": "arrêt déplacé"}
    info = {"type_evenement": "information chauffeur"}
    annu = {"type_evenement": "détour avec annulation d'arrêt"}

    check(not arret_reellement_annule([]),
          "agrégation: aucun évènement → rien à annuler")
    check(arret_reellement_annule([annu]), "agrégation: un seul, annulant")
    check(not arret_reellement_annule([depl, info]),
          "agrégation: que des évènements maintenant l'arrêt → maintenu")
    # Cas réel data/Events/85_ouest.json, arrêt 53038 : « Arrêt déplacé » arrive
    # EN TÊTE de liste, mais une annulation réelle couvre le même arrêt.
    check(arret_reellement_annule([depl, annu]),
          "agrégation: le plus grave l'emporte, même si l'ambre est en tête")
    check(arret_reellement_annule([annu, depl]),
          "agrégation: ordre inverse, même verdict")

    # ── Résultat ──────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_evenements")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ applicabilité + tri par arrêts du parcours + sémantique des annulations")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
