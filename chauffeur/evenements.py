"""chauffeur.evenements — classement applicable/non-applicable des évènements.

Décision pure (sans I/O fichier) : un consommateur lit les fichiers d'évènements
puis appelle ces fonctions avec la plage de quart de la ligne concernée.
"""
from __future__ import annotations

from datetime import datetime

from .effectif import event_applies_to_shift


def applicable_au_quart(event: dict, shift_start: datetime, shift_end: datetime) -> bool:
    """L'évènement est-il actif pendant la plage de quart de la ligne ?"""
    return event_applies_to_shift(event, shift_start, shift_end)


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
