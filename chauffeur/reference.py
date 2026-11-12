#!/usr/bin/env python3
"""Accès aux données de référence (data/reference/).

Pour l'instant : appariement d'un code de point de relève vers son lieu lisible
à partir des fichiers `points_de_releve_<année>.json` (un par année).

Le fichier de l'année de la journée s'applique ; à défaut, le plus récent des
fichiers d'une année antérieure (les points de relève sont reconduits tant que
le transporteur n'en publie pas de nouveaux). Pour une nouvelle année, il suffit
d'ajouter `points_de_releve_<AAAA>.json` : aucun code à modifier.
"""
from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"
_MOTIF_POINTS = re.compile(r"^points_de_releve_(\d{4})\.json$")


def _en_date(jour) -> date:
    """`jour` (date, chaîne ISO ou None) → date ; None ou illisible → aujourd'hui."""
    if isinstance(jour, date):
        return jour
    try:
        return date.fromisoformat(str(jour)[:10])
    except (TypeError, ValueError):
        return date.today()


def fichier_points_releve(jour=None, dossier: Path | None = None) -> Path | None:
    """Fichier de points de relève applicable à `jour`, ou None.

    Année exacte d'abord, sinon la dernière année antérieure disponible ;
    None si tous les fichiers sont d'années postérieures (ou s'il n'y en a pas).
    """
    base = Path(dossier) if dossier else REFERENCE_DIR
    annee = _en_date(jour).year
    candidats = []
    for p in base.glob("points_de_releve_*.json"):
        m = _MOTIF_POINTS.match(p.name)
        if m and int(m.group(1)) <= annee:
            candidats.append((int(m.group(1)), p))
    return max(candidats)[1] if candidats else None


@lru_cache(maxsize=None)
def _garage_index_cache(path_str: str, mtime_ns: int, garage: str) -> dict:
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


def _garage_index(path_str: str, garage: str) -> dict:
    """Index code -> lieu pour un garage (en cache, relu si le fichier change).

    Le code -> lieu est cohérent au sein d'un garage (un même code renvoie
    toujours au même lieu), on peut donc ignorer la ligne.
    """
    try:
        mtime = Path(path_str).stat().st_mtime_ns
    except OSError:
        return {}
    return _garage_index_cache(path_str, mtime, garage)


def lieu_point_releve(code: str, garage: str, path: Path | None = None,
                      jour=None) -> str | None:
    """Lieu lisible correspondant à un code de point de relève, ou None.

    `jour` (date ou « AAAA-MM-JJ ») choisit le fichier de l'année ; absent,
    l'année courante. `path` impose un fichier précis (tests).

    Les codes de la journée portent un suffixe de quai (ex. « V07002 » pour le
    point de référence « V070 », « M14001 » pour « M140 »). Appariement :
    exact d'abord, puis plus long préfixe de référence. Portée : le garage.
    """
    if not code or not garage:
        return None
    p = Path(path) if path else fichier_points_releve(jour)
    if p is None or not p.exists():
        return None
    idx = _garage_index(str(p), garage)
    if code in idx:
        return idx[code]
    best: tuple[str, str] | None = None
    for ref_code, lieu in idx.items():
        if code.startswith(ref_code) and (best is None or len(ref_code) > len(best[0])):
            best = (ref_code, lieu)
    return best[1] if best else None
