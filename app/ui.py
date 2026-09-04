#!/usr/bin/env python3
"""
Interface Streamlit — Chauffeur STM
Onglets : Ma journée · Préparation d'une journée · Rapports · Fichiers · Logs
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
RAPPORTS_DIR = DATA_DIR / "rapports"
APP_DIR      = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(APP_DIR))

# Chemins, chargement et fraîcheur des données : source unique dans le noyau.
from chauffeur.depots import (  # noqa: E402
    CA_DIR, GD_DIR, EVENTS_DIR, JOURNEES_DIR,
    FRAICHEUR_GD_JOURS, FRAICHEUR_GTFS_JOURS,
    charger_evenements, charger_gd, charger_journee, sauvegarder_journee,
    chemin_evenements, chemin_journee,
    info_gd, info_gtfs, lister_journees_fenetre,
)
from chauffeur.effectif import bornes_quart  # noqa: E402
from chauffeur.evenements import trier_evenements_par_arrets  # noqa: E402
from chauffeur.journal import ecrire_bloc, lister_journaux  # noqa: E402
from chauffeur.preparation import (  # noqa: E402
    ResultatRafraichissement, ResultatRafraichissementGD,
    etat_rapport, finaliser_rapports, fusionner_rafraichissements,
    fusionner_rafraichissements_gd, generer_v2_et_marquer,
    importer_journee_portail, marquer_rapport_a_jour,
    rafraichir_evenements_journee, rafraichir_gd_journee,
)
from chauffeur.portail import (  # noqa: E402
    etat_session, valider_et_sauvegarder_session,
)
from chauffeur.presentation_evenements import (  # noqa: E402
    presenter_evenement, rendre_table_evenements_html,
)


# ── Utilitaires parcours / événements ────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _cached_arrets_pour_parcours(
    gtfs_dir_str: str, ligne: str, direction: str, id_parcours
) -> tuple[str, ...] | None:
    """Séquence des stop_ids GTFS d'un parcours (mise en cache par session).

    Retourne None si la résolution échoue (GTFS corrompu, ligne inconnue…) :
    « arrêts inconnus », qui déclenche le fail-safe d'applicabilité — à
    distinguer d'un tuple vide (« le GTFS a parlé : aucun arrêt »).
    """
    try:
        from chauffeur.gtfs import stops_for_parcours
        stops = stops_for_parcours(Path(gtfs_dir_str), ligne, direction, id_parcours)
        return tuple(sid for _, sid in stops)
    except Exception:
        return None


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
    "🧰 Préparation d'une journée",
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


@st.dialog("Renouveler la session employé STM")
def _dialog_session_portail() -> None:
    st.caption(
        "Reconnectez-vous sur employe.stm.info, puis copiez la valeur complète "
        "de l'en-tête `cookie` depuis les outils réseau du navigateur."
    )
    cookie = st.text_input(
        "Cookie",
        type="password",
        key="session_cookie_dialog",
        placeholder="TS01846…; laravel_session=…",
    )
    c1, c2 = st.columns(2)
    if c1.button("Valider et reprendre", type="primary", use_container_width=True):
        if not cookie.strip():
            st.warning("Le champ est vide.")
        else:
            with st.spinner("Validation de la session…"):
                ok, message = valider_et_sauvegarder_session(cookie.strip())
            if ok:
                st.session_state.pop("session_cookie_dialog", None)
                pending = st.session_state.get("operation_portail")
                if pending:
                    pending["reprendre"] = True
                st.session_state["ouvrir_dialog_session"] = False
                st.rerun()
            else:
                st.error(message)
    if c2.button("Annuler", use_container_width=True):
        st.session_state.pop("operation_portail", None)
        st.session_state["ouvrir_dialog_session"] = False
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Ma journée (orchestrateur : sélection unique + checklist + consultation)
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    from chauffeur.ca import resoudre_ca
    from chauffeur.gtfs_rt import parse_vehicle_positions, find_vehicle

    st.header("Ma journée")

    _journees_fenetre = lister_journees_fenetre(date.today()) if JOURNEES_DIR.exists() else []
    db_j_files = [path for _, path in _journees_fenetre]

    if not db_j_files:
        st.info(
            "Aucune journée enregistrée. "
            "Importez-en une dans **🧰 Préparation d'une journée**."
        )
    else:
        # ── Sélecteur UNIQUE de journée (source partagée journee_date) ─────────
        db_j_labels = [p.stem.replace("journee-", "") for p in db_j_files]
        # Purge d'une sélection périmée (journée supprimée entre deux reruns)
        if st.session_state.get("journee_date") not in db_j_labels:
            st.session_state.pop("journee_date", None)
        _today_label = date.today().isoformat()
        _default_idx = (
            db_j_labels.index(_today_label)
            if _today_label in db_j_labels
            else min(
                range(len(db_j_labels)),
                key=lambda i: abs((date.fromisoformat(db_j_labels[i]) - date.today()).days),
            )
        )
        db_date_str = st.selectbox(
            "Journée", db_j_labels, index=_default_idx, key="journee_date"
        )
        db_j_path   = chemin_journee(db_date_str)

        try:
            db_j_data = charger_journee(db_j_path)
        except Exception as e:
            st.error(f"Erreur lecture journée : {e}")
            st.stop()

        # ── Rafraîchissement du jour ─────────────────────────────────────────
        gtfs_info = info_gtfs()
        RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)

        from chauffeur.journee import lignes_de_service as _lignes_de_service
        _paires = _lignes_de_service(db_j_data)
        db_rpt_niveau = "détaillé"
        _ca_info = resoudre_ca(
            date.fromisoformat(db_date_str), db_j_data.get("journee_numero")
        )

        st.subheader("Rafraîchir les données du jour")
        _session_info = etat_session()
        _session_icon = {
            "absente": "⬜", "non_verifiee": "🟡",
            "valide": "✅", "expiree": "❌",
        }.get(_session_info.statut, "⬜")
        st.caption(
            f"{_session_icon} Session portail — {_session_info.message}. "
            "La validité est contrôlée juste avant la récupération."
        )

        _est_aujourdhui = db_date_str == date.today().isoformat()
        _pending = st.session_state.get("operation_portail")
        _reprendre_db = bool(
            _pending
            and _pending.get("type") == "ma_journee"
            and _pending.get("date") == db_date_str
            and _pending.get("reprendre")
        )
        _refresh_clicked = st.button(
            "🔄 Rafraîchir les lignes restantes",
            type="primary",
            key="db_refresh_events",
            disabled=not _est_aujourdhui or not _paires,
            help=(
                "" if _est_aujourdhui
                else "Le rafraîchissement des lignes restantes est réservé à aujourd’hui."
            ),
        )

        if _refresh_clicked or _reprendre_db:
            _precedent = None
            _paires_refresh = None
            if _reprendre_db:
                _precedent = ResultatRafraichissement.from_dict(
                    _pending.get("resultat", {})
                )
                _paires_refresh = _precedent.restantes
                _pending["reprendre"] = False
            with st.status("Rafraîchissement des événements…", expanded=True) as _status:
                _nouveau = rafraichir_evenements_journee(
                    db_j_data,
                    restantes_seulement=True,
                    paires=_paires_refresh,
                    log=True,
                )
                _resultat = fusionner_rafraichissements(_precedent, _nouveau)
                _afficher_resultat_rafraichissement(_nouveau)
                if _nouveau.session_expiree:
                    st.session_state["operation_portail"] = {
                        "type": "ma_journee",
                        "date": db_date_str,
                        "resultat": _resultat.to_dict(),
                        "reprendre": False,
                    }
                    st.session_state["ouvrir_dialog_session"] = True
                    _status.update(label="Session à renouveler", state="error")
                elif not _resultat.succes_complet:
                    st.session_state.pop("operation_portail", None)
                    st.session_state["db_refresh_result"] = _resultat.to_dict()
                    _status.update(label="Rafraîchissement partiel", state="error")
                else:
                    st.session_state.pop("operation_portail", None)
                    if _resultat.modifie:
                        st.write("Des événements ont changé — génération du v2 détaillé…")
                        _rapport = generer_v2_et_marquer(
                            db_j_path, niveau="détaillé", rapports_dir=RAPPORTS_DIR
                        )
                        st.session_state["db_refresh_report"] = {
                            "statut": _rapport.statut, "message": _rapport.message
                        }
                        if _rapport.statut == "erreur":
                            st.error(_rapport.message)
                    else:
                        st.caption("Aucun changement — le rapport existant est conservé.")
                    st.session_state["db_refresh_result"] = _resultat.to_dict()
                    _status.update(label="Rafraîchissement terminé", state="complete")

        if st.session_state.get("db_refresh_result"):
            _afficher_resultat_rafraichissement(
                ResultatRafraichissement.from_dict(
                    st.session_state["db_refresh_result"]
                )
            )

        st.divider()

        # ── Métriques résumé ──────────────────────────────────────────────────
        db_pieces = db_j_data.get("pieces", [])
        db_debut_all = [p.get("debut", "") for p in db_pieces if p.get("debut")]
        db_fin_all   = [p.get("fin",   "") for p in db_pieces if p.get("fin")]
        db_bornes_deb = bornes_quart(db_debut_all, date.fromisoformat(db_date_str))
        db_bornes_fin = bornes_quart(db_fin_all,   date.fromisoformat(db_date_str))

        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Journée n°",      db_j_data.get("journee_numero", "–"))
        mc2.metric("Garage",          db_j_data.get("garage",         "–"))
        mc3.metric("Temps travaillé", db_j_data.get("temps_travaille","–"))
        mc4.metric("Prise début",      db_bornes_deb[0] if db_bornes_deb else "–")
        mc5.metric("Prise fin",       db_bornes_fin[1] if db_bornes_fin else "–")

        # ── Notes (carte agent + journée) ─────────────────────────────────────
        from chauffeur.ca import cle_note_carte as _cle_note_carte
        from chauffeur.notes import (
            note_carte as _note_carte,
            note_journee as _note_journee,
            sauvegarder_note_carte as _save_note_carte,
            sauvegarder_note_journee as _save_note_journee,
        )

        nn1, nn2 = st.columns(2)
        with nn1:
            _cle_ca = _cle_note_carte(_ca_info)
            if _cle_ca is None:
                st.caption("Aucune carte agent résolue pour cette journée.")
            else:
                note_c = _note_carte(_cle_ca) or {}
                st.text_area(
                    "📝 Note carte agent",
                    value=note_c.get("note", ""),
                    help="Suit la carte : réutilisée aux journées partageant "
                         "cette liste/jour-type (identité n°_liste_jour).",
                    key=f"db_note_ca_edit_{db_date_str}_{_cle_ca}",
                )
                if st.button("💾 Enregistrer", key=f"db_note_ca_save_{db_date_str}_{_cle_ca}"):
                    _save_note_carte(
                        _cle_ca,
                        st.session_state.get(f"db_note_ca_edit_{db_date_str}_{_cle_ca}", ""),
                    )
                    st.rerun()
                if note_c.get("maj"):
                    st.caption(f"Mise à jour : {note_c['maj']}")
        with nn2:
            note_j = _note_journee(db_date_str) or {}
            st.text_area(
                "📝 Note journée",
                value=note_j.get("note", ""),
                help="Note propre à cette journée.",
                key=f"db_note_journee_edit_{db_date_str}",
            )
            if st.button("💾 Enregistrer", key=f"db_note_journee_save_{db_date_str}"):
                _save_note_journee(
                    db_date_str,
                    st.session_state.get(f"db_note_journee_edit_{db_date_str}", ""),
                )
                st.rerun()
            if note_j.get("maj"):
                st.caption(f"Mise à jour : {note_j['maj']}")

        # ── Aperçu du dernier rapport v2 complet ─────────────────────────────
        _v2_html = sorted(
            RAPPORTS_DIR.glob(f"rapport-v2-{db_date_str}-*.html"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        ) if RAPPORTS_DIR.exists() else []
        _v2_html_jour = [p for p in _v2_html if not re.search(r"-id\d+", p.stem)]
        latest_html_jour = _v2_html_jour[0] if _v2_html_jour else None

        if latest_html_jour:
            with st.expander(f"📊 Rapport v2 — Aperçu  ({latest_html_jour.name})"):
                components.html(
                    latest_html_jour.read_text(encoding="utf-8"),
                    height=600, scrolling=True,
                )
        else:
            st.caption("Aucun rapport v2 complet à prévisualiser pour cette journée.")

        st.divider()

        # ── Pièces de travail (consultation « En route ») ─────────────────────
        st.subheader("Pièces de travail")

        for idx, piece in enumerate(db_pieces):
            pid = piece.get("id", f"pièce-{idx + 1}")
            type_piece = " — TS continu" if piece.get("type_horaire") == "continu" else ""
            with st.expander(
                f"Pièce {pid}{type_piece}  —  {piece.get('debut', '?')} → {piece.get('fin', '?')}"
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
                            sauvegarder_journee(db_j_path, db_j_data)
                            st.success("Sauvegardé.")
                        st.markdown("</div>", unsafe_allow_html=True)
                    current_bus = (
                        st.session_state.get(bus_edit_key, "").strip()
                        or piece.get("numero_autobus") or ""
                    )

                    if current_bus:
                        from chauffeur.notes import note_voiture as _note_voiture
                        from chauffeur.notes import sauvegarder_note_voiture as _save_note_voiture

                        note_v = _note_voiture(current_bus)
                        note_v_key  = f"db_note_voiture_edit_{db_date_str}_{idx}"
                        note_v_save = f"db_note_voiture_save_{db_date_str}_{idx}"
                        _nvcol, _nvscol = st.columns([5, 1])
                        with _nvcol:
                            st.text_area(
                                f"Note — bus {current_bus}",
                                value=(note_v or {}).get("note", ""),
                                height=68,
                                key=note_v_key,
                            )
                        with _nvscol:
                            st.markdown("<div style='margin-top:1.75rem'>", unsafe_allow_html=True)
                            if st.button("💾", key=note_v_save, help="Enregistrer la note du bus"):
                                _save_note_voiture(current_bus, st.session_state.get(note_v_key, ""))
                                st.success("Note sauvegardée.")
                            st.markdown("</div>", unsafe_allow_html=True)
                        if note_v and note_v.get("maj"):
                            st.caption(f"Mise à jour : {note_v['maj']}")

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
                    from chauffeur.notes import note_matricule as _note_matricule
                    from chauffeur.notes import sauvegarder_note_matricule as _save_note_matricule

                    releve = piece.get("releve") or {}
                    for _rk, _label in (
                        ("je_releve", "Relève"), ("je_suis_releve_par", "Relevé par"),
                    ):
                        r = releve.get(_rk)
                        if not r:
                            continue
                        _mat = r.get("matricule") or ""
                        _suffixe_mat = f" ({_mat})" if _mat else ""
                        st.caption(f"{_label} : {r['nom']}{_suffixe_mat}")
                        if not _mat:
                            continue
                        note_m = _note_matricule(_mat)
                        note_m_key  = f"db_note_mat_edit_{db_date_str}_{idx}_{_rk}"
                        note_m_save = f"db_note_mat_save_{db_date_str}_{idx}_{_rk}"
                        st.text_area(
                            f"Note — {r['nom']}",
                            value=(note_m or {}).get("note", ""),
                            height=68,
                            key=note_m_key,
                        )
                        if st.button("💾 Enregistrer", key=note_m_save):
                            _save_note_matricule(
                                _mat, st.session_state.get(note_m_key, ""), nom=r["nom"]
                            )
                            st.success("Note sauvegardée.")
                        if note_m and note_m.get("maj"):
                            st.caption(f"Mise à jour : {note_m['maj']}")

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
                        if not chemin_evenements(tl, td).exists():
                            st.info(f"Aucun fichier d'évènements pour {tl} {td}.")
                        else:
                            try:
                                events_t = charger_evenements(tl, td)
                                tr_t = (
                                    (dep_t.get("heure"), arr_t.get("heure"))
                                    if dep_t.get("heure") and arr_t.get("heure")
                                    else None
                                )

                                # Instructions G-D du parcours (pour filtrage rues)
                                try:
                                    _ev_gd_instr = charger_gd(tl, td, tid)[0]
                                except Exception:
                                    _ev_gd_instr = []

                                # Stop IDs GTFS du parcours (mis en cache) —
                                # None = inconnus (GTFS absent ou en erreur) → fail-safe
                                _ev_gtfs_dir = DATA_DIR / "gtfs" / "gtfs_stm"
                                _ev_arrets_ordonnes = (
                                    _cached_arrets_pour_parcours(
                                        str(_ev_gtfs_dir), tl, td, tid
                                    )
                                    if _ev_gtfs_dir.exists() else None
                                )
                                _ev_stop_ids = (
                                    frozenset(_ev_arrets_ordonnes)
                                    if _ev_arrets_ordonnes is not None else None
                                )
                                events_t = trier_evenements_par_arrets(
                                    events_t, _ev_arrets_ordonnes or ()
                                )

                                from chauffeur.evenements import applicable_a_la_plage
                                from chauffeur.gd import event_applicable_to_parcours

                                with st.expander(
                                    f"Évènements — {tl} {td.capitalize()} ID {tid}",
                                    expanded=True,
                                ):
                                    if not events_t:
                                        st.caption("Aucun évènement enregistré.")
                                    affichages = []
                                    for evt in events_t:
                                        applies_quart = applicable_a_la_plage(
                                            evt, date.fromisoformat(db_date_str), tr_t
                                        )
                                        applies_parc = event_applicable_to_parcours(
                                            evt, _ev_stop_ids, _ev_gd_instr
                                        )
                                        applies = applies_quart and applies_parc
                                        if not applies_quart:
                                            raison = (
                                                "Hors plage de validité ou d'effectif "
                                                "du trajet."
                                            )
                                        elif not applies_parc:
                                            raison = (
                                                "Les arrêts ou les rues ne correspondent "
                                                "pas à ce parcours."
                                            )
                                        else:
                                            raison = ""
                                        affichages.append(presenter_evenement(
                                            evt,
                                            applicable=applies,
                                            raison_exclusion=raison,
                                        ))
                                    if affichages:
                                        st.markdown(
                                            rendre_table_evenements_html(affichages),
                                            unsafe_allow_html=True,
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
# Tab 2 — Préparation d'une journée
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.header("Préparation d'une journée")
    if st.session_state.get("prep_flash"):
        st.success(st.session_state.pop("prep_flash"))
    _prep_date = st.date_input(
        "Date à préparer", value=date.today(), key="prep_date"
    )
    _prep_date_str = str(_prep_date)
    _prep_path = chemin_journee(_prep_date_str)
    _prep_data = None
    _prep_error = None
    if _prep_path.exists():
        try:
            _prep_data = charger_journee(_prep_path)
        except Exception as _e:
            _prep_error = str(_e)

    from chauffeur.ca import resoudre_ca as _prep_resoudre_ca
    from chauffeur.journee import lignes_de_service as _prep_lignes
    _prep_paires = _prep_lignes(_prep_data) if _prep_data else []
    _prep_ca = (
        _prep_resoudre_ca(_prep_date, _prep_data.get("journee_numero"))
        if _prep_data else {"annotee": None}
    )
    _prep_gd_missing = [
        (ligne, direction) for ligne, direction in _prep_paires
        if not info_gd(ligne, direction)["exists"]
    ]
    _prep_gd_stale = [
        (ligne, direction, info_gd(ligne, direction)["age_days"])
        for ligne, direction in _prep_paires
        if info_gd(ligne, direction)["exists"] and not info_gd(ligne, direction)["fresh"]
    ]
    _prep_events_missing = [
        (ligne, direction) for ligne, direction in _prep_paires
        if not chemin_evenements(ligne, direction).exists()
    ]
    _prep_gtfs = info_gtfs()
    _prep_gtfs_present = (DATA_DIR / "gtfs" / "gtfs_stm").exists()
    _prep_session = etat_session()
    _prep_rj = _prep_v2 = None
    if _prep_data and not _prep_error:
        try:
            _prep_rj = etat_rapport(_prep_path, "journalier", rapports_dir=RAPPORTS_DIR)
            _prep_v2 = etat_rapport(
                _prep_path, "v2", niveau="standard", rapports_dir=RAPPORTS_DIR
            )
        except Exception as _e:
            _prep_error = str(_e)

    st.subheader("État de la préparation")
    _s1, _s2, _s3, _s4 = st.columns(4)
    _s1.markdown("✅ **Journée**" if _prep_data else "⬜ **Journée absente**")
    _s2.markdown("✅ **Carte agent**" if _prep_ca.get("annotee") else "⚠️ **Carte agent absente**")
    if _prep_gtfs_present:
        _gtfs_age = _prep_gtfs.get("static_age_days")
        _s3.markdown(
            f"{'✅' if _gtfs_age is not None and _gtfs_age <= FRAICHEUR_GTFS_JOURS else '⚠️'} "
            f"**GTFS statique**" + (f" ({_gtfs_age} j)" if _gtfs_age is not None else "")
        )
    else:
        _s3.markdown("⛔ **GTFS absent**")
    _prep_session_icon = {
        "valide": "✅", "non_verifiee": "🟡", "expiree": "❌", "absente": "⬜",
    }.get(_prep_session.statut, "⬜")
    _s4.markdown(
        f"{_prep_session_icon} **Session portail** — {_prep_session.message}"
    )
    _s5, _s6, _s7 = st.columns(3)
    if _prep_gd_missing:
        _s5.markdown("⛔ **G-D manquants** — " + ", ".join(f"{l} {d}" for l, d in _prep_gd_missing))
    elif _prep_gd_stale:
        _s5.markdown("⚠️ **G-D périmés** — " + ", ".join(f"{l} {d}" for l, d, _ in _prep_gd_stale))
    else:
        _s5.markdown("✅ **G-D disponibles**" if _prep_paires else "⬜ **G-D à déterminer**")
    _s6.markdown(
        "⚠️ **Événements incomplets**" if _prep_events_missing
        else ("✅ **Événements présents**" if _prep_paires else "⬜ **Événements à déterminer**")
    )
    _statut_lisible = {
        "a_jour": "à jour", "obsolete": "obsolète", "absent": "absent",
    }
    _s7.markdown(
        f"**Rapports** — journalier: "
        f"{_statut_lisible.get(_prep_rj.statut, _prep_rj.statut) if _prep_rj else 'à déterminer'}; "
        f"v2: {_statut_lisible.get(_prep_v2.statut, _prep_v2.statut) if _prep_v2 else 'à déterminer'}"
    )
    if _prep_error:
        st.error(f"Erreur de préparation : {_prep_error}")
    st.divider()

    # ── 2a — Journée ─────────────────────────────────────────────────────────
    with st.expander("1 — Importer la journée", expanded=not bool(_prep_data)):
        st.markdown(
            "Récupérez le **Détail de ma journée** depuis une session STM valide. "
            "Le fichier `journee-YYYY-MM-DD.json` sera créé dans `data/journees/`."
        )

        j_imp_date = _prep_date
        st.caption(f"Date de la journée : **{j_imp_date}**")

        _j_pending = st.session_state.get("operation_portail")
        _j_reprende = bool(
            _j_pending
            and _j_pending.get("type") == "import_journee"
            and _j_pending.get("date") == _prep_date_str
            and _j_pending.get("reprendre")
        )
        _j_auto = st.button(
            "🌐 Récupérer depuis STM", type="primary", key="j_auto_btn"
        )
        if _j_auto or _j_reprende:
            if _j_reprende:
                _j_pending["reprendre"] = False
            with st.spinner("Récupération de la journée…"):
                _j_resultat = importer_journee_portail(j_imp_date, log=True)
            if _j_resultat.session_expiree:
                st.session_state["operation_portail"] = {
                    "type": "import_journee",
                    "date": _prep_date_str,
                    "reprendre": False,
                }
                st.session_state["ouvrir_dialog_session"] = True
                st.warning("Session expirée — renouvellement requis.")
            elif _j_resultat.succes:
                st.session_state.pop("operation_portail", None)
                st.session_state["prep_flash"] = (
                    f"Journée du {j_imp_date} récupérée depuis STM."
                )
                st.rerun()
            else:
                st.session_state.pop("operation_portail", None)
                st.error(_j_resultat.message or "Échec de la récupération.")

        st.divider()
        st.caption("Import manuel de secours")
        st.markdown(
            "Collez le texte brut du **Détail de ma journée** copié depuis l'interface STM."
        )

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
                    resume_j = parser.get_summary(result_j, saved_j)
                    ecrire_bloc("parse_journee", resume_j)
                    st.session_state["prep_flash"] = f"Journée du {j_imp_date} importée."
                    st.rerun()
                else:
                    resume_j = parser.get_summary()
                    st.error("Échec du parsing.")
                    st.code(resume_j)
                    ecrire_bloc("parse_journee", resume_j)

    # ── 2b — Carte Agent ──────────────────────────────────────────────────────
    with st.expander("2 — Importer ou vérifier la carte agent", expanded=bool(_prep_data and not _prep_ca.get("annotee"))):
        from chauffeur.ca import ranger_ca
        from chauffeur.periodes import identite_ca

        st.markdown(
            "Déposez le PDF brut de votre carte agent. L'application l'annote (horaires "
            "GTFS surlignés) et la range par **identité** (numéro + liste + jour-type) — "
            "une même identité est réutilisée automatiquement entre journées, sans "
            "réimporter le PDF."
        )

        uploaded = st.file_uploader("Fichier carte agent (PDF)", type="pdf", key="ca_upload")

        ca_date = _prep_date
        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"Date représentative de la carte : **{ca_date}**")
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
                    sortie = result.stderr or result.stdout
                    st.error("Erreur lors du traitement.")
                    st.code(sortie)
                    ecrire_bloc("carte_agent",
                                f"❌ Échec du traitement de {uploaded.name}\n{sortie}")
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

                try:
                    ranges = ranger_ca(
                        numero, groupe_id, jour_type,
                        annotee_tmp=tmp_src if ca_deja_annotee else tmp_out,
                        brute_tmp=None if ca_deja_annotee else tmp_src,
                        remplacer=ca_remplacer,
                    )
                except FileExistsError as e:
                    st.error(f"{e} Cochez « Remplacer » ci-dessus pour l'écraser.")
                    _nettoyer_tmp()
                    return

                dest_out = ranges["annotee"]
                if ca_deja_annotee:
                    st.success(
                        f"Version annotée remplacée directement (sans traitement GTFS) "
                        f"— identité : n° {numero} · {groupe_id} · {jour_type}."
                    )
                else:
                    st.success(
                        f"Carte annotée et rangée — identité : n° {numero} · "
                        f"{groupe_id} · {jour_type}."
                    )

                trace = [
                    f"✅ Carte agent n° {numero} · {groupe_id} · {jour_type}",
                    f"  • Source : {uploaded.name}",
                    f"  • Rangée : {dest_out}",
                    f"  • Mode : {'remplacement direct (sans GTFS)' if ca_deja_annotee else 'annotation GTFS'}",
                ]
                if jt_imprime and jt_imprime != jour_type:
                    trace.append(f"  ⚠️ Écart calendrier/carte : la carte imprime « {jt_imprime} »")
                ecrire_bloc("carte_agent", "\n".join(trace))

                st.download_button(
                    "⬇️ Télécharger la carte annotée",
                    data=dest_out.read_bytes(),
                    file_name=dest_out.name,
                    mime="application/pdf",
                    key="ca_dl",
                )

            _traiter_upload()


    # ── 2c — Gauche-Droite ───────────────────────────────────────────────────
    with st.expander("3 — Importer les Gauche-Droite", expanded=bool(_prep_data and _prep_gd_missing)):
        st.markdown(
            "Récupérez les G-D manquants ou périmés depuis la section `/listeBus` du portail STM."
        )

        _gd_cibles = list(_prep_gd_missing) + [
            (ligne, direction) for ligne, direction, _ in _prep_gd_stale
        ]
        _gd_pending = st.session_state.get("operation_portail")
        _gd_reprende = bool(
            _gd_pending
            and _gd_pending.get("type") == "import_gd"
            and _gd_pending.get("date") == _prep_date_str
            and _gd_pending.get("reprendre")
        )
        _gd_auto = st.button(
            "🌐 Récupérer les G-D manquants ou périmés",
            type="primary",
            key="gd_auto_btn",
            disabled=not bool(_prep_data and _gd_cibles),
        )
        if _gd_auto or _gd_reprende:
            _gd_precedent = None
            _gd_a_traiter = _gd_cibles
            if _gd_reprende:
                _gd_precedent = ResultatRafraichissementGD.from_dict(
                    _gd_pending.get("resultat", {})
                )
                _gd_a_traiter = _gd_precedent.restantes
                _gd_pending["reprendre"] = False
            with st.status("Récupération des G-D…", expanded=True) as _gd_status:
                _gd_nouveau = rafraichir_gd_journee(
                    _prep_data, paires=_gd_a_traiter, log=True
                )
                _gd_total = fusionner_rafraichissements_gd(
                    _gd_precedent, _gd_nouveau
                )
                _afficher_resultat_gd(_gd_nouveau)
                if _gd_nouveau.session_expiree:
                    st.session_state["operation_portail"] = {
                        "type": "import_gd",
                        "date": _prep_date_str,
                        "resultat": _gd_total.to_dict(),
                        "reprendre": False,
                    }
                    st.session_state["ouvrir_dialog_session"] = True
                    _gd_status.update(label="Session à renouveler", state="error")
                elif not _gd_total.succes_complet:
                    st.session_state.pop("operation_portail", None)
                    _gd_status.update(label="Récupération partielle", state="error")
                else:
                    st.session_state.pop("operation_portail", None)
                    st.session_state["prep_flash"] = "Gauche-Droite récupérés depuis STM."
                    _gd_status.update(label="Récupération terminée", state="complete")
                    st.rerun()
        elif _prep_data and not _gd_cibles:
            st.caption("Tous les G-D de cette journée sont présents et à jour.")

        st.divider()
        st.caption("Import manuel de secours")
        st.markdown(
            "Collez le texte brut copié depuis l'interface STM. Le fichier "
            "`gd<ligne>_<direction>.json` sera créé ou mis à jour."
        )

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
                    parser      = GDParser(section)
                    result_data = parser.parse()
                    rapport     = parser.report

                    if result_data:
                        st.success(f"Ligne {parser.ligne} {parser.direction} — importé.")
                        st.code(rapport)
                        ecrire_bloc("parse_gd", rapport)
                    else:
                        erreurs = "\n".join(parser.errors)
                        st.error("Échec pour une section.")
                        st.code(erreurs)
                        ecrire_bloc("parse_gd", erreurs)
                        all_ok = False

                if all_ok:
                    st.session_state["prep_flash"] = "Gauche-Droite importés."
                    st.rerun()

    # ── 2d — Évènements ──────────────────────────────────────────────────────
    with st.expander("4 — Importer manuellement des événements (facultatif)", expanded=False):
        st.caption(
            "Option de secours : collez ici les événements obtenus manuellement. "
            "La finalisation pourra ensuite utiliser ces fichiers sans session portail."
        )
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

    # ── Finalisation ─────────────────────────────────────────────────────────
    st.subheader("Finaliser la préparation")
    _prep_blocked = (
        not _prep_data or not _prep_paires
        or bool(_prep_gd_missing) or bool(_prep_error)
    )
    if _prep_blocked:
        st.warning(
            "Importez une journée contenant des trajets de service et tous ses G-D "
            "avant de finaliser."
        )
    _fc1, _fc2 = st.columns(2)
    _auto_clicked = _fc1.button(
        "🌐 Récupérer les événements et finaliser",
        type="primary",
        use_container_width=True,
        disabled=_prep_blocked,
    )
    _local_clicked = _fc2.button(
        "📁 Finaliser avec les événements présents",
        use_container_width=True,
        disabled=_prep_blocked,
    )
    _prep_pending = st.session_state.get("operation_portail")
    _reprendre_prep = bool(
        _prep_pending
        and _prep_pending.get("type") == "preparation"
        and _prep_pending.get("date") == _prep_date_str
        and _prep_pending.get("reprendre")
    )

    def _afficher_finalisation(_resultats):
        for _resultat in _resultats:
            _icone = {
                "genere": "✅", "ignore": "↪️", "bloque": "⛔", "erreur": "❌",
            }.get(_resultat.statut, "•")
            st.write(f"{_icone} {_resultat.variante} — {_resultat.message}")

    if _local_clicked and _prep_data:
        with st.status("Évaluation des rapports…", expanded=True) as _status:
            _final = finaliser_rapports(
                _prep_path, niveau_v2="standard", rapports_dir=RAPPORTS_DIR
            )
            _afficher_finalisation(_final)
            _status.update(label="Finalisation terminée", state="complete")

    if (_auto_clicked or _reprendre_prep) and _prep_data:
        _precedent = None
        _paires_resume = None
        if _reprendre_prep:
            _precedent = ResultatRafraichissement.from_dict(
                _prep_pending.get("resultat", {})
            )
            _paires_resume = _precedent.restantes
            _prep_pending["reprendre"] = False
        with st.status("Récupération et finalisation…", expanded=True) as _status:
            _nouveau = rafraichir_evenements_journee(
                _prep_data, paires=_paires_resume, log=True
            )
            _refresh_total = fusionner_rafraichissements(_precedent, _nouveau)
            _afficher_resultat_rafraichissement(_nouveau)
            if _nouveau.session_expiree:
                st.session_state["operation_portail"] = {
                    "type": "preparation",
                    "date": _prep_date_str,
                    "resultat": _refresh_total.to_dict(),
                    "reprendre": False,
                }
                st.session_state["ouvrir_dialog_session"] = True
                _status.update(label="Session à renouveler", state="error")
            elif not _refresh_total.succes_complet:
                st.session_state.pop("operation_portail", None)
                _status.update(label="Récupération partielle — rapports non générés", state="error")
            else:
                st.session_state.pop("operation_portail", None)
                _final = finaliser_rapports(
                    _prep_path, niveau_v2="standard", rapports_dir=RAPPORTS_DIR
                )
                _afficher_finalisation(_final)
                _status.update(label="Préparation finalisée", state="complete")

    st.divider()

    # ── 2e — GTFS ────────────────────────────────────────────────────────────
    with st.expander("Outils avancés — GTFS", expanded=False):
        _imp_gtfs_path     = DATA_DIR / "gtfs" / "gtfs_stm"
        _imp_gtfs_manifest = DATA_DIR / "gtfs" / "gtfs_manifest.json"
        _imp_gtfs_info     = info_gtfs()

        if _imp_gtfs_manifest.exists():
            _imp_age = _imp_gtfs_info.get("static_age_days")
            if _imp_age is not None and _imp_age > FRAICHEUR_GTFS_JOURS:
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

        # Journée active partagée (choisie dans 🏠 Ma journée)
        v2_date   = st.session_state.get("journee_date")
        v2_j_path = (
            chemin_journee(v2_date) if v2_date else None
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

    def _file_manager(label: str, files: list[Path], mime: str | None = "application/octet-stream") -> None:
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
                _mime = mime or {
                    ".pdf": "application/pdf", ".html": "text/html", ".json": "application/json",
                }.get(path.suffix.lower(), "application/octet-stream")
                st.download_button(
                    "⬇️",
                    data=path.read_bytes(),
                    file_name=path.name,
                    mime=_mime,
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
        "📄 Rapports",
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
        rp_all = sorted(
            list(RAPPORTS_DIR.glob("rapport-*.pdf"))
            + list(RAPPORTS_DIR.glob("rapport-*.html")),
            reverse=True,
        ) if RAPPORTS_DIR.exists() else []
        st.caption(f"{len(rp_all)} fichier(s) dans `data/rapports/`")
        _file_manager("rp", rp_all, mime=None)
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


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 5 — Logs
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.header("Logs")

    log_files = lister_journaux()

    if not log_files:
        st.info(
            "Aucun fichier de log trouvé dans `data/log/`. "
            "Les imports faits depuis **Préparation d'une journée** y laissent leur trace ; "
            "en ligne de commande, les scripts journalisent avec l'option `--log`."
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


# La boîte de renouvellement est déclenchée après le rendu de l'opération qui
# l'a demandée. La reprise se fera automatiquement au prochain rerun.
if st.session_state.get("ouvrir_dialog_session"):
    _dialog_session_portail()
