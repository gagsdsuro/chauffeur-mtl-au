"""chauffeur.calendrier — fichiers iCalendar (.ics), un par pièce de travail.

Un .ics par pièce : début → fin de la pièce, titre « <pièce> · Lignes <lignes> »,
détails (prise, autobus, relève) en description. Importable tel quel dans un
calendrier (Google, Apple, Outlook, Proton…).

Heures écrites en heure locale **flottante** (sans fuseau) : le calendrier les
lit dans son propre fuseau (Montréal). L'image Docker slim n'a pas de base
tzdata, donc pas de conversion vers un fuseau nommé. Une fin au-delà de 24 h
(« 25:11 ») tombe le lendemain.

UID stable par (date, rang de la pièce, id) : réimporter le fichier met
l'évènement à jour au lieu de le dupliquer.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
import re
import tempfile

from .journee import _as_dict

PRODID = "-//chauffeur-mtl-au//Pieces de travail//FR"
_HEURE_RE = re.compile(r"^(\d{1,2}):([0-5]\d)$")
_LIMITE_OCTETS = 75


def _heure_vers_dt(jour: date, heure: str | None) -> datetime | None:
    """« 13:45 » → ce jour à 13:45 ; « 25:11 » → le lendemain à 01:11 ; invalide → None."""
    m = _HEURE_RE.match((heure or "").strip())
    if not m:
        return None
    return datetime.combine(jour, time()) + timedelta(hours=int(m[1]), minutes=int(m[2]))


def lignes_de_piece(piece: dict) -> list[str]:
    """Lignes des trajets de service, dans l'ordre de passage, sans doublon."""
    vues: list[str] = []
    for trajet in piece.get("trajets") or []:
        ligne = trajet.get("ligne")
        if trajet.get("type") == "service" and ligne and ligne not in vues:
            vues.append(str(ligne))
    return vues


def _titre(piece: dict) -> str:
    lignes = lignes_de_piece(piece)
    if not lignes:
        return str(piece.get("id") or "Pièce")
    return f"{piece.get('id')} · Lignes {', '.join(lignes)}"


def _personne(p: dict | None) -> str:
    if not p:
        return ""
    nom, mat = (p.get("nom") or "").strip(), (p.get("matricule") or "").strip()
    return f"{nom} ({mat})" if nom and mat else nom or mat


def _description(piece: dict) -> str:
    def lieu(heure, endroit):
        return " ".join(x for x in (heure, f"({endroit})" if endroit else "") if x)

    lignes = [f"Pièce {piece.get('id')}"]
    if piece.get("prise"):
        lignes.append("Prise : " + lieu(piece["prise"], piece.get("lieu_prise")))
    lignes.append("Fin : " + lieu(piece.get("fin"), piece.get("lieu_fin")))
    if piece.get("numero_autobus"):
        lignes.append(f"Autobus : {piece['numero_autobus']}")
    releve = piece.get("releve") or {}
    for cle, libelle in (("je_releve", "Je relève"), ("je_suis_releve_par", "Relevé par")):
        qui = _personne(releve.get(cle))
        if qui:
            lignes.append(f"{libelle} : {qui}")
    par_ligne: dict[str, list[str]] = {}
    for t in piece.get("trajets") or []:
        if t.get("type") == "service" and t.get("ligne"):
            sens = par_ligne.setdefault(str(t["ligne"]), [])
            if t.get("direction") and t["direction"] not in sens:
                sens.append(t["direction"])
    if par_ligne:
        lignes.append("Lignes : " + " · ".join(
            f"{ligne} {'/'.join(sens)}".strip() for ligne, sens in par_ligne.items()
        ))
    return "\n".join(lignes)


