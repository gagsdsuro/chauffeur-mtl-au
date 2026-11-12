# -*- coding: utf-8 -*-
"""Explorateur des fichiers personnels et communs."""
import bootstrap

bootstrap.initialiser_page()

import streamlit as st
from app.components.file_manager import explorateur
from app.components.session_dialog import declencher_dialog_si_requis
from chauffeur.depots import matricule_effectif

st.header("Fichiers")
# État non lié aux widgets : persiste entre catégories/pages, isolé par compte.
stockage = f"fichiers_etat_{matricule_effectif() or 'legacy'}"
st.session_state.setdefault(stockage, {})
try:
    explorateur(stockage)
except (OSError, ValueError) as exc:
    st.error(f"Impossible de charger les fichiers : {exc}")
declencher_dialog_si_requis()
