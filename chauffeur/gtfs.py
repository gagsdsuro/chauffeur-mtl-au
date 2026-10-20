"""chauffeur.gtfs — accès GTFS statique (repository, dossier injecté).

Anciennement des fonctions globales de rapport_gd.py liées à une variable GTFS
module. Ici le dossier GTFS est passé en paramètre → testable et réutilisable.

Performance : `build_stops_index()` construit stops_index.json à l'import GTFS
(lecture unique de stop_times.txt). `stops_for_line()` utilise cet index si
présent (< 50 ms) plutôt que de rescanner les 7 M lignes de stop_times.txt.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

# Cache mémoire : évite de relire stops_index.json à chaque appel dans le
# même processus (Streamlit, rapport multi-groupes). Clé = (dossier, date de
# modification du fichier) : une mise à jour GTFS faite par un AUTRE processus
# (fetch_gtfs.py, cron) est prise en compte au prochain appel — sans quoi
# l'app servait l'ancienne séquence d'arrêts avec les nouveaux noms.
_idx_cache: dict | None = None
_idx_cache_dir: Path | None = None
_idx_cache_mtime: int | None = None


def _load_index(gtfs_dir: Path) -> dict | None:
    """Charge stops_index.json en mémoire (cache invalidé si le fichier change)."""
    global _idx_cache, _idx_cache_dir, _idx_cache_mtime
    index_path = gtfs_dir / "stops_index.json"
    try:
        mtime = index_path.stat().st_mtime_ns
    except OSError:
        return None
    if _idx_cache is None or _idx_cache_dir != gtfs_dir or _idx_cache_mtime != mtime:
        _idx_cache = json.loads(index_path.read_text(encoding="utf-8"))
        _idx_cache_dir = gtfs_dir
        _idx_cache_mtime = mtime
    return _idx_cache


def route_id(gtfs_dir: Path, ligne: str) -> str:
    with open(Path(gtfs_dir) / "routes.txt") as f:
        for r in csv.DictReader(f):
            if r["route_short_name"] == ligne:
                return r["route_id"]
    raise ValueError(f"Ligne {ligne} introuvable dans GTFS")


def direction_id(gtfs_dir: Path, route_id: str, direction: str) -> str:
    # Limite de mot (\b) : évite que "est" matche dans "ouest"
    import re
    pattern = re.compile(r'\b' + re.escape(direction.lower()) + r'\b', re.IGNORECASE)
    seen = {}
    with open(Path(gtfs_dir) / "trips.txt") as f:
        for r in csv.DictReader(f):
            if r["route_id"] == route_id:
                seen[r["direction_id"]] = r["trip_headsign"]
                if pattern.search(r["trip_headsign"]):
                    return r["direction_id"]
    raise ValueError(f"Direction '{direction}' introuvable. Disponibles: {seen}")


def stops_for_line(gtfs_dir: Path, route_id: str, dir_id: str,
                   shape_hint: str | None = None) -> list:
    """Retourne la séquence d'arrêts du trip le plus long pour la ligne/direction.

    Utilise stops_index.json si disponible (< 50 ms), sinon scanne stop_times.txt.
    Si shape_hint est fourni (ex. '24_3'), filtre d'abord les trips de cette
    shape. Repli sur tous les trips si aucun trip ne correspond au shape_hint.
    """
    gtfs_dir = Path(gtfs_dir)
    index = _load_index(gtfs_dir)
    if index is not None:
        if shape_hint:
            skey = f"{route_id}|{dir_id}|{shape_hint}"
            if skey in index:
                return [tuple(x) for x in index[skey]]
        key = f"{route_id}|{dir_id}"
        if key in index:
            return [tuple(x) for x in index[key]]
        # shape_hint inconnu → repli sans shape
        if shape_hint:
            key = f"{route_id}|{dir_id}"
            if key in index:
                return [tuple(x) for x in index[key]]
        return []

    # Repli CSV — chemin lent (stops_index.json absent)
    trip_ids: set[str] = set()
    with open(gtfs_dir / "trips.txt") as f:
        for r in csv.DictReader(f):
            if r["route_id"] == route_id and r["direction_id"] == dir_id:
                if shape_hint is None or r["shape_id"] == shape_hint:
                    trip_ids.add(r["trip_id"])

    if not trip_ids and shape_hint:
        return stops_for_line(gtfs_dir, route_id, dir_id, shape_hint=None)

    trip_stops: dict = {}
    with open(gtfs_dir / "stop_times.txt") as f:
        for r in csv.DictReader(f):
            if r["trip_id"] in trip_ids:
                trip_stops.setdefault(r["trip_id"], []).append(
                    (int(r["stop_sequence"]), r["stop_id"])
                )

    best = max(trip_stops, key=lambda t: len(trip_stops[t]))
    return [(seq, sid) for seq, sid in sorted(trip_stops[best])]


def stops_for_parcours(gtfs_dir: Path, ligne: str, direction: str,
                       id_parcours=None) -> list:
    """Séquence d'arrêts [(seq, stop_id), …] d'un parcours (ligne/direction/id).

    Encapsule la résolution route_id → direction_id → stops_for_line avec le
    shape_hint "<ligne>_<id_parcours>". Lève ValueError/OSError si la ligne ou
    la direction est introuvable — le repli (fail-safe ou liste vide) est la
    décision du consommateur.
    """
    rid   = route_id(gtfs_dir, ligne)
    did   = direction_id(gtfs_dir, rid, direction)
    shape = f"{ligne}_{id_parcours}" if id_parcours is not None else None
    return stops_for_line(gtfs_dir, rid, did, shape_hint=shape)


def stop_names(gtfs_dir: Path) -> dict:
    stops = {}
    with open(Path(gtfs_dir) / "stops.txt") as f:
        for r in csv.DictReader(f):
            stops[r["stop_id"]] = {"code": r["stop_code"], "name": r["stop_name"]}
    return stops


def build_stops_index(gtfs_dir: Path) -> Path:
    """Construit stops_index.json : scan unique de trips.txt + stop_times.txt.

    Clés :
      "{route_id}|{dir_id}"             → meilleure séquence toutes shapes
      "{route_id}|{dir_id}|{shape_id}"  → meilleure séquence pour cette shape

    Valeur : [[seq, stop_id], ...] trié par seq.
    Retourne le chemin du fichier écrit.
    """
    global _idx_cache, _idx_cache_dir, _idx_cache_mtime
    gtfs_dir = Path(gtfs_dir)

    # Étape 1 : trips.txt → trip_id → (route_id, dir_id, shape_id)
    trip_meta: dict[str, tuple[str, str, str]] = {}
    with open(gtfs_dir / "trips.txt") as f:
        for r in csv.DictReader(f):
            trip_meta[r["trip_id"]] = (r["route_id"], r["direction_id"], r["shape_id"])

    # Étape 2 : stop_times.txt → trip_id → [(seq, stop_id)]  (scan unique)
    trip_stops: dict[str, list] = {}
    with open(gtfs_dir / "stop_times.txt") as f:
        for r in csv.DictReader(f):
            tid = r["trip_id"]
            if tid in trip_meta:
                trip_stops.setdefault(tid, []).append(
                    [int(r["stop_sequence"]), r["stop_id"]]
                )

    # Étape 3 : trier chaque séquence + sélectionner le trip le plus long par groupe
    index: dict[str, list] = {}
    for tid, stops in trip_stops.items():
        stops.sort()
        route_id, dir_id, shape_id = trip_meta[tid]

        key  = f"{route_id}|{dir_id}"
        skey = f"{route_id}|{dir_id}|{shape_id}"

        if key not in index or len(stops) > len(index[key]):
            index[key] = stops
        if skey not in index or len(stops) > len(index[skey]):
            index[skey] = stops

    # Étape 4 : écrire l'index (JSON compact — pas d'indentation)
    index_path = gtfs_dir / "stops_index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=True), encoding="utf-8")

    # Invalider le cache mémoire
    _idx_cache = None
    _idx_cache_dir = None
    _idx_cache_mtime = None

    return index_path
