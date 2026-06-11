#!/usr/bin/env python3
"""
gen_rapport.py — Générateur de rapport journalier STM (autonome)

Usage:
  python gen_rapport.py                         # carte agent du jour
  python gen_rapport.py --date 2026-06-05       # date spécifique
  python gen_rapport.py --output /tmp/out.pdf   # chemin de sortie custom
  python gen_rapport.py --data rapport.json     # JSON pré-assemblé (override)
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

# ─── Chemins ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
GD_DIR       = DATA_DIR / "Gauche-Droite"
EVENTS_DIR   = DATA_DIR / "Events"
DOCS_DIR     = DATA_DIR / "ca"
OUTPUT_DIR   = DATA_DIR / "rapports"

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable, KeepInFrame, KeepTogether, PageBreak, Paragraph,
        SimpleDocTemplate, Spacer, Table, TableStyle,
    )
except ImportError:
    print("reportlab non installé. Exécute: pip install reportlab --break-system-packages")
    sys.exit(1)

# ─── Palette STM ────────────────────────────────────────────────────────────
BLUE     = colors.HexColor('#0072CE')
DARK     = colors.HexColor('#1A1A2E')
GREY_BG  = colors.HexColor('#F5F5F5')
RED      = colors.HexColor('#CC0000')
ORANGE   = colors.HexColor('#E87722')
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
    """Construit les flowables de la page 1 (G-D + HLP)."""
    story = []

    # En-tête
    date_str  = data.get('date_travail', '')
    jour_str  = data.get('jour_semaine', '')
    agent     = data.get('agent', {})
    heure_p   = data.get('heure_prise', '')
    lieu_p    = data.get('lieu_prise', '')
    heure_f   = data.get('heure_fin', '')
    voiture   = data.get('voiture', '')
    assignation = agent.get('assignation', '')

    story.append(Paragraph(
        f'RAPPORT DE JOURNÉE — {jour_str.upper()} {date_str}',
        S['title']
    ))
    story.append(Paragraph(
        f'Agent {assignation} – {agent.get("nom","")}  |  Voiture {voiture}  |  '
        f'Prise {lieu_p} {heure_p}  →  Fin {heure_f}  |  Garage {agent.get("garage","")}',
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

    # HLP
    hlp_list = data.get('hlp', [])
    if hlp_list:
        story.append(HRFlowable(width='100%', thickness=1, color=LGREY,
                                spaceAfter=3, spaceBefore=4))
        story.append(Paragraph('HLP', S['subsec']))
        hlp_rows = []
        for h in hlp_list:
            hlp_rows.append([
                Paragraph(f'<b>{h.get("id","")}</b>', S['body']),
                Paragraph(h.get('instructions', ''), S['hlp']),
            ])
        ht = Table(hlp_rows, colWidths=[14*mm, doc_width - 14*mm])
        ht.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(ht)

    return story


def page2_detours(data):
    story = []
    date_str = data.get('date_travail', '')
    jour_str = data.get('jour_semaine', '')
    doc_width = letter[0] - 30*mm

    story.append(Paragraph(
        f'DÉTOURS & ARRÊTS MODIFIÉS — {jour_str.upper()} {date_str}',
        S['title']
    ))
    story.append(HRFlowable(width='100%', thickness=2, color=BLUE, spaceAfter=5))

    TYPE_SYMBOL = {
        "annulation d'arrêts"            : '✗',
        "arrêt déplacé"                  : '!',
        "détour avec annulation d'arrêt" : '⚠',
        "détour"                         : '⚠',
    }

    def _symbol(titre):
        tl = titre.lower()
        for k, v in TYPE_SYMBOL.items():
            if k in tl:
                return v
        return '•'

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
    ])
    COL_W = [38*mm, 52*mm, 72*mm, 22*mm]

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
            any_applicable = True
            label = f'Direction {sens}' if sens else 'Toutes directions'
            story.append(Paragraph(
                f"LIGNE {num}{type_svc} — {label} — Arrêts modifiés (applicables aujourd'hui)",
                S['section']
            ))
            story.append(Spacer(1, 3))

            rows = [['Évènement / Titre', 'Arrêts', 'Détour & Commentaires', 'Effectif']]
            for ev in evs:
                ev_id    = ev.get('evenement_id', '')
                titre    = ev.get('titre', '')
                motif    = ev.get('motif', '')
                sym      = _symbol(titre)
                arrets   = ev.get('arrets_annules', [])
                gd       = ev.get('description_gd') or ''
                comm     = ev.get('commentaire') or ''
                effectif = ev.get('effectif', '')

                ev_text = (f'<b>#{ev_id}</b><br/>{titre}<br/><i>{motif}</i>'
                           if ev_id else f'{titre}<br/><i>{motif}</i>')
                arrets_txt = '<br/>'.join(
                    f'{sym} {a.get("id", "")} {a.get("nom", "")}'
                    for a in arrets
                ) or '—'
                parts = []
                if gd:
                    parts.append(f'<b>G-D :</b> {gd}')
                if comm:
                    parts.append(comm)
                detail = '<br/>'.join(parts) if parts else '—'

                rows.append([
                    Paragraph(ev_text,    S['body']),
                    Paragraph(arrets_txt, S['body']),
                    Paragraph(detail,     S['body']),
                    Paragraph(effectif,   S['body']),
                ])

            t = Table(rows, colWidths=COL_W)
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
            arrets = ev.get('arrets_annules', [])
            arrets_text = ', '.join(
                f'{a.get("id", "")} {a.get("nom", "")}' for a in arrets
            ) if arrets else ev.get('nom_arret', '')
            non_app_rows.append([
                Paragraph(f'<b>{num}</b>', S['body']),
                Paragraph(ev.get('direction', ''), S['note']),
                Paragraph(arrets_text, S['note']),
                Paragraph(ev.get('raison_exclusion', ''), S['note']),
            ])

    if non_app_rows:
        story.append(Paragraph("Non applicables aujourd'hui", S['subsec']))
        na_hdr = [['Ligne', 'Dir.', 'Arrêt(s)', "Raison d'exclusion"]]
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

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=15*mm,
        rightMargin=15*mm,
        topMargin=12*mm,
        bottomMargin=12*mm,
    )

    story = page1_gd(data)
    story.append(PageBreak())
    story += page2_detours(data)

    doc.build(story)
    return output_path


# ─── Lecture carte agent PDF ─────────────────────────────────────────────────

JOURS_FR = {
    0: 'Lundi', 1: 'Mardi', 2: 'Mercredi', 3: 'Jeudi',
    4: 'Vendredi', 5: 'Samedi', 6: 'Dimanche',
}


def find_carte_agent(target_date: date) -> Path:
    """Retourne la carte agent PDF pour la date donnée, ou la plus récente disponible."""
    date_str = target_date.strftime('%Y-%m-%d')
    exact = DOCS_DIR / f"carte-agent-{date_str}.pdf"
    if exact.exists():
        return exact
    # Fallback : carte la plus récente (exclut les versions surlignées)
    candidates = sorted(
        (p for p in DOCS_DIR.glob("carte-agent-*.pdf") if 'surligné' not in p.name),
        reverse=True
    )
    if candidates:
        print(f"⚠️  Carte agent du {date_str} introuvable — utilisation de : {candidates[0].name}")
        return candidates[0]
    raise FileNotFoundError(
        f"Aucune carte agent trouvée dans {DOCS_DIR}\n"
        f"  Fichier attendu : carte-agent-{date_str}.pdf"
    )


def parse_carte_agent(pdf_path: Path) -> dict:
    """Extrait les données structurées de la carte agent HASTUS (PDF)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF non installé. Exécute: pip install pymupdf --break-system-packages")
        sys.exit(1)

    doc = fitz.open(str(pdf_path))
    page1_text = doc[0].get_text() if len(doc) > 0 else ''
    page2_text = doc[1].get_text() if len(doc) > 1 else ''
    doc.close()

    result = {
        'assignation': '',
        'date': None,
        'voiture': '',
        'heure_debut': '',
        'lieu_debut': '',
        'heure_fin': '',
        'garage': '',
        'lignes': [],
        'hlp': [],
    }

    # Assignation : premier nombre ≥ 3 chiffres en début de ligne
    m = re.search(r'^(\d{3,4})\s', page1_text, re.MULTILINE)
    if m:
        result['assignation'] = m.group(1)

    # Date : format dd/mm/yyyy
    m = re.search(r'(\d{2})/(\d{2})/(\d{4})', page1_text)
    if m:
        result['date'] = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # Ligne du tableau shift — fitz mélange les colonnes, ex :
    # "V036 5622:28 22:28 29:38 29:48 12 - 04"
    # Voiture : dernier motif "NN - NN" de la ligne contenant les heures
    shift_line_m = re.search(r'[A-Z]\w+\s+\d+\d{2}:\d{2}.+?(\d+\s*-\s*\d+)\s*$',
                             page1_text, re.MULTILINE)
    if shift_line_m:
        result['voiture'] = shift_line_m.group(1).replace(' ', '')

    # Lieu début : code alphanumérique avant les heures fusionnées (ex: V036)
    lieu_m = re.search(r'([A-Z]\d+)\s+\d+\d{2}:\d{2}', page1_text)
    if lieu_m:
        result['lieu_debut'] = lieu_m.group(1)

    # Heures : extraire les HH:MM non précédés d'un chiffre (évite "5622:28")
    shift_line_text = shift_line_m.group(0) if shift_line_m else ''
    times = re.findall(r'(?<!\d)(\d{2}:\d{2})', shift_line_text)
    if len(times) >= 2:
        result['heure_debut'] = times[0]
        result['heure_fin']   = times[1]

    # Lignes travaillées : "12 - P / - / Régulier", "125 / - / Régulier" ou
    # "a12 - P / ..." (note ref). Le " - P" (rampe avant) est OPTIONNEL : certaines
    # lignes n'ont pas cette désignation et seraient sinon absentes du rapport.
    # Ancré en début de ligne (^) pour ne pas capturer "hlp1/hlp2" comme "1"/"2".
    seen = []
    for m in re.finditer(r'^[a-z]?(\d+)(?:\s+-\s+\w+)?\s+/', page1_text, re.MULTILINE):
        num = m.group(1)
        if num not in seen:
            seen.append(num)
    result['lignes'] = seen

    # Segments départ/arrivée par ligne (pour filtrage des parcours G-D)
    result['segments'] = extract_segments_from_carte(page1_text)

    # Garage : "GARAGE LASALLE" → "LaSalle"
    m = re.search(r'GARAGE\s+(\S+)', page1_text, re.IGNORECASE)
    if m:
        result['garage'] = m.group(1).capitalize()

    # HLP depuis page 2
    # Format: "hlp1: 61564 - [V] de l'Église, ... - 54112"
    # ou:     "hlp3: 60238 - [V] Tupper, ..."  (sans code de fin)
    for m in re.finditer(
        r'(hlp\d+):\s+\d+\s+-\s+(.+?)(?:\s+-\s+\d+)?$',
        page2_text, re.MULTILINE | re.IGNORECASE
    ):
        raw = m.group(2).strip()
        # Convertir [V]/[G]/[D] en abréviations lisibles
        instructions = re.sub(r'\[V\]', 'Via', raw)
        instructions = re.sub(r'\[G\]', 'Gauche', instructions)
        instructions = re.sub(r'\[D\]', 'Droite', instructions)
        result['hlp'].append({
            'id': m.group(1),
            'instructions': instructions,
        })

    return result


