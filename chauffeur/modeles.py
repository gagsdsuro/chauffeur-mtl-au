"""chauffeur.modeles — contrats de données du domaine (dataclasses).

Le modèle EST l'architecture : ces structures sont les frontières entre le
parsing (carte agent), l'appariement G-D et le filtrage d'évènements.

Domaines couverts :
  · Journée de travail  — Journee, Piece, TrajetService, TrajetHlp, ArretHoraire
  · Événements du portail      — FichierEvenements, Evenement, ArretAnnule
  · Gauche-Droite       — FichierGD, RouteGD, ParcoursGD

Chaque dataclass expose :
  from_dict(d)  → construit depuis le dict JSON tel qu'écrit sur disque.
  to_dict()     → retourne le dict JSON canonique (clés dans l'ordre de référence).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════════
# Domaine Journée
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ArretHoraire:
    """Arrêt avec heure (ex. départ/arrivée d'un trajet de service)."""
    heure: str
    arret: str

    @classmethod
    def from_dict(cls, d: dict) -> ArretHoraire:
        return cls(heure=d.get("heure", ""), arret=d.get("arret", ""))

    def to_dict(self) -> dict:
        return {"heure": self.heure, "arret": self.arret}


@dataclass
class TrajetService:
    """Trajet de service (type='service') d'une pièce de travail."""
    ligne: str
    direction: str
    id_parcours: int | None
    depart: ArretHoraire
    arrivee: ArretHoraire
    detour: bool = False
    notes_voyage: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> TrajetService:
        return cls(
            ligne=d.get("ligne", ""),
            direction=(d.get("direction") or "").lower(),
            id_parcours=d.get("id_parcours"),
            depart=ArretHoraire.from_dict(d.get("depart") or {}),
            arrivee=ArretHoraire.from_dict(d.get("arrivee") or {}),
            detour=bool(d.get("detour", False)),
            notes_voyage=list(d.get("notes_voyage") or []),
        )

    def to_dict(self) -> dict:
        d: dict = {
            "type": "service",
            "ligne": self.ligne,
            "direction": self.direction,
            "id_parcours": self.id_parcours,
            "detour": self.detour,
            "depart": self.depart.to_dict(),
            "arrivee": self.arrivee.to_dict(),
        }
        if self.notes_voyage:
            d["notes_voyage"] = self.notes_voyage
        return d


@dataclass
class TrajetHlp:
    """Trajet haut-le-pied (type='haut_le_pied') — déplacement à vide."""
    depart: ArretHoraire
    arrivee: ArretHoraire

    @classmethod
    def from_dict(cls, d: dict) -> TrajetHlp:
        return cls(
            depart=ArretHoraire.from_dict(d.get("depart") or {}),
            arrivee=ArretHoraire.from_dict(d.get("arrivee") or {}),
        )

    def to_dict(self) -> dict:
        return {
            "type": "haut_le_pied",
            "ligne": None, "direction": None, "id_parcours": None, "detour": False,
            "depart": self.depart.to_dict(),
            "arrivee": self.arrivee.to_dict(),
        }


def _trajet_from_dict(d: dict) -> TrajetService | TrajetHlp | dict:
    """Désérialise un trajet selon son type ; conserve les types inconnus comme dict."""
    t = d.get("type")
    if t == "service":
        return TrajetService.from_dict(d)
    if t == "haut_le_pied":
        return TrajetHlp.from_dict(d)
    return d


def _trajet_to_dict(t: TrajetService | TrajetHlp | dict) -> dict:
    return t.to_dict() if hasattr(t, "to_dict") else t


@dataclass
class Piece:
    """Une pièce de travail ou d'absence (type_horaire="absence").

    Champs horaires :
      prise  — heure de début de la prise de service (arrivée au lieu_prise).
      debut  — heure du premier trajet de service.
      fin    — heure du dernier trajet de service.
    Pour une absence, prise/debut et fin bornent la période indiquée par le
    portail ; motif_absence conserve le code et le libellé, sans trajet.
    """
    id: str
    duree: str
    prise: str
    lieu_prise: str
    debut: str
    fin: str
    lieu_fin: str
    type_horaire: str = "horaire"
    trajets: list = field(default_factory=list)   # list[TrajetService | TrajetHlp | dict]
    numero_autobus: str | None = None
    releve: dict | None = None
    motif_absence: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Piece:
        return cls(
            id=d.get("id", ""),
            duree=d.get("duree", ""),
            prise=d.get("prise", ""),
            lieu_prise=d.get("lieu_prise", ""),
            debut=d.get("debut", ""),
            fin=d.get("fin", ""),
            lieu_fin=d.get("lieu_fin", ""),
            type_horaire=d.get("type_horaire", "horaire"),
            numero_autobus=d.get("numero_autobus"),
            releve=d.get("releve"),
            motif_absence=d.get("motif_absence"),
            trajets=[_trajet_from_dict(t) for t in d.get("trajets", [])],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type_horaire": self.type_horaire,
            **({"motif_absence": self.motif_absence} if self.motif_absence is not None else {}),
            "numero_autobus": self.numero_autobus,
            "duree": self.duree,
            "prise": self.prise,
            "lieu_prise": self.lieu_prise,
            "debut": self.debut,
            "fin": self.fin,
            "lieu_fin": self.lieu_fin,
            "releve": self.releve,
            "trajets": [_trajet_to_dict(t) for t in self.trajets],
        }

    def trajets_service(self) -> list[TrajetService]:
        return [t for t in self.trajets if isinstance(t, TrajetService)]


@dataclass
class Journee:
    """Journée de travail complète (sortie de parse_journee.py)."""
    date: str
    journee_numero: int | str   # int depuis parse_journee, str si chargé tel quel
    garage: str
    temps_travaille: str
    garage_id: str = ""
    temps_supplementaire: str = ""
    mis_a_jour: str = ""
    pieces: list[Piece] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Journee:
        return cls(
            date=d.get("date", ""),
            garage_id=d.get("garage_id", ""),
            garage=d.get("garage", ""),
            journee_numero=d.get("journee_numero", ""),
            temps_travaille=d.get("temps_travaille", ""),
            temps_supplementaire=d.get("temps_supplementaire", ""),
            mis_a_jour=d.get("mis_a_jour", ""),
            pieces=[Piece.from_dict(p) for p in d.get("pieces", [])],
        )

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "garage_id": self.garage_id,
            "garage": self.garage,
            "journee_numero": self.journee_numero,
            "temps_travaille": self.temps_travaille,
            "temps_supplementaire": self.temps_supplementaire,
            "mis_a_jour": self.mis_a_jour,
            "pieces": [p.to_dict() for p in self.pieces],
        }

    def trajets_service(self) -> list[TrajetService]:
        return [t for p in self.pieces for t in p.trajets_service()]


