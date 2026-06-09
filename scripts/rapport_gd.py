#!/usr/bin/env python3
"""
Rapport détaillé G-D / Arrêts / Détours STM
Usage: python rapport_gd.py --ligne 195 --direction ouest --date 2026-06-07 [--format html|md]
                             [--heure-debut 22:00] [--heure-fin 28:30]
                             [--parcours principal|secondaire|école|weekend]
                             [--arret-debut 54112] [--arret-fin 57365]

Les heures de quart peuvent dépasser 24h (ex: 25:19 = 1h19 le lendemain).
Si --heure-debut et --heure-fin sont omis, tous les événements actifs le jour J
sont inclus (comportement précédent).

Variantes école : utiliser --ligne 24e, --ligne 168e, etc.
"""

import argparse
import csv
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Rapport G-D / Arrêts / Détours STM")
    p.add_argument("--ligne", required=True, help="Numéro de ligne (ex: 195, 24e)")
    p.add_argument("--direction", required=True, choices=["est", "ouest", "nord", "sud"])
    p.add_argument("--date", required=True, help="Date de début du quart (YYYY-MM-DD)")
    p.add_argument("--heure-debut", default=None,
                   help="Heure de début du quart (HH:MM ou 25:30 pour 1h30 le lendemain)")
    p.add_argument("--heure-fin", default=None,
                   help="Heure de fin du quart (HH:MM ou 25:30 pour 1h30 le lendemain)")
    p.add_argument("--parcours", default=None,
                   help="Mot-clé dans le nom du parcours (ex: principal, secondaire, école, weekend). "
                        "Par défaut: premier parcours du fichier.")
    p.add_argument("--arret-debut", default=None,
                   help="Code STM de l'arrêt de départ effectif (ex: 54112). "
                        "Tronque l'affichage à partir de cet arrêt.")
    p.add_argument("--arret-fin", default=None,
                   help="Code STM de l'arrêt de fin effectif (ex: 57365). "
                        "Tronque l'affichage jusqu'à cet arrêt.")
    p.add_argument("--format", default="html", choices=["html", "md"])
    p.add_argument("--base", default=None,
                   help="Chemin racine du projet STM (défaut: dossier parent du script)")
    return p.parse_args()


# ── Gestion des heures de quart ───────────────────────────────────────────────

def parse_shift_time(time_str: str, base_date: date) -> datetime:
    """
    Convertit une heure de quart en datetime.
    "22:00" → base_date à 22:00
    "25:19" → base_date+1 à 01:19  (heure dépassant minuit du quart de nuit)
    "30:00" → base_date+1 à 06:00
    """
    parts = time_str.strip().split(":")
    total_hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 else 0
    extra_days = total_hours // 24
    hours = total_hours % 24
    base_dt = datetime(base_date.year, base_date.month, base_date.day, hours, minutes)
    return base_dt + timedelta(days=extra_days)


def parse_effectif_times(effectif: str):
    """
    Extrait une plage horaire journalière depuis le champ effectif.
    Retourne (h_debut, m_debut, h_fin, m_fin) ou None si non trouvé.

    Exemples reconnus :
      "Seulement entre 12:00 et 19:00 chaque jour"
      "12H00 À 19H00"
      "entre 7h30 et 23h00"
    """
    # Format "HH:MM à HH:MM" ou "HHhMM à HHhMM"
    m = re.search(
        r'(\d{1,2})[h:](\d{2})\s*[àa]\s*(\d{1,2})[h:](\d{2})',
        effectif, re.IGNORECASE
    )
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    # Format "entre HH:MM et HH:MM"
    m = re.search(
        r'entre\s+(\d{1,2})[h:](\d{2})\s+et\s+(\d{1,2})[h:](\d{2})',
        effectif, re.IGNORECASE
    )
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return None


def _day_range(start: datetime, end: datetime):
    """Génère tous les objets date entre start et end (inclus)."""
    d = start.date()
    while d <= end.date():
        yield d
        d += timedelta(days=1)


