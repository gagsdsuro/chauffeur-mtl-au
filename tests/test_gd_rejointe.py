#!/usr/bin/env python3
"""Régression : une rejointe ne doit pas englober une boucle de desserte."""
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from chauffeur.gd import annotate_events, apply_gd_detours, build_rows
from gen_rapport_v2 import _render_rows_html, filter_rows_by_niveau

INSTRUCTIONS = [
    "Via - Roméo-Vachon",
    "Gauche - Albert-de-Niverville",
    "Gauche - Arthur-Fecteau",
    "Gauche - Cardinal",
    "Droite - Gare Dorval Nord",
    "Droite - Cardinal",
    "Via - Michel-Jasmin",
]
EVENEMENT = {
    "evenement_id": "11343378",
    "titre": "Détour sans annulation",
    "arrets_annules": [],
    "description_gd": (
        "VIA ROMÉO-VACHON\n"
        "VIA NOUVELLE BRETELLE (301) - VERS IND. CELL PARC\n"
        "VIA BRETELLE 302 IND. AV. CARDINAL\n"
        "G/ ALBERT-DE-NIVERVILLE\nG/ CARDINAL\nVIA R.R."
    ),
}


def construire():
    # Code synthétique : ce test ne dépend pas du GTFS installé.
    rows = build_rows(INSTRUCTIONS, [(2, "50001")], {
        "50001": {"code": "50001", "name": "Gare Dorval Nord"},
    })
    return annotate_events(rows, [EVENEMENT])[0]


def instructions_barrees(rows, evenement=None):
    resultat = apply_gd_detours(deepcopy(rows), [evenement or EVENEMENT])
    return {r["gd"] for r in resultat if r.get("detour_removed")}


def main():
    rows = construire()
    attendues = {
        "Gauche - Albert-de-Niverville", "Gauche - Arthur-Fecteau",
        "Gauche - Cardinal",
    }
    assert instructions_barrees(rows) == attendues, "La desserte de la gare doit rester active"

    # Un arrêt groupé peut se trouver sur une ligne sans instruction G-D.
    groupes = deepcopy(rows)
    position = next(i for i, r in enumerate(groupes) if r.get("stop_id"))
    arret = groupes[position]
    groupes[position:position + 1] = [
        {"gd": arret["gd"], "stop_id": None, "stop_code": ""},
        dict(arret, gd=""),
    ]
    assert instructions_barrees(groupes) == attendues, "Protéger aussi les arrêts groupés"

    # Sans arrêt intermédiaire, conserver la tolérance aux raccords courts.
    sans_arret = build_rows(INSTRUCTIONS, [], {})
    etendues = attendues | {"Droite - Gare Dorval Nord", "Droite - Cardinal"}
    assert instructions_barrees(sans_arret) == etendues, "Conserver les raccords sans arrêt"

    # Une desserte explicitement reprise permet de remplacer la boucle régulière.
    for mention in ("GARE DORVAL NORD", "ARRÊT 50001"):
        evenement = dict(EVENEMENT, description_gd=(
            f"VIA ROMÉO-VACHON\nVIA {mention}\nD/ CARDINAL\nVIA R.R."
        ))
        assert instructions_barrees(rows, evenement) == etendues, mention

    # Un mot commun ou un code plus long ne prouve pas la reprise de cet arrêt.
    for mention in ("GARE DORVAL SUD", "ARRÊT 150001"):
        evenement = dict(EVENEMENT, description_gd=(
            f"VIA ROMÉO-VACHON\nVIA {mention}\nD/ CARDINAL\nVIA R.R."
        ))
        assert instructions_barrees(rows, evenement) == attendues, mention

    resultat = apply_gd_detours(deepcopy(rows), [EVENEMENT])
    arret = next(r for r in resultat if r.get("stop_id") == "50001")
    assert not arret["cancelled"] and not arret.get("detour_removed")
    html = _render_rows_html(filter_rows_by_niveau(resultat, "standard"), False, "standard")
    for instruction in ("Droite - Gare Dorval Nord", "Droite - Cardinal"):
        assert f'<span class="gd">{instruction}</span>' in html, instruction
        assert f"✂ {instruction}" not in html, instruction

    print("✓ reprise du détour : gare maintenue, arrêts groupés, raccords et rendu v2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
