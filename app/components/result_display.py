"""Affichage des résultats de rafraîchissement (événements et G-D)."""
from __future__ import annotations

import streamlit as st

from chauffeur.preparation import ResultatRafraichissement, ResultatRafraichissementGD
from chauffeur.preparation_auto import ETAPES, LIBELLES, ResultatEtape, ResultatSemiAuto
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


_ICONES_ETAPE = {
    "ok": ":green[:material/check_circle:]",
    "ignore": ":gray[:material/skip_next:]",
    "avertissement": ":orange[:material/warning:]",
    "bloque": ":red[:material/error:]",
    "session_expiree": ":orange[:material/lock_clock:]",
}


def ligne_etape_semi_auto(etape: ResultatEtape) -> str:
    """Ligne markdown d'une étape : icône, libellé, message."""
    icone = _ICONES_ETAPE.get(etape.statut, ":material/circle:")
    message = f" — {etape.message}" if etape.message else ""
    return f"{icone} **{LIBELLES.get(etape.etape, etape.etape)}**{message}"


def _afficher_bilan_semi_auto(resultat: ResultatSemiAuto) -> None:
    """Étapes exécutées (avec leurs détails), puis étapes restant à faire."""
    for etape in resultat.etapes:
        st.markdown(ligne_etape_semi_auto(etape))
        for detail in etape.details:
            st.caption(f"• {detail}")
    if resultat.reprise_a:
        restantes = ETAPES[ETAPES.index(resultat.reprise_a) + 1:]
        for nom in restantes:
            st.markdown(f":gray[:material/radio_button_unchecked:] {LIBELLES[nom]}")


def progression_semi_auto(statut_widget):
    """Rappel de progression pour `executer_semi_auto` : titre du `st.status` + une ligne par étape."""
    def _rappel(etape: str, statut: str, message: str) -> None:
        if statut == "demarre":
            statut_widget.update(label=f"{message}…")
        else:
            st.markdown(ligne_etape_semi_auto(ResultatEtape(etape, statut, message)))
    return _rappel