def event_applies_to_shift(event: dict, shift_start: datetime, shift_end: datetime) -> bool:
    """
    Détermine si un événement est actif pendant la plage de quart donnée.

    Critères :
    1. La plage de validité de l'événement (date_heure_debut / date_heure_fin)
       doit chevaucher [shift_start, shift_end].
    2. Le champ effectif peut restreindre :
       - Les jours de la semaine (lundi-vendredi, fins de semaine…)
       - Une plage horaire quotidienne (ex. "12:00 à 19:00")
    """
    debut_str = event.get("date_heure_debut")
    fin_str   = event.get("date_heure_fin")

    event_start = datetime.fromisoformat(debut_str) if debut_str else datetime.min
    event_end   = datetime.fromisoformat(fin_str)   if fin_str   else datetime.max

    # 1. Chevauchement de la plage de validité
    if event_end < shift_start or event_start > shift_end:
        return False

    effectif = (event.get("effectif") or "").strip()

    # 2. Filtre jour de la semaine
    weekdays_in_shift = {d.weekday() for d in _day_range(shift_start, shift_end)}
    if re.search(r'lundi.*vendredi|jour.*semaine|semaine(?!\s*de)', effectif, re.IGNORECASE):
        if not any(w < 5 for w in weekdays_in_shift):
            return False
    elif re.search(r'fin.*semaine|samedi.*dimanche|week.?end', effectif, re.IGNORECASE):
        if not any(w >= 5 for w in weekdays_in_shift):
            return False

    # 3. Filtre plage horaire quotidienne
    tw = parse_effectif_times(effectif)
    if tw:
        h_s, m_s, h_e, m_e = tw
        overlaps = False
        for d in _day_range(shift_start, shift_end):
            w_start = datetime(d.year, d.month, d.day, h_s, m_s)
            w_end   = datetime(d.year, d.month, d.day, h_e, m_e)
            # Si fin ≤ début → la fenêtre passe minuit
            if w_end <= w_start:
                w_end += timedelta(days=1)
            if w_start < shift_end and w_end > shift_start:
                overlaps = True
                break
        if not overlaps:
            return False

    return True


# ── Chargement des données ────────────────────────────────────────────────────

def get_route_id(ligne):
    with open(GTFS / "routes.txt") as f:
        for r in csv.DictReader(f):
            if r["route_short_name"] == ligne:
                return r["route_id"]
    raise ValueError(f"Ligne {ligne} introuvable dans GTFS")


def get_direction_id(route_id, direction):
    # Limite de mot (\b) : évite que "est" matche dans "ouest"
    pattern = re.compile(r'\b' + re.escape(direction.lower()) + r'\b', re.IGNORECASE)
    seen = {}
    with open(GTFS / "trips.txt") as f:
        for r in csv.DictReader(f):
            if r["route_id"] == route_id:
                seen[r["direction_id"]] = r["trip_headsign"]
                if pattern.search(r["trip_headsign"]):
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


def list_parcours(ligne, direction, base):
    """
    Retourne la liste de tous les parcours disponibles pour cette ligne/direction,
    ou [] si le fichier G-D n'existe pas.
    """
    path = base / f"data/Gauche-Droite/gd{ligne}_{direction}.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    routes = data.get("routes", [])
    if not routes:
        return []
    return [
        {
            "id":         p.get("id"),
            "name":       p.get("name", ""),
            "start":      p.get("start", ""),
            "start_code": str(p.get("start_code", "")),
            "end":        p.get("end", ""),
            "end_code":   str(p.get("end_code", "")),
        }
        for p in routes[0].get("parcours", [])
    ]


def _select_parcours(all_parcours, hint):
    """
    Choisit un parcours selon un mot-clé dans le nom, ou le premier par défaut.
    """
    if hint and all_parcours:
        h = hint.strip().lower()
        for p in all_parcours:
            if h in p.get("name", "").lower():
                return p
        print(f"  ⚠ Parcours '{hint}' introuvable — utilisation du premier parcours.")
    return all_parcours[0] if all_parcours else {}


