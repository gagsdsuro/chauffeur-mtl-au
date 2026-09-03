#!/usr/bin/env python3
"""Tests unitaires de la projection et des résumés d'évènements."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.evenements import (  # noqa: E402
    comparer_evenements, evenements_modifies, evenements_retires,
    resumer_changements_evenements,
)
from chauffeur.presentation_evenements import (  # noqa: E402
    formater_evenement_modifie, formater_evenement_retire,
    instructions_description_gd,
    presenter_evenement, rendre_table_evenements_html,
)


def main() -> int:
    echecs = []

    def check(condition, message):
        if not condition:
            echecs.append(message)

    event = {
        "evenement_id": "123",
        "titre": "Détour <urgent>",
        "motif": "Travaux & voirie",
        "date_heure_debut": "2026-09-02T06:50:00",
        "date_heure_fin": None,
        "effectif": "En tout temps",
        "description_gd": "VIA CARTIER\nG/ DE MAISONNEUVE\nTERMINUS TEMPORAIRE",
        "commentaire": "Attention <virage>",
        "arrets_annules": [{"id": "53051", "nom": "Station Papineau"}],
        "arrets_ajoutes": [
            {"id": "53047", "nom": "Station temporaire"},
            "52869 - Parc des Faubourgs",
            "Temp. - Cartier / Sainte-Catherine",
        ],
    }
    affiche = presenter_evenement(
        event, applicable=False, raison_exclusion="Hors parcours & quart"
    )
    check(
        affiche.instructions_gd == (
            "VIA CARTIER", "G/ DE MAISONNEUVE", "TERMINUS TEMPORAIRE"
        ),
        "les lignes G-D originales doivent être conservées",
    )
    check(affiche.arrets_annules[0].texte == "53051 – Station Papineau",
          "l'identifiant d'arrêt doit précéder son nom")
    check(affiche.arrets_ajoutes[1].identifiant == "52869",
          "un arrêt historique sous forme de chaîne doit être reconnu")
    check(affiche.fin == "—", "une fin indéterminée doit être explicite")

    ancien = instructions_description_gd(
        "VIA DE MAISONNEUVE G/ PAPINEAU D/ ONTARIO VIA RR"
    )
    check(len(ancien) == 4 and ancien[0].startswith("Via -"),
          f"repli G-D historique incorrect: {ancien}")

    html = rendre_table_evenements_html([affiche])
    check(html.index("Détour &amp; commentaires") < html.index("Arrêts"),
          "ordre des colonnes HTML incorrect")
    check("Détour &lt;urgent&gt;" in html and "Travaux &amp; voirie" in html,
          "les données métier HTML doivent être échappées")
    check("Hors parcours &amp; quart" in html and "53051 – Station Papineau" in html,
          "état, raison et identifiant d'arrêt absents du HTML")

    version_avant = {
        **event,
        "evenement_id": "200",
        "titre": "Détour modifié",
        "description_gd": "VIA ANCIENNE RUE\nD/ AVANT",
        "commentaire": "Ancien commentaire",
        "arrets_annules": [{"id": "11111", "nom": "Ancien arrêt"}],
        "arrets_ajoutes": [{"id": "22222", "nom": "Ancien ajout"}],
    }
    version_apres = {
        **version_avant,
        "description_gd": "VIA NOUVELLE RUE\nG/ APRÈS",
        "commentaire": "Nouveau commentaire",
        "arrets_annules": [{"id": "33333", "nom": "Nouvel arrêt"}],
        "arrets_ajoutes": [{"id": "44444", "nom": "Nouvel ajout"}],
    }
    avant = [
        dict(event),
        {**event, "titre": "Deuxième variante", "date_heure_debut": "2026-09-03T08:00:00"},
        version_avant,
    ]
    apres = [
        version_apres,
        {**event, "evenement_id": "300", "titre": "Nouveau"},
    ]
    comparaison = comparer_evenements(avant, apres)
    check(len(comparaison["retires"]) == 1,
          "un ID retiré doit former un seul groupe")
    check(len(evenements_retires(avant, apres)) == 2,
          "toutes les variantes d'un ID retiré doivent être conservées")
    modifies = evenements_modifies(avant, apres)
    check(len(modifies) == 1 and modifies[0]["avant"] == [version_avant]
          and modifies[0]["apres"] == [version_apres],
          "les versions complètes avant/après doivent être transportées")
    check(resumer_changements_evenements(avant, apres) == [
        "Nouveau #300 — Nouveau", "Retiré #123 — Détour <urgent>", "Modifié #200"
    ], "ordre ou contenu du résumé commun incorrect")

    retire = formater_evenement_retire(event)
    for attendu in (
        "Détour & commentaires", "G/ DE MAISONNEUVE",
        "Annulés ou concernés", "53051 – Station Papineau",
        "Ajoutés", "53047 – Station temporaire",
    ):
        check(attendu in retire, f"résumé de retrait incomplet: {attendu}")

    modifie = formater_evenement_modifie("200", [version_avant], [version_apres])
    for attendu in (
        "Avant", "VIA ANCIENNE RUE", "Ancien commentaire",
        "11111 – Ancien arrêt", "22222 – Ancien ajout",
        "Après", "VIA NOUVELLE RUE", "Nouveau commentaire",
        "33333 – Nouvel arrêt", "44444 – Nouvel ajout",
    ):
        check(attendu in modifie, f"résumé de modification incomplet: {attendu}")

    if echecs:
        print("✗ test_presentation_evenements")
        for erreur in echecs:
            print(f"    {erreur}")
        return 1
    print("✓ projection HTML/texte + G-D multiligne + comparaison structurée")
    return 0


if __name__ == "__main__":
    sys.exit(main())
