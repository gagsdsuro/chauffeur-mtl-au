"""Inventaire, édition et export des fichiers autorisés de l'utilisateur courant."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import threading
from uuid import uuid4

from . import auth, depots
from .periodes import periode_pour_date, regime_pour_date, jour_type_semaine

CATEGORIES = {"ca": "Cartes agent", "gd": "Gauche-Droite", "ev": "Événements",
              "rp": "Rapports", "journee": "Journées"}
REGIMES = {"normal": "Régime normal", "variation": "Semaine de variation",
           "ferie": "Férié", "indetermine": "Indéterminé"}
COLONNES_CSV = ["date", "garage_id", "journee_numero", "piece_id", "type_horaire"] + [
    f"trajet{i}_ligne" for i in range(1, 8)]
_VERROU = threading.RLock()


@dataclass(frozen=True)
class Fichier:
    nom: str
    categorie: str
    taille: int
    modification: float
    date: date | None = None
    periode: str = "?"
    regime: str = "indetermine"
    jour_type: str = ""
    numero: str = ""
    ligne: str = ""
    direction: str = ""
    annotee: bool = False


def repertoire(categorie: str) -> Path:
    if categorie == "gd":
        return depots.GD_DIR
    if categorie == "ev":
        return depots.EVENTS_DIR
    return depots.repertoire_prive({"ca": "ca", "rp": "rapports", "journee": "journees"}[categorie])


def _nom_admis(categorie: str, nom: str) -> bool:
    if Path(nom).name != nom or nom in (".", ".."):
        return False
    return bool({
        "ca": re.fullmatch(r".+\.pdf", nom),
        "gd": re.fullmatch(r"gd.+\.json", nom),
        "ev": re.fullmatch(r".+\.json", nom),
        "rp": re.fullmatch(r"rapport-.+\.(pdf|html)", nom),
        "journee": re.fullmatch(r"journee-.+\.json", nom),
    }[categorie])


def chemin(categorie: str, nom: str) -> Path:
    racine = repertoire(categorie).resolve()
    p = racine / nom
    if not _nom_admis(categorie, nom) or p.is_symlink() or p.resolve().parent != racine:
        raise ValueError("Chemin de fichier non autorisé.")
    return p


def peut_modifier(categorie: str) -> bool:
    matricule = depots.matricule_contexte()
    if categorie in ("gd", "ev"):
        return bool(matricule and auth.role(matricule) == auth.ROLE_ADMIN)
    # Aucune mutation legacy lorsque des comptes existent sans session authentifiée.
    if auth.comptes_configure():
        return bool(matricule and auth.role(matricule) in auth.ROLES)
    return True


def _autoriser(categorie: str, nom: str) -> Path:
    if not peut_modifier(categorie):
        raise PermissionError("Vous n'avez pas le droit de modifier ces fichiers.")
    return chemin(categorie, nom)


def decrire(categorie: str, nom: str, taille=0, modification=0, reference_dir=None) -> Fichier:
    valeurs = dict(nom=nom, categorie=categorie, taille=taille, modification=modification)
    jour = None
    regime = None
    if categorie == "journee":
        m = re.fullmatch(r"journee-(\d{4}-\d{2}-\d{2})\.json", nom)
        date_texte = m[1] if m else None
    elif categorie == "ca":
        m = re.fullmatch(r"(\d+)_([LV]?)(\d{4}-\d{2}-\d{2})_(semaine|samedi|dimanche|variation)(-annotee)?\.pdf", nom)
        if m:
            valeurs.update(numero=m[1], jour_type=m[4], annotee=bool(m[5]))
            date_texte = m[3]
            regime = {"L": "normal", "V": "variation", "": "ferie"}[m[2]]
        else:
            m = re.fullmatch(r"carte-agent-(\d{4}-\d{2}-\d{2})(-annotee|-surligné)?\.pdf", nom)
            date_texte = m[1] if m else None
            valeurs["annotee"] = bool(m and m[2] in ("-annotee", "-surligné"))
    elif categorie == "rp":
        m = re.match(r"rapport-(?:v2-)?(\d{4}-\d{2}-\d{2})", nom)
        date_texte = m[1] if m else None
    else:
        m = re.fullmatch(r"(?:gd)?(\d+e?)_(est|ouest|nord|sud)\.json", nom)
        if m:
            valeurs.update(ligne=m[1], direction=m[2])
        date_texte = None
    if date_texte:
        try:
            jour = date.fromisoformat(date_texte)
        except ValueError:
            pass
    if jour:
        valeurs["date"] = jour
        if categorie in ("ca", "journee"):
            periode = periode_pour_date(jour, reference_dir)
            # Une identité L doit désigner un véritable début de liste.
            identite_liste = categorie == "ca" and re.match(r"\d+_L", nom)
            if periode and (not identite_liste or periode.debut == jour):
                valeurs["periode"] = periode.cle
            valeurs["regime"] = regime or regime_pour_date(jour, reference_dir)
            valeurs.setdefault("jour_type", jour_type_semaine(jour))
    return Fichier(**valeurs)


def inventorier(categorie: str) -> list[Fichier]:
    resultat = []
    dossier = repertoire(categorie)
    if dossier.exists():
        for p in dossier.iterdir():
            if not _nom_admis(categorie, p.name) or p.is_symlink() or not p.is_file():
                continue
            try:
                stat = p.stat()
                resultat.append(decrire(categorie, p.name, stat.st_size, stat.st_mtime))
            except FileNotFoundError:
                continue
    return resultat


def filtrer(fichiers: list[Fichier], *, recherche="", periode="*", regime="*",
            jour_type="*", version="*", ligne="*", direction="*", format="*",
            debut=None, fin=None, tri="Nom") -> list[Fichier]:
    resultat = [f for f in fichiers if
                recherche.casefold() in f.nom.casefold()
                and (periode == "*" or f.periode == periode)
                and (regime == "*" or f.regime == regime)
                and (jour_type == "*" or f.jour_type == jour_type)
                and (version == "*" or f.annotee == (version == "annotée"))
                and (ligne == "*" or f.ligne == ligne)
                and (direction == "*" or f.direction == direction)
                and (format == "*" or Path(f.nom).suffix == format)
                and (debut is None or f.date is not None and f.date >= debut)
                and (fin is None or f.date is not None and f.date <= fin)]
    if tri == "Date décroissante":
        return sorted(resultat, key=lambda f: (f.date or date.min, f.nom), reverse=True)
    if tri == "Modification récente":
        return sorted(resultat, key=lambda f: (f.modification, f.nom), reverse=True)
    if tri == "Ligne":
        return sorted(resultat, key=lambda f: (int(re.sub(r"\D", "", f.ligne) or 0), f.ligne, f.direction))
    return sorted(resultat, key=lambda f: f.nom.casefold())


def lire(categorie: str, nom: str) -> bytes:
    return chemin(categorie, nom).read_bytes()


def empreinte(contenu: bytes) -> str:
    return hashlib.sha256(contenu).hexdigest()


def _objets(valeur, nom):
    if not isinstance(valeur, list) or not all(isinstance(v, dict) for v in valeur):
        raise ValueError(f"{nom} doit être une liste d'objets.")
    return valeur


def valider_json(categorie: str, nom: str, texte: str) -> dict:
    if categorie not in ("journee", "gd", "ev"):
        raise ValueError("Ce format n'est pas éditable.")
    def refuser_constante(valeur):
        raise ValueError(f"Constante JSON invalide : {valeur}")
    contenu = json.loads(texte, parse_constant=refuser_constante)
    if not isinstance(contenu, dict):
        raise ValueError("La racine JSON doit être un objet.")
    info = decrire(categorie, nom)
    if categorie == "journee":
        if info.date is None or contenu.get("date") != info.date.isoformat():
            raise ValueError("La date doit correspondre au nom du fichier.")
        for piece in _objets(contenu.get("pieces"), "pieces"):
            for trajet in _objets(piece.get("trajets", []), "trajets"):
                for cle in ("depart", "arrivee"):
                    if cle in trajet and not isinstance(trajet[cle], dict):
                        raise ValueError(f"{cle} doit être un objet.")
    else:
        if not info.ligne or str(contenu.get("ligne")) != info.ligne or contenu.get("direction") != info.direction:
            raise ValueError("La ligne et la direction doivent correspondre au nom du fichier.")
        if categorie == "gd":
            for route in _objets(contenu.get("routes"), "routes"):
                if str(route.get("line_number")) != info.ligne or str(route.get("direction", "")).lower() != info.direction:
                    raise ValueError("L'identité d'une route ne correspond pas au fichier.")
                for parcours in _objets(route.get("parcours"), "parcours"):
                    directions = parcours.get("direction")
                    if not isinstance(directions, list) or not all(isinstance(d, str) for d in directions):
                        raise ValueError("Les instructions du parcours doivent être une liste de textes.")
        else:
            for evenement in _objets(contenu.get("detours"), "detours"):
                for cle in ("arrets_annules", "arrets_ajoutes"):
                    if cle in evenement:
                        _objets(evenement[cle], cle)
                description = evenement.get("description_gd", "")
                if description is not None and not isinstance(description, (str, list)):
                    raise ValueError("description_gd doit être un texte ou une liste.")
    return contenu


def enregistrer(categorie: str, nom: str, texte: str, attendu: str) -> Path:
    contenu = valider_json(categorie, nom, texte)
    with _VERROU:
        p = _autoriser(categorie, nom)
        ancien = p.read_bytes()
        if empreinte(ancien) != attendu:
            raise ValueError("Le fichier a changé. Votre brouillon est conservé ; rechargez la version actuelle.")
        sauvegarde = p.with_name(f"{p.name}.{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}-{uuid4().hex[:8]}.bak")
        with sauvegarde.open("xb") as sortie:
            sortie.write(ancien)
        # Revérifier après la sauvegarde pour détecter un import concurrent.
        if empreinte(p.read_bytes()) != attendu:
            raise ValueError("Le fichier a changé pendant l'enregistrement ; rechargez-le.")
        depots._sauvegarder_json_atomique(p, contenu)
        return sauvegarde


def supprimer(categorie: str, nom: str, attendu: str) -> None:
    with _VERROU:
        p = _autoriser(categorie, nom)
        if empreinte(p.read_bytes()) != attendu:
            raise ValueError("Le fichier a changé depuis la confirmation. Recommencez.")
        p.unlink()


def candidats_purge(fichiers: list[Fichier], jours: int) -> list[Fichier]:
    seuil = datetime.now().timestamp() - jours * 86400
    return [f for f in fichiers if f.modification < seuil]


def exporter_journees(debut: date, fin: date) -> tuple[list[dict], bytes, list[str]]:
    if debut > fin:
        raise ValueError("La date de début doit précéder la date de fin.")
    lignes, erreurs = [], []
    for f in sorted(inventorier("journee"), key=lambda f: f.nom, reverse=True):
        if not f.date or not debut <= f.date <= fin:
            continue
        try:
            jd = json.loads(lire("journee", f.nom))
            pieces = _objets(jd.get("pieces", []), "pieces")
            ajout = []
            for piece in pieces:
                services = [t.get("ligne") for t in _objets(piece.get("trajets", []), "trajets")
                            if t.get("type") == "service"]
                # Une occurrence par pièce, dans l'ordre de première apparition,
                # avant de limiter l'export aux sept colonnes historiques.
                services = list(dict.fromkeys(services))
                row = {"date": jd.get("date", ""), "garage_id": jd.get("garage_id", ""),
                       "journee_numero": jd.get("journee_numero", ""), "piece_id": piece.get("id", ""),
                       "type_horaire": piece.get("type_horaire", "horaire")}
                row.update({f"trajet{i+1}_ligne": services[i] if i < len(services) else "" for i in range(7)})
                ajout.append(row)
            lignes.extend(ajout)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            erreurs.append(f"{f.nom} : {exc}")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLONNES_CSV)
    writer.writeheader()
    writer.writerows(lignes)
    return lignes, buf.getvalue().encode("utf-8"), erreurs
