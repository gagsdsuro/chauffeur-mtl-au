"""Renouvellement de la session portail employé et reprise automatique.

Partagé par les pages « Ma journée » et « Préparation d'une journée » :
toute opération portail interrompue par une session expirée enregistre son
état (`operation_portail`), puis le dialogue s'ouvre pour saisir un nouveau
cookie. Après validation, l'opération reprend au prochain rerun.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.state import (
    OPERATION_PORTAIL,
    OUVRIR_DIALOG_SESSION,
    SESSION_COOKIE_DIALOG,
)
from chauffeur.avis import AVIS_PORTAIL
from chauffeur.portail import valider_et_sauvegarder_session


def demander_renouvellement(operation: dict) -> None:
    """Marque l'opération `operation` à reprendre et demande le dialogue."""
    st.session_state[OPERATION_PORTAIL] = operation
    st.session_state[OUVRIR_DIALOG_SESSION] = True


@st.dialog("Renouveler la session du portail employé")
def _dialog_session_portail(chemin_session: Path) -> None:
    st.caption(
        "Reconnectez-vous sur employe.stm.info, puis copiez la valeur complète "
        "de l'en-tête `cookie` depuis les outils réseau du navigateur."
    )
    st.caption(AVIS_PORTAIL)
    cookie = st.text_input(
        "Cookie",
        type="password",
        key=SESSION_COOKIE_DIALOG,
        placeholder="TS01846…; laravel_session=…",
    )
    c1, c2 = st.columns(2)
    if c1.button("Valider et reprendre", type="primary", width="stretch"):
        if not cookie.strip():
            st.warning("Le champ est vide.")
        else:
            with st.spinner("Validation de la session…"):
                ok, message = valider_et_sauvegarder_session(
                    cookie.strip(), session_path=chemin_session
                )
            if ok:
                st.session_state.pop(SESSION_COOKIE_DIALOG, None)
                pending = st.session_state.get(OPERATION_PORTAIL)
                if pending:
                    pending["reprendre"] = True
                st.session_state[OUVRIR_DIALOG_SESSION] = False
                st.rerun()
            else:
                st.error(message)
    if c2.button("Annuler", width="stretch"):
        st.session_state.pop(OPERATION_PORTAIL, None)
        st.session_state[OUVRIR_DIALOG_SESSION] = False
        st.rerun()


def declencher_dialog_si_requis() -> None:
    """À appeler en fin de page : ouvre le dialogue si un renouvellement attend."""
    if st.session_state.get(OUVRIR_DIALOG_SESSION):
        # Résoudre pendant l'exécution de la page authentifiée. Le dialogue
        # conserve ses arguments lors des reruns partiels, qui peuvent utiliser
        # un autre thread sans le contexte matricule initialisé par la page.
        from chauffeur.depots import repertoire_prive

        _dialog_session_portail(repertoire_prive("session") / "cookies.json")
