#!/usr/bin/env python3
"""
Interface Streamlit — Chauffeur STM
Onglets : Tableau de bord · Importation · Rapports · Fichiers · GTFS
"""

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import streamlit as st

# ── Chemins ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR  = PROJECT_ROOT / "scripts"
DATA_DIR     = PROJECT_ROOT / "data"
CA_DIR       = DATA_DIR / "ca"
RAPPORTS_DIR = DATA_DIR / "rapports"
GD_DIR       = DATA_DIR / "Gauche-Droite"
EVENTS_DIR   = DATA_DIR / "Events"
APP_DIR      = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(APP_DIR))

# ── Config page ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Chauffeur STM",
    page_icon="🚌",
    layout="wide",
)

st.title("🚌 Chauffeur STM")

tabs = st.tabs([
    "🏠 Tableau de bord",
    "📥 Importation",
    "📊 Rapports",
    "🗂️ Fichiers",
    "📡 GTFS",
])


# ── Utilitaires partagés ──────────────────────────────────────────────────────

def _fmt_mtime(path: Path) -> str:
    if not path.exists():
        return "–"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _fmt_size(path: Path) -> str:
    if not path.exists():
        return ""
    b = path.stat().st_size
    return f"{b/1024:.0f} KB" if b < 1_048_576 else f"{b/1_048_576:.1f} MB"


