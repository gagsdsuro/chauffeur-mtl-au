"""Présentation Streamlit du résumé calculé par chauffeur.durees."""
from __future__ import annotations

from html import escape

import streamlit as st

from chauffeur.durees import LigneDuree, ResumeDurees


TYPES_SEGMENTS = ("ligne", "prise", "hlp", "fin", "pause", "entrée", "sortie")


def rendre_table_durees_html(lignes: list[LigneDuree]) -> str:
    """Rend les lignes déjà calculées ; échappe toutes les valeurs affichées."""
    def cellule(valeur, classe="", titre=""):
        texte = "—" if valeur is None else str(valeur)
        return f'<td class="{classe}" title="{titre}">{escape(texte)}</td>'

    contenu = []
    for ligne in lignes:
        classes = []
        if ligne.type_segment != "ligne":
            classes.append("durees-special")
        if ligne.type_segment in ("prise", "pause", "fin"):
            classes.append("durees-repere")
        classe_battement = "durees-nombre"
        if ligne.battement_maximal:
            classe_battement += " durees-max"
        contenu.append(
            f'<tr class="{" ".join(classes)}" data-piece="{ligne.index_piece}" '
            f'data-type="{escape(ligne.type_segment, quote=True)}">'
            + cellule(ligne.heure, "durees-heure")
            + cellule(ligne.segment)
            + cellule(ligne.direction)
            + cellule(ligne.duree, "durees-nombre")
            + cellule(ligne.battement, classe_battement,
                      "Battement maximal de la pièce" if ligne.battement_maximal else "")
            + cellule(ligne.duree_totale, "durees-nombre")
            + "</tr>"
        )
    return """<style>
.durees-wrap{overflow-x:auto;width:100%;margin:.25rem 0 1rem}
.durees-table{border-collapse:collapse;width:100%;min-width:510px;font-size:.9rem}
.durees-table th,.durees-table td{border:1px solid #8886;padding:.35rem .6rem}
.durees-table th{text-align:left;white-space:nowrap}
.durees-table .durees-nombre{text-align:right;font-variant-numeric:tabular-nums}
.durees-table .durees-heure{white-space:nowrap;font-variant-numeric:tabular-nums}
.durees-special{font-weight:700}
.durees-repere{font-style:italic}
.durees-table .durees-max{background:#ffe082;color:#332600;font-weight:700}
</style><div class="durees-wrap"><table class="durees-table" aria-label="Résumé des durées">
<thead><tr><th scope="col">Heure</th><th scope="col">Segm.</th><th scope="col">Dir.</th>
<th scope="col" class="durees-nombre">Durée (m)</th>
<th scope="col" class="durees-nombre">Bat. (m)</th>
<th scope="col" class="durees-nombre">Durée t. (m)</th></tr></thead><tbody>""" + "".join(contenu) + "</tbody></table></div>"


def afficher_resume_durees(resume: ResumeDurees) -> None:
    with st.expander("Résumé des durées", expanded=False):
        if resume.anomalies:
            pieces = dict.fromkeys(
                f"{a.index_piece + 1} ({a.id_piece})" for a in resume.anomalies
            )
            st.warning(
                "Horaires incomplets ou incohérents — pièces : " + ", ".join(pieces)
                + ". Les valeurs incalculables sont indiquées par « — »."
            )
        if not resume.lignes:
            st.info("Aucune pièce de travail à résumer.")
            return
        options = list(dict.fromkeys([
            *TYPES_SEGMENTS, *(l.type_segment for l in resume.lignes),
        ]))
        selection = st.multiselect(
            "Types de segments", options, default=options, key="db_durees_types",
        )
        if not selection:
            st.info("Aucun type de segment sélectionné.")
            return
        lignes = [l for l in resume.lignes if l.type_segment in selection]
        if not lignes:
            st.info("Aucun segment ne correspond aux types sélectionnés.")
            return
        st.markdown(rendre_table_durees_html(lignes), unsafe_allow_html=True)