# ═══════════════════════════════════════════════════════════════════════════════
# Domaine Événements
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ArretAnnule:
    """Référence à un arrêt annulé dans un événement."""
    id: str
    nom: str

    @classmethod
    def from_dict(cls, d: dict) -> ArretAnnule:
        return cls(id=d.get("id", ""), nom=d.get("nom", ""))

    def to_dict(self) -> dict:
        return {"id": self.id, "nom": self.nom}


@dataclass
class Evenement:
    """Un détour ou annulation d'arrêt."""
    evenement_id: str
    titre: str
    motif: str
    effectif: str
    date_heure_debut: str | None
    date_heure_fin: str | None
    arrets_annules: list[ArretAnnule] = field(default_factory=list)
    arrets_ajoutes: list = field(default_factory=list)   # str | dict selon l'origine
    description_gd: str | None = None
    commentaire: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Evenement:
        return cls(
            evenement_id=d.get("evenement_id", ""),
            titre=d.get("titre", ""),
            motif=d.get("motif", ""),
            effectif=d.get("effectif", ""),
            date_heure_debut=d.get("date_heure_debut"),
            date_heure_fin=d.get("date_heure_fin"),
            arrets_annules=[ArretAnnule.from_dict(a) for a in d.get("arrets_annules", [])],
            arrets_ajoutes=list(d.get("arrets_ajoutes") or []),
            description_gd=d.get("description_gd"),
            commentaire=d.get("commentaire"),
        )

    def to_dict(self) -> dict:
        return {
            "evenement_id": self.evenement_id,
            "titre": self.titre,
            "motif": self.motif,
            "date_heure_debut": self.date_heure_debut,
            "date_heure_fin": self.date_heure_fin,
            "effectif": self.effectif,
            "arrets_annules": [a.to_dict() for a in self.arrets_annules],
            "commentaire": self.commentaire,
            "arrets_ajoutes": self.arrets_ajoutes,
            "description_gd": self.description_gd,
        }


@dataclass
class FichierEvenements:
    """Contenu d'un fichier data/Events/<ligne>_<direction>.json."""
    ligne: str
    direction: str
    detours: list[Evenement] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> FichierEvenements:
        return cls(
            ligne=d.get("ligne", ""),
            direction=d.get("direction", ""),
            detours=[Evenement.from_dict(e) for e in d.get("detours", [])],
        )

    def to_dict(self) -> dict:
        return {
            "ligne": self.ligne,
            "direction": self.direction,
            "detours": [e.to_dict() for e in self.detours],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Domaine Gauche-Droite
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ParcoursGD:
    """Un parcours d'une ligne G-D (ex. 'Parcours principal', 'Parcours scolaire')."""
    id: int
    name: str
    start: str
    start_code: str
    end: str
    end_code: str
    direction: list[str] = field(default_factory=list)  # instructions GPS

    @classmethod
    def from_dict(cls, d: dict) -> ParcoursGD:
        return cls(
            id=d.get("id", 0),
            name=d.get("name", ""),
            start=d.get("start", ""),
            start_code=d.get("start_code", ""),
            end=d.get("end", ""),
            end_code=d.get("end_code", ""),
            direction=list(d.get("direction") or []),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "start": self.start, "start_code": self.start_code,
            "end": self.end, "end_code": self.end_code,
            "direction": self.direction,
        }


@dataclass
class RouteGD:
    """Une route dans un fichier G-D (direction capitalisée, ex. 'Est')."""
    line_number: str
    direction: str   # capitalisée : "Est", "Ouest", "Nord", "Sud"
    parcours: list[ParcoursGD] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> RouteGD:
        return cls(
            line_number=d.get("line_number", ""),
            direction=d.get("direction", ""),
            parcours=[ParcoursGD.from_dict(p) for p in d.get("parcours", [])],
        )

    def to_dict(self) -> dict:
        return {
            "line_number": self.line_number,
            "direction": self.direction,
            "parcours": [p.to_dict() for p in self.parcours],
        }


@dataclass
class FichierGD:
    """Contenu d'un fichier data/Gauche-Droite/gd<ligne>_<direction>.json.

    direction à la racine est en minuscule ('est') ;
    RouteGD.direction est en majuscule initiale ('Est').
    """
    ligne: str
    direction: str   # minuscule : "est", "ouest", "nord", "sud"
    routes: list[RouteGD] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> FichierGD:
        return cls(
            ligne=d.get("ligne", ""),
            direction=d.get("direction", ""),
            routes=[RouteGD.from_dict(r) for r in d.get("routes", [])],
        )

    def to_dict(self) -> dict:
        return {
            "ligne": self.ligne,
            "direction": self.direction,
            "routes": [r.to_dict() for r in self.routes],
        }