# ─── Extraction des segments de la carte agent ───────────────────────────────

def extract_segments_from_carte(page1_text: str) -> dict:
    """
    Extrait les paires (départ, arrivée) par ligne depuis le texte de la carte agent.
    Retourne: { '195': [('STATION ANGRIGNON', 'TERMINUS DORVAL'), ...], ... }

    Format PyMuPDF (fitz) : chaque heure est sur sa propre ligne, sauf quand
    le nom d'arrêt est trop long — l'heure est alors collée à la fin.
    """
    _pure_time = re.compile(r'^\d{1,2}:\d{2}$')
    _end_time  = re.compile(r'^(.+?)\s*(\d{2}:\d{2})$')

    segments: dict = {}
    # " - P" optionnel (cf. parse_carte_agent) ; re.match ancre déjà au début du
    # bloc, donc "hlp1/hlp2" ne matchent pas (pas de chiffre en tête après [a-z]?).
    blocks = re.split(r'\n(?=[a-z]?\d+(?:\s+-\s+\w+)?\s+/|hlp\d|GARAGE)', page1_text)

    for block in blocks:
        m_ligne = re.match(r'[a-z]?(\d+)(?:\s+-\s+\w+)?\s+/', block)
        if not m_ligne:
            continue
        numero = m_ligne.group(1)

        lines = [l.strip() for l in block.split('\n') if l.strip()]

        # Classe chaque ligne en (time, stop, stop_time)
        items: list[dict] = []
        for line in lines[1:]:
            if _pure_time.match(line):
                items.append({'type': 'time', 'stop': None})
            else:
                m = _end_time.match(line)
                if m:
                    items.append({'type': 'stop_time', 'stop': m.group(1).strip()})
                else:
                    items.append({'type': 'stop', 'stop': line})

        # Temps indexés dans l'ordre d'apparition
        timed = [i for i, it in enumerate(items) if it['type'] in ('time', 'stop_time')]
        if len(timed) < 2:
            continue

        # Stop de départ : premier item stop après le premier temps
        debut_stop = None
        for j in range(timed[0] + 1, len(items)):
            if items[j]['stop'] and len(items[j]['stop']) > 2:
                debut_stop = items[j]['stop']
                break
        if items[timed[0]]['type'] == 'stop_time':
            debut_stop = items[timed[0]]['stop']

        # Stop d'arrivée : dernier item stop avant/dans le dernier temps
        fin_stop = None
        last_i = timed[-1]
        if items[last_i]['type'] == 'stop_time':
            fin_stop = items[last_i]['stop']
        else:
            for j in range(last_i - 1, -1, -1):
                if items[j]['stop'] and len(items[j]['stop']) > 2:
                    fin_stop = items[j]['stop']
                    break

        if debut_stop and fin_stop:
            segments.setdefault(numero, []).append((debut_stop, fin_stop))

    return segments


