"""Aperçu isolé des rapports conçus pour une palette claire."""
import streamlit as st


def afficher_rapport_html(contenu: str, *, height: int = 600):
    # Couvre également les anciens rapports au fond transparent, sans toucher
    # au document enregistré ni au thème du reste de l'application.
    palette = "<style>html,body{color-scheme:light;background:#fff;color:#1A1A2E}</style>"
    st.iframe(contenu + palette, height=height)
