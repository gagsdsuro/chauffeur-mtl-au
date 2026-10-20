#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page — Appariement des arrêts (G-D ↔ GTFS), commun à tous les chauffeurs.

Révision humaine de `chauffeur.appariement` : pour un parcours, chaque arrêt
GTFS est rattaché à une étape du Gauche-Droite. Le chauffeur corrige l'étape
d'un arrêt (ou le « fixe »), l'alignement automatique est aussitôt recalculé
autour de ses choix, puis il valide : le résultat est enregistré dans
`data/Appariements/` (commun) et utilisé par le rapport v2.

Aucune logique métier ici : calcul, statuts, validation et contrôle de
version vivent dans `chauffeur.appariement` / `chauffeur.registre_appariement`.
"""
import bootstrap  # noqa: F401  (configure sys.path avant tout import)

bootstrap.initialiser_page()

from datetime import date  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.components.session_dialog import declencher_dialog_si_requis  # noqa: E402
from app.utils import (  # noqa: E402
    _cached_noms_arrets, _cached_sequence_parcours, _mtime_gtfs,
)

import chauffeur.depots as depots  # noqa: E402
from chauffeur import registre_appariement as reg  # noqa: E402
from chauffeur.appariement import apparier  # noqa: E402
from chauffeur.journee import groupes_de_service  # noqa: E402

FLASH = "app_flash"
ICONES = {"auto": "✅", "valide": "✔️", "incertain": "⚠️", "a_revalider": "🔁", None: "⬜"}
LIBELLES = {
    "auto": "automatique, sans doute", "valide": "validé",
    "incertain": "incertain", "a_revalider": "à revalider", None: "non calculé",
}


def _cle(ligne, direction, pid) -> str:
    return f"{ligne}_{direction}_{pid}"


def _etat_session(cle: str, contenu: dict, existant: dict | None) -> None:
    """Initialise les choix de travail d'un parcours (une seule fois par ouverture)."""
    if f"app_ancres::{cle}" not in st.session_state:
        st.session_state[f"app_ancres::{cle}"] = reg.ancres_courantes(contenu)
        st.session_state[f"app_version::{cle}"] = existant.get("version") if existant else None
        st.session_state[f"app_gen::{cle}"] = 0


def _oublier(cle: str) -> None:
    for prefixe in ("app_ancres", "app_version", "app_gen"):
        st.session_state.pop(f"{prefixe}::{cle}", None)


def _appliquer_edition(cle, editor_key, seqs, etapes, instructions, stops, noms):
    """Callback du tableau : traduit les cellules modifiées en arrêts fixés."""
    edits = st.session_state.get(editor_key, {}).get("edited_rows", {})
    changements = [(seqs[int(pos)], c.get("Étape G-D"), c.get("Fixé")) for pos, c in edits.items()]
    try:
        st.session_state[f"app_ancres::{cle}"] = reg.modifier_ancres(
            st.session_state[f"app_ancres::{cle}"], changements, etapes, instructions, stops, noms)
    except ValueError:
        st.session_state[FLASH] = ("error",
            "Ordre impossible : un arrêt ne peut pas précéder, dans le G-D, "
            "un arrêt qui le précède sur le parcours. Modification annulée.")
    st.session_state[f"app_gen::{cle}"] += 1      # nouveau tableau, sans éditions en attente


# ── Catalogue des parcours ───────────────────────────────────────────────────

st.header("Appariement des arrêts")
st.caption(
    "Rattache chaque arrêt GTFS à son étape du Gauche-Droite. Commun à tous les "
    "chauffeurs : un appariement validé sert à tout le monde dans le rapport v2."
)
if st.session_state.get(FLASH):
    niveau, message = st.session_state.pop(FLASH)
    getattr(st, niveau)(message)

gtfs_dir = depots.GTFS_DIR
if not (gtfs_dir / "stops.txt").exists():
    st.error("GTFS absent : téléchargez-le depuis **Préparation d'une journée** "
             "avant de réviser un appariement.")
    st.stop()

stockes = reg.lister_appariements()
catalogue = {(l, d, p.get("id")): p for l, d, p in reg.lister_parcours_gd()}


def _statut(cle_parcours):
    c = stockes.get(cle_parcours)
    return c.get("statut") if c else None


