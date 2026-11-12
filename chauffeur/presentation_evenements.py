"""Projection commune des évènements pour les rapports, l'app et les journaux.

Ce module ne fait aucune lecture de fichier. Il transforme les dictionnaires du
format ``data/Events`` en valeurs d'affichage sûres et cohérentes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
import re

from .gd import parse_description_gd


@dataclass(frozen=True)
class ArretAffiche:
    identifiant: str
    nom: str

    @property
    def texte(self) -> str:
        if self.identifiant and self.nom:
            return f"{self.identifiant} – {self.nom}"
        return self.identifiant or self.nom or "—"


@dataclass(frozen=True)
class EvenementAffiche:
    evenement_id: str
    titre: str
    motif: str
    debut: str
    fin: str
    periode: str
    effectif: str
    instructions_gd: tuple[str, ...]
    commentaire: str
    arrets_annules: tuple[ArretAffiche, ...]
    arrets_ajoutes: tuple[ArretAffiche, ...]
    applicable: bool | None = None
    raison_exclusion: str = ""


def _formater_date_heure(valeur) -> str:
    if not valeur:
        return "—"
    try:
        dt = datetime.fromisoformat(str(valeur))
    except (TypeError, ValueError):
        return str(valeur)
    return dt.strftime("%Y-%m-%d\n%H:%M")


def _formater_periode(debut: str, fin: str) -> str:
    if debut == "—" and fin == "—":
        return "—"
    return f"{debut}\n→\n{fin}"


def _normaliser_arret(arret) -> ArretAffiche:
    if isinstance(arret, dict):
        identifiant = str(arret.get("id") or arret.get("code") or "").strip()
        nom = str(arret.get("nom") or arret.get("name") or "").strip()
        return ArretAffiche(identifiant, nom)

    texte = str(arret or "").strip()
    match = re.match(r"^(\d{5})\s*[-–]\s*(.+)$", texte)
    if match:
        return ArretAffiche(match.group(1), match.group(2).strip())
    return ArretAffiche("", texte)


def instructions_description_gd(description) -> tuple[str, ...]:
    """Retourne une instruction par ligne, sans inventer de coupure perdue.

    Les nouveaux imports conservent les retours de ligne du portail. Pour les
    anciennes chaînes aplaties, ``parse_description_gd`` fournit un repli au
    mieux selon les marqueurs VIA/G/D.
    """
    texte = str(description or "").strip()
    if not texte:
        return ()
    if "\n" in texte:
        return tuple(ligne.strip() for ligne in texte.splitlines() if ligne.strip())
    instructions = parse_description_gd(texte)
    return tuple(instructions or (texte,))


def presenter_evenement(event: dict, *, applicable: bool | None = None,
                        raison_exclusion: str = "") -> EvenementAffiche:
    debut = _formater_date_heure(event.get("date_heure_debut"))
    fin = _formater_date_heure(event.get("date_heure_fin"))
    return EvenementAffiche(
        evenement_id=str(event.get("evenement_id") or "?"),
        titre=str(event.get("titre") or "(sans titre)"),
        motif=str(event.get("motif") or ""),
        debut=debut,
        fin=fin,
        periode=_formater_periode(debut, fin),
        effectif=str(event.get("effectif") or "—"),
        instructions_gd=instructions_description_gd(event.get("description_gd")),
        commentaire=str(event.get("commentaire") or ""),
        arrets_annules=tuple(
            _normaliser_arret(a) for a in (event.get("arrets_annules") or [])
        ),
        arrets_ajoutes=tuple(
            _normaliser_arret(a) for a in (event.get("arrets_ajoutes") or [])
        ),
        applicable=applicable,
        raison_exclusion=raison_exclusion,
    )


def _details_evenement_texte(event: dict, retrait: bool = False) -> list[str]:
    ev = presenter_evenement(event)
    lignes = []
    if retrait:
        lignes.append(f"🗑️ Événement {ev.evenement_id} retiré — {ev.titre}")
    else:
        lignes.append(f"#{ev.evenement_id} — {ev.titre}")
    if ev.motif:
        lignes.append(f"   Motif : {ev.motif}")
    lignes.append("   Détour & commentaires :")
    if ev.instructions_gd:
        lignes.append("     G-D :")
        lignes.extend(f"       {instruction}" for instruction in ev.instructions_gd)
    if ev.commentaire:
        lignes.append(f"     Commentaire : {ev.commentaire}")
    if not ev.instructions_gd and not ev.commentaire:
        lignes.append("     —")
    lignes.append("   Arrêts :")
    if ev.arrets_annules:
        lignes.append("     Annulés ou concernés :")
        lignes.extend(f"       - {arret.texte}" for arret in ev.arrets_annules)
    if ev.arrets_ajoutes:
        lignes.append("     Ajoutés :")
        lignes.extend(f"       + {arret.texte}" for arret in ev.arrets_ajoutes)
    if not ev.arrets_annules and not ev.arrets_ajoutes:
        lignes.append("     —")
    return lignes


def formater_evenement_retire(event: dict) -> str:
    """Résumé texte détaillé d'un ancien évènement retiré."""
    lignes = _details_evenement_texte(event, retrait=True)
    return "\n".join(lignes)


