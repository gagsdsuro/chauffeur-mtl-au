#!/usr/bin/env python3
"""
carte_agent.py — Annotation autonome de la carte agent (version CLI)

Prend un PDF de carte agent déjà téléchargé et produit une version annotée :
  • Heures de prise (début / fin) et marqueurs de ligne précédente/suivante
    « (XXX) »                        surlignés en JAUNE
  • Numéro de ligne de chaque segment (« XX - P » rampe avant et
    « XX / - / Régulier »)           surligné en BLEU
  • Départ précédent (GTFS) annoté en ROUGE au-dessus de l'heure de départ,
    au premier segment de chaque pièce de travail et à chaque changement
    de ligne à l'intérieur d'une pièce

Les horaires terminus proviennent des données GTFS statiques du transporteur (données ouvertes), lues
localement — aucun appel réseau, aucun navigateur, aucune API Google.

Cette version regroupe en un seul fichier la logique qui était auparavant
répartie entre le skill « carte-agent » (extraction PDF), get_terminus_times.py
(horaires GTFS) et process_pdf.py (annotation).

------------------------------------------------------------------------------
Dépendance :  pip install pymupdf
------------------------------------------------------------------------------

Exemples
--------
    # Cas le plus simple : la date est lue dans le nom du fichier,
    # le GTFS est cherché dans $STM_GTFS_DIR puis ./gtfs_stm
    python3 carte_agent.py --pdf ~/carte-agent-2026-06-03.pdf

    # Tout préciser explicitement
    python3 carte_agent.py \
        --pdf   ~/cartes/carte-agent-2026-06-03.pdf \
        --out   ~/cartes/carte-2026-06-03-annotee.pdf \
        --gtfs  ~/data/gtfs_stm \
        --date  2026-06-03

    # Sans GTFS : surlignage jaune + bleu seulement (pas d'annotation rouge)
    python3 carte_agent.py --pdf carte.pdf --no-gtfs
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import pymupdf  # PyMuPDF
except ImportError:
    sys.exit("ERREUR : PyMuPDF manquant.  Installe-le avec :  pip install pymupdf")

# --------------------------------------------------------------------------- #
# Couleurs et constantes de mise en page (PDF carte agent)
# --------------------------------------------------------------------------- #
JAUNE = (1, 1, 0)
BLEU  = (0.4, 0.7, 1.0)
ROUGE = (0.8, 0.1, 0.1)

PAGE_MID = 200          # frontière colonne gauche / droite du PDF
BODY_Y   = 125          # sous cette ordonnée commence le corps (segments)
TIME_RE  = re.compile(r'^\d{1,2}:\d{2}$')
LINE_RE  = re.compile(r'^(\d+)\s*(?:-\s*P\b|\s+/)')
MARKER_RE = re.compile(r'^\(\d+\)$')   # ligne précédente / suivante : « (168) »


def log(msg: str) -> None:
    print(f"[INFO] {msg}", file=sys.stderr)


# ===========================================================================
#  1.  Lecture des spans du PDF
# ===========================================================================
def get_spans(page) -> list:
    """Retourne tous les spans non vides : [{'text', 'bbox'}, ...]."""
    spans = []
    for block in page.get_text('dict')['blocks']:
        if block['type'] == 0:
            for line in block['lines']:
                for span in line['spans']:
                    t = span['text'].strip()
                    if t:
                        spans.append({'text': t, 'bbox': span['bbox']})
    return spans


def to_min(t: str) -> int:
    """'25:47' -> 1547 minutes.  Supporte les heures > 24 h."""
    h, m = map(int, t.split(':'))
    return h * 60 + m


# ===========================================================================
#  2.  Extraction des métadonnées (numéro de carte, prise début / fin, lignes)
# ===========================================================================
def extract_meta(spans: list) -> dict:
    """
    Lit dans l'en-tête du PDF :
      • carte  : numéro de la carte agent (1 à 9999, y < 130)
      • debut  : min de la colonne « Prise » gauche
      • fin    : max de la colonne « Prise » droite
      • lignes : liste ordonnée des numéros de ligne ("XX - P")
    """
    # --- colonnes « Prise » triées par X (gauche = début, droite = fin) ------
    prise_cols = []
    for s in spans:
        if s['text'] == 'Prise':
            x0, _, x1, _ = s['bbox']
            prise_cols.append({'x0': x0, 'range': (x0 - 4, x1 + 4), 'times': []})
    prise_cols.sort(key=lambda c: c['x0'])

    for col in prise_cols:
        px0, px1 = col['range']
        for s in spans:
            bx0, by0, bx1, _ = s['bbox']
            if px0 <= bx0 and bx1 <= px1 and 92 < by0 < 125 and TIME_RE.match(s['text']):
                col['times'].append(s['text'])

    debut_times = prise_cols[0]['times'] if prise_cols else []
    fin_times   = prise_cols[1]['times'] if len(prise_cols) > 1 else []
    heure_debut = min(debut_times, key=to_min) if debut_times else None
    heure_fin   = max(fin_times,   key=to_min) if fin_times   else None

    # --- numéro de carte : 1er span numérique de 1 à 9999, y<130 ------------
    carte_num = "?"
    for s in spans:
        if s['bbox'][1] < 130 and re.fullmatch(r'[1-9][0-9]{0,3}', s['text']):
            carte_num = s['text']
            break

    # --- numéros de ligne uniques, dans l'ordre d'apparition ------------------
    lignes = []
    for s in spans:
        m = LINE_RE.match(s['text'])
        if m and m.group(1) not in lignes:
            lignes.append(m.group(1))

    return {"carte": carte_num, "debut": heure_debut,
            "fin": heure_fin, "lignes": lignes}


_DATE_LIGNE_RE  = re.compile(r'^\d{2}/\d{2}/\d{4}$')
_JOUR_TYPE_RE   = re.compile(r'^(Semaine|Samedi|Dimanche)\s*-\s*(\S+)$')
_EN_VIGUEUR_RE  = re.compile(r'En vigueur:\s*(\d{2})/(\d{2})/(\d{4})')


def extract_jour_type(page1_text: str) -> dict:
    """Champ optionnel imprimé sur certaines cartes : jour-type + date de mise en
    vigueur (ex. « Samedi - BASE » juste après la date de la carte, « En vigueur:
    15/06/2026 » en en-tête). Absent sur d'autres cartes (raison non confirmée à ce
    jour — cf. mémoire projet). Sert uniquement de validation croisée à
    chauffeur.periodes.identite_ca() — jamais de source d'identité, pour que
    toutes les cartes (avec ou sans ce champ) suivent la même règle de dérivation.

    Retour : {"jour_type_imprime": "samedi"|"dimanche"|"semaine"|None,
              "variante": "BASE"|"REM"|... |None, "en_vigueur": "YYYY-MM-DD"|None}
    """
    en_vigueur = None
    m = _EN_VIGUEUR_RE.search(page1_text)
    if m:
        j, mo, a = m.groups()
        en_vigueur = f"{a}-{mo}-{j}"

    jour_type, variante = None, None
    lignes = page1_text.split("\n")
    for i, ligne in enumerate(lignes):
        if _DATE_LIGNE_RE.match(ligne) and i + 1 < len(lignes):
            mj = _JOUR_TYPE_RE.match(lignes[i + 1])
            if mj:
                jour_type = mj.group(1).lower()
                variante  = mj.group(2)
            break

    return {"jour_type_imprime": jour_type, "variante": variante, "en_vigueur": en_vigueur}


# ===========================================================================
#  3.  Horaires terminus depuis le GTFS statique
# ===========================================================================
def get_active_services(gtfs_dir: Path, date_str: str) -> set:
    """service_id actifs pour la date (calendar.txt + calendar_dates.txt)."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    day_field = ["monday", "tuesday", "wednesday", "thursday",
                 "friday", "saturday", "sunday"][date.weekday()]
    date_int = int(date_str.replace("-", ""))
    active = set()

    cal = gtfs_dir / "calendar.txt"
    if cal.exists():
        with open(cal, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get(day_field) != "1":
                    continue
                if int(row["start_date"]) <= date_int <= int(row["end_date"]):
                    active.add(row["service_id"])

    cdates = gtfs_dir / "calendar_dates.txt"
    if cdates.exists():
        with open(cdates, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if int(row["date"]) == date_int:
                    if row["exception_type"] == "1":
                        active.add(row["service_id"])
                    elif row["exception_type"] == "2":
                        active.discard(row["service_id"])

    log(f"Services actifs pour {date_str} ({day_field}) : {len(active)}")
    return active


def fmt_time(gtfs_time: str) -> str:
    """'25:30:00' -> '25:30'  (les heures > 24 h sont conservées)."""
    p = gtfs_time.split(":")
    return f"{p[0]}:{p[1]}"


def get_terminus_times(gtfs_dir: Path, lignes: list, date_str: str) -> dict:
    """
    Pour chaque ligne, heures de départ du 1er arrêt (stop_sequence min)
    par direction (0 et 1), pour les services actifs à cette date.

    Retour : {"136": {"a": [...], "b": [...], "stop_a": "...", "stop_b": "..."}}
    """
    active = get_active_services(gtfs_dir, date_str)

    log("Chargement stops.txt...")
    stops = {}
    with open(gtfs_dir / "stops.txt", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stops[row["stop_id"]] = row["stop_name"]

    log("Chargement trips.txt...")
    ligne_trips = {ln: {0: [], 1: []} for ln in lignes}
    needed = set()
    with open(gtfs_dir / "trips.txt", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["route_id"] not in lignes:
                continue
            if row["service_id"] not in active:
                continue
            d = int(row.get("direction_id", "0"))
            if d not in (0, 1):
                continue
            ligne_trips[row["route_id"]][d].append(row["trip_id"])
            needed.add(row["trip_id"])

    log(f"Trips pertinents : {len(needed)}")
    if not needed:
        log("Aucun trip actif pour les lignes demandées à cette date.")
        return {}

    log("Scan stop_times.txt (premier arrêt de chaque trip)...")
    trip_first = {}
    with open(gtfs_dir / "stop_times.txt", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["trip_id"]
            if tid not in needed:
                continue
            seq = int(row["stop_sequence"])
            if tid not in trip_first or seq < trip_first[tid]["seq"]:
                trip_first[tid] = {"seq": seq,
                                   "stop_id": row["stop_id"],
                                   "departure_time": row["departure_time"]}

    log(f"Premiers arrêts trouvés : {len(trip_first)} trips")

    result = {}
    for ln in lignes:
        def collect(d):
            times, votes = [], {}
            for tid in ligne_trips[ln][d]:
                info = trip_first.get(tid)
                if not info:
                    continue
                times.append(fmt_time(info["departure_time"]))
                votes[info["stop_id"]] = votes.get(info["stop_id"], 0) + 1
            times = sorted(set(times))
            top = max(votes, key=votes.get) if votes else ""
            return times, stops.get(top, top)

        ta, sa = collect(0)
        tb, sb = collect(1)
        if not ta and not tb:
            log(f"  Ligne {ln}: aucun horaire actif pour {date_str}")
            continue
        result[ln] = {"a": ta, "b": tb, "stop_a": sa, "stop_b": sb}
        log(f"  Ligne {ln}: {len(ta)} dir0 ({sa[:30]}) | {len(tb)} dir1 ({sb[:30]})")

    return result


# ===========================================================================
#  4.  Annotation du PDF
# ===========================================================================
def prev_dep(times: list, target: str):
    """Dernier départ strictement avant l'heure cible."""
    tmin = to_min(target)
    before = [t for t in times if to_min(t) < tmin]
    return before[-1] if before else None


def highlight_prise(page, spans) -> None:
    """Surligne en jaune les valeurs des colonnes Prise début / Prise fin."""
    ranges = []
    for s in spans:
        if s['text'] == 'Prise':
            x0, _, x1, _ = s['bbox']
            ranges.append((x0 - 4, x1 + 4))
    for (px0, px1) in ranges:
        for s in spans:
            bx0, by0, bx1, _ = s['bbox']
            if px0 <= bx0 and bx1 <= px1 and 92 < by0 < 120:
                page.draw_rect(pymupdf.Rect(bx0 - 2, by0 - 2, bx1 + 2, by1_safe(s) + 2),
                               color=None, fill=JAUNE, fill_opacity=0.4, overlay=False)


def by1_safe(s) -> float:
    return s['bbox'][3]


def collect_items(spans: list) -> list:
    """
    Repère dans le corps de la page (y > BODY_Y), en ordre de lecture
    (colonne gauche puis droite, de haut en bas) :
      • 'piece'   : en-tête « Voiture » d'une pièce de travail
      • 'marker'  : ligne précédente / suivante « (XXX) »
      • 'segment' : trajet « XX - P » ou « XX / - / Régulier »
    """
    items = []
    for s in spans:
        x0, y0 = s['bbox'][0], s['bbox'][1]
        if y0 <= BODY_Y:
            continue
        col = 0 if x0 < PAGE_MID else 1
        m = LINE_RE.match(s['text'])
        if m:
            items.append({'kind': 'segment', 'ligne': m.group(1),
                          'span': s, 'col': col, 'y': y0})
        elif s['text'] == 'Voiture':
            items.append({'kind': 'piece', 'col': col, 'y': y0})
        elif MARKER_RE.match(s['text']):
            items.append({'kind': 'marker', 'span': s, 'col': col, 'y': y0})
    items.sort(key=lambda i: (i['col'], i['y']))
    return items


def find_departure(spans: list, seg_bbox, in_left: bool):
    """(arrêt de départ, heure, bbox de l'heure) juste sous un segment."""
    _, _, _, ry1 = seg_bbox
    first_stop_y, dep_stop = None, None
    for s in spans:
        bx0, by0, _, _ = s['bbox']
        if ((bx0 < PAGE_MID) == in_left and ry1 < by0 < ry1 + 40
                and not TIME_RE.match(s['text']) and len(s['text']) > 5):
            first_stop_y, dep_stop = by0, s['text']
            break
    if first_stop_y is None:
        return None, None, None
    for s in spans:
        bx0, by0, _, _ = s['bbox']
        if (abs(by0 - first_stop_y) < 3 and TIME_RE.match(s['text'])
                and (bx0 < PAGE_MID) == in_left):
            return dep_stop, s['text'], s['bbox']
    return dep_stop, None, None


def pick_direction(dep_stop: str, stop_a: str, stop_b: str) -> bool:
    """True = direction A, selon les mots-clés du nom d'arrêt de départ."""
    if not dep_stop:
        return True
    def norm(x):
        return x.lower().replace('-', ' ').replace('/', ' ')
    dn = norm(dep_stop)
    ka = [k for k in norm(stop_a).split() if len(k) > 3]
    kb = [k for k in norm(stop_b).split() if len(k) > 3]
    return sum(k in dn for k in ka) >= sum(k in dn for k in kb)


def num_rect_in_span(page, span, ligne) -> pymupdf.Rect:
    """Rectangle couvrant uniquement le numéro de ligne dans le span."""
    rect = pymupdf.Rect(span['bbox'])
    hits = page.search_for(str(ligne), clip=rect)
    if hits:
        return hits[0]
    ratio = len(str(ligne)) / max(len(span['text']), 1)
    return pymupdf.Rect(rect.x0, rect.y0, rect.x0 + rect.width * ratio, rect.y1)


def plan_annotations(page, spans: list, schedules: dict) -> list:
    """
    Construit le plan d'annotations du corps de la carte (liste de dicts),
    sans rien dessiner — c'est cette structure que les tests de régression
    comparent à l'attendu :
      {'type': 'jaune',  'texte': '(168)'}
      {'type': 'bleu',   'ligne': '168', 'heure': '16:31'}
      {'type': 'rouge',  'ligne': '168', 'heure': '16:31', 'prec': '16:07',
       'texte': 'p:16.07'}
    Règle du rouge : premier segment de chaque pièce de travail, puis chaque
    changement de ligne à l'intérieur d'une pièce.
    """
    plan = []
    prev_ligne = None
    for it in collect_items(spans):
        if it['kind'] == 'piece':
            prev_ligne = None
            continue

        if it['kind'] == 'marker':
            plan.append({'type': 'jaune', 'texte': it['span']['text'],
                         'rect': pymupdf.Rect(it['span']['bbox'])})
            continue

        # --- segment -------------------------------------------------------
        ligne = it['ligne']
        in_left = it['col'] == 0
        dep_stop, dep_time, dep_bbox = find_departure(spans, it['span']['bbox'], in_left)
        plan.append({'type': 'bleu', 'ligne': ligne, 'heure': dep_time,
                     'rect': num_rect_in_span(page, it['span'], ligne)})

        nouvelle_ligne = ligne != prev_ligne
        prev_ligne = ligne
        if not nouvelle_ligne:
            continue
        if ligne not in schedules:
            log(f"  Ligne {ligne} @ {dep_time}: pas de données GTFS -- pas de rouge")
            continue
        if not dep_time:
            log(f"  Ligne {ligne}: heure de départ non trouvée (stop={dep_stop})")
            continue
        sc = schedules[ligne]
        use_a = pick_direction(dep_stop, sc['stop_a'], sc['stop_b'])
        prec = prev_dep(sc['a'] if use_a else sc['b'], dep_time)
        log(f"  Ligne {ligne} @ {dep_time} ({dep_stop}) "
            f"dir={'A' if use_a else 'B'} -> Prec={prec}")
        if prec:
            plan.append({'type': 'rouge', 'ligne': ligne, 'heure': dep_time,
                         'prec': prec, 'texte': f"p:{prec.replace(':', '.')}",
                         'point': (dep_bbox[0], dep_bbox[1] - 1)})
    return plan


def apply_annotations(page, plan: list) -> None:
    """Dessine le plan d'annotations sur la page."""
    for a in plan:
        if a['type'] == 'jaune':
            r = a['rect']
            page.draw_rect(pymupdf.Rect(r.x0 - 2, r.y0 - 2, r.x1 + 2, r.y1 + 2),
                           color=None, fill=JAUNE, fill_opacity=0.4, overlay=False)
        elif a['type'] == 'bleu':
            page.draw_rect(a['rect'], color=None, fill=BLEU,
                           fill_opacity=0.4, overlay=False)
        elif a['type'] == 'rouge':
            page.insert_text(pymupdf.Point(*a['point']), a['texte'],
                             fontsize=7, color=ROUGE, fontname='helv')


def annotate(src: str, dst: str, schedules: dict) -> dict:
    """Annote le PDF et le sauvegarde. Retourne les métadonnées extraites."""
    doc = pymupdf.open(src)
    page = doc[0]
    spans = get_spans(page)

    meta = extract_meta(spans)
    meta.update(extract_jour_type(page.get_text()))

    highlight_prise(page, spans)
    plan = plan_annotations(page, spans, schedules)
    apply_annotations(page, plan)
    n = {t: sum(1 for a in plan if a['type'] == t) for t in ('jaune', 'bleu', 'rouge')}
    log(f"Annotations : {n['jaune']} jaune(s), {n['bleu']} bleu(s), {n['rouge']} rouge(s)")

    tmp = os.path.join(tempfile.gettempdir(), f'_carte_agent_{os.getpid()}.pdf')
    doc.save(tmp, garbage=4, deflate=True)
    doc.close()
    shutil.copy2(tmp, dst)
    try:
        os.unlink(tmp)
    except OSError:
        pass
    return meta


# ===========================================================================
#  5.  Résolution des chemins / date
# ===========================================================================
def resolve_date(pdf_path: Path, explicit: str | None) -> str:
    if explicit:
        datetime.strptime(explicit, "%Y-%m-%d")   # valide le format
        return explicit
    m = re.search(r'(\d{4}-\d{2}-\d{2})', pdf_path.name)
    if m:
        return m.group(1)
    return datetime.now().strftime("%Y-%m-%d")


def resolve_gtfs(arg: str | None) -> Path | None:
    candidates = []
    if arg:
        candidates.append(Path(arg))
    if os.environ.get("STM_GTFS_DIR"):
        candidates.append(Path(os.environ["STM_GTFS_DIR"]))
    candidates.append(Path.cwd() / "gtfs_stm")
    for c in candidates:
        if (c / "trips.txt").exists():
            return c
    return None


# ===========================================================================
#  6.  CLI
# ===========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Annote une carte agent (PDF) avec horaires GTFS locaux.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", required=True, help="PDF source de la carte agent")
    ap.add_argument("--out", help="PDF annoté en sortie "
                                  "(défaut : <pdf>-surligné.pdf à côté de la source)")
    ap.add_argument("--gtfs", help="Dossier GTFS STM (contenant trips.txt, etc.). "
                                   "Défaut : $STM_GTFS_DIR puis ./gtfs_stm")
    ap.add_argument("--date", help="Date AAAA-MM-JJ (défaut : extraite du nom de "
                                   "fichier, sinon aujourd'hui)")
    ap.add_argument("--no-gtfs", action="store_true",
                    help="Ignore le GTFS : surlignage jaune + bleu seulement")
    ap.add_argument("--json", action="store_true",
                    help="Affiche un résumé JSON sur stdout (carte, début, fin, lignes)")
    ap.add_argument("--meta-only", action="store_true",
                    help="N'annote pas le PDF : extrait seulement les métadonnées "
                         "(carte, prise début/fin, lignes) et les imprime en JSON sur "
                         "stdout. Utile pour un PDF déjà annoté ailleurs (identifier "
                         "sans relancer le traitement GTFS).")
    args = ap.parse_args()

    src = Path(args.pdf).expanduser()
    if not src.is_file():
        sys.exit(f"ERREUR : PDF introuvable : {src}")

    if args.meta_only:
        doc = pymupdf.open(str(src))
        meta = extract_meta(get_spans(doc[0]))
        meta.update(extract_jour_type(doc[0].get_text()))
        doc.close()
        print(json.dumps(meta, ensure_ascii=False))
        return 0

    out = (Path(args.out).expanduser() if args.out
           else src.with_name(f"{src.stem}-surligné.pdf"))
    date_str = resolve_date(src, args.date)
    log(f"Date retenue : {date_str}")

    # Pré-lecture pour connaître les lignes avant d'interroger le GTFS
    doc = pymupdf.open(str(src))
    meta_pre = extract_meta(get_spans(doc[0]))
    doc.close()
    log(f"Lignes détectées : {meta_pre['lignes']}")

    schedules = {}
    if args.no_gtfs:
        log("GTFS désactivé (--no-gtfs).")
    elif meta_pre["lignes"]:
        gtfs_dir = resolve_gtfs(args.gtfs)
        if gtfs_dir is None:
            log("GTFS introuvable — surlignage bleu seulement (pas d'annotation rouge).")
            log("  Précise le dossier avec --gtfs ou la variable STM_GTFS_DIR.")
        else:
            log(f"GTFS : {gtfs_dir}")
            schedules = get_terminus_times(gtfs_dir, meta_pre["lignes"], date_str)

    meta = annotate(str(src), str(out), schedules)

    log(f"OK — PDF annoté : {out}")
    summary = {"carte": meta["carte"], "debut": meta["debut"],
               "fin": meta["fin"], "lignes": meta["lignes"], "out": str(out)}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"\nCarte {meta['carte']} — {meta['debut']} -> {meta['fin']}")
        print(f"Lignes : {', '.join(meta['lignes']) or '(aucune)'}")
        print(f"Sortie : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
