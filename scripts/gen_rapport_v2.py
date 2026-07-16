#!/usr/bin/env python3
"""
gen_rapport_v2.py — Rapport journalier v2

Source : data/journees/journee-YYYY-MM-DD.json (structure + id_parcours direct).
Réutilise le noyau chauffeur/ sans dupliquer la logique.

Usage :
  python gen_rapport_v2.py --journee data/journees/journee-2026-06-17.json
  python gen_rapport_v2.py --journee ... --niveau standard --format html
  python gen_rapport_v2.py --journee ... --codearret --output /tmp/r.pdf
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chauffeur.gd import (
    build_rows, annotate_events, apply_gd_detours, insert_added_stops_inline,
    event_applicable_to_parcours,
)
from chauffeur.gtfs import stops_for_parcours, stop_names as gtfs_stop_names
from chauffeur.depots import charger_journee, charger_gd, evenements_pour_date
from chauffeur.effectif import bornes_quart
from chauffeur.evenements import applicable_a_la_plage, arret_reellement_annule
from chauffeur.journee import groupes_de_service

GTFS_DIR   = ROOT / "data" / "gtfs" / "gtfs_stm"
OUTPUT_DIR = ROOT / "data" / "rapports"


# ── Chargement événements ─────────────────────────────────────────────────────

def load_events_for_groupe(groupe: dict, date_str: str) -> list:
    """Événements applicables à la plage horaire du groupe (filtre quart)."""
    jour   = date.fromisoformat(date_str)
    all_ev = evenements_pour_date(groupe["ligne"], groupe["direction"], jour)
    trips  = groupe.get("trips", [])
    if not trips or not all_ev:
        return []
    heures_deb = [t["depart_heure"]  for t in trips if t.get("depart_heure")]
    heures_fin = [t["arrivee_heure"] for t in trips if t.get("arrivee_heure")]
    bornes_deb = bornes_quart(heures_deb, jour)
    bornes_fin = bornes_quart(heures_fin, jour)
    plage = (bornes_deb[0], bornes_fin[1]) if bornes_deb and bornes_fin else None
    return [e for e in all_ev if applicable_a_la_plage(e, jour, plage)]


# ── GTFS ──────────────────────────────────────────────────────────────────────

def _load_gtfs_stops(ligne: str, direction: str, id_parcours=None):
    if not GTFS_DIR.exists():
        return [], {}
    try:
        sfl = stops_for_parcours(GTFS_DIR, ligne, direction, id_parcours)
        return sfl, gtfs_stop_names(GTFS_DIR)
    except Exception:
        return [], {}


# ── Filtrage par niveau ────────────────────────────────────────────────────────

def filter_rows_by_niveau(rows: list, niveau: str) -> list:
    if niveau == "détaillé":
        return rows
    result = []
    for r in rows:
        added    = r.get("detour_added",   False)
        removed  = r.get("detour_removed", False)
        inline   = r.get("added_inline",   False)
        cancelled= r.get("cancelled",      [])
        if niveau == "standard":
            # Instructions G-D + toutes les lignes modifiées (sans les arrêts standard)
            if added or removed or inline or cancelled or r.get("gd"):
                result.append(r)
        elif niveau == "compact":
            # Exceptions uniquement : ajouts de détour + arrêts annulés + arrêts ajoutés
            if added or inline or cancelled:
                result.append(r)
    return result


# ── Pipeline par groupe ───────────────────────────────────────────────────────

def process_groupe(groupe: dict, date_str: str, ev_all_cache: dict) -> dict:
    ligne, direction, id_p = groupe["ligne"], groupe["direction"], groupe.get("id_parcours")
    instructions, parcours = charger_gd(ligne, direction, id_p)
    stops_ordered, snames  = _load_gtfs_stops(ligne, direction, id_p)
    events                 = load_events_for_groupe(groupe, date_str)

    cache_key = (ligne, direction)
    if cache_key not in ev_all_cache:
        ev_all_cache[cache_key] = evenements_pour_date(
            ligne, direction, date.fromisoformat(date_str))
    events_all = ev_all_cache[cache_key]

    if not instructions:
        return dict(groupe=groupe, rows=[], added=[], events=events,
                    events_all=events_all, parcours=parcours)

    rows = build_rows(instructions, stops_ordered, snames)

    # Filtrer les évènements non-applicables à ce parcours spécifique.
    # Un évènement dont les arrêts annulés ou les rues de détour ne concernent
    # pas ce parcours est exclu ici — il reste visible dans le tableau des
    # évènements (events_all) comme « non-applicable ».
    # GTFS indisponible (stops_ordered vide) → stop_ids=None : les arrêts du
    # parcours sont inconnus et les évènements à arrêts annulés sont présumés
    # applicables (fail-safe, même règle que l'onglet Ma journée).
    stop_ids = ({r["stop_id"] for r in rows if r.get("stop_id")}
                if stops_ordered else None)
    events = [e for e in events
              if event_applicable_to_parcours(e, stop_ids, instructions)]

    rows, added, _ = annotate_events(rows, events)
    rows = apply_gd_detours(rows, events)
    rows, added = insert_added_stops_inline(rows, added)
    return dict(groupe=groupe, rows=rows, added=added, events=events,
                events_all=events_all, parcours=parcours)


# ── Rendu HTML ────────────────────────────────────────────────────────────────

_CSS = """
body{font-family:Arial,sans-serif;font-size:13px;margin:20px;color:#1A1A2E}
h1{font-size:16px;margin-bottom:4px;color:#0072CE}
.meta{color:#555;margin-bottom:12px;font-size:12px}
h2{font-size:14px;margin:22px 0 2px;padding:4px 8px;background:#0072CE;color:#fff}
h3{font-size:12px;margin:10px 0 2px;color:#1a4a7a}
.trips{font-size:11px;color:#555;margin-bottom:6px}
.no-gd{color:#888;font-style:italic;margin:6px 0 10px}
table{border-collapse:collapse;width:100%;margin-bottom:12px}
th{background:#2c5f8a;color:#fff;padding:5px 8px;text-align:left;font-size:12px}
td{padding:4px 8px;border-bottom:1px solid #ddd;vertical-align:top}
.gd{color:#1a4a7a;font-weight:bold;white-space:nowrap}
.code{color:#888;font-size:11px;white-space:nowrap}
.seq{color:#aaa;font-size:11px;text-align:right;padding-right:4px}
.effectif{font-size:10px;color:#666;font-style:italic}
.periode{font-size:10px;color:#888;display:block}
.eid{font-size:10px;color:#555;font-weight:bold;display:block}
.cancelled td{background:#fff0f0}
.cancelled .stop-name{text-decoration:line-through;color:#c00}
.maintenu td{background:#fff8e1}
.maintenu .stop-name{color:#e65100}
.maintenu .event-label{color:#e65100}
.detour-removed .gd{text-decoration:line-through;color:#e65100;opacity:.7}
.detour-added td{background:#e8f5e9}
.detour-added .gd{color:#2e7d32}
.detour-badge{font-size:9px;font-weight:bold;color:#2e7d32;display:block}
.added-inline td{background:#f0fff0}
.added-inline .stop-name{color:#2e7d32;font-weight:bold}
.added-inline-label{font-size:10px;color:#388e3c;display:block}
.event-label{font-size:10px;color:#c00;display:block}
.event-comment{font-size:10px;color:#7a3e00;font-style:italic;display:block}
.event-precision{font-size:11px;color:#b45309;font-weight:bold;display:block}
.ev-table th{background:#f0f0f0;color:#333}
.ev-na{color:#bbb}
@media print{body{margin:8px;font-size:11px}tr:hover{background:none}}
"""

TYPE_SYMBOL = {
    "annulation d'arrêts"            : "✗",
    "arrêt déplacé"                  : "!",
    "détour avec annulation d'arrêt" : "▲",
    "détour"                         : "▲",
}


def _h(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_periode(e: dict) -> str:
    """Période d'un évènement, avec heure : 'YYYY-MM-DD HH:MM → HH:MM' (même jour)
    ou 'YYYY-MM-DD HH:MM → YYYY-MM-DD HH:MM' (jours différents), '→ ' si fin ouverte."""
    debut_raw = e.get("date_heure_debut")
    if not debut_raw:
        return ""
    debut = datetime.fromisoformat(debut_raw)
    fin_raw = e.get("date_heure_fin")
    if not fin_raw:
        return f"{debut:%Y-%m-%d %H:%M} → "
    fin = datetime.fromisoformat(fin_raw)
    fin_fmt = f"{fin:%H:%M}" if fin.date() == debut.date() else f"{fin:%Y-%m-%d %H:%M}"
    return f"{debut:%Y-%m-%d %H:%M} → {fin_fmt}"


def _arr_key(r: dict) -> str:
    """Clé de l'annotation événement sous le nom d'arrêt — sert à détecter les répétitions.

    Basée sur le(s) evenement_id plutôt que sur le texte affiché : deux
    évènements distincts peuvent produire le même libellé (ex. deux "Arrêt
    déplacé (Travaux)" sans lien) et ne doivent pas être confondus.
    """
    if r.get("added_inline"):
        return r.get("evenement_id", "")
    cancelled = r.get("cancelled") or []
    return "|".join(ev.get("evenement_id", "") for ev in cancelled)


def _render_rows_html(rows: list, show_code: bool, niveau: str = "détaillé",
                       events: list = ()) -> str:
    code_th = '<th style="width:7%">Code</th>' if show_code else ""
    out = [
        '<table><thead><tr>'
        '<th style="width:4%">#</th>'
        '<th style="width:28%">G-D</th>'
        + code_th +
        '<th>Arrêt / Détour</th>'
        '<th style="width:20%">#évènement / Effectif / Période</th>'
        '</tr></thead><tbody>'
    ]
    periode_by_eid = {e.get("evenement_id", ""): _format_periode(e) for e in events}
    prev_arr_key = None
    prev_ev_eids = set()   # eid des badges #évènement affichés à la ligne précédente
    for r in rows:
        cancelled   = r.get("cancelled",      [])
        d_added     = r.get("detour_added",   False)
        d_removed   = r.get("detour_removed", False)
        added_inline= r.get("added_inline",   False)
        label       = r.get("detour_label",   "")

        key = _arr_key(r)
        is_ditto = bool(key) and key == prev_arr_key
        if key:
            prev_arr_key = key

        if added_inline:
            nm = f'<span class="stop-name">➕ {_h(r["stop_name"])}</span>'
            if not is_ditto:
                _albl = r.get("added_short_label") or r.get("added_label", "")
                if _albl:
                    nm += f'<span class="added-inline-label">{_h(_albl)}</span>'
                if r.get("commentaire"):
                    nm += f'<span class="event-comment">{_h(r["commentaire"])}</span>'
            eid_inline = r.get("evenement_id", "")
            ditto_eid  = bool(eid_inline) and eid_inline in prev_ev_eids
            eff_inline = "" if ditto_eid else r.get("effectif", "")
            per_inline = "" if ditto_eid else periode_by_eid.get(eid_inline, "")
            inline_eff_cell = (
                (f'<span class="eid">#{_h(str(eid_inline))}</span>' if eid_inline else "") +
                (f'<span class="effectif">{_h(eff_inline)}</span>' if eff_inline else "") +
                (f'<span class="periode">{_h(per_inline)}</span>' if per_inline else "")
            )
            prev_ev_eids = {eid_inline} if eid_inline else set()
            code_td = f'<td class="code"></td>' if show_code else ""
            out.append(f'<tr class="added-inline"><td class="seq"></td><td></td>'
                       f'{code_td}<td>{nm}</td><td>{inline_eff_cell}</td></tr>')
            continue

        # G-D cell
        gd_txt = r.get("gd") or ""
        if gd_txt:
            if d_added:
                gd_cell = f'<span class="gd">🔀 {_h(gd_txt)}</span>'
                if label:
                    gd_cell += f'<span class="detour-badge">Détour : {_h(label)}</span>'
            elif d_removed:
                gd_cell = f'<span class="gd">✂ {_h(gd_txt)}</span>'
            else:
                gd_cell = f'<span class="gd">{_h(gd_txt)}</span>'
        else:
            gd_cell = ""

        # Arrêt cell — toujours construire eff_parts (même pour ditto)
        eff_parts = []
        seen_eid  = set()
        plain_gd = gd_txt and not d_added and not d_removed and not cancelled
        nm = "" if (niveau == "standard" and plain_gd) else (
            f'<span class="stop-name">{_h(r.get("stop_name") or "")}</span>'
            if r.get("stop_name") else ""
        )
        if not is_ditto:
            for ev in cancelled:
                nom_evt = ev.get("nom_evt", "")
                if nom_evt and nom_evt != r.get("stop_name"):
                    nm += f'<span class="event-precision">📍 {_h(nom_evt)}</span>'
                sym = TYPE_SYMBOL.get(ev.get("type_evenement", ""), "!")
                short = ev.get("short_label") or ev["label"]
                nm += f'<span class="event-label">{sym} {_h(short)}</span>'
                if ev.get("commentaire"):
                    nm += f'<span class="event-comment">{_h(ev["commentaire"])}</span>'
        for ev in cancelled:
            eid = ev.get("evenement_id", "")
            eff = ev.get("effectif", "")
            if eid and eid not in seen_eid:
                eff_parts.append((eid, eff))
                seen_eid.add(eid)
        # Pour les lignes detour_added, ajouter l'ID d'évènement à la colonne eff
        if d_added:
            eid = r.get("evenement_id", "")
            eff = r.get("effectif", "")
            if eid and eid not in seen_eid:
                eff_parts.append((eid, eff))
                seen_eid.add(eid)

        # Badges #évènement / Effectif / Période — Effectif et Période sont
        # tus quand le même évènement couvrait déjà la ligne précédente.
        curr_ev_eids = set()
        eff_cell_bits = []
        for eid, eff in eff_parts:
            ditto_eid = eid in prev_ev_eids
            per = "" if ditto_eid else periode_by_eid.get(eid, "")
            eff = "" if ditto_eid else eff
            eff_cell_bits.append(
                f'<span class="eid">#{_h(str(eid))}</span>'
                + (f'<span class="effectif">{_h(eff)}</span>' if eff else "")
                + (f'<span class="periode">{_h(per)}</span>' if per else "")
            )
            curr_ev_eids.add(eid)
        eff_cell = "".join(eff_cell_bits)
        prev_ev_eids = curr_ev_eids

        # Row class — rouge seulement si l'arrêt disparaît vraiment ; ambre s'il
        # reste desservi (« Arrêt déplacé », « Information chauffeur »).
        if d_added:
            cls = ' class="detour-added"'
        elif cancelled:
            etat = "cancelled" if arret_reellement_annule(cancelled) else "maintenu"
            cls = f' class="{etat} detour-removed"' if d_removed else f' class="{etat}"'
        elif d_removed:
            cls = ' class="detour-removed"'
        else:
            cls = ""

        seq = str(r["seq"]) if r.get("seq") else ""
        code_td = f'<td class="code">{_h(r.get("stop_code") or "")}</td>' if show_code else ""
        out.append(f'<tr{cls}><td class="seq">{seq}</td><td>{gd_cell}</td>'
                   f'{code_td}<td>{nm}</td><td>{eff_cell}</td></tr>')

    out.append("</tbody></table>")
    return "".join(out)


def _render_events_table_html(events_all: list, events_app: list) -> str:
    if not events_all:
        return ""
    app_ids = {e.get("evenement_id") for e in events_app}
    out = [
        '<table class="ev-table"><thead><tr>'
        '<th style="width:3%"></th><th style="width:9%">#</th>'
        '<th>Titre</th><th style="width:18%">Effectif</th>'
        '<th style="width:16%">Période</th>'
        '</tr></thead><tbody>'
    ]
    for e in events_all:
        eid    = e.get("evenement_id", "?")
        appl   = eid in app_ids
        mark   = "✅" if appl else "⬜"
        cls    = "" if appl else ' class="ev-na"'
        titre  = _h(e.get("titre", ""))
        eff    = _h(e.get("effectif", ""))
        per    = _h(_format_periode(e))
        out.append(f'<tr{cls}><td>{mark}</td><td>{eid}</td><td>{titre}</td>'
                   f'<td>{eff}</td><td>{per}</td></tr>')
    out.append("</tbody></table>")
    return "".join(out)


def render_html(groupes_data: list, journee: dict, niveau: str,
                show_code: bool = False) -> str:
    date_str  = journee.get("date", "")
    garage_id = journee.get("garage_id", "")
    garage    = journee.get("garage", "")
    jnum      = journee.get("journee_numero", "")
    duree     = journee.get("temps_travaille", "")

    body = [
        f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        f'<title>Rapport {date_str}</title><style>{_CSS}</style></head><body>',
        f'<h1>Rapport journalier — {date_str}</h1>',
        f'<div class="meta">Garage {garage_id} — {garage}'
        f' &nbsp;·&nbsp; Journée #{jnum} &nbsp;·&nbsp; Durée {duree}'
        f' &nbsp;·&nbsp; Niveau : {niveau}</div>',
    ]

    for gd in groupes_data:
        groupe     = gd["groupe"]
        rows       = gd["rows"]
        events_app = gd["events"]
        events_all = gd["events_all"]
        parcours   = gd["parcours"]
        id_p       = groupe.get("id_parcours")
        trips      = groupe.get("trips", [])
        ligne      = groupe["ligne"]
        direction  = groupe["direction"]

        # En-tête de section : "24 Ouest — ID 2"
        body.append(f'<h2>{ligne} {direction.capitalize()} — ID {id_p}</h2>')

        pname  = (parcours.get("name") or f"Parcours {id_p}") if parcours else f"Parcours {id_p}"
        pstart = (parcours.get("start") or "") if parcours else ""
        pend   = (parcours.get("end")   or "") if parcours else ""
        times  = ", ".join(t["depart_heure"] for t in trips if t.get("depart_heure"))
        sub    = f"{pname}"
        if pstart:
            sub += f" — {_h(pstart)} → {_h(pend)}"
        body.append(f'<h3>{sub}</h3><div class="trips">Départs : {times}</div>')

        filtered = filter_rows_by_niveau(rows, niveau)

        if not parcours:
            body.append('<p class="no-gd">G-D non disponible pour cette direction.</p>')
        elif not filtered and niveau != "détaillé":
            body.append('<p class="no-gd">Aucune modification pour ce parcours.</p>')
        else:
            body.append(_render_rows_html(filtered, show_code, niveau, events_app))

        body.append(_render_events_table_html(events_all, events_app))

    body.append("</body></html>")
    return "\n".join(body)


# ── Rendu PDF (reportlab) ─────────────────────────────────────────────────────

def render_pdf(groupes_data: list, journee: dict, niveau: str, output: Path,
               show_code: bool = False):
    try:
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError:
        print("reportlab requis : pip install reportlab --break-system-packages",
              file=sys.stderr)
        sys.exit(1)

    BLUE  = rl_colors.HexColor("#0072CE")
    DARK  = rl_colors.HexColor("#1A1A2E")
    RED   = rl_colors.HexColor("#CC0000")
    AMBER = rl_colors.HexColor("#E65100")
    GREEN = rl_colors.HexColor("#2e7d32")
    LGREY = rl_colors.HexColor("#CCCCCC")

    def _s(name, **kw):
        defaults = dict(fontName="Helvetica", fontSize=8, leading=10,
                        textColor=DARK, spaceAfter=1)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    S = {
        "h1"   : _s("h1", fontSize=13, textColor=BLUE, fontName="Helvetica-Bold",
                     spaceAfter=3),
        "meta" : _s("meta", fontSize=7, textColor=rl_colors.grey, spaceAfter=6),
        "h2"   : _s("h2", fontSize=10, textColor=rl_colors.white,
                     fontName="Helvetica-Bold", backColor=BLUE,
                     leftIndent=4, borderPad=3, spaceAfter=2, spaceBefore=10),
        "h3"   : _s("h3", fontSize=9, textColor=BLUE, fontName="Helvetica-Bold",
                     spaceAfter=1, spaceBefore=6),
        "trips": _s("trips", fontSize=7, textColor=rl_colors.grey, spaceAfter=3),
        "no_gd": _s("no_gd", fontSize=8, textColor=LGREY,
                     fontName="Helvetica-Oblique", spaceAfter=4),
        "body" : _s("body"),
    }

    # Styles pour cellules de tableau (word-wrap via Paragraph)
    CS = {
        "base"   : _s("cs_base",   fontSize=7, leading=9),
        "gd"     : _s("cs_gd",     fontSize=7, leading=9, fontName="Helvetica-Bold",
                       textColor=DARK),
        "gd_add" : _s("cs_gd_add", fontSize=7, leading=9, fontName="Helvetica-Bold",
                       textColor=GREEN),
        "gd_rem" : _s("cs_gd_rem", fontSize=7, leading=9, textColor=LGREY),
        "arr"    : _s("cs_arr",    fontSize=7, leading=9),
        "arr_red": _s("cs_arr_r",  fontSize=7, leading=9, textColor=RED),
        "arr_amb": _s("cs_arr_a",  fontSize=7, leading=9, textColor=AMBER),
        "eff"    : _s("cs_eff",    fontSize=6.5, leading=8.5, textColor=DARK),
        "seq"    : _s("cs_seq",    fontSize=7, leading=9, textColor=LGREY),
        "add_grn": _s("cs_ag",     fontSize=7, leading=9, textColor=GREEN,
                       fontName="Helvetica-Bold"),
    }

    date_str  = journee.get("date", "")
    garage_id = journee.get("garage_id", "")
    garage    = journee.get("garage", "")
    jnum      = journee.get("journee_numero", "")
    duree     = journee.get("temps_travaille", "")

    story = [
        Paragraph(f"Rapport journalier — {date_str}", S["h1"]),
        Paragraph(
            f"Garage {garage_id} — {garage}  ·  "
            f"Journée #{jnum}  ·  Durée {duree}  ·  Niveau : {niveau}",
            S["meta"],
        ),
        HRFlowable(width="100%", thickness=0.5),
        Spacer(1, 4),
    ]

    # Largeurs colonnes : total = 186mm (letter - 2×15mm marges)
    # [#, G-D, (Code), Arrêt/Détour, #evt/Effectif]
    if show_code:
        COL_W = [8*mm, 50*mm, 14*mm, 84*mm, 30*mm]
    else:
        COL_W = [8*mm, 50*mm, 98*mm, 30*mm]

    HDR = ["#", "G-D"] + (["Code"] if show_code else []) + \
          ["Arrêt / Détour", "#évènement / Effectif / Période"]

    for gd in groupes_data:
        groupe     = gd["groupe"]
        rows       = gd["rows"]
        events_app = gd["events"]
        events_all = gd["events_all"]
        parcours   = gd["parcours"]
        id_p       = groupe.get("id_parcours")
        trips      = groupe.get("trips", [])
        ligne      = groupe["ligne"]
        direction  = groupe["direction"]

        # En-tête de section : "24 Ouest — ID 2"
        story.append(Paragraph(f"{ligne} {direction.capitalize()} — ID {id_p}", S["h2"]))

        pname  = (parcours.get("name") or f"Parcours {id_p}") if parcours else f"Parcours {id_p}"
        pstart = (parcours.get("start") or "") if parcours else ""
        pend   = (parcours.get("end")   or "") if parcours else ""
        times  = ", ".join(t["depart_heure"] for t in trips if t.get("depart_heure"))
        sub    = pname
        if pstart:
            sub += f"  —  {pstart} → {pend}"
        story.append(Paragraph(sub, S["h3"]))
        story.append(Paragraph(f"Départs : {times}", S["trips"]))

        filtered = filter_rows_by_niveau(rows, niveau)

        if not parcours:
            story.append(Paragraph("G-D non disponible pour cette direction.", S["no_gd"]))
        elif not filtered and niveau != "détaillé":
            story.append(Paragraph("Aucune modification pour ce parcours.", S["no_gd"]))
        else:
            tdata  = [HDR]
            tstyle = [
                ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
                ("FONTSIZE",     (0, 0), (-1, 0),  7),
                ("BACKGROUND",   (0, 0), (-1, 0),  rl_colors.HexColor("#2c5f8a")),
                ("TEXTCOLOR",    (0, 0), (-1, 0),  rl_colors.white),
                ("GRID",         (0, 0), (-1, -1), 0.25, LGREY),
                ("VALIGN",       (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING",  (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING",   (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
            ]

            periode_by_eid_pdf = {str(e.get("evenement_id", "")): _format_periode(e)
                                   for e in events_app}
            prev_arr_key_pdf = None
            prev_ev_eids_pdf = set()   # eid des badges #évènement affichés à la ligne précédente
            for ri, r in enumerate(filtered, start=1):
                d_added   = r.get("detour_added",   False)
                d_removed = r.get("detour_removed",  False)
                inline    = r.get("added_inline",    False)
                cancelled = r.get("cancelled",       [])
                label     = r.get("detour_label",    "")
                gd_txt    = r.get("gd") or ""
                stop_nm   = r.get("stop_name") or ""
                stop_cd   = r.get("stop_code") or ""
                seq       = str(r["seq"]) if r.get("seq") else ""

                key = _arr_key(r)
                is_ditto = bool(key) and key == prev_arr_key_pdf
                if key:
                    prev_arr_key_pdf = key

                if inline:
                    arr_p = Paragraph(f"+ {stop_nm}", CS["add_grn"])
                    if not is_ditto:
                        _albl = r.get("added_short_label") or r.get("added_label", "")
                        _txt = f"+ {stop_nm}"
                        if _albl:
                            _txt += f"<br/>{_albl}"
                        if r.get("commentaire"):
                            _txt += f"<br/>{r['commentaire']}"
                        arr_p = Paragraph(_txt, CS["add_grn"])
                    eid_in    = str(r.get("evenement_id", ""))
                    ditto_eid = bool(eid_in) and eid_in in prev_ev_eids_pdf
                    eff_txt   = "" if ditto_eid else r.get("effectif", "")
                    per_txt   = "" if ditto_eid else periode_by_eid_pdf.get(eid_in, "")
                    eff_parts_in = []
                    if eid_in:
                        line = f"#{eid_in}"
                        if eff_txt:
                            line += f"<br/>{eff_txt}"
                        if per_txt:
                            line += f"<br/>{per_txt}"
                        eff_parts_in.append(line)
                    eff_p = Paragraph("<br/>".join(eff_parts_in), CS["eff"]) if eff_parts_in else ""
                    prev_ev_eids_pdf = {eid_in} if eid_in else set()
                    row_cells = [seq, "", arr_p, eff_p]
                    if show_code:
                        row_cells = [seq, "", "", arr_p, eff_p]
                    tdata.append(row_cells)
                    continue

                # G-D cell
                if d_added:
                    gd_text = f"&gt;&gt; {gd_txt}"
                    if label:
                        gd_text += f"<br/>({label})"
                    gd_p = Paragraph(gd_text, CS["gd_add"])
                elif d_removed:
                    gd_p = Paragraph(f"[X] {gd_txt}", CS["gd_rem"])
                else:
                    gd_p = Paragraph(gd_txt, CS["gd"]) if gd_txt else ""

                # Arrêt / Détour cell — toujours construire eff_lines (même pour ditto)
                plain_gd = gd_txt and not d_added and not d_removed and not cancelled
                show_stop = stop_nm and not (niveau == "standard" and plain_gd)
                if not cancelled:
                    arr_style = CS["arr"]
                elif arret_reellement_annule(cancelled):
                    arr_style = CS["arr_red"]
                else:
                    arr_style = CS["arr_amb"]
                eff_lines = []
                seen_eid  = set()
                arr_lines = ([stop_nm] if show_stop else [])
                if not is_ditto:
                    for ev in cancelled:
                        nom_evt = ev.get("nom_evt", "")
                        if nom_evt and nom_evt != stop_nm:
                            arr_lines.append(f"  📍 {nom_evt}")
                        sym = TYPE_SYMBOL.get(ev.get("type_evenement", ""), "!")
                        short = ev.get("short_label") or ev["label"]
                        arr_lines.append(f"{sym} {short}")
                        if ev.get("commentaire"):
                            arr_lines.append(f"  → {ev['commentaire']}")
                eff_parts = []
                for ev in cancelled:
                    eid = str(ev.get("evenement_id", ""))
                    eff = ev.get("effectif", "")
                    if eid and eid not in seen_eid:
                        eff_parts.append((eid, eff))
                        seen_eid.add(eid)
                if d_added:
                    eid = str(r.get("evenement_id", ""))
                    eff = r.get("effectif", "")
                    if eid and eid not in seen_eid:
                        eff_parts.append((eid, eff))
                        seen_eid.add(eid)

                # Badges #évènement / Effectif / Période — Effectif et Période
                # sont tus quand le même évènement couvrait déjà la ligne précédente.
                curr_ev_eids_pdf = set()
                for eid, eff in eff_parts:
                    ditto_eid = eid in prev_ev_eids_pdf
                    per = "" if ditto_eid else periode_by_eid_pdf.get(eid, "")
                    eff = "" if ditto_eid else eff
                    line = f"#{eid}"
                    if eff:
                        line += f"<br/>{eff}"
                    if per:
                        line += f"<br/>{per}"
                    eff_lines.append(line)
                    curr_ev_eids_pdf.add(eid)
                prev_ev_eids_pdf = curr_ev_eids_pdf

                arr_p = Paragraph("<br/>".join(arr_lines), arr_style) if arr_lines else ""
                eff_p = Paragraph("<br/>".join(eff_lines), CS["eff"]) if eff_lines else ""

                if show_code:
                    row_cells = [seq, gd_p, stop_cd, arr_p, eff_p]
                else:
                    row_cells = [seq, gd_p, arr_p, eff_p]
                tdata.append(row_cells)

                if d_removed:
                    tstyle.append(("TEXTCOLOR", (0, ri), (-1, ri), LGREY))

            t = Table(tdata, colWidths=COL_W)
            t.setStyle(TableStyle(tstyle))
            story.append(t)

        # Tableau événements — pleine largeur, Paragraph pour word-wrap
        if events_all:
            app_ids  = {e.get("evenement_id") for e in events_app}
            EV_S     = _s("ev_cell",  fontSize=6.5, leading=8.5)
            EV_GRY_S = _s("ev_grey",  fontSize=6.5, leading=8.5, textColor=LGREY)
            ev_data  = [["", "#", "Titre", "Effectif", "Période"]]
            ev_style = [
                ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
                ("FONTSIZE",     (0, 0), (-1, 0),  6.5),
                ("BACKGROUND",   (0, 0), (-1, 0),  rl_colors.HexColor("#f0f0f0")),
                ("GRID",         (0, 0), (-1, -1), 0.25, LGREY),
                ("VALIGN",       (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING",  (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING",   (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 1),
            ]
            for ri, e in enumerate(events_all, start=1):
                eid   = str(e.get("evenement_id", "?"))
                appl  = eid in app_ids
                mark  = "OK" if appl else "--"
                cs    = EV_S if appl else EV_GRY_S
                ev_data.append([
                    mark, eid,
                    Paragraph(e.get("titre", ""), cs),
                    Paragraph(e.get("effectif", ""), cs),
                    Paragraph(_format_periode(e), cs),
                ])
            et = Table(ev_data,
                       colWidths=[6*mm, 18*mm, 78*mm, 52*mm, 32*mm])
            et.setStyle(TableStyle(ev_style))
            story.append(Spacer(1, 4))
            story.append(et)

        story.append(Spacer(1, 8))

    doc = SimpleDocTemplate(
        str(output), pagesize=letter,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm,
    )
    doc.build(story)


# ── Worker parallèle ─────────────────────────────────────────────────────────

def _process_groupe_worker(args):
    """Wrapper sans cache partagé — chaque processus gère son propre cache."""
    groupe, date_str = args
    return process_groupe(groupe, date_str, {})


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Rapport journalier v2 — source : fichier journée JSON."
    )
    ap.add_argument("--journee", required=True, type=Path,
                    help="data/journees/journee-YYYY-MM-DD.json")
    ap.add_argument("--niveau", choices=["détaillé", "standard", "compact"],
                    default="détaillé",
                    help="Niveau de détail (défaut : détaillé)")
    ap.add_argument("--format", choices=["html", "pdf"], default="pdf", dest="fmt",
                    help="Format de sortie (défaut : pdf)")
    ap.add_argument("--output", type=Path, default=None,
                    help="Chemin de sortie (défaut : data/rapports/rapport-v2-DATE.EXT)")

    code_grp = ap.add_mutually_exclusive_group()
    code_grp.add_argument("--codearret", dest="show_code", action="store_true",
                          default=False,
                          help="Affiche la colonne 'Code arrêt' (désactivée par défaut)")
    code_grp.add_argument("--nocodearret", dest="show_code", action="store_false",
                          help="Cache la colonne 'Code arrêt' (défaut)")

    ap.add_argument("--filtre-ligne",        default=None,
                    help="Restreindre le rapport à cette ligne (ex: 24)")
    ap.add_argument("--filtre-direction",    default=None,
                    help="Restreindre le rapport à cette direction (ex: ouest)")
    ap.add_argument("--filtre-id-parcours",  type=int, default=None,
                    help="Restreindre le rapport à cet ID parcours (ex: 3)")

    args = ap.parse_args()

    try:
        out = generer_rapport(
            args.journee,
            fmt=args.fmt,
            output=args.output,
            niveau=args.niveau,
            show_code=args.show_code,
            filtre_ligne=args.filtre_ligne,
            filtre_direction=args.filtre_direction,
            filtre_id_parcours=args.filtre_id_parcours,
        )
        print(f"Rapport généré : {out}")
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def generer_rapport(
    journee_path: Path,
    fmt: str = "html",
    output: Path | None = None,
    niveau: str = "détaillé",
    show_code: bool = False,
    filtre_ligne: str | None = None,
    filtre_direction: str | None = None,
    filtre_id_parcours: int | None = None,
) -> Path:
    """Génère le rapport v2 et retourne le chemin du fichier créé.

    Lève FileNotFoundError si journee_path n'existe pas,
    ValueError si la journée est vide ou si les filtres excluent tout.
    """
    if not journee_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {journee_path}")

    journee  = charger_journee(journee_path)
    date_str = journee.get("date", "inconnu")
    groupes  = groupes_de_service(journee, avec_trips=True)

    if not groupes:
        raise ValueError("Aucun trajet de service dans le fichier journée.")

    if filtre_ligne or filtre_direction or filtre_id_parcours is not None:
        groupes = [
            g for g in groupes
            if (filtre_ligne is None      or g["ligne"]       == filtre_ligne)
            and (filtre_direction is None  or g["direction"]   == filtre_direction)
            and (filtre_id_parcours is None or g["id_parcours"] == filtre_id_parcours)
        ]
        if not groupes:
            raise ValueError("Aucun groupe ne correspond aux filtres spécifiés.")

    if len(groupes) > 1:
        import os
        from concurrent.futures import ThreadPoolExecutor
        workers = min(len(groupes), os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            groupes_data = list(pool.map(
                _process_groupe_worker, [(g, date_str) for g in groupes]
            ))
    else:
        groupes_data = [process_groupe(groupes[0], date_str, {})]

    out = output or (OUTPUT_DIR / f"rapport-v2-{date_str}.{fmt}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        html = render_html(groupes_data, journee, niveau, show_code)
        out.write_text(html, encoding="utf-8")
    else:
        render_pdf(groupes_data, journee, niveau, out, show_code)

    return out


if __name__ == "__main__":
    main()
