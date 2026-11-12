#!/usr/bin/env python3
"""
gen_rapport.py — Générateur de rapport journalier (recto-verso)

Source : data/journees/journee-YYYY-MM-DD.json

Usage:
  python gen_rapport.py                              # journée du jour
  python gen_rapport.py --date 2026-06-05            # date spécifique
  python gen_rapport.py --journee data/journees/journee-2026-06-05.json
  python gen_rapport.py --output /tmp/out.pdf
  python gen_rapport.py --data rapport.json          # JSON pré-assemblé (override)
"""

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

# ─── Chemins ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
GD_DIR       = DATA_DIR / "Gauche-Droite"
EVENTS_DIR   = DATA_DIR / "Events"
GTFS_DIR     = DATA_DIR / "gtfs" / "gtfs_stm"
JOURNEES_DIR = DATA_DIR / "journees"
OUTPUT_DIR   = DATA_DIR / "rapports"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from chauffeur.effectif import parse_shift_time          # noqa: E402
from chauffeur.evenements import (  # noqa: E402
    applicable_au_quart, raison_exclusion, trier_evenements_par_arrets,
)
from chauffeur.gtfs import stops_for_parcours  # noqa: E402
from chauffeur.journee import groupes_de_service  # noqa: E402
from chauffeur.modeles import FichierGD  # noqa: E402
from chauffeur.presentation_evenements import presenter_evenement  # noqa: E402

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate, Frame, HRFlowable, KeepInFrame, KeepTogether,
        LongTable, NextPageTemplate, PageBreak, PageTemplate, Paragraph,
        Spacer, Table, TableStyle,
    )
except ImportError:
    print("reportlab non installé. Exécute: pip install reportlab --break-system-packages")
    sys.exit(1)

# ─── Palette ────────────────────────────────────────────────────────────
BLUE     = colors.HexColor('#0072CE')
DARK     = colors.HexColor('#1A1A2E')
GREY_BG  = colors.HexColor('#F5F5F5')
RED      = colors.HexColor('#CC0000')
LGREY    = colors.HexColor('#CCCCCC')

# ─── Styles ─────────────────────────────────────────────────────────────────
def _style(name, **kw):
    defaults = dict(fontName='Helvetica', fontSize=8, leading=10,
                    textColor=DARK, spaceAfter=1)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)

S = {
    'title'    : _style('title', fontSize=13, textColor=BLUE, fontName='Helvetica-Bold',
                         alignment=1, spaceAfter=2),
    'subtitle' : _style('subtitle', fontSize=7, textColor=colors.grey, alignment=1, spaceAfter=4),
    'section'  : _style('section', fontSize=8.5, textColor=colors.white,
                         fontName='Helvetica-Bold', backColor=BLUE,
                         leftIndent=4, borderPad=3, spaceAfter=2, spaceBefore=5),
    'subsec'   : _style('subsec', fontSize=8, textColor=BLUE,
                         fontName='Helvetica-Bold', spaceAfter=2, spaceBefore=3),
    'body'     : _style('body'),
    'bold'     : _style('bold', fontName='Helvetica-Bold'),
    'warn'     : _style('warn', textColor=RED, fontName='Helvetica-Bold'),
    'note'     : _style('note', fontSize=6.5, textColor=colors.grey,
                         fontName='Helvetica-Oblique'),
    'hlp'      : _style('hlp', fontSize=7.5, textColor=DARK),
}

# ─── Symboles G-D ───────────────────────────────────────────────────────────
ARROW = {
    'droite'   : '→',
    'gauche'   : '←',
    'via'      : '↑',
    'terminus' : '●',
}

def gd_paragraphs(instructions):
    """Convertit une liste d'instructions G-D en paragraphes."""
    paras = []
    for instr in instructions:
        t = instr.get('type', 'via')
        texte = instr.get('texte', '')
        arret = instr.get('arret', '')
        sym = ARROW.get(t, '↑')

        if t == 'terminus':
            arret_txt = f'  <font size="6" color="grey">#{arret}</font>' if arret else ''
            paras.append(Paragraph(
                f'<b>{sym}  {texte}</b>{arret_txt}',
                _style(f'gd_t_{arret}', fontSize=8, fontName='Helvetica-Bold',
                       textColor=DARK, leading=11, spaceAfter=1)
            ))
        else:
            paras.append(Paragraph(
                f'<font color="#555555">{sym}</font>  {texte}',
                _style(f'gd_{t}_{texte[:10]}', fontSize=7.5, textColor=DARK,
                       leading=10, spaceAfter=1)
            ))
    return paras


