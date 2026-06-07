#!/usr/bin/env python3
"""
gen_rapport.py — Générateur de rapport journalier STM
Usage: python gen_rapport.py --data rapport_data.json [--output /chemin/sortie.pdf]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

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
        "annulation d'arrêts"            : '\u2717',
        "arrêt déplacé"                  : '!',
        "détour avec annulation d'arrêt" : '\u26a0',
        "détour"                         : '\u26a0',
    }

    def _symbol(titre):
        tl = titre.lower()
        for k, v in TYPE_SYMBOL.items():
            if k in tl:
                return v
        return '\u2022'

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
        type_svc = ' (\u00e9cole)' if ligne.get('type') == 'Scolaire' else ''
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
                f"LIGNE {num}{type_svc} \u2014 {label} \u2014 Arr\u00eats modifi\u00e9s (applicables aujourd'hui)",
                S['section']
            ))
            story.append(Spacer(1, 3))

            rows = [['\u00c9v\u00e8nement / Titre', 'Arr\u00eats', 'D\u00e9tour & Commentaires', 'Effectif']]
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
                ) or '\u2014'
                parts = []
                if gd:
                    parts.append(f'<b>G-D :</b> {gd}')
                if comm:
                    parts.append(comm)
                detail = '<br/>'.join(parts) if parts else '\u2014'

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
            "Aucun d\u00e9tour applicable pour les lignes travaill\u00e9es aujourd'hui.",
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
        na_hdr = [['Ligne', 'Dir.', 'Arr\u00eat(s)', "Raison d'exclusion"]]
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


def main():
    parser = argparse.ArgumentParser(description='Générateur de rapport journalier STM')
    parser.add_argument('--data', required=True, help='Fichier JSON de données (rapport_data.json)')
    parser.add_argument('--output', default=None, help='Chemin du PDF de sortie')
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f'Erreur : fichier introuvable : {data_path}')
        sys.exit(1)

    with open(data_path, encoding='utf-8') as f:
        data = json.load(f)

    out = generate(data, args.output)
    print(f'✅ Rapport généré : {out}')


if __name__ == '__main__':
    main()