# Jetons trop communs pour distinguer un terminus (articles, génériques, indicateurs
# de quai/direction). Ignorés lors de l'appariement. (Aligné sur app/dashboard.py.)
_STOP_NOISE = {
    "DE", "DU", "DES", "LA", "LE", "LES", "AU", "AUX", "ET", "A",
    "NO", "DIR", "STATION", "REM", "TERMINUS", "GARAGE",
    "NORD", "SUD", "EST", "OUEST",
}

_ABBREV = {"STE": "SAINTE", "ST": "SAINT", "PRES": "PRESIDENT"}


def _stop_tokens(name: str) -> set:
    """
    Réduit un nom d'arrêt à un ensemble de jetons distinctifs pour l'appariement.

    Conserve le contenu des parenthèses : la carte agent y trouve souvent le nom de
    rue que le fichier G-D met entre parenthèses, ex. « Station McGill (De Maisonneuve
    / Robert-Bourassa) » ↔ « DE MAISONNEUVE / ROBERT-BOURASSA ». Retire accents,
    articles/génériques, et jetons trop courts ou purement numériques. Robuste aux
    noms tronqués par la mise en page du PDF (« STATION VIAU(P.-DE-COUBERTIN O./TH »).
    """
    n = unicodedata.normalize("NFKD", name.upper())
    n = "".join(c for c in n if not unicodedata.combining(c))
    tokens = set()
    for raw in re.split(r"[^A-Z0-9]+", n):
        if not raw:
            continue
        tok = _ABBREV.get(raw, raw)
        if len(tok) < 2 or tok.isdigit() or tok in _STOP_NOISE:
            continue
        tokens.add(tok)
    return tokens


