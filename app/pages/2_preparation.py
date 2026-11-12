# -*- coding: utf-8 -*-
"""Page — Préparation d'une journée (import + finalisation).

Ancien onglet 2 de l'application monolithique (app/ui.py).
"""
import bootstrap  # noqa: F401  (configure sys.path avant tout import)

bootstrap.initialiser_page()

import io
import subprocess
import sys
import zipfile
from datetime import date

import streamlit as st

from app.components.result_display import (
    _afficher_bilan_semi_auto,
    _afficher_resultat_gd,
    _afficher_resultat_rafraichissement,
    progression_semi_auto,
)
from app.components.session_dialog import (
    declencher_dialog_si_requis,
    demander_renouvellement,
)
from app.state import (
    PREP_DATE,
    PREP_FLASH,
    PREP_SEMI_AUTO,
    effacer_operation_portail,
    operation_portail,
    reprise_en_attente,
)
from bootstrap import DATA_DIR, SCRIPTS_DIR, journees_dir

from parse_event import PortailEventParser, split_sections as split_ev
from parse_gd import GDParser, libelle_retraits, split_sections
from parse_journee import JourneeParser

from chauffeur.ca import annoter_et_ranger_ca, resoudre_ca
from chauffeur.calendrier import dossier_calendrier, evenements_ics, rendre_ics
from chauffeur.depots import (
    FRAICHEUR_GTFS_JOURS,
    charger_journee,
    chemin_evenements,
    chemin_journee,
    info_gd,
    info_gtfs,
)
from chauffeur.journal import ecrire_bloc
from chauffeur.journee import groupes_de_service, lignes_de_service
from chauffeur.registre_appariement import parcours_a_reviser
from chauffeur.registre_detours import detours_a_reviser
from chauffeur.portail import etat_session
from chauffeur.preparation_auto import LIBELLES, ResultatSemiAuto, executer_semi_auto
from chauffeur.preparation import (
    ResultatRafraichissement,
    ResultatRafraichissementGD,
    etat_rapport,
    finaliser_rapports,
    fusionner_rafraichissements,
    fusionner_rafraichissements_gd,
    importer_journee_portail,
    rafraichir_evenements_journee,
    rafraichir_gd_journee,
)

RAPPORTS_DIR = bootstrap.rapports_dir()

st.header("Préparation d'une journée")
if st.session_state.get(PREP_FLASH):
    st.success(st.session_state.pop(PREP_FLASH))
