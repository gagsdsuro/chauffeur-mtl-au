# -*- coding: utf-8 -*-
"""Page — Gestion des fichiers (téléchargement, suppression, purge).

Ancien onglet 4 de l'application monolithique (app/ui.py).
"""
import bootstrap  # noqa: F401  (configure sys.path avant tout import)

bootstrap.initialiser_page()

from datetime import date

import streamlit as st

from app.components.file_manager import (
    _file_manager,
    _purge_older_than,
    _purge_ui,
)
from app.components.session_dialog import declencher_dialog_si_requis

from chauffeur.depots import (
    EVENTS_DIR,
    GD_DIR,
    charger_journee,
)

CA_DIR = bootstrap.ca_dir()
JOURNEES_DIR = bootstrap.journees_dir()
RAPPORTS_DIR = bootstrap.rapports_dir()

st.header("Gestion des fichiers")

fm_tabs = st.tabs([
    "📋 Cartes agent",
    "↔️ Gauche-Droite",
    "⚠️ Évènements",
    "📄 Rapports",
    "📅 Journées",
])

# ── Cartes agent ──────────────────────────────────────────────────────────
with fm_tabs[0]:
    ca_all = sorted(CA_DIR.glob("*.pdf"), reverse=True) if CA_DIR.exists() else []
    st.caption(f"{len(ca_all)} fichier(s) dans `{CA_DIR}`")
    _file_manager("ca", ca_all, mime="application/pdf")
    _purge_ui("ca", ca_all, days=365)

# ── Gauche-Droite ─────────────────────────────────────────────────────────
with fm_tabs[1]:
    gd_all = sorted(GD_DIR.glob("gd*.json")) if GD_DIR.exists() else []
    st.caption(f"{len(gd_all)} fichier(s) dans `{GD_DIR}`")
    _file_manager("gd", gd_all, mime="application/json")
    _purge_ui("gd", gd_all, days=365)

# ── Évènements ────────────────────────────────────────────────────────────
with fm_tabs[2]:
    ev_all = sorted(EVENTS_DIR.glob("*.json")) if EVENTS_DIR.exists() else []
    st.caption(f"{len(ev_all)} fichier(s) dans `{EVENTS_DIR}`")
    _file_manager("ev", ev_all, mime="application/json")
    _purge_ui("ev", ev_all, days=90)

# ── Rapports journaliers ──────────────────────────────────────────────────
with fm_tabs[3]:
    rp_all = sorted(
        list(RAPPORTS_DIR.glob("rapport-*.pdf"))
        + list(RAPPORTS_DIR.glob("rapport-*.html")),
        reverse=True,
    ) if RAPPORTS_DIR.exists() else []
    st.caption(f"{len(rp_all)} fichier(s) dans `{RAPPORTS_DIR}`")
    _file_manager("rp", rp_all, mime=None)
    _purge_ui("rp", rp_all, days=90)

