#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page — Logs (consultation des fichiers de journalisation).

Ancien onglet 5 de l'application monolithique (app/ui.py). Deux familles :
les journaux de la flotte (imports G-D/Événements/GTFS, communs à tous dans
`data/log/`) et les journaux personnels du compte (journée, carte agent,
dans `data/<matricule>/log/`).
"""
import bootstrap  # noqa: F401  (configure sys.path avant tout import)

bootstrap.initialiser_page()

import streamlit as st

from app.components.session_dialog import declencher_dialog_si_requis
from app.utils import _fmt_mtime, _fmt_size

from chauffeur.journal import lister_journaux_communs, lister_journaux_personnels

commun_dir = bootstrap.LOG_DIR_COMMUN
perso_dir = bootstrap.log_dir()

st.header("Logs")

journaux_communs = lister_journaux_communs()
journaux_personnels = lister_journaux_personnels()

entrees = []
vus = set()
for famille, repertoire, journaux in (
    ("Flotte", commun_dir, journaux_communs),
    ("Personnel", perso_dir, journaux_personnels),
):
    for p in journaux:
        if p in vus:
            continue
        vus.add(p)
        entrees.append((f"[{famille}] {p.name}", p))

if not entrees:
    st.info(
        f"Aucun fichier de log trouvé dans `{commun_dir}` (flotte) ni dans "
        f"`{perso_dir}` (personnel). Les imports faits depuis **Préparation "
        "d'une journée** y laissent leur trace ; en ligne de commande, les "
        "scripts journalisent avec l'option `--log`."
    )
else:
    log_labels = [label for label, _ in entrees]
    log_sel = st.selectbox(
        "Fichier de log",
        range(len(log_labels)),
        format_func=lambda i: log_labels[i],
        key="log_sel",
    )
    log_path = entrees[log_sel][1]

    lc1, lc2, lc3 = st.columns([2, 2, 4])
    with lc1:
        log_lines = st.number_input(
            "Dernières lignes",
            min_value=10, max_value=2000, value=200, step=50,
            key="log_lines",
        )
    with lc2:
        st.markdown("<div style='margin-top:1.75rem'>", unsafe_allow_html=True)
        if st.button("🔄 Rafraîchir", key="log_refresh"):
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    with lc3:
        st.caption(
            f"Modifié le {_fmt_mtime(log_path)}  ·  {_fmt_size(log_path)}"
        )

    try:
        log_content = log_path.read_text(encoding="utf-8", errors="replace")
        all_lines = log_content.splitlines()
        display_lines = all_lines[-int(log_lines):]
        st.code("\n".join(display_lines), language=None)
    except Exception as e:
        st.error(f"Erreur lecture log : {e}")

declencher_dialog_si_requis()