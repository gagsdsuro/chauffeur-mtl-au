"""chauffeur.ca — cartes agent : résolution par identité et rangement.

Une carte agent est identifiée par (numéro, liste/variation, jour-type) via
chauffeur.periodes.identite_ca — pas par sa seule date. Ce module résout les
PDF applicables à une journée (avec repli sur l'ancien nommage par date) et
range les PDF importés selon la politique d'identité : collision refusée sauf
remplacement explicite, sauvegarde .bak des versions écrasées.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from . import depots
from .depots import CA_DIR
from .journal import ecrire_bloc
from .periodes import identite_ca, nom_ca

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


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


@dataclass
class ResultatCA:
    """Issue de `annoter_et_ranger_ca` (sans dépendance à l'interface).

    statut : « ok » | « erreur » | « existe » (identité déjà présente, remplacement refusé).
    `detail` porte la sortie brute du traitement (à afficher en bloc de code).
    """

    statut: str
    message: str = ""
    detail: str = ""
    numero: str = ""
    groupe_id: str = ""
    jour_type: str = ""
    chemin_annotee: Path | None = None
    chemin_brute: Path | None = None
    avertissements: list[str] = field(default_factory=list)

    @property
    def succes(self) -> bool:
        return self.statut == "ok"


def annoter_et_ranger_ca(
    pdf: bytes | Path,
    jour: date,
    *,
    nom_source: str = "carte-agent.pdf",
    journee_numero=None,
    avec_gtfs: bool = True,
    deja_annotee: bool = False,
    remplacer: bool = False,
    ca_dir: Path | None = None,
    gtfs_dir: Path | None = None,
    executer: Callable = subprocess.run,
) -> ResultatCA:
    """Annote une carte agent PDF (horaires GTFS) puis la range par identité.

    Reprend le traitement de la page Préparation : sous-processus
    `scripts/carte_agent.py` (`--json`, ou `--meta-only` si `deja_annotee`),
    identité via `identite_ca`, rangement via `ranger_ca`, trace dans le journal
    « carte_agent ». `journee_numero` (facultatif) refuse une carte d'un autre
    numéro que la journée ; un numéro illisible (« ? ») est toujours refusé.
    """
    ca_dir = Path(ca_dir or _ca_dir())
    ca_dir.mkdir(parents=True, exist_ok=True)
    nom_source = Path(nom_source).name or "carte-agent.pdf"
    tmp_src = ca_dir / f"_tmp_{nom_source}"
    tmp_out = None if deja_annotee else ca_dir / f"_tmp_annotee_{nom_source}"
    tmp_src.write_bytes(pdf if isinstance(pdf, bytes) else Path(pdf).read_bytes())

    try:
        if deja_annotee:
            cmd = [sys.executable, str(SCRIPTS_DIR / "carte_agent.py"),
                   "--pdf", str(tmp_src), "--meta-only"]
        else:
            gtfs = Path(gtfs_dir) if gtfs_dir else depots.GTFS_DIR
            cmd = [sys.executable, str(SCRIPTS_DIR / "carte_agent.py"),
                   "--pdf", str(tmp_src), "--out", str(tmp_out),
                   "--date", str(jour), "--json"]
            if avec_gtfs and gtfs.exists():
                cmd += ["--gtfs", str(gtfs)]
            elif not avec_gtfs:
                cmd.append("--no-gtfs")

        result = executer(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            sortie = result.stderr or result.stdout
            ecrire_bloc("carte_agent", f"❌ Échec du traitement de {nom_source}\n{sortie}")
            return ResultatCA("erreur", "Erreur lors du traitement.", detail=sortie)

        try:
            meta = json.loads(result.stdout.strip().splitlines()[-1])
            numero_lu = str(meta["carte"]).strip()
        except (json.JSONDecodeError, IndexError, KeyError) as exc:
            return ResultatCA(
                "erreur", f"Sortie inattendue du traitement : {exc}", detail=result.stdout
            )
        if numero_lu in ("", "?"):
            return ResultatCA("erreur", "Numéro de carte illisible dans le PDF.")
        if journee_numero not in (None, "") and numero_lu != str(journee_numero):
            return ResultatCA(
                "erreur",
                f"La carte agent est la n° {numero_lu}, la journée porte le n° {journee_numero}.",
            )
        try:
            numero, groupe_id, jour_type = identite_ca(jour, meta["carte"])
        except (FileNotFoundError, ValueError) as exc:
            return ResultatCA("erreur", f"Impossible de calculer l'identité de la carte : {exc}")

        avertissements = []
        # Validation croisée (pas une source d'identité) : certaines cartes
        # impriment elles-mêmes leur jour-type ; on signale un écart sans bloquer.
        jt_imprime = meta.get("jour_type_imprime")
        if jt_imprime and jt_imprime != jour_type:
            variante_txt = f" ({meta['variante']})" if meta.get("variante") else ""
            avertissements.append(
                f"⚠️ Écart calendrier/carte : identite_ca calcule jour_type="
                f"« {jour_type} » pour cette date, mais la carte imprime "
                f"« {jt_imprime} »{variante_txt} (En vigueur : "
                f"{meta.get('en_vigueur') or '?'}). Vérifie le calendrier de "
                "référence — l'identité retenue reste celle du calendrier."
            )

        try:
            ranges = ranger_ca(
                numero, groupe_id, jour_type,
                annotee_tmp=tmp_src if deja_annotee else tmp_out,
                brute_tmp=None if deja_annotee else tmp_src,
                remplacer=remplacer, ca_dir=ca_dir,
            )
        except FileExistsError as exc:
            return ResultatCA("existe", str(exc), numero=numero, groupe_id=groupe_id,
                              jour_type=jour_type, avertissements=avertissements)

        dest_out = ranges["annotee"]
        trace = [
            f"✅ Carte agent n° {numero} · {groupe_id} · {jour_type}",
            f"  • Source : {nom_source}",
            f"  • Rangée : {dest_out}",
            f"  • Mode : {'remplacement direct (sans GTFS)' if deja_annotee else 'annotation GTFS'}",
        ]
        if jt_imprime and jt_imprime != jour_type:
            trace.append(f"  ⚠️ Écart calendrier/carte : la carte imprime « {jt_imprime} »")
        ecrire_bloc("carte_agent", "\n".join(trace))
        message = (
            "Version annotée remplacée directement (sans traitement GTFS) "
            f"— identité : n° {numero} · {groupe_id} · {jour_type}."
            if deja_annotee else
            f"Carte annotée et rangée — identité : n° {numero} · {groupe_id} · {jour_type}."
        )
        return ResultatCA(
            "ok", message, numero=numero, groupe_id=groupe_id, jour_type=jour_type,
            chemin_annotee=dest_out, chemin_brute=ranges["brute"],
            avertissements=avertissements,
        )
    finally:
        tmp_src.unlink(missing_ok=True)
        if tmp_out:
            tmp_out.unlink(missing_ok=True)
