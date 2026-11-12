"""Constantes et helpers pour ``st.session_state``.

Le ``session_state`` est partagé entre les pages d'une même session
navigateur. Ce module est la source unique des clés transverses (celles
lues ou écrites par plus d'une page) ; les clés locales à une page
(widgets dynamiques « {date}/{index} ») restent dans la page concernée.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

# ── Clés transverses partagées entre pages ─────────────────────────────────────
JOURNEE_DATE = "journee_date"             # journée sélectionnée dans « Ma journée »
PREP_DATE = "prep_date"                   # « Préparation d'une journée »
PREP_FLASH = "prep_flash"                 # message éphémère affiché au rerun (page 2)
PREP_SEMI_AUTO = "prep_semi_auto"         # bilan de la préparation semi-automatique (page 2)
OPERATION_PORTAIL = "operation_portail"   # reprise après expiration de session (pages 1 et 2)
OUVRIR_DIALOG_SESSION = "ouvrir_dialog_session"
SESSION_COOKIE_DIALOG = "session_cookie_dialog"

# ── Authentification ──────────────────────────────────────────────────────────
AUTH_MATRICULE = "auth_matricule"         # matricule authentifié de la session
AUTH_ROLE = "auth_role"                   # « Chauffeur » | « Chauffeur-admin »
AUTH_NOM = "auth_nom"                     # nom libre du compte (informatif)

# ── Clés locales à la page « Ma journée » ──────────────────────────────────────
DB_REFRESH_RESULT = "db_refresh_result"
DB_REFRESH_REPORT = "db_refresh_report"
DB_REFRESH_DATE = "db_refresh_date"       # journée à laquelle ces résultats appartiennent

# ── Helpers opération portail ──────────────────────────────────────────────────

def operation_portail() -> dict[str, Any] | None:
    """État d'une opération portail en cours (ou None)."""
    return st.session_state.get(OPERATION_PORTAIL)


def mettre_a_jour_operation_portail(operation: dict[str, Any]) -> None:
    """Enregistre l'opération portail en cours (reprise possible)."""
    st.session_state[OPERATION_PORTAIL] = operation


def effacer_operation_portail() -> None:
    """Annule l'opération portail en cours."""
    st.session_state.pop(OPERATION_PORTAIL, None)


def reprise_en_attente(type_operation: str, date_iso: str) -> dict[str, Any] | None:
    """L'opération portail à reprendre (type et date correspondants), sinon None."""
    operation = operation_portail()
    if (
        operation
        and operation.get("type") == type_operation
        and operation.get("date") == date_iso
        and operation.get("reprendre")
    ):
        return operation
    return None
