#!/usr/bin/env python3
"""
Rapport détaillé G-D / Arrêts / Détours STM
Usage: python rapport_gd.py --ligne 195 --direction ouest --date 2026-06-07 [--format html|md]
"""

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser(description="Rapport G-D / Arrêts / Détours STM")
    p.add_argument("--ligne", required=True, help="Numéro de ligne (ex: 195)")
    p.add_argument("--direction", required=True, choices=["est", "ouest", "nord", "sud"])
    p.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    p.add_argument("--format", default="html", choices=["html", "md"])
    p.add_argument("--base", default=None,
                   help="Chemin racine du projet STM (défaut: dossier parent du script)")
    return p.parse_args()


def get_route_id(ligne):
    with open(GTFS / "routes.txt") as f:
        for r in csv.DictReader(f):
            if r["route_short_name"] == ligne:
                return r["route_id"]
    raise ValueError(f"Ligne {ligne} introuvable dans GTFS")


def get_direction_id(route_id, direction):
    label = direction.capitalize()
    seen = {}
    with open(GTFS / "trips.txt") as f:
        for r in csv.DictReader(f):
            if r["route_id"] == route_id:
                seen[r["direction_id"]] = r["trip_headsign"]
                if label.lower() in r["trip_headsign"].lower():
                    return r["direction_id"]
    raise ValueError(f"Direction '{direction}' introuvable. Disponibles: {seen}")


def get_stops_for_line(route_id, dir_id):
    trip_ids = set()
    with open(GTFS / "trips.txt") as f:
        for r in csv.DictReader(f):
            if r["route_id"] == route_id and r["direction_id"] == dir_id:
                trip_ids.add(r["trip_id"])

    trip_stops = {}
    with open(GTFS / "stop_times.txt") as f:
        for r in csv.DictReader(f):
            if r["trip_id"] in trip_ids:
                trip_stops.setdefault(r["trip_id"], []).append(
                    (int(r["stop_sequence"]), r["stop_id"])
                )

    best = max(trip_stops, key=lambda t: len(trip_stops[t]))
    return [(seq, sid) for seq, sid in sorted(trip_stops[best])]


def load_stop_names():
    stops = {}
    with open(GTFS / "stops.txt") as f:
        for r in csv.DictReader(f):
            stops[r["stop_id"]] = {"code": r["stop_code"], "name": r["stop_name"]}
    return stops


def load_gd(ligne, direction, base):
    path = base / f"data/Gauche-Droite/gd{ligne}_{direction}.json"
    if not path.exists():
        return [], None
    with open(path) as f:
        data = json.load(f)
    routes = data.get("routes", [])
    if not routes:
        return [], None
    parcours = routes[0].get("parcours", [{}])[0]
    return parcours.get("direction", []), parcours


def load_events(ligne, direction, date_str, base):
    path = base / f"data/Events/{ligne}_{direction}.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    active = []
    for e in data.get("detours", []):
        debut = e.get("date_heure_debut")
        fin = e.get("date_heure_fin")
        if debut and datetime.fromisoformat(debut).date() > target:
            continue
        if fin and datetime.fromisoformat(fin).date() < target:
            continue
        active.append(e)
    return active


def extract_street(instruction):
    """'Gauche - Lafleur' → 'lafleur'"""
    parts = instruction.split(" - ", 1)
    return parts[1].strip().lower() if len(parts) == 2 else instruction.lower()


def build_rows(gd_instructions, stops_ordered, stop_names):
    """
    Align G-D instructions with GTFS stops by street name matching.
    Returns list of dicts: {gd, seq, stop_id, stop_name, stop_code}
    """
    rows = []
    stop_idx = 0
    n_stops = len(stops_ordered)

    for i, instr in enumerate(gd_instructions):
        street = extract_street(instr)
        # Via instructions often don't have stops — skip "via" with no match
        is_via = instr.lower().startswith("via")

        # Collect stops whose name contains this street
        matched = []
        tmp_idx = stop_idx
        while tmp_idx < n_stops:
            seq, sid = stops_ordered[tmp_idx]
            name = stop_names.get(sid, {}).get("name", "").lower()
            if street in name:
                matched.append((seq, sid))
                tmp_idx += 1
            else:
                # Peek ahead: if next G-D instruction matches this stop, stop
                break

        if matched:
            stop_idx = tmp_idx
            rows.append({"gd": instr, "seq": matched[0][0], "stop_id": matched[0][1]})
            for seq, sid in matched[1:]:
                rows.append({"gd": "", "seq": seq, "stop_id": sid})
        else:
            rows.append({"gd": instr, "seq": None, "stop_id": None})

    # Remaining unmatched stops
    while stop_idx < n_stops:
        seq, sid = stops_ordered[stop_idx]
        rows.append({"gd": "", "seq": seq, "stop_id": sid})
        stop_idx += 1

    # Enrich with names
    for r in rows:
        if r["stop_id"]:
            s = stop_names.get(r["stop_id"], {})
            r["stop_code"] = s.get("code", "")
            r["stop_name"] = s.get("name", "")
        else:
            r["stop_code"] = ""
            r["stop_name"] = ""
    return rows


