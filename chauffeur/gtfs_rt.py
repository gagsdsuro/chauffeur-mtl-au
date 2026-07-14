"""chauffeur.gtfs_rt — décodeur minimal du flux GTFS-RT vehiclePositions (protobuf).

Décodage wire-format sans dépendance protobuf, adapté aux particularités STM :
la position est au field 2 (pas field 3 du standard GTFS-RT), aucun
VehicleDescriptor n'est envoyé — l'ID du bus est FeedEntity.id.
Fonctions pures sur bytes (anciennement dans app/dashboard.py).
"""
from __future__ import annotations

import re
import struct


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
    return result, pos


def _iter_fields(data: bytes):
    """Itère sur les champs d'un message protobuf (wire-format minimal)."""
    pos = 0
    while pos < len(data):
        try:
            tag, pos = _read_varint(data, pos)
        except Exception:
            break
        field_num = tag >> 3
        wire_type = tag & 0x7
        try:
            if wire_type == 0:          # varint
                val, pos = _read_varint(data, pos)
            elif wire_type == 1:        # 64-bit fixé
                val = data[pos:pos+8]; pos += 8
            elif wire_type == 2:        # longueur + contenu
                length, pos = _read_varint(data, pos)
                val = data[pos:pos+length]; pos += length
            elif wire_type == 5:        # 32-bit fixé (float)
                val = data[pos:pos+4]; pos += 4
            else:
                break
        except Exception:
            break
        yield field_num, wire_type, val


def _str(b: bytes) -> str:
    return b.decode("utf-8", errors="replace")


def _parse_trip_desc(data: bytes) -> str | None:
    for fnum, wtype, val in _iter_fields(data):
        if fnum == 5 and wtype == 2:   # route_id
            return _str(val)
    return None


def _parse_position(data: bytes) -> tuple[float | None, float | None]:
    lat = lon = None
    for fnum, wtype, val in _iter_fields(data):
        if fnum == 1 and wtype == 5:
            lat = struct.unpack("<f", val)[0]
        elif fnum == 2 and wtype == 5:
            lon = struct.unpack("<f", val)[0]
    return lat, lon


def _parse_vp(data: bytes, entity_id: str | None = None) -> dict | None:
    # STM encode la position au field 2 (pas field 3 du standard GTFS-RT)
    # et n'envoie pas de VehicleDescriptor ; l'ID du bus est FeedEntity.id
    route_id = None; lat = lon = None; v_label = None
    for fnum, wtype, val in _iter_fields(data):
        if fnum == 1 and wtype == 2:
            route_id = _parse_trip_desc(val)
        elif fnum == 2 and wtype == 2:   # Position (field 2 dans les données STM)
            lat, lon = _parse_position(val)
        elif fnum == 7 and wtype == 2:   # label interne STM
            v_label = _str(val)
    if lat is not None and lon is not None:
        return {"v_id": entity_id, "v_label": v_label, "lat": lat, "lon": lon, "route_id": route_id}
    return None


def parse_vehicle_positions(pb_data: bytes) -> list[dict]:
    """Parse un flux GTFS-RT vehiclePositions (protobuf). Retourne la liste des véhicules."""
    vehicles = []
    for fnum, wtype, val in _iter_fields(pb_data):
        if fnum == 2 and wtype == 2:   # FeedEntity
            entity_id = None
            vp_data = None
            for f2, w2, v2 in _iter_fields(val):
                if f2 == 1 and w2 == 2:
                    entity_id = _str(v2)
                elif f2 == 4 and w2 == 2:   # VehiclePosition
                    vp_data = v2
            if vp_data is not None:
                vp = _parse_vp(vp_data, entity_id)
                if vp:
                    vehicles.append(vp)
    return vehicles


def find_vehicle(bus_number: str, vehicles: list[dict]) -> dict | None:
    """Trouve un véhicule par son numéro (label ou id). Normalise le format xx-xxx."""
    bus_norm = re.sub(r"[-\s]", "", bus_number).lower()
    for v in vehicles:
        label = re.sub(r"[-\s]", "", v.get("v_label") or "").lower()
        vid   = re.sub(r"[-\s]", "", v.get("v_id")    or "").lower()
        if label == bus_norm or vid == bus_norm:
            return v
    return None