def build_gd_column(ligne, direction):
    """Retourne une liste de flowables pour une colonne G-D (une direction)."""
    sens = direction.get('sens', '')
    parc_nom = direction.get('parcours_nom', '')
    instructions = direction.get('instructions', [])
    num = ligne.get('numero', '')
    type_svc = '(école)' if ligne.get('type', '') == 'Scolaire' else ''

    items = []
    items.append(Paragraph(
        f'<b>{num} {type_svc} {sens}</b>',
        _style('col_hdr', fontSize=9, textColor=BLUE, fontName='Helvetica-Bold',
               spaceAfter=1, spaceBefore=2)
    ))
    if parc_nom:
        items.append(Paragraph(parc_nom, S['note']))
    items += gd_paragraphs(instructions)
    return items


def page1_gd(data):
    """Construit les flowables de la page 1 (G-D)."""
    story = []

    # En-tête
    date_str  = data.get('date_travail', '')
    jour_str  = data.get('jour_semaine', '')
    agent     = data.get('agent', {})
    heure_p   = data.get('heure_prise', '')
    lieu_p    = data.get('lieu_prise', '')
    heure_f   = data.get('heure_fin', '')
    voiture   = data.get('voiture', '')

    story.append(Paragraph(
        f'RAPPORT DE JOURNÉE — {jour_str.upper()} {date_str}',
        S['title']
    ))
    story.append(Paragraph(
        f'Garage {agent.get("garage_id","")} – {agent.get("garage","")}  |  Voiture {voiture}  |  '
        f'Prise {lieu_p} {heure_p}  →  Fin {heure_f}',
        S['subtitle']
    ))
    story.append(HRFlowable(width='100%', thickness=2, color=BLUE, spaceAfter=4))

    # Colonnes G-D par ligne
    doc_width = letter[0] - 30*mm   # marges 15mm chaque côté
    lignes = data.get('lignes', [])

    for ligne in lignes:
        directions = ligne.get('directions', [])
        if not directions:
            continue

        num = ligne.get('numero', '')
        nom = ligne.get('nom', '')
        type_svc = ' (école)' if ligne.get('type') == 'Scolaire' else ''
        hdr = Paragraph(f'LIGNE {num}{type_svc} — {nom}', S['section'])

        # Construit une colonne par direction
        cols = [build_gd_column(ligne, d) for d in directions]
        n_cols = len(cols)
        col_w = (doc_width - (n_cols - 1) * 6*mm) / n_cols

        frames = [KeepInFrame(col_w, 0, col, mode='shrink') for col in cols]

        line_gap = 3*mm if n_cols > 1 else 0
        col_widths = []
        for i in range(n_cols):
            col_widths.append(col_w)
            if i < n_cols - 1:
                col_widths.append(line_gap)

        # Intercale des séparateurs vides si besoin
        row = []
        for i, frame in enumerate(frames):
            row.append(frame)
            if i < n_cols - 1:
                row.append(Paragraph('', S['body']))

        t = Table([row], colWidths=col_widths)
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('LINEAFTER', (0, 0), (-2, -1), 0.5, LGREY),
        ]))
        story.append(KeepTogether([hdr, t]))

    return story