def annotate_events(rows, events):
    """Add event annotations to rows."""
    cancelled_ids = {}  # stop_id -> list of event descriptions
    added = []          # list of added stops with descriptions

    for e in events:
        titre = e.get("titre", "")
        motif = e.get("motif", "")
        desc = e.get("description_gd", "") or ""
        commentaire = e.get("commentaire", "") or ""
        label = f"{titre} ({motif})"
        if desc:
            label += f" — G-D: {desc}"
        if commentaire:
            label += f" — {commentaire}"

        for a in e.get("arrets_annules", []):
            cancelled_ids.setdefault(a["id"], []).append(label)
        for a in e.get("arrets_ajoutes", []):
            name = a if isinstance(a, str) else a.get("nom", "")
            added.append({"name": name, "label": label})

    for r in rows:
        sid = r.get("stop_id")
        if sid and sid in cancelled_ids:
            r["cancelled"] = cancelled_ids[sid]
        else:
            r["cancelled"] = []
    return rows, added


# ── Intégration G-D des détours ──────────────────────────────────────────────

# Marqueur « retour au régulier »
_RR_RE = re.compile(r'^R[.\s]?R\.?$', re.IGNORECASE)

def parse_description_gd(desc: str):
    """
    Tente de parser une description_gd en liste d'instructions normalisées.
    Retourne une liste ["Via - X", "Gauche - Y", ...] si le texte suit le
    pattern VIA/G/D, sinon None (texte libre → garder en note).
    """
    if not desc:
        return None
    # Doit contenir au moins un marqueur directionnel suivi d'un mot
    if not re.search(r'\b(VIA\s+\w|G[/.\s]\w|D[/.\s]\w)', desc, re.IGNORECASE):
        return None

    # Multi-ligne : chaque ligne est une instruction
    if '\n' in desc:
        raw = [l.strip() for l in desc.split('\n') if l.strip()]
    else:
        # Ligne unique : découper à chaque nouveau marqueur directionnel
        raw = re.split(r'(?=\bVIA\b|\bG[/.\s]|\bD[/.\s])', desc.strip(), flags=re.IGNORECASE)
        raw = [p.strip() for p in raw if p.strip()]

    instructions = []
    for part in raw:
        part = part.strip().rstrip('.')
        m = re.match(r'^VIA\s+(.+)$', part, re.IGNORECASE)
        if m:
            text = m.group(1).strip()
            instructions.append("Via - R.R." if _RR_RE.match(text) else f"Via - {text}")
            continue
        m = re.match(r'^G[/.\s]\s*(.+)$', part, re.IGNORECASE)
        if m:
            instructions.append(f"Gauche - {m.group(1).strip()}")
            continue
        m = re.match(r'^D[/.\s]\s*(.+)$', part, re.IGNORECASE)
        if m:
            instructions.append(f"Droite - {m.group(1).strip()}")
            continue
        # Partie non reconnue : inclure comme Via
        instructions.append(f"Via - {part}")

    return instructions if instructions else None


