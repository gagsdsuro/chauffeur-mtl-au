"""chauffeur.journee — fonctions de domaine sur les journées de travail.

Fonctions pures (sans I/O) opérant sur un objet Journee ou sur le dict brut
tel que produit par parse_journee.py.
"""
from __future__ import annotations

from datetime import datetime
import re


def parser_sommaire_absence(entete: str, lignes: list[str]) -> dict:
    """Lit une absence du portail, sans déduire ses heures des autres pièces.

    Les balises HTML peuvent séparer les heures, le tiret et le motif.
    Une absence illisible doit faire échouer l'import, pas disparaître.
    """
    heure = r"[0-9]{1,2}:[0-5][0-9]"
    sommaire = re.fullmatch(
        rf"Sommaire\s*Absence\s*En vigueur\s*({heure})\s*Horaire",
        entete, re.IGNORECASE,
    )
    horaire = re.fullmatch(
        rf"({heure})\s*-\s*({heure})\s+(.+)",
        " ".join(l.strip() for l in lignes if l.strip()),
    )
    if not sommaire or not horaire:
        raise ValueError("Sommaire d'absence incomplet : durée, heures ou motif introuvables")
    return {
        "id": "Absence", "type_horaire": "absence",
        "duree": sommaire.group(1),
        "prise": horaire.group(1), "debut": horaire.group(1),
        "fin": horaire.group(2), "motif_absence": horaire.group(3),
    }


def _as_dict(journee) -> dict:
    """Normalise un Journee ou un dict brut → dict."""
    return journee.to_dict() if hasattr(journee, "to_dict") else journee


def groupes_de_service(journee, avec_trips: bool = False) -> list[dict]:
    """Retourne les groupes uniques (ligne · direction · id_parcours) de la journée.

    Chaque groupe : {ligne, direction, id_parcours, detour}.
    Ordre d'apparition préservé. Si un groupe apparaît avec detour=True dans
    au moins un trajet, le groupe est marqué detour=True.
    Avec avec_trips=True, chaque groupe accumule aussi ses trajets de service
    sous "trips" : [{depart_heure, arrivee_heure}, …] (format heure de quart).
    Accepte un objet Journee ou un dict brut.
    """
    groupes: list[dict] = []
    seen: dict[tuple, int] = {}
    d = _as_dict(journee)

    for piece in d.get("pieces", []):
        for trajet in piece.get("trajets", []):
            if trajet.get("type") != "service":
                continue
            lg = trajet.get("ligne") or ""
            dr = (trajet.get("direction") or "").lower()
            ip = trajet.get("id_parcours")
            if not lg or not dr:
                continue
            key = (lg, dr, ip)
            if key not in seen:
                seen[key] = len(groupes)
                groupe = {
                    "ligne": lg, "direction": dr,
                    "id_parcours": ip, "detour": bool(trajet.get("detour")),
                }
                if avec_trips:
                    groupe["trips"] = []
                groupes.append(groupe)
            elif trajet.get("detour"):
                groupes[seen[key]]["detour"] = True
            if avec_trips:
                groupes[seen[key]]["trips"].append({
                    "depart_heure":  trajet.get("depart",  {}).get("heure", ""),
                    "arrivee_heure": trajet.get("arrivee", {}).get("heure", ""),
                })

    return groupes


def lignes_de_service(
    journee,
    restantes_seulement: bool = False,
    now: datetime | None = None,
) -> list[tuple[str, str]]:
    """Retourne les paires (ligne, direction) uniques de la journée.

    Avec restantes_seulement=True, exclut les pièces dont l'heure de fin
    est dépassée (piece["fin"] <= heure courante). Une pièce sans champ
    "fin" est toujours incluse.
    Accepte un objet Journee ou un dict brut.
    """
    now_hm: str | None = None
    if restantes_seulement:
        now_hm = (now or datetime.now()).strftime("%H:%M")

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    d = _as_dict(journee)

    for piece in d.get("pieces", []):
        if restantes_seulement and piece.get("fin", "99:99") <= now_hm:
            continue
        for trajet in piece.get("trajets", []):
            if trajet.get("type") != "service":
                continue
            ligne = trajet.get("ligne")
            direction = trajet.get("direction")
            if not ligne or not direction:
                continue
            key = (ligne, direction.lower())
            if key not in seen:
                seen.add(key)
                pairs.append(key)

    return pairs
