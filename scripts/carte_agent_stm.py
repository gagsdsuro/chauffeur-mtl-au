#!/usr/bin/env python3
"""
carte_agent_stm.py — Annotation autonome de la carte agent STM (version CLI)

Prend un PDF de carte agent STM déjà téléchargé et produit une version annotée :
  • Heures de prise (début / fin)  surlignées en JAUNE
  • Numéros de ligne ("XX - P")    surlignés en BLEU
  • Départ précédent de chaque segment annoté en ROUGE (au-dessus de l'heure)

Les horaires terminus proviennent des données GTFS statiques de la STM, lues
localement — aucun appel réseau, aucun navigateur, aucune API Google.

Cette version regroupe en un seul fichier la logique qui était auparavant
répartie entre le skill « carte-agent-stm » (extraction PDF), get_terminus_times.py
(horaires GTFS) et process_pdf.py (annotation).

------------------------------------------------------------------------------
Dépendance :  pip install pymupdf
------------------------------------------------------------------------------

Exemples
--------
    # Cas le plus simple : la date est lue dans le nom du fichier,
    # le GTFS est cherché dans $STM_GTFS_DIR puis ./gtfs_stm
    python3 carte_agent_stm.py --pdf ~/carte-agent-2026-06-03.pdf

    # Tout préciser explicitement
    python3 carte_agent_stm.py \
        --pdf   ~/cartes/carte-agent-2026-06-03.pdf \
        --out   ~/cartes/carte-2026-06-03-annotee.pdf \
        --gtfs  ~/data/gtfs_stm \
        --date  2026-06-03

    # Sans GTFS : surlignage jaune + bleu seulement (pas d'annotation rouge)
    python3 carte_agent_stm.py --pdf carte.pdf --no-gtfs
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
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("ERREUR : PyMuPDF manquant.  Installe-le avec :  pip install pymupdf")

# --------------------------------------------------------------------------- #
# Couleurs et constantes de mise en page (PDF carte agent STM)
# --------------------------------------------------------------------------- #
JAUNE = (1, 1, 0)
BLEU  = (0.4, 0.7, 1.0)
ROUGE = (0.8, 0.1, 0.1)

PAGE_MID = 200          # frontière colonne gauche / droite du PDF STM
TIME_RE  = re.compile(r'^\d{1,2}:\d{2}$')
LINE_RE  = re.compile(r'^(\d+)\s*-\s*P\b')


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
    """'25:47' -> 1547 minutes.  Supporte les heures STM > 24 h."""
    h, m = map(int, t.split(':'))
    return h * 60 + m


# ===========================================================================
#  2.  Extraction des métadonnées (numéro de carte, prise début / fin, lignes)
# ===========================================================================
def extract_meta(spans: list) -> dict:
    """
    Lit dans l'en-tête du PDF :
      • carte  : numéro de la carte agent (3-6 chiffres, y < 130)
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

    # --- numéro de carte : 1er span purement numérique (3-6 chiffres) y<130 --
    carte_num = "?"
    for s in spans:
        if s['bbox'][1] < 130 and re.match(r'^\d{3,6}$', s['text']):
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
                annot = page.add_highlight_annot(
                    fitz.Rect(bx0 - 2, by0 - 2, bx1 + 2, by1_safe(s) + 2))
                annot.set_colors(stroke=JAUNE)
                annot.update()


def by1_safe(s) -> float:
    return s['bbox'][3]


def process_line(page, spans, line_no, times_a, times_b, stop_a, stop_b) -> None:
    """Surligne en bleu chaque segment 'XX - P' et annote en rouge le départ précédent."""
    def norm(x):
        return x.lower().replace('-', ' ').replace('/', ' ')

    stop_a_norm, stop_b_norm = norm(stop_a), norm(stop_b)

    hits = page.search_for(f'{line_no} - P')
    if not hits:
        log(f"  Ligne {line_no}: aucun hit trouvé")
        return
    log(f"  Ligne {line_no}: {len(hits)} segment(s)")

    for rect in hits:
        annot = page.add_highlight_annot(rect)
        annot.set_colors(stroke=BLEU)
        annot.update()

        rx0, _, _, ry1 = rect
        in_left = rx0 < PAGE_MID

        # 1) premier arrêt (non-heure) juste sous le segment, même colonne
        first_stop_y, dep_stop = None, None
        for s in spans:
            bx0, by0, _, _ = s['bbox']
            if ((bx0 < PAGE_MID) == in_left and ry1 < by0 < ry1 + 40
                    and not TIME_RE.match(s['text']) and len(s['text']) > 5):
                first_stop_y, dep_stop = by0, s['text']
                break

        # 2) heure sur la même ligne Y, même colonne
        dep_time, dep_bbox = None, None
        if first_stop_y is not None:
            for s in spans:
                bx0, by0, _, _ = s['bbox']
                if (abs(by0 - first_stop_y) < 3 and TIME_RE.match(s['text'])
                        and (bx0 < PAGE_MID) == in_left):
                    dep_time, dep_bbox = s['text'], s['bbox']
                    break

        if not dep_time:
            log(f"    heure non trouvée (stop={dep_stop})")
            continue

        # 3) direction A ou B selon le nom de l'arrêt
        if dep_stop:
            dn = norm(dep_stop)
            ka = [k for k in stop_a_norm.split() if len(k) > 3]
            kb = [k for k in stop_b_norm.split() if len(k) > 3]
            use_a = sum(k in dn for k in ka) >= sum(k in dn for k in kb)
        else:
            use_a = True

        prec = prev_dep(times_a if use_a else times_b, dep_time)
        log(f"    dep={dep_time} -> Prec={prec}")

        if prec:
            page.insert_text(fitz.Point(dep_bbox[0], dep_bbox[1] - 1),
                             f'Prec: {prec}', fontsize=7, color=ROUGE, fontname='helv')


def annotate(src: str, dst: str, schedules: dict) -> dict:
    """Annote le PDF et le sauvegarde. Retourne les métadonnées extraites."""
    doc = fitz.open(src)
    page = doc[0]
    spans = get_spans(page)

    meta = extract_meta(spans)

    highlight_prise(page, spans)

    for ln in meta["lignes"]:
        if ln in schedules:
            sc = schedules[ln]
            process_line(page, spans, ln, sc['a'], sc['b'], sc['stop_a'], sc['stop_b'])
        else:
            log(f"  Ligne {ln}: pas de données GTFS -- bleu seulement")
            for rect in page.search_for(f'{ln} - P'):
                annot = page.add_highlight_annot(rect)
                annot.set_colors(stroke=BLEU)
                annot.update()

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
        description="Annote une carte agent STM (PDF) avec horaires GTFS locaux.",
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
    args = ap.parse_args()

    src = Path(args.pdf).expanduser()
    if not src.is_file():
        sys.exit(f"ERREUR : PDF introuvable : {src}")

    out = (Path(args.out).expanduser() if args.out
           else src.with_name(f"{src.stem}-surligné.pdf"))
    date_str = resolve_date(src, args.date)
    log(f"Date retenue : {date_str}")

    # Pré-lecture pour connaître les lignes avant d'interroger le GTFS
    doc = fitz.open(str(src))
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