def page2_detours(data):
    story = []
    date_str = data.get('date_travail', '')
    jour_str = data.get('jour_semaine', '')
    doc_width = landscape(letter)[0] - 30*mm

    story.append(Paragraph(
        f'DÉTOURS & ARRÊTS MODIFIÉS — {jour_str.upper()} {date_str}',
        S['title']
    ))
    story.append(HRFlowable(width='100%', thickness=2, color=BLUE, spaceAfter=5))

    HDR_STYLE = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [GREY_BG, colors.white]),
        ('GRID',       (0, 0), (-1, -1), 0.3, LGREY),
        ('VALIGN',     (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ])
    COL_W = [36*mm, 31*mm, 73*mm, 80*mm, 29*mm]

    def _paragraph(texte, style=None):
        return Paragraph(escape(str(texte)).replace('\n', '<br/>'), style or S['body'])

    any_applicable = False

    for ligne in data.get('lignes', []):
        num      = ligne.get('numero', '')
        type_svc = ' (école)' if ligne.get('type') == 'Scolaire' else ''
        all_app  = ligne.get('detours_applicables', [])

        dirs_avec = {}
        for ev in all_app:
            dirs_avec.setdefault(ev.get('direction', ''), []).append(ev)

        dirs_order = [d.get('sens', '') for d in ligne.get('directions', [])]
        seen = set()
        for sens in dirs_order + ['']:
            if sens in seen:
                continue
            seen.add(sens)
            evs = dirs_avec.get(sens, [])
            if not evs:
                continue
            ordre_arrets = []
            for direction in ligne.get('directions', []):
                if direction.get('sens', '') == sens:
                    ordre_arrets.extend(direction.get('ordre_arrets', []))
            evs = trier_evenements_par_arrets(evs, ordre_arrets)
            any_applicable = True
            label = f'Direction {sens}' if sens else 'Toutes directions'
            story.append(Paragraph(
                f"LIGNE {num}{type_svc} — {label} — Arrêts modifiés (applicables aujourd'hui)",
                S['section']
            ))
            story.append(Spacer(1, 3))

            rows = [[
                'Évènement / Titre', 'Période', 'Détour & Commentaires',
                'Arrêts', 'Effectif',
            ]]
            for ev in evs:
                affichage = presenter_evenement(ev)

                identite = f'<b>#{escape(affichage.evenement_id)}</b><br/>' \
                           f'{escape(affichage.titre)}'
                if affichage.motif:
                    identite += f'<br/><i>{escape(affichage.motif)}</i>'

                details = []
                if affichage.instructions_gd:
                    instructions = '<br/>'.join(
                        escape(instruction) for instruction in affichage.instructions_gd
                    )
                    details.append(f'<b>G-D :</b><br/>{instructions}')
                if affichage.commentaire:
                    commentaire = escape(affichage.commentaire).replace('\n', '<br/>')
                    details.append(f'<b>Commentaire :</b><br/>{commentaire}')
                detail = '<br/>'.join(details) if details else '—'

                arrets_parts = []
                if affichage.arrets_annules:
                    valeurs = '<br/>'.join(
                        escape(arret.texte) for arret in affichage.arrets_annules
                    )
                    arrets_parts.append(
                        f'<b>Annulés ou concernés :</b><br/>{valeurs}'
                    )
                if affichage.arrets_ajoutes:
                    valeurs = '<br/>'.join(
                        escape(arret.texte) for arret in affichage.arrets_ajoutes
                    )
                    arrets_parts.append(f'<b>Ajoutés :</b><br/>{valeurs}')
                arrets_txt = '<br/>'.join(arrets_parts) if arrets_parts else '—'

                rows.append([
                    Paragraph(identite, S['body']),
                    _paragraph(affichage.periode),
                    Paragraph(detail, S['body']),
                    Paragraph(arrets_txt, S['body']),
                    _paragraph(affichage.effectif),
                ])

            t = LongTable(
                rows,
                colWidths=COL_W,
                repeatRows=1,
                splitByRow=1,
                splitInRow=1,
            )
            t.setStyle(HDR_STYLE)
            story.append(t)
            story.append(Spacer(1, 5))

    if not any_applicable:
        story.append(Paragraph(
            "Aucun détour applicable pour les lignes travaillées aujourd'hui.",
            _style('none', fontSize=8, textColor=colors.grey,
                   fontName='Helvetica-Oblique', spaceAfter=6)
        ))

    non_app_rows = []
    for ligne in data.get('lignes', []):
        num = ligne.get('numero', '')
        for ev in ligne.get('detours_non_applicables', []):
            ev_id    = ev.get('evenement_id', '')
            ev_titre = ev.get('titre', '')
            ev_label = f'{ev_id} — {ev_titre}' if ev_id else ev_titre
            non_app_rows.append([
                Paragraph(f'<b>{num}</b>', S['body']),
                Paragraph(ev.get('direction', ''), S['note']),
                Paragraph(ev_label, S['note']),
                Paragraph(ev.get('raison_exclusion', ''), S['note']),
            ])

    if non_app_rows:
        story.append(Paragraph("Non applicables aujourd'hui", S['subsec']))
        na_hdr = [['Ligne', 'Dir.', 'Évènement', "Raison d'exclusion"]]
        na_t = Table(na_hdr + non_app_rows,
                     colWidths=[14*mm, 14*mm, 52*mm, doc_width - 80*mm])
        na_t.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#888888')),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, -1), 6.5),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1),
             [colors.HexColor('#F8F8F8'), colors.white]),
            ('GRID',          (0, 0), (-1, -1), 0.3, LGREY),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING',   (0, 0), (-1, -1), 4),
            ('TEXTCOLOR',     (0, 1), (-1, -1), colors.grey),
        ]))
        story.append(na_t)

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width='100%', thickness=0.5, color=LGREY, spaceAfter=3))
    story.append(Paragraph(
        'Généré le ' + datetime.now().strftime('%Y-%m-%d à %Hh%M') + ' — Source : employe.stm.info/listeBus',
        _style('footer', fontSize=6, textColor=colors.grey,
               fontName='Helvetica', alignment=1)
    ))

    return story


