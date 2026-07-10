#!/usr/bin/env python3
"""Notes libres sur autobus et matricules (data/notes/voiture.json, matricule.json).

Fichiers indexés par clé (numéro d'autobus ou matricule) -> {"note": str,
"maj": "YYYY-MM-DD"} (+ "nom" pour les matricules). Édités manuellement ou
via l'onglet Ma journée de l'app.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

NOTES_DIR = Path(__file__).resolve().parent.parent / "data" / "notes"


def _path(nom_fichier: str) -> Path:
    return NOTES_DIR / f"{nom_fichier}.json"


def _charger(nom_fichier: str) -> dict:
    p = _path(nom_fichier)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sauvegarder(nom_fichier: str, notes: dict) -> None:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    _path(nom_fichier).write_text(
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
