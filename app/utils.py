"""Helpers partagés entre les pages Streamlit (formatage, cache GTFS)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st


def _fmt_mtime(path: Path) -> str:
    if not path.exists():
        return "–"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _fmt_size(path: Path) -> str:
    if not path.exists():
        return ""
    b = path.stat().st_size
    return f"{b/1024:.0f} KB" if b < 1_048_576 else f"{b/1_048_576:.1f} MB"


@st.cache_data(show_spinner=False)
def _cached_arrets_pour_parcours(
    gtfs_dir_str: str, ligne: str, direction: str, id_parcours
) -> tuple[str, ...] | None:
    """Séquence des stop_ids GTFS d'un parcours (mise en cache par session).

    Retourne None si la résolution échoue (GTFS corrompu, ligne inconnue…) :
    « arrêts inconnus », qui déclenche le fail-safe d'applicabilité — à
    distinguer d'un tuple vide (« le GTFS a parlé : aucun arrêt »).
    """
    try:
        from chauffeur.gtfs import stops_for_parcours
        stops = stops_for_parcours(Path(gtfs_dir_str), ligne, direction, id_parcours)
        return tuple(sid for _, sid in stops)
    except Exception:
        return None