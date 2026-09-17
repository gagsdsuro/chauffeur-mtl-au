# -*- coding: utf-8 -*-
"""Page — Rapports (journalier PDF + rapport v2).

Ancien onglet 3 de l'application monolithique (app/ui.py).
"""
import bootstrap  # noqa: F401  (configure sys.path avant tout import)

bootstrap.initialiser_page()

import subprocess
import sys
from datetime import date

import streamlit as st

from gen_rapport_v2 import generer_rapport

from app.components.session_dialog import declencher_dialog_si_requis
from bootstrap import SCRIPTS_DIR

from chauffeur.depots import charger_journee, chemin_journee
from chauffeur.effectif import bornes_quart
from chauffeur.journee import groupes_de_service
from chauffeur.preparation import etat_rapport, marquer_rapport_a_jour

RAPPORTS_DIR = bootstrap.rapports_dir()

st.header("Rapports")
rpt_tabs = st.tabs(["📄 Rapport journalier", "📊 Rapport v2 (journée)"])

# ── 3a — Rapport journalier ───────────────────────────────────────────────
with rpt_tabs[0]:
    st.markdown("Génère le PDF recto-verso (G-D + détours) à partir de la journée du jour.")

    rj_date = st.date_input(
        "Date du rapport", value=date.today(), key="rj_date", persist_state="session"
    )
    rj_out = RAPPORTS_DIR / f"rapport-{rj_date}.pdf"

    rj_generated = False
    if st.button("Générer le rapport", type="primary", key="rj_btn"):
        RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, str(SCRIPTS_DIR / "gen_rapport.py"),
            "--date", str(rj_date),
            "--output", str(rj_out),
        ]
        with st.spinner("Génération en cours…"):
            result = subprocess.run(cmd, capture_output=True, text=True)
        output_text = result.stdout + ("\n" + result.stderr if result.stderr else "")
        st.code(output_text)
        if result.returncode == 0 and rj_out.exists():
            rj_generated = True
            _rj_journee = chemin_journee(str(rj_date))
            if _rj_journee.exists():
                _rj_etat = etat_rapport(
                    _rj_journee, "journalier", rapports_dir=RAPPORTS_DIR
                )
                marquer_rapport_a_jour(_rj_journee, _rj_etat, RAPPORTS_DIR)
        else:
            st.error(
                "Erreur lors de la génération. "
                "Vérifiez qu'une journée JSON existe pour cette date dans `data/journees/`."
            )

    if rj_out.exists():
        if rj_generated:
            st.success("Rapport généré.")
        st.download_button(
            "⬇️ Télécharger le rapport",
            data=rj_out.read_bytes(),
            file_name=rj_out.name,
            mime="application/pdf",
            key="rj_dl",
        )

# ── 3b — Rapport v2 (journée) ────────────────────────────────────────────────
with rpt_tabs[1]:
    st.markdown(
        "Génère un rapport G-D à partir d'une journée importée (`journee-YYYY-MM-DD.json`). "
        "Chaque groupe (ligne · direction · ID parcours) est traité séparément."
    )

    v2_date = st.date_input(
        "Date du rapport", value=date.today(), key="rpt_v2_date", persist_state="session"
    ).isoformat()
    v2_j_path = chemin_journee(v2_date)

    if not v2_j_path.exists():
        st.info(
            f"Aucune journée importée pour le {v2_date}. "
            "Importez-la dans **Préparation d'une journée**."
        )
    else:
        try:
            v2_j_data = charger_journee(v2_j_path)
        except Exception as e:
            st.error(f"Erreur lecture journée : {e}")
            st.stop()

        # ── Résumé journée et plage horaire ───────────────────────────────
        v2_pieces = v2_j_data.get("pieces", [])
        v2_debuts = [
            t.get("depart",  {}).get("heure", "")
            for p in v2_pieces for t in p.get("trajets", [])
            if t.get("type") == "service" and t.get("depart", {}).get("heure")
        ]
        v2_fins = [
            t.get("arrivee", {}).get("heure", "")
            for p in v2_pieces for t in p.get("trajets", [])
            if t.get("type") == "service" and t.get("arrivee", {}).get("heure")
        ]
        v2_bornes_deb = bornes_quart(v2_debuts, date.fromisoformat(v2_date))
        v2_bornes_fin = bornes_quart(v2_fins,   date.fromisoformat(v2_date))
        if v2_bornes_deb and v2_bornes_fin:
            st.caption(
                f"Plage du quart : **{v2_bornes_deb[0]} → {v2_bornes_fin[1]}**"
                f"  ·  Garage {v2_j_data.get('garage', '–')}"
                f"  ·  Journée #{v2_j_data.get('journee_numero', '–')}"
                f"  ·  Temps travaillé {v2_j_data.get('temps_travaille', '–')}"
            )

        # ── Groupes détectés ──────────────────────────────────────────────
        v2_groupes = groupes_de_service(v2_j_data)

        if v2_groupes:
            grp_txt = "  ·  ".join(
                f"{g['ligne']} {g['direction'].capitalize()} ID {g['id_parcours']}"
                + (" 🔀" if g.get("detour") else "")
                for g in v2_groupes
            )
            st.caption(f"Groupes : {grp_txt}")

        st.divider()

        # ── Options ───────────────────────────────────────────────────────
        v2_col_n, v2_col_f, v2_col_c = st.columns(3)
        with v2_col_n:
            v2_niveau = st.selectbox(
                "Niveau",
                ["détaillé", "standard", "compact"],
                key="rpt_v2_niveau",
            )
        with v2_col_f:
            v2_fmt = st.radio("Format", ["html", "pdf"], horizontal=True, key="rpt_v2_fmt")
        with v2_col_c:
            v2_code = st.checkbox("Codes arrêts", value=False, key="rpt_v2_code")

        if st.button("Générer", type="primary", key="rpt_v2_btn"):
            RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)
            v2_date_str = v2_j_data.get("date", v2_date)
            v2_out = RAPPORTS_DIR / f"rapport-v2-{v2_date_str}-{v2_niveau}.{v2_fmt}"

            with st.spinner("Génération en cours…"):
                try:
                    _out = generer_rapport(
                        v2_j_path,
                        fmt=v2_fmt,
                        output=v2_out,
                        niveau=v2_niveau,
                        show_code=v2_code,
                    )
                    if v2_fmt == "html" and not v2_code:
                        _v2_etat = etat_rapport(
                            v2_j_path, "v2", niveau=v2_niveau,
                            rapports_dir=RAPPORTS_DIR,
                        )
                        marquer_rapport_a_jour(v2_j_path, _v2_etat, RAPPORTS_DIR)
                    st.success("Rapport généré.")
                    v2_mime = "text/html" if v2_fmt == "html" else "application/pdf"
                    st.download_button(
                        f"⬇️ Télécharger ({v2_fmt.upper()})",
                        data=_out.read_bytes(),
                        file_name=_out.name,
                        mime=v2_mime,
                        key="rpt_v2_dl",
                    )
                    if v2_fmt == "html":
                        with st.expander("Aperçu HTML"):
                            st.iframe(
                                _out.read_text(encoding="utf-8"),
                                height=600,
                            )
                except Exception as _e:
                    st.error(f"Erreur lors de la génération : {_e}")

declencher_dialog_si_requis()
