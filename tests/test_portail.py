#!/usr/bin/env python3
"""
test_portail.py — Régression du parseur portail employé (scripts/parse_event.py)

Rejoue un fragment HTML figé (tests/cas_portail/34_ouest_portail.json) et
vérifie que PortailEventParser.from_portal_json() normalise correctement les
événements, y compris le cas d'un evenement_id en double (11205733).

Régression couverte :
  - 5 événements extraits, 0 erreur, 0 warning
  - evenement_id 11205733 présent 2× comme entrées séparées
  - merge_events() ne génère pas de faux warning pour un ID dupliqué valide

Usage : python3 tests/test_portail.py   (code de sortie 0 si tout passe)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from parse_event import PortailEventParser  # noqa: E402


CAS = ROOT / "tests" / "cas_portail" / "34_ouest_portail.json"


def _parser():
    raw = CAS.read_text(encoding="utf-8")
    return PortailEventParser.from_portal_json(raw, "34", "ouest")


def main() -> int:
    echecs = []

    p = _parser()

    # ── 1. Aucune erreur ni warning ───────────────────────────────────────────
    if p.errors:
        echecs.append(f"erreurs inattendues : {p.errors}")
    if p.warnings:
        echecs.append(f"warnings inattendus : {p.warnings}")

    # ── 2. Nombre d'événements ────────────────────────────────────────────────
    if len(p.events) != 5:
        echecs.append(f"{len(p.events)} événements, attendu 5")

    # ── 3. ID dupliqué — deux entrées distinctes conservées ──────────────────
    ids_733 = [e for e in p.events if e["evenement_id"] == "11205733"]
    if len(ids_733) != 2:
        echecs.append(f"11205733 présent {len(ids_733)}×, attendu 2×")
    else:
        titres = {e["titre"] for e in ids_733}
        if titres != {"Détour sans annulation", "Détour avec annulation d'arrêt"}:
            echecs.append(f"Titres 11205733 inattendus : {titres}")

    # ── 4. Arrêts annulés de l'événement 'avec annulation' ───────────────────
    avec = next((e for e in p.events
                 if e["evenement_id"] == "11205733"
                 and e["titre"] == "Détour avec annulation d'arrêt"), None)
    if avec:
        ids = [a["id"] for a in avec["arrets_annules"]]
        attendus = ["53046", "53062", "53074", "53090", "53104", "54188"]
        if ids != attendus:
            echecs.append(f"arrets_annules 11205733/avec : {ids}")
        aj = [a["id"] for a in avec["arrets_ajoutes"]]
        if aj != ["53016", "54038"]:
            echecs.append(f"arrets_ajoutes 11205733/avec : {aj}")
    else:
        echecs.append("événement 11205733/avec annulation introuvable")

    # ── 5. Description G-D de l'événement 'sans annulation' ──────────────────
    sans = next((e for e in p.events
                 if e["evenement_id"] == "11205733"
                 and e["titre"] == "Détour sans annulation"), None)
    if sans:
        gd = sans.get("description_gd") or ""
        if "VIA DE MAISONNEUVE" not in gd:
            echecs.append(f"description_gd 11205733/sans inattendue : {gd!r}")
        if "\n" not in gd:
            echecs.append("description_gd 11205733/sans : retours de ligne perdus")
        if sans["arrets_annules"]:
            echecs.append(f"11205733/sans : arrets_annules devrait être vide, obtenu {sans['arrets_annules']}")
    else:
        echecs.append("événement 11205733/sans annulation introuvable")

    # ── 6. Date fin None sur 'Non applicable' ─────────────────────────────────
    deplace = next((e for e in p.events if e["evenement_id"] == "11205949"), None)
    if deplace:
        if deplace["date_heure_fin"] is not None:
            echecs.append(f"11205949: date_heure_fin devrait être None, obtenu {deplace['date_heure_fin']!r}")
    else:
        echecs.append("événement 11205949 introuvable")

    # ── 7. merge_events() — pas de faux warning pour ID dupliqué ─────────────
    # Simuler un fichier existant identique aux nouveaux événements.
    existing = {"detours": list(p.events)}
    p2 = _parser()
    p2.merge_events(existing)
    faux = [w for w in p2.warnings if "11205733" in w and "remplacé" in w]
    if faux:
        echecs.append(f"merge_events faux warning pour ID dupliqué : {faux}")

    # ── Résultat ──────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_portail")
        for e in echecs:
            print(f"    {e}")
        print(f"\n0/1 cas réussis")
        return 1

    print("✓ 34 ouest portail (5 évts, ID 11205733×2, merge sans faux warning)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
