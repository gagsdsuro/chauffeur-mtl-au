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
from datetime import datetime
from pathlib import Path

CA_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
TIME_RE    = re.compile(r"^\d{1,2}:\d{2}$")
LINE_RE    = re.compile(r"^(\d+)\s*-\s*P\b")


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

    Format HASTUS (texte extrait de PyMuPDF) :
      - Départ : "23:46STATION ANGRIGNON (BOUCLE NORD)"  (heure collée avant le nom)
      - Arrivée : "TERMINUS DORVAL 24:32"                (heure collée après le nom)

    Retourne { '195': [{'debut': '23:46', 'fin': '24:32',
                        'debut_stop': 'STATION ANGRIGNON (BOUCLE NORD)',
                        'fin_stop': 'TERMINUS DORVAL'}, ...] }
    """
    result: dict = {}
    blocks = re.split(r"\n(?=[a-z]?\d+\s+-\s+P\s+/|hlp\d|GARAGE)", page1_text)

    for block in blocks:
        m_ligne = re.match(r"[a-z]?(\d+)\s+-\s+P\s+/", block)
        if not m_ligne:
            continue
        numero = m_ligne.group(1)

        lines = [l.strip() for l in block.split("\n") if l.strip()]
        debut_time = fin_time = None
        debut_stop = fin_stop = None

        for line in lines[1:]:
            # Départ : heure collée au début → "23:46STATION ANGRIGNON …"
            m = re.match(r"(\d+:\d{2})(.+)", line)
            if m:
                if debut_time is None:
                    debut_time = m.group(1)
                    debut_stop = m.group(2).strip()
                # On continue pour chercher la fin
                continue
            # Arrivée : heure collée à la fin → "TERMINUS DORVAL 24:32"
            m = re.match(r"(.+?)\s*(\d{2}:\d{2})\s*$", line)
            if m:
                fin_stop = m.group(1).strip()
                fin_time = m.group(2)

        if debut_time and fin_time:
            result.setdefault(numero, []).append({
                "debut":      debut_time,
                "fin":        fin_time,
                "debut_stop": debut_stop or "",
                "fin_stop":   fin_stop or "",
            })

    return result


def _norm_stop(name: str) -> str:
    """Normalise un nom d'arrêt pour comparaison (casse, abbréviations, parenthèses)."""
    n = re.sub(r"\s*\([^)]*\)", "", name.upper())
    n = re.sub(r"\bSTE\b", "SAINTE", n)
    n = re.sub(r"\bST\b",  "SAINT",  n)
    return re.sub(r"\s+", " ", n).strip()


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

    # Collecte les (start, end) normalisés de tous les parcours du fichier G-D
    gd_endpoints: list[tuple[str, str]] = []
    for route in gd_data.get("routes", []):
        for parcours in route.get("parcours", []):
            s = _norm_stop(parcours.get("start", ""))
            e = _norm_stop(parcours.get("end",   ""))
            if s and e:
                gd_endpoints.append((s, e))

    if not gd_endpoints:
        return None

    matching: list[dict] = []
    for seg in segments:
        seg_s = _norm_stop(seg["debut_stop"])
        seg_e = _norm_stop(seg["fin_stop"])
        for (gd_s, gd_e) in gd_endpoints:
            s_ok = (seg_s in gd_s) or (gd_s in seg_s)
            e_ok = (seg_e in gd_e) or (gd_e in seg_e)
            if s_ok and e_ok:
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


def get_gtfs_info(data_dir: Path) -> dict:
    """Retourne les métadonnées GTFS statique et RT."""
    static_manifest = data_dir / "gtfs" / "gtfs_manifest.json"
    rt_manifest     = data_dir / "gtfs_rt" / "gtfs_rt_manifest.json"
    rt_pb_path      = data_dir / "gtfs_rt" / "response_vehiclePositions.pb"

    static_ts = "–"
    if static_manifest.exists():
        try:
            m = json.loads(static_manifest.read_text(encoding="utf-8"))
            static_ts = m.get("last_update") or m.get("downloaded_at") or fmt_mtime(static_manifest)
        except Exception:
            static_ts = fmt_mtime(static_manifest)

    rt_ts = "–"
    if rt_manifest.exists():
        try:
            m = json.loads(rt_manifest.read_text(encoding="utf-8"))
            rt_ts = m.get("last_update") or fmt_mtime(rt_manifest)
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