def apply_gd_detours(rows: list, events: list) -> list:
    """
    Pour chaque événement dont la description_gd est parseable :
      • Insère les étapes du détour avant le premier arrêt annulé  (detour_added=True)
      • Marque les instructions G-D régulières contournées          (detour_removed=True)
    Les arrêts annulés sont déjà marqués par annotate_events().
    """
    for event in events:
        desc = event.get("description_gd") or ""
        instructions = parse_description_gd(desc)
        if not instructions:
            continue

        cancelled_codes = {a["id"] for a in event.get("arrets_annules", [])}

        # Positions des arrêts annulés dans rows (par stop_code)
        cancelled_positions = [
            i for i, r in enumerate(rows)
            if r.get("stop_code") in cancelled_codes
        ]

        if cancelled_positions:
            first_pos = cancelled_positions[0]
            last_pos  = cancelled_positions[-1]
        else:
            first_pos = 0
            last_pos  = -1

        # Marquer les instructions G-D régulières contournées
        # = lignes GD sans arrêt (ou avec un arrêt non annulé) entre first et last
        if last_pos >= first_pos:
            for i in range(first_pos, last_pos + 1):
                r = rows[i]
                if (r.get("gd")
                        and not r.get("detour_added")
                        and r.get("stop_code", "") not in cancelled_codes):
                    r["detour_removed"] = True

        # Construire les lignes de détour à insérer
        label = event.get("titre", "")
        detour_rows = [
            {
                "gd": instr,
                "seq": None,
                "stop_id": None,
                "stop_code": "",
                "stop_name": "",
                "cancelled": [],
                "detour_added": True,
                "detour_label": label if i == 0 else "",
            }
            for i, instr in enumerate(instructions)
        ]

        rows = rows[:first_pos] + detour_rows + rows[first_pos:]

    return rows


# ── Output formatters ────────────────────────────────────────────────────────