def formater_evenement_modifie(identifiant: str, anciens: list[dict],
                               nouveaux: list[dict]) -> str:
    """Résumé texte des deux versions et de toutes leurs variantes."""
    lignes = [f"⚠️ Événement {identifiant} modifié"]
    for etiquette, versions in (("Avant", anciens), ("Après", nouveaux)):
        lignes.append(f"   {etiquette} :")
        if not versions:
            lignes.append("     —")
            continue
        for index, event in enumerate(versions, start=1):
            if len(versions) > 1:
                lignes.append(f"     Variante {index} :")
            lignes.extend(f"     {ligne}" for ligne in _details_evenement_texte(event))
    return "\n".join(lignes)


def rendre_table_evenements_html(evenements: list[EvenementAffiche]) -> str:
    """Tableau HTML responsive; toutes les valeurs métier sont échappées."""
    def lignes_html(valeurs) -> str:
        return "<br>".join(escape(str(v)) for v in valeurs)

    lignes = []
    for ev in evenements:
        if ev.applicable is True:
            etat = '<span class="evt-ok">✅ Applicable</span>'
        elif ev.applicable is False:
            etat = '<span class="evt-non">⬜ Non applicable</span>'
            if ev.raison_exclusion:
                etat += f'<div class="evt-raison">{escape(ev.raison_exclusion)}</div>'
        else:
            etat = "—"

        identite = f"<strong>#{escape(ev.evenement_id)}</strong><br>{escape(ev.titre)}"
        if ev.motif:
            identite += f'<br><em>{escape(ev.motif)}</em>'

        details = []
        if ev.instructions_gd:
            details.append("<strong>G-D :</strong><br>" + lignes_html(ev.instructions_gd))
        if ev.commentaire:
            details.append("<strong>Commentaire :</strong><br>" + escape(ev.commentaire).replace("\n", "<br>"))
        detour = "<br>".join(details) if details else "—"

        arrets = []
        if ev.arrets_annules:
            arrets.append("<strong>Annulés ou concernés :</strong><br>" +
                          lignes_html(a.texte for a in ev.arrets_annules))
        if ev.arrets_ajoutes:
            arrets.append("<strong>Ajoutés :</strong><br>" +
                          lignes_html(a.texte for a in ev.arrets_ajoutes))
        arrets_html = "<br>".join(arrets) if arrets else "—"

        lignes.append(
            f"<tr><td>{etat}</td><td>{identite}</td>"
            f"<td>{lignes_html(ev.periode.splitlines())}</td>"
            f"<td>{detour}</td><td>{arrets_html}</td>"
            f"<td>{escape(ev.effectif)}</td></tr>"
        )

    return """<style>
.evt-wrap{overflow-x:auto;width:100%;margin:.25rem 0 1rem;background:#fff;color:#1A1A2E;color-scheme:light}
.evt-table{border-collapse:collapse;width:100%;min-width:980px;font-size:.88rem;color:#1A1A2E}
.evt-table th{background:#0072ce;color:white;text-align:left;white-space:nowrap}
.evt-table th,.evt-table td{border:1px solid #ccc;padding:.45rem;vertical-align:top}
.evt-table td{color:#1A1A2E}
.evt-table tbody tr:nth-child(odd){background:#f7f7f7}
.evt-ok{color:#176b2c;font-weight:600}.evt-non{color:#666;font-weight:600}
.evt-raison{color:#8a5a00;font-size:.8rem;margin-top:.2rem}
</style><div class="evt-wrap"><table class="evt-table"><thead><tr>
<th>État</th><th>Événement / titre</th><th>Période</th>
<th>Détour &amp; commentaires</th><th>Arrêts</th><th>Effectif</th>
</tr></thead><tbody>""" + "".join(lignes) + "</tbody></table></div>"