def _event_applies_to_date(event: dict, date_str: str) -> bool:
    debut = event.get("date_heure_debut", "")
    fin   = event.get("date_heure_fin",   "")
    if not debut:
        return True
    try:
        d      = date.fromisoformat(date_str)
        d_deb  = datetime.fromisoformat(debut).date()
        d_fin  = datetime.fromisoformat(fin).date() if fin else d_deb
        return d_deb <= d <= d_fin
    except Exception:
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Tableau de bord
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    from dashboard import (
        get_available_ca_pdfs, extract_pieces_from_pdf,
        get_gd_files_for_ligne, get_event_file_mtime,
        get_gtfs_info, parse_vehicle_positions, find_vehicle,
        get_time_range_for_direction,
    )

    st.header("Tableau de bord")

    ca_pdfs = get_available_ca_pdfs(CA_DIR)

    if not ca_pdfs:
        st.info("Aucune carte agent disponible. Chargez-en une dans l'onglet **Importation**.")
    else:
        ca_labels = [p["name"] for p in ca_pdfs]
        sel_idx   = st.selectbox(
            "Carte agent",
            range(len(ca_labels)),
            format_func=lambda i: ca_labels[i],
            key="db_ca_select",
        )
        sel_ca      = ca_pdfs[sel_idx]
        ca_date_str = sel_ca["date_str"]

        # ── Téléchargements carte agent ────────────────────────────────────────
        annotee_path  = CA_DIR / f"carte-agent-{ca_date_str}-annotee.pdf"
        surligné_path = CA_DIR / f"carte-agent-{ca_date_str}-surligné.pdf"
        annotee_avail = annotee_path.exists() or surligné_path.exists()
        annotee_file  = annotee_path if annotee_path.exists() else surligné_path

        dl1, dl2, dl3 = st.columns(3)
        with dl1:
            st.download_button(
                "⬇️ Carte agent source",
                data=sel_ca["path"].read_bytes(),
                file_name=sel_ca["path"].name,
                mime="application/pdf",
                key="db_ca_dl_src",
            )
        with dl2:
            if annotee_avail:
                st.download_button(
                    "⬇️ Carte annotée",
                    data=annotee_file.read_bytes(),
                    file_name=annotee_file.name,
                    mime="application/pdf",
                    key="db_ca_dl_ann",
                )
            else:
                st.button("⬇️ Carte annotée (non disponible)", disabled=True, key="db_ca_dl_ann_dis")
        with dl3:
            rapport_path = RAPPORTS_DIR / f"rapport-{ca_date_str}.pdf"
            if rapport_path.exists():
                st.download_button(
                    "⬇️ Rapport journalier",
                    data=rapport_path.read_bytes(),
                    file_name=rapport_path.name,
                    mime="application/pdf",
                    key="db_rj_dl",
                )
            else:
                st.button("⬇️ Rapport journalier (non disponible)", disabled=True, key="db_rj_dl_dis")

        ca_data = extract_pieces_from_pdf(sel_ca["path"])

        if ca_data is None:
            st.error("Impossible de lire la carte agent (PyMuPDF requis).")
        else:
            # ── Sommaire de la journée ─────────────────────────────────────────
            st.subheader(f"Carte {ca_data['carte']} — {ca_date_str}")

            pieces = ca_data["pieces"]

            def _to_min(t: str) -> int:
                h, m = map(int, t.split(":"))
                return h * 60 + m

            if pieces:
                debut_global = min(pieces, key=lambda p: _to_min(p["debut"]))["debut"]
                fin_global   = max(pieces, key=lambda p: _to_min(p["fin"]))["fin"]
                c1, c2, c3 = st.columns(3)
                c1.metric("Heure de début", debut_global)
                c2.metric("Heure de fin",   fin_global)
                c3.metric("Nombre de pièces", len(pieces))

            st.divider()

            # ── Pièces de travail ──────────────────────────────────────────────
            st.subheader("Pièces de travail")

            gtfs_info = get_gtfs_info(DATA_DIR)

            for i, piece in enumerate(pieces):
                with st.expander(
                    f"Pièce {i + 1} — Prise {piece['debut']} → {piece['fin']}",
                    expanded=True,
                ):
                    col_t, col_bus, col_geo = st.columns([2, 3, 2])

                    with col_t:
                        st.markdown(f"**Début :** `{piece['debut']}`")
                        st.markdown(f"**Fin :** `{piece['fin']}`")

                    with col_bus:
                        bus_num = st.text_input(
                            "Numéro d'autobus",
                            placeholder="12-345",
                            key=f"db_bus_{i}",
                        )

                    with col_geo:
                        st.write("")
                        geo_clicked = st.button(
                            "📍 Géolocaliser",
                            key=f"db_geo_btn_{i}",
                            disabled=not gtfs_info["rt_avail"],
                            help="Requiert vehiclePositions.pb (onglet GTFS)." if not gtfs_info["rt_avail"] else "",
                        )

                    geo_key = f"db_geo_result_{i}"
                    if geo_clicked:
                        if not bus_num.strip():
                            st.warning("Entrez un numéro d'autobus avant de géolocaliser.")
                        else:
                            with st.spinner("Recherche du véhicule…"):
                                try:
                                    vehicles = parse_vehicle_positions(
                                        gtfs_info["rt_pb"].read_bytes()
                                    )
                                    st.session_state[geo_key] = find_vehicle(bus_num.strip(), vehicles)
                                except Exception as e:
                                    st.error(f"Erreur parsing GTFS-RT : {e}")
                                    st.session_state[geo_key] = None

                    if geo_key in st.session_state:
                        v = st.session_state[geo_key]
                        if v:
                            st.success(
                                f"🚌 Bus `{v.get('v_label') or v.get('v_id')}` — "
                                f"Lat {v['lat']:.5f}, Lon {v['lon']:.5f}"
                                + (f" — Ligne {v['route_id']}" if v.get("route_id") else "")
                            )
                            try:
                                import pandas as pd
                                st.map(pd.DataFrame([{"lat": v["lat"], "lon": v["lon"]}]), zoom=15)
                            except Exception:
                                st.markdown(f"[Voir sur Google Maps](https://www.google.com/maps?q={v['lat']},{v['lon']})")
                        else:
                            st.warning(f"Bus `{bus_num.strip()}` introuvable dans les données GTFS-RT.")

            st.divider()

            # ── Lignes du jour ─────────────────────────────────────────────────
            st.subheader("Lignes du jour")

            lignes = ca_data["lignes"]
            if not lignes:
                st.info("Aucun numéro de ligne détecté dans la carte agent.")
            else:
                line_tr = ca_data.get("line_time_ranges", {})

                for ligne in lignes:
                    gd_files = get_gd_files_for_ligne(ligne, DATA_DIR)

                    with st.expander(f"Ligne {ligne}", expanded=True):
                        if not gd_files:
                            st.caption(f"Aucun fichier G-D pour la ligne {ligne}.")
                            continue

                        for gd in gd_files:
                            direction = gd["direction"]
                            evt_path  = EVENTS_DIR / f"{ligne}_{direction}.json"
                            evt_mtime = get_event_file_mtime(ligne, direction, DATA_DIR)
                            segments  = line_tr.get(ligne, [])
                            tr        = get_time_range_for_direction(gd["path"], segments)

                            # ── Ligne d'info ───────────────────────────────────
                            ci1, ci2, ci3, ci4 = st.columns([1, 3, 3, 2])
                            ci1.markdown(f"**{direction.capitalize()}**")
                            ci2.caption(f"G-D : {gd['mtime']}")
                            ci3.caption(f"Évènements : {evt_mtime}")
                            with ci4:
                                if tr:
                                    st.caption(f"⏱ {tr[0]} → {tr[1]}")

                            # ── Boutons d'action ───────────────────────────────
                            cb1, cb2, cb3 = st.columns(3)
                            with cb1:
                                if st.button("📄 Voir G-D", key=f"db_gd_btn_{ligne}_{direction}"):
                                    k = f"db_gd_open_{ligne}_{direction}"
                                    st.session_state[k] = not st.session_state.get(k, False)
                            with cb2:
                                if st.button("⚠️ Évènements", key=f"db_ev_btn_{ligne}_{direction}"):
                                    k = f"db_ev_open_{ligne}_{direction}"
                                    st.session_state[k] = not st.session_state.get(k, False)
                            with cb3:
                                if st.button("🗺️ Rapport G-D", key=f"db_rpt_{ligne}_{direction}"):
                                    st.session_state[f"db_rpt_run_{ligne}_{direction}"] = True

                            # ── Visualisation G-D ──────────────────────────────
                            if st.session_state.get(f"db_gd_open_{ligne}_{direction}"):
                                try:
                                    gd_data = json.loads(gd["path"].read_text(encoding="utf-8"))
                                    with st.expander(f"G-D — {ligne} {direction}", expanded=True):
                                        for route in gd_data.get("routes", []):
                                            for parcours in route.get("parcours", []):
                                                st.markdown(
                                                    f"**{parcours.get('name', '?')}** "
                                                    f"— {parcours.get('start', '')} `{parcours.get('start_code', '')}` "
                                                    f"→ {parcours.get('end', '')} `{parcours.get('end_code', '')}`"
                                                )
                                                for instr in parcours.get("direction", []):
                                                    st.text(f"   {instr}")
                                                st.divider()
                                except Exception as e:
                                    st.error(f"Erreur lecture G-D : {e}")

                            # ── Visualisation évènements ───────────────────────
                            if st.session_state.get(f"db_ev_open_{ligne}_{direction}"):
                                if not evt_path.exists():
                                    st.info(f"Aucun fichier d'évènements pour {ligne} {direction}.")
                                else:
                                    try:
                                        evt_data = json.loads(evt_path.read_text(encoding="utf-8"))
                                        events   = evt_data.get("detours", [])
                                        with st.expander(f"Évènements — {ligne} {direction}", expanded=True):
                                            if not events:
                                                st.caption("Aucun évènement enregistré.")
                                            for evt in events:
                                                applies = _event_applies_to_date(evt, ca_date_str)
                                                eid   = evt.get("evenement_id", "?")
                                                titre = evt.get("titre", "(sans titre)")
                                                eff   = evt.get("effectif", "")
                                                d_deb = evt.get("date_heure_debut", "")[:10]
                                                d_fin = evt.get("date_heure_fin",   "")[:10]
                                                label = f"{'✅' if applies else '⬜'} #{eid} — {titre}"
                                                with st.expander(label, expanded=applies):
                                                    if not applies:
                                                        st.caption("⚠️ Hors de la plage de validité pour cette date.")
                                                    if eff:
                                                        st.caption(f"Effectif : {eff}")
                                                    if d_deb:
                                                        st.caption(f"Période : {d_deb} → {d_fin or '?'}")
                                                    ann = evt.get("arrets_annules", [])
                                                    ajt = evt.get("arrets_ajoutes", [])
                                                    if ann:
                                                        st.markdown("**Arrêts annulés :**")
                                                        for a in ann:
                                                            nm = a.get("nom", a.get("code", "?"))
                                                            cd = a.get("code", "")
                                                            st.text(f"  ✖ {nm}" + (f" ({cd})" if cd else ""))
                                                    if ajt:
                                                        st.markdown("**Arrêts ajoutés :**")
                                                        for a in ajt:
                                                            nm = a.get("nom", a.get("code", "?"))
                                                            cd = a.get("code", "")
                                                            st.text(f"  ✚ {nm}" + (f" ({cd})" if cd else ""))
                                    except Exception as e:
                                        st.error(f"Erreur lecture évènements : {e}")

                            # ── Génération rapport G-D ─────────────────────────
                            if st.session_state.get(f"db_rpt_run_{ligne}_{direction}"):
                                gtfs_path = DATA_DIR / "gtfs" / "gtfs_stm"
                                if not gtfs_path.exists():
                                    st.warning("Données GTFS introuvables.")
                                else:
                                    cmd = [
                                        sys.executable, str(SCRIPTS_DIR / "rapport_gd.py"),
                                        "--ligne", ligne,
                                        "--direction", direction,
                                        "--date", ca_date_str,
                                        "--format", "html",
                                        "--base", str(PROJECT_ROOT),
                                    ]
                                    if tr:
                                        cmd += ["--heure-debut", tr[0], "--heure-fin", tr[1]]
                                    with st.spinner(f"Génération rapport {ligne} {direction}…"):
                                        rpt_result = subprocess.run(cmd, capture_output=True, text=True)

                                    out_path = SCRIPTS_DIR / f"rapport_{ligne}_{direction}_{ca_date_str}.html"
                                    if rpt_result.returncode == 0 and out_path.exists():
                                        rpt_html = out_path.read_bytes()
                                        st.download_button(
                                            f"⬇️ Rapport {ligne} {direction} (HTML)",
                                            data=rpt_html,
                                            file_name=out_path.name,
                                            mime="text/html",
                                            key=f"db_rpt_dl_{ligne}_{direction}",
                                        )
                                        with st.expander(f"Aperçu — {ligne} {direction}", expanded=True):
                                            st.components.v1.html(
                                                rpt_html.decode("utf-8"), height=600, scrolling=True
                                            )
                                    else:
                                        st.error("Erreur lors de la génération du rapport.")
                                        st.code(rpt_result.stderr or rpt_result.stdout)

                            st.markdown("---")

            st.divider()

            # ── Données GTFS ───────────────────────────────────────────────────
            st.subheader("Données GTFS")
            c1, c2 = st.columns(2)
            c1.metric("GTFS statique", gtfs_info["static_ts"])
            c2.metric("GTFS temps réel", gtfs_info["rt_ts"])


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Importation
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.header("Importation")
    imp_tabs = st.tabs(["📋 Carte Agent", "↔️ Gauche-Droite", "⚠️ Évènements"])

    # ── 2a — Carte Agent ──────────────────────────────────────────────────────
    with imp_tabs[0]:
        st.markdown("Déposez le PDF brut de votre carte agent. L'application le sauvegarde et génère une version annotée (horaires GTFS surlignés).")

        uploaded = st.file_uploader("Fichier carte agent (PDF)", type="pdf", key="ca_upload")

        col1, col2 = st.columns(2)
        with col1:
            ca_date = st.date_input("Date de la carte", value=date.today(), key="ca_date")
        with col2:
            no_gtfs = st.checkbox("Sans GTFS (surlignage seulement)", value=False, key="ca_no_gtfs")

        if uploaded and st.button("Annoter la carte", type="primary", key="ca_btn"):
            CA_DIR.mkdir(parents=True, exist_ok=True)
            src_path  = CA_DIR / f"carte-agent-{ca_date}.pdf"
            out_path  = CA_DIR / f"carte-agent-{ca_date}-annotee.pdf"
            gtfs_path = DATA_DIR / "gtfs" / "gtfs_stm"

            src_path.write_bytes(uploaded.read())
            st.info(f"PDF sauvegardé : {src_path.name}")

            cmd = [
                sys.executable, str(SCRIPTS_DIR / "carte_agent_stm.py"),
                "--pdf", str(src_path),
                "--out", str(out_path),
                "--date", str(ca_date),
            ]
            if not no_gtfs and gtfs_path.exists():
                cmd += ["--gtfs", str(gtfs_path)]
            elif no_gtfs:
                cmd.append("--no-gtfs")

            with st.spinner("Annotation en cours…"):
                result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                st.success("Carte annotée avec succès.")
                st.code(result.stdout or "(pas de sortie)")
                if out_path.exists():
                    st.download_button(
                        "⬇️ Télécharger la carte annotée",
                        data=out_path.read_bytes(),
                        file_name=out_path.name,
                        mime="application/pdf",
                        key="ca_dl",
                    )
            else:
                st.error("Erreur lors de l'annotation.")
                st.code(result.stderr or result.stdout)

    # ── 2b — Gauche-Droite ───────────────────────────────────────────────────
    with imp_tabs[1]:
        st.markdown("Collez le texte brut copié depuis l'interface STM. Le fichier `gd<ligne>_<direction>.json` sera créé ou mis à jour.")

        gd_text = st.text_area(
            "Texte brut G-D",
            height=400,
            placeholder="Gauche-Droite / 195 Ouest\nParcours principal ID 1\n...",
            key="gd_text",
        )

        if st.button("Importer", type="primary", key="gd_btn"):
            if not gd_text.strip():
                st.warning("Le champ est vide.")
            else:
                from parse_gd import GDParser, split_sections
                import io as _io

                sections = split_sections(gd_text) or [gd_text]
                all_ok = True
                for section in sections:
                    parser     = GDParser(section)
                    old_stdout = sys.stdout
                    sys.stdout = buf = _io.StringIO()
                    result_data = parser.parse()
                    sys.stdout = old_stdout
                    rapport    = buf.getvalue()

                    if result_data:
                        st.success(f"Ligne {parser.ligne} {parser.direction} — importé.")
                        st.code(rapport)
                    else:
                        st.error("Échec pour une section.")
                        st.code("\n".join(parser.errors))
                        all_ok = False

                if all_ok:
                    st.balloons()

    # ── 2c — Évènements ──────────────────────────────────────────────────────
    with imp_tabs[2]:
        st.markdown("Collez le texte brut des évènements / détours STM. Le fichier `<ligne>_<direction>.json` sera créé ou mis à jour.")

        ev_text = st.text_area(
            "Texte brut des évènements",
            height=400,
            placeholder="Détours / 195 Ouest\nÉvènement - 10075400 - Annulation d'arrêts\n...",
            key="ev_text",
        )

        if st.button("Importer", type="primary", key="ev_btn"):
            if not ev_text.strip():
                st.warning("Le champ est vide.")
            else:
                from parse_event import STMEventParser, split_sections as split_ev

                sections = split_ev(ev_text) or [ev_text]
                all_ok = True
                for section in sections:
                    parser  = STMEventParser(section)
                    success = parser.parse_all()
                    if success:
                        saved, changed = parser.save_json()
                        if saved:
                            st.success(f"Ligne {parser.ligne} {parser.direction} — {'sauvegardé' if changed else 'aucun changement'}.")
                        else:
                            st.error("Erreur de sauvegarde.")
                            all_ok = False
                    else:
                        st.error("Erreur de parsing.")
                        all_ok = False
                    st.code(parser.get_summary())

                if all_ok:
                    st.balloons()


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Rapports
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.header("Rapports")
    rpt_tabs = st.tabs(["📄 Rapport journalier", "🗺️ Rapport G-D détaillé"])

    # ── 3a — Rapport journalier ───────────────────────────────────────────────
    with rpt_tabs[0]:
        st.markdown("Génère le PDF recto-verso (G-D + détours) à partir de la carte agent du jour.")

        rj_date = st.date_input("Date du rapport", value=date.today(), key="rj_date")

        if st.button("Générer le rapport", type="primary", key="rj_btn"):
            RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)
            out_path = RAPPORTS_DIR / f"rapport-{rj_date}.pdf"

            cmd = [
                sys.executable, str(SCRIPTS_DIR / "gen_rapport.py"),
                "--date", str(rj_date),
                "--output", str(out_path),
            ]

            with st.spinner("Génération en cours…"):
                result = subprocess.run(cmd, capture_output=True, text=True)

            output_text = result.stdout + ("\n" + result.stderr if result.stderr else "")
            st.code(output_text)

            if result.returncode == 0 and out_path.exists():
                st.success("Rapport généré.")
                st.download_button(
                    "⬇️ Télécharger le rapport",
                    data=out_path.read_bytes(),
                    file_name=out_path.name,
                    mime="application/pdf",
                    key="rj_dl",
                )
            else:
                st.error("Erreur lors de la génération. Vérifiez qu'une carte agent existe pour cette date dans `data/ca/`.")

    # ── 3b — Rapport G-D détaillé ─────────────────────────────────────────────
    with rpt_tabs[1]:
        st.markdown("Croise les arrêts GTFS, les instructions G-D et les évènements actifs pour une ligne et une date.")

        col1, col2, col3 = st.columns(3)
        with col1:
            gdr_ligne = st.text_input("Ligne", placeholder="195  ou  24e", key="gdr_ligne",
                                      help="Ajoutez 'e' pour les variantes école (ex: 24e, 168e).")
        with col2:
            gdr_dir = st.selectbox("Direction", ["est", "ouest", "nord", "sud"], key="gdr_dir")
        with col3:
            gdr_date = st.date_input("Date", value=date.today(), key="gdr_date")

        st.markdown("**Parcours**")
        _parcours_options = []
        if gdr_ligne.strip():
            from rapport_gd import list_parcours as _list_parcours
            _parcours_options = _list_parcours(gdr_ligne.strip(), gdr_dir, PROJECT_ROOT)

        if _parcours_options:
            _labels = [f"[{p['id']}] {p['name']}  ({p['start_code']} → {p['end_code']})"
                       for p in _parcours_options]
            _sel_idx = st.selectbox("Parcours disponibles", range(len(_labels)),
                                    format_func=lambda i: _labels[i], key="gdr_parcours_idx")
            gdr_parcours_hint = _parcours_options[_sel_idx]["name"]
        else:
            st.caption("Entrez un numéro de ligne valide pour voir les parcours disponibles.")
            gdr_parcours_hint = st.text_input(
                "Mot-clé parcours (optionnel)", placeholder="principal, secondaire, école, weekend",
                key="gdr_parcours_hint",
            )

        st.markdown("**Plage d'arrêts effective** *(optionnel)*")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            gdr_arret_debut = st.text_input("Code arrêt de départ", placeholder="54112", key="gdr_arret_debut")
        with col_s2:
            gdr_arret_fin = st.text_input("Code arrêt de fin", placeholder="57365", key="gdr_arret_fin")

        st.markdown("**Plage horaire du quart** *(optionnel)*")
        col_a, col_b = st.columns(2)
        with col_a:
            gdr_heure_debut = st.text_input("Heure de début", placeholder="22:00  ou  06:30", key="gdr_heure_debut")
        with col_b:
            gdr_heure_fin = st.text_input("Heure de fin", placeholder="06:30  ou  28:00", key="gdr_heure_fin")

        gdr_format = st.radio("Format de sortie", ["html", "md"], horizontal=True, key="gdr_fmt")

        if st.button("Générer", type="primary", key="gdr_btn"):
            if not gdr_ligne.strip():
                st.warning("Entrez un numéro de ligne.")
            elif bool(gdr_heure_debut.strip()) != bool(gdr_heure_fin.strip()):
                st.warning("Veuillez renseigner les deux heures (début ET fin) ou laisser les deux vides.")
            else:
                gtfs_path = DATA_DIR / "gtfs" / "gtfs_stm"
                if not gtfs_path.exists():
                    st.error("Données GTFS introuvables. Lancez d'abord le téléchargement GTFS.")
                else:
                    expected_out = SCRIPTS_DIR / f"rapport_{gdr_ligne.strip()}_{gdr_dir}_{gdr_date}.{gdr_format}"

                    cmd = [
                        sys.executable, str(SCRIPTS_DIR / "rapport_gd.py"),
                        "--ligne", gdr_ligne.strip(),
                        "--direction", gdr_dir,
                        "--date", str(gdr_date),
                        "--format", gdr_format,
                        "--base", str(PROJECT_ROOT),
                    ]
                    hint = gdr_parcours_hint if not _parcours_options else gdr_parcours_hint
                    if hint and hint.strip():
                        cmd += ["--parcours", hint.strip()]
                    if gdr_arret_debut.strip():
                        cmd += ["--arret-debut", gdr_arret_debut.strip()]
                    if gdr_arret_fin.strip():
                        cmd += ["--arret-fin", gdr_arret_fin.strip()]
                    if gdr_heure_debut.strip() and gdr_heure_fin.strip():
                        cmd += ["--heure-debut", gdr_heure_debut.strip(),
                                "--heure-fin",   gdr_heure_fin.strip()]

                    with st.spinner("Génération en cours…"):
                        result = subprocess.run(cmd, capture_output=True, text=True)

                    output_text = result.stdout + ("\n" + result.stderr if result.stderr else "")
                    st.code(output_text)

                    if result.returncode == 0 and expected_out.exists():
                        st.success("Rapport généré.")
                        content = expected_out.read_bytes()
                        mime = "text/html" if gdr_format == "html" else "text/markdown"
                        st.download_button(
                            f"⬇️ Télécharger le rapport ({gdr_format.upper()})",
                            data=content,
                            file_name=expected_out.name,
                            mime=mime,
                            key="gdr_dl",
                        )
                        if gdr_format == "html":
                            with st.expander("Aperçu HTML"):
                                st.components.v1.html(content.decode("utf-8"), height=600, scrolling=True)
                    else:
                        st.error("Erreur lors de la génération.")


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 4 — Fichiers
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.header("Gestion des fichiers")

    def _file_manager(label: str, files: list[Path], mime: str = "application/octet-stream") -> None:
        """Affiche une liste de fichiers avec téléchargement et suppression (avec confirmation)."""
        if not files:
            st.caption(f"Aucun fichier {label}.")
            return

        for idx, path in enumerate(files):
            col_name, col_date, col_size, col_dl, col_del = st.columns([4, 2, 1, 1, 1])
            col_name.text(path.name)
            col_date.caption(_fmt_mtime(path))
            col_size.caption(_fmt_size(path))

            with col_dl:
                st.download_button(
                    "⬇️",
                    data=path.read_bytes(),
                    file_name=path.name,
                    mime=mime,
                    key=f"fm_dl_{label}_{idx}",
                    help=f"Télécharger {path.name}",
                )

            confirm_key = f"fm_del_confirm_{label}_{idx}"
            with col_del:
                if st.session_state.get(confirm_key):
                    if st.button("⚠️", key=f"fm_del_ok_{label}_{idx}", help="Confirmer la suppression"):
                        path.unlink(missing_ok=True)
                        del st.session_state[confirm_key]
                        st.rerun()
                else:
                    if st.button("🗑️", key=f"fm_del_{label}_{idx}", help="Supprimer (cliquez à nouveau pour confirmer)"):
                        st.session_state[confirm_key] = True
                        st.rerun()

    fm_tabs = st.tabs([
        "📋 Cartes agent",
        "↔️ Gauche-Droite",
        "⚠️ Évènements",
        "📄 Rapports journaliers",
    ])

    # ── Cartes agent ──────────────────────────────────────────────────────────
    with fm_tabs[0]:
        ca_all = sorted(CA_DIR.glob("*.pdf"), reverse=True) if CA_DIR.exists() else []
        st.caption(f"{len(ca_all)} fichier(s) dans `data/ca/`")
        _file_manager("ca", ca_all, mime="application/pdf")

    # ── Gauche-Droite ─────────────────────────────────────────────────────────
    with fm_tabs[1]:
        gd_all = sorted(GD_DIR.glob("gd*.json")) if GD_DIR.exists() else []
        st.caption(f"{len(gd_all)} fichier(s) dans `data/Gauche-Droite/`")
        _file_manager("gd", gd_all, mime="application/json")

    # ── Évènements ────────────────────────────────────────────────────────────
    with fm_tabs[2]:
        ev_all = sorted(EVENTS_DIR.glob("*.json")) if EVENTS_DIR.exists() else []
        st.caption(f"{len(ev_all)} fichier(s) dans `data/Events/`")
        _file_manager("ev", ev_all, mime="application/json")

    # ── Rapports journaliers ──────────────────────────────────────────────────
    with fm_tabs[3]:
        rp_all = sorted(RAPPORTS_DIR.glob("rapport-*.pdf"), reverse=True) if RAPPORTS_DIR.exists() else []
        st.caption(f"{len(rp_all)} fichier(s) dans `data/rapports/`")
        _file_manager("rp", rp_all, mime="application/pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 5 — GTFS
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.header("Données GTFS")

    gtfs_path     = DATA_DIR / "gtfs" / "gtfs_stm"
    gtfs_manifest = DATA_DIR / "gtfs" / "gtfs_manifest.json"

    if gtfs_manifest.exists():
        manifest = json.loads(gtfs_manifest.read_text())
        dl_date  = manifest.get("downloaded_at", "?")
        st.info(f"GTFS statique présent — téléchargé le {dl_date}")
    else:
        st.warning("Aucune donnée GTFS statique. Cliquez sur **Télécharger** pour initialiser.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("GTFS statique")
        st.caption("Données de lignes, arrêts et horaires (mis à jour hebdomadairement).")
        if st.button("Télécharger GTFS statique", key="gtfs_static_btn"):
            with st.spinner("Téléchargement en cours…"):
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs.py")],
                    capture_output=True, text=True,
                )
            st.code(result.stdout + ("\n" + result.stderr if result.stderr else ""))
            if result.returncode == 0:
                st.success("GTFS statique mis à jour.")
            else:
                st.error("Erreur lors du téléchargement.")

    with col2:
        st.subheader("GTFS temps réel")
        st.caption("Positions et retards en temps réel (nécessite une clé API STM dans `Installation/config/secrets.json`).")
        if st.button("Télécharger GTFS-RT", key="gtfs_rt_btn"):
            with st.spinner("Téléchargement en cours…"):
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs_rt.py")],
                    capture_output=True, text=True,
                )
            st.code(result.stdout + ("\n" + result.stderr if result.stderr else ""))
            if result.returncode == 0:
                st.success("GTFS-RT récupéré.")
            else:
                st.error("Erreur lors du téléchargement.")
