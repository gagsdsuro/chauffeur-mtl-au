"""chauffeur.modeles — contrats de données du domaine (dataclasses).

Le modèle EST l'architecture : ces structures sont les frontières entre le
parsing (carte agent), l'appariement G-D et le filtrage d'évènements.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date


@dataclass
class Segment:
    """Un aller d'un trajet : terminus de départ/arrivée + heures (HH:MM HASTUS,
    peut dépasser 24:00 pour les services de nuit). Les stops peuvent être vides
    si la mise en page du PDF ne les a pas rendus exploitables."""
    debut_stop: str = ""
    fin_stop: str = ""
    debut: str = ""
    fin: str = ""


@dataclass
class Trajet:
    """Un bloc de trajet de la carte agent (un en-tête « 125 - P / - / Régulier »)."""
    ligne: str
    designation: str = ""      # ce qui suit « - » dans l'en-tête (« P », « 05 », …)
    service: str = ""          # « Régulier », « Scolaire », …
    segment: Segment = field(default_factory=Segment)


@dataclass
class Hlp:
    """Trajet haut-le-pied (déplacement à vide)."""
    id: str
    instructions: str = ""
    code_debut: str = ""
    code_fin: str = ""


@dataclass
class CarteAgent:
    """Modèle texte d'une carte agent HASTUS (pages 1-2)."""
    assignation: str = ""
    date: _date | None = None
    voiture: str = ""
    lieu_debut: str = ""
    heure_debut: str = ""
    heure_fin: str = ""
    garage: str = ""
    lignes: list[str] = field(default_factory=list)
    trajets: list[Trajet] = field(default_factory=list)
    hlp: list[Hlp] = field(default_factory=list)

    def segments_par_ligne(self) -> dict:
        """{ '125': [(départ, arrivée), …] } — seulement les trajets dont les deux
        terminus sont exploitables (filtrage de gen_rapport)."""
        out: dict = {}
        for tr in self.trajets:
            s = tr.segment
            if s.debut_stop and s.fin_stop:
                out.setdefault(tr.ligne, []).append((s.debut_stop, s.fin_stop))
        return out

    def time_ranges_par_ligne(self) -> dict:
        """{ '125': [{debut, fin, debut_stop, fin_stop}, …] } — tous les trajets
        ayant des heures (forme attendue par le tableau de bord)."""
        out: dict = {}
        for tr in self.trajets:
            s = tr.segment
            if s.debut and s.fin:
                out.setdefault(tr.ligne, []).append({
                    "debut": s.debut, "fin": s.fin,
                    "debut_stop": s.debut_stop, "fin_stop": s.fin_stop,
                })
        return out
