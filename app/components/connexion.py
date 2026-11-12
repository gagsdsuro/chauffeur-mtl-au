"""Connexion par PIN — verrouillage des pages et statut de session côté app.

Garde la couche Streamlit sans logique métier : l'essentiel (hash, comptes,
verrouillage) vit dans `chauffeur.auth`. Ce module décide quand l'app exige
une connexion et transporte le matricule authentifié dans le `session_state`.
"""
from __future__ import annotations

import streamlit as st

from app.state import AUTH_MATRICULE, AUTH_NOM, AUTH_ROLE
from chauffeur import auth
from chauffeur.depots import mode_strict


def matricule_connecte() -> str | None:
    """Matricule authentifié de la session (None si non connecté)."""
    return st.session_state.get(AUTH_MATRICULE)


def est_connecte() -> bool:
    return matricule_connecte() is not None


def est_admin() -> bool:
    """True si le compte authentifié est Chauffeur-admin."""
    return (matricule_connecte() is not None
            and st.session_state.get(AUTH_ROLE) == auth.ROLE_ADMIN)


def _afficher_formulaire_connexion() -> None:
    st.markdown("## 🔒 Connexion")
    st.caption("Identifiez-vous pour accéder aux données personnelles.")
    with st.form("form_login", clear_on_submit=False):
        matricule = st.text_input(
            "Matricule", max_chars=5,
            placeholder="5 chiffres (20000-99999)",
            key="login_matricule",
        )
        pin = st.text_input(
            "PIN", type="password", max_chars=auth.PIN_MAX,
            placeholder=f"{auth.PIN_MIN}-{auth.PIN_MAX} chiffres",
            key="login_pin",
        )
        soumis = st.form_submit_button("Se connecter")
    if soumis:
        ok, message = auth.verifier_pin((matricule or "").strip(), pin or "")
        if ok:
            _ouvrir_session((matricule or "").strip())
        else:
            st.error(message)


def _afficher_creation_premier_compte() -> None:
    st.markdown("## 🔐 Premier lancement")
    st.caption(
        "Aucun compte n'est configuré. Créez le premier compte "
        "(il sera **Chauffeur-admin**)."
    )
    with st.form("form_initial_setup"):
        matricule = st.text_input(
            "Matricule", max_chars=5,
            placeholder="5 chiffres (20000-99999)",
            key="setup_matricule",
        )
        nom = st.text_input("Nom (optionnel)", key="setup_nom")
        pin = st.text_input(
            "PIN", type="password", max_chars=auth.PIN_MAX,
            placeholder=f"{auth.PIN_MIN}-{auth.PIN_MAX} chiffres",
            key="setup_pin",
        )
        pin2 = st.text_input(
            "Confirmer le PIN", type="password", max_chars=auth.PIN_MAX,
            key="setup_pin2",
        )
        soumis = st.form_submit_button("Créer le compte admin")
    if soumis:
        erreurs = []
        if pin != pin2:
            erreurs.append("Les deux PIN ne correspondent pas.")
        if not erreurs:
            try:
                auth.creer_compte(
                    (matricule or "").strip(), pin or "",
                    nom=(nom or "").strip() or None,
                )
                _ouvrir_session((matricule or "").strip())
            except ValueError as exc:
                erreurs.append(str(exc))
        if erreurs:
            for e in erreurs:
                st.error(e)


def _ouvrir_session(matricule: str) -> None:
    info = auth.compte_info(matricule) or {}
    st.session_state[AUTH_MATRICULE] = matricule
    st.session_state[AUTH_ROLE] = info.get("role") or auth.ROLE_CHAUFFEUR
    st.session_state[AUTH_NOM] = info.get("nom") or ""
    st.rerun()


def exiger_connexion() -> None:
    """Verrouille la page courante si l'authentification est requise.

    * Compte(s) configuré(s) ou mode strict → formulaire, puis `st.stop`.
    * Aucun compte en mode strict → création du premier compte (admin), puis stop.
    * Aucun compte, mode non strict → comportement legacy (rien à faire) :
      l'adoption de l'authentification est un choix explicite.
    """
    if est_connecte():
        return
    if auth.comptes_configure():
        _afficher_formulaire_connexion()
        st.stop()
    if mode_strict():
        _afficher_creation_premier_compte()
        st.stop()


def afficher_statut_connexion() -> None:
    """Identité, changement de PIN et déconnexion dans la barre latérale."""
    matricule = matricule_connecte()
    if matricule is None:
        return
    info = auth.compte_info(matricule) or {}
    role = info.get("role") or st.session_state.get(AUTH_ROLE) or ""
    etiquette = f"🚌 Chauffeur {matricule}" + (f" · {role}" if role else "")
    if st.sidebar.button("Se déconnecter", key="btn_deconnexion",
                         width="stretch"):
        _deconnecter()
    st.sidebar.caption(etiquette)
    _afficher_changement_pin(matricule)


def _afficher_changement_pin(matricule: str) -> None:
    """Changement du PIN personnel (l'ancien PIN est requis)."""
    with st.sidebar.expander("🔑 Changer mon PIN", expanded=False):
        ancien = st.text_input(
            "PIN actuel", type="password", max_chars=auth.PIN_MAX,
            key="pin_chg_ancien",
        )
        nouveau = st.text_input(
            "Nouveau PIN", type="password", max_chars=auth.PIN_MAX,
            key="pin_chg_nouveau",
        )
        confirmation = st.text_input(
            "Confirmer le PIN", type="password", max_chars=auth.PIN_MAX,
            key="pin_chg_confirmation",
        )
        clique = st.button("Changer le PIN", key="btn_changer_pin",
                           width="stretch")
        if clique:
            if nouveau != confirmation:
                st.error("Les deux nouveaux PIN ne correspondent pas.")
            else:
                try:
                    auth.changer_pin(matricule, ancien, nouveau)
                    st.success("PIN mis à jour.")
                except ValueError as exc:
                    st.error(str(exc))


def _deconnecter() -> None:
    # Les dates persistantes, brouillons et résultats appartiennent au compte
    # sortant. Ne rien transmettre au prochain compte dans le même navigateur.
    for cle in list(st.session_state):
        st.session_state.pop(cle, None)
    st.rerun()