_prep_date = st.date_input(
    "Date à préparer", value=date.today(), key=PREP_DATE, persist_state="session"
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

_prep_paires = lignes_de_service(_prep_data) if _prep_data else []
_prep_ca = (
    resoudre_ca(_prep_date, _prep_data.get("journee_numero"))
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

# ── Préparation semi-automatique ─────────────────────────────────────────
_semi = st.session_state.get(PREP_SEMI_AUTO)
if _semi and _semi.get("date") != _prep_date_str:
    _semi = None   # bilan d'une autre date : conservé, mais pas affiché ici
_semi_res = ResultatSemiAuto.from_dict(_semi["resultat"]) if _semi else None
_semi_a_executer = None   # (résultat précédent ou None, sans_portail)

_semi_reprise = reprise_en_attente("semi_auto", _prep_date_str)
if _semi_reprise:
    _semi_reprise["reprendre"] = False
    _semi_a_executer = (ResultatSemiAuto.from_dict(_semi_reprise["resultat"]), False)

if _semi_res is None and not _prep_data and not _prep_error:
    with st.container(border=True):
        st.markdown(
            f"**Journée du {_prep_date_str} non importée** — la préparation "
            "semi-automatique enchaîne toutes les étapes tant qu'aucune erreur "
            "bloquante n'est rencontrée."
        )
        st.caption(
            " → ".join(LIBELLES.values())
        )
        if _prep_session.statut in ("absente", "expiree"):
            st.info(
                "La session portail n'est pas active : un dialogue demandera "
                "le cookie, puis la préparation reprendra automatiquement."
            )
        if st.button(
            "Lancer la préparation semi-automatique", type="primary",
            icon=":material/play_arrow:", key="semi_auto_btn",
        ):
            _semi_a_executer = (None, False)
elif _semi_res is not None:
    with st.expander(
        "Bilan de la préparation semi-automatique",
        expanded=bool(_semi_res.reprise_a or _semi_res.avertissements),
    ):
        _afficher_bilan_semi_auto(_semi_res)
        with st.container(horizontal=True):
            if _semi_res.reprise_a and st.button(
                "Reprendre", type="primary", icon=":material/replay:",
                key="semi_auto_reprendre",
            ):
                _semi_a_executer = (_semi_res, False)
            if _semi_res.reprise_a == "evenements" and st.button(
                "Continuer sans les évènements du portail",
                icon=":material/skip_next:", key="semi_auto_sans_portail",
            ):
                _semi_a_executer = (_semi_res, True)
            if st.button("Fermer le bilan", key="semi_auto_fermer"):
                st.session_state.pop(PREP_SEMI_AUTO, None)
                st.rerun()

if _semi_a_executer:
    _semi_precedent, _semi_sans_portail = _semi_a_executer
    with st.status("Préparation semi-automatique…", expanded=True) as _semi_status:
        _semi_nouveau = executer_semi_auto(
            _prep_date_str, precedent=_semi_precedent, sans_portail=_semi_sans_portail,
            rapports_dir=RAPPORTS_DIR, progression=progression_semi_auto(_semi_status),
        )
        st.session_state[PREP_SEMI_AUTO] = {
            "date": _prep_date_str, "resultat": _semi_nouveau.to_dict(),
        }
        if _semi_nouveau.session_expiree:
            demander_renouvellement({
                "type": "semi_auto", "date": _prep_date_str,
                "resultat": _semi_nouveau.to_dict(), "reprendre": False,
            })
            _semi_status.update(label="Session à renouveler", state="error")
        else:
            effacer_operation_portail()
            if _semi_nouveau.reprise_a:
                _semi_status.update(label="Préparation interrompue", state="error")
            else:
                _n = len(_semi_nouveau.avertissements)
                st.session_state[PREP_FLASH] = "Préparation semi-automatique terminée" + (
                    f" — {_n} avertissement(s), voir le bilan." if _n else "."
                )
                _semi_status.update(label="Préparation terminée", state="complete")
            st.rerun()

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
_prep_app = parcours_a_reviser(groupes_de_service(_prep_data)) if _prep_data else []
if _prep_app:
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("⚠️ **Appariements à réviser** — " + ", ".join(_prep_app))
        st.page_link("pages/7_appariement.py", label="Réviser", icon="🧭")
_prep_det = detours_a_reviser(groupes_de_service(_prep_data), _prep_date) if _prep_data else []
if _prep_det:
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("⚠️ **Détours à réviser** — " + ", ".join(_prep_det))
        st.page_link("pages/8_detours.py", label="Réviser", icon="🧭")
if _prep_error:
    st.error(f"Erreur de préparation : {_prep_error}")
st.divider()

# ── 2a — Journée ─────────────────────────────────────────────────────────
with st.expander("1 — Importer la journée", expanded=not bool(_prep_data)):
    st.markdown(
        "Récupérez le **Détail de ma journée** depuis une session valide du portail employé. "
        f"Le fichier `journee-YYYY-MM-DD.json` sera créé dans `{journees_dir()}/`."
    )

    j_imp_date = _prep_date
    st.caption(f"Date de la journée : **{j_imp_date}**")

    _j_pending = operation_portail()
    _j_reprende = bool(
        _j_pending
        and _j_pending.get("type") == "import_journee"
        and _j_pending.get("date") == _prep_date_str
        and _j_pending.get("reprendre")
    )
    _j_auto = st.button(
        "🌐 Récupérer depuis le portail employé", type="primary", key="j_auto_btn"
    )
    if _j_auto or _j_reprende:
        if _j_reprende:
            _j_pending["reprendre"] = False
        with st.spinner("Récupération de la journée…"):
            _j_resultat = importer_journee_portail(j_imp_date, log=True)
        if _j_resultat.session_expiree:
            demander_renouvellement({
                "type": "import_journee",
                "date": _prep_date_str,
                "reprendre": False,
            })
            st.warning("Session expirée — renouvellement requis.")
        elif _j_resultat.succes:
            effacer_operation_portail()
            st.session_state[PREP_FLASH] = (
                f"Journée du {j_imp_date} récupérée depuis le portail employé."
            )
            st.rerun()
        else:
            effacer_operation_portail()
            st.error(_j_resultat.message or "Échec de la récupération.")

    st.divider()
    st.caption("Import manuel de secours")
    st.markdown(
        "Collez le texte brut du **Détail de ma journée** copié depuis l'interface du portail employé."
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
        key=f"j_text_{_prep_date_str}",
    )

    if st.button("Importer", type="primary", key="j_imp_btn"):
        if not j_text.strip():
            st.warning("Le champ est vide.")
        else:
            parser = JourneeParser(j_text, date_str=str(j_imp_date))
            result_j = parser.parse()

            if result_j:
                saved_j = parser.save(result_j)
                resume_j = parser.get_summary(result_j, saved_j)
                ecrire_bloc("parse_journee", resume_j)
                st.session_state[PREP_FLASH] = f"Journée du {j_imp_date} importée."
                st.rerun()
            else:
                resume_j = parser.get_summary()
                st.error("Échec du parsing.")
                st.code(resume_j)
                ecrire_bloc("parse_journee", resume_j)

# ── 1b — Calendrier ──────────────────────────────────────────────────────
_prep_ics = evenements_ics(_prep_data) if _prep_data else []
with st.expander(
    f"1b — Calendrier (.ics){f' · {len(_prep_ics)} pièce(s)' if _prep_ics else ''}",
    expanded=False,
):
    if not _prep_ics:
        st.caption("Importez d'abord la journée : un fichier .ics est créé par pièce de travail.")
    else:
        st.caption(
            "Un fichier par pièce, à ouvrir ou importer dans votre calendrier. "
            f"Copies générées à l'import dans `{dossier_calendrier(_prep_path) / _prep_date_str}/`."
        )
        _ics_fichiers = {ev["nom_fichier"]: rendre_ics(ev).encode("utf-8") for ev in _prep_ics}
        for _ev in _prep_ics:
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(
                    f"**{_ev['titre']}** · {_ev['debut']:%H:%M} → {_ev['fin']:%H:%M}"
                    + (" (+1 j)" if _ev["fin"].date() > _ev["debut"].date() else "")
                )
                st.download_button(
                    "Télécharger", data=_ics_fichiers[_ev["nom_fichier"]],
                    file_name=_ev["nom_fichier"], mime="text/calendar",
                    icon=":material/event:", key=f"ics_{_prep_date_str}_{_ev['rang']}",
                )
        if len(_ics_fichiers) > 1:
            _zip = io.BytesIO()
            with zipfile.ZipFile(_zip, "w", zipfile.ZIP_DEFLATED) as _z:
                for _nom, _contenu in _ics_fichiers.items():
                    _z.writestr(_nom, _contenu)
            st.download_button(
                "Tout télécharger (.zip)", data=_zip.getvalue(),
                file_name=f"calendrier-{_prep_date_str}.zip", mime="application/zip",
                icon=":material/download:", key=f"ics_zip_{_prep_date_str}",
            )

# ── 2b — Carte Agent ──────────────────────────────────────────────────────
with st.expander("2 — Importer ou vérifier la carte agent", expanded=bool(_prep_data and not _prep_ca.get("annotee"))):
    st.markdown(
        "Déposez le PDF brut de votre carte agent. L'application l'annote (horaires "
        "GTFS surlignés) et la range par **identité** (numéro + liste + jour-type) — "
        "une même identité est réutilisée automatiquement entre journées, sans "
        "réimporter le PDF."
    )

    # Le fichier et les autorisations de remplacement appartiennent à la
    # journée/CA choisie, pas à la position du formulaire dans la page.
    _ca_contexte = f"{_prep_date_str}_{(_prep_data or {}).get('journee_numero', '')}"
    uploaded = st.file_uploader("Fichier carte agent (PDF)", type="pdf", key=f"ca_upload_{_ca_contexte}")

    ca_date = _prep_date
    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"Date représentative de la carte : **{ca_date}**")
    with col2:
        no_gtfs = st.checkbox("Sans GTFS (surlignage seulement)", value=False, key="ca_no_gtfs")

    ca_remplacer = st.checkbox(
        "Remplacer une CA existante pour cette identité (version augmentée)",
        value=False, key=f"ca_remplacer_{_ca_contexte}",
    )
    ca_deja_annotee = st.checkbox(
        "Le PDF déposé est déjà annoté — le ranger tel quel (remplace uniquement "
        "la version annotée, sans relancer le traitement GTFS)",
        value=False, key=f"ca_deja_annotee_{_ca_contexte}",
    )

    btn_label = "Enregistrer la version annotée" if ca_deja_annotee else "Annoter la carte"
    if uploaded and st.button(btn_label, type="primary", key="ca_btn"):
        with st.spinner("Lecture des métadonnées…" if ca_deja_annotee else "Annotation en cours…"):
            _ca_res = annoter_et_ranger_ca(
                uploaded.read(), ca_date,
                nom_source=uploaded.name, avec_gtfs=not no_gtfs,
                deja_annotee=ca_deja_annotee, remplacer=ca_remplacer,
            )
        for _avert in _ca_res.avertissements:
            st.warning(_avert)
        if _ca_res.succes:
            st.success(_ca_res.message)
            st.download_button(
                "⬇️ Télécharger la carte annotée",
                data=_ca_res.chemin_annotee.read_bytes(),
                file_name=_ca_res.chemin_annotee.name,
                mime="application/pdf",
                key="ca_dl",
            )
        elif _ca_res.statut == "existe":
            st.error(f"{_ca_res.message} Cochez « Remplacer » ci-dessus pour l'écraser.")
        else:
            st.error(_ca_res.message)
            if _ca_res.detail:
                st.code(_ca_res.detail)


# ── 2c — Gauche-Droite ───────────────────────────────────────────────────
with st.expander("3 — Importer les Gauche-Droite", expanded=bool(_prep_data and _prep_gd_missing)):
    st.markdown(
        "Récupérez les G-D manquants ou périmés depuis la section `/listeBus` du portail employé."
    )

    _gd_cibles = list(_prep_gd_missing) + [
        (ligne, direction) for ligne, direction, _ in _prep_gd_stale
    ]
    _gd_pending = operation_portail()
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
                demander_renouvellement({
                    "type": "import_gd",
                    "date": _prep_date_str,
                    "resultat": _gd_total.to_dict(),
                    "reprendre": False,
                })
                _gd_status.update(label="Session à renouveler", state="error")
            elif not _gd_total.succes_complet:
                effacer_operation_portail()
                _gd_status.update(label="Récupération partielle", state="error")
            else:
                effacer_operation_portail()
                st.session_state[PREP_FLASH] = "Gauche-Droite récupérés depuis le portail employé."
                _gd_status.update(label="Récupération terminée", state="complete")
                st.rerun()
    elif _prep_data and not _gd_cibles:
        st.caption("Tous les G-D de cette journée sont présents et à jour.")

    st.divider()
    st.caption("Import manuel de secours")
    st.markdown(
        "Collez le texte brut copié depuis l'interface du portail employé. Le fichier "
        "`gd<ligne>_<direction>.json` sera créé ou mis à jour."
    )

    gd_text = st.text_area(
        "Texte brut G-D",
        height=400,
        placeholder="Gauche-Droite / 195 Ouest\nParcours principal ID 1\n...",
        key="gd_text",
    )

    # Un collage qui ne contient pas tous les parcours déjà importés d'une
    # ligne/direction en retirerait : le chauffeur choisit fusionner ou remplacer.
    gd_mode = None
    if st.button("Importer", type="primary", key="gd_btn"):
        st.session_state.pop("gd_attente", None)
        if not gd_text.strip():
            st.warning("Le champ est vide.")
        else:
            retraits = []
            for section in split_sections(gd_text) or [gd_text]:
                analyse = GDParser(section)
                if analyse.parcours_retires():
                    retraits.append(libelle_retraits(analyse))
            if retraits:
                st.session_state["gd_attente"] = {"texte": gd_text, "retraits": retraits}
            else:
                gd_mode = "remplacer"   # rien à retirer : fusion et remplacement coïncident

    gd_attente = st.session_state.get("gd_attente")
    if gd_attente and gd_attente["texte"] != gd_text:
        st.session_state.pop("gd_attente")   # texte modifié depuis la demande
        gd_attente = None
    gd_zone = st.empty()
    if gd_attente:
        with gd_zone.container():
            st.warning(
                "Ce collage ne contient pas tous les parcours déjà importés. "
                "Parcours absents du collage :\n\n"
                + "\n".join(f"- {r}" for r in gd_attente["retraits"])
            )
            gd_c1, gd_c2, gd_c3 = st.columns(3)
            if gd_c1.button("Fusionner (conserver ces parcours)", type="primary",
                            key="gd_fusionner"):
                gd_mode = "fusionner"
            if gd_c2.button("Remplacer (retirer ces parcours)", key="gd_remplacer"):
                gd_mode = "remplacer"
            if gd_c3.button("Annuler", key="gd_annuler"):
                st.session_state.pop("gd_attente", None)
                st.rerun()

    if gd_mode:
        st.session_state.pop("gd_attente", None)
        gd_zone.empty()
        all_ok = True
        for section in split_sections(gd_text) or [gd_text]:
            parser      = GDParser(section)
            result_data = parser.parse(gd_mode)
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
            st.session_state[PREP_FLASH] = "Gauche-Droite importés."
            st.rerun()

# ── 2d — Évènements ──────────────────────────────────────────────────────
with st.expander("4 — Importer manuellement des événements (facultatif)", expanded=False):
    st.caption(
        "Option de secours : collez ici les événements obtenus manuellement. "
        "La finalisation pourra ensuite utiliser ces fichiers sans session portail."
    )
    # --- Import manuel (texte brut) ---
    st.subheader("Import manuel (texte brut)")
    st.markdown("Collez le texte brut des évènements / détours du portail employé. Le fichier `<ligne>_<direction>.json` sera créé ou mis à jour.")

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
            sections = split_ev(ev_text) or [ev_text]
            all_ok = True
            for section in sections:
                parser  = PortailEventParser(section)
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
    width="stretch",
    disabled=_prep_blocked,
)
_local_clicked = _fc2.button(
    "📁 Finaliser avec les événements présents",
    width="stretch",
    disabled=_prep_blocked,
)
_prep_pending = operation_portail()
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
            demander_renouvellement({
                "type": "preparation",
                "date": _prep_date_str,
                "resultat": _refresh_total.to_dict(),
                "reprendre": False,
            })
            _status.update(label="Session à renouveler", state="error")
        elif not _refresh_total.succes_complet:
            effacer_operation_portail()
            _status.update(label="Récupération partielle — rapports non générés", state="error")
        else:
            effacer_operation_portail()
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
            "(nécessite une clé API du portail développeurs dans `Installation/config/secrets.json`)."
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

declencher_dialog_si_requis()
