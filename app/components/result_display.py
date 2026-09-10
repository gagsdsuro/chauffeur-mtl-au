"""Affichage des résultats de rafraîchissement (événements et G-D)."""
from __future__ import annotations

import streamlit as st

from chauffeur.preparation import ResultatRafraichissement, ResultatRafraichissementGD
from chauffeur.presentation_evenements import (
    presenter_evenement,
    rendre_table_evenements_html,
)


def _afficher_resultat_rafraichissement(resultat: ResultatRafraichissement) -> None:
    for ligne in resultat.lignes:
        icone = "✅" if ligne.succes else "❌"
        changement = " — modifié" if ligne.modifie else ""
        st.write(f"{icone} {ligne.ligne} {ligne.direction}{changement}")
        for detail in ligne.changements:
            st.caption(f"• {detail}")
        if ligne.evenements_retires:
            with st.expander(
                f"Évènements retirés — {ligne.ligne} {ligne.direction.capitalize()}",
                expanded=True,
            ):
                st.markdown(
                    rendre_table_evenements_html([
                        presenter_evenement(event)
                        for event in ligne.evenements_retires
                    ]),
                    unsafe_allow_html=True,
                )
        for modification in ligne.evenements_modifies:
            identifiant = modification.get("evenement_id", "?")
            with st.expander(
                f"Évènement modifié #{identifiant} — avant / après",
                expanded=True,
            ):
                st.markdown("**Avant**")
                st.markdown(
                    rendre_table_evenements_html([
                        presenter_evenement(event)
                        for event in modification.get("avant", [])
                    ]),
                    unsafe_allow_html=True,
                )
                st.markdown("**Après**")
                st.markdown(
                    rendre_table_evenements_html([
                        presenter_evenement(event)
                        for event in modification.get("apres", [])
                    ]),
                    unsafe_allow_html=True,
                )
        if not ligne.succes and ligne.message:
            st.caption(ligne.message)


def _afficher_resultat_gd(resultat: ResultatRafraichissementGD) -> None:
    for ligne in resultat.lignes:
        icone = "✅" if ligne.succes else "❌"
        etat = "modifié" if ligne.modifie else "vérifié"
        st.write(f"{icone} {ligne.ligne} {ligne.direction} — {etat}")
        if not ligne.succes and ligne.message:
            st.caption(ligne.message)