def generate(data: dict, output_path: str):
    """Point d'entrée principal : génère le PDF."""
    date_str = data.get('date_travail', datetime.now().strftime('%Y-%m-%d'))
    if not output_path:
        output_path = f'rapport-journalier-{date_str}.pdf'

    doc = BaseDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=15*mm,
        rightMargin=15*mm,
        topMargin=12*mm,
        bottomMargin=12*mm,
    )

    portrait_w, portrait_h = letter
    paysage_w, paysage_h = landscape(letter)
    cadre_portrait = Frame(
        15*mm, 12*mm, portrait_w - 30*mm, portrait_h - 24*mm,
        id='cadre_portrait',
    )
    cadre_paysage = Frame(
        15*mm, 12*mm, paysage_w - 30*mm, paysage_h - 24*mm,
        id='cadre_paysage',
    )
    doc.addPageTemplates([
        PageTemplate(id='gd', frames=[cadre_portrait], pagesize=letter),
        PageTemplate(
            id='detours', frames=[cadre_paysage], pagesize=landscape(letter)
        ),
    ])

    story = page1_gd(data)
    story.append(NextPageTemplate('detours'))
    story.append(PageBreak())
    story += page2_detours(data)

    doc.build(story)
    return output_path


# ─── Journée JSON ────────────────────────────────────────────────────────────

JOURS_FR = {
    0: 'Lundi', 1: 'Mardi', 2: 'Mercredi', 3: 'Jeudi',
    4: 'Vendredi', 5: 'Samedi', 6: 'Dimanche',
}


def find_journee(target_date: date) -> Path:
    """Retourne le fichier journée JSON pour la date donnée, ou le plus récent disponible."""
    date_str = target_date.strftime('%Y-%m-%d')
    exact = JOURNEES_DIR / f"journee-{date_str}.json"
    if exact.exists():
        return exact
    candidates = sorted(JOURNEES_DIR.glob("journee-*.json"), reverse=True)
    if candidates:
        print(f"⚠️  Journée du {date_str} introuvable — utilisation de : {candidates[0].name}")
        return candidates[0]
    raise FileNotFoundError(
        f"Aucune journée trouvée dans {JOURNEES_DIR}\n"
        f"  Fichier attendu : journee-{date_str}.json"
    )


def extract_groupes(journee: dict) -> list:
    """
    Retourne les groupes (ligne, direction, id_parcours) en ordre chronologique,
    sans répétition, avec leurs trajets de service (délégué au noyau).
    """
    return groupes_de_service(journee, avec_trips=True)


# ─── Lecture des données G-D ─────────────────────────────────────────────────