def _stops_match(a: str, b: str) -> bool:
    """Deux noms d'arrêt désignent-ils le même lieu (≥ 1 jeton distinctif commun) ?"""
    ta, tb = _stop_tokens(a), _stop_tokens(b)
    return bool(ta and tb and (ta & tb))


def parcours_matches_segments(parcours: dict, segments: list) -> bool:
    """
    Vérifie si un parcours G-D correspond à au moins un segment de la carte agent.
    Appariement par jetons distinctifs (cf. _stop_tokens) — insensible à la casse,
    aux accents, et capable de relier un nom de station à son nom de rue (parenthèses).
    """
    gd_start = parcours.get('start', '')
    gd_end   = parcours.get('end', '')

    for (dep, arr) in segments:
        if _stops_match(gd_start, dep) and _stops_match(gd_end, arr):
            return True
    return False


# ─── Lecture des données G-D ─────────────────────────────────────────────────

def load_gd_directions(numero: str, segments: list) -> list:
    """
    Charge les directions G-D d'une ligne filtrées selon les segments de la carte agent.
    segments : liste de (départ, arrivée) issus de extract_segments_from_carte().
    Retourne une liste de directions au format attendu par page1_gd().
    """
    directions = []
    for gd_file in sorted(GD_DIR.glob(f"gd{numero}_*.json")):
        try:
            data = json.loads(gd_file.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"⚠️  Erreur lecture {gd_file.name}: {e}", file=sys.stderr)
            continue

        for route in data.get('routes', []):
            sens = route.get('direction', '')
            for parcours in route.get('parcours', []):
                # Filtrer : ne garder que les parcours présents dans la carte agent
                if segments and not parcours_matches_segments(parcours, segments):
                    continue

                instructions = []

                # Terminus de départ
                instructions.append({
                    'type': 'terminus',
                    'texte': parcours.get('start', ''),
                    'arret': str(parcours.get('start_code', '')),
                })

                # Instructions virage-par-virage
                for instr in parcours.get('direction', []):
                    m = re.match(r'^(Via|Gauche|Droite)\s+-\s+(.+)$', instr, re.IGNORECASE)
                    if m:
                        instructions.append({
                            'type': m.group(1).lower(),
                            'texte': m.group(2),
                        })

                # Terminus d'arrivée
                instructions.append({
                    'type': 'terminus',
                    'texte': parcours.get('end', ''),
                    'arret': str(parcours.get('end_code', '')),
                })

                directions.append({
                    'sens': sens,
                    'parcours_nom': parcours.get('name', ''),
                    'instructions': instructions,
                })

    return directions


