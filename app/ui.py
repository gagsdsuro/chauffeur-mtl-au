#!/usr/bin/env python3
"""
Interface Streamlit — Chauffeur STM
Onglets : Tableau de bord · Importation · Rapports · Fichiers · GTFS
"""

import base64
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ── Chemins ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR  = PROJECT_ROOT / "scripts"
DATA_DIR     = PROJECT_ROOT / "data"
CA_DIR       = DATA_DIR / "ca"
RAPPORTS_DIR = DATA_DIR / "rapports"
GD_DIR       = DATA_DIR / "Gauche-Droite"
EVENTS_DIR   = DATA_DIR / "Events"
JOURNEES_DIR = DATA_DIR / "journees"
APP_DIR      = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(APP_DIR))


# ── Utilitaires parcours / événements ────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _cached_stop_ids_for_parcours(
    gtfs_dir_str: str, ligne: str, direction: str, id_parcours
) -> frozenset:
    """Ensemble des stop_ids GTFS pour un parcours (mis en cache par session).

    Retourne frozenset() si le GTFS est absent ou si la ligne est inconnue.
    """
    try:
        from chauffeur.gtfs import (
            route_id as _rid, direction_id as _did, stops_for_line as _sfl,
        )
        gtfs  = Path(gtfs_dir_str)
        r     = _rid(gtfs, ligne)
        d     = _did(gtfs, r, direction)
        shape = f"{ligne}_{id_parcours}" if id_parcours is not None else None
        stops = _sfl(gtfs, r, d, shape_hint=shape)
        return frozenset(sid for _, sid in stops)
    except Exception:
        return frozenset()


def _ev_applicable_parcours_tb(
    evt: dict, stop_ids, gd_instr: list
) -> bool:
    """Applicabilité d'un évènement à un parcours depuis le tableau de bord.

    stop_ids=None = GTFS non disponible → présumer applicable pour les
    évènements avec arrêts annulés (fail-safe).
    """
    from chauffeur.gd import event_applicable_to_parcours as _eap
    cancelled = evt.get("arrets_annules", [])
    if cancelled:
        if stop_ids is None:
            return True
        return any(a["id"] in stop_ids for a in cancelled)
    return _eap(evt, frozenset(), gd_instr)


# ── Config page ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Chauffeur STM",
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

st.title("🚌 Chauffeur STM")