def load_gd(ligne, direction, base, parcours_hint=None):
    """
    Charge les instructions G-D et le parcours sélectionné.
    Retourne (instructions, parcours_obj, all_parcours).
    """
    path = base / f"data/Gauche-Droite/gd{ligne}_{direction}.json"
    if not path.exists():
        return [], None, []
    with open(path) as f:
        data = json.load(f)
    routes = data.get("routes", [])
    if not routes:
        return [], None, []
    all_parcours = routes[0].get("parcours", [])
    parcours = _select_parcours(all_parcours, parcours_hint)
    return parcours.get("direction", []), parcours, all_parcours


def load_events(ligne, direction, base,
                shift_start: datetime | None = None,
                shift_end: datetime | None = None,
                date_str: str | None = None):
    """
    Charge les événements actifs pour la ligne/direction.

    Si shift_start et shift_end sont fournis, utilise la logique de plage
    horaire (chevauchement + effectif). Sinon, retombe sur le filtrage
    par journée (date_str requis dans ce cas).
    """
    path = base / f"data/Events/{ligne}_{direction}.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)

    active = []
    for e in data.get("detours", []):
        if shift_start is not None and shift_end is not None:
            if event_applies_to_shift(e, shift_start, shift_end):
                active.append(e)
        else:
            # Comportement original : filtrage par date uniquement
            target = datetime.strptime(date_str, "%Y-%m-%d").date()
            debut = e.get("date_heure_debut")
            fin   = e.get("date_heure_fin")
            if debut and datetime.fromisoformat(debut).date() > target:
                continue
            if fin and datetime.fromisoformat(fin).date() < target:
                continue
            active.append(e)

    return active


# ── Alignement G-D / arrêts ───────────────────────────────────────────────────

def extract_street(instruction):
    """'Gauche - Lafleur' → 'lafleur'"""
    parts = instruction.split(" - ", 1)
    return parts[1].strip().lower() if len(parts) == 2 else instruction.lower()


def build_rows(gd_instructions, stops_ordered, stop_names):
    """
    Aligne les instructions G-D avec les arrêts GTFS par correspondance de rue.
    Retourne une liste de dicts : {gd, seq, stop_id, stop_name, stop_code}
    """
    rows = []
    stop_idx = 0
    n_stops = len(stops_ordered)

    for instr in gd_instructions:
        street = extract_street(instr)

        matched = []
        tmp_idx = stop_idx
        while tmp_idx < n_stops:
            seq, sid = stops_ordered[tmp_idx]
            name = stop_names.get(sid, {}).get("name", "").lower()
            if street in name:
                matched.append((seq, sid))
                tmp_idx += 1
            else:
                break

        if matched:
            stop_idx = tmp_idx
            rows.append({"gd": instr, "seq": matched[0][0], "stop_id": matched[0][1]})
            for seq, sid in matched[1:]:
                rows.append({"gd": "", "seq": seq, "stop_id": sid})
        else:
            rows.append({"gd": instr, "seq": None, "stop_id": None})

    # Arrêts restants sans instruction G-D
    while stop_idx < n_stops:
        seq, sid = stops_ordered[stop_idx]
        rows.append({"gd": "", "seq": seq, "stop_id": sid})
        stop_idx += 1

    # Enrichissement avec les noms
    for r in rows:
        if r["stop_id"]:
            s = stop_names.get(r["stop_id"], {})
            r["stop_code"] = s.get("code", "")
            r["stop_name"] = s.get("name", "")
        else:
            r["stop_code"] = ""
            r["stop_name"] = ""
    return rows


