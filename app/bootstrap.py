"""Initialisation des chemins d'import et constantes de répertoires.

À importer EN PREMIER dans chaque page Streamlit (avant tout import de
`chauffeur.*`, `scripts.*` ou `gen_rapport_v2`) : ce module insère dans
``sys.path`` la racine du projet, le dossier des scripts et le dossier app,
puis réexpose les répertoires canoniques définis par ``chauffeur.depots``
(source unique).

Dans l'app, le matricule de la session (authentifié par PIN) prime sur
l'environnement : ``initialiser_page()`` (appeler en tête de page) applique
ce contexte au thread courant, puis les accesseurs ``journees_dir()``,
``rapports_dir()``, … résolvent les répertoires privés selon la session.
"""
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
APP_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(APP_DIR))

import chauffeur.depots as _depots  # noqa: E402
from chauffeur.depots import (  # noqa: E402
    DATA_DIR, GD_DIR, EVENTS_DIR, JOURNEES_DIR, CA_DIR, NOTES_DIR,
    RAPPORTS_DIR, LOG_DIR, LOG_DIR_COMMUN, SESSION_DIR, SESSION_PATH,
    GTFS_DIR, GTFS_MANIFEST,
)


# ── Connexion et contexte de session ──────────────────────────────────────────

def _matricule_session() -> str | None:
    return st.session_state.get("auth_matricule")


def _appliquer_matricule_session() -> None:
    """Applique (ou efface) le contexte de matricule de la session au thread."""
    matricule = _matricule_session()
    if matricule:
        _depots.definir_matricule_contexte(matricule)
    else:
        _depots.effacer_matricule_contexte()


def initialiser_page() -> None:
    """Appelé en tête de chaque page : verrouillage + contexte matricule.

    Affiche le formulaire de connexion quand l'authentification est configurée
    (ou la création du premier compte en mode strict), puis applique le
    matricule authentifié au thread courant pour que tous les répertoires
    privés suivent la session.
    """
    from app.components.connexion import afficher_statut_connexion, exiger_connexion

    exiger_connexion()
    _appliquer_matricule_session()
    afficher_statut_connexion()


# ── Répertoires privés de la session (contexte actif) ─────────────────────────

def repertoire_prive(sous_dossier: str) -> Path:
    """data/<matricule de session>/<sous_dossier> (ou data/<dossier> legacy)."""
    return _depots.repertoire_prive(sous_dossier)


def journees_dir() -> Path:
    return repertoire_prive("journees")


def ca_dir() -> Path:
    return repertoire_prive("ca")


def notes_dir() -> Path:
    return repertoire_prive("notes")


def rapports_dir() -> Path:
    return repertoire_prive("rapports")


def log_dir() -> Path:
    return repertoire_prive("log")


def session_dir() -> Path:
    return repertoire_prive("session")


def session_path() -> Path:
    return session_dir() / "cookies.json"