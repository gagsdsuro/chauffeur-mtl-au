"""chauffeur.evenements — applicabilité et sémantique des évènements.

Décision pure (sans I/O fichier) : un consommateur lit les fichiers d'évènements
puis appelle ces fonctions avec la plage de quart de la ligne concernée.

Deux familles : l'applicabilité (l'évènement joue-t-il ce jour / ce quart ?) et
la sémantique des arrêts touchés (l'arrêt listé est-il supprimé ou maintenu ?) —
source unique de la teinte des rapports.
"""
from __future__ import annotations

from datetime import date, datetime
import re

from .effectif import event_applies_to_shift, parse_shift_time


def comparer_evenements(avant: list[dict], apres: list[dict]) -> dict[str, list]:
    """Compare deux listes par groupe d'ID, sans perdre les doublons légitimes.

    Le résultat contient les groupes ``nouveaux``, ``retires`` et ``modifies``.
    Chaque entrée est ``(identifiant, anciens, nouveaux)``; les listes absentes
    sont vides. L'ordre est stable et déterministe par identifiant.
    """
    def grouper(items: list[dict]) -> dict[str, list[dict]]:
        groupes: dict[str, list[dict]] = {}
        for item in items:
            groupes.setdefault(str(item.get("evenement_id", "?")), []).append(item)
        return groupes

    anciens, nouveaux = grouper(avant), grouper(apres)
    return {
        "nouveaux": [
            (identifiant, [], nouveaux[identifiant])
            for identifiant in sorted(nouveaux.keys() - anciens.keys())
        ],
        "retires": [
            (identifiant, anciens[identifiant], [])
            for identifiant in sorted(anciens.keys() - nouveaux.keys())
        ],
        "modifies": [
            (identifiant, anciens[identifiant], nouveaux[identifiant])
            for identifiant in sorted(anciens.keys() & nouveaux.keys())
            if anciens[identifiant] != nouveaux[identifiant]
        ],
    }


def resumer_changements_evenements(avant: list[dict], apres: list[dict]) -> list[str]:
    """Résumé court commun à l'UI et aux importeurs."""
    comparaison = comparer_evenements(avant, apres)
    changements: list[str] = []
    for identifiant, _, nouveaux in comparaison["nouveaux"]:
        titre = nouveaux[0].get("titre", "sans titre")
        changements.append(f"Nouveau #{identifiant} — {titre}")
    for identifiant, anciens, _ in comparaison["retires"]:
        titre = anciens[0].get("titre", "sans titre")
        changements.append(f"Retiré #{identifiant} — {titre}")
    for identifiant, _, _ in comparaison["modifies"]:
        changements.append(f"Modifié #{identifiant}")
    return changements


def evenements_retires(avant: list[dict], apres: list[dict]) -> list[dict]:
    """Toutes les variantes des ID entièrement absents de la nouvelle liste."""
    comparaison = comparer_evenements(avant, apres)
    return [event for _, anciens, _ in comparaison["retires"] for event in anciens]


def evenements_modifies(avant: list[dict], apres: list[dict]) -> list[dict]:
    """Groupes modifiés avec leurs variantes complètes avant et après."""
    comparaison = comparer_evenements(avant, apres)
    return [
        {
            "evenement_id": identifiant,
            "avant": anciens,
            "apres": nouveaux,
        }
        for identifiant, anciens, nouveaux in comparaison["modifies"]
    ]


def trier_evenements_par_arrets(events: list[dict], ordre_arrets) -> list[dict]:
    """Trie les évènements selon leur premier arrêt sur le parcours.

    L'ancre est le premier arrêt annulé ou concerné; à défaut, le premier arrêt
    ajouté. Les ancres absentes du parcours sont placées à la fin sans modifier
    leur ordre relatif. La liste reçue n'est jamais modifiée.

    ``ordre_arrets`` accepte une suite d'identifiants ou les couples
    ``(sequence, identifiant)`` retournés par ``stops_for_parcours``.
    """
    if len(events) < 2 or not ordre_arrets:
        return list(events)

    positions: dict[str, int] = {}
    for position, item in enumerate(ordre_arrets):
        identifiant = item[1] if isinstance(item, (list, tuple)) and len(item) >= 2 else item
        positions.setdefault(str(identifiant), position)

    def identifiant_arret(arret) -> str:
        if isinstance(arret, dict):
            return str(arret.get("id") or arret.get("code") or "").strip()
        match = re.match(r"^\s*(\d{5})(?:\s*[-–]|\s*$)", str(arret or ""))
        return match.group(1) if match else ""

    def ancre(event: dict) -> str:
        annules = event.get("arrets_annules") or []
        ajoutes = event.get("arrets_ajoutes") or []
        if annules:
            identifiant = identifiant_arret(annules[0])
            if identifiant:
                return identifiant
        return identifiant_arret(ajoutes[0]) if ajoutes else ""

    hors_parcours = len(positions)
    indexes = sorted(
        range(len(events)),
        key=lambda index: (positions.get(ancre(events[index]), hors_parcours), index),
    )
    return [events[index] for index in indexes]


def applicable_au_quart(event: dict, shift_start: datetime, shift_end: datetime) -> bool:
    """L'évènement est-il actif pendant la plage de quart de la ligne ?"""
    return event_applies_to_shift(event, shift_start, shift_end)


# ── Sémantique des arrêts touchés ─────────────────────────────────────────────
#
# Le portail employé consigne dans `arrets_annules` les arrêts CONCERNÉS par
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
