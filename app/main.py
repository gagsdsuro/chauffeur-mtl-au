# -*- coding: utf-8 -*-
"""Point d'entrée Streamlit — Chauffeur Mtl-AU.

Lancement : ``streamlit run app/main.py``

Le fichier ``.env`` de la racine du projet est chargé avant tout import métier
(Streamlit ne le lit pas lui-même ; les clés déjà présentes dans l'environnement
du process l'emportent). Seule l'app charge ``.env`` — les scripts et les tests
restent hermétiques et lisent uniquement l'environnement réel.

La navigation (`st.navigation`) expose les pages de ``app/pages/`` dans la
barre latérale ; l'entrée « Administration » n'apparaît que pour un
Chauffeur-admin. La connexion et le contexte matricule sont appliqués en tête
de chaque page par ``bootstrap.initialiser_page()``. Ce fichier ne contient
aucune logique métier — uniquement la configuration globale et le style.
"""
import os
from pathlib import Path


def _charger_env() -> None:
    """Charge `KEY=VALUE` du `.env` racine (aucune dépendance).

    Lignes vides ou commentées (#) ignorées ; `export ` optionnel accepté ;
    guillemets simples/doubles retirés. Une clé déjà présente dans l'environnement
    du process n'est jamais écrasée.
    """
    chemin = Path(__file__).resolve().parent.parent / ".env"
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        if ligne.startswith("export "):
            ligne = ligne[len("export "):]
        if "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        cle = cle.strip()
        valeur = valeur.strip()
        if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "'\"":
            valeur = valeur[1:-1]
        if cle and cle not in os.environ:
            os.environ[cle] = valeur


_charger_env()

import bootstrap  # noqa: F401  (configure sys.path avant tout import)

import streamlit as st

from app.components.connexion import est_admin
from chauffeur.avis import ATTRIBUTION, AVIS_INFORMATION, AVIS_PORTAIL

st.set_page_config(
    page_title="Chauffeur Mtl-AU",
    page_icon="🚌",
    layout="wide",
)

st.markdown(
    """
    <style>
    /* Réduire les marges supérieure et latérales */
    .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 2rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
    }
    /* Compresser le bandeau d'en-tête Streamlit */
    [data-testid="stHeader"],
    header[data-testid="stHeader"] {
        height: 2.25rem !important;
        min-height: 2.25rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🚌 Chauffeur Mtl-AU")

_pages = [
    st.Page("pages/1_ma_journee.py", title="Ma journée"),
    st.Page("pages/2_preparation.py", title="Préparation d'une journée"),
    st.Page("pages/3_rapports.py", title="Rapports"),
    st.Page("pages/4_fichiers.py", title="Fichiers"),
    st.Page("pages/5_logs.py", title="Logs"),
    st.Page("pages/7_appariement.py", title="Appariement des arrêts"),
    st.Page("pages/8_detours.py", title="Appariement des détours"),
]
if est_admin():
    _pages.append(st.Page("pages/6_administration.py", title="Administration"))

with st.sidebar.expander("ℹ️ Avis et sources", expanded=False):
    st.caption(f"{AVIS_INFORMATION}\n\n{AVIS_PORTAIL}\n\n{ATTRIBUTION}")

st.navigation(_pages).run()