def filter_rows_by_stop_range(rows, arret_debut, arret_fin):
    """
    Tronque la liste de lignes selon les codes d'arrêt de départ et de fin.
    Si un code n'est pas trouvé, un avertissement est émis et la borne est ignorée.
    """
    if not arret_debut and not arret_fin:
        return rows

    start_idx = 0
    end_idx = len(rows) - 1

    if arret_debut:
        found = next(
            (i for i, r in enumerate(rows) if r.get("stop_code") == str(arret_debut)),
            None,
        )
        if found is not None:
            start_idx = found
        else:
            print(f"  ⚠ Arrêt de départ '{arret_debut}' introuvable dans les arrêts GTFS — borne ignorée.")

    if arret_fin:
        found = next(
            (i for i, r in enumerate(rows) if r.get("stop_code") == str(arret_fin)),
            None,
        )
        if found is not None:
            end_idx = found
        else:
            print(f"  ⚠ Arrêt de fin '{arret_fin}' introuvable dans les arrêts GTFS — borne ignorée.")

    return rows[start_idx : end_idx + 1]


def annotate_events(rows, events):
    """
    Ajoute les annotations d'événements aux lignes du tableau.
    Chaque ligne annulée reçoit une liste d'objets :
      {"label": str, "effectif": str}

    Retourne (rows, added, orphan_events) où orphan_events contient les
    événements dont aucun arrêt annulé ne figure dans le trajet GTFS
    sélectionné (ils sont affichés dans une section "Alertes" séparée).
    """
    cancelled_ids = {}   # stop_id -> list of {label, effectif}
    added = []           # arrêts ajoutés avec descriptions
    stop_ids_in_rows = {r["stop_id"] for r in rows if r.get("stop_id")}

    for e in events:
        titre       = e.get("titre", "")
        motif       = e.get("motif", "")
        effectif    = (e.get("effectif") or "").strip()
        desc        = e.get("description_gd", "") or ""
        commentaire = e.get("commentaire", "") or ""
        label = f"{titre} ({motif})"
        if desc:
            label += f" — G-D: {desc}"
        if commentaire:
            label += f" — {commentaire}"

        for a in e.get("arrets_annules", []):
            cancelled_ids.setdefault(a["id"], []).append(
                {"label": label, "effectif": effectif, "nom_evt": a.get("nom", "")}
            )
        for a in e.get("arrets_ajoutes", []):
            name = a if isinstance(a, str) else a.get("nom", "")
            added.append({"name": name, "label": label, "effectif": effectif})

    for r in rows:
        sid = r.get("stop_id")
        if sid and sid in cancelled_ids:
            r["cancelled"] = cancelled_ids[sid]
        else:
            r["cancelled"] = []

    # Événements dont les arrêts annulés ne figurent pas dans le trajet GTFS
    orphan_events = []
    for e in events:
        arrets = e.get("arrets_annules", [])
        if arrets and not any(a["id"] in stop_ids_in_rows for a in arrets):
            orphan_events.append(e)

    return rows, added, orphan_events


# ── Intégration G-D des détours ───────────────────────────────────────────────

_RR_RE = re.compile(r'^R[.\s]?R\.?$', re.IGNORECASE)


def parse_description_gd(desc: str):
    """
    Tente de parser une description_gd en liste d'instructions normalisées.
    Retourne ["Via - X", "Gauche - Y", ...] ou None (texte libre).
    """
    if not desc:
        return None
    if not re.search(r'\b(VIA\s+\w|G[/.\s]\w|D[/.\s]\w)', desc, re.IGNORECASE):
        return None

    if '\n' in desc:
        raw = [l.strip() for l in desc.split('\n') if l.strip()]
    else:
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
        instructions.append(f"Via - {part}")

    return instructions if instructions else None


def apply_gd_detours(rows: list, events: list) -> list:
    """
    Pour chaque événement avec une description_gd parseable :
    - Insère les étapes du détour avant le premier arrêt annulé (detour_added=True)
    - Marque les instructions G-D régulières contournées (detour_removed=True)
    """
    for event in events:
        desc = event.get("description_gd") or ""
        instructions = parse_description_gd(desc)
        if not instructions:
            continue

        cancelled_codes = {a["id"] for a in event.get("arrets_annules", [])}

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

        if last_pos >= first_pos:
            for i in range(first_pos, last_pos + 1):
                r = rows[i]
                if (r.get("gd")
                        and not r.get("detour_added")
                        and r.get("stop_code", "") not in cancelled_codes):
                    r["detour_removed"] = True

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


