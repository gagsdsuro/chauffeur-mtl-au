# -*- coding: utf-8 -*-
"""Administration — gestion des comptes et des autorisations (Chauffeur-admin).

Garde-fou en plus de la navigation filtrée : directement atteignable par URL,
la page se verrouille pour un simple Chauffeur (st.info + st.stop). Toute la
logique d'autorisations vit dans `chauffeur.auth`.
"""
import bootstrap  # noqa: F401  (configure sys.path avant tout import)

bootstrap.initialiser_page()

import streamlit as st

from app.components.connexion import est_admin
from chauffeur import auth

if not est_admin():
    st.info("Page réservée aux Chauffeur-admin.")
    st.stop()

st.header("⚙️ Administration")
st.caption("Gestion des comptes : rôles, réinitialisation de PIN, déverrouillage, révocation.")

_flash = st.session_state.pop("admin_flash", None)
if _flash:
    st.success(_flash)


def _executer(cle: str, action: object) -> None:
    """Exécute une opération et rafraîchit l'écran (message éphémère)."""
    try:
        action()
        st.session_state["admin_flash"] = cle
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))


_admin_matricule = st.session_state["auth_matricule"]
_comptes = auth.lister_comptes()

# ── Tableau des comptes ────────────────────────────────────────────────────────
st.subheader("Comptes")
_routes = [
    {
        "matricule": c["matricule"],
        "nom": c["nom"] or "",
        "role": c["role"],
        "créé le": (c["creer_le"] or "")[:10],
        "verrouillé": c["verrouille"],
    }
    for c in _comptes
]
st.dataframe(_routes, width="stretch", hide_index=True)

# ── Actions sur un compte ──────────────────────────────────────────────────────
st.subheader("Actions sur un compte")
if not _comptes:
    st.info("Aucun compte.")
    st.stop()

_choix = st.selectbox(
    "Compte", [c["matricule"] for c in _comptes], key="admin_cible"
)
_cible = next(c for c in _comptes if c["matricule"] == _choix)
_est_soi = _choix == _admin_matricule
_cible_role = _cible["role"]

st.caption(
    f"{_cible.get('nom') or ''} · {_cible_role}"
    + (" · (vous)" if _est_soi else "")
)

_btn_col, _ = st.columns([1, 2])
with _btn_col:
    if _cible_role == auth.ROLE_CHAUFFEUR:
        if st.button("Promouvoir en Chauffeur-admin", key="btn_promouvoir",
                     width="stretch"):
            _executer("Compte promu Chauffeur-admin.",
                      lambda: auth.changer_role(_choix, _admin_matricule,
                                                auth.ROLE_ADMIN))
    elif _est_soi:
        if st.button("Se destituer (revenir Chauffeur)", key="btn_destituer",
                     width="stretch"):
            _executer("Vous êtes redevenu Chauffeur.",
                      lambda: auth.changer_role(_choix, _admin_matricule,
                                                auth.ROLE_CHAUFFEUR))
    else:
        st.caption("Autorité d'un autre administrateur : non modifiable.")

    if _cible["verrouille"]:
        if st.button("Déverrouiller", key="btn_deverrouiller",
                     width="stretch"):
            _executer("Compte déverrouillé.",
                      lambda: auth.deverrouiller_compte(_choix, _admin_matricule))

    if _cible_role == auth.ROLE_CHAUFFEUR and not _est_soi:
        confirmer = st.checkbox("Confirmer la révocation", key="admin_revoquer_conf")
        if st.button("Révoquer le compte", key="btn_revoquer",
                     disabled=not confirmer, width="stretch"):
            _executer(f"Compte {_choix} révoqué.",
                      lambda: auth.revoquer_compte(_choix, _admin_matricule))

# ── Réinitialisation du PIN (sans l'ancien) ────────────────────────────────────
with st.expander("🔑 Réinitialiser le PIN", expanded=False):
    nouveau = st.text_input(
        "Nouveau PIN", type="password", max_chars=auth.PIN_MAX,
        key="admin_pin_nouveau",
    )
    confirmation = st.text_input(
        "Confirmer le PIN", type="password", max_chars=auth.PIN_MAX,
        key="admin_pin_confirmation",
    )
    if st.button("Réinitialiser le PIN", key="btn_reset_pin",
                 width="stretch"):
        if nouveau != confirmation:
            st.error("Les deux PIN ne correspondent pas.")
        else:
            _executer(f"PIN de {_choix} réinitialisé.",
                      lambda: auth.reinitialiser_pin(_choix, nouveau,
                                                     _admin_matricule))

# ── Création d'un compte ───────────────────────────────────────────────────────
with st.expander("➕ Créer un compte", expanded=False):
    with st.form("form_admin_creation"):
        matricule = st.text_input(
            "Matricule", max_chars=5,
            placeholder="5 chiffres (20000-99999)",
            key="admin_nouveau_matricule",
        )
        nom = st.text_input("Nom (optionnel)", key="admin_nouveau_nom")
        pin = st.text_input(
            "PIN", type="password", max_chars=auth.PIN_MAX,
            placeholder=f"{auth.PIN_MIN}-{auth.PIN_MAX} chiffres",
            key="admin_nouveau_pin",
        )
        role = st.selectbox(
            "Rôle", [auth.ROLE_CHAUFFEUR, auth.ROLE_ADMIN],
            key="admin_nouveau_role",
        )
        creation = st.form_submit_button("Créer le compte")
    if creation:
        _executer(f"Compte {matricule} créé ({role}).",
                  lambda: auth.creer_compte(
                      (matricule or "").strip(), pin or "",
                      nom=(nom or "").strip() or None,
                      role=role, operateur=_admin_matricule))