def render_html(rows, added, args, parcours):
    date_fmt = datetime.strptime(args.date, "%Y-%m-%d").strftime("%d %B %Y")
    start = parcours.get("start", "") if parcours else ""
    end = parcours.get("end", "") if parcours else ""

    lines = [f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Rapport G-D — Ligne {args.ligne} {args.direction.capitalize()} — {args.date}</title>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 13px; margin: 20px; }}
  h1 {{ font-size: 16px; margin-bottom: 4px; }}
  .meta {{ color: #555; margin-bottom: 12px; font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ background: #2c5f8a; color: white; padding: 6px 8px; text-align: left; font-size: 12px; }}
  td {{ padding: 4px 8px; border-bottom: 1px solid #ddd; vertical-align: top; }}
  tr:hover {{ background: #f5f5f5; }}
  .gd {{ color: #1a4a7a; font-weight: bold; white-space: nowrap; }}
  .code {{ color: #888; font-size: 11px; white-space: nowrap; }}
  .seq {{ color: #aaa; font-size: 11px; text-align: right; padding-right: 4px; }}
  .cancelled td {{ background: #fff0f0; }}
  .cancelled .stop-name {{ text-decoration: line-through; color: #c00; }}
  .event-label {{ font-size: 10px; color: #c00; display: block; }}
  .added {{ background: #f0fff0; }}
  .added-section {{ margin-top: 16px; padding: 8px; background: #e8f5e9; border-left: 4px solid #4caf50; }}
  .detour-added td {{ background: #e8f5e9; }}
  .detour-added .gd {{ color: #2e7d32; }}
  .detour-removed .gd {{ text-decoration: line-through; color: #e65100; opacity: 0.7; }}
  .detour-badge {{ font-size: 9px; font-weight: bold; color: #2e7d32; display: block; }}
  @media print {{
    body {{ margin: 10px; font-size: 11px; }}
    h1 {{ font-size: 14px; }}
    th {{ font-size: 11px; }}
    td {{ padding: 3px 6px; }}
    tr:hover {{ background: none; }}
  }}
</style>
</head>
<body>
<h1>Ligne {args.ligne} — {args.direction.capitalize()} &nbsp;|&nbsp; {date_fmt}</h1>
<div class="meta">{start} → {end}</div>
<table>
<thead>
  <tr>
    <th style="width:5%">#</th>
    <th style="width:30%">G-D (instruction)</th>
    <th style="width:8%">Code</th>
    <th>Arrêt GTFS / Détour</th>
  </tr>
</thead>
<tbody>"""]

    for r in rows:
        cancelled       = r.get("cancelled", [])
        detour_added    = r.get("detour_added", False)
        detour_removed  = r.get("detour_removed", False)
        detour_label    = r.get("detour_label", "")

        if detour_added:
            cls = ' class="detour-added"'
        elif detour_removed:
            cls = ' class="detour-removed"'
        elif cancelled:
            cls = ' class="cancelled"'
        else:
            cls = ""

        gd_text = r["gd"]
        if detour_added:
            gd_text = f'🔀 {gd_text}'
        elif detour_removed:
            gd_text = f'✂ {gd_text}'
        gd_cell = f'<span class="gd">{gd_text}</span>' if gd_text else ""

        if detour_added and detour_label:
            gd_cell += f'<span class="detour-badge">Détour : {detour_label}</span>'

        seq_cell = str(r["seq"]) if r["seq"] else ""

        if r["stop_name"]:
            name_span = f'<span class="stop-name">{r["stop_name"]}</span>'
            if cancelled:
                for ev in cancelled:
                    name_span += f'<span class="event-label">❌ {ev}</span>'
        else:
            name_span = ""

        lines.append(
            f'<tr{cls}>'
            f'<td class="seq">{seq_cell}</td>'
            f'<td>{gd_cell}</td>'
            f'<td class="code">{r["stop_code"]}</td>'
            f'<td>{name_span}</td>'
            f'</tr>'
        )

    lines.append("</tbody></table>")

    if added:
        lines.append('<div class="added-section"><strong>Arrêts ajoutés (temporaires)</strong><ul>')
        for a in added:
            lines.append(f'<li>➕ {a["name"]} — {a["label"]}</li>')
        lines.append("</ul></div>")

    lines.append("</body></html>")
    return "\n".join(lines)


def render_md(rows, added, args, parcours):
    date_fmt = datetime.strptime(args.date, "%Y-%m-%d").strftime("%d %B %Y")
    start = parcours.get("start", "") if parcours else ""
    end = parcours.get("end", "") if parcours else ""

    lines = [
        f"# Ligne {args.ligne} — {args.direction.capitalize()} | {date_fmt}",
        f"**{start} → {end}**\n",
        "| # | G-D (instruction) | Code | Arrêt GTFS / Détour |",
        "|---|---|---|---|",
    ]
    for r in rows:
        cancelled      = r.get("cancelled", [])
        detour_added   = r.get("detour_added", False)
        detour_removed = r.get("detour_removed", False)

        seq  = str(r["seq"]) if r["seq"] else ""
        gd   = r["gd"]
        code = r["stop_code"]
        name = r["stop_name"]

        if detour_added:
            gd = f"🔀 {gd}"
            if r.get("detour_label"):
                gd += f" *(Détour : {r['detour_label']})*"
        elif detour_removed:
            gd = f"~~✂ {gd}~~"

        if cancelled:
            name = f"~~{name}~~ ❌ " + " / ".join(cancelled)

        lines.append(f"| {seq} | {gd} | {code} | {name} |")

    if added:
        lines.append("\n## Arrêts ajoutés (temporaires)")
        for a in added:
            lines.append(f"- ➕ **{a['name']}** — {a['label']}")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Résolution du chemin de base
    base = Path(args.base) if args.base else Path(__file__).resolve().parent.parent
    global GTFS
    GTFS = base / "data" / "gtfs" / "gtfs_stm"

    print(f"→ Ligne {args.ligne} {args.direction} — {args.date}")
    print(f"  Base projet : {base}")

    route_id = get_route_id(args.ligne)
    dir_id = get_direction_id(route_id, args.direction)
    stops = get_stops_for_line(route_id, dir_id)
    stop_names = load_stop_names()
    gd_instructions, parcours = load_gd(args.ligne, args.direction, base)
    events = load_events(args.ligne, args.direction, args.date, base)

    print(f"  {len(stops)} arrêts GTFS, {len(gd_instructions)} instructions G-D, {len(events)} événements actifs")

    rows = build_rows(gd_instructions, stops, stop_names)
    rows, added = annotate_events(rows, events)
    rows = apply_gd_detours(rows, events)

    ext = args.format
    outfile = Path(__file__).resolve().parent / f"rapport_{args.ligne}_{args.direction}_{args.date}.{ext}"

    if args.format == "html":
        content = render_html(rows, added, args, parcours)
    else:
        content = render_md(rows, added, args, parcours)

    outfile.write_text(content, encoding="utf-8")
    print(f"  ✅ Rapport écrit: {outfile}")


if __name__ == "__main__":
    main()