def _assainir(texte: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", texte).strip("_") or "piece"


def evenements_ics(journee) -> list[dict]:
    """Une entrée par pièce de travail datée ; absences et pièces sans heures ignorées."""
    d = _as_dict(journee)
    try:
        jour = date.fromisoformat(str(d.get("date")))
    except ValueError:
        return []
    evenements = []
    for rang, piece in enumerate(d.get("pieces") or [], start=1):
        if piece.get("type_horaire") == "absence":
            continue
        debut = _heure_vers_dt(jour, piece.get("debut"))
        fin = _heure_vers_dt(jour, piece.get("fin"))
        if debut is None or fin is None or fin <= debut:
            continue
        evenements.append({
            "piece_id": piece.get("id"),
            "rang": rang,
            "nom_fichier": f"{rang:02d}-{_assainir(str(piece.get('id')))}.ics",
            # UID historique conservé tel quel : le changer dupliquerait dans les
            # calendriers déjà alimentés les évènements réimportés.
            "uid": f"chauffeur-stm-{jour.isoformat()}-{rang}-{_assainir(str(piece.get('id')))}@chauffeur-stm",
            "titre": _titre(piece),
            "debut": debut,
            "fin": fin,
            "lieu": piece.get("lieu_prise") or "",
            "description": _description(piece),
        })
    return evenements


def _echapper(texte: str) -> str:
    return (texte.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\n").replace("\n", "\\n"))


def _plier(ligne: str) -> list[str]:
    """Plie à 75 octets UTF-8 (continuations préfixées d'une espace), sans couper un caractère."""
    morceaux, courant, taille = [], "", 0
    for car in ligne:
        n = len(car.encode("utf-8"))
        limite = _LIMITE_OCTETS if not morceaux else _LIMITE_OCTETS - 1
        if taille + n > limite:
            morceaux.append(courant)
            courant, taille = "", 0
        courant += car
        taille += n
    morceaux.append(courant)
    return [morceaux[0]] + [" " + m for m in morceaux[1:]]


def rendre_ics(evenement: dict, *, maintenant: datetime | None = None) -> str:
    """VCALENDAR (un VEVENT), fins de ligne CRLF."""
    stamp = (maintenant or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    fmt = "%Y%m%dT%H%M%S"
    proprietes = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{evenement['uid']}",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{evenement['debut'].strftime(fmt)}",
        f"DTEND:{evenement['fin'].strftime(fmt)}",
        f"SUMMARY:{_echapper(evenement['titre'])}",
    ]
    if evenement.get("lieu"):
        proprietes.append(f"LOCATION:{_echapper(evenement['lieu'])}")
    proprietes += [
        f"DESCRIPTION:{_echapper(evenement['description'])}",
        "SEQUENCE:0", "TRANSP:OPAQUE", "END:VEVENT", "END:VCALENDAR",
    ]
    return "".join(f"{p}\r\n" for ligne in proprietes for p in _plier(ligne))


def dossier_calendrier(chemin_journee: Path) -> Path:
    """`calendrier/` voisin de `journees/` ; dossier quelconque (tests) → sous-dossier."""
    parent = Path(chemin_journee).parent
    return (parent.parent if parent.name == "journees" else parent) / "calendrier"


def _ecrire_atomique(chemin: Path, contenu: str) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ics-", suffix=".tmp", dir=chemin.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenu.encode("utf-8"))
        os.replace(tmp, chemin)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def ecrire_calendrier(journee, dossier: Path, *, maintenant: datetime | None = None) -> list[Path]:
    """Écrit `<dossier>/<date>/<rang>-<id>.ics` ; retire les .ics devenus obsolètes."""
    d = _as_dict(journee)
    cible = Path(dossier) / str(d.get("date"))
    ecrits = []
    for ev in evenements_ics(d):
        chemin = cible / ev["nom_fichier"]
        _ecrire_atomique(chemin, rendre_ics(ev, maintenant=maintenant))
        ecrits.append(chemin)
    if cible.is_dir():
        for ancien in cible.glob("*.ics"):
            if ancien not in ecrits:
                ancien.unlink()
    return ecrits


def ecrire_calendrier_sans_echec(journee, dossier: Path) -> tuple[list[Path], str]:
    """Comme `ecrire_calendrier`, mais ne fait jamais échouer un import : (chemins, erreur)."""
    try:
        return ecrire_calendrier(journee, dossier), ""
    except Exception as exc:  # noqa: BLE001 — l'import de la journée prime
        return [], f"{type(exc).__name__}: {exc}"


def lignes_calendrier(chemins: list[Path], erreur: str = "") -> list[str]:
    """Lignes du rapport d'import : fichiers .ics produits, ou avertissement."""
    if erreur:
        return [f"⚠️ Calendrier (.ics) non généré : {erreur}"]
    if not chemins:
        return ["📅 Aucun .ics (aucune pièce de travail avec heures)"]
    return [f"📅 {len(chemins)} fichier(s) .ics → {chemins[0].parent}"]