# ─── Filtrage des événements ─────────────────────────────────────────────────

# Mapping mots-clés effectif → jours de la semaine (0=lundi … 6=dimanche)
EFFECTIF_JOURS = {
    'lundi':          [0],
    'mardi':          [1],
    'mercredi':       [2],
    'jeudi':          [3],
    'vendredi':       [4],
    'samedi':         [5],
    'dimanche':       [6],
    'en semaine':     [0, 1, 2, 3, 4],
    'fin de semaine': [5, 6],
}


def is_event_applicable(event: dict, target_date: date):
    """
    Détermine si un événement est applicable à la date cible.
    Retourne (True, '') ou (False, raison_exclusion).
    """
    debut_str = event.get('date_heure_debut')
    fin_str   = event.get('date_heure_fin')

    if debut_str:
        debut = datetime.fromisoformat(debut_str).date()
        if target_date < debut:
            return False, f"Pas encore actif (début {debut})"

    if fin_str:
        fin = datetime.fromisoformat(fin_str).date()
        if target_date > fin:
            return False, f"Expiré (fin {fin})"

    # Filtre jour de semaine selon effectif
    effectif = (event.get('effectif') or '').lower().strip()
    if effectif not in ('en tout temps', ''):
        dow = target_date.weekday()
        for key, jours in EFFECTIF_JOURS.items():
            if key in effectif:
                if dow not in jours:
                    return False, f"Effectif : {event.get('effectif')}"
                break

    return True, ''


