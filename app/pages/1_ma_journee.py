# -*- coding: utf-8 -*-
"""Page — Ma journée (orchestrateur : sélection unique + checklist + consultation).

Ancien onglet 1 de l'application monolithique (app/ui.py).
"""
import bootstrap  # noqa: F401  (configure sys.path avant tout import)

bootstrap.initialiser_page()

import re
import subprocess
import sys
from datetime import date

import streamlit as st

from app.components.apercu_html import afficher_rapport_html

from gen_rapport_v2 import generer_rapport as _gen_v2

from app.components.result_display import _afficher_resultat_rafraichissement
from app.components.resume_durees import afficher_resume_durees
from app.components.session_dialog import (
    declencher_dialog_si_requis,
    demander_renouvellement,
)
from app.state import (
    DB_REFRESH_DATE,
    DB_REFRESH_REPORT,
    DB_REFRESH_RESULT,
    JOURNEE_DATE,
    effacer_operation_portail,
    operation_portail,
)
from app.utils import _cached_arrets_pour_parcours
from bootstrap import DATA_DIR, SCRIPTS_DIR

from chauffeur.ca import cle_note_carte, resoudre_ca
from chauffeur.depots import (
    charger_evenements,
    charger_gd,
    charger_journee,
    chemin_evenements,
    chemin_journee,
    info_gtfs,
    lister_journees_fenetre,
    sauvegarder_journee,
)
from chauffeur.durees import resumer_durees
from chauffeur.evenements import applicable_a_la_plage, trier_evenements_par_arrets
from chauffeur.gd import event_applicable_to_parcours
from chauffeur.gtfs_rt import find_vehicle, parse_vehicle_positions
from chauffeur.journee import lignes_de_service
from chauffeur.notes import (
    note_carte,
    note_journee,
    note_matricule,
    note_voiture,
    sauvegarder_note_carte,
    sauvegarder_note_journee,
    sauvegarder_note_matricule,
    sauvegarder_note_voiture,
)
from chauffeur.portail import etat_session
from chauffeur.preparation import (
    ResultatRafraichissement,
    fusionner_rafraichissements,
    generer_v2_et_marquer,
    rafraichir_evenements_journee,
)
from chauffeur.presentation_evenements import (
    presenter_evenement,
    rendre_table_evenements_html,
)
from chauffeur.reference import lieu_point_releve

JOURNEES_DIR = bootstrap.journees_dir()
RAPPORTS_DIR = bootstrap.rapports_dir()

st.header("Ma journée")

_journees_fenetre = lister_journees_fenetre(date.today()) if JOURNEES_DIR.exists() else []
db_j_labels = [jour.isoformat() for jour, _ in _journees_fenetre]

# ── Sélecteur UNIQUE : journées proches ou date saisie manuellement ──────
_today_label = date.today().isoformat()
_default_idx = (
    db_j_labels.index(_today_label)
    if _today_label in db_j_labels
    else min(
        range(len(db_j_labels)),
        key=lambda i: abs((date.fromisoformat(db_j_labels[i]) - date.today()).days),
        default=None,
    )
)
db_date_str = st.selectbox(
    "Journée", db_j_labels, index=_default_idx, key=JOURNEE_DATE,
    persist_state="session",
    accept_new_options=True,
    placeholder="Choisir ou saisir une date (AAAA-MM-JJ)",
    help="Pour consulter une journée antérieure, saisissez sa date au format "
         "AAAA-MM-JJ (ex. 2026-08-23), puis appuyez sur Entrée.",
)

# Les résultats non liés à un widget survivent à la navigation : ne pas
# présenter ceux d'une ancienne journée sous la nouvelle date sélectionnée.
if st.session_state.get(DB_REFRESH_DATE) != db_date_str:
    st.session_state.pop(DB_REFRESH_RESULT, None)
    st.session_state.pop(DB_REFRESH_REPORT, None)
    st.session_state[DB_REFRESH_DATE] = db_date_str

if db_date_str is None:
    st.info(
        "Choisissez une journée ou saisissez une date au format AAAA-MM-JJ. "
        "La liste propose les journées enregistrées entre J−2 et J+5."
    )
else:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", db_date_str):
            raise ValueError
        date.fromisoformat(db_date_str)
    except ValueError:
        st.warning("Saisissez une date valide au format AAAA-MM-JJ (ex. 2026-08-23).")
        st.stop()

    db_j_path = chemin_journee(db_date_str)
    if not db_j_path.exists():
        st.info(
            f"Aucune journée enregistrée pour le {db_date_str}. "
            "Importez-la dans **🧰 Préparation d'une journée**."
        )
        st.stop()

    try:
        db_j_data = charger_journee(db_j_path)
    except Exception as e:
        st.error(f"Erreur lecture journée : {e}")
        st.stop()

    # ── Rafraîchissement du jour ─────────────────────────────────────────
    gtfs_info = info_gtfs()
    RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)

    _paires = lignes_de_service(db_j_data)
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
    _pending = operation_portail()
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
                demander_renouvellement({
                    "type": "ma_journee",
                    "date": db_date_str,
                    "resultat": _resultat.to_dict(),
                    "reprendre": False,
                })
                _status.update(label="Session à renouveler", state="error")
            elif not _resultat.succes_complet:
                effacer_operation_portail()
                st.session_state[DB_REFRESH_RESULT] = _resultat.to_dict()
                _status.update(label="Rafraîchissement partiel", state="error")
            else:
                effacer_operation_portail()
                if _resultat.modifie:
                    st.write("Des événements ont changé — génération du v2 détaillé…")
                    _rapport = generer_v2_et_marquer(
                        db_j_path, niveau="détaillé", rapports_dir=RAPPORTS_DIR
                    )
                    st.session_state[DB_REFRESH_REPORT] = {
                        "statut": _rapport.statut, "message": _rapport.message
                    }
                    if _rapport.statut == "erreur":
                        st.error(_rapport.message)
                else:
                    st.caption("Aucun changement — le rapport existant est conservé.")
                st.session_state[DB_REFRESH_RESULT] = _resultat.to_dict()
                _status.update(label="Rafraîchissement terminé", state="complete")

    if st.session_state.get(DB_REFRESH_RESULT):
        _afficher_resultat_rafraichissement(
            ResultatRafraichissement.from_dict(
                st.session_state[DB_REFRESH_RESULT]
            )
        )

    st.divider()

    # ── Métriques résumé ──────────────────────────────────────────────────
    db_pieces = db_j_data.get("pieces", [])
    db_resume_durees = resumer_durees(db_j_data)

    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric("Journée n°",      db_j_data.get("journee_numero", "–"))
    mc2.metric("Garage",          db_j_data.get("garage",         "–"))
    mc3.metric("Temps travaillé", db_j_data.get("temps_travaille","–"))
    mc4.metric("Prise début",     db_resume_durees.prise_debut or "—")
    mc5.metric("Prise fin",       db_resume_durees.prise_fin or "—")

    # ── Notes (carte agent + journée) ─────────────────────────────────────
    nn1, nn2 = st.columns(2)
    with nn1:
        _cle_ca = cle_note_carte(_ca_info)
        if _cle_ca is None:
            st.caption("Aucune carte agent résolue pour cette journée.")
        else:
            note_c = note_carte(_cle_ca) or {}
            st.text_area(
                "📝 Note carte agent",
                value=note_c.get("note", ""),
                help="Suit la carte : réutilisée aux journées partageant "
                     "cette liste/jour-type (identité n°_liste_jour).",
                key=f"db_note_ca_edit_{db_date_str}_{_cle_ca}",
            )
            if st.button("💾 Enregistrer", key=f"db_note_ca_save_{db_date_str}_{_cle_ca}"):
                sauvegarder_note_carte(
                    _cle_ca,
                    st.session_state.get(f"db_note_ca_edit_{db_date_str}_{_cle_ca}", ""),
                )
                st.rerun()
            if note_c.get("maj"):
                st.caption(f"Mise à jour : {note_c['maj']}")
    with nn2:
        note_j = note_journee(db_date_str) or {}
        st.text_area(
            "📝 Note journée",
            value=note_j.get("note", ""),
            help="Note propre à cette journée.",
            key=f"db_note_journee_edit_{db_date_str}",
        )
        if st.button("💾 Enregistrer", key=f"db_note_journee_save_{db_date_str}"):
            sauvegarder_note_journee(
                db_date_str,
                st.session_state.get(f"db_note_journee_edit_{db_date_str}", ""),
            )
            st.rerun()
        if note_j.get("maj"):
            st.caption(f"Mise à jour : {note_j['maj']}")

    # ── Aperçu de la carte agent annotée ─────────────────────────────────
    _ca_annotee = _ca_info.get("annotee")
    if _ca_annotee:
        _ca_exp = st.expander(
            f"🗺️ Carte agent — Aperçu  ({_ca_annotee.name})",
            on_change="rerun",  # contenu rendu seulement si la section est ouverte
            key=f"db_ca_apercu_{db_date_str}",
        )
        if _ca_exp.open:
            with _ca_exp:
                st.pdf(
                    _ca_annotee.read_bytes(),
                    height=700,
                    key=f"db_ca_pdf_{db_date_str}_{_ca_annotee.stat().st_mtime_ns}",
                )
    else:
        st.caption(
            "Aucune carte agent annotée pour cette journée "
            "(à importer dans Préparation d'une journée, étape 2)."
        )

    # ── Aperçu du dernier rapport v2 complet ─────────────────────────────
    _v2_html = sorted(
        RAPPORTS_DIR.glob(f"rapport-v2-{db_date_str}-*.html"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    ) if RAPPORTS_DIR.exists() else []
    _v2_html_jour = [p for p in _v2_html if not re.search(r"-id\d+", p.stem)]
    latest_html_jour = _v2_html_jour[0] if _v2_html_jour else None

    if latest_html_jour:
        with st.expander(f"📊 Rapport v2 — Aperçu  ({latest_html_jour.name})"):
            afficher_rapport_html(
                latest_html_jour.read_text(encoding="utf-8"),
                height=600,
            )
    else:
        st.caption("Aucun rapport v2 complet à prévisualiser pour cette journée.")

    st.divider()

    # ── Pièces de travail (consultation « En route ») ─────────────────────
    afficher_resume_durees(db_resume_durees)
    st.subheader("Pièces de travail")

    for idx, piece in enumerate(db_pieces):
        pid = piece.get("id", f"pièce-{idx + 1}")
        type_piece = " — TS continu" if piece.get("type_horaire") == "continu" else ""
        with st.expander(
            f"Pièce {pid}{type_piece}  —  {piece.get('debut', '?')} → {piece.get('fin', '?')}"
            f"  ({piece.get('duree', '?')})",
            expanded=False,
        ):
            if piece.get("type_horaire") == "absence":
                st.write(piece.get("motif_absence") or "Absence")
                continue
            pc1, pc2, pc3 = st.columns([2, 2, 2])

            with pc1:
                _garage = db_j_data.get("garage")

                def _lieu_md(label, code):
                    code = code or "–"
                    lieu = (lieu_point_releve(code, _garage, jour=db_j_data.get("date") or db_date_str)
                            if code != "–" else None)
                    suffix = f" — {lieu}" if lieu else ""
                    return f"**{label} :** `{code}`{suffix}"

                st.markdown(_lieu_md("Lieu prise", piece.get("lieu_prise")))
                st.markdown(_lieu_md("Lieu fin", piece.get("lieu_fin")))

            with pc2:
                # Un réimport peut changer la pièce ou son bus sans changer
                # la date ni l'indice : abandonner alors l'ancien brouillon.
                bus_identite = f"{db_date_str}_{idx}_{pid}_{piece.get('numero_autobus') or ''}"
                bus_edit_key = f"db_bus_edit_{bus_identite}"
                bus_save_key = f"db_bus_save_{bus_identite}"
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
                    note_v = note_voiture(current_bus)
                    # L'état du champ doit suivre le bus, même si Streamlit
                    # conserve les widgets dont seuls le libellé et la valeur changent.
                    note_v_key  = f"db_note_voiture_edit_{db_date_str}_{idx}_{current_bus}"
                    note_v_save = f"db_note_voiture_save_{db_date_str}_{idx}_{current_bus}"
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
                            sauvegarder_note_voiture(current_bus, st.session_state.get(note_v_key, ""))
                            st.success("Note sauvegardée.")
                        st.markdown("</div>", unsafe_allow_html=True)
                    if note_v and note_v.get("maj"):
                        st.caption(f"Mise à jour : {note_v['maj']}")

                geo_key = f"db_geo_r_{db_date_str}_{idx}_{current_bus}"
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
                    note_m = note_matricule(_mat)
                    # La note doit suivre le matricule après un réimport,
                    # même si Streamlit conserve les widgets à clé identique.
                    note_m_key  = f"db_note_mat_edit_{db_date_str}_{idx}_{_rk}_{_mat}"
                    note_m_save = f"db_note_mat_save_{db_date_str}_{idx}_{_rk}_{_mat}"
                    st.text_area(
                        f"Note — {r['nom']}",
                        value=(note_m or {}).get("note", ""),
                        height=68,
                        key=note_m_key,
                    )
                    if st.button("💾 Enregistrer", key=note_m_save):
                        sauvegarder_note_matricule(
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

                t_key = f"db_t_{db_date_str}_{idx}_{ti}_{tl}_{td}_{tid}"
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
                        afficher_rapport_html(
                            rpt_html.decode("utf-8"),
                            height=600,
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

declencher_dialog_si_requis()