# ── Journées ──────────────────────────────────────────────────────────────
with fm_tabs[4]:
    j_all = sorted(JOURNEES_DIR.glob("journee-*.json"), reverse=True) if JOURNEES_DIR.exists() else []
    st.caption(f"{len(j_all)} fichier(s) dans `{JOURNEES_DIR}`")
    _file_manager("journee", j_all, mime="application/json")
    _purge_ui("journee", j_all, days=365)

    if j_all:
        st.divider()
        st.subheader("Aperçu")
        j_preview_labels = [p.stem.replace("journee-", "") for p in j_all]
        j_prev_sel = st.selectbox(
            "Journée à prévisualiser",
            range(len(j_all)),
            format_func=lambda i: j_preview_labels[i],
            key="fm_j_preview_sel",
        )
        try:
            j_prev_data = charger_journee(j_all[j_prev_sel])
            j_pieces = j_prev_data.get("pieces", [])
            j_trajets = [
                t for p in j_pieces for t in p.get("trajets", [])
                if t.get("type") == "service"
            ]
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Journée n°",      j_prev_data.get("journee_numero", "–"))
            mc2.metric("Garage",          j_prev_data.get("garage", "–"))
            mc3.metric("Temps travaillé", j_prev_data.get("temps_travaille", "–"))
            if j_trajets:
                for t in j_trajets:
                    tl = t.get("ligne", "?")
                    td = (t.get("direction") or "").lower().capitalize()
                    tid = t.get("id_parcours", "?")
                    dep = t.get("depart",  {})
                    arr = t.get("arrivee", {})
                    det = " 🔀" if t.get("detour") else ""
                    st.markdown(
                        f"🚌 **{tl} {td} ID {tid}**{det}"
                        f" &ensp; `{dep.get('heure', '?')}` {dep.get('arret', '?')}"
                        f" → `{arr.get('heure', '?')}` {arr.get('arret', '?')}"
                    )
            with st.expander("JSON brut"):
                st.json(j_prev_data)
        except Exception as e:
            st.error(f"Erreur lecture : {e}")
    else:
        st.info(f"Aucune journée enregistrée dans `{JOURNEES_DIR}` pour le moment.")

    # ── Export CSV ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Export CSV")

    if not j_all:
        st.info("Aucune journée enregistrée : rien à exporter pour le moment.")
    else:
        j_dates = sorted(date.fromisoformat(p.stem.replace("journee-", ""))
                         for p in j_all)
        exp_c1, exp_c2 = st.columns(2)
        with exp_c1:
            exp_debut = st.date_input(
                "Date de début", value=j_dates[0], key="fm_j_exp_debut"
            )
        with exp_c2:
            exp_fin = st.date_input(
                "Date de fin", value=j_dates[-1], key="fm_j_exp_fin"
            )

        N_TRAJET_COLS = 7

        if st.button("📤 Générer l'export CSV", key="fm_j_exp_btn"):
            import csv
            import io

            lignes_csv = []
            for p in j_all:
                try:
                    d = date.fromisoformat(p.stem.replace("journee-", ""))
                except ValueError:
                    continue
                if not (exp_debut <= d <= exp_fin):
                    continue
                try:
                    jd = charger_journee(p)
                except Exception:
                    continue

                for piece in jd.get("pieces", []):
                    lignes_service = [
                        t.get("ligne") for t in piece.get("trajets", [])
                        if t.get("type") == "service"
                    ]
                    row = {
                        "date": jd.get("date", ""),
                        "garage_id": jd.get("garage_id", ""),
                        "journee_numero": jd.get("journee_numero", ""),
                        "piece_id": piece.get("id", ""),
                        "type_horaire": piece.get("type_horaire", "horaire"),
                    }
                    for i in range(N_TRAJET_COLS):
                        row[f"trajet{i + 1}_ligne"] = (
                            lignes_service[i] if i < len(lignes_service) else ""
                        )
                    lignes_csv.append(row)

            if not lignes_csv:
                st.warning("Aucune journée dans cet intervalle.")
            else:
                buf = io.StringIO()
                fieldnames = [
                    "date", "garage_id", "journee_numero", "piece_id", "type_horaire"
                ] + [
                    f"trajet{i + 1}_ligne" for i in range(N_TRAJET_COLS)
                ]
                writer = csv.DictWriter(buf, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(lignes_csv)
                st.download_button(
                    "⬇️ Télécharger le CSV",
                    data=buf.getvalue().encode("utf-8"),
                    file_name=f"journees-{exp_debut}-{exp_fin}.csv",
                    mime="text/csv",
                    key="fm_j_exp_dl",
                )
                st.success(f"{len(lignes_csv)} pièce(s) exportée(s).")

# ── Registre des journées (fonction future) ───────────────────────────────
st.divider()
with st.expander("📒 Registre des journées de travail (à venir)"):
    st.info(
        "Fonction à venir : registre consolidé des journées travaillées "
        "(consultation et révision par le chauffeur-admin)."
    )

declencher_dialog_si_requis()