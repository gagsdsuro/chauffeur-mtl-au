#!/usr/bin/env python3
"""
dashboard.py — Fonctions utilitaires pour l'onglet Tableau de bord.

Extraction de la carte agent STM (PDF), info sur les fichiers de données,
et parsing minimal du flux GTFS-RT vehiclePositions (protobuf).
"""

from __future__ import annotations

import json
import re
import struct
import sys
from datetime import datetime
from pathlib import Path

# Rendre le package `chauffeur/` (noyau de domaine) importable depuis app/.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

CA_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
TIME_RE    = re.compile(r"^\d{1,2}:\d{2}$")
# En-tête de trajet : « 136 - P /  -  / Régulier » ou « 125 /  -  / Régulier ».
# Le « - P » (désignation de voiture, rampe avant) est optionnel ; on ne doit pas
# l'exiger, sinon les lignes sans cette mention (ex. 125) sont ignorées. Exclut les
# numéros de voiture (« 29 - 04 ») et la date (« 11/06/2026 ») qui n'ont pas le « / ».
LINE_RE    = re.compile(r"^[a-z]?(\d+)(?:\s+-\s+\w+)?\s+/")


# ── Carte Agent ──────────────────────────────────────────────────────────────────

def get_available_ca_pdfs(ca_dir: Path) -> list[dict]:
    """Retourne les cartes agent disponibles, triées du plus récent au plus ancien."""
    pdfs = []
    for p in ca_dir.glob("carte-agent-*.pdf"):
        stem = p.stem.lower()
        if "annot" in stem or "surligné" in stem or "annotee" in stem:
            continue
        m = CA_DATE_RE.search(p.name)
        date_str = m.group(1) if m else "0000-00-00"
        pdfs.append({"path": p, "date_str": date_str, "name": p.name})
    pdfs.sort(key=lambda x: x["date_str"], reverse=True)
    return pdfs


