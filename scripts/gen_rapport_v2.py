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
import copy
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chauffeur.gd import (
    build_rows, annotate_events, apply_gd_detours, insert_added_stops_inline,
    event_applicable_to_parcours, rows_de_rendu, message_diagnostic, _diag,
)
from chauffeur.gtfs import stops_for_parcours, stop_names as gtfs_stop_names
from chauffeur.depots import charger_journee, charger_gd, evenements_pour_date
from chauffeur.avis import AVIS_RAPPORT
from chauffeur.effectif import parse_shift_time
from chauffeur.evenements import (
    applicable_a_la_plage, arret_reellement_annule,
    trier_evenements_par_arrets,
)
from chauffeur.journee import groupes_de_service
from chauffeur.registre_appariement import appariement_pour_rapport
from chauffeur.registre_detours import fournisseurs as fournisseurs_detours

GTFS_DIR   = ROOT / "data" / "gtfs" / "gtfs_stm"
OUTPUT_DIR = ROOT / "data" / "rapports"


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

NIVEAUX = ("détaillé", "standard", "compact")


def evenements_par_trajet(trips: list, jour: date, events_jour: list,
                          applicable_parcours=None) -> list:
    """Pour chaque trajet, tuple des indices (dans `events_jour`) des évènements
    applicables à sa plage (départ → arrivée), puis au parcours.

    Les indices, plutôt que les `evenement_id`, distinguent les variantes d'un
    même ID. `applicable_parcours` (évènement → bool) est indépendant du trajet :
    appliqué ici pour ne pas scinder un parcours sur un évènement qui ne le
    concerne de toute façon pas.
    """
    resultat = []
    for t in trips:
        plage = ((t["depart_heure"], t["arrivee_heure"])
                 if t.get("depart_heure") and t.get("arrivee_heure") else None)
        resultat.append(tuple(
            i for i, e in enumerate(events_jour)
            if applicable_a_la_plage(e, jour, plage)
            and (applicable_parcours is None or applicable_parcours(e))
        ))
    return resultat


def scinder_trajets(trips: list, signatures: list, jour: date) -> list:
    """Regroupe les trajets de même signature d'évènements.

    Retourne [(signature, [trajets])] dans l'ordre du premier départ. Sans
    trajet, un seul groupe vide (aucun évènement applicable).
    """
    if not trips:
        return [((), [])]
    groupes: dict[tuple, list] = {}
    for t, sig in zip(trips, signatures):
        groupes.setdefault(sig, []).append(t)

    def premier_depart(item):
        heures = []
        for t in item[1]:
            try:
                heures.append(parse_shift_time(t["depart_heure"], jour))
            except (KeyError, ValueError, TypeError, AttributeError):
                pass
        return min(heures) if heures else datetime.max

    return sorted(groupes.items(), key=premier_depart)


