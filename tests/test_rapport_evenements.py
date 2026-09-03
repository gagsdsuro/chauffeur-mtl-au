#!/usr/bin/env python3
"""Régression de mise en page des évènements du rapport journalier."""
import sys
import tempfile
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gen_rapport as gr  # noqa: E402


def _event(index: int) -> dict:
    premier_arret = 53000 + index * 10
    return {
        "evenement_id": str(11205733 + index),
        "titre": "Détour avec annulation d'arrêt",
        "motif": "Travaux",
        "date_heure_debut": "2026-08-06T06:50:00",
        "date_heure_fin": None,
        "effectif": "En tout temps",
        "description_gd": (
            "VIA TT CARTIER / STE-CATHERINE CÔTÉ NORD\n"
            "VIA CARTIER\nG /DE MAISONNEUVE\nD /CHAMPLAIN\n"
            "D /ONTARIO\nG /DE LORIMIER\nVIA RR"
        ),
        "commentaire": "Attention au terminus temporaire",
        "arrets_annules": [
            {"id": str(premier_arret + n), "nom": f"Arrêt annulé numéro {n}"}
            for n in range(8)
        ],
        "arrets_ajoutes": [
            {"id": "53047", "nom": "Station Papineau temporaire"}
        ],
        "direction": "Nord",
    }


def main() -> int:
    data = {
        "date_travail": "2026-09-03",
        "jour_semaine": "Jeudi",
        "agent": {"garage_id": "59200", "garage": "Frontenac"},
        "heure_prise": "06:00",
        "lieu_prise": "E13301",
        "heure_fin": "14:00",
        "voiture": "38013",
        "lignes": [{
            "numero": "10",
            "type": "Régulier",
            "directions": [{
                "sens": "Nord", "parcours_nom": "Parcours principal",
                "instructions": [],
                "ordre_arrets": [str(53000 + i * 10) for i in reversed(range(9))],
            }],
            "detours_applicables": [_event(i) for i in range(9)],
            "detours_non_applicables": [],
        }],
    }

    with tempfile.TemporaryDirectory() as tmp:
        sortie = Path(tmp) / "rapport.pdf"
        gr.generate(data, str(sortie))
        document = pymupdf.open(sortie)
        erreurs = []
        if not (document[0].rect.height > document[0].rect.width):
            erreurs.append("la première page doit rester en portrait")
        if len(document) < 3:
            erreurs.append("le cas complexe devrait produire plusieurs pages paysage")
        for numero, page in enumerate(document[1:], start=2):
            if not page.rect.width > page.rect.height:
                erreurs.append(f"page {numero}: orientation paysage attendue")
            texte = page.get_text()
            if "Évènement / Titre" not in texte:
                erreurs.append(f"page {numero}: en-tête du tableau non répété")

        texte_detours = "\n".join(page.get_text() for page in document[1:])
        entete = document[1].get_text().splitlines()
        if entete.index("Détour & Commentaires") > entete.index("Arrêts"):
            erreurs.append("la colonne détour doit précéder la colonne arrêts")
        for attendu in (
            "VIA CARTIER", "G /DE MAISONNEUVE", "D /CHAMPLAIN",
            "Ajoutés :", "53047 – Station Papineau temporaire",
        ):
            if attendu not in texte_detours:
                erreurs.append(f"contenu normalisé absent du PDF: {attendu}")
        if texte_detours.find("#11205741") > texte_detours.find("#11205733"):
            erreurs.append("les événements ne suivent pas l'ordre des arrêts du parcours")
        document.close()

    if erreurs:
        print("✗ test_rapport_evenements")
        for erreur in erreurs:
            print(f"    {erreur}")
        return 1
    print("✓ rapport portrait + pages évènements paysage et en-têtes répétés")
    return 0


if __name__ == "__main__":
    sys.exit(main())
