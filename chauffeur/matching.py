"""chauffeur.matching — appariement de noms d'arrêts et de rues (utilitaire pur).

Source de vérité unique, anciennement dupliquée dans gen_rapport.py
(appariement d'arrêts) et rapport_gd.py (normalisation de rue).
Aucune dépendance UI/CLI.
"""
import re
import unicodedata

# Jetons trop communs pour distinguer un terminus (articles, génériques,
# indicateurs de quai/direction). Ignorés lors de l'appariement.
STOP_NOISE = {
    "DE", "DU", "DES", "LA", "LE", "LES", "AU", "AUX", "ET", "A",
    "NO", "DIR", "STATION", "REM", "TERMINUS", "GARAGE",
    "NORD", "SUD", "EST", "OUEST",
}

ABBREV = {"STE": "SAINTE", "ST": "SAINT", "PRES": "PRESIDENT"}


def stop_tokens(name: str) -> set:
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
        tok = ABBREV.get(raw, raw)
        if len(tok) < 2 or tok.isdigit() or tok in STOP_NOISE:
            continue
        tokens.add(tok)
    return tokens


def stops_match(a: str, b: str) -> bool:
    """Deux noms d'arrêt désignent-ils le même lieu (≥ 1 jeton distinctif commun) ?"""
    ta, tb = stop_tokens(a), stop_tokens(b)
    return bool(ta and tb and (ta & tb))


def normalize_street(s: str) -> str:
    """Normalise un nom de rue pour la comparaison : minuscules, sans accents ni tirets.

    Étend aussi les abréviations courantes des descriptions_gd :
      STE → sainte, ST → saint.
    """
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[-\s]+", " ", s).strip()
    s = re.sub(r"\bste\b", "sainte", s)
    s = re.sub(r"\bst\b",  "saint",  s)
    return s