with st.container(horizontal=True, vertical_alignment="bottom"):
    vue = st.segmented_control(
        "Afficher", ["À réviser", "Ma journée", "Tous"], default="À réviser", required=True,
        key="app_vue",
    )
    if st.button("🔄 Synchroniser", key="app_sync",
                 help="Calcule les appariements absents ou périmés (G-D ou GTFS modifié)."):
        with st.spinner("Calcul des appariements…"):
            messages = reg.synchroniser_tout(log=True)
        st.session_state[FLASH] = ("info", "\n\n".join(messages) if messages
                                   else "Tous les appariements sont déjà à jour.")
        st.rerun()

if vue == "Ma journée":
    fenetre = depots.lister_journees_fenetre(date.today(), journees_dir=bootstrap.journees_dir())
    if not fenetre:
        st.info("Aucune journée importée entre J−2 et J+5.")
        st.stop()
    jours = [j for j, _ in fenetre]
    jour = st.selectbox("Journée", jours, index=jours.index(date.today()) if date.today() in jours else 0,
                        format_func=lambda j: j.isoformat(), key="app_jour")
    journee = depots.charger_journee(dict(fenetre)[jour])
    cles = []
    for g in groupes_de_service(journee):
        _, parcours = depots.charger_gd(g["ligne"], g["direction"], g.get("id_parcours"))
        if parcours:
            cles.append((g["ligne"].lower(), g["direction"], parcours.get("id")))
    cles = [c for c in dict.fromkeys(cles) if c in catalogue]
elif vue == "À réviser":
    cles = [c for c in catalogue if _statut(c) in ("incertain", "a_revalider")]
else:
    cles = list(catalogue)

if not cles:
    st.success("Aucun parcours à réviser." if vue == "À réviser" else "Aucun parcours G-D.")
    st.stop()


def _libelle(c):
    contenu = stockes.get(c) or {}
    blocs = len(contenu.get("blocs", []))
    suite = f" — {blocs} segment(s) à réviser" if blocs else ""
    return (f"{ICONES[_statut(c)]} {c[0]} {c[1]} — id {c[2]} · "
            f"{catalogue[c].get('name', '')}{suite}")


choix = st.selectbox("Parcours", cles, format_func=_libelle, key="app_parcours")
ligne, direction, pid = choix
parcours = catalogue[choix]
instructions = parcours.get("direction", [])

mtime = _mtime_gtfs(gtfs_dir)
noms = _cached_noms_arrets(str(gtfs_dir), mtime)
stops = _cached_sequence_parcours(str(gtfs_dir), mtime, ligne, direction, pid)
if not stops:
    st.warning(f"Le GTFS ne connaît pas la ligne {ligne} {direction} (id {pid}) : "
               "aucun arrêt à apparier.")
    st.stop()

# ── État du parcours et choix de travail ─────────────────────────────────────

existant = reg.charger_appariement(ligne, direction, pid)
contenu, action = reg.calculer(ligne, direction, parcours, stops, noms, existant)
cle = _cle(ligne, direction, pid)
_etat_session(cle, contenu, existant)
ancres = st.session_state[f"app_ancres::{cle}"]

if ancres == reg.ancres_courantes(contenu) and action == "inchange":
    travail = contenu                       # rien de modifié : l'enregistré fait foi
else:
    travail = apparier(instructions, stops, noms, ancres=ancres)
modifie = ancres != reg.ancres_courantes(contenu)

statut = contenu.get("statut")
etat = f"{ICONES[statut]} **{LIBELLES[statut].capitalize()}**"
if statut == "valide":
    etat += f" par {contenu.get('valide_par')} le {contenu.get('valide_le', '')[:10]}"
if action != "inchange":
    etat += " · non encore enregistré (source modifiée depuis le dernier calcul)"
if statut == "a_revalider" and contenu.get("choix_abandonnes"):
    etat += f" · {contenu['choix_abandonnes']} choix humain(s) n'ont pas pu être reportés"
st.markdown(etat)

with st.container(horizontal=True):
    st.metric("Arrêts", len(stops), border=True)
    st.metric("Étapes G-D", len(instructions), border=True)
    st.metric("Segments à réviser", len(travail["blocs"]), border=True)
    st.metric("Arrêts fixés", len(ancres), border=True)

# ── Tableau des arrêts ───────────────────────────────────────────────────────

incertains = {seq for b in travail["blocs"] for seq in b["seqs"]}
etapes = {a["seq"]: a["etape"] for a in travail["arrets"]}
lignes = []
for a in travail["arrets"]:
    seq = a["seq"]
    if seq in ancres:
        marque = "📌 fixé"
    elif seq in incertains:
        marque = "⚠️ à réviser"
    else:
        marque = ""
    lignes.append({
        "seq": seq,
        "Fixé": seq in ancres,
        "Code": noms.get(a["stop_id"], {}).get("code", a["stop_id"]),
        "Arrêt": noms.get(a["stop_id"], {}).get("name", ""),
        "Étape G-D": a["etape"],
        "Confiance": float(a["confiance"]),
        "État": marque,
    })