def load_events_for_ligne(numero: str, target_date: date):
    """
    Charge et filtre les événements d'une ligne.
    Retourne (applicables, non_applicables).
    """
    applicables     = []
    non_applicables = []

    for ev_file in sorted(EVENTS_DIR.glob(f"{numero}_*.json")):
        try:
            data = json.loads(ev_file.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"⚠️  Erreur lecture {ev_file.name}: {e}", file=sys.stderr)
            continue

        direction = data.get('direction', '').capitalize()  # 'est' → 'Est'
        for event in data.get('detours', []):
            ok, raison = is_event_applicable(event, target_date)
            ev = dict(event)
            ev['direction'] = direction
            if ok:
                applicables.append(ev)
            else:
                ev['raison_exclusion'] = raison
                non_applicables.append(ev)

    return applicables, non_applicables


# ─── Assemblage des données ───────────────────────────────────────────────────

def build_rapport_data(carte: dict, target_date: date) -> dict:
    """Construit le dictionnaire de données complet à partir de la carte agent."""
    jour_str = JOURS_FR.get(target_date.weekday(), '')

    all_segments = carte.get('segments', {})
    lignes = []
    for numero in carte['lignes']:
        segments = all_segments.get(numero, [])
        directions = load_gd_directions(numero, segments)
        app, non_app = load_events_for_ligne(numero, target_date)
        lignes.append({
            'numero':                 numero,
            'nom':                    '',
            'type':                   'Régulier',
            'directions':             directions,
            'detours_applicables':    app,
            'detours_non_applicables': non_app,
        })

    return {
        'date_travail': target_date.isoformat(),
        'jour_semaine': jour_str,
        'agent': {
            'assignation': carte['assignation'],
            'nom':         '',
            'garage':      carte['garage'],
        },
        'heure_prise': carte['heure_debut'],
        'lieu_prise':  carte['lieu_debut'],
        'heure_fin':   carte['heure_fin'],
        'voiture':     carte['voiture'],
        'lignes':      lignes,
        'hlp':         carte['hlp'],
    }


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main():
    arg_parser = argparse.ArgumentParser(description='Générateur de rapport journalier STM')
    arg_parser.add_argument('--date',   default=None,
                            help='Date cible YYYY-MM-DD (défaut: aujourd\'hui)')
    arg_parser.add_argument('--output', default=None,
                            help='Chemin du PDF de sortie (défaut: data/rapports/rapport-DATE.pdf)')
    arg_parser.add_argument('--data',   default=None,
                            help='Override: fichier JSON pré-assemblé (bypass carte agent)')
    args = arg_parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today()

    if args.data:
        # Mode override : JSON fourni manuellement
        data_path = Path(args.data)
        if not data_path.exists():
            print(f'Erreur : fichier introuvable : {data_path}')
            sys.exit(1)
        data = json.loads(data_path.read_text(encoding='utf-8'))
    else:
        # Mode autonome : lecture de la carte agent PDF
        try:
            pdf_path = find_carte_agent(target_date)
            print(f'📄 Carte agent : {pdf_path.name}')
            carte = parse_carte_agent(pdf_path)
            if not carte['lignes']:
                print('Erreur : aucune ligne trouvée dans la carte agent.')
                sys.exit(1)
            print(f'   Assignation : {carte["assignation"]} | Voiture : {carte["voiture"]}')
            print(f'   Lignes : {", ".join(carte["lignes"])}')
            data = build_rapport_data(carte, target_date)
        except FileNotFoundError as e:
            print(f'Erreur : {e}')
            sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or str(OUTPUT_DIR / f"rapport-{target_date}.pdf")

    out = generate(data, output_path)
    print(f'✅ Rapport généré : {out}')


if __name__ == '__main__':
    main()
