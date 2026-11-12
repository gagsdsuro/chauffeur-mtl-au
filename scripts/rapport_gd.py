#!/usr/bin/env python3
"""
Rapport détaillé G-D / Arrêts / Détours
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
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Noyau de domaine partagé (chauffeur/) ────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from chauffeur.effectif import parse_shift_time, event_applies_to_shift  # noqa: E402
from chauffeur.evenements import (  # noqa: E402
    arret_reellement_annule,
    titre_annule_l_arret,
)
from chauffeur.gd import (  # noqa: E402
    _select_parcours, build_rows, filter_rows_by_stop_range, annotate_events,
    apply_gd_detours, insert_added_stops_inline, rows_de_rendu, message_diagnostic,
)
from chauffeur.modeles import FichierGD, ParcoursGD  # noqa: E402
from chauffeur import gtfs as _gtfs  # noqa: E402

# Dossier GTFS par défaut ; main() le réaffecte selon --base, les outils de test
# peuvent le surcharger (rg.GTFS = ...).
GTFS = PROJECT_ROOT / "data" / "gtfs" / "gtfs_stm"


def parse_args():
    p = argparse.ArgumentParser(description="Rapport G-D / Arrêts / Détours")
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
                   help="Code de l'arrêt de départ effectif (ex: 54112). "
                        "Tronque l'affichage à partir de cet arrêt.")
    p.add_argument("--arret-fin", default=None,
                   help="Code de l'arrêt de fin effectif (ex: 57365). "
                        "Tronque l'affichage jusqu'à cet arrêt.")
    p.add_argument("--format", default="html", choices=["html", "md"])
    p.add_argument("--base", default=None,
                   help="Chemin racine du projet (défaut: dossier parent du script)")
    p.add_argument("--output", default=None,
                   help="Chemin du fichier de sortie (défaut: à côté du script)")
    return p.parse_args()


# Logique d'effectif (parse_shift_time, event_applies_to_shift) : importée de
# chauffeur.effectif (cf. en-tête).


# ── Chargement des données ────────────────────────────────────────────────────

# Accès GTFS : délégué à chauffeur.gtfs (dossier GTFS injecté). Wrappers minces
# conservant l'API historique (rg.get_route_id, …) liée à la variable GTFS.
def get_route_id(ligne):
    return _gtfs.route_id(GTFS, ligne)


def get_direction_id(route_id, direction):
    return _gtfs.direction_id(GTFS, route_id, direction)


def get_stops_for_line(route_id, dir_id):
    return _gtfs.stops_for_line(GTFS, route_id, dir_id)


def load_stop_names():
    return _gtfs.stop_names(GTFS)


def load_gd(ligne, direction, base, parcours_hint=None):
    """
    Charge les instructions G-D et le parcours sélectionné.
    Retourne (instructions: list[str], parcours: ParcoursGD | None, all_parcours: list[ParcoursGD]).
    """
    path = base / f"data/Gauche-Droite/gd{ligne}_{direction}.json"
    if not path.exists():
        return [], None, []
    with open(path) as f:
        fichier = FichierGD.from_dict(json.load(f))
    if not fichier.routes:
        return [], None, []
    route = fichier.routes[0]
    if not route.parcours:
        return [], None, []
    parcours = _select_parcours(route.parcours, parcours_hint)
    return parcours.direction, parcours, route.parcours


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
    start = parcours.start if parcours else ""
    end   = parcours.end   if parcours else ""
    quart = fmt_shift_range(shift_start, shift_end, base_date)

    lines = [f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Rapport G-D — Ligne {args.ligne} {args.direction.capitalize()} — {args.date}</title>
<style>
  html {{ color-scheme: light; background: #fff; }}
  body {{ font-family: Arial, sans-serif; font-size: 13px; margin: 20px; color: #1A1A2E; background: #fff; }}
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
  .cancelled.detour-removed td {{ background: #fff0f0; }}
  .cancelled.detour-removed .gd {{ text-decoration: line-through; color: #e65100; opacity: 0.7; }}
  .maintenu td {{ background: #fff8e1; }}
  .maintenu .stop-name {{ color: #e65100; }}
  .maintenu .event-label {{ color: #e65100; }}
  .maintenu.detour-removed td {{ background: #fff8e1; }}
  .maintenu.detour-removed .gd {{ text-decoration: line-through; color: #e65100; opacity: 0.7; }}
  .event-label {{ font-size: 10px; color: #c00; display: block; }}
  .event-precision {{ font-size: 11px; color: #b45309; font-weight: bold; display: block; }}
  .added {{ background: #f0fff0; }}
  .added-section {{ margin-top: 16px; padding: 8px; background: #e8f5e9; border-left: 4px solid #4caf50; }}
  .detour-added td {{ background: #e8f5e9; }}
  .detour-added .gd {{ color: #2e7d32; }}
  .added-inline td {{ background: #f0fff0; }}
  .added-inline .stop-name {{ color: #2e7d32; font-weight: bold; }}
  .added-inline-label {{ font-size: 10px; color: #388e3c; display: block; }}
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
<div class="meta">{start} → {end} &nbsp;·&nbsp; {parcours.name if parcours else ""} &nbsp;·&nbsp; Quart : {quart}</div>"""]

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
        added_inline   = r.get("added_inline", False)

        if added_inline:
            cls = ' class="added-inline"'
        elif detour_added:
            cls = ' class="detour-added"'
        elif cancelled:
            # Rouge seulement si l'arrêt disparaît vraiment ; ambre s'il reste
            # desservi (« Arrêt déplacé », « Information chauffeur »).
            etat = "cancelled" if arret_reellement_annule(cancelled) else "maintenu"
            cls = (f' class="{etat} detour-removed"' if detour_removed
                   else f' class="{etat}"')
        elif detour_removed:
            cls = ' class="detour-removed"'
        else:
            cls = ""

        # Arrêt temporaire inline : rendu spécial, pas de cellule G-D
        if added_inline:
            name_span = f'<span class="stop-name">➕ {r["stop_name"]}</span>'
            if r.get("added_label"):
                name_span += f'<span class="added-inline-label">{r["added_label"]}</span>'
            eff = r.get("effectif", "")
            eff_cell = f'<span class="effectif">{eff}</span>' if eff else ""
            lines.append(
                f'<tr{cls}>'
                f'<td class="seq"></td>'
                f'<td></td>'
                f'<td class="code"></td>'
                f'<td>{name_span}</td>'
                f'<td>{eff_cell}</td>'
                f'</tr>'
            )
            continue

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
                sym = "❌" if titre_annule_l_arret(ev.get("type_evenement", "")) else "⚠️"
                name_span += f'<span class="event-label">{sym} {label_str}</span>'
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
    start = parcours.start if parcours else ""
    end   = parcours.end   if parcours else ""
    quart = fmt_shift_range(shift_start, shift_end, base_date)

    lines = [
        f"# Ligne {args.ligne} — {args.direction.capitalize()} | {date_fmt}",
        f"**{start} → {end}** · {parcours.name if parcours else ''} · Quart : {quart}\n",
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

        # Arrêt temporaire inline
        if r.get("added_inline"):
            label_md = f" *{r['added_label']}*" if r.get("added_label") else ""
            eff_md   = r.get("effectif", "")
            lines.append(f"| | | | ➕ **{r['stop_name']}**{label_md} | {eff_md} |")
            continue

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
            eff_ordered = []          # ordre stable (déduplication via seen_eff)
            ev_parts = []
            precision_parts = []
            for ev in cancelled:
                ev_parts.append(ev["label"])
                eff = ev.get("effectif", "")
                if eff and eff not in seen_eff:
                    seen_eff.add(eff)
                    eff_ordered.append(eff)
                nom_evt = ev.get("nom_evt", "")
                if nom_evt and nom_evt != name:
                    precision_parts.append(f"📍 {nom_evt}")
            precision = " ".join(precision_parts)
            # Le Markdown n'a pas de teinte : c'est le barré et le symbole qui
            # disent si l'arrêt disparaît ou s'il reste desservi.
            if arret_reellement_annule(cancelled):
                name = f"~~{name}~~ {precision} ❌ " + " / ".join(ev_parts)
            else:
                name = f"{name} {precision} ⚠️ " + " / ".join(ev_parts)
            effectif_str = " / ".join(eff_ordered)

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
        selected_name = parcours.name if parcours else ""
        for p in all_parcours:
            marker = "►" if p.name == selected_name else " "
            print(f"    {marker} [{p.id}] {p.name}  {p.start_code} → {p.end_code}")

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
    diagnostics = []
    rows = apply_gd_detours(rows, events, diagnostics)
    rows, added = insert_added_stops_inline(rows, added, diagnostics)
    for message in dict.fromkeys(message_diagnostic(d) for d in diagnostics):
        print(f"  ⚠️  {message}")

    # Tronquer selon la plage d'arrêts effective du chauffeur
    if args.arret_debut or args.arret_fin:
        before = len(rows)
        rows = filter_rows_by_stop_range(rows, args.arret_debut, args.arret_fin)
        print(f"  Plage d'arrêts : {args.arret_debut or '(début)'} → "
              f"{args.arret_fin or '(fin)'}  ({len(rows)}/{before} lignes)")
    rows = rows_de_rendu(rows)

    if orphan_events:
        print(f"  ⚠️  {len(orphan_events)} événement(s) actif(s) hors trajet GTFS sélectionné — affichés en alerte")

    ext = args.format
    if args.output:
        outfile = Path(args.output)
        outfile.parent.mkdir(parents=True, exist_ok=True)
    else:
        outfile = Path(__file__).resolve().parent / f"rapport_{args.ligne}_{args.direction}_{args.date}.{ext}"

    if args.format == "html":
        content = render_html(rows, added, args, parcours, shift_start, shift_end, orphan_events)
    else:
        content = render_md(rows, added, args, parcours, shift_start, shift_end, orphan_events)

    outfile.write_text(content, encoding="utf-8")
    print(f"  ✅ Rapport écrit: {outfile}")


if __name__ == "__main__":
    main()
