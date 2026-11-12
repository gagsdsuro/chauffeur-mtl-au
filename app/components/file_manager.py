"""Explorateur compact : widgets et aperçus, opérations déléguées au domaine."""
from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from app.components.apercu_html import afficher_rapport_html

from chauffeur import fichiers as domaine
from chauffeur.periodes import listes_fichiers, periode_pour_date
from chauffeur.presentation_evenements import presenter_evenement, rendre_table_evenements_html


def _memoriser(cle, stockage):
    st.session_state[stockage][cle] = st.session_state[f"fm_widget_{cle}"]


def _choix(label, options, cle, stockage, defaut=None, format_func=str):
    etat = st.session_state[stockage]
    valeur = etat.get(cle, defaut if defaut is not None else options[0])
    if valeur not in options:
        valeur = options[0]
    etat[cle] = valeur
    key = f"fm_widget_{cle}"
    st.session_state[key] = valeur
    return st.selectbox(label, options, key=key, format_func=format_func,
                        on_change=_memoriser, args=(cle, stockage))


def _texte(label, cle, stockage):
    key = f"fm_widget_{cle}"
    st.session_state[key] = st.session_state[stockage].get(cle, "")
    return st.text_input(label, key=key, on_change=_memoriser, args=(cle, stockage))


def _date(label, cle, stockage):
    key = f"fm_widget_{cle}"
    st.session_state[key] = st.session_state[stockage].get(cle)
    return st.date_input(label, value=None, key=key, on_change=_memoriser, args=(cle, stockage))


def afficher_apercu(categorie, nom, brut):
    suffixe = Path(nom).suffix
    if suffixe == ".pdf":
        st.pdf(brut, height=650, key=f"fm_pdf_{categorie}_{nom}")
        return
    if suffixe == ".html":
        afficher_rapport_html(brut.decode("utf-8"), height=650)
        return
    contenu = json.loads(brut)
    vue = st.segmented_control("Présentation", ["Aperçu", "JSON"], default="Aperçu",
                               key=f"fm_vue_{categorie}_{nom}")
    if vue == "JSON":
        st.json(contenu)
    elif categorie == "ev":
        evenements = [presenter_evenement(e) for e in contenu.get("detours", [])]
        if evenements:
            st.markdown(rendre_table_evenements_html(evenements), unsafe_allow_html=True)
        else:
            st.caption("Aucun événement enregistré.")
    elif categorie == "gd":
        parcours = [p for r in contenu.get("routes", []) for p in r.get("parcours", [])]
        if not parcours:
            st.caption("Aucun parcours enregistré.")
            return
        i = st.selectbox("Parcours", range(len(parcours)),
                         format_func=lambda i: f"{parcours[i].get('id', '?')} · {parcours[i].get('name', '')}",
                         key=f"fm_parcours_{nom}")
        p = parcours[i]
        st.write(f"{p.get('start', '')} ({p.get('start_code', '')}) → {p.get('end', '')} ({p.get('end_code', '')})")
        st.dataframe([{"Étape": i + 1, "Instruction": texte} for i, texte in enumerate(p.get("direction", []))],
                     hide_index=True, width="stretch")
    else:
        st.write(f"Journée {contenu.get('journee_numero', '—')} · {contenu.get('garage', '—')}")
        st.caption(f"Temps travaillé : {contenu.get('temps_travaille', '—')}")
        pieces = contenu.get("pieces", [])
        if not pieces:
            st.info("Cette journée ne contient aucune pièce de travail.")
        for p in pieces:
            with st.expander(f"Pièce {p.get('id', '—')} · {p.get('type_horaire', 'horaire')}", expanded=True):
                trajets = p.get("trajets", [])
                if not trajets:
                    st.caption("Aucun trajet pour cette pièce.")
                else:
                    st.dataframe([{"Type": t.get("type", ""), "Ligne": t.get("ligne", ""),
                                   "Direction": t.get("direction", ""),
                                   "Départ": t.get("depart", {}).get("heure", ""),
                                   "Arrivée": t.get("arrivee", {}).get("heure", "")}
                                  for t in trajets], hide_index=True, width="stretch")


