#!/usr/bin/env python3
"""
Interface Streamlit — Chauffeur STM
Onglets : Ma journée · Importation · Rapports · Fichiers · Logs
"""

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
    "🏠 Ma journée",
    "📥 Importation",
    "📊 Rapports",
    "🗂️ Fichiers",
    "📋 Logs",
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
# Tab 1 — Ma journée (orchestrateur : sélection unique + checklist + consultation)
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    from dashboard import (
        get_gtfs_info, get_gd_info, get_ca_info, parse_vehicle_positions, find_vehicle,
    )

    st.header("Ma journée")

    db_j_files = (
        sorted(JOURNEES_DIR.glob("journee-*.json"), reverse=True)
        if JOURNEES_DIR.exists() else []
    )

    if not db_j_files:
        st.info(
            "Aucune journée enregistrée. "
            "Importez-en une dans **📥 Importation › Journée**."
        )
    else:
        # ── Sélecteur UNIQUE de journée (source partagée journee_date) ─────────
        db_j_labels = [p.stem.replace("journee-", "") for p in db_j_files]
        # Purge d'une sélection périmée (journée supprimée entre deux reruns)
        if st.session_state.get("journee_date") not in db_j_labels:
            st.session_state.pop("journee_date", None)
        db_date_str = st.selectbox("Journée", db_j_labels, key="journee_date")
        db_j_path   = JOURNEES_DIR / f"journee-{db_date_str}.json"

        try:
            db_j_data = json.loads(db_j_path.read_text(encoding="utf-8"))
        except Exception as e:
            st.error(f"Erreur lecture journée : {e}")
            st.stop()

        # ── Checklist de préparation ──────────────────────────────────────────
        gtfs_info = get_gtfs_info(DATA_DIR)
        RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)

        from chauffeur.journee import lignes_de_service as _lignes_de_service
        _paires = _lignes_de_service(db_j_data)

        db_rpt_niveau = st.radio(
            "Niveau des rapports G-D",
            ["standard", "détaillé", "compact"],
            index=0, horizontal=True, key="db_rpt_niveau",
        )

        # États dérivés
        _gtfs_age = gtfs_info.get("static_age_days")
        _gtfs_ok  = _gtfs_age is not None and _gtfs_age <= 7
        _ca_info  = get_ca_info(CA_DIR, date.fromisoformat(db_date_str),
                                 db_j_data.get("journee_numero"))
        _ca_ok    = _ca_info["annotee"] is not None

        _gd_missing, _gd_stale = [], []
        _ev_missing = []
        for _lg, _dr in _paires:
            _gd = get_gd_info(GD_DIR, _lg, _dr)
            if not _gd["exists"]:
                _gd_missing.append((_lg, _dr))
            elif not _gd["fresh"]:
                _gd_stale.append((_lg, _dr, _gd["age_days"]))
            if not (EVENTS_DIR / f"{_lg}_{_dr}.json").exists():
                _ev_missing.append((_lg, _dr))

        _v2_present = bool(
            [p for p in RAPPORTS_DIR.glob(f"rapport-v2-{db_date_str}-*.html")
             if not re.search(r"-id\d+", p.stem)]
            + [p for p in RAPPORTS_DIR.glob(f"rapport-v2-{db_date_str}-*.pdf")
               if not re.search(r"-id\d+", p.stem)]
        ) if RAPPORTS_DIR.exists() else False
        _v1_present = (RAPPORTS_DIR / f"rapport-{db_date_str}.pdf").exists()

        with st.expander("✅ Préparation de la journée", expanded=False):
            from chauffeur.portail import SESSION_PATH as _CHK_SESS
            _sess_ok = _CHK_SESS.exists()
            _gtfs_present = (DATA_DIR / "gtfs" / "gtfs_stm").exists()

            # ── Actions chaînées ──────────────────────────────────────────────
            def _chain_gtfs():
                _r = subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs.py")],
                    capture_output=True, text=True)
                return _r.returncode == 0, _r

            def _chain_refresh_events():
                _r = subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / "refresh_events.py"),
                     "--journee", str(db_j_path), "--log"],
                    capture_output=True, text=True)
                st.session_state["ref_result_code"] = _r.returncode
                st.session_state["ref_result_out"] = (
                    _r.stdout + ("\n" + _r.stderr if _r.stderr else ""))
                return _r.returncode, _r

            def _check_cookie() -> bool:
                """Vérifie la validité du cookie (appel live) et l'affiche. True si valide."""
                with st.spinner("Vérification du cookie…"):
                    try:
                        from chauffeur.portail import is_session_valid
                        _ok, _msg = is_session_valid()
                    except Exception as _e:
                        _ok, _msg = False, str(_e)
                st.write(("✅ Cookie valide" if _ok else f"❌ Cookie invalide — {_msg}"))
                return _ok

            def _chain_gen_v2():
                from gen_rapport_v2 import generer_rapport as _gv2
                _gv2(db_j_path, fmt="html",
                     output=RAPPORTS_DIR / f"rapport-v2-{db_date_str}-{db_rpt_niveau}.html",
                     niveau=db_rpt_niveau)

            def _chain_gen_v1():
                _r = subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / "gen_rapport.py"),
                     "--date", db_date_str,
                     "--output", str(RAPPORTS_DIR / f"rapport-{db_date_str}.pdf")],
                    capture_output=True, text=True)
                return _r.returncode == 0, _r

            def _diff_summary(out: str) -> None:
                """Résumé compact des changements d'événements depuis le stdout."""
                retires  = [l for l in out.splitlines() if "🗑️" in l]
                remplaces = [l for l in out.splitlines()
                             if "remplacé" in l or "champs modifiés" in l]
                if not (retires or remplaces):
                    st.caption("Aucun changement d'événement détecté.")
                    return
                st.markdown(
                    f"**Changements :** {len(retires)} retiré·s · "
                    f"{len(remplaces)} remplacé·s / modifié·s")
                for l in retires + remplaces:
                    st.text(f"  {l.strip()}")

            ca1, ca2 = st.columns(2)
            with ca1:
                if st.button("🌙 Tout préparer (veille)", key="chk_prep_all",
                             use_container_width=True):
                    with st.status("Préparation de la journée…", expanded=False) as _stt:
                        if not _gtfs_ok:
                            st.write("① GTFS statique…")
                            ok, _r = _chain_gtfs()
                            if not ok:
                                _stt.update(label="Échec GTFS", state="error")
                                st.code(_r.stderr or _r.stdout)
                                st.stop()
                        if not _ca_ok:
                            st.write("② Carte agent : 🔒 upload requis (📥 Carte Agent) — ignoré.")
                        st.write(f"③ Journée : ✅ {db_date_str}")
                        if _gd_missing or _gd_stale:
                            st.write("④ G-D manquants/périmés : 🔒 collage requis (📥 Gauche-Droite) — ignoré.")
                        if _sess_ok:
                            st.write("⑤ Cookie…")
                            if not _check_cookie():
                                _stt.update(label="Cookie invalide", state="error")
                                st.error("Renouvelez vos cookies (📥 Évènements).")
                                st.stop()
                            st.write("⑤ Événements…")
                            rc, _r = _chain_refresh_events()
                            if rc == 2:
                                _stt.update(label="Session expirée", state="error")
                                st.error("Renouvelez vos cookies (📥 Évènements).")
                                st.stop()
                            _diff_summary(st.session_state.get("ref_result_out", ""))
                        else:
                            st.write("⑤ Événements : 🔒 session requise (📥 Évènements) — ignoré.")
                        if _gtfs_present:
                            st.write("⑥ Rapport v2…")
                            try:
                                _chain_gen_v2()
                            except Exception as _e:
                                st.warning(f"Rapport v2 non généré : {_e}")
                            st.write("⑦ Rapport journalier…")
                            ok, _r = _chain_gen_v1()
                            if not ok:
                                st.warning("Rapport journalier non généré.")
                        else:
                            st.write("⑥⑦ Rapports : GTFS requis — ignorés.")
                        _stt.update(label="Préparation terminée", state="complete")
                    st.rerun()
            with ca2:
                if st.button("🚀 Tout rafraîchir (avant départ)", key="chk_refresh_all",
                             use_container_width=True, disabled=not _sess_ok,
                             help="" if _sess_ok else "Session requise (📥 Évènements)."):
                    with st.status("Rafraîchissement…", expanded=True) as _stt:
                        st.write("⑤ Cookie…")
                        if not _check_cookie():
                            _stt.update(label="Cookie invalide", state="error")
                            st.error("Renouvelez vos cookies (📥 Évènements).")
                            st.stop()
                        st.write("⑤ Événements…")
                        rc, _r = _chain_refresh_events()
                        if rc == 2:
                            _stt.update(label="Session expirée", state="error")
                            st.error("Renouvelez vos cookies (📥 Évènements).")
                            st.stop()
                        _diff_summary(st.session_state.get("ref_result_out", ""))
                        if _gtfs_present:
                            st.write("⑥ Rapport v2…")
                            try:
                                _chain_gen_v2()
                            except Exception as _e:
                                st.warning(f"Rapport v2 non généré : {_e}")
                        else:
                            st.write("⑥ Rapport v2 : GTFS requis — ignoré.")
                        _stt.update(label="Rafraîchissement terminé", state="complete")
                    st.rerun()

            st.markdown("---")

            # 1 — GTFS
            c1, c2 = st.columns([7, 2])
            if _gtfs_ok:
                c1.markdown(f"✅ **GTFS statique frais** ({_gtfs_age} j)")
            elif _gtfs_age is not None:
                c1.markdown(f"⚠️ **GTFS statique périmé** ({_gtfs_age} j)")
            else:
                c1.markdown("⬜ **GTFS statique absent**")
            if not _gtfs_ok and c2.button("⬇️ GTFS", key="chk_gtfs"):
                with st.spinner("Téléchargement GTFS…"):
                    _r = subprocess.run(
                        [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs.py")],
                        capture_output=True, text=True,
                    )
                (st.success if _r.returncode == 0 else st.error)(
                    "GTFS mis à jour." if _r.returncode == 0 else "Échec GTFS.")
                st.code(_r.stdout + ("\n" + _r.stderr if _r.stderr else ""))

            # 2 — Carte agent annotée (action manuelle : upload)
            c1, c2 = st.columns([7, 2])
            if _ca_ok:
                _ca_msg = "✅ **Carte agent annotée présente**"
                if _ca_info["legacy"]:
                    _ca_msg += " (ancien import par date)"
                elif _ca_info["identite"]:
                    _n, _g, _j = _ca_info["identite"]
                    _ca_msg += f" (n° {_n} · {_g} · {_j} — réutilisable)"
                c1.markdown(_ca_msg)
            else:
                c1.markdown("🔒 **Carte agent non annotée**")
                c2.caption("→ 📥 Carte Agent")

            # 3 — Journée chargée
            st.markdown(f"✅ **Journée chargée** ({db_date_str})")

            # 4 — Gauche-Droite disponibles et récents (<90 j)
            c1, c2 = st.columns([7, 2])
            if not _paires:
                c1.markdown("⬜ **Aucune ligne de service**")
            elif _gd_missing:
                c1.markdown(
                    "🔒 **G-D manquants** : "
                    + ", ".join(f"{l} {d}" for l, d in _gd_missing))
                c2.caption("→ 📥 Gauche-Droite")
            elif _gd_stale:
                c1.markdown(
                    "⚠️ **G-D périmés (>90 j)** : "
                    + ", ".join(f"{l} {d} ({a} j)" for l, d, a in _gd_stale))
                c2.caption("→ 📥 Gauche-Droite")
            else:
                c1.markdown(f"✅ **Gauche-Droite à jour** ({len(_paires)} ligne·s)")

            # 5 — Événements extraits (fichier absent = « à extraire », pas « manquant » :
            #     un refresh valide sans évènement matérialise un fichier vide)
            c1, c2 = st.columns([7, 2])
            if not _paires:
                c1.markdown("⬜ **Aucune ligne de service**")
            elif _ev_missing:
                c1.markdown(
                    "⬜ **Événements à extraire** : "
                    + ", ".join(f"{l} {d}" for l, d in _ev_missing))
            else:
                c1.markdown(f"✅ **Événements extraits** ({len(_paires)} ligne·s)")
            if _paires and c2.button(
                "🔄 Événements", key="chk_events", disabled=not _sess_ok,
                help="" if _sess_ok else "Session requise (📥 Évènements).",
            ):
                if not _check_cookie():
                    st.error("Renouvelez vos cookies (📥 Évènements).")
                else:
                    _rc = [
                        sys.executable, str(SCRIPTS_DIR / "refresh_events.py"),
                        "--journee", str(db_j_path), "--log",
                    ]
                    with st.spinner("Rafraîchissement des événements…"):
                        _r = subprocess.run(_rc, capture_output=True, text=True)
                    st.session_state["ref_result_code"] = _r.returncode
                    st.session_state["ref_result_out"] = (
                        _r.stdout + ("\n" + _r.stderr if _r.stderr else ""))
                    if _r.returncode == 2:
                        st.error("Session expirée — renouvelez vos cookies (📥 Évènements).")
                    elif _r.returncode == 0:
                        st.success("Événements rafraîchis.")
                    else:
                        st.warning("Rafraîchissement partiel.")
                    if st.session_state["ref_result_out"].strip():
                        st.code(st.session_state["ref_result_out"])

            # 6 — Rapport v2
            c1, c2 = st.columns([7, 2])
            c1.markdown(
                "✅ **Rapport v2 présent**" if _v2_present
                else "⬜ **Rapport v2 non généré**")
            if c2.button("📊 Rapport v2", key="chk_v2",
                         disabled=not (DATA_DIR / "gtfs" / "gtfs_stm").exists(),
                         help="" if (DATA_DIR / "gtfs" / "gtfs_stm").exists()
                              else "GTFS requis."):
                from gen_rapport_v2 import generer_rapport as _gen_v2
                _v2_out = RAPPORTS_DIR / f"rapport-v2-{db_date_str}-{db_rpt_niveau}.html"
                with st.spinner("Génération du rapport v2…"):
                    try:
                        _gen_v2(db_j_path, fmt="html", output=_v2_out,
                                niveau=db_rpt_niveau)
                        st.success("Rapport v2 généré.")
                    except Exception as _e:
                        st.error(f"Erreur génération v2 : {_e}")

            # 7 — Rapport journalier (v1)
            c1, c2 = st.columns([7, 2])
            c1.markdown(
                "✅ **Rapport journalier présent**" if _v1_present
                else "⬜ **Rapport journalier non généré**")
            if c2.button("📄 Rapport v1", key="chk_v1"):
                _v1_out = RAPPORTS_DIR / f"rapport-{db_date_str}.pdf"
                with st.spinner("Génération du rapport journalier…"):
                    _r = subprocess.run(
                        [sys.executable, str(SCRIPTS_DIR / "gen_rapport.py"),
                         "--date", db_date_str, "--output", str(_v1_out)],
                        capture_output=True, text=True,
                    )
                if _r.returncode == 0 and _v1_out.exists():
                    st.success("Rapport journalier généré.")
                else:
                    st.error("Échec de la génération.")
                    st.code(_r.stdout + ("\n" + _r.stderr if _r.stderr else ""))

        st.divider()

        # ── Métriques résumé ──────────────────────────────────────────────────
        db_pieces = db_j_data.get("pieces", [])
        db_debut_all = [p.get("debut", "") for p in db_pieces if p.get("debut")]
        db_fin_all   = [p.get("fin",   "") for p in db_pieces if p.get("fin")]

        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Journée n°",      db_j_data.get("journee_numero", "–"))
        mc2.metric("Garage",          db_j_data.get("garage",         "–"))
        mc3.metric("Temps travaillé", db_j_data.get("temps_travaille","–"))
        mc4.metric("Prise début",      min(db_debut_all) if db_debut_all else "–")
        mc5.metric("Prise fin",       max(db_fin_all)   if db_fin_all   else "–")

        # ── Téléchargements ──────────────────────────────────────────────────
        annotee_file = _ca_info["annotee"]
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

        # ── Pièces de travail (consultation « En route ») ─────────────────────
        st.subheader("Pièces de travail")

        for idx, piece in enumerate(db_pieces):
            pid = piece.get("id", f"pièce-{idx + 1}")
            with st.expander(
                f"Pièce {pid}  —  {piece.get('debut', '?')} → {piece.get('fin', '?')}"
                f"  ({piece.get('duree', '?')})",
                expanded=False,
            ):
                pc1, pc2, pc3 = st.columns([2, 2, 2])

                with pc1:
                    from chauffeur.reference import lieu_point_releve as _lieu_pr
                    _garage = db_j_data.get("garage")

                    def _lieu_md(label, code):
                        code = code or "–"
                        lieu = _lieu_pr(code, _garage) if code != "–" else None
                        suffix = f" — {lieu}" if lieu else ""
                        return f"**{label} :** `{code}`{suffix}"

                    st.markdown(_lieu_md("Lieu prise", piece.get("lieu_prise")))
                    st.markdown(_lieu_md("Lieu fin", piece.get("lieu_fin")))

                with pc2:
                    bus_edit_key = f"db_bus_edit_{db_date_str}_{idx}"
                    bus_save_key = f"db_bus_save_{db_date_str}_{idx}"
                    _bcol, _scol = st.columns([5, 1])
                    with _bcol:
                        st.text_input(
                            "Numéro d'autobus",
                            value=piece.get("numero_autobus") or "",
                            placeholder="ex : 38013",
                            key=bus_edit_key,
                        )
                    with _scol:
                        st.markdown("<div style='margin-top:1.75rem'>", unsafe_allow_html=True)
                        if st.button("💾", key=bus_save_key, help="Enregistrer le numéro d'autobus"):
                            val = st.session_state.get(bus_edit_key, "").strip()
                            db_j_data["pieces"][idx]["numero_autobus"] = val or None
                            db_j_path.write_text(
                                json.dumps(db_j_data, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8",
                            )
                            st.success("Sauvegardé.")
                        st.markdown("</div>", unsafe_allow_html=True)
                    current_bus = (
                        st.session_state.get(bus_edit_key, "").strip()
                        or piece.get("numero_autobus") or ""
                    )
                    geo_key = f"db_geo_r_{idx}"
                    _rt_ts_key = "db_rt_last_fetch"
                    geo_clicked = st.button(
                        "📍 Géolocaliser",
                        key=f"db_geo_{idx}",
                        disabled=not gtfs_info["rt_avail"],
                        help="Requiert vehiclePositions.pb (onglet GTFS)."
                                 if not gtfs_info["rt_avail"] else "",
                    )
                    if geo_clicked:
                        if not current_bus:
                            st.warning("Entrez un numéro d'autobus avant de géolocaliser.")
                        else:
                            import time as _time
                            last_fetch = st.session_state.get(_rt_ts_key, 0)
                            if _time.time() - last_fetch >= 10:
                                with st.spinner("Rafraîchissement GTFS-RT…"):
                                    _rt_res = subprocess.run(
                                        [sys.executable, str(SCRIPTS_DIR / "fetch_gtfs_rt.py")],
                                        capture_output=True, text=True,
                                    )
                                if _rt_res.returncode == 0:
                                    st.session_state[_rt_ts_key] = _time.time()
                                else:
                                    st.error("Erreur lors du rafraîchissement GTFS-RT.")
                                    st.code(_rt_res.stderr)
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
                            from gen_rapport_v2 import generer_rapport as _gen_v2
                            with st.spinner(
                                f"Génération rapport {tl} {td.capitalize()} ID {tid}…"
                            ):
                                try:
                                    _gen_v2(
                                        db_j_path,
                                        fmt="html",
                                        output=out_rpt,
                                        niveau=db_rpt_niveau,
                                        filtre_ligne=tl,
                                        filtre_direction=td,
                                        filtre_id_parcours=tid,
                                    )
                                    rpt_just_generated = True
                                except Exception as _e:
                                    st.error(f"Erreur lors de la génération : {_e}")
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

    # ── Réserve (fonction future) ─────────────────────────────────────────────
    with st.expander("🅿️ Réserve — pré-appel / note spécifique (à venir)"):
        st.info(
            "Fonction à venir : chargement de la liste pré-appel, application des "
            "critères de préférence et génération de la note spécifique réserve."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Importation
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.header("Importation")
    imp_tabs = st.tabs(["📋 Carte Agent", "📅 Journée", "↔️ Gauche-Droite", "⚠️ Évènements", "📡 GTFS"])

    # ── 2a — Carte Agent ──────────────────────────────────────────────────────
    with imp_tabs[0]:
        from chauffeur.periodes import identite_ca, nom_ca

        st.markdown(
            "Déposez le PDF brut de votre carte agent. L'application l'annote (horaires "
            "GTFS surlignés) et la range par **identité** (numéro + liste + jour-type) — "
            "une même identité est réutilisée automatiquement entre journées, sans "
            "réimporter le PDF."
        )

        uploaded = st.file_uploader("Fichier carte agent (PDF)", type="pdf", key="ca_upload")

        col1, col2 = st.columns(2)
        with col1:
            ca_date = st.date_input(
                "Date représentative de la carte", value=date.today(), key="ca_date",
                help="Sert à calculer la liste et le jour-type (semaine/samedi/dimanche/"
                     "variation) via le calendrier de référence — pas seulement à nommer le fichier.",
            )
        with col2:
            no_gtfs = st.checkbox("Sans GTFS (surlignage seulement)", value=False, key="ca_no_gtfs")

        ca_remplacer = st.checkbox(
            "Remplacer une CA existante pour cette identité (version augmentée)",
            value=False, key="ca_remplacer",
        )
        ca_deja_annotee = st.checkbox(
            "Le PDF déposé est déjà annoté — le ranger tel quel (remplace uniquement "
            "la version annotée, sans relancer le traitement GTFS)",
            value=False, key="ca_deja_annotee",
        )

        btn_label = "Enregistrer la version annotée" if ca_deja_annotee else "Annoter la carte"
        if uploaded and st.button(btn_label, type="primary", key="ca_btn"):
            def _traiter_upload():
                CA_DIR.mkdir(parents=True, exist_ok=True)
                tmp_src = CA_DIR / f"_tmp_{uploaded.name}"
                tmp_out = None if ca_deja_annotee else CA_DIR / f"_tmp_annotee_{uploaded.name}"
                tmp_src.write_bytes(uploaded.read())

                def _nettoyer_tmp():
                    tmp_src.unlink(missing_ok=True)
                    if tmp_out:
                        tmp_out.unlink(missing_ok=True)

                if ca_deja_annotee:
                    cmd = [sys.executable, str(SCRIPTS_DIR / "carte_agent_stm.py"),
                           "--pdf", str(tmp_src), "--meta-only"]
                    spinner_msg = "Lecture des métadonnées…"
                else:
                    gtfs_path = DATA_DIR / "gtfs" / "gtfs_stm"
                    cmd = [sys.executable, str(SCRIPTS_DIR / "carte_agent_stm.py"),
                           "--pdf", str(tmp_src), "--out", str(tmp_out),
                           "--date", str(ca_date), "--json"]
                    if not no_gtfs and gtfs_path.exists():
                        cmd += ["--gtfs", str(gtfs_path)]
                    elif no_gtfs:
                        cmd.append("--no-gtfs")
                    spinner_msg = "Annotation en cours…"

                with st.spinner(spinner_msg):
                    result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode != 0:
                    st.error("Erreur lors du traitement.")
                    st.code(result.stderr or result.stdout)
                    _nettoyer_tmp()
                    return

                try:
                    meta = json.loads(result.stdout.strip().splitlines()[-1])
                    numero, groupe_id, jour_type = identite_ca(ca_date, meta["carte"])
                except (json.JSONDecodeError, IndexError, KeyError) as e:
                    st.error(f"Sortie inattendue du traitement : {e}")
                    st.code(result.stdout)
                    _nettoyer_tmp()
                    return
                except (FileNotFoundError, ValueError) as e:
                    st.error(f"Impossible de calculer l'identité de la carte : {e}")
                    _nettoyer_tmp()
                    return

                # Validation croisée (pas une source d'identité) : certaines cartes
                # impriment elles-mêmes leur jour-type ; on signale un écart sans bloquer.
                jt_imprime = meta.get("jour_type_imprime")
                if jt_imprime and jt_imprime != jour_type:
                    variante_txt = f" ({meta['variante']})" if meta.get("variante") else ""
                    st.warning(
                        f"⚠️ Écart calendrier/carte : identite_ca calcule jour_type="
                        f"« {jour_type} » pour cette date, mais la carte imprime "
                        f"« {jt_imprime} »{variante_txt} (En vigueur : "
                        f"{meta.get('en_vigueur') or '?'}). Vérifie le calendrier de "
                        "référence — l'identité retenue reste celle du calendrier."
                    )

                dest_out = CA_DIR / nom_ca(numero, groupe_id, jour_type, annotee=True)
                dest_src = None if ca_deja_annotee else CA_DIR / nom_ca(numero, groupe_id, jour_type)
                collision = dest_out.exists() or (dest_src is not None and dest_src.exists())

                if collision and not ca_remplacer:
                    st.error(
                        f"Une CA existe déjà pour cette identité (n° {numero} · "
                        f"{groupe_id} · {jour_type}). Cochez « Remplacer » ci-dessus "
                        "pour l'écraser."
                    )
                    _nettoyer_tmp()
                    return

                if collision:
                    for dest in filter(None, (dest_src, dest_out)):
                        if dest.exists():
                            dest.replace(dest.with_name(dest.name + ".bak"))

                if ca_deja_annotee:
                    tmp_src.replace(dest_out)
                    st.success(
                        f"Version annotée remplacée directement (sans traitement GTFS) "
                        f"— identité : n° {numero} · {groupe_id} · {jour_type}."
                    )
                else:
                    tmp_src.replace(dest_src)
                    tmp_out.replace(dest_out)
                    st.success(
                        f"Carte annotée et rangée — identité : n° {numero} · "
                        f"{groupe_id} · {jour_type}."
                    )

                st.download_button(
                    "⬇️ Télécharger la carte annotée",
                    data=dest_out.read_bytes(),
                    file_name=dest_out.name,
                    mime="application/pdf",
                    key="ca_dl",
                )

            _traiter_upload()

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
        # --- Rafraîchissement depuis le portail ---
        from chauffeur.portail import save_session, SESSION_PATH as _SESS_PATH

        st.subheader("Rafraîchissement depuis le portail")

        # Badge session (lecture fichier uniquement, pas d'appel HTTP)
        if _SESS_PATH.exists():
            try:
                _sess_data = json.loads(_SESS_PATH.read_text(encoding="utf-8"))
                _saved_at  = _sess_data.get("saved_at", "?")
                st.success(f"Session enregistrée le {_saved_at}")
            except Exception:
                st.warning("Fichier de session illisible")
        else:
            st.warning("Aucune session enregistrée")

        # Journée active partagée (choisie dans 🏠 Ma journée)
        _ref_date   = st.session_state.get("journee_date")
        _ref_j_path = (
            JOURNEES_DIR / f"journee-{_ref_date}.json" if _ref_date else None
        )
        if _ref_j_path and _ref_j_path.exists():
            st.caption(
                f"Journée active : **{_ref_date}** — changer dans **🏠 Ma journée**."
            )
            _rc2, _rc3 = st.columns([2, 2])
            with _rc2:
                _ref_restantes = st.checkbox(
                    "Restantes seulement",
                    value=True,
                    key="ref_restantes",
                    help="Saute les pièces dont l'heure de fin est dépassée.",
                )
            with _rc3:
                st.markdown("<div style='margin-top:1.75rem'>", unsafe_allow_html=True)
                _ref_disabled = not _SESS_PATH.exists()
                if st.button(
                    "🔄 Rafraîchir",
                    type="primary",
                    key="ref_btn",
                    disabled=_ref_disabled,
                    help="Session requise — enregistrez vos cookies ci-dessous." if _ref_disabled else "",
                ):
                    _ref_cmd = [
                        sys.executable, str(SCRIPTS_DIR / "refresh_events.py"),
                        "--journee", str(_ref_j_path),
                        "--log",
                    ]
                    if _ref_restantes:
                        _ref_cmd.append("--restantes")
                    with st.spinner("Rafraîchissement en cours…"):
                        _ref_res = subprocess.run(_ref_cmd, capture_output=True, text=True)
                    _ref_out = _ref_res.stdout + ("\n" + _ref_res.stderr if _ref_res.stderr else "")
                    st.session_state["ref_result_code"] = _ref_res.returncode
                    st.session_state["ref_result_out"]  = _ref_out
                st.markdown("</div>", unsafe_allow_html=True)

            # Résultat pleine largeur — affiché après le bloc de colonnes
            if "ref_result_code" in st.session_state:
                _rc = st.session_state["ref_result_code"]
                if _rc == 2:
                    st.error("Session expirée — renouvelez vos cookies ci-dessous.")
                elif _rc == 0:
                    st.success("Rafraîchissement terminé.")
                else:
                    st.warning("Rafraîchissement partiel (certaines lignes ont échoué).")
                _ref_out_saved = st.session_state.get("ref_result_out", "")
                if _ref_out_saved.strip():
                    st.code(_ref_out_saved)
        else:
            st.info(
                "Aucune journée active. Sélectionnez-en une dans **🏠 Ma journée** "
                "(ou importez-en une dans **📅 Journée**)."
            )

        with st.expander("🔑 Renouveler la session", expanded=not _SESS_PATH.exists()):
            st.caption(
                "Connectez-vous sur `employe.stm.info` dans votre navigateur, puis ouvrez les "
                "DevTools (F12) → onglet **Réseau** → cliquez sur n'importe quelle requête → "
                "onglet **En-têtes** → copiez la valeur complète du champ **cookie**."
            )
            _cookie_input = st.text_area(
                "Cookie (chaîne brute)",
                height=100,
                key="ref_cookie_input",
                placeholder="TS01846...=...; laravel_session=eyJ...; remember_web_...=eyJ...",
            )
            if st.button("Enregistrer la session", key="ref_cookie_save"):
                if _cookie_input.strip():
                    save_session(_cookie_input.strip())
                    st.success("Session enregistrée.")
                    st.rerun()
                else:
                    st.warning("Le champ est vide.")

        st.divider()

        # --- Import manuel (texte brut) ---
        st.subheader("Import manuel (texte brut)")
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
                    summary = parser.get_summary()
                    st.code(summary)
                    parser.append_log(summary)

                if all_ok:
                    st.balloons()

    # ── 2e — GTFS ────────────────────────────────────────────────────────────
    with imp_tabs[4]:
        from dashboard import get_gtfs_info as _imp_get_gtfs_info

        _imp_gtfs_path     = DATA_DIR / "gtfs" / "gtfs_stm"
        _imp_gtfs_manifest = DATA_DIR / "gtfs" / "gtfs_manifest.json"
        _imp_gtfs_info     = _imp_get_gtfs_info(DATA_DIR)

        if _imp_gtfs_manifest.exists():
            _imp_age = _imp_gtfs_info.get("static_age_days")
            if _imp_age is not None and _imp_age > 7:
                st.warning(
                    f"⚠️ GTFS statique périmé ({_imp_age} jours) — "
                    f"dernier téléchargement le {_imp_gtfs_info['static_ts']}. "
                    "Cliquez sur **Télécharger** pour mettre à jour."
                )
            else:
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

    # ── 3b — Rapport v2 (journée) ────────────────────────────────────────────────
    with rpt_tabs[1]:
        st.markdown(
            "Génère un rapport G-D à partir d'une journée importée (`journee-YYYY-MM-DD.json`). "
            "Chaque groupe (ligne · direction · ID parcours) est traité séparément."
        )

        # Journée active partagée (choisie dans 🏠 Ma journée)
        v2_date   = st.session_state.get("journee_date")
        v2_j_path = (
            JOURNEES_DIR / f"journee-{v2_date}.json" if v2_date else None
        )

        if not (v2_j_path and v2_j_path.exists()):
            st.info(
                "Aucune journée active. Sélectionnez-en une dans **🏠 Ma journée** "
                "(ou importez-en une dans **📅 Journée**)."
            )
        else:
            st.caption(
                f"Journée active : **{v2_date}** — changer dans **🏠 Ma journée**."
            )
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

            # ── Groupes détectés ──────────────────────────────────────────────
            from chauffeur.journee import groupes_de_service as _groupes_de_service
            v2_groupes = _groupes_de_service(v2_j_data)

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

                from gen_rapport_v2 import generer_rapport as _gen_v2
                with st.spinner("Génération en cours…"):
                    try:
                        _out = _gen_v2(
                            v2_j_path,
                            fmt=v2_fmt,
                            output=v2_out,
                            niveau=v2_niveau,
                            show_code=v2_code,
                        )
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
                                components.html(
                                    _out.read_text(encoding="utf-8"),
                                    height=600, scrolling=True,
                                )
                    except Exception as _e:
                        st.error(f"Erreur lors de la génération : {_e}")


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

    def _purge_older_than(files: list[Path], days: int) -> list[Path]:
        """Fichiers dont le mtime dépasse `days` jours (candidats à la purge)."""
        cutoff = datetime.now().timestamp() - days * 86400
        return [f for f in files if f.stat().st_mtime < cutoff]

    def _purge_ui(label: str, files: list[Path], days: int) -> None:
        """Bouton de purge des fichiers obsolètes (> `days`), avec confirmation."""
        candidats = _purge_older_than(files, days)
        annees = days // 365
        seuil_txt = f"{annees} an·s" if annees >= 1 else f"{days // 30} mois"
        st.divider()
        st.caption(
            f"🧹 **Entretien** — {len(candidats)} fichier(s) obsolète(s) "
            f"(> {seuil_txt})."
        )
        if not candidats:
            return
        confirm_key = f"fm_purge_confirm_{label}"
        if st.session_state.get(confirm_key):
            st.warning(
                "⚠️ Ces fichiers sont suivis par git ; la suppression modifie "
                "l'arbre de travail et devra être committée séparément."
            )
            for f in candidats:
                st.text(f"  • {f.name}  ({_fmt_mtime(f)})")
            pc1, pc2 = st.columns([1, 4])
            with pc1:
                if st.button("⚠️ Confirmer", key=f"fm_purge_ok_{label}"):
                    for f in candidats:
                        f.unlink(missing_ok=True)
                    del st.session_state[confirm_key]
                    st.rerun()
            with pc2:
                if st.button("Annuler", key=f"fm_purge_cancel_{label}"):
                    del st.session_state[confirm_key]
                    st.rerun()
        else:
            if st.button(
                f"🧹 Purger les {len(candidats)} fichier(s) obsolète(s)",
                key=f"fm_purge_{label}",
            ):
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
        _purge_ui("ca", ca_all, days=365)

    # ── Gauche-Droite ─────────────────────────────────────────────────────────
    with fm_tabs[1]:
        gd_all = sorted(GD_DIR.glob("gd*.json")) if GD_DIR.exists() else []
        st.caption(f"{len(gd_all)} fichier(s) dans `data/Gauche-Droite/`")
        _file_manager("gd", gd_all, mime="application/json")
        _purge_ui("gd", gd_all, days=365)

    # ── Évènements ────────────────────────────────────────────────────────────
    with fm_tabs[2]:
        ev_all = sorted(EVENTS_DIR.glob("*.json")) if EVENTS_DIR.exists() else []
        st.caption(f"{len(ev_all)} fichier(s) dans `data/Events/`")
        _file_manager("ev", ev_all, mime="application/json")
        _purge_ui("ev", ev_all, days=90)

    # ── Rapports journaliers ──────────────────────────────────────────────────
    with fm_tabs[3]:
        rp_all = sorted(RAPPORTS_DIR.glob("rapport-*.pdf"), reverse=True) if RAPPORTS_DIR.exists() else []
        st.caption(f"{len(rp_all)} fichier(s) dans `data/rapports/`")
        _file_manager("rp", rp_all, mime="application/pdf")
        _purge_ui("rp", rp_all, days=90)

    # ── Journées ──────────────────────────────────────────────────────────────
    with fm_tabs[4]:
        j_all = sorted(JOURNEES_DIR.glob("journee-*.json"), reverse=True) if JOURNEES_DIR.exists() else []
        st.caption(f"{len(j_all)} fichier(s) dans `data/journees/`")
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

        # ── Export CSV ────────────────────────────────────────────────────────
        st.divider()
        st.subheader("Export CSV")

        j_dates = sorted(date.fromisoformat(p.stem.replace("journee-", "")) for p in j_all)
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
                    jd = json.loads(p.read_text(encoding="utf-8"))
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
                fieldnames = ["date", "garage_id", "journee_numero", "piece_id"] + [
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


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 5 — Logs
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.header("Logs")

    LOG_DIR = DATA_DIR / "log"
    log_files = sorted(LOG_DIR.glob("*.log"), reverse=True) if LOG_DIR.exists() else []

    if not log_files:
        st.info(
            "Aucun fichier de log trouvé dans `data/log/`. "
            "Les logs sont créés lors de l'exécution des scripts avec l'option `--log`."
        )
    else:
        log_labels = [p.name for p in log_files]
        log_sel = st.selectbox(
            "Fichier de log",
            range(len(log_labels)),
            format_func=lambda i: log_labels[i],
            key="log_sel",
        )
        log_path = log_files[log_sel]

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
