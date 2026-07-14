"""chauffeur.depots — dépôts de données locaux (data/) : chemins et chargement.

Source unique des conventions de nommage des fichiers de données
(gd<ligne>_<direction>.json, <ligne>_<direction>.json, journee-YYYY-MM-DD.json)
et de leur lecture, partagée entre les scripts et l'app Streamlit.

Chaque fonction accepte un répertoire optionnel (défaut = constante du module)
pour permettre des tests hermétiques sur des fichiers gelés.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .evenements import applicable_a_la_date

DATA_DIR     = Path(__file__).resolve().parent.parent / "data"
GD_DIR       = DATA_DIR / "Gauche-Droite"
EVENTS_DIR   = DATA_DIR / "Events"
JOURNEES_DIR = DATA_DIR / "journees"


# ── Chemins canoniques ────────────────────────────────────────────────────────

def chemin_gd(ligne: str, direction: str, gd_dir: Path | None = None) -> Path:
    """gd<ligne>_<direction>.json (direction minuscule)."""
    return (gd_dir or GD_DIR) / f"gd{ligne}_{(direction or '').lower()}.json"


def chemin_evenements(ligne: str, direction: str,
                      events_dir: Path | None = None) -> Path:
    """<ligne>_<direction>.json (sans préfixe, direction minuscule)."""
    return (events_dir or EVENTS_DIR) / f"{ligne}_{(direction or '').lower()}.json"


def chemin_journee(date_str: str, journees_dir: Path | None = None) -> Path:
    """journee-YYYY-MM-DD.json."""
    return (journees_dir or JOURNEES_DIR) / f"journee-{date_str}.json"


# ── Chargement ────────────────────────────────────────────────────────────────

def charger_journee(path: Path) -> dict:
    """Charge un fichier journée JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def charger_gd(ligne: str, direction: str, id_parcours=None,
               gd_dir: Path | None = None) -> tuple[list, dict | None]:
    """Retourne (instructions, parcours) du fichier G-D, ou ([], None) si absent.

    Le parcours est sélectionné par son id ; repli sur le premier parcours si
    l'id est absent du fichier (ou None).
    """
    path = chemin_gd(ligne, direction, gd_dir)
    if not path.exists():
        return [], None
    data = json.loads(path.read_text(encoding="utf-8"))
    all_p = (data.get("routes") or [{}])[0].get("parcours", [])
    if not all_p:
        return [], None
    parcours = next((p for p in all_p if p.get("id") == id_parcours), all_p[0])
    return parcours.get("direction", []), parcours


def charger_evenements(ligne: str, direction: str,
                       events_dir: Path | None = None) -> list:
    """Liste brute des évènements (clé "detours") de la ligne/direction, [] si absent."""
    path = chemin_evenements(ligne, direction, events_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("detours", [])


def evenements_pour_date(ligne: str, direction: str, jour: date,
                         events_dir: Path | None = None) -> list:
    """Évènements de la ligne/direction valides à cette date (filtre date seulement)."""
    return [e for e in charger_evenements(ligne, direction, events_dir)
            if applicable_a_la_date(e, jour)]