tabs = st.tabs([
    "🏠 Tableau de bord",
    "📥 Importation",
    "📊 Rapports",
    "🗂️ Fichiers",
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


def _pdf_embed_html(pdf_bytes: bytes, height: int = 800) -> str:
    """Embarque un PDF via un Blob URL (data: URLs bloquées par Chrome pour les PDF)."""
    import uuid
    b64 = base64.b64encode(pdf_bytes).decode()
    frame_id = f"pdf_{uuid.uuid4().hex}"
    return f"""
<iframe id="{frame_id}" width="100%" height="{height}px" style="border:none;"></iframe>
<script>
(function(){{
    var b64="{b64}", s=atob(b64), i, arr=[];
    for(i=0;i<s.length;i+=512){{
        var sl=s.slice(i,i+512), n=new Array(sl.length);
        for(var j=0;j<sl.length;j++) n[j]=sl.charCodeAt(j);
        arr.push(new Uint8Array(n));
    }}
    var url=URL.createObjectURL(new Blob(arr,{{type:"application/pdf"}}));
    document.getElementById("{frame_id}").src=url;
}})();
</script>"""


def _event_applies_to_date(event: dict, date_str: str) -> bool:
    debut = event.get("date_heure_debut") or ""
    fin   = event.get("date_heure_fin")   or ""
    if not debut:
        return True
    try:
        d      = date.fromisoformat(date_str)
        d_deb  = datetime.fromisoformat(debut).date()
        if fin:
            d_fin = datetime.fromisoformat(fin).date()
            return d_deb <= d <= d_fin
        else:
            return d >= d_deb
    except Exception:
        return True


def _event_applies(event: dict, date_str: str, tr) -> bool:
    """Marqueur ✅/⬜ cohérent avec gen_rapport : si la plage horaire travaillée
    (tr = (début, fin)) est connue, évalue la plage d'effectif vs le quart ;
    sinon repli sur la seule plage de validité (date)."""
    if tr:
        try:
            from chauffeur.effectif import parse_shift_time
            from chauffeur.evenements import applicable_au_quart
            d = date.fromisoformat(date_str)
            return applicable_au_quart(
                event, parse_shift_time(tr[0], d), parse_shift_time(tr[1], d))
        except Exception:
            pass
    return _event_applies_to_date(event, date_str)


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Tableau de bord
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    from dashboard import (
        get_gtfs_info, parse_vehicle_positions, find_vehicle,
    )

    st.header("Tableau de bord")

    db_j_files = (
        sorted(JOURNEES_DIR.glob("journee-*.json"), reverse=True)
        if JOURNEES_DIR.exists() else []
    )

    if not db_j_files:
        st.info(
            "Aucune journée enregistrée. "
            "Importez-en une dans l'onglet **Journées**."
        )
    else:
        db_j_labels = [p.stem.replace("journee-", "") for p in db_j_files]
        db_sel = st.selectbox(
            "Journée",
            range(len(db_j_labels)),
            format_func=lambda i: db_j_labels[i],
            key="db_j_sel",
        )
        db_j_path   = db_j_files[db_sel]
        db_date_str = db_j_labels[db_sel]

        try:
            db_j_data = json.loads(db_j_path.read_text(encoding="utf-8"))
        except Exception as e:
            st.error(f"Erreur lecture journée : {e}")
            st.stop()

        # ── Métriques résumé ──────────────────────────────────────────────────
        db_pieces = db_j_data.get("pieces", [])
        db_debut_all = [
            t.get("depart",  {}).get("heure", "")
            for p in db_pieces for t in p.get("trajets", [])
            if t.get("type") == "service" and t.get("depart", {}).get("heure")
        ]
        db_fin_all = [
            t.get("arrivee", {}).get("heure", "")
            for p in db_pieces for t in p.get("trajets", [])
            if t.get("type") == "service" and t.get("arrivee", {}).get("heure")
        ]

        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Journée n°",      db_j_data.get("journee_numero", "–"))
        mc2.metric("Garage",          db_j_data.get("garage",         "–"))
        mc3.metric("Temps travaillé", db_j_data.get("temps_travaille","–"))
        mc4.metric("Début",           min(db_debut_all) if db_debut_all else "–")
        mc5.metric("Fin",             max(db_fin_all)   if db_fin_all   else "–")

        # ── Téléchargements ──────────────────────────────────────────────────
        annotee_path  = CA_DIR / f"carte-agent-{db_date_str}-annotee.pdf"
        surligné_path = CA_DIR / f"carte-agent-{db_date_str}-surligné.pdf"
        annotee_file  = (
            annotee_path  if annotee_path.exists()  else
            surligné_path if surligné_path.exists() else None
        )
        _v2_html = sorted(
            RAPPORTS_DIR.glob(f"rapport-v2-{db_date_str}-*.html"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        ) if RAPPORTS_DIR.exists() else []
        _v2_pdf = sorted(
            RAPPORTS_DIR.glob(f"rapport-v2-{db_date_str}-*.pdf"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        ) if RAPPORTS_DIR.exists() else []
        latest_rpt = (_v2_html + _v2_pdf)[0] if (_v2_html or _v2_pdf) else None
        # Rapport complet (journée entière) — exclut les rapports per-trajet (-idN)
        _v2_html_jour = [p for p in _v2_html if not re.search(r"-id\d+", p.stem)]
        latest_html_jour = _v2_html_jour[0] if _v2_html_jour else None

        rj_file = RAPPORTS_DIR / f"rapport-{db_date_str}.pdf" if RAPPORTS_DIR else None
        rj_file = rj_file if (rj_file and rj_file.exists()) else None

        dl1, dl2, dl3 = st.columns(3)
        with dl1:
            if annotee_file:
                st.download_button(
                    "⬇️ Carte annotée",
                    data=annotee_file.read_bytes(),
                    file_name=annotee_file.name,
                    mime="application/pdf",
                    key="db_ca_dl",
                )
            else:
                st.button("⬇️ Carte annotée (non disponible)", disabled=True,
                          key="db_ca_dl_dis")
        with dl2:
            if rj_file:
                st.download_button(
                    "⬇️ Rapport journalier",
                    data=rj_file.read_bytes(),
                    file_name=rj_file.name,
                    mime="application/pdf",
                    key="db_rj_dl",
                )
            else:
                st.button("⬇️ Rapport journalier (non généré)", disabled=True,
                          key="db_rj_dl_dis")
        with dl3:
            if latest_rpt:
                _rpt_mime = "text/html" if latest_rpt.suffix == ".html" else "application/pdf"
                _rpt_label = latest_rpt.stem[len(f"rapport-v2-{db_date_str}-"):]
                st.download_button(
                    f"⬇️ Rapport v2 ({_rpt_label})",
                    data=latest_rpt.read_bytes(),
                    file_name=latest_rpt.name,
                    mime=_rpt_mime,
                    key="db_rpt_v2_dl",
                )
            else:
                st.button("⬇️ Rapport v2 (non généré)", disabled=True,
                          key="db_rpt_v2_dis")

        if latest_html_jour:
            with st.expander(f"📊 Rapport v2 — Aperçu  ({latest_html_jour.name})"):
                components.html(
                    latest_html_jour.read_text(encoding="utf-8"),
                    height=600, scrolling=True,
                )

        st.divider()

        # ── Pièces de travail ─────────────────────────────────────────────────
        st.subheader("Pièces de travail")

        gtfs_info = get_gtfs_info(DATA_DIR)
        RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)

        db_rpt_niveau = st.radio(
            "Niveau des rapports G-D",
            ["standard", "détaillé", "compact"],
            index=0,
            horizontal=True,
            key="db_rpt_niveau",
        )

        for idx, piece in enumerate(db_pieces):
            pid = piece.get("id", f"pièce-{idx + 1}")
            with st.expander(
                f"Pièce {pid}  —  {piece.get('debut', '?')} → {piece.get('fin', '?')}"
                f"  ({piece.get('duree', '?')})",
                expanded=False,
            ):
                pc1, pc2, pc3 = st.columns([2, 2, 2])

                with pc1:
                    st.markdown(f"**Lieu prise :** `{piece.get('lieu_prise', '–')}`")
                    st.markdown(f"**Lieu fin :** `{piece.get('lieu_fin', '–')}`")

                with pc2:
                    bus_edit_key = f"db_bus_edit_{db_date_str}_{idx}"
                    st.text_input(
                        "Numéro d'autobus",
                        value=piece.get("numero_autobus") or "",
                        placeholder="ex : 38013",
                        key=bus_edit_key,
                    )
                    current_bus = (
                        st.session_state.get(bus_edit_key, "").strip()
                        or piece.get("numero_autobus") or ""
                    )
                    geo_key = f"db_geo_r_{idx}"
                    _gcol, _rcol = st.columns([4, 1])
                    with _gcol:
                        geo_clicked = st.button(
                            "📍 Géolocaliser",
                            key=f"db_geo_{idx}",
                            disabled=not gtfs_info["rt_avail"],
                            help="Requiert vehiclePositions.pb (onglet GTFS)."
                                 if not gtfs_info["rt_avail"] else "",
                        )
                    with _rcol:
                        rt_refresh = st.button(
                            "🔄",
                            key=f"db_rt_refresh_{idx}",
                            help="Rafraîchir les données GTFS-RT",
                        )
                    if rt_refresh:
                        with st.spinner("Rafraîchissement GTFS-RT…"):
                            _rt_res = subprocess.run(
                                [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs_rt.py")],
                                capture_output=True, text=True,
                            )
                        if _rt_res.returncode == 0:
                            st.success("Données GTFS-RT mises à jour.")
                        else:
                            st.error("Erreur lors du rafraîchissement GTFS-RT.")
                            st.code(_rt_res.stderr)
                    if geo_clicked:
                        if not current_bus:
                            st.warning("Entrez un numéro d'autobus avant de géolocaliser.")
                        else:
                            with st.spinner("Recherche du véhicule…"):
                                try:
                                    vehicles = parse_vehicle_positions(
                                        gtfs_info["rt_pb"].read_bytes()
                                    )
                                    st.session_state[geo_key] = find_vehicle(
                                        current_bus, vehicles
                                    )
                                except Exception as e:
                                    st.error(f"Erreur GTFS-RT : {e}")
                                    st.session_state[geo_key] = None
                    if geo_key in st.session_state:
                        v = st.session_state[geo_key]
                        if v:
                            st.success(
                                f"Bus `{v.get('v_label') or v.get('v_id')}` — "
                                f"Lat {v['lat']:.5f}, Lon {v['lon']:.5f}"
                                + (f" — Ligne {v['route_id']}"
                                   if v.get("route_id") else "")
                            )
                            try:
                                import pandas as pd
                                st.map(
                                    pd.DataFrame([{"lat": v["lat"], "lon": v["lon"]}]),
                                    zoom=15,
                                )
                            except Exception:
                                st.markdown(
                                    f"[Voir sur Google Maps]"
                                    f"(https://www.google.com/maps?q={v['lat']},{v['lon']})"
                                )
                        else:
                            st.warning(
                                f"Bus `{current_bus}` introuvable dans les données GTFS-RT."
                            )

                with pc3:
                    releve = piece.get("releve") or {}
                    if releve.get("je_releve"):
                        r = releve["je_releve"]
                        st.caption(f"Relève : {r['nom']} ({r['matricule']})")
                    if releve.get("je_suis_releve_par"):
                        r = releve["je_suis_releve_par"]
                        st.caption(f"Relevé par : {r['nom']} ({r['matricule']})")

                # ── Trajets ───────────────────────────────────────────────────
                for ti, trajet in enumerate(piece.get("trajets", [])):
                    if trajet.get("type") == "haut_le_pied":
                        dep_t = trajet.get("depart",  {})
                        arr_t = trajet.get("arrivee", {})
                        st.markdown(
                            f"&nbsp;&nbsp;🚶 *Haut-le-pied* &ensp;"
                            f"`{dep_t.get('heure', '?')}` {dep_t.get('arret', '?')}"
                            f" → `{arr_t.get('heure', '?')}` {arr_t.get('arret', '?')}"
                        )
                        continue

                    if trajet.get("type") != "service":
                        continue

                    tl    = trajet.get("ligne", "?")
                    td    = (trajet.get("direction") or "").lower()
                    tid   = trajet.get("id_parcours")
                    dep_t = trajet.get("depart",  {})
                    arr_t = trajet.get("arrivee", {})
                    det_mark = " 🔀" if trajet.get("detour") else ""
                    notes    = trajet.get("notes_voyage", [])
                    note_txt = f"  *(note : {', '.join(notes)})*" if notes else ""

                    st.markdown(
                        f"&nbsp;&nbsp;🚌 **{tl} {td.capitalize()} ID {tid}**{det_mark}"
                        f" &ensp; `{dep_t.get('heure', '?')}` {dep_t.get('arret', '?')}"
                        f" → `{arr_t.get('heure', '?')}` {arr_t.get('arret', '?')}"
                        f"{note_txt}"
                    )

                    t_key = f"db_t_{idx}_{ti}"
                    out_rpt = (
                        RAPPORTS_DIR
                        / f"rapport-v2-{db_date_str}-{tl}-{td}-id{tid}.html"
                    )
                    tb1, tb2 = st.columns(2)
                    with tb1:
                        _rpt_btn = "🔄 Regénérer G-D" if out_rpt.exists() else "🗺️ Rapport G-D"
                        if st.button(_rpt_btn, key=f"{t_key}_rpt"):
                            st.session_state[f"{t_key}_rpt_run"] = True
                    with tb2:
                        if st.button("⚠️ Évènements", key=f"{t_key}_ev"):
                            ev_k = f"{t_key}_ev_open"
                            st.session_state[ev_k] = not st.session_state.get(ev_k, False)

                    # Rapport G-D pour ce trajet — génération si demandée
                    rpt_just_generated = False
                    if st.session_state.get(f"{t_key}_rpt_run"):
                        if not (DATA_DIR / "gtfs" / "gtfs_stm").exists():
                            st.warning("Données GTFS introuvables.")
                            st.session_state[f"{t_key}_rpt_run"] = False
                        else:
                            cmd = [
                                sys.executable,
                                str(SCRIPTS_DIR / "gen_rapport_v2.py"),
                                "--journee",          str(db_j_path),
                                "--filtre-ligne",     tl,
                                "--filtre-direction", td,
                                "--niveau",           db_rpt_niveau,
                                "--format",           "html",
                                "--output",           str(out_rpt),
                            ]
                            if tid is not None:
                                cmd += ["--filtre-id-parcours", str(tid)]
                            with st.spinner(
                                f"Génération rapport {tl} {td.capitalize()} ID {tid}…"
                            ):
                                rpt_res = subprocess.run(
                                    cmd, capture_output=True, text=True
                                )
                            if rpt_res.returncode == 0 and out_rpt.exists():
                                rpt_just_generated = True
                            else:
                                st.error("Erreur lors de la génération.")
                                st.code(rpt_res.stderr or rpt_res.stdout)
                            st.session_state[f"{t_key}_rpt_run"] = False

                    # Aperçu persistant : affiché dès que le fichier existe
                    if out_rpt.exists():
                        if rpt_just_generated:
                            st.success(
                                f"Rapport {tl} {td.capitalize()} ID {tid} généré."
                            )
                        rpt_html = out_rpt.read_bytes()
                        with st.expander(
                            f"Aperçu — {tl} {td.capitalize()} ID {tid}",
                            expanded=rpt_just_generated,
                        ):
                            components.html(
                                rpt_html.decode("utf-8"),
                                height=600, scrolling=True,
                            )

                    # Évènements pour ce trajet
                    if st.session_state.get(f"{t_key}_ev_open"):
                        evt_path_t = EVENTS_DIR / f"{tl}_{td}.json"
                        if not evt_path_t.exists():
                            st.info(f"Aucun fichier d'évènements pour {tl} {td}.")
                        else:
                            try:
                                evt_data_t = json.loads(
                                    evt_path_t.read_text(encoding="utf-8")
                                )
                                events_t = evt_data_t.get("detours", [])
                                tr_t = (
                                    (dep_t.get("heure"), arr_t.get("heure"))
                                    if dep_t.get("heure") and arr_t.get("heure")
                                    else None
                                )

                                # Instructions G-D du parcours (pour filtrage rues)
                                _ev_gd_instr: list = []
                                _ev_gd_file = GD_DIR / f"gd{tl}_{td}.json"
                                if _ev_gd_file.exists():
                                    try:
                                        _ev_raw  = json.loads(
                                            _ev_gd_file.read_text(encoding="utf-8")
                                        )
                                        _ev_all_p = (
                                            _ev_raw.get("routes") or [{}]
                                        )[0].get("parcours", [])
                                        _ev_parc = next(
                                            (p for p in _ev_all_p
                                             if p.get("id") == tid),
                                            _ev_all_p[0] if _ev_all_p else {},
                                        )
                                        _ev_gd_instr = _ev_parc.get("direction", [])
                                    except Exception:
                                        pass

                                # Stop IDs GTFS du parcours (mis en cache)
                                _ev_gtfs_dir = DATA_DIR / "gtfs" / "gtfs_stm"
                                _ev_stop_ids = (
                                    _cached_stop_ids_for_parcours(
                                        str(_ev_gtfs_dir), tl, td, tid
                                    )
                                    if _ev_gtfs_dir.exists() else None
                                )

                                with st.expander(
                                    f"Évènements — {tl} {td.capitalize()} ID {tid}",
                                    expanded=True,
                                ):
                                    if not events_t:
                                        st.caption("Aucun évènement enregistré.")
                                    for evt in events_t:
                                        applies_quart = _event_applies(
                                            evt, db_date_str, tr_t
                                        )
                                        applies_parc = _ev_applicable_parcours_tb(
                                            evt, _ev_stop_ids, _ev_gd_instr
                                        )
                                        applies = applies_quart and applies_parc
                                        eid   = evt.get("evenement_id", "?")
                                        titre = evt.get("titre", "(sans titre)")
                                        eff   = evt.get("effectif", "")
                                        d_deb = (evt.get("date_heure_debut") or "")[:10]
                                        d_fin = (evt.get("date_heure_fin")   or "")[:10]
                                        label = (
                                            f"{'✅' if applies else '⬜'}"
                                            f" #{eid} — {titre}"
                                        )
                                        with st.expander(label, expanded=applies):
                                            if not applies_quart:
                                                st.caption(
                                                    "⚠️ Non applicable à ce trajet "
                                                    "(plage de validité ou d'effectif)."
                                                )
                                            elif not applies_parc:
                                                st.caption(
                                                    "⚠️ Non applicable à ce parcours "
                                                    "(arrêts ou rues ne correspondent pas)."
                                                )
                                            if eff:
                                                st.caption(f"Effectif : {eff}")
                                            if d_deb:
                                                st.caption(
                                                    f"Période : {d_deb} → {d_fin or '?'}"
                                                )
                                            ann = evt.get("arrets_annules", [])
                                            ajt = evt.get("arrets_ajoutes", [])
                                            if ann:
                                                st.markdown("**Arrêts annulés :**")
                                                for a in ann:
                                                    if isinstance(a, str):
                                                        st.text(f"  ✖ {a}")
                                                    else:
                                                        nm = a.get("nom", a.get("code", "?"))
                                                        cd = a.get("code", "")
                                                        st.text(
                                                            f"  ✖ {nm}"
                                                            + (f" ({cd})" if cd else "")
                                                        )
                                            if ajt:
                                                st.markdown("**Arrêts ajoutés :**")
                                                for a in ajt:
                                                    if isinstance(a, str):
                                                        st.text(f"  ✚ {a}")
                                                    else:
                                                        nm = a.get("nom", a.get("code", "?"))
                                                        cd = a.get("code", "")
                                                        st.text(
                                                            f"  ✚ {nm}"
                                                            + (f" ({cd})" if cd else "")
                                                        )
                            except Exception as e:
                                st.error(f"Erreur lecture évènements : {e}")

        # ── Sauvegarde des numéros d'autobus ─────────────────────────────────
        st.divider()
        if st.button("💾 Enregistrer les numéros d'autobus", key="db_bus_save"):
            db_pieces_save = json.loads(json.dumps(db_j_data.get("pieces", [])))
            for save_idx in range(len(db_pieces_save)):
                bus_save_key = f"db_bus_edit_{db_date_str}_{save_idx}"
                val = st.session_state.get(bus_save_key, "").strip()
                db_pieces_save[save_idx]["numero_autobus"] = val or None
            db_j_data["pieces"] = db_pieces_save
            db_j_path.write_text(
                json.dumps(db_j_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            st.success("Numéros d'autobus sauvegardés.")
            st.rerun()

        # ── Données GTFS ──────────────────────────────────────────────────────
        st.divider()
        st.subheader("Données GTFS")
        c1, c2 = st.columns(2)
        c1.metric("GTFS statique",   gtfs_info["static_ts"])
        c2.metric("GTFS temps réel", gtfs_info["rt_ts"])


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Importation
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.header("Importation")
    imp_tabs = st.tabs(["📋 Carte Agent", "📅 Journée", "↔️ Gauche-Droite", "⚠️ Évènements", "📡 GTFS"])

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

    # ── 2b — Journée ─────────────────────────────────────────────────────────
    with imp_tabs[1]:
        st.markdown(
            "Collez le texte brut du **Détail de ma journée** (copié depuis l'interface STM). "
            "Le fichier `journee-YYYY-MM-DD.json` sera créé dans `data/journees/`. "
            "La journée importée apparaît ensuite dans le **Tableau de bord**."
        )

        col_jd, _ = st.columns([1, 3])
        with col_jd:
            j_imp_date = st.date_input("Date de la journée", value=date.today(), key="j_imp_date")

        j_text = st.text_area(
            "Texte brut",
            height=400,
            placeholder=(
                "Détail de ma journée\n"
                "Hier59200 - Frontenac\n"
                "Journée439\n"
                "Temps travaillé7:30\n"
                "Temps supplémentaire0:00\n"
                "Mis à jour le 17 juin 2026 00:32\n"
                "Sommaire24 - 1538013--3:18Horaire\n..."
            ),
            key="j_text",
        )

        if st.button("Importer", type="primary", key="j_imp_btn"):
            if not j_text.strip():
                st.warning("Le champ est vide.")
            else:
                from parse_journee import JourneeParser

                parser = JourneeParser(j_text, date_str=str(j_imp_date))
                result_j = parser.parse()

                if result_j:
                    saved_j = parser.save(result_j)
                    st.success(f"Journée du {j_imp_date} importée.")
                    st.code(parser.get_summary(result_j, saved_j))
                    st.balloons()
                else:
                    st.error("Échec du parsing.")
                    st.code(parser.get_summary())

    # ── 2c — Gauche-Droite ───────────────────────────────────────────────────
    with imp_tabs[2]:
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

    # ── 2d — Évènements ──────────────────────────────────────────────────────
    with imp_tabs[3]:
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

    # ── 2e — GTFS ────────────────────────────────────────────────────────────
    with imp_tabs[4]:
        from dashboard import get_gtfs_info as _imp_get_gtfs_info

        _imp_gtfs_path     = DATA_DIR / "gtfs" / "gtfs_stm"
        _imp_gtfs_manifest = DATA_DIR / "gtfs" / "gtfs_manifest.json"
        _imp_gtfs_info     = _imp_get_gtfs_info(DATA_DIR)

        if _imp_gtfs_manifest.exists():
            st.info(
                f"GTFS statique présent — dernier téléchargement le "
                f"{_imp_gtfs_info['static_ts']}"
            )
        else:
            st.warning(
                "Aucune donnée GTFS statique. Cliquez sur **Télécharger** pour initialiser."
            )

        gc1, gc2 = st.columns(2)
        gc1.metric("GTFS statique — dernier téléchargement", _imp_gtfs_info["static_ts"])
        gc2.metric("GTFS temps réel — dernier téléchargement", _imp_gtfs_info["rt_ts"])

        gcol1, gcol2 = st.columns(2)
        with gcol1:
            st.subheader("GTFS statique")
            st.caption("Données de lignes, arrêts et horaires (mis à jour hebdomadairement).")
            if st.button("Télécharger GTFS statique", key="gtfs_static_btn"):
                with st.spinner("Téléchargement en cours…"):
                    _res_static = subprocess.run(
                        [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs.py")],
                        capture_output=True, text=True,
                    )
                st.code(
                    _res_static.stdout
                    + ("\n" + _res_static.stderr if _res_static.stderr else "")
                )
                if _res_static.returncode == 0:
                    st.success("GTFS statique mis à jour.")
                else:
                    st.error("Erreur lors du téléchargement.")

        with gcol2:
            st.subheader("GTFS temps réel")
            st.caption(
                "Positions et retards en temps réel "
                "(nécessite une clé API STM dans `Installation/config/secrets.json`)."
            )
            if st.button("Télécharger GTFS-RT", key="gtfs_rt_btn"):
                with st.spinner("Téléchargement en cours…"):
                    _res_rt = subprocess.run(
                        [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs_rt.py")],
                        capture_output=True, text=True,
                    )
                st.code(
                    _res_rt.stdout
                    + ("\n" + _res_rt.stderr if _res_rt.stderr else "")
                )
                if _res_rt.returncode == 0:
                    st.success("GTFS-RT récupéré.")
                else:
                    st.error("Erreur lors du téléchargement.")


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Rapports
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.header("Rapports")
    rpt_tabs = st.tabs(["📄 Rapport journalier", "📊 Rapport v2 (journée)"])

    # ── 3a — Rapport journalier ───────────────────────────────────────────────
    with rpt_tabs[0]:
        st.markdown("Génère le PDF recto-verso (G-D + détours) à partir de la journée du jour.")

        rj_date = st.date_input("Date du rapport", value=date.today(), key="rj_date")
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
            with st.expander("📄 Aperçu PDF", expanded=rj_generated):
                components.html(
                    _pdf_embed_html(rj_out.read_bytes(), height=800),
                    height=820,
                )

    # ── 3b — Rapport v2 (journée) ────────────────────────────────────────────────
    with rpt_tabs[1]:
        st.markdown(
            "Génère un rapport G-D à partir d'une journée importée (`journee-YYYY-MM-DD.json`). "
            "Chaque groupe (ligne · direction · ID parcours) est traité séparément."
        )

        v2_journee_files = (
            sorted(JOURNEES_DIR.glob("journee-*.json"), reverse=True)
            if JOURNEES_DIR.exists() else []
        )

        if not v2_journee_files:
            st.info("Aucune journée disponible. Importez-en une dans l'onglet **Journées**.")
        else:
            v2_j_labels = [p.stem.replace("journee-", "") for p in v2_journee_files]
            v2_sel = st.selectbox(
                "Journée",
                range(len(v2_j_labels)),
                format_func=lambda i: v2_j_labels[i],
                key="rpt_v2_sel",
            )
            v2_j_path = v2_journee_files[v2_sel]

            try:
                v2_j_data = json.loads(v2_j_path.read_text(encoding="utf-8"))
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
            if v2_debuts and v2_fins:
                st.caption(
                    f"Plage du quart : **{min(v2_debuts)} → {max(v2_fins)}**"
                    f"  ·  Garage {v2_j_data.get('garage', '–')}"
                    f"  ·  Journée #{v2_j_data.get('journee_numero', '–')}"
                    f"  ·  Temps travaillé {v2_j_data.get('temps_travaille', '–')}"
                )

            # ── Groupes détectés (lecture inline) ─────────────────────────────
            v2_groupes = []
            v2_seen_g: dict = {}
            for _p in v2_pieces:
                for _t in _p.get("trajets", []):
                    if _t.get("type") != "service":
                        continue
                    _lg = _t.get("ligne") or ""
                    _dr = (_t.get("direction") or "").lower()
                    _ip = _t.get("id_parcours")
                    if not _lg or not _dr:
                        continue
                    _key = (_lg, _dr, _ip)
                    if _key not in v2_seen_g:
                        v2_seen_g[_key] = len(v2_groupes)
                        v2_groupes.append({
                            "ligne": _lg, "direction": _dr,
                            "id_parcours": _ip, "detour": _t.get("detour", False),
                        })
                    elif _t.get("detour"):
                        v2_groupes[v2_seen_g[_key]]["detour"] = True

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
                v2_fmt = st.radio("Format", ["pdf", "html"], horizontal=True, key="rpt_v2_fmt")
            with v2_col_c:
                v2_code = st.checkbox("Codes arrêts", value=False, key="rpt_v2_code")

            if st.button("Générer", type="primary", key="rpt_v2_btn"):
                RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)
                v2_date_str = v2_j_data.get("date", v2_j_labels[v2_sel])
                v2_out = RAPPORTS_DIR / f"rapport-v2-{v2_date_str}-{v2_niveau}.{v2_fmt}"

                cmd = [
                    sys.executable, str(SCRIPTS_DIR / "gen_rapport_v2.py"),
                    "--journee", str(v2_j_path),
                    "--niveau",  v2_niveau,
                    "--format",  v2_fmt,
                    "--output",  str(v2_out),
                ]
                if v2_code:
                    cmd.append("--codearret")

                with st.spinner("Génération en cours…"):
                    v2_result = subprocess.run(cmd, capture_output=True, text=True)

                v2_out_txt = v2_result.stdout + ("\n" + v2_result.stderr if v2_result.stderr else "")
                st.code(v2_out_txt)

                if v2_result.returncode == 0 and v2_out.exists():
                    st.success("Rapport généré.")
                    v2_mime = "text/html" if v2_fmt == "html" else "application/pdf"
                    st.download_button(
                        f"⬇️ Télécharger ({v2_fmt.upper()})",
                        data=v2_out.read_bytes(),
                        file_name=v2_out.name,
                        mime=v2_mime,
                        key="rpt_v2_dl",
                    )
                    if v2_fmt == "html":
                        with st.expander("Aperçu HTML"):
                            components.html(
                                v2_out.read_text(encoding="utf-8"),
                                height=600, scrolling=True,
                            )
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
        "📅 Journées",
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

    # ── Journées ──────────────────────────────────────────────────────────────
    with fm_tabs[4]:
        j_all = sorted(JOURNEES_DIR.glob("journee-*.json"), reverse=True) if JOURNEES_DIR.exists() else []
        st.caption(f"{len(j_all)} fichier(s) dans `data/journees/`")
        _file_manager("journee", j_all, mime="application/json")

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
                j_prev_data = json.loads(j_all[j_prev_sel].read_text(encoding="utf-8"))
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
