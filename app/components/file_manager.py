"""Gestion de fichiers (liste, téléchargement, suppression, purge).

Utilisé par la page « Gestion des fichiers ». Les opérations de purge
s'appuient sur la date de modification des fichiers.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from app.utils import _fmt_mtime, _fmt_size


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