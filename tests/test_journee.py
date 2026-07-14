#!/usr/bin/env python3
"""
test_journee.py — Tests unitaires chauffeur.journee

Couvre groupes_de_service() et lignes_de_service() sur des journées
synthétiques inline (pas de fichier externe requis).

Usage : python3 tests/test_journee.py   (code de sortie 0 si tout passe)
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.journee import groupes_de_service, lignes_de_service  # noqa: E402

# ── Journée synthétique ───────────────────────────────────────────────────────
# 2 pièces :
#   pièce A  fin=10:00  trajets : 34 est id2 (détour), 34 ouest id1
#   pièce B  fin=18:00  trajets : 136 nord id1, 34 est id2 (doublon inter-pièces)
JOURNEE = {
    "pieces": [
        {
            "id": "A", "debut": "07:00", "fin": "10:00",
            "trajets": [
                {"type": "service",     "ligne": "34",  "direction": "est",   "id_parcours": 2, "detour": True,
                 "depart": {"heure": "07:10"}, "arrivee": {"heure": "08:00"}},
                {"type": "service",     "ligne": "34",  "direction": "ouest", "id_parcours": 1, "detour": False},
                {"type": "haut_le_pied","ligne": None,  "direction": None,    "id_parcours": None, "detour": False},
            ],
        },
        {
            "id": "B", "debut": "11:00", "fin": "18:00",
            "trajets": [
                {"type": "service", "ligne": "136", "direction": "nord", "id_parcours": 1, "detour": False},
                # même groupe que le premier trajet de A — ne doit pas créer de doublon
                {"type": "service", "ligne": "34",  "direction": "est",  "id_parcours": 2, "detour": False,
                 "depart": {"heure": "12:00"}, "arrivee": {"heure": "12:50"}},
            ],
        },
    ]
}


def main() -> int:
    echecs = []

    # ── groupes_de_service ────────────────────────────────────────────────────
    g = groupes_de_service(JOURNEE)

    # 3 groupes uniques : (34,est,2), (34,ouest,1), (136,nord,1)
    if len(g) != 3:
        echecs.append(f"groupes_de_service: {len(g)} groupes, attendu 3")

    # Ordre d'apparition préservé
    if g and g[0] != {"ligne": "34", "direction": "est", "id_parcours": 2, "detour": True}:
        echecs.append(f"groupes_de_service: premier groupe inattendu : {g[0]}")

    # detour=True propagé même si le doublon inter-pièces a detour=False
    g34est = next((x for x in g if x["ligne"] == "34" and x["direction"] == "est"), None)
    if g34est and not g34est["detour"]:
        echecs.append("groupes_de_service: 34 est devrait être detour=True")

    # haut_le_pied exclu
    if any(x["ligne"] is None for x in g):
        echecs.append("groupes_de_service: haut_le_pied ne devrait pas apparaître")

    # Sans avec_trips : aucune clé "trips" (sortie historique inchangée)
    if any("trips" in x for x in g):
        echecs.append("groupes_de_service: pas de clé trips sans avec_trips")

    # ── groupes_de_service (avec_trips) ───────────────────────────────────────
    gt = groupes_de_service(JOURNEE, avec_trips=True)
    if len(gt) != 3:
        echecs.append(f"avec_trips: {len(gt)} groupes, attendu 3")
    gt34 = next((x for x in gt if x["ligne"] == "34" and x["direction"] == "est"), {})
    # Le doublon inter-pièces accumule ses 2 trajets dans le même groupe
    if gt34.get("trips") != [
        {"depart_heure": "07:10", "arrivee_heure": "08:00"},
        {"depart_heure": "12:00", "arrivee_heure": "12:50"},
    ]:
        echecs.append(f"avec_trips: trips 34 est inattendus : {gt34.get('trips')}")
    # Trajet sans heures : trip accumulé avec chaînes vides
    gt34o = next((x for x in gt if x["ligne"] == "34" and x["direction"] == "ouest"), {})
    if gt34o.get("trips") != [{"depart_heure": "", "arrivee_heure": ""}]:
        echecs.append(f"avec_trips: trips 34 ouest inattendus : {gt34o.get('trips')}")

    # ── lignes_de_service (toutes) ────────────────────────────────────────────
    l = lignes_de_service(JOURNEE)
    # 3 paires uniques : (34,est), (34,ouest), (136,nord)
    if len(l) != 3:
        echecs.append(f"lignes_de_service toutes: {len(l)} paires, attendu 3")
    if l and l[0] != ("34", "est"):
        echecs.append(f"lignes_de_service: première paire inattendue : {l[0]}")

    # ── lignes_de_service (restantes) ────────────────────────────────────────
    # À 10:30, la pièce A (fin=10:00) est terminée, B (fin=18:00) reste.
    midi = datetime(2026, 6, 26, 10, 30)
    r = lignes_de_service(JOURNEE, restantes_seulement=True, now=midi)
    # Seule pièce B reste → (136,nord) + (34,est) — dans l'ordre d'apparition
    if len(r) != 2:
        echecs.append(f"lignes_de_service restantes: {len(r)} paires, attendu 2")
    if ("34", "ouest") in r:
        echecs.append("lignes_de_service restantes: (34,ouest) ne devrait plus apparaître")
    if ("136", "nord") not in r:
        echecs.append("lignes_de_service restantes: (136,nord) manquant")

    # ── Pièce sans champ fin — toujours incluse ───────────────────────────────
    journee_sans_fin = {
        "pieces": [{"id": "X", "trajets": [
            {"type": "service", "ligne": "10", "direction": "sud", "id_parcours": 1, "detour": False}
        ]}]
    }
    r2 = lignes_de_service(journee_sans_fin, restantes_seulement=True, now=datetime(2026, 6, 26, 23, 59))
    if r2 != [("10", "sud")]:
        echecs.append(f"pièce sans fin: attendu [('10','sud')], obtenu {r2}")

    # ── Résultat ──────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_journee")
        for e in echecs:
            print(f"    {e}")
        print(f"\n0/1 cas réussis")
        return 1

    print("✓ groupes_de_service (+avec_trips) + lignes_de_service (ordre, détour, restantes, sans-fin)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