def extract_pieces_from_pdf(pdf_path: Path) -> dict | None:
    """
    Extrait les pièces de travail d'une carte agent STM (PDF).
    Retourne {carte, pieces: [{debut, fin}], lignes, line_time_ranges} ou None.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None

    try:
        doc        = fitz.open(str(pdf_path))
        page       = doc[0]
        page1_text = page.get_text()
        spans      = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] == 0:
                for line in block["lines"]:
                    for span in line["spans"]:
                        t = span["text"].strip()
                        if t:
                            spans.append({"text": t, "bbox": span["bbox"]})
        doc.close()
    except Exception:
        return None

    # ── Colonnes Prise ────────────────────────────────────────────────────────
    prise_cols: list[dict] = []
    for s in spans:
        if s["text"] == "Prise":
            x0, _, x1, _ = s["bbox"]
            prise_cols.append({
                "x0": x0,
                "range": (x0 - 6, x1 + 6),
                "entries": [],
            })
    prise_cols.sort(key=lambda c: c["x0"])

    if len(prise_cols) < 2:
        return None

    for col in prise_cols:
        px0, px1 = col["range"]
        for s in spans:
            bx0, by0, bx1, _ = s["bbox"]
            if px0 <= bx0 and bx1 <= px1 and 80 < by0 < 400 and TIME_RE.match(s["text"]):
                col["entries"].append({"time": s["text"], "y": by0})
        col["entries"].sort(key=lambda e: e["y"])

    col0 = prise_cols[0]["entries"]
    col1 = prise_cols[1]["entries"]
    n    = min(len(col0), len(col1))
    pieces = [{"debut": col0[i]["time"], "fin": col1[i]["time"]} for i in range(n)]

    # ── Numéros de ligne ──────────────────────────────────────────────────────
    lignes: list[str] = []
    for s in spans:
        m = LINE_RE.match(s["text"])
        if m and m.group(1) not in lignes:
            lignes.append(m.group(1))

    # ── Numéro de carte ───────────────────────────────────────────────────────
    carte_num = "?"
    for s in spans:
        if s["bbox"][1] < 130 and re.match(r"^\d{3,6}$", s["text"]):
            carte_num = s["text"]
            break

    return {
        "carte":            carte_num,
        "pieces":           pieces,
        "lignes":           lignes,
        "line_time_ranges": extract_line_time_ranges(page1_text),
    }


# ── Extraction des plages horaires par ligne depuis le texte de la carte agent ──

def _to_min(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def extract_line_time_ranges(page1_text: str) -> dict:
    """
    Extrait les plages horaires (début/fin) par ligne, avec stops de départ/arrivée.

    Format PyMuPDF (fitz) pour une carte agent HASTUS :
      - Les heures sont sur leurs propres lignes : "23:46"
      - Les noms d'arrêts sont sur leurs propres lignes : "TERMINUS DORVAL"
      - Exception : quand le nom est trop long, l'heure est collée à la fin :
        "SHERBROOKE / MEADOWBROOK (Dir. O24:22"

    Retourne { '195': [{'debut': '23:46', 'fin': '24:32',
                        'debut_stop': 'STATION ANGRIGNON',
                        'fin_stop': 'TERMINUS DORVAL'}, ...] }
    """
    # En-tête de trajet : « 168 /  -  / Régulier » ou « 168 - P /  -  / Régulier ».
    # Le « - P » (ou « - 05 », etc.) est une désignation de voiture optionnelle, pas
    # toujours présente ; on ne doit donc pas l'exiger pour reconnaître un trajet.
    _trip_header = r"[a-z]?\d+(?:\s+-\s+\w+)?\s+/"
    result: dict = {}
    blocks = re.split(rf"\n(?={_trip_header}|hlp\d|GARAGE)", page1_text)

    _pure_time = re.compile(r"^\d{1,2}:\d{2}$")
    _end_time  = re.compile(r"^(.+?)\s*(\d{2}:\d{2})$")

    for block in blocks:
        m_ligne = re.match(r"[a-z]?(\d+)(?:\s+-\s+\w+)?\s+/", block)
        if not m_ligne:
            continue
        numero = m_ligne.group(1)

        lines = [l.strip() for l in block.split("\n") if l.strip()]

        # Construit une liste structurée d'items
        items: list[dict] = []
        for line in lines[1:]:      # skip the "XX - P / ..." header
            if _pure_time.match(line):
                items.append({"type": "time", "time": line, "stop": None})
            else:
                m = _end_time.match(line)
                if m:
                    items.append({"type": "stop_time",
                                  "time": m.group(2),
                                  "stop": m.group(1).strip()})
                else:
                    items.append({"type": "stop", "time": None, "stop": line})

        # Collecte tous les temps dans l'ordre d'apparition
        timed = [(i, it["time"]) for i, it in enumerate(items) if it["time"]]
        if len(timed) < 2:
            continue

        debut_i, debut_time = timed[0]
        fin_i,   fin_time   = timed[-1]

        # Stop de départ : premier item de type stop après la première heure
        debut_stop = None
        for j in range(debut_i + 1, len(items)):
            if items[j]["stop"] and len(items[j]["stop"]) > 2:
                debut_stop = items[j]["stop"]
                break
        # Si le premier item est stop_time, son stop est le stop de départ
        if items[debut_i]["type"] == "stop_time":
            debut_stop = items[debut_i]["stop"]

        # Stop d'arrivée : dernier item de type stop avant la dernière heure
        fin_stop = None
        if items[fin_i]["type"] == "stop_time":
            fin_stop = items[fin_i]["stop"]
        else:
            for j in range(fin_i - 1, -1, -1):
                if items[j]["stop"] and len(items[j]["stop"]) > 2:
                    fin_stop = items[j]["stop"]
                    break

        if debut_time and fin_time:
            result.setdefault(numero, []).append({
                "debut":      debut_time,
                "fin":        fin_time,
                "debut_stop": debut_stop or "",
                "fin_stop":   fin_stop or "",
            })

    return result


# Appariement de noms d'arrêts : source de vérité dans chauffeur/matching.py.
from chauffeur.matching import stops_match as _stops_match  # noqa: E402


def get_time_range_for_direction(
    gd_path: Path,
    segments: list[dict],
) -> tuple[str, str] | None:
    """
    Associe les segments de la carte agent à un fichier G-D en comparant les noms
    de terminus (départ / arrivée). Retourne (heure_debut_min, heure_fin_max) ou None.
    """
    if not segments:
        return None

    try:
        gd_data = json.loads(gd_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Collecte les (start, end) de tous les parcours du fichier G-D
    gd_endpoints: list[tuple[str, str]] = []
    for route in gd_data.get("routes", []):
        for parcours in route.get("parcours", []):
            s = parcours.get("start", "")
            e = parcours.get("end",   "")
            if s and e:
                gd_endpoints.append((s, e))

    if not gd_endpoints:
        return None

    matching: list[dict] = []
    for seg in segments:
        for (gd_s, gd_e) in gd_endpoints:
            if _stops_match(seg["debut_stop"], gd_s) and _stops_match(seg["fin_stop"], gd_e):
                matching.append(seg)
                break

    if not matching:
        return None

    debut = min(matching, key=lambda s: _to_min(s["debut"]))["debut"]
    fin   = max(matching, key=lambda s: _to_min(s["fin"]))["fin"]
    return debut, fin


# ── Fichiers de données ──────────────────────────────────────────────────────────

def fmt_mtime(path: Path) -> str:
    """Retourne la date/heure de modification du fichier, ou '–' s'il n'existe pas."""
    if not path.exists():
        return "–"
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return mtime.strftime("%Y-%m-%d %H:%M")


def get_gd_files_for_ligne(ligne: str, data_dir: Path) -> list[dict]:
    """Trouve tous les fichiers G-D d'une ligne (toutes directions)."""
    gd_dir = data_dir / "Gauche-Droite"
    results = []
    for direction in ("est", "ouest", "nord", "sud"):
        p = gd_dir / f"gd{ligne}_{direction}.json"
        if p.exists():
            results.append({"direction": direction, "path": p, "mtime": fmt_mtime(p)})
    return results