def editer(categorie, nom, brut, etat):
    identite = f"{categorie}/{nom}"
    brouillons = etat.setdefault("brouillons", {})
    if identite not in brouillons:
        brouillons[identite] = {"texte": brut.decode("utf-8"), "empreinte": domaine.empreinte(brut)}
    brouillon = brouillons[identite]
    st.caption("Les imports ultérieurs peuvent remplacer ces corrections. Une sauvegarde sera conservée.")
    # Le callback copie le texte hors de la clé widget avant sa disparition.
    key = f"fm_edition_{identite}"
    if key not in st.session_state:
        st.session_state[key] = brouillon["texte"]
    def retenir():
        brouillon["texte"] = st.session_state[key]
    st.text_area("Contenu JSON", height=350, key=key, on_change=retenir)
    with st.form(f"fm_enregistrement_{identite}"):
        sauver = st.form_submit_button("Enregistrer", type="primary")
        annuler = st.form_submit_button("Annuler")
    if sauver:
        brouillon["texte"] = st.session_state[key]
        try:
            domaine.enregistrer(categorie, nom, brouillon["texte"], brouillon["empreinte"])
            del brouillons[identite]
            etat.pop("edition", None)
            st.session_state.pop(key, None)
            etat["message"] = "Fichier enregistré ; version précédente sauvegardée."
            st.rerun()
        except (OSError, ValueError, PermissionError) as exc:
            st.error(str(exc))
    if annuler:
        del brouillons[identite]
        etat.pop("edition", None)
        st.session_state.pop(key, None)
        st.rerun()
    if domaine.empreinte(brut) != brouillon["empreinte"]:
        st.warning("Le fichier a changé depuis l'ouverture de ce brouillon.")
        st.download_button("Télécharger le brouillon", brouillon["texte"], file_name=f"brouillon-{nom}", key=f"fm_draft_{identite}")
        if st.button("Recharger le fichier et remplacer le brouillon", key=f"fm_reload_{identite}"):
            del brouillons[identite]
            st.session_state.pop(key, None)
            st.rerun()


def afficher_fiche(categorie, fichier, etat):
    nom = fichier.nom
    st.subheader(nom)
    st.caption(f"{fichier.taille:,} octets · modifié le {datetime.fromtimestamp(fichier.modification):%d/%m/%Y %H:%M}")
    try:
        brut = domaine.lire(categorie, nom)
        autorise = domaine.peut_modifier(categorie)
        with st.container(horizontal=True):
            mime = {".pdf": "application/pdf", ".html": "text/html", ".json": "application/json"}[Path(nom).suffix]
            st.download_button("Télécharger", brut, file_name=nom, mime=mime, icon=":material/download:")
            if autorise:
                if categorie in ("journee", "gd", "ev") and st.button("Modifier", icon=":material/edit:"):
                    etat["edition"] = f"{categorie}/{nom}"
                if st.button("Supprimer", icon=":material/delete:"):
                    etat["suppression"] = (categorie, nom, domaine.empreinte(brut))
        confirmation = etat.get("suppression")
        if confirmation and confirmation[:2] == (categorie, nom):
            st.warning(f"Supprimer définitivement {nom} ?")
            with st.container(horizontal=True):
                if st.button("Confirmer la suppression"):
                    domaine.supprimer(*confirmation)
                    etat.pop("suppression", None)
                    etat.setdefault("brouillons", {}).pop(f"{categorie}/{nom}", None)
                    st.rerun()
                if st.button("Conserver ce fichier"):
                    etat.pop("suppression", None)
                    st.rerun()
        if autorise and etat.get("edition") == f"{categorie}/{nom}":
            editer(categorie, nom, brut, etat)
        else:
            afficher_apercu(categorie, nom, brut)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        st.error(f"Impossible de traiter ce fichier : {exc}")