def load_gd_direction_by_id(ligne: str, direction: str, id_parcours) -> dict | None:
    """
    Charge une direction G-D depuis son fichier, identifiée par id_parcours.
    Retourne un dict {sens, parcours_nom, instructions} ou None si fichier absent.
    """
    gd_file = GD_DIR / f"gd{ligne}_{direction}.json"
    if not gd_file.exists():
        return None
    try:
        fichier = FichierGD.from_dict(json.loads(gd_file.read_text(encoding='utf-8')))
    except Exception as e:
        print(f"⚠️  Erreur lecture {gd_file.name}: {e}", file=sys.stderr)
        return None

    for route in fichier.routes:
        if not route.parcours:
            continue
        parcours = next((p for p in route.parcours if p.id == id_parcours), route.parcours[0])

        instructions = [{'type': 'terminus', 'texte': parcours.start, 'arret': str(parcours.start_code)}]
        for instr in parcours.direction:
            m = re.match(r'^(Via|Gauche|Droite)\s+-\s+(.+)$', instr, re.IGNORECASE)
            if m:
                instructions.append({'type': m.group(1).lower(), 'texte': m.group(2)})
        instructions.append({'type': 'terminus', 'texte': parcours.end, 'arret': str(parcours.end_code)})

        ordre_arrets = []
        if GTFS_DIR.exists():
            try:
                ordre_arrets = [
                    stop_id for _, stop_id in stops_for_parcours(
                        GTFS_DIR, ligne, route.direction, parcours.id
                    )
                ]
            except (OSError, ValueError, KeyError):
                pass

        return {
            'sens': route.direction,
            'parcours_nom': parcours.name,
            'instructions': instructions,
            'ordre_arrets': ordre_arrets,
        }
    return None


# ─── Filtrage des événements ─────────────────────────────────────────────────

def _shift_range_pour_ligne(time_ranges: list, target_date: date):
    """Plage [début, fin] (datetimes) depuis une liste de {debut, fin} horaires.

    Retourne (None, None) si aucune heure exploitable."""
    if not time_ranges:
        return None, None
    debuts = [parse_shift_time(tr['debut'], target_date) for tr in time_ranges]
    fins   = [parse_shift_time(tr['fin'],   target_date) for tr in time_ranges]
    return min(debuts), max(fins)


def load_events_for_ligne(numero: str, target_date: date,
                          shift_start=None, shift_end=None):
    """
    Charge et filtre les événements d'une ligne (toutes directions).

    Quand shift_start/shift_end sont fournis, délègue à chauffeur.evenements
    (chevauchement de plage, jour de semaine, plage horaire journalière).
    Sans plage de quart, repli sur filtrage par date seulement.
    Retourne (applicables, non_applicables).
    """
    applicables     = []
    non_applicables = []
    par_quart = shift_start is not None and shift_end is not None

    for ev_file in sorted(EVENTS_DIR.glob(f"{numero}_*.json")):
        try:
            data = json.loads(ev_file.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"⚠️  Erreur lecture {ev_file.name}: {e}", file=sys.stderr)
            continue

        direction = data.get('direction', '').capitalize()
        for event in data.get('detours', []):
            ev = dict(event)
            ev['direction'] = direction
            if par_quart:
                ok = applicable_au_quart(event, shift_start, shift_end)
                if ok:
                    applicables.append(ev)
                else:
                    ev['raison_exclusion'] = raison_exclusion(event, shift_start, shift_end)
                    non_applicables.append(ev)
            else:
                debut_str = event.get('date_heure_debut')
                fin_str   = event.get('date_heure_fin')
                ok = True
                if debut_str and datetime.fromisoformat(debut_str).date() > target_date:
                    ok = False
                    ev['raison_exclusion'] = f"Pas encore actif (début {datetime.fromisoformat(debut_str).date()})"
                elif fin_str and datetime.fromisoformat(fin_str).date() < target_date:
                    ok = False
                    ev['raison_exclusion'] = f"Expiré (fin {datetime.fromisoformat(fin_str).date()})"
                if ok:
                    applicables.append(ev)
                else:
                    non_applicables.append(ev)

    return applicables, non_applicables


# ─── Assemblage des données ───────────────────────────────────────────────────