def get_event_file_mtime(ligne: str, direction: str, data_dir: Path) -> str:
    return fmt_mtime(data_dir / "Events" / f"{ligne}_{direction}.json")


def fmt_iso(value: str) -> str:
    """Formate un horodatage ISO 8601 en 'YYYY-MM-DD HH:MM', ou retourne la valeur brute."""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return value


def get_gtfs_info(data_dir: Path) -> dict:
    """Retourne les métadonnées GTFS statique et RT."""
    static_manifest = data_dir / "gtfs" / "gtfs_manifest.json"
    rt_manifest     = data_dir / "gtfs_rt" / "gtfs_rt_manifest.json"
    rt_pb_path      = data_dir / "gtfs_rt" / "response_vehiclePositions.pb"

    static_ts = "–"
    if static_manifest.exists():
        try:
            m = json.loads(static_manifest.read_text(encoding="utf-8"))
            static_ts = fmt_iso(m.get("last_update") or m.get("downloaded_at")) if (m.get("last_update") or m.get("downloaded_at")) else fmt_mtime(static_manifest)
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
        "static_ts": static_ts,
        "rt_ts":     rt_ts,
        "rt_pb":     rt_pb_path,
        "rt_avail":  rt_pb_path.exists(),
    }


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


def _parse_vp(data: bytes) -> dict | None:
    route_id = None; lat = lon = None; v_id = v_label = None
    for fnum, wtype, val in _iter_fields(data):
        if fnum == 1 and wtype == 2:
            route_id = _parse_trip_desc(val)
        elif fnum == 3 and wtype == 2:
            lat, lon = _parse_position(val)
        elif fnum == 4 and wtype == 2:
            v_id, v_label = _parse_vehicle_desc(val)
    if lat is not None and lon is not None:
        return {"v_id": v_id, "v_label": v_label, "lat": lat, "lon": lon, "route_id": route_id}
    return None


def parse_vehicle_positions(pb_data: bytes) -> list[dict]:
    """Parse un flux GTFS-RT vehiclePositions (protobuf). Retourne la liste des véhicules."""
    vehicles = []
    for fnum, wtype, val in _iter_fields(pb_data):
        if fnum == 2 and wtype == 2:   # FeedEntity
            for f2, w2, v2 in _iter_fields(val):
                if f2 == 4 and w2 == 2:   # VehiclePosition
                    vp = _parse_vp(v2)
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
