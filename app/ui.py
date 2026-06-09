#!/usr/bin/env python3
"""
Interface Streamlit — Chauffeur STM
Regroupe : carte agent, G-D, évènements, rapport journalier, rapport G-D, GTFS.
"""

import io
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

import streamlit as st

# ── Chemins ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR  = PROJECT_ROOT / "scripts"
DATA_DIR     = PROJECT_ROOT / "data"
CA_DIR       = DATA_DIR / "ca"
RAPPORTS_DIR = DATA_DIR / "rapports"
APP_DIR      = Path(__file__).resolve().parent

# Rend les scripts et le répertoire app importables directement
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
    "📋 Carte Agent",
    "↔️ Gauche-Droite",
    "⚠️ Évènements",
    "📄 Rapport journalier",
    "🗺️ Rapport G-D détaillé",
    "📡 GTFS",
])


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
        st.info("Aucune carte agent disponible. Chargez-en une dans l'onglet **Carte Agent**.")
    else:
        ca_labels  = [p["name"] for p in ca_pdfs]
        sel_idx    = st.selectbox(
            "Carte agent",
            range(len(ca_labels)),
            format_func=lambda i: ca_labels[i],
            key="db_ca_select",
        )
        sel_ca     = ca_pdfs[sel_idx]
        ca_date_str = sel_ca["date_str"]

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
                        st.write("")  # aligne verticalement le bouton
                        geo_clicked = st.button(
                            "📍 Géolocaliser",
                            key=f"db_geo_btn_{i}",
                            disabled=not gtfs_info["rt_avail"],
                            help="Requiert un fichier vehiclePositions.pb (onglet GTFS)." if not gtfs_info["rt_avail"] else "",
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
                                    vehicle = find_vehicle(bus_num.strip(), vehicles)
                                    st.session_state[geo_key] = vehicle
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
                                df_map = pd.DataFrame([{"lat": v["lat"], "lon": v["lon"]}])
                                st.map(df_map, zoom=15)
                            except Exception:
                                maps_url = f"https://www.google.com/maps?q={v['lat']},{v['lon']}"
                                st.markdown(f"[Voir sur Google Maps]({maps_url})")
                        else:
                            st.warning(f"Bus `{bus_num.strip()}` introuvable dans les données GTFS-RT.")

            st.divider()

            # ── Lignes du jour ─────────────────────────────────────────────────
            st.subheader("Lignes du jour")

            lignes = ca_data["lignes"]
            if not lignes:
                st.info("Aucun numéro de ligne détecté dans la carte agent.")
            else:
                for ligne in lignes:
                    gd_files = get_gd_files_for_ligne(ligne, DATA_DIR)

                    with st.expander(f"Ligne {ligne}", expanded=True):
                        if not gd_files:
                            st.caption(f"Aucun fichier G-D pour la ligne {ligne}.")
                            continue

                        for gd in gd_files:
                            direction  = gd["direction"]
                            evt_mtime  = get_event_file_mtime(ligne, direction, DATA_DIR)

                            c1, c2, c3, c4 = st.columns([1, 3, 3, 2])
                            c1.markdown(f"**{direction.capitalize()}**")
                            c2.caption(f"G-D : {gd['mtime']}")
                            c3.caption(f"Évènements : {evt_mtime}")

                            # Plage horaire de cette direction depuis la carte agent
                            line_tr  = ca_data.get("line_time_ranges", {})
                            segments = line_tr.get(ligne, [])
                            tr = get_time_range_for_direction(gd["path"], segments)

                            with c4:
                                if tr:
                                    st.caption(f"⏱ {tr[0]} → {tr[1]}")
                                if st.button(
                                    "🗺️ Rapport G-D",
                                    key=f"db_rpt_{ligne}_{direction}",
                                ):
                                    st.session_state[f"db_rpt_run_{ligne}_{direction}"] = True

                            rpt_key = f"db_rpt_run_{ligne}_{direction}"
                            if st.session_state.get(rpt_key):
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
                                        cmd += ["--heure-debut", tr[0],
                                                "--heure-fin",   tr[1]]
                                    with st.spinner(f"Génération du rapport {ligne} {direction}…"):
                                        rpt_result = subprocess.run(
                                            cmd, capture_output=True, text=True
                                        )

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
                                                rpt_html.decode("utf-8"),
                                                height=600,
                                                scrolling=True,
                                            )
                                    else:
                                        st.error("Erreur lors de la génération du rapport.")
                                        st.code(rpt_result.stderr or rpt_result.stdout)

            st.divider()

            # ── Données GTFS ───────────────────────────────────────────────────
            st.subheader("Données GTFS")
            c1, c2 = st.columns(2)
            c1.metric("GTFS statique (dernière mise à jour)", gtfs_info["static_ts"])
            c2.metric("GTFS temps réel (dernière mise à jour)", gtfs_info["rt_ts"])


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Carte Agent
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.header("Carte Agent")
    st.markdown("Déposez le PDF brut de votre carte agent. L'application le sauvegarde et génère une version annotée (horaires GTFS surlignés).")

    uploaded = st.file_uploader("Fichier carte agent (PDF)", type="pdf", key="ca_upload")

    col1, col2 = st.columns(2)
    with col1:
        ca_date = st.date_input("Date de la carte", value=date.today(), key="ca_date")
    with col2:
        no_gtfs = st.checkbox("Sans GTFS (surlignage seulement)", value=False, key="ca_no_gtfs")

    if uploaded and st.button("Annoter la carte", type="primary", key="ca_btn"):
        CA_DIR.mkdir(parents=True, exist_ok=True)
        src_path = CA_DIR / f"carte-agent-{ca_date}.pdf"
        out_path = CA_DIR / f"carte-agent-{ca_date}-annotee.pdf"
        gtfs_path = DATA_DIR / "gtfs" / "gtfs_stm"

        # Sauvegarde le PDF source
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


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Gauche-Droite
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.header("Import Gauche-Droite")
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

            sections = split_sections(gd_text) or [gd_text]
            all_ok = True
            for section in sections:
                parser = GDParser(section)
                # Capture stdout du rapport
                import io as _io
                old_stdout = sys.stdout
                sys.stdout = buf = _io.StringIO()
                result_data = parser.parse()
                sys.stdout = old_stdout
                rapport = buf.getvalue()

                if result_data:
                    st.success(f"Ligne {parser.ligne} {parser.direction} — importé.")
                    st.code(rapport)
                else:
                    st.error(f"Échec pour une section.")
                    st.code("\n".join(parser.errors))
                    all_ok = False

            if all_ok:
                st.balloons()


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 4 — Évènements
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.header("Import Évènements")
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
                parser = STMEventParser(section)
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
# Tab 5 — Rapport journalier
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.header("Rapport journalier")
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


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 6 — Rapport G-D détaillé
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.header("Rapport G-D détaillé")
    st.markdown("Croise les arrêts GTFS, les instructions G-D et les évènements actifs pour une ligne et une date.")

    col1, col2, col3 = st.columns(3)
    with col1:
        gdr_ligne = st.text_input("Ligne", placeholder="195  ou  24e", key="gdr_ligne",
                                  help="Ajoutez 'e' pour les variantes école (ex: 24e, 168e).")
    with col2:
        gdr_dir = st.selectbox("Direction", ["est", "ouest", "nord", "sud"], key="gdr_dir")
    with col3:
        gdr_date = st.date_input("Date", value=date.today(), key="gdr_date")

    # ── Sélection du parcours ──────────────────────────────────────────────────
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

    # ── Plage d'arrêts effective ───────────────────────────────────────────────
    st.markdown("**Plage d'arrêts effective** *(optionnel — si le chauffeur ne fait pas le parcours complet)*")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        gdr_arret_debut = st.text_input("Code arrêt de départ", placeholder="54112",
                                         key="gdr_arret_debut",
                                         help="Code STM à 5 chiffres. Laissez vide pour le début du parcours.")
    with col_s2:
        gdr_arret_fin = st.text_input("Code arrêt de fin", placeholder="57365",
                                       key="gdr_arret_fin",
                                       help="Code STM à 5 chiffres. Laissez vide pour la fin du parcours.")

    # ── Plage horaire du quart ─────────────────────────────────────────────────
    st.markdown("**Plage horaire du quart** *(optionnel — laisser vide pour la journée complète)*")
    col_a, col_b = st.columns(2)
    with col_a:
        gdr_heure_debut = st.text_input(
            "Heure de début", placeholder="22:00  ou  06:30",
            key="gdr_heure_debut",
            help="Accepte les heures de quart dépassant minuit : ex. 25:30 = 1h30 le lendemain."
        )
    with col_b:
        gdr_heure_fin = st.text_input(
            "Heure de fin", placeholder="06:30  ou  28:00",
            key="gdr_heure_fin",
            help="Accepte les heures de quart dépassant minuit : ex. 28:00 = 4h00 le lendemain."
        )

    gdr_format = st.radio("Format de sortie", ["html", "md"], horizontal=True, key="gdr_fmt")

    if st.button("Générer", type="primary", key="gdr_btn"):
        if not gdr_ligne.strip():
            st.warning("Entrez un numéro de ligne.")
        elif bool(gdr_heure_debut.strip()) != bool(gdr_heure_fin.strip()):
            st.warning("Veuillez renseigner les deux heures (début ET fin) ou laisser les deux vides.")
        else:
            gtfs_path = DATA_DIR / "gtfs" / "gtfs_stm"
            if not gtfs_path.exists():
                st.error("Données GTFS introuvables. Lancez d'abord le téléchargement GTFS (onglet GTFS).")
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
                # Parcours
                hint = gdr_parcours_hint if not _parcours_options else gdr_parcours_hint
                if hint and hint.strip():
                    cmd += ["--parcours", hint.strip()]
                # Plage d'arrêts
                if gdr_arret_debut.strip():
                    cmd += ["--arret-debut", gdr_arret_debut.strip()]
                if gdr_arret_fin.strip():
                    cmd += ["--arret-fin", gdr_arret_fin.strip()]
                # Heures de quart
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
# Tab 7 — GTFS
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.header("Données GTFS")

    gtfs_path = DATA_DIR / "gtfs" / "gtfs_stm"
    gtfs_manifest = DATA_DIR / "gtfs" / "gtfs_manifest.json"

    # Statut actuel
    if gtfs_manifest.exists():
        import json as _json
        manifest = _json.loads(gtfs_manifest.read_text())
        dl_date = manifest.get("downloaded_at", "?")
        st.info(f"GTFS statique présent — téléchargé le {dl_date}")
    else:
        st.warning("Aucune donnée GTFS statique. Cliquez sur **Télécharger** pour initialiser.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("GTFS statique")
        st.caption("Données de lignes, arrêts et horaires (mis à jour hebdomadairement).")
        if st.button("Télécharger GTFS statique", key="gtfs_static_btn"):
            log_area = st.empty()
            with st.spinner("Téléchargement en cours…"):
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs.py")],
                    capture_output=True, text=True,
                )
            log_area.code(result.stdout + ("\n" + result.stderr if result.stderr else ""))
            if result.returncode == 0:
                st.success("GTFS statique mis à jour.")
            else:
                st.error("Erreur lors du téléchargement.")

    with col2:
        st.subheader("GTFS temps réel")
        st.caption("Positions et retards en temps réel (nécessite une clé API STM dans `Installation/config/secrets.json`).")
        if st.button("Télécharger GTFS-RT", key="gtfs_rt_btn"):
            log_area_rt = st.empty()
            with st.spinner("Téléchargement en cours…"):
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs_rt.py")],
                    capture_output=True, text=True,
                )
            log_area_rt.code(result.stdout + ("\n" + result.stderr if result.stderr else ""))
            if result.returncode == 0:
                st.success("GTFS-RT récupéré.")
            else:
                st.error("Erreur lors du téléchargement.")