# ── Formatage de la plage de quart ────────────────────────────────────────────

def fmt_shift_range(shift_start, shift_end, base_date):
    """Retourne une chaîne lisible pour l'en-tête du rapport."""
    if shift_start is None or shift_end is None:
        return "Journée complète"

    def fmt_dt(dt):
        if dt.date() == base_date:
            return dt.strftime("%H:%M")
        else:
            return dt.strftime("%H:%M (+1j)")

    return f"{fmt_dt(shift_start)} — {fmt_dt(shift_end)}"


# ── Rendus HTML et Markdown ───────────────────────────────────────────────────

def render_html(rows, added, args, parcours, shift_start=None, shift_end=None, orphan_events=None):
    base_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    date_fmt = datetime.strptime(args.date, "%Y-%m-%d").strftime("%d %B %Y")
    start = parcours.get("start", "") if parcours else ""
    end   = parcours.get("end", "")   if parcours else ""
    quart = fmt_shift_range(shift_start, shift_end, base_date)

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
  .effectif {{ font-size: 10px; color: #666; font-style: italic; white-space: nowrap; }}
  .cancelled td {{ background: #fff0f0; }}
  .cancelled .stop-name {{ text-decoration: line-through; color: #c00; }}
  .event-label {{ font-size: 10px; color: #c00; display: block; }}
  .event-precision {{ font-size: 11px; color: #b45309; font-weight: bold; display: block; }}
  .added {{ background: #f0fff0; }}
  .added-section {{ margin-top: 16px; padding: 8px; background: #e8f5e9; border-left: 4px solid #4caf50; }}
  .detour-added td {{ background: #e8f5e9; }}
  .detour-added .gd {{ color: #2e7d32; }}
  .detour-removed .gd {{ text-decoration: line-through; color: #e65100; opacity: 0.7; }}
  .detour-badge {{ font-size: 9px; font-weight: bold; color: #2e7d32; display: block; }}
  .alert-section {{ margin-bottom: 14px; padding: 8px 12px; background: #fff3e0; border-left: 4px solid #e65100; font-size: 12px; }}
  .alert-section li {{ margin: 4px 0; }}
  .alert-stops {{ color: #666; font-size: 11px; }}
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
<div class="meta">{start} → {end} &nbsp;·&nbsp; {parcours.get("name", "") if parcours else ""} &nbsp;·&nbsp; Quart : {quart}</div>"""]

    if orphan_events:
        lines.append('<div class="alert-section"><strong>⚠️ Alertes actives (arrêts hors trajet sélectionné)</strong><ul>')
        for e in orphan_events:
            titre    = e.get("titre", "")
            motif    = e.get("motif", "")
            effectif = (e.get("effectif") or "").strip()
            ev_id    = e.get("evenement_id", "")
            arrets   = ", ".join(
                f'{a["id"]} – {a["nom"]}' for a in e.get("arrets_annules", [])
            )
            eff_txt  = f' <em>({effectif})</em>' if effectif else ""
            lines.append(
                f'<li>❌ <strong>{titre}</strong> ({motif}) — #{ev_id}{eff_txt}'
                f'<br><span class="alert-stops">Arrêts : {arrets}</span></li>'
            )
        lines.append("</ul></div>")

    lines.append(
        '<table>\n<thead>\n  <tr>\n'
        '    <th style="width:4%">#</th>\n'
        '    <th style="width:28%">G-D (instruction)</th>\n'
        '    <th style="width:7%">Code</th>\n'
        '    <th>Arrêt GTFS / Détour</th>\n'
        '    <th style="width:18%">Effectif</th>\n'
        '  </tr>\n</thead>\n<tbody>'
    )

    for r in rows:
        cancelled      = r.get("cancelled", [])
        detour_added   = r.get("detour_added", False)
        detour_removed = r.get("detour_removed", False)
        detour_label   = r.get("detour_label", "")

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
        else:
            name_span = ""

        # Colonne Effectif : agrège les valeurs uniques des événements de la ligne
        effectif_parts = []
        if cancelled:
            seen_eff = set()
            for ev in cancelled:
                label_str = ev["label"]
                eff_str   = ev.get("effectif", "")
                nom_evt   = ev.get("nom_evt", "")
                # Précision de localisation issue du nom de l'événement
                # Ex. "Sherbrooke / Gascon (50 mètres après)"
                if nom_evt and nom_evt != r["stop_name"]:
                    name_span += f'<span class="event-precision">📍 {nom_evt}</span>'
                name_span += f'<span class="event-label">❌ {label_str}</span>'
                if eff_str and eff_str not in seen_eff:
                    effectif_parts.append(eff_str)
                    seen_eff.add(eff_str)
        effectif_cell = (
            f'<span class="effectif">{" / ".join(effectif_parts)}</span>'
            if effectif_parts else ""
        )

        lines.append(
            f'<tr{cls}>'
            f'<td class="seq">{seq_cell}</td>'
            f'<td>{gd_cell}</td>'
            f'<td class="code">{r["stop_code"]}</td>'
            f'<td>{name_span}</td>'
            f'<td>{effectif_cell}</td>'
            f'</tr>'
        )

    lines.append("</tbody></table>")

    if added:
        lines.append('<div class="added-section"><strong>Arrêts ajoutés (temporaires)</strong><ul>')
        for a in added:
            eff = f' <em>({a["effectif"]})</em>' if a.get("effectif") else ""
            lines.append(f'<li>➕ {a["name"]} — {a["label"]}{eff}</li>')
        lines.append("</ul></div>")

    lines.append("</body></html>")
    return "\n".join(lines)


def render_md(rows, added, args, parcours, shift_start=None, shift_end=None, orphan_events=None):
    base_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    date_fmt = datetime.strptime(args.date, "%Y-%m-%d").strftime("%d %B %Y")
    start = parcours.get("start", "") if parcours else ""
    end   = parcours.get("end", "")   if parcours else ""
    quart = fmt_shift_range(shift_start, shift_end, base_date)

    lines = [
        f"# Ligne {args.ligne} — {args.direction.capitalize()} | {date_fmt}",
        f"**{start} → {end}** · {parcours.get('name', '') if parcours else ''} · Quart : {quart}\n",
    ]

    if orphan_events:
        lines.append("### ⚠️ Alertes actives (arrêts hors trajet sélectionné)")
        for e in orphan_events:
            titre    = e.get("titre", "")
            motif    = e.get("motif", "")
            effectif = (e.get("effectif") or "").strip()
            ev_id    = e.get("evenement_id", "")
            arrets   = ", ".join(
                f'{a["id"]} – {a["nom"]}' for a in e.get("arrets_annules", [])
            )
            eff_txt = f" *({effectif})*" if effectif else ""
            lines.append(f"- ❌ **{titre}** ({motif}) — #{ev_id}{eff_txt}  \n  Arrêts : {arrets}")
        lines.append("")

    lines += [
        "| # | G-D (instruction) | Code | Arrêt GTFS / Détour | Effectif |",
        "|---|---|---|---|---|",
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

        effectif_str = ""
        if cancelled:
            seen_eff = set()
            ev_parts = []
            precision_parts = []
            for ev in cancelled:
                ev_parts.append(ev["label"])
                eff = ev.get("effectif", "")
                if eff and eff not in seen_eff:
                    seen_eff.add(eff)
                nom_evt = ev.get("nom_evt", "")
                if nom_evt and nom_evt != name:
                    precision_parts.append(f"📍 {nom_evt}")
            precision = " ".join(precision_parts)
            name = f"~~{name}~~ {precision} ❌ " + " / ".join(ev_parts)
            effectif_str = " / ".join(seen_eff)

        lines.append(f"| {seq} | {gd} | {code} | {name} | {effectif_str} |")

    if added:
        lines.append("\n## Arrêts ajoutés (temporaires)")
        for a in added:
            eff = f" *(Effectif : {a['effectif']})*" if a.get("effectif") else ""
            lines.append(f"- ➕ **{a['name']}** — {a['label']}{eff}")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    base = Path(args.base) if args.base else Path(__file__).resolve().parent.parent
    global GTFS
    GTFS = base / "data" / "gtfs" / "gtfs_stm"

    # Calcul de la plage de quart
    base_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    shift_start = parse_shift_time(args.heure_debut, base_date) if args.heure_debut else None
    shift_end   = parse_shift_time(args.heure_fin,   base_date) if args.heure_fin   else None

    # Validation : si une seule heure est fournie, les deux sont requises
    if (shift_start is None) != (shift_end is None):
        import sys
        print("Erreur : --heure-debut et --heure-fin doivent être fournis ensemble.", file=sys.stderr)
        sys.exit(1)

    if shift_start and shift_end and shift_end <= shift_start:
        # Le quart passe minuit : shift_end est forcément le lendemain
        # Normalement déjà géré par parse_shift_time (heures > 24),
        # mais on corrige au cas où l'utilisateur donne ex. "22:00" / "06:00"
        shift_end += timedelta(days=1)

    print(f"→ Ligne {args.ligne} {args.direction} — {args.date}")
    print(f"  Base projet : {base}")
    if shift_start:
        print(f"  Quart       : {shift_start.strftime('%Y-%m-%d %H:%M')} → {shift_end.strftime('%Y-%m-%d %H:%M')}")
    else:
        print("  Quart       : journée complète")

    # Charger le G-D et sélectionner le parcours
    gd_instructions, parcours, all_parcours = load_gd(
        args.ligne, args.direction, base, parcours_hint=args.parcours
    )
    if all_parcours:
        print("  Parcours disponibles :")
        selected_name = (parcours or {}).get("name", "")
        for p in all_parcours:
            marker = "►" if p.get("name") == selected_name else " "
            print(f"    {marker} [{p['id']}] {p['name']}  {p['start_code']} → {p['end_code']}")

    # Arrêts GTFS (avec fallback si variante école absente du GTFS)
    try:
        route_id = get_route_id(args.ligne)
        dir_id   = get_direction_id(route_id, args.direction)
        stops    = get_stops_for_line(route_id, dir_id)
    except ValueError as exc:
        print(f"  ⚠ GTFS : {exc} — rapport sans correspondance d'arrêts GTFS.")
        stops = []

    stop_names = load_stop_names()
    events = load_events(
        args.ligne, args.direction, base,
        shift_start=shift_start,
        shift_end=shift_end,
        date_str=args.date,
    )

    print(f"  {len(stops)} arrêts GTFS, {len(gd_instructions)} instructions G-D, {len(events)} événements actifs")

    rows = build_rows(gd_instructions, stops, stop_names)
    rows, added, orphan_events = annotate_events(rows, events)
    rows = apply_gd_detours(rows, events)

    # Tronquer selon la plage d'arrêts effective du chauffeur
    if args.arret_debut or args.arret_fin:
        before = len(rows)
        rows = filter_rows_by_stop_range(rows, args.arret_debut, args.arret_fin)
        print(f"  Plage d'arrêts : {args.arret_debut or '(début)'} → "
              f"{args.arret_fin or '(fin)'}  ({len(rows)}/{before} lignes)")

    if orphan_events:
        print(f"  ⚠️  {len(orphan_events)} événement(s) actif(s) hors trajet GTFS sélectionné — affichés en alerte")

    ext = args.format
    outfile = Path(__file__).resolve().parent / f"rapport_{args.ligne}_{args.direction}_{args.date}.{ext}"

    if args.format == "html":
        content = render_html(rows, added, args, parcours, shift_start, shift_end, orphan_events)
    else:
        content = render_md(rows, added, args, parcours, shift_start, shift_end, orphan_events)

    outfile.write_text(content, encoding="utf-8")
    print(f"  ✅ Rapport écrit: {outfile}")


if __name__ == "__main__":
    main()
