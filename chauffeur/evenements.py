"""chauffeur.evenements — applicabilité et sémantique des évènements.

Décision pure (sans I/O fichier) : un consommateur lit les fichiers d'évènements
puis appelle ces fonctions avec la plage de quart de la ligne concernée.

Deux familles : l'applicabilité (l'évènement joue-t-il ce jour / ce quart ?) et
la sémantique des arrêts touchés (l'arrêt listé est-il supprimé ou maintenu ?) —
source unique de la teinte des rapports.
"""
from __future__ import annotations

from datetime import date, datetime

from .effectif import event_applies_to_shift, parse_shift_time


def applicable_au_quart(event: dict, shift_start: datetime, shift_end: datetime) -> bool:
    """L'évènement est-il actif pendant la plage de quart de la ligne ?"""
    return event_applies_to_shift(event, shift_start, shift_end)


# ── Sémantique des arrêts touchés ─────────────────────────────────────────────
#
# Le portail STM consigne dans `arrets_annules` les arrêts CONCERNÉS par
# l'évènement, pas seulement ceux qui disparaissent. Sous ces titres, l'arrêt
# reste desservi — déplacé de quelques mètres, ou simple consigne au chauffeur.
TITRES_SANS_ANNULATION = frozenset({"arrêt déplacé", "information chauffeur"})


def titre_annule_l_arret(type_evenement: str) -> bool:
    """L'évènement supprime-t-il l'arrêt qu'il liste, ou le maintient-il ?

    Titre inconnu → présumé annulant (fail-safe : ne jamais faire manquer une
    annulation réelle).
    """
    return (type_evenement or "").strip().lower() not in TITRES_SANS_ANNULATION


def arret_reellement_annule(cancelled: list[dict]) -> bool:
    """Au moins un des évènements couvrant l'arrêt le supprime-t-il ?

    Un même arrêt peut cumuler des évènements de sémantiques opposées
    (« Arrêt déplacé » + « Détour avec annulation d'arrêt ») : le plus grave
    l'emporte, quel que soit leur ordre.
    """
    return any(titre_annule_l_arret(ev.get("type_evenement", ""))
               for ev in cancelled or [])


def applicable_a_la_date(event: dict, jour: date) -> bool:
    """L'évènement est-il dans sa plage de validité (date_heure_debut/fin) ce jour ?

    Chaque borne est vérifiée indépendamment ; une borne manquante est ouverte.
    Dates invalides → présumé applicable (fail-safe : ne pas cacher un évènement
    sur une donnée malformée).
    """
    try:
        debut = event.get("date_heure_debut")
        if debut and datetime.fromisoformat(debut).date() > jour:
            return False
        fin = event.get("date_heure_fin")
        if fin and datetime.fromisoformat(fin).date() < jour:
            return False
    except (ValueError, TypeError):
        return True
    return True


def applicable_a_la_plage(event: dict, jour: date,
                          plage: tuple[str, str] | None = None) -> bool:
    """Applicabilité au quart si la plage horaire travaillée est connue,
    sinon repli sur la seule plage de validité (date).

    `plage` = (début, fin) au format heure de quart, ex. ("17:27", "25:21") —
    les heures > 24h débordent sur le lendemain (parse_shift_time). Une plage
    non parseable retombe sur le filtre date (fail-safe).
    """
    if plage:
        try:
            return applicable_au_quart(
                event,
                parse_shift_time(plage[0], jour),
                parse_shift_time(plage[1], jour),
            )
        except (ValueError, TypeError, IndexError):
            pass
    return applicable_a_la_date(event, jour)


def raison_exclusion(event: dict, shift_start: datetime, shift_end: datetime) -> str:
    """Pourquoi l'évènement est non-applicable au quart (chaîne lisible)."""
    debut_str = event.get("date_heure_debut")
    fin_str   = event.get("date_heure_fin")

    if debut_str and datetime.fromisoformat(debut_str) > shift_end:
        return f"Pas encore actif (début {datetime.fromisoformat(debut_str).date()})"
    if fin_str and datetime.fromisoformat(fin_str) < shift_start:
        return f"Expiré (fin {datetime.fromisoformat(fin_str).date()})"

    effectif = event.get("effectif") or ""
    return f"Effectif : {effectif}" if effectif else "Hors plage du quart"
