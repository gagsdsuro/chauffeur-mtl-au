#!/usr/bin/env python3
"""Tests de la logique de publication GTFS contextuelle.

Vérifie que les fonctions de chauffeur.periodes calculent correctement :
  - la liste active pour une date donnée
  - la date de publication GTFS (J-10 avant début de liste)
  - la disponibilité du GTFS pour une date cible

Cas 2026 (data/reference/periodes_2026.json) :
  Listes : 5 janvier, 23 mars, 15 juin, 24 août, 26 octobre
  Publications GTFS : 26 déc 2025, 13 mars, 5 juin, 14 août, 16 octobre

Usage : python3 tests/test_periodes_gtfs.py
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.periodes import (
    DELAI_PUBLICATION_GTFS_JOURS,
    liste_active_pour_date,
    publication_gtfs_pour_date,
    publication_gtfs_pour_liste,
    gtfs_disponible_pour_date,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"✗ {message}")
        sys.exit(1)


def test_delai_publication():
    check(DELAI_PUBLICATION_GTFS_JOURS == 10,
          f"Délai de publication : attendu 10, obtenu {DELAI_PUBLICATION_GTFS_JOURS}")
    print("✓ test_delai_publication")


def test_publication_gtfs_pour_liste():
    # Liste du 5 janvier 2026 → publication le 26 décembre 2025
    check(
        publication_gtfs_pour_liste(date(2026, 1, 5)) == date(2025, 12, 26),
        "Publication liste janvier : attendu 2025-12-26",
    )
    # Liste du 23 mars 2026 → publication le 13 mars 2026
    check(
        publication_gtfs_pour_liste(date(2026, 3, 23)) == date(2026, 3, 13),
        "Publication liste mars : attendu 2026-03-13",
    )
    # Liste du 15 juin 2026 → publication le 5 juin 2026
    check(
        publication_gtfs_pour_liste(date(2026, 6, 15)) == date(2026, 6, 5),
        "Publication liste juin : attendu 2026-06-05",
    )
    print("✓ test_publication_gtfs_pour_liste")


def test_liste_active_pour_date():
    # 10 janvier → liste du 5 janvier
    check(
        liste_active_pour_date(date(2026, 1, 10)) == date(2026, 1, 5),
        "10 janvier → liste du 5 janvier",
    )
    # 15 mars → encore liste du 5 janvier (pas encore au 23 mars)
    check(
        liste_active_pour_date(date(2026, 3, 15)) == date(2026, 1, 5),
        "15 mars → liste du 5 janvier (transition)",
    )
    # 25 mars → liste du 23 mars
    check(
        liste_active_pour_date(date(2026, 3, 25)) == date(2026, 3, 23),
        "25 mars → liste du 23 mars",
    )
    # 10 juin → encore liste du 23 mars
    check(
        liste_active_pour_date(date(2026, 6, 10)) == date(2026, 3, 23),
        "10 juin → liste du 23 mars (transition)",
    )
    # 20 juin → liste du 15 juin
    check(
        liste_active_pour_date(date(2026, 6, 20)) == date(2026, 6, 15),
        "20 juin → liste du 15 juin",
    )
    # 30 octobre → liste du 26 octobre
    check(
        liste_active_pour_date(date(2026, 10, 30)) == date(2026, 10, 26),
        "30 octobre → liste du 26 octobre",
    )
    print("✓ test_liste_active_pour_date")


def test_publication_gtfs_pour_date():
    # 15 mars → liste du 5 janvier → publication le 26 déc 2025
    check(
        publication_gtfs_pour_date(date(2026, 3, 15)) == date(2025, 12, 26),
        "Publication pour 15 mars : 2025-12-26",
    )
    # 25 mars → liste du 23 mars → publication le 13 mars 2026
    check(
        publication_gtfs_pour_date(date(2026, 3, 25)) == date(2026, 3, 13),
        "Publication pour 25 mars : 2026-03-13",
    )
    print("✓ test_publication_gtfs_pour_date")


def test_gtfs_disponible_pour_date():
    # 15 mars avec ref=10 mars : liste du 5 janvier, publication 26 déc 2025
    # 10 mars >= 26 déc → disponible
    check(
        gtfs_disponible_pour_date(date(2026, 3, 15), date(2026, 3, 10)) is True,
        "15 mars (ref 10 mars) : GTFS disponible (liste janvier)",
    )

    # 25 mars avec ref=15 mars : liste du 23 mars, publication 13 mars 2026
    # 15 mars >= 13 mars → disponible
    check(
        gtfs_disponible_pour_date(date(2026, 3, 25), date(2026, 3, 15)) is True,
        "25 mars (ref 15 mars) : GTFS disponible (liste mars)",
    )

    # 25 mars avec ref=10 mars : publication 13 mars 2026
    # 10 mars < 13 mars → pas disponible
    check(
        gtfs_disponible_pour_date(date(2026, 3, 25), date(2026, 3, 10)) is False,
        "25 mars (ref 10 mars) : GTFS pas encore disponible (liste mars)",
    )

    # 10 janvier avec ref=5 janvier : liste du 5 janvier, publication 26 déc 2025
    # 5 janvier >= 26 déc → disponible
    check(
        gtfs_disponible_pour_date(date(2026, 1, 10), date(2026, 1, 5)) is True,
        "10 janvier (ref 5 janvier) : GTFS disponible",
    )

    # Hors fenêtre : 15 juin avec ref=1er juin
    # Liste du 15 juin → publication le 5 juin
    # 1er juin < 5 juin → pas disponible
    check(
        gtfs_disponible_pour_date(date(2026, 6, 15), date(2026, 6, 1)) is False,
        "15 juin (ref 1er juin) : GTFS pas encore disponible",
    )

    # Dans la fenêtre : 15 juin avec ref=5 juin
    # 5 juin >= 5 juin → disponible
    check(
        gtfs_disponible_pour_date(date(2026, 6, 15), date(2026, 6, 5)) is True,
        "15 juin (ref 5 juin) : GTFS disponible",
    )

    print("✓ test_gtfs_disponible_pour_date")


def test_info_gtfs_contextuel():
    """Vérifie les champs ajoutés à info_gtfs(date_cible=...)."""
    from chauffeur.depots import info_gtfs

    # Sans date_cible : pas de contexte
    info = info_gtfs()
    check(info.get("liste_active") is None, "Sans date_cible : liste_active est None")

    # Avec date_cible : contexte rempli
    info = info_gtfs(date_cible=date(2026, 3, 15))
    check(info.get("liste_active") == "2026-01-05",
          f"15 mars : liste_active = {info.get('liste_active')}")
    check(info.get("publication_cible") == "2025-12-26",
          f"15 mars : publication_cible = {info.get('publication_cible')}")
    check(isinstance(info.get("fenetre_ouverte"), bool),
          "fenetre_ouverte est un booléen")
    check(isinstance(info.get("gtfs_a_jour"), bool),
          "gtfs_a_jour est un booléen")
    check(isinstance(info.get("mise_a_jour_requise"), bool),
          "mise_a_jour_requise est un booléen")

    print("✓ test_info_gtfs_contextuel")


def test_preparation_auto_etapes():
    """Vérifie que gtfs_statique est bien dans ETAPES et LIBELLES."""
    from chauffeur.preparation_auto import ETAPES, LIBELLES, NON_BLOQUANTES

    check("gtfs_statique" in ETAPES,
          f"gtfs_statique dans ETAPES : {ETAPES}")
    check("gtfs_statique" in LIBELLES,
          f"gtfs_statique dans LIBELLES : {list(LIBELLES.keys())}")
    check("gtfs_statique" in NON_BLOQUANTES,
          "gtfs_statique est non bloquante")
    # Vérifier l'ordre : gtfs_statique entre calendrier et carte_agent
    idx_cal = ETAPES.index("calendrier")
    idx_gtfs = ETAPES.index("gtfs_statique")
    idx_ca = ETAPES.index("carte_agent")
    check(idx_cal < idx_gtfs < idx_ca,
          f"Ordre : calendrier({idx_cal}) < gtfs({idx_gtfs}) < carte_agent({idx_ca})")

    print("✓ test_preparation_auto_etapes")


if __name__ == "__main__":
    test_delai_publication()
    test_publication_gtfs_pour_liste()
    test_liste_active_pour_date()
    test_publication_gtfs_pour_date()
    test_gtfs_disponible_pour_date()
    test_info_gtfs_contextuel()
    test_preparation_auto_etapes()
    print("\n✓ Tous les tests de publication GTFS sont passés.")
