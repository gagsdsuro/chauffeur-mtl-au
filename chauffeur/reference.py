#!/usr/bin/env python3
"""Accès aux données de référence (data/reference/).

Pour l'instant : appariement d'un code de point de relève vers son lieu lisible
à partir de `points_de_releve.json`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DEFAULT_POINTS = (
    Path(__file__).resolve().parent.parent
    / "data" / "reference" / "points_de_releve.json"
)


@lru_cache(maxsize=None)
def _garage_index(path_str: str, garage: str) -> dict:
    """Index code -> lieu pour un garage (mis en cache).

    Le code -> lieu est cohérent au sein d'un garage (un même code renvoie
    toujours au même lieu), on peut donc ignorer la ligne.
    """
    try:
        data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    except Exception:
        return {}
    idx: dict = {}
    for entry in data.get("garages", {}).get(garage, []):
        code = entry.get("code")
        lieu = entry.get("lieu")
        if code and lieu:
            idx.setdefault(code, lieu)
    return idx


def lieu_point_releve(code: str, garage: str,
                      path: Path | None = None) -> str | None:
    """Lieu lisible correspondant à un code de point de relève, ou None.

    Les codes de la journée portent un suffixe de quai (ex. « V07002 » pour le
    point de référence « V070 », « M14001 » pour « M140 »). Appariement :
    exact d'abord, puis plus long préfixe de référence. Portée : le garage.
    """
    if not code or not garage:
        return None
    p = Path(path) if path else _DEFAULT_POINTS
    if not p.exists():
        return None
    idx = _garage_index(str(p), garage)
    if code in idx:
        return idx[code]
    best: tuple[str, str] | None = None
    for ref_code, lieu in idx.items():
        if code.startswith(ref_code) and (best is None or len(ref_code) > len(best[0])):
            best = (ref_code, lieu)
    return best[1] if best else None
