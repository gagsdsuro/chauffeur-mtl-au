#!/usr/bin/env python3
"""
test_parse_event.py — Régression du parseur d'évènements (scripts/parse_event.py)

Rejoue des collages bruts figés dans tests/cas_event/*.txt et vérifie que le
parsing ne produit pas d'avertissements parasites et capture correctement les
arrêts/description.

Régression couverte (ligne 34, juin 2026) : un évènement « Détour sans
annulation » a une section « Arrêt(s) » VIDE suivie immédiatement de
« Description Gauche-Droite ». L'ancienne capture des arrêts avalait alors tout
le bloc virage-par-virage → 10 avertissements « Format d'arrêt non reconnu ».

Usage : python3 tests/test_parse_event.py   (code de sortie 0 si tout passe)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from parse_event import PortailEventParser, split_sections  # noqa: E402


def _events_par_section(txt: str):
    """{ (ligne, direction): (events, warnings) }."""
    out = {}
    for sec in split_sections(txt):
        p = PortailEventParser(sec)
        p.parse_all()
        out[(p.ligne, p.direction)] = (p.events, p.warnings)
    return out


def _trouver(events, ev_id, titre):
    for e in events:
        if e["evenement_id"] == ev_id and e["titre"] == titre:
            return e
    return None


def main() -> int:
    echecs = []
    txt = (ROOT / "tests" / "cas_event" / "34.txt").read_text(encoding="utf-8")
    sections = _events_par_section(txt)

    # 1. Aucun avertissement « Format d'arrêt » sur l'ensemble (le bug).
    for (lig, dir), (_, warnings) in sections.items():
        parasites = [w for w in warnings if "Format d'arrêt" in w]
        if parasites:
            echecs.append(f"{lig} {dir}: {len(parasites)} avertissement(s) parasite(s)")

    ouest = sections.get(("34", "ouest"), ([], []))[0]
    if len(ouest) != 5:
        echecs.append(f"34 ouest: {len(ouest)} évènements, attendu 5")

    # 2. « Détour sans annulation » : section Arrêt(s) vide, mais description_gd captée.
    sans = _trouver(ouest, "11205733", "Détour sans annulation")
    if not sans:
        echecs.append("34 ouest: évènement 'Détour sans annulation' introuvable")
    else:
        if sans["arrets_annules"]:
            echecs.append(f"'sans annulation': arrets_annules devrait être vide, obtenu {sans['arrets_annules']}")
        if not (sans.get("description_gd") or "").startswith("VIA DE MAISONNEUVE"):
            echecs.append(f"'sans annulation': description_gd inattendue: {sans.get('description_gd')!r}")
        if "\n" not in (sans.get("description_gd") or ""):
            echecs.append("'sans annulation': les retours de ligne G-D doivent être conservés")

    # 3. « Détour avec annulation » : 6 arrêts annulés + 2 ajoutés, non pollués.
    avec = _trouver(ouest, "11205733", "Détour avec annulation d'arrêt")
    if avec:
        ids = [a["id"] for a in avec["arrets_annules"]]
        if ids != ["53046", "53062", "53074", "53090", "53104", "54188"]:
            echecs.append(f"'avec annulation': arrets_annules={ids}")
        aj = [a.get("id") for a in avec["arrets_ajoutes"]]
        if aj != ["53016", "54038"]:
            echecs.append(f"'avec annulation': arrets_ajoutes={aj}")
    else:
        echecs.append("34 ouest: évènement 'Détour avec annulation' introuvable")

    # 4. Le compte rendu d'un retrait restitue le G-D et les deux groupes d'arrêts.
    if avec:
        retire = PortailEventParser("", verbose=True)
        retire.ligne, retire.direction = "34", "ouest"
        retire.merge_events({"detours": [avec]})
        resume = retire.get_summary()
        for attendu in (
            "Détour & commentaires", "VIA FRONTENAC",
            "Annulés ou concernés", "53046", "Ajoutés", "53016",
        ):
            if attendu not in resume:
                echecs.append(f"résumé de retrait incomplet: {attendu}")

        retire_court = PortailEventParser("", verbose=False)
        retire_court.merge_events({"detours": [avec]})
        if "Détour & commentaires" in "\n".join(retire_court.warnings):
            echecs.append("verbose=False devrait masquer les détails du retrait")

        version_apres = {
            **avec,
            "description_gd": "VIA NOUVELLE RUE\nG/ APRÈS",
            "commentaire": "Nouveau commentaire",
            "arrets_annules": [{"id": "33333", "nom": "Nouvel arrêt"}],
            "arrets_ajoutes": [{"id": "44444", "nom": "Nouvel ajout"}],
        }
        modifie = PortailEventParser("", verbose=True)
        modifie.ligne, modifie.direction = "34", "ouest"
        modifie.events = [version_apres]
        modifie.merge_events({"detours": [avec]})
        resume_modifie = modifie.get_summary()
        for attendu in (
            "Avant", "VIA FRONTENAC", "53046", "53016",
            "Après", "VIA NOUVELLE RUE", "Nouveau commentaire", "33333", "44444",
        ):
            if attendu not in resume_modifie:
                echecs.append(f"résumé de modification incomplet: {attendu}")

    if echecs:
        print("✗ test_parse_event")
        for e in echecs:
            print(f"    {e}")
        print(f"\n0/1 cas réussis")
        return 1
    print("✓ cas-34 (5 évts ouest + 2 est, 0 avertissement parasite)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
