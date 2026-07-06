#!/usr/bin/env python3
"""
dashboard.py — Fonctions utilitaires pour l'onglet Tableau de bord.

Info sur les fichiers de données GTFS et parsing minimal du flux
GTFS-RT vehiclePositions (protobuf).
"""

from __future__ import annotations

import json
import re
import struct
import sys
from datetime import date as _date, datetime, timezone
from pathlib import Path

# Rendre le package `chauffeur/` (noyau de domaine) importable depuis app/.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chauffeur.periodes import identite_ca, nom_ca  # noqa: E402


# ── Fichiers de données ──────────────────────────────────────────────────────────

def fmt_mtime(path: Path) -> str:
    """Retourne la date/heure de modification du fichier, ou '–' s'il n'existe pas."""
    if not path.exists():
        return "–"
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return mtime.strftime("%Y-%m-%d %H:%M")


def fmt_iso(value: str) -> str:
    """Formate un horodatage ISO 8601 en 'YYYY-MM-DD HH:MM', ou retourne la valeur brute."""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return value


def get_gtfs_info(data_dir: Path) -> dict:
    """Retourne les métadonnées GTFS statique et RT.

    Champs retournés :
      static_ts       — date lisible du dernier téléchargement (str)
      static_age_days — âge en jours entiers (int) ou None si inconnu
      rt_ts           — date lisible du dernier RT (str)
      rt_pb           — chemin du fichier protobuf RT (Path)
      rt_avail        — True si le fichier RT existe (bool)
    """
    static_manifest = data_dir / "gtfs" / "gtfs_manifest.json"
    rt_manifest     = data_dir / "gtfs_rt" / "gtfs_rt_manifest.json"
    rt_pb_path      = data_dir / "gtfs_rt" / "response_vehiclePositions.pb"

    static_ts       = "–"
    static_age_days = None
    if static_manifest.exists():
        try:
            m = json.loads(static_manifest.read_text(encoding="utf-8"))
            raw_date = m.get("last_update") or m.get("downloaded_at")
            if raw_date:
                static_ts = fmt_iso(raw_date)
                try:
                    dt = datetime.fromisoformat(raw_date)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    static_age_days = (datetime.now(timezone.utc) - dt).days
                except Exception:
                    pass
            else:
                static_ts = fmt_mtime(static_manifest)
        except Exception:
            static_ts = fmt_mtime(static_manifest)

    rt_ts = "–"
    if rt_manifest.exists():
        try:
            m = json.loads(rt_manifest.read_text(encoding="utf-8"))
            rt_ts = fmt_iso(m["last_update"]) if m.get("last_update") else fmt_mtime(rt_manifest)
        except Exception:
            rt_ts = fmt_mtime(rt_manifest)

    return {
        "static_ts":       static_ts,
        "static_age_days": static_age_days,
        "rt_ts":           rt_ts,
        "rt_pb":           rt_pb_path,
        "rt_avail":        rt_pb_path.exists(),
    }


def get_gd_info(gd_dir: Path, ligne: str, direction: str,
                max_age_days: int = 90) -> dict:
    """Info de fraîcheur d'un fichier Gauche-Droite (miroir de get_gtfs_info).

    Les JSON G-D ne contiennent aucune date : la fraîcheur est basée sur le
    mtime du fichier. Un fichier ré-importé sans changement paraîtra « frais ».

    Convention de nommage : gd<ligne>_<direction>.json (direction minuscule).

    Champs retournés :
      exists    — True si le fichier existe (bool)
      path      — chemin du fichier (Path) ou None
      age_days  — âge en jours entiers (int) ou None si absent
      fresh     — True si présent et age_days <= max_age_days (bool)
    """
    path = gd_dir / f"gd{ligne}_{(direction or '').lower()}.json"
    if not path.exists():
        return {"exists": False, "path": None, "age_days": None, "fresh": False}
    age_days = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).days
    return {
        "exists":   True,
        "path":     path,
        "age_days": age_days,
        "fresh":    age_days <= max_age_days,
    }


def get_ca_info(ca_dir: Path, jour: _date, numero) -> dict:
    """Résout le PDF de carte agent (brute + annotée) applicable à une journée.

    Cherche d'abord par identité (chauffeur.periodes.identite_ca) — ce qui permet
    la réutilisation d'une même CA entre journées partageant numéro/liste/jour-type.
    Si absent, replie sur l'ancien nommage par date (carte-agent-YYYY-MM-DD[-annotee|
    -surligné].pdf), pour les CA importées avant la refonte par identité.

    Champs retournés :
      identite — (numero, groupe_id, jour_type) ou None si non calculable
      brute    — Path du PDF brut, ou None
      annotee  — Path du PDF annoté, ou None
      legacy   — True si le PDF annoté résolu vient de l'ancien nommage par date
    """
    date_str = jour.isoformat()
    identite = None
    brute = annotee = None

    if numero:
        try:
            identite = identite_ca(jour, str(numero))
        except (FileNotFoundError, ValueError):
            identite = None

    if identite:
        n, g, j = identite
        p_brute = ca_dir / nom_ca(n, g, j)
        p_annotee = ca_dir / nom_ca(n, g, j, annotee=True)
        if p_brute.exists():
            brute = p_brute
        if p_annotee.exists():
            annotee = p_annotee

    legacy = False
    if annotee is None:
        for suffixe in ("-annotee", "-surligné"):
            p = ca_dir / f"carte-agent-{date_str}{suffixe}.pdf"
            if p.exists():
                annotee, legacy = p, True
                break
    if brute is None:
        p = ca_dir / f"carte-agent-{date_str}.pdf"
        if p.exists():
            brute = p

    return {"identite": identite, "brute": brute, "annotee": annotee, "legacy": legacy}


# ── GTFS-RT — parser protobuf minimal ───────────────────────────────────────────

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


def _parse_vehicle_desc(data: bytes) -> tuple[str | None, str | None]:
    v_id = v_label = None
    for fnum, wtype, val in _iter_fields(data):
        if fnum == 1 and wtype == 2:
            v_id = _str(val)
        elif fnum == 2 and wtype == 2:
            v_label = _str(val)
    return v_id, v_label


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