def entretien(categorie, fichiers, etat):
    if not domaine.peut_modifier(categorie):
        st.caption("Les fichiers communs sont modifiables par les administrateurs.")
        return
    jours = 90 if categorie in ("ev", "rp") else 365
    with st.expander("Entretien"):
        candidats = domaine.candidats_purge(fichiers, jours)
        st.caption(f"{len(candidats)} fichier(s) modifié(s) il y a plus de {jours} jours. Toutes les périodes sont concernées.")
        if candidats:
            st.dataframe([{"Fichier": f.nom, "Modification": datetime.fromtimestamp(f.modification)} for f in candidats], hide_index=True)
            if st.button("Préparer la purge", key=f"fm_purge_{categorie}"):
                try:
                    etat["purge"] = (categorie, [(f.nom, domaine.empreinte(domaine.lire(categorie, f.nom))) for f in candidats])
                except OSError as exc:
                    st.error(str(exc))
        if etat.get("purge", (None,))[0] == categorie:
            st.warning(f"Supprimer définitivement les {len(etat['purge'][1])} fichiers confirmés ci-dessous ?")
            st.write([nom for nom, _ in etat["purge"][1]])
            with st.container(horizontal=True):
                if st.button("Confirmer la purge", key=f"fm_purge_ok_{categorie}"):
                    erreurs = []
                    for nom, empreinte in etat["purge"][1]:
                        try:
                            domaine.supprimer(categorie, nom, empreinte)
                        except (OSError, ValueError) as exc:
                            erreurs.append(f"{nom} : {exc}")
                    etat.pop("purge", None)
                    etat["message"] = "Purge terminée." if not erreurs else "Purge partielle : " + "; ".join(erreurs)
                    st.rerun()
                if st.button("Annuler la purge"):
                    etat.pop("purge", None)
                    st.rerun()


def export_journees(etat):
    st.subheader("Export des journées")
    st.caption("Intervalle indépendant des filtres de l'explorateur. Une ligne par pièce de travail.")
    dates = [f.date for f in domaine.inventorier("journee") if f.date]
    if not dates:
        st.info("Aucune journée datée à exporter.")
        return
    with st.form("fm_export_dates"):
        debut = st.date_input("Date de début", min(dates))
        fin = st.date_input("Date de fin", max(dates))
        generer = st.form_submit_button("Préparer l'export")
    if generer:
        etat.pop("export", None)
        try:
            lignes, csv, erreurs = domaine.exporter_journees(debut, fin)
            etat["export"] = (debut, fin, lignes, csv, erreurs)
        except (OSError, ValueError) as exc:
            st.error(str(exc))
    if "export" in etat:
        debut, fin, lignes, csv, erreurs = etat["export"]
        st.caption(f"Export préparé du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} · {len(lignes)} pièce(s)")
        for erreur in erreurs:
            st.warning(erreur)
        if lignes:
            st.dataframe(lignes, hide_index=True, width="stretch")
            st.download_button("Télécharger le CSV", csv, file_name=f"journees-{debut}-{fin}.csv", mime="text/csv")
        else:
            st.info("Aucune pièce dans cet intervalle.")