def process_groupe(groupe: dict, date_str: str, ev_all_cache: dict) -> list:
    """Traite un groupe (ligne · direction · id parcours).

    Retourne une liste de résultats : un seul quand les évènements applicables
    sont les mêmes à tous les départs, un par ensemble distinct d'évènements
    sinon (le parcours est alors dupliqué, `groupe["variante"] = (k, n)`).
    """
    ligne, direction, id_p = groupe["ligne"], groupe["direction"], groupe.get("id_parcours")
    jour = date.fromisoformat(date_str)
    trips = groupe.get("trips", [])
    instructions, parcours = charger_gd(ligne, direction, id_p)
    stops_ordered, snames  = _load_gtfs_stops(ligne, direction, id_p)

    cache_key = (ligne, direction)
    if cache_key not in ev_all_cache:
        ev_all_cache[cache_key] = evenements_pour_date(ligne, direction, jour)
    events_all = trier_evenements_par_arrets(ev_all_cache[cache_key], stops_ordered)

    if not instructions:
        sigs = evenements_par_trajet(trips, jour, events_all)
        idx = sorted({i for sig in sigs for i in sig})
        return [dict(groupe=groupe, rows=[], added=[],
                     events=[events_all[i] for i in idx],
                     events_all=events_all, parcours=parcours, appariement=None,
                     alertes=[], diagnostics=[])]

    # Appariement persisté (validé par un chauffeur) s'il est à jour, sinon
    # calcul automatique — jamais bloquant, l'avertissement suit le groupe.
    appariement = None
    if stops_ordered:
        rows_base, appariement = appariement_pour_rapport(
            ligne, direction, parcours, stops_ordered, snames)
    else:
        rows_base = build_rows(instructions, stops_ordered, snames)

    # Évènements non-applicables à ce parcours spécifique : exclus ici, ils
    # restent visibles dans le tableau des évènements (events_all) comme
    # « non-applicable ». GTFS indisponible (stops_ordered vide) → stop_ids=None :
    # les arrêts du parcours sont inconnus et les évènements à arrêts annulés
    # sont présumés applicables (fail-safe, même règle que l'onglet Ma journée).
    stop_ids = ({r.get("stop_code") or r["stop_id"] for r in rows_base if r.get("stop_id")}
                if stops_ordered else None)
    sigs = evenements_par_trajet(
        trips, jour, events_all,
        lambda e: event_applicable_to_parcours(e, stop_ids, instructions))
    variantes = scinder_trajets(trips, sigs, jour)

    # Choix humains validés (page Détours, communs) : imposés au pipeline.
    choix, choix_arrets = fournisseurs_detours(ligne, direction)

    resultats = []
    for k, (sig, trips_v) in enumerate(variantes, start=1):
        events = [events_all[i] for i in sig]
        # annotate_events & co. modifient les lignes en place : une copie par variante.
        rows = copy.deepcopy(rows_base)
        rows, added, orphelins = annotate_events(rows, events)
        diagnostics = [_diag(e, "hors_trajet") for e in orphelins] if stops_ordered else []
        rows = apply_gd_detours(rows, events, diagnostics, choix)
        rows, added = insert_added_stops_inline(rows, added, diagnostics, choix_arrets)
        rows = rows_de_rendu(rows)
        alertes = list(dict.fromkeys(message_diagnostic(d) for d in diagnostics))
        g = dict(groupe, trips=trips_v) if len(variantes) > 1 else groupe
        if len(variantes) > 1:
            g["variante"] = (k, len(variantes))
        resultats.append(dict(groupe=g, rows=rows, added=added, events=events,
                              events_all=events_all, parcours=parcours,
                              appariement=appariement, alertes=alertes,
                              diagnostics=diagnostics))
    return resultats


def avertissement_appariement(info: dict | None) -> str:
    """Texte d'avertissement du groupe, ou "" si l'appariement est sûr."""
    if not info:
        return ""
    if info["statut"] == "a_revalider":
        return ("⚠ Appariement des arrêts à revalider : le G-D ou le GTFS a changé "
                "depuis la dernière validation.")
    if info["statut"] == "incertain":
        return (f"⚠ Appariement des arrêts incertain ({info['blocs']} segment(s)) : "
                "la position de certains arrêts est à vérifier.")
    return ""


def avertissements_groupe(gd: dict) -> list:
    """Avertissements non bloquants d'un groupe : appariement des arrêts, puis
    ce que le pipeline n'a pas pu décider seul pour les évènements (détour non
    ancré, arrêt ajouté non placé ou d'ordre incertain)."""
    textes = [avertissement_appariement(gd.get("appariement"))]
    textes += [f"⚠ {a}" for a in gd.get("alertes", [])]
    return [t for t in textes if t]


# ── Rendu HTML ────────────────────────────────────────────────────────────────

