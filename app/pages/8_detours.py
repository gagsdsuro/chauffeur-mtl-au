#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page — Appariement des détours (évènements), commun à tous les chauffeurs.

Quand les informations d'un évènement ne permettent pas de situer son détour ou
l'ordre de ses arrêts ajoutés, le pipeline G-D le signale au lieu d'échouer en
silence. Ici le chauffeur fixe où le détour démarre, jusqu'où il barre le
parcours et dans quel ordre se posent les arrêts ajoutés. Le choix est enregistré
dans `data/Appariements/detours/` sous la **signature du détour** (sans numéro
d'évènement) : il resservira quand le même détour reviendra, et le rapport v2 de
tous les chauffeurs l'applique.

Aucune logique métier ici : signature, statuts, validation et contrôle de
version vivent dans `chauffeur.registre_detours` ; le placement dans `chauffeur.gd`.
"""
import bootstrap  # noqa: F401  (configure sys.path avant tout import)

bootstrap.initialiser_page()

import json  # noqa: E402
from copy import deepcopy  # noqa: E402
from datetime import date  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.components.session_dialog import declencher_dialog_si_requis  # noqa: E402
from app.utils import (  # noqa: E402
    _cached_noms_arrets, _cached_sequence_parcours, _mtime_gtfs,
)

import chauffeur.depots as depots  # noqa: E402
from chauffeur import registre_detours as rd  # noqa: E402
from chauffeur.gd import (  # noqa: E402
    annotate_events, apply_gd_detours, cle_arret_ajoute, etapes_des_arrets_ajoutes,
    event_applicable_to_parcours, insert_added_stops_inline, message_diagnostic,
    parse_description_gd, reference_ligne, resoudre_ref, rows_de_rendu,
)
from chauffeur.evenements import applicable_a_la_date  # noqa: E402
from chauffeur.journee import groupes_de_service  # noqa: E402
from chauffeur.registre_appariement import _parcours_uniques, appariement_pour_rapport  # noqa: E402

FLASH = "det_flash"
ICONES = {"auto": "✅", "valide": "✔️", "incertain": "⚠️", "a_revalider": "🔁", None: "⬜"}
LIBELLES = {"auto": "automatique", "valide": "validé", "incertain": "à réviser",
            "a_revalider": "à revalider", None: "résolu automatiquement"}

base = depots.DATA_DIR
events_dir, gd_dir = base / "Events", base / "Gauche-Droite"
detours_dir = depots.repertoire_detours(gd_dir)
gtfs_dir = depots.GTFS_DIR


def _oublier(cle: str) -> None:
    st.session_state[f"det_gen::{cle}"] = st.session_state.get(f"det_gen::{cle}", 0) + 1


st.header("Appariement des détours")
st.caption(
    "Situe un détour dans le parcours quand l'automatique ne peut pas le deviner. "
    "Commun à tous les chauffeurs, et réutilisé quand le même détour revient sous un autre numéro."
)
if st.session_state.get(FLASH):
    niveau, message = st.session_state.pop(FLASH)
    getattr(st, niveau)(message)

if not (gtfs_dir / "stops.txt").exists():
    st.error("GTFS absent : téléchargez-le depuis **Préparation d'une journée** "
             "avant de réviser un détour.")
    st.stop()

# ── Catalogue des détours ────────────────────────────────────────────────────

today = date.today()
stockes = rd.lister_detours(detours_dir)          # {(ligne, direction): contenu}


def _entrees():
    for (ligne, direction), contenu in stockes.items():
        for signature, entree in contenu.get("detours", {}).items():
            yield ligne, direction, signature, entree


def _evenements_actifs(ligne, direction, jour=None):
    evenements = depots.charger_evenements(ligne, direction, events_dir)
    return [e for e in evenements if (rd.non_expire(e, today) if jour is None
                                      else applicable_a_la_date(e, jour))]


with st.container(horizontal=True, vertical_alignment="bottom"):
    vue = st.segmented_control(
        "Afficher", ["À réviser", "Ma journée", "Tous"], default="À réviser", required=True,
        key="det_vue")
    if st.button("🔄 Synchroniser", key="det_sync",
                 help="Revérifie les détours des évènements non expirés (G-D, GTFS ou évènements modifiés)."):
        with st.spinner("Vérification des détours…"):
            messages = rd.synchroniser_tout_detours(base=base, log=True)
        st.session_state[FLASH] = ("info", "\n\n".join(messages) if messages
                                   else "Tous les détours sont déjà à jour.")
        st.rerun()

catalogue = {}      # (ligne, direction, signature) -> {"evenement", "entree"}


def _ajouter(ligne, direction, evenement):
    signature = rd.signature_detour(ligne, direction, evenement)
    entree = stockes.get((ligne, direction), {}).get("detours", {}).get(signature)
    catalogue.setdefault((ligne, direction, signature), {"evenement": evenement, "entree": entree})


if vue == "Ma journée":
    fenetre = depots.lister_journees_fenetre(today, journees_dir=bootstrap.journees_dir())
    if not fenetre:
        st.info("Aucune journée importée entre J−2 et J+5.")
        st.stop()
    jours = [j for j, _ in fenetre]
    jour = st.selectbox("Journée", jours, index=jours.index(today) if today in jours else 0,
                        format_func=lambda j: j.isoformat(), key="det_jour")
    journee = depots.charger_journee(dict(fenetre)[jour])
    for g in groupes_de_service(journee):
        for e in _evenements_actifs(g["ligne"].lower(), g["direction"], jour):
            _ajouter(g["ligne"].lower(), g["direction"], e)
elif vue == "À réviser":
    for ligne, direction, signature, entree in _entrees():
        if entree.get("statut") in rd.ETAT_A_REVISER:
            evenement = next((e for e in _evenements_actifs(ligne, direction)
                              if rd.signature_detour(ligne, direction, e) == signature),
                             rd.evenement_depuis_entree(entree))
            catalogue.setdefault((ligne, direction, signature),
                                 {"evenement": evenement, "entree": entree})
else:
    for fichier in sorted(events_dir.glob("*_*.json")):
        ligne, _, direction = fichier.stem.partition("_")
        for e in _evenements_actifs(ligne, direction):
            _ajouter(ligne, direction, e)

if not catalogue:
    st.success("Aucun détour à réviser." if vue == "À réviser" else "Aucun détour.")
    st.stop()


def _libelle(c):
    evenement, entree = catalogue[c]["evenement"], catalogue[c]["entree"]
    statut = (entree or {}).get("statut")
    return (f"{ICONES[statut]} {c[0]} {c[1]} — {evenement.get('titre', '')} "
            f"· évènement {evenement.get('evenement_id', '?')} · {LIBELLES[statut]}")


choix_detour = st.selectbox("Détour", list(catalogue), format_func=_libelle, key="det_detour")
ligne, direction, signature = choix_detour
evenement, entree = catalogue[choix_detour]["evenement"], catalogue[choix_detour]["entree"]
cle = f"{ligne}_{direction}_{signature}"
st.session_state.setdefault(f"det_gen::{cle}", 0)
gen = st.session_state[f"det_gen::{cle}"]
stocke = (stockes.get((ligne, direction)) or {})
version = stocke.get("version")
choix_enregistre = (entree or {}).get("choix") if (entree or {}).get("statut") in ("valide", "a_revalider") else None

# ── État du détour ───────────────────────────────────────────────────────────

statut = (entree or {}).get("statut")
etat = f"{ICONES[statut]} **{LIBELLES[statut].capitalize()}**"
if statut == "valide":
    etat += f" par {entree.get('valide_par')} le {(entree.get('valide_le') or '')[:10]}"
st.markdown(etat)
if (entree or {}).get("diagnostics"):
    for texte in entree["diagnostics"]:
        st.warning(texte)
if statut == "a_revalider":
    st.warning("Le G-D a changé : le choix enregistré ne s'applique plus tel quel. "
               "Recalculé automatiquement en attendant que vous le reconfirmiez.")

with st.expander("Description du détour (évènement)", expanded=False):
    st.write(evenement.get("description_gd") or "—")
    if evenement.get("arrets_annules"):
        st.write("**Arrêts annulés** : " + ", ".join(
            f"{a.get('id')} {a.get('nom', '')}".strip() for a in evenement["arrets_annules"]))
    if evenement.get("arrets_ajoutes"):
        st.write("**Arrêts ajoutés** : " + " · ".join(
            a if isinstance(a, str) else a.get("nom", "") for a in evenement["arrets_ajoutes"]))

# ── Parcours touchés ─────────────────────────────────────────────────────────

mtime = _mtime_gtfs(gtfs_dir)
noms = _cached_noms_arrets(str(gtfs_dir), mtime)
try:
    gd = json.loads(depots.chemin_gd(ligne, direction, gd_dir).read_text(encoding="utf-8"))
except (OSError, ValueError):
    st.error(f"G-D {ligne} {direction} introuvable ou illisible.")
    st.stop()

touches = {}      # id -> (parcours, stops, rows)
for parcours in _parcours_uniques(gd):
    stops = _cached_sequence_parcours(str(gtfs_dir), mtime, ligne, direction, parcours.get("id"))
    if not stops:
        continue
    rows, _ = appariement_pour_rapport(ligne, direction, parcours, stops, noms,
                                       depots.repertoire_appariements(gd_dir))
    codes = {r.get("stop_code") or r["stop_id"] for r in rows if r.get("stop_id")}
    if event_applicable_to_parcours(evenement, codes, parcours.get("direction", [])):
        touches[parcours.get("id")] = (parcours, stops, rows)
if not touches:
    st.info("Aucun parcours de cette ligne n'est touché par ce détour.")
    st.stop()

pid = st.selectbox("Parcours (aperçu)", list(touches), key=f"det_parcours::{cle}",
                   format_func=lambda p: f"id {p} · {touches[p][0].get('name', '')}")
parcours, stops, rows_base = touches[pid]

# ── Choix de travail ─────────────────────────────────────────────────────────

nu, _, _ = annotate_events(deepcopy(rows_base), [evenement])      # sans détour posé


def _libelle_ligne(i):
    r = nu[i]
    if r.get("stop_id"):
        return f"      ↳ {r.get('stop_code') or r['stop_id']} · {r.get('stop_name', '')}"
    return f"{i:03d} · {r.get('gd', '')}"


instructions_detour = parse_description_gd(evenement.get("description_gd") or "") or []
options_lignes = list(range(len(nu)))
deja = {"debut": None, "fin": None}
if choix_enregistre and choix_enregistre.get("debut"):
    deja["debut"] = resoudre_ref(nu, choix_enregistre["debut"])
    deja["fin"] = resoudre_ref(nu, choix_enregistre.get("fin"))

st.subheader("Début et fin du détour")
if instructions_detour:
    debut = st.selectbox(
        "Le détour s'insère avant…", [None, *options_lignes], key=f"det_debut::{cle}::{gen}",
        index=0 if deja["debut"] is None else deja["debut"] + 1,
        format_func=lambda i: "Automatique" if i is None else _libelle_ligne(i),
        help="Ligne du parcours devant laquelle viennent les étapes du détour.")
    fin = None
    if debut is not None:
        suivantes = [None, *[i for i in options_lignes if i >= debut and not nu[i].get("stop_id")]]
        fin = st.selectbox(
            "Dernière instruction contournée", suivantes, key=f"det_fin::{cle}::{gen}",
            index=suivantes.index(deja["fin"]) if deja["fin"] in suivantes else 0,
            format_func=lambda i: "Rien n'est barré" if i is None else _libelle_ligne(i),
            help="Les instructions du début à celle-ci (incluse) sont barrées.")
else:
    st.caption("La description du détour n'est pas exploitable : seul l'ordre des arrêts ajoutés "
               "peut être réglé ici.")
    debut = fin = None

# Arrêts ajoutés : prérempli avec ce que l'automatique a fait (ou le choix enregistré).
lignes_auto = apply_gd_detours(deepcopy(nu), [evenement])
_, ajoutes, _ = annotate_events(deepcopy(rows_base), [evenement])
lignes_auto, _ = insert_added_stops_inline(lignes_auto, ajoutes)
auto = {r["stop_name"]: (etape, avant)
        for r, etape, avant in etapes_des_arrets_ajoutes(lignes_auto)}
enregistres = {a["cle"]: (rang, a) for rang, a in
               enumerate((choix_enregistre or {}).get("arrets_ajoutes") or [])}
arrets_df = None
if ajoutes:
    st.subheader("Arrêts ajoutés")
    lignes_df = []
    for ordre, a in enumerate(ajoutes):
        k = cle_arret_ajoute(a)
        if k in enregistres:
            rang, c = enregistres[k]
            etape, avant = c["etape"], c["avant"]
        else:
            rang, (etape, avant) = ordre, auto.get(a["name"], (0, False))
        lignes_df.append({"cle": k, "Ordre": rang + 1, "Arrêt": a["name"],
                          "Étape du détour": etape, "Avant l'étape": avant})
    steps = max(len(instructions_detour), 1)
    arrets_df = st.data_editor(
        pd.DataFrame(lignes_df).set_index("cle"), key=f"det_arrets::{cle}::{gen}",
        disabled=["Arrêt"], column_config={
            "Ordre": st.column_config.NumberColumn(min_value=1, step=1, width="small",
                                                   help="Ordre de service des arrêts ajoutés."),
            "Arrêt": st.column_config.TextColumn(width="large"),
            "Étape du détour": st.column_config.SelectboxColumn(
                width="large", required=True, options=list(range(steps)),
                format_func=lambda k: (f"{k} · {instructions_detour[k]}"
                                       if k < len(instructions_detour) else str(k)),
                help="Étape du détour à laquelle l'arrêt se pose."),
            "Avant l'étape": st.column_config.CheckboxColumn(width="small"),
        })

# ── Aperçu ───────────────────────────────────────────────────────────────────

choix_travail = {"debut": reference_ligne(nu, debut) if debut is not None else None,
                 "fin": reference_ligne(nu, fin) if fin is not None else None}
if arrets_df is not None:
    triee = arrets_df.sort_values("Ordre", kind="stable")
    choix_travail["arrets_ajoutes"] = [
        {"cle": k, "etape": int(r["Étape du détour"]), "avant": bool(r["Avant l'étape"])}
        for k, r in triee.iterrows()]
sans_choix = not (choix_travail["debut"] or choix_travail.get("arrets_ajoutes"))

diagnostics = []
fournis = None if sans_choix else (lambda e: choix_travail if choix_travail["debut"] else None)
fournis_arrets = None
if choix_travail.get("arrets_ajoutes"):
    par_cle = {a["cle"]: dict(rang=i, etape=a["etape"], avant=a["avant"])
               for i, a in enumerate(choix_travail["arrets_ajoutes"])}
    fournis_arrets = lambda stop_info: par_cle.get(cle_arret_ajoute(stop_info))  # noqa: E731
apercu = apply_gd_detours(deepcopy(nu), [evenement], diagnostics, fournis)
_, ajoutes, _ = annotate_events(deepcopy(rows_base), [evenement])
apercu, _ = insert_added_stops_inline(apercu, ajoutes, diagnostics, fournis_arrets)
for d in diagnostics:
    st.warning(message_diagnostic(d))

lignes_apercu = []
for r in rows_de_rendu(apercu):
    if r.get("detour_added"):
        marque, texte = "🟠", r["gd"]
    elif r.get("added_inline"):
        marque, texte = "➕", ""
    else:
        marque = "✂️" if r.get("detour_removed") else ""
        texte = r.get("gd", "")
    lignes_apercu.append({
        "": marque, "Instruction": texte,
        "Code": r.get("stop_code", ""),
        "Arrêt": ("✖ " if r.get("cancelled") else "") + (r.get("stop_name") or ""),
    })
with st.expander("Aperçu du parcours avec ce choix", expanded=True):
    st.dataframe(pd.DataFrame(lignes_apercu), hide_index=True, height=420,
                 column_config={"": st.column_config.TextColumn(width="small")})

# ── Actions ──────────────────────────────────────────────────────────────────

with st.container(horizontal=True):
    valider = st.button("✅ Valider ce choix", type="primary", key=f"det_valider::{cle}",
                        disabled=sans_choix,
                        help="Enregistre le choix pour tous les chauffeurs.")
    if st.button("↩️ Annuler mes modifications", key=f"det_annuler::{cle}"):
        _oublier(cle)
        st.rerun()
    retirer = st.button("🧹 Retirer le choix enregistré", key=f"det_retirer::{cle}",
                        disabled=statut not in ("valide", "a_revalider"))

par = st.session_state.get("auth_matricule") or depots.matricule_effectif() or "anonyme"
if valider:
    try:
        rd.valider_detour(ligne, direction, evenement, choix_travail, par, version, detours_dir)
    except rd.ConflitAppariement:
        st.error("Un autre chauffeur a modifié les détours de cette ligne pendant votre révision. "
                 "Annulez vos modifications pour recharger sa version, puis recommencez.")
    except ValueError as exc:
        st.error(f"Validation refusée : {exc}.")
    else:
        _oublier(cle)
        st.session_state[FLASH] = ("success", f"Détour {ligne} {direction} validé.")
        st.rerun()
if retirer:
    try:
        rd.retirer_choix(ligne, direction, signature, par, version, detours_dir)
    except (rd.ConflitAppariement, ValueError) as exc:
        st.error(f"Retrait refusé : {exc}.")
    else:
        _oublier(cle)
        st.session_state[FLASH] = ("success", "Choix retiré : le détour redevient automatique.")
        st.rerun()

declencher_dialog_si_requis()
