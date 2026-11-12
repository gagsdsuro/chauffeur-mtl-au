"""chauffeur.matricule — validation des matricules de chauffeur.

Un matricule est une chaîne de 5 chiffres comprise entre MATRICULE_MIN et
MATRICULE_MAX. Il est l'identifiant stable d'un chauffeur : il désigne son
répertoire personnel dans `data/<matricule>/` et servira de login pour
l'authentification (phase 3, auth par PIN).
"""
from __future__ import annotations

import re

MATRICULE_MIN = 20000
MATRICULE_MAX = 99999

# Séquences de 5 chiffres isolées : tous les matricules valides (20000-99999)
# font exactement 5 chiffres, donc une telle séquence ne peut pas être un
# sous-ensemble d'un nombre plus long (ex. 100000).
_MOT_MATRICULE = re.compile(r"\b\d{5}\b")


def matricule_valide(matricule: str | None) -> bool:
    """True si `matricule` est une valeur de 5 chiffres dans la plage valide."""
    if not isinstance(matricule, str):
        return False
    return (
        len(matricule) == 5
        and matricule.isdigit()
        and MATRICULE_MIN <= int(matricule) <= MATRICULE_MAX
    )


def matcher_matricule(texte: str | None) -> str | None:
    """Premier matricule valide trouvé dans un texte libre, ou None.

    Utile pour extraire le matricule d'un résumé de journée, d'un champ de
    relève (ex. « Je suis relevé par - 40001 ») ou d'une saisie libre.
    """
    for candidat in _MOT_MATRICULE.findall(texte or ""):
        if matricule_valide(candidat):
            return candidat
    return None