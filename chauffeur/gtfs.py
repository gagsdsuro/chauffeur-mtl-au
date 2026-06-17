"""chauffeur.gtfs — accès GTFS statique (repository, dossier injecté).

Anciennement des fonctions globales de rapport_gd.py liées à une variable GTFS
module. Ici le dossier GTFS est passé en paramètre → testable et réutilisable.
"""
from __future__ import annotations

import csv
from pathlib import Path


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

    Si shape_hint est fourni (ex. '24_3'), filtre d'abord les trips de cette
    shape. Repli sur tous les trips si aucun trip ne correspond au shape_hint.
    """
    gtfs_dir = Path(gtfs_dir)
    trip_ids: set[str] = set()
    with open(gtfs_dir / "trips.txt") as f:
        for r in csv.DictReader(f):
            if r["route_id"] == route_id and r["direction_id"] == dir_id:
                if shape_hint is None or r["shape_id"] == shape_hint:
                    trip_ids.add(r["trip_id"])

    # Repli : aucun trip pour ce shape (variante inactive) → tous les trips
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


def stop_names(gtfs_dir: Path) -> dict:
    stops = {}
    with open(Path(gtfs_dir) / "stops.txt") as f:
        for r in csv.DictReader(f):
            stops[r["stop_id"]] = {"code": r["stop_code"], "name": r["stop_name"]}
    return stops