df = pd.DataFrame(lignes).set_index("seq")

onglet_arrets, onglet_gd = st.tabs(["Arrêts", "Parcours G-D"])

with onglet_arrets:
    seulement = st.toggle(
        "Seulement les segments à réviser", value=bool(incertains), key=f"app_filtre::{cle}",
        help="Affiche les arrêts signalés et leurs voisins immédiats.",
    )
    vue_df = df
    if seulement and incertains:
        rang = list(df.index)
        garder = {rang[j] for i, s in enumerate(rang) if s in incertains
                  for j in range(max(0, i - 1), min(len(rang), i + 2))}
        vue_df = df[df.index.isin(garder)]
    elif seulement:
        st.caption("Aucun segment signalé : tout le parcours est affiché.")

    editor_key = f"app_editor::{cle}::{st.session_state[f'app_gen::{cle}']}"
    st.data_editor(
        vue_df,
        key=editor_key,
        hide_index=False,
        disabled=["Code", "Arrêt", "Confiance", "État"],
        column_config={
            "_index": st.column_config.NumberColumn("Seq", width="small"),
            "Fixé": st.column_config.CheckboxColumn(
                width="small", help="Un arrêt fixé est conservé tel quel ; l'automatique "
                "recalcule les autres autour de lui."),
            "Arrêt": st.column_config.TextColumn(width="large"),
            "Étape G-D": st.column_config.SelectboxColumn(
                width="large", required=True, options=list(range(len(instructions))),
                format_func=lambda k: f"{k:02d} · {instructions[k]}",
                help="Instruction du Gauche-Droite pendant laquelle l'arrêt est desservi. "
                     "La modifier fixe l'arrêt."),
            "Confiance": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="percent"),
        },
        on_change=_appliquer_edition,
        args=(cle, editor_key, list(vue_df.index), etapes, instructions, stops, noms),
    )

with onglet_gd:
    par_etape = {}
    for a in travail["arrets"]:
        par_etape.setdefault(a["etape"], []).append(a)
    apercu = []
    for k, instr in enumerate(instructions):
        arrets = par_etape.get(k) or [None]
        for i, a in enumerate(arrets):
            apercu.append({
                "Étape": k if i == 0 else None,
                "Instruction": instr if i == 0 else "",
                "Code": noms.get(a["stop_id"], {}).get("code", "") if a else "",
                "Arrêt": (("⚠️ " if a["seq"] in incertains else "📌 " if a["seq"] in ancres else "")
                          + noms.get(a["stop_id"], {}).get("name", "")) if a else "",
            })
    st.dataframe(pd.DataFrame(apercu), hide_index=True,
                 column_config={"Étape": st.column_config.NumberColumn(width="small")})

# ── Actions ──────────────────────────────────────────────────────────────────

if travail["blocs"]:
    st.caption("Valider confirme aussi les arrêts encore signalés, tels qu'affichés.")
with st.container(horizontal=True):
    valider = st.button("✅ Valider l'appariement", type="primary", key=f"app_valider::{cle}")
    if st.button("↩️ Annuler mes modifications", key=f"app_annuler::{cle}", disabled=not modifie):
        _oublier(cle)
        st.rerun()
    if st.button("🧹 Retirer tous les arrêts fixés", key=f"app_vider::{cle}", disabled=not ancres):
        st.session_state[f"app_ancres::{cle}"] = {}
        st.session_state[f"app_gen::{cle}"] += 1
        st.rerun()

if valider:
    par = st.session_state.get("auth_matricule") or depots.matricule_effectif() or "anonyme"
    try:
        reg.valider_appariement(ligne, direction, parcours, stops, noms, ancres, par,
                                st.session_state[f"app_version::{cle}"])
    except reg.ConflitAppariement:
        st.error("Un autre chauffeur a modifié cet appariement pendant votre révision. "
                 "Annulez vos modifications pour recharger sa version, puis recommencez.")
    except ValueError as exc:
        st.error(f"Validation refusée : {exc}.")
    else:
        _oublier(cle)
        st.session_state[FLASH] = ("success", f"Appariement {ligne} {direction} id {pid} validé.")
        st.rerun()

declencher_dialog_si_requis()
