"""Notes libres sur autobus, matricules, cartes agent et journées
(NOTES_DIR/voiture.json, matricule.json, carte_agent.json, journee.json).

Fichiers indexés par clé (numéro d'autobus, matricule, identité de carte
agent ou date ISO de journée) -> {"note": str, "maj": "YYYY-MM-DD"}
(+ "nom" pour les matricules). Édités manuellement ou via la page
Ma journée de l'app.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import depots
from .depots import NOTES_DIR


def _notes_dir() -> Path:
    """Répertoire des notes : session (thread) si active, sinon la constante.

    Dans l'app, le matricule de session prime (par chauffeur) ; en CLI et dans
    les tests (où NOTES_DIR est patchable), la constante du module s'applique.
    """
    return depots.repertoire_prive_contexte("notes") or NOTES_DIR


def _path(nom_fichier: str, notes_dir: Path | None = None) -> Path:
    return (notes_dir or _notes_dir()) / f"{nom_fichier}.json"


def _charger(nom_fichier: str, notes_dir: Path | None = None) -> dict:
    p = _path(nom_fichier, notes_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sauvegarder(nom_fichier: str, notes: dict, notes_dir: Path | None = None) -> None:
    notes_dir = notes_dir or _notes_dir()
    notes_dir.mkdir(parents=True, exist_ok=True)
    _path(nom_fichier, notes_dir).write_text(
        json.dumps(notes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def note_voiture(numero_autobus: str) -> dict | None:
    return _charger("voiture").get(numero_autobus)


def note_matricule(matricule: str) -> dict | None:
    return _charger("matricule").get(matricule)


def sauvegarder_note_voiture(numero_autobus: str, texte: str) -> None:
    """Écrit (ou retire si texte vide) la note du bus `numero_autobus`."""
    notes = _charger("voiture")
    texte = texte.strip()
    if texte:
        notes[numero_autobus] = {"note": texte, "maj": date.today().isoformat()}
    else:
        notes.pop(numero_autobus, None)
    _sauvegarder("voiture", notes)


def sauvegarder_note_matricule(matricule: str, texte: str, nom: str | None = None) -> None:
    """Écrit (ou retire si texte vide) la note du matricule `matricule`."""
    notes = _charger("matricule")
    texte = texte.strip()
    if texte:
        notes[matricule] = {
            "nom": nom or notes.get(matricule, {}).get("nom"),
            "note": texte,
            "maj": date.today().isoformat(),
        }
    else:
        notes.pop(matricule, None)
    _sauvegarder("matricule", notes)


def note_carte(cle: str) -> dict | None:
    """Note de la carte agent `cle` (clé produite par chauffeur.ca.cle_note_carte)."""
    return _charger("carte_agent").get(cle)


def sauvegarder_note_carte(cle: str, texte: str) -> None:
    """Écrit (ou retire si texte vide) la note de la carte agent `cle`.

    La clé est l'identité de la carte (numero_groupe_id_jour_type) : la note
    suit la carte réutilisée d'une journée à l'autre — listes, variations et
    fériés donnant des identités distinctes (cf. chauffeur.periodes.identite_ca).
    """
    notes = _charger("carte_agent")
    texte = texte.strip()
    if texte:
        notes[cle] = {"note": texte, "maj": date.today().isoformat()}
    else:
        notes.pop(cle, None)
    _sauvegarder("carte_agent", notes)


def note_journee(date_str: str) -> dict | None:
    """Note de la journée `date_str` (date ISO), propre à cette date."""
    return _charger("journee").get(date_str)


def sauvegarder_note_journee(date_str: str, texte: str) -> None:
    """Écrit (ou retire si texte vide) la note de la journée `date_str`."""
    notes = _charger("journee")
    texte = texte.strip()
    if texte:
        notes[date_str] = {"note": texte, "maj": date.today().isoformat()}
    else:
        notes.pop(date_str, None)
    _sauvegarder("journee", notes)
