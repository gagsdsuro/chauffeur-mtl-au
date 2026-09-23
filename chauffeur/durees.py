"""Résumé des durées d'une journée, sans accès aux fichiers ni à Streamlit.

Les heures restent exprimées dans le quart (24:15, 26:33, etc.). Une valeur
inconnue est représentée par None ; zéro reste une durée connue.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import re

from .modeles import Journee


TEMPS_FIN_ENTREE = 10
_TYPES_TRAJET = {
    "service": "ligne", "haut_le_pied": "hlp",
    "entree": "entrée", "sortie": "sortie",
}


@dataclass(frozen=True)
class LigneDuree:
    index_piece: int
    type_segment: str
    heure: str | None
    segment: str
    direction: str | None = None
    duree: int | None = None
    battement: int | None = None
    duree_totale: int | None = None
    battement_maximal: bool = False


@dataclass(frozen=True)
class AnomalieDuree:
    index_piece: int
    id_piece: str
    message: str


@dataclass
class ResumeDurees:
    lignes: list[LigneDuree] = field(default_factory=list)
    prise_debut: str | None = None
    prise_fin: str | None = None
    anomalies: list[AnomalieDuree] = field(default_factory=list)


def _heure(minutes: int | None) -> str | None:
    return None if minutes is None else f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class _CalculPiece:
    index: int
    identifiant: str
    anomalies: list[AnomalieDuree]

    def signaler(self, message: str) -> None:
        anomalie = AnomalieDuree(self.index, self.identifiant, message)
        if anomalie not in self.anomalies:
            self.anomalies.append(anomalie)

    def minutes(self, valeur, libelle: str) -> int | None:
        if isinstance(valeur, str) and re.fullmatch(r"[0-9]+:[0-5][0-9]", valeur.strip()):
            heures, minutes = map(int, valeur.split(":"))
            return heures * 60 + minutes
        self.signaler(f"{libelle} : heure absente ou invalide.")
        return None

    def intervalle(self, debut: int | None, fin: int | None, libelle: str) -> int | None:
        if debut is None or fin is None:
            self.signaler(f"{libelle} : durée incalculable.")
            return None
        if fin < debut:
            self.signaler(f"{libelle} : horaires incohérents (durée négative).")
            return None
        return fin - debut


def resumer_durees(journee: Journee | dict) -> ResumeDurees:
    """Calcule les lignes, bornes de prise et anomalies, sans modifier l'entrée.

    L'ordre et les occurrences de pièces sont conservés, même en TS ou avec
    des identifiants identiques. Une entrée finale se termine à son arrivée
    + 10 minutes ; sinon la borne finale est le champ ``fin`` de la pièce.
    Les maxima sont établis avant tout filtrage, uniquement si tous les
    battements des trajets de la pièce sont connus (y compris les zéros).
    """
    donnees = journee.to_dict() if isinstance(journee, Journee) else journee
    resultat = ResumeDurees()
    precedent: _CalculPiece | None = None
    fin_precedente: int | None = None

    for index, piece in enumerate(donnees.get("pieces") or []):
        calcul = _CalculPiece(index, str(piece.get("id") or "sans identifiant"), resultat.anomalies)
        prise = calcul.minutes(piece.get("prise"), "Prise")
        trajets = piece.get("trajets") or []
        departs, arrivees = [], []
        for numero, trajet in enumerate(trajets, 1):
            departs.append(calcul.minutes(
                (trajet.get("depart") or {}).get("heure"), f"Trajet {numero}, départ"
            ))
            arrivees.append(calcul.minutes(
                (trajet.get("arrivee") or {}).get("heure"), f"Trajet {numero}, arrivée"
            ))

        if trajets and trajets[-1].get("type") == "entree":
            fin = arrivees[-1] + TEMPS_FIN_ENTREE if arrivees[-1] is not None else None
        else:
            fin = calcul.minutes(piece.get("fin"), "Fin")
        if prise is not None and fin is not None:
            calcul.intervalle(prise, fin, "Pièce")

        if index == 0:
            resultat.prise_debut = _heure(prise)
        resultat.prise_fin = _heure(fin)

        if precedent is not None:
            pause = precedent.intervalle(fin_precedente, prise, "Pause vers la pièce suivante")
            if pause != 0:
                resultat.lignes.append(LigneDuree(
                    precedent.index, "pause", _heure(fin_precedente), "pause",
                    battement=pause, duree_totale=pause,
                ))

        if piece.get("type_horaire") == "absence":
            duree = calcul.intervalle(prise, fin, "Absence")
            resultat.lignes.append(LigneDuree(
                index, "absence", _heure(prise), "absence",
                duree=duree, duree_totale=duree,
            ))
            resultat.lignes.append(LigneDuree(index, "fin", _heure(fin), "fin"))
            precedent, fin_precedente = calcul, fin
            continue

        if not trajets:
            calcul.signaler("Aucun trajet renseigné.")
        duree_prise = calcul.intervalle(prise, departs[0] if departs else None, "Prise")
        resultat.lignes.append(LigneDuree(
            index, "prise", _heure(prise), "prise",
            battement=duree_prise, duree_totale=duree_prise,
        ))

        lignes_trajets = []
        for numero, trajet in enumerate(trajets):
            type_segment = _TYPES_TRAJET.get(trajet.get("type"), "inconnu")
            if type_segment == "inconnu":
                calcul.signaler(f"Trajet {numero + 1} : type inconnu.")
            duree = calcul.intervalle(departs[numero], arrivees[numero], f"Trajet {numero + 1}")
            prochain = departs[numero + 1] if numero + 1 < len(trajets) else fin
            battement = calcul.intervalle(arrivees[numero], prochain, f"Battement {numero + 1}")
            total = duree + battement if duree is not None and battement is not None else None
            lignes_trajets.append(LigneDuree(
                index, type_segment, _heure(departs[numero]),
                str(trajet.get("ligne") or "—") if type_segment == "ligne" else type_segment,
                direction=(trajet.get("direction") or None) if type_segment == "ligne" else None,
                duree=duree, battement=battement, duree_totale=total,
            ))

        if lignes_trajets and all(l.battement is not None for l in lignes_trajets):
            maximum = max(l.battement for l in lignes_trajets)
            lignes_trajets = [
                replace(l, battement_maximal=l.battement == maximum) for l in lignes_trajets
            ]
        resultat.lignes.extend(lignes_trajets)
        resultat.lignes.append(LigneDuree(index, "fin", _heure(fin), "fin"))
        precedent, fin_precedente = calcul, fin

    return resultat