def explorateur(stockage):
    etat = st.session_state[stockage]
    if message := etat.pop("message", None):
        st.info(message)
    with st.container(horizontal=True, vertical_alignment="bottom"):
        categorie = _choix("Catégorie", list(domaine.CATEGORIES), "categorie", stockage,
                            format_func=domaine.CATEGORIES.get)
        if st.button("Export des journées", icon=":material/download:"):
            etat["export_ouvert"] = not etat.get("export_ouvert", False)
    if etat.get("export_ouvert"):
        with st.container(border=True):
            export_journees(etat)
    fichiers = domaine.inventorier(categorie)
    filtres = {}
    if categorie in ("ca", "journee"):
        periode_col, recherche_col = st.columns(2)
        with periode_col:
            periodes = listes_fichiers()
            actuelle = periode_pour_date(datetime.now(ZoneInfo("America/Toronto")).date())
            labels = {"*": "Toutes les périodes", "?": "Période indéterminée"}
            labels.update({p.cle: p.libelle for p in reversed(periodes)})
            filtres["periode"] = _choix("Période", list(labels), f"{categorie}_periode", stockage,
                                        actuelle.cle if actuelle else "*", labels.get)
        with recherche_col:
            filtres["recherche"] = _texte("Rechercher un fichier", f"{categorie}_recherche", stockage)
    else:
        filtres["recherche"] = _texte("Rechercher un fichier", f"{categorie}_recherche", stockage)
    with st.expander("Filtres et tri"):
        tris = ["Nom", "Date décroissante", "Modification récente", "Ligne"]
        filtres["tri"] = _choix("Trier par", tris, f"{categorie}_tri", stockage,
                                "Date décroissante" if categorie in ("journee", "rp") else "Ligne" if categorie in ("gd", "ev") else "Nom")
        if categorie in ("ca", "journee"):
            regimes = {"*": "Tous", **domaine.REGIMES}
            filtres["regime"] = _choix("Régime", list(regimes), f"{categorie}_regime", stockage, format_func=regimes.get)
        if categorie == "ca":
            filtres["jour_type"] = _choix("Jour-type", ["*", "semaine", "samedi", "dimanche", "variation"], "ca_jour_type", stockage, format_func=lambda x: "Tous" if x == "*" else x.capitalize())
            filtres["version"] = _choix("Version", ["*", "originale", "annotée"], "ca_version", stockage, format_func=lambda x: "Toutes" if x == "*" else x.capitalize())
        if categorie in ("gd", "ev"):
            for cle, label in (("ligne", "Ligne"), ("direction", "Direction")):
                options = ["*"] + sorted({getattr(f, cle) for f in fichiers if getattr(f, cle)})
                filtres[cle] = _choix(label, options, f"{categorie}_{cle}", stockage, format_func=lambda x: "Toutes" if x == "*" else x)
        if categorie in ("journee", "rp"):
            filtres["debut"] = _date("À partir du", f"{categorie}_debut", stockage)
            filtres["fin"] = _date("Jusqu'au", f"{categorie}_fin", stockage)
        if categorie == "rp":
            filtres["format"] = _choix("Format", ["*", ".pdf", ".html"], "rp_format", stockage, format_func=lambda x: "Tous" if x == "*" else x[1:].upper())
    visibles = domaine.filtrer(fichiers, **filtres)
    signature = repr(filtres)
    if etat.get(f"{categorie}_filtre") != signature:
        etat[f"{categorie}_page"] = 0
        etat[f"{categorie}_filtre"] = signature
    noms = [f.nom for f in visibles]
    selection = etat.get(f"{categorie}_selection")
    if selection not in noms:
        selection = None
        etat.pop(f"{categorie}_selection", None)
    st.caption(f"{len(visibles)} fichier(s) trouvé(s) sur {len(fichiers)}")
    gauche, droite = st.columns([2, 3])
    with gauche:
        nb_pages = max(1, (len(visibles) + 9) // 10)
        page = min(etat.get(f"{categorie}_page", 0), nb_pages - 1)
        with st.container(horizontal=True):
            if st.button("Précédent", disabled=page == 0):
                etat[f"{categorie}_page"] = page - 1
                st.rerun()
            st.caption(f"Page {page + 1} / {nb_pages}")
            if st.button("Suivant", disabled=page == nb_pages - 1):
                etat[f"{categorie}_page"] = page + 1
                st.rerun()
        portion = visibles[page * 10:(page + 1) * 10]
        if portion:
            def selectionner(noms_page, widget):
                lignes = st.session_state[widget]["selection"]["rows"]
                etat[f"{categorie}_selection"] = noms_page[lignes[0]] if lignes else None
            noms_page = [f.nom for f in portion]
            # Une clé liée au contenu évite de réinterpréter une ancienne position.
            ident = domaine.empreinte(repr((signature, noms_page)).encode())[:16]
            key = f"fm_liste_{categorie}_{ident}"
            st.dataframe([{"Fichier": f.nom, "Modifié le": datetime.fromtimestamp(f.modification)} for f in portion],
                         hide_index=True, width="stretch", height=385, key=key,
                         selection_mode="single-row", on_select=lambda: selectionner(noms_page, key),
                         selection_default={"selection": {"rows": [noms_page.index(selection)] if selection in noms_page else []}})
        else:
            st.info("Aucun fichier ne correspond aux filtres.")
    with droite:
        if selection:
            afficher_fiche(categorie, next(f for f in visibles if f.nom == selection), etat)
        else:
            st.caption("Sélectionnez un fichier pour afficher son aperçu.")
    entretien(categorie, fichiers, etat)
