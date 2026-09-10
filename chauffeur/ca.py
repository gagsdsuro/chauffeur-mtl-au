"""chauffeur.ca — cartes agent : résolution par identité et rangement.

Une carte agent est identifiée par (numéro, liste/variation, jour-type) via
chauffeur.periodes.identite_ca — pas par sa seule date. Ce module résout les
PDF applicables à une journée (avec repli sur l'ancien nommage par date) et
range les PDF importés selon la politique d'identité : collision refusée sauf
remplacement explicite, sauvegarde .bak des versions écrasées.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import depots
from .depots import CA_DIR
from .periodes import identite_ca, nom_ca


def _ca_dir() -> Path:
    """Répertoire des cartes agent : session (thread) si active, sinon constante."""
    return depots.repertoire_prive_contexte("ca") or CA_DIR


def resoudre_ca(jour: date, numero, ca_dir: Path | None = None) -> dict:
    """Résout le PDF de carte agent (brute + annotée) applicable à une journée.

    Cherche d'abord par identité (identite_ca) — ce qui permet la réutilisation
    d'une même CA entre journées partageant numéro/liste/jour-type. Si absent,
    replie sur l'ancien nommage par date (carte-agent-YYYY-MM-DD[-annotee|
    -surligné].pdf), pour les CA importées avant la refonte par identité.

    Champs retournés :
      identite — (numero, groupe_id, jour_type) ou None si non calculable
      brute    — Path du PDF brut, ou None
      annotee  — Path du PDF annoté, ou None
      legacy   — True si le PDF annoté résolu vient de l'ancien nommage par date
    """
    ca_dir = ca_dir or _ca_dir()
    date_str = jour.isoformat()
    identite = None
    brute = annotee = None

    if numero:
        try:
            identite = identite_ca(jour, str(numero))
        except (FileNotFoundError, ValueError):
            identite = None

    if identite:
        n, g, j = identite
        p_brute = ca_dir / nom_ca(n, g, j)
        p_annotee = ca_dir / nom_ca(n, g, j, annotee=True)
        if p_brute.exists():
            brute = p_brute
        if p_annotee.exists():
            annotee = p_annotee

    legacy = False
    if annotee is None:
        for suffixe in ("-annotee", "-surligné"):
            p = ca_dir / f"carte-agent-{date_str}{suffixe}.pdf"
            if p.exists():
                annotee, legacy = p, True
                break
    if brute is None:
        p = ca_dir / f"carte-agent-{date_str}.pdf"
        if p.exists():
            brute = p

    return {"identite": identite, "brute": brute, "annotee": annotee, "legacy": legacy}


def cle_note_carte(info: dict) -> str | None:
    """Clé de note (chauffeur.notes) pour un résultat de resoudre_ca().

    Identité « numero_groupe_id_jour_type » si calculable — la note suit la
    carte réutilisée d'une journée à l'autre, listes/variations/fériés
    distingués par identite_ca ; sinon nom du fichier legacy résolu sans
    suffixe d'annotation (note spécifique à la date). None si aucune CA.
    """
    if info.get("identite"):
        n, g, j = info["identite"]
        return f"{n}_{g}_{j}"
    p = info.get("annotee") or info.get("brute")
    if p is None:
        return None
    stem = Path(p).stem
    for suffixe in ("-annotee", "-surligné"):
        if stem.endswith(suffixe):
            return stem[: -len(suffixe)]
    return stem


def ranger_ca(numero: str, groupe_id: str, jour_type: str,
              annotee_tmp: Path, brute_tmp: Path | None = None,
              remplacer: bool = False, ca_dir: Path | None = None) -> dict:
    """Range une carte agent importée sous son identité (déplace les fichiers).

    annotee_tmp — PDF annoté temporaire, déplacé vers <identité>-annotee.pdf.
    brute_tmp   — PDF brut temporaire, déplacé vers <identité>.pdf ;
                  None = mode « déjà annotée » (seule la version annotée est
                  remplacée, la brute existante n'est pas touchée).

    Une identité déjà présente est refusée (FileExistsError) sauf
    remplacer=True — les destinations existantes sont alors sauvegardées en
    .bak avant le remplacement.

    Retourne {"annotee": Path, "brute": Path | None} (destinations finales).
    """
    ca_dir = ca_dir or _ca_dir()
    dest_annotee = ca_dir / nom_ca(numero, groupe_id, jour_type, annotee=True)
    dest_brute = None if brute_tmp is None else ca_dir / nom_ca(numero, groupe_id, jour_type)
    collision = dest_annotee.exists() or (dest_brute is not None and dest_brute.exists())

    if collision and not remplacer:
        raise FileExistsError(
            f"Une CA existe déjà pour cette identité (n° {numero} · "
            f"{groupe_id} · {jour_type})."
        )

    if collision:
        for dest in filter(None, (dest_brute, dest_annotee)):
            if dest.exists():
                dest.replace(dest.with_name(dest.name + ".bak"))

    if brute_tmp is not None:
        Path(brute_tmp).replace(dest_brute)
    Path(annotee_tmp).replace(dest_annotee)

    return {"annotee": dest_annotee, "brute": dest_brute}