_CSS = """
html{color-scheme:light;background:#fff}
body{font-family:Arial,sans-serif;font-size:13px;margin:20px;color:#1A1A2E;background:#fff}
h1{font-size:16px;margin-bottom:4px;color:#0072CE}
.meta{color:#555;margin-bottom:12px;font-size:12px}
h2{font-size:14px;margin:22px 0 2px;padding:4px 8px;background:#0072CE;color:#fff}
h3{font-size:12px;margin:10px 0 2px;color:#1a4a7a}
.trips{font-size:11px;color:#555;margin-bottom:6px}
.no-gd{color:#888;font-style:italic;margin:6px 0 10px}
.avis{color:#777;font-size:10px;margin-top:18px;border-top:1px solid #ddd;padding-top:6px}
.avert-app{color:#E65100;font-weight:bold;font-size:11px;margin:2px 0 6px}
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
.ev-detail{display:block;font-size:10px;color:#7a3e00;margin-top:1px}
.variante{color:#555;font-size:11px;font-style:italic;margin:2px 0 4px}
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


def _libelle_arret(a) -> str:
    """Arrêt annulé/ajouté : objet {id, nom} ou ancienne chaîne libre."""
    if isinstance(a, dict):
        code, nom = str(a.get("id") or "").strip(), (a.get("nom") or "").strip()
        return f"{code} — {nom}" if code and nom else (code or nom)
    return str(a or "").strip()


def _details_evenement(e: dict, diagnostics: list) -> list:
    """Informations disponibles d'un évènement que le pipeline n'a pas su traiter
    seul (texte brut, une chaîne par ligne) ; [] si aucun avertissement ne le
    concerne — l'évènement reste alors compact dans le sommaire.
    """
    eid = str(e.get("evenement_id", ""))
    diags = [d for d in diagnostics or [] if str(d.get("evenement_id", "")) == eid]
    if not diags:
        return []
    lignes = []
    annules = [_libelle_arret(a) for a in e.get("arrets_annules") or []]
    if any(annules):
        lignes.append("Arrêts annulés : " + " ; ".join(a for a in annules if a))
    ajoutes = [_libelle_arret(a) for a in e.get("arrets_ajoutes") or []]
    if any(ajoutes):
        lignes.append("Arrêts ajoutés : " + " ; ".join(a for a in ajoutes if a))
    if e.get("commentaire"):
        lignes.append("Commentaire : " + " / ".join(
            l.strip() for l in str(e["commentaire"]).splitlines() if l.strip()))
    desc = [l.strip() for l in str(e.get("description_gd") or "").splitlines() if l.strip()]
    if desc:
        lignes.append("Description G-D : " + " › ".join(desc))
    lignes += [f"⚠ {message_diagnostic(d)}" for d in diags]
    return lignes


def _render_events_table_html(events_all: list, events_app: list,
                              diagnostics: list = ()) -> str:
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
        titre += "".join(f'<span class="ev-detail">{_h(l)}</span>'
                         for l in _details_evenement(e, diagnostics))
        eff    = _h(e.get("effectif", ""))
        per    = _h(_format_periode(e))
        out.append(f'<tr{cls}><td>{mark}</td><td>{eid}</td><td>{titre}</td>'
                   f'<td>{eff}</td><td>{per}</td></tr>')
    out.append("</tbody></table>")
    return "".join(out)


def _niveau_entete(groupes_data: list, niveau: str) -> tuple:
    """(libellé du niveau pour l'en-tête, niveaux différents selon les parcours ?)"""
    niveaux = {gd.get("niveau", niveau) for gd in groupes_data}
    if len(niveaux) > 1:
        return "par parcours", True
    return (niveaux.pop() if niveaux else niveau), False


def _entete_groupe(gd: dict, niveau: str, mixte: bool) -> str:
    groupe = gd["groupe"]
    txt = f'{groupe["ligne"]} {groupe["direction"].capitalize()} — ID {groupe.get("id_parcours")}'
    if mixte:
        txt += f' — {gd.get("niveau", niveau)}'
    return txt


def _note_variante(groupe: dict) -> str:
    if not groupe.get("variante"):
        return ""
    k, n = groupe["variante"]
    return ("Parcours dupliqué : les évènements applicables diffèrent selon "
            f"l'heure de départ ({k}/{n}).")


def render_html(groupes_data: list, journee: dict, niveau: str,
                show_code: bool = False) -> str:
    date_str  = journee.get("date", "")
    garage_id = journee.get("garage_id", "")
    garage    = journee.get("garage", "")
    jnum      = journee.get("journee_numero", "")
    duree     = journee.get("temps_travaille", "")

    niveau_txt, mixte = _niveau_entete(groupes_data, niveau)
    body = [
        f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        f'<title>Rapport {date_str}</title><style>{_CSS}</style></head><body>',
        f'<h1>Rapport journalier — {date_str}</h1>',
        f'<div class="meta">Garage {garage_id} — {garage}'
        f' &nbsp;·&nbsp; Journée #{jnum} &nbsp;·&nbsp; Durée {duree}'
        f' &nbsp;·&nbsp; Niveau : {niveau_txt}</div>',
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

        niv = gd.get("niveau", niveau)

        # En-tête de section : "24 Ouest — ID 2"
        body.append(f'<h2>{_h(_entete_groupe(gd, niveau, mixte))}</h2>')
        if _note_variante(groupe):
            body.append(f'<p class="variante">{_h(_note_variante(groupe))}</p>')

        pname  = (parcours.get("name") or f"Parcours {id_p}") if parcours else f"Parcours {id_p}"
        pstart = (parcours.get("start") or "") if parcours else ""
        pend   = (parcours.get("end")   or "") if parcours else ""
        times  = ", ".join(t["depart_heure"] for t in trips if t.get("depart_heure"))
        sub    = f"{pname}"
        if pstart:
            sub += f" — {_h(pstart)} → {_h(pend)}"
        body.append(f'<h3>{sub}</h3><div class="trips">Départs : {times}</div>')
        for avert in avertissements_groupe(gd):
            body.append(f'<p class="avert-app">{_h(avert)}</p>')

        filtered = filter_rows_by_niveau(rows, niv)

        if not parcours:
            body.append('<p class="no-gd">G-D non disponible pour cette direction.</p>')
        elif not filtered and niv != "détaillé":
            body.append('<p class="no-gd">Aucune modification pour ce parcours.</p>')
        else:
            body.append(_render_rows_html(filtered, show_code, niv, events_app))

        body.append(_render_events_table_html(
            events_all, events_app, gd.get("diagnostics", [])))

    body.append(f'<p class="avis">{_h(AVIS_RAPPORT)}</p>')
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
        "avert_app": _s("avert_app", fontSize=7, textColor=AMBER,
                        fontName="Helvetica-Bold", spaceAfter=3),
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
    niveau_txt, mixte = _niveau_entete(groupes_data, niveau)

    story = [
        Paragraph(f"Rapport journalier — {date_str}", S["h1"]),
        Paragraph(
            f"Garage {garage_id} — {garage}  ·  "
            f"Journée #{jnum}  ·  Durée {duree}  ·  Niveau : {niveau_txt}",
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

        niveau_g = gd.get("niveau", niveau)

        # En-tête de section : "24 Ouest — ID 2"
        story.append(Paragraph(_h(_entete_groupe(gd, niveau, mixte)), S["h2"]))
        if _note_variante(groupe):
            story.append(Paragraph(_h(_note_variante(groupe)), S["trips"]))

        pname  = (parcours.get("name") or f"Parcours {id_p}") if parcours else f"Parcours {id_p}"
        pstart = (parcours.get("start") or "") if parcours else ""
        pend   = (parcours.get("end")   or "") if parcours else ""
        times  = ", ".join(t["depart_heure"] for t in trips if t.get("depart_heure"))
        sub    = pname
        if pstart:
            sub += f"  —  {pstart} → {pend}"
        story.append(Paragraph(sub, S["h3"]))
        story.append(Paragraph(f"Départs : {times}", S["trips"]))
        for avert in avertissements_groupe(gd):
            story.append(Paragraph(_h(avert.replace("⚠ ", "")), S["avert_app"]))

        filtered = filter_rows_by_niveau(rows, niveau_g)

        if not parcours:
            story.append(Paragraph("G-D non disponible pour cette direction.", S["no_gd"]))
        elif not filtered and niveau_g != "détaillé":
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
                show_stop = stop_nm and not (niveau_g == "standard" and plain_gd)
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
                titre_pdf = _h(e.get("titre", "")) + "".join(
                    f"<br/>{_h(l.replace('⚠ ', ''))}"
                    for l in _details_evenement(e, gd.get("diagnostics", [])))
                ev_data.append([
                    mark, eid,
                    Paragraph(titre_pdf, cs),
                    Paragraph(e.get("effectif", ""), cs),
                    Paragraph(_format_periode(e), cs),
                ])
            et = Table(ev_data,
                       colWidths=[6*mm, 18*mm, 78*mm, 52*mm, 32*mm])
            et.setStyle(TableStyle(ev_style))
            story.append(Spacer(1, 4))
            story.append(et)

        story.append(Spacer(1, 8))

    story.append(Paragraph(_h(AVIS_RAPPORT), S["no_gd"]))

    doc = SimpleDocTemplate(
        str(output), pagesize=letter,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm,
    )
    doc.build(story)


# ── Sélection des parcours ───────────────────────────────────────────────────

def cle_groupe(groupe: dict) -> tuple:
    """Clé de sélection d'un groupe : (ligne, direction, id_parcours), casse neutre."""
    return (str(groupe["ligne"]).lower(), str(groupe["direction"]).lower(),
            groupe.get("id_parcours"))


def _normaliser_selection(selection: dict | None) -> dict:
    return {(str(l).lower(), str(d).lower(), i): niv
            for (l, d, i), niv in (selection or {}).items()}


def resoudre_selection(groupes: list, niveau: str, selection: dict | None) -> list:
    """[(groupe, niveau)] des groupes à générer.

    `selection` : {(ligne, direction, id_parcours): niveau ou None}. None (ou
    « aucun ») exclut le parcours ; une clé absente prend le niveau par défaut.
    Lève ValueError pour un niveau inconnu, un parcours absent de la journée ou
    une sélection qui n'en laisse aucun.
    """
    sel = _normaliser_selection(selection)
    inconnus = set(sel) - {cle_groupe(g) for g in groupes}
    if inconnus:
        l, d, i = sorted(inconnus, key=str)[0]
        raise ValueError(f"Parcours absent de la journée : {l} {d} ID {i}")
    retenus = []
    for g in groupes:
        niv = sel.get(cle_groupe(g), niveau)
        if niv in (None, "aucun"):
            continue
        if niv not in NIVEAUX:
            raise ValueError(f"Niveau inconnu : {niv!r} (attendu : "
                             f"{', '.join(NIVEAUX)}, aucun)")
        retenus.append((g, niv))
    if not retenus:
        raise ValueError("Aucun parcours sélectionné.")
    return retenus


def selection_est_personnalisee(groupes: list, niveau: str, selection: dict | None) -> bool:
    """Vrai si la sélection exclut un parcours ou s'écarte du niveau par défaut :
    le rapport n'est alors pas le rapport standard du niveau (autre fichier, pas
    de marquage « à jour »)."""
    sel = _normaliser_selection(selection)
    return any(sel.get(cle_groupe(g), niveau) != niveau for g in groupes)


def _parser_parcours(texte: str) -> tuple:
    """'24:ouest:2=compact' → (('24', 'ouest', 2), 'compact') ; niveau 'aucun' → None."""
    try:
        cle, niv = texte.rsplit("=", 1)
        ligne, direction, id_p = cle.split(":")
        id_parcours = int(id_p)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{texte!r} : format attendu LIGNE:DIRECTION:ID=NIVEAU (ex. 24:ouest:2=compact)")
    niv = niv.strip()
    if niv not in NIVEAUX + ("aucun",):
        raise argparse.ArgumentTypeError(
            f"{texte!r} : niveau « {niv} » inconnu ({', '.join(NIVEAUX)}, aucun)")
    return (ligne, direction, id_parcours), (None if niv == "aucun" else niv)


# ── Worker parallèle ─────────────────────────────────────────────────────────

def _process_groupe_worker(args):
    """Wrapper sans cache partagé — chaque processus gère son propre cache."""
    groupe, date_str = args
    return process_groupe(groupe, date_str, {})  # liste de résultats (variantes)


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

    ap.add_argument("--parcours", action="append", default=[], type=_parser_parcours,
                    metavar="LIGNE:DIR:ID=NIVEAU",
                    help="Niveau d'un parcours de la journée, répétable "
                         "(détaillé|standard|compact|aucun pour l'exclure ; "
                         "les autres prennent --niveau). Ex. : --parcours 24:ouest:2=compact "
                         "--parcours 445:ouest:19=aucun")

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
            selection=dict(args.parcours) or None,
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
    selection: dict | None = None,
) -> Path:
    """Génère le rapport v2 et retourne le chemin du fichier créé.

    Lève FileNotFoundError si journee_path n'existe pas,
    ValueError si la journée est vide ou si les filtres/la sélection excluent tout.

    `selection` : {(ligne, direction, id_parcours): niveau ou None} — niveau propre
    à chaque parcours, None pour ne pas le générer ; un parcours absent prend
    `niveau`. Un parcours dont les évènements diffèrent selon l'heure de départ
    est dupliqué en autant de sections.
    """
    if not journee_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {journee_path}")

    journee  = charger_journee(journee_path)
    date_str = journee.get("date", "inconnu")
    groupes  = groupes_de_service(journee, avec_trips=True)

    if not groupes:
        raise ValueError("Aucun trajet de service dans le fichier journée.")

    groupes_tous = groupes
    if filtre_ligne or filtre_direction or filtre_id_parcours is not None:
        groupes = [
            g for g in groupes
            if (filtre_ligne is None      or g["ligne"]       == filtre_ligne)
            and (filtre_direction is None  or g["direction"]   == filtre_direction)
            and (filtre_id_parcours is None or g["id_parcours"] == filtre_id_parcours)
        ]
        if not groupes:
            raise ValueError("Aucun groupe ne correspond aux filtres spécifiés.")

    niveaux = {}
    if selection:
        retenus = resoudre_selection(groupes_tous, niveau, selection)
        retenus = [(g, n) for g, n in retenus if g in groupes]
        if not retenus:
            raise ValueError("Aucun parcours sélectionné.")
        groupes = [g for g, _ in retenus]
        niveaux = {cle_groupe(g): n for g, n in retenus}

    if len(groupes) > 1:
        import os
        from concurrent.futures import ThreadPoolExecutor
        workers = min(len(groupes), os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            resultats = list(pool.map(
                _process_groupe_worker, [(g, date_str) for g in groupes]
            ))
    else:
        resultats = [process_groupe(groupes[0], date_str, {})]

    groupes_data = [gd for variantes in resultats for gd in variantes]
    for gd in groupes_data:
        gd["niveau"] = niveaux.get(cle_groupe(gd["groupe"]), niveau)

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
