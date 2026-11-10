"""chauffeur.effectif — applicabilité d'un évènement selon les heures de quart.

Source de vérité de la logique d'effectif, anciennement dans rapport_gd.py.
Évalue : chevauchement de la plage de validité, restriction jour de semaine,
et plage horaire quotidienne (« Seulement entre 07:00 et 19:00 »).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta


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


def bornes_quart(heures: list[str], base_date: date) -> tuple[str, str] | None:
    """(min, max) d'une liste d'heures de quart (HH:MM, peut dépasser 24h),
    triées par valeur réelle via parse_shift_time — pas par ordre lexical, qui
    trie mal un H:MM non zero-paddé (ex. "9:15" > "10:00" lexicalement).
    None si la liste est vide.
    """
    if not heures:
        return None
    par_valeur = sorted((parse_shift_time(h, base_date), h) for h in heures)
    return par_valeur[0][1], par_valeur[-1][1]


def parse_effectif_times(effectif: str):
    """
    Extrait une plage horaire journalière depuis le champ effectif.
    Retourne (h_debut, m_debut, h_fin, m_fin) ou None si non trouvé.

    Exemples reconnus :
      "Seulement entre 12:00 et 19:00 chaque jour"
      "12H00 À 19H00"
      "entre 7h30 et 23h00"
    """
    m = re.search(
        r'(\d{1,2})[h:](\d{2})\s*[àa]\s*(\d{1,2})[h:](\d{2})',
        effectif, re.IGNORECASE
    )
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
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


# « fin(s) de semaine » n'est pas « semaine » (jours ouvrables) : lookbehind.
_RE_JOURS_OUVRABLES = r'lundi.*vendredi|jour.*semaine|(?<!fin de )(?<!fins de )semaine(?!\s*de)'
_RE_FIN_SEMAINE = r'fin.*semaine|samedi.*dimanche|week.?end'


def _restreint(texte: str) -> bool:
    """Le texte contient-il une restriction de jours ou d'heures reconnue ?"""
    return bool(
        re.search(_RE_JOURS_OUVRABLES, texte, re.IGNORECASE)
        or re.search(_RE_FIN_SEMAINE, texte, re.IGNORECASE)
        or parse_effectif_times(texte)
    )


def _texte_restriction(event: dict) -> str:
    """Texte portant les jours/heures d'un évènement.

    L'effectif prime ; s'il ne restreint rien (« En tout temps »), le portail
    consigne parfois la restriction dans le commentaire (« LUNDI AU VENDREDI
    12H00 À 19H00 ») : on s'y replie.
    """
    effectif = (event.get("effectif") or "").strip()
    if _restreint(effectif):
        return effectif
    commentaire = (event.get("commentaire") or "").strip()
    return commentaire if _restreint(commentaire) else effectif


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

    effectif = _texte_restriction(event)

    # 2. Filtre jour de la semaine
    weekdays_in_shift = {d.weekday() for d in _day_range(shift_start, shift_end)}
    if re.search(_RE_JOURS_OUVRABLES, effectif, re.IGNORECASE):
        if not any(w < 5 for w in weekdays_in_shift):
            return False
    elif re.search(_RE_FIN_SEMAINE, effectif, re.IGNORECASE):
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