def build_rapport_data(journee: dict, target_date: date) -> dict:
    """Construit le dictionnaire de données complet à partir de la journée JSON."""
    pieces = journee.get('pieces', [])

    heure_prise = pieces[0].get('prise', '')      if pieces else ''
    lieu_prise  = pieces[0].get('lieu_prise', '') if pieces else ''
    heure_fin   = pieces[-1].get('fin', '')       if pieces else ''
    voiture     = pieces[0].get('numero_autobus', '') if pieces else ''

    groupes = extract_groupes(journee)

    lignes_dict  = {}
    dirs_seen    = {}   # {num: set of (direction, id_parcours)}
    trips_by_num = {}   # {num: list of {depart_heure, arrivee_heure}}

    for g in groupes:
        num  = g['ligne']
        dir_ = g['direction']
        id_p = g['id_parcours']

        if num not in lignes_dict:
            lignes_dict[num] = {
                'numero':                  num,
                'nom':                     '',
                'type':                    'Régulier',
                'directions':              [],
                'detours_applicables':     [],
                'detours_non_applicables': [],
            }
            dirs_seen[num]    = set()
            trips_by_num[num] = []

        trips_by_num[num].extend(g['trips'])

        # G-D : une entrée par (direction, id_parcours) unique
        if (dir_, id_p) not in dirs_seen[num]:
            dirs_seen[num].add((dir_, id_p))
            gd_dir = load_gd_direction_by_id(num, dir_, id_p)
            if gd_dir:
                lignes_dict[num]['directions'].append(gd_dir)

    # Événements : une passe par ligne, plage de quart couvrant tous ses trajets
    for num, l in lignes_dict.items():
        time_ranges = [
            {'debut': t['depart_heure'], 'fin': t['arrivee_heure']}
            for t in trips_by_num[num]
            if t.get('depart_heure') and t.get('arrivee_heure')
        ]
        shift_start, shift_end = _shift_range_pour_ligne(time_ranges, target_date)
        app, non_app = load_events_for_ligne(num, target_date, shift_start, shift_end)
        l['detours_applicables']     = app
        l['detours_non_applicables'] = non_app

    return {
        'date_travail': target_date.isoformat(),
        'jour_semaine': JOURS_FR.get(target_date.weekday(), ''),
        'agent': {
            'garage_id': journee.get('garage_id', ''),
            'nom':       '',
            'garage':    journee.get('garage', ''),
        },
        'heure_prise': heure_prise,
        'lieu_prise':  lieu_prise,
        'heure_fin':   heure_fin,
        'voiture':     voiture,
        'lignes':      list(lignes_dict.values()),
    }


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main():
    arg_parser = argparse.ArgumentParser(description='Générateur de rapport journalier')
    arg_parser.add_argument('--date',    default=None,
                            help="Date cible YYYY-MM-DD (défaut : aujourd'hui)")
    arg_parser.add_argument('--journee', default=None,
                            help='Chemin vers journee-YYYY-MM-DD.json (override auto-detect)')
    arg_parser.add_argument('--output',  default=None,
                            help='Chemin du PDF de sortie (défaut: data/rapports/rapport-DATE.pdf)')
    arg_parser.add_argument('--data',    default=None,
                            help='Override: fichier JSON pré-assemblé (bypass journée)')
    args = arg_parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today()

    if args.data:
        data_path = Path(args.data)
        if not data_path.exists():
            print(f'Erreur : fichier introuvable : {data_path}')
            sys.exit(1)
        data = json.loads(data_path.read_text(encoding='utf-8'))
    else:
        try:
            journee_path = Path(args.journee) if args.journee else find_journee(target_date)
            journee = json.loads(journee_path.read_text(encoding='utf-8'))
        except FileNotFoundError as e:
            print(f'Erreur : {e}')
            sys.exit(1)

        # La date canonique vient du fichier journée
        date_from_journee = journee.get('date')
        if date_from_journee:
            target_date = date.fromisoformat(date_from_journee)

        print(f'📄 Journée : {journee_path.name}')
        print(f'   Garage : {journee.get("garage_id", "")} — {journee.get("garage", "")}')
        groupes = extract_groupes(journee)
        if not groupes:
            print('Erreur : aucun trajet de service dans la journée.')
            sys.exit(1)
        lignes_uniques = sorted({g["ligne"] for g in groupes})
        print(f'   Lignes : {", ".join(lignes_uniques)}')
        data = build_rapport_data(journee, target_date)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or str(OUTPUT_DIR / f"rapport-{target_date}.pdf")

    out = generate(data, output_path)
    print(f'✅ Rapport généré : {out}')


if __name__ == '__main__':
    main()
