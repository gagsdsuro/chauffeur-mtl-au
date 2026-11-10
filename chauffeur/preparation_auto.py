"""Préparation semi-automatique d'une journée : enchaîne les étapes sans interface.

Étapes, dans l'ordre : journée → calendrier → carte agent → G-D → évènements →
rapport v2. La chaîne s'arrête sur une erreur **bloquante** (journée absente ou
invalide, session portail expirée, G-D requis toujours absents, rapport v2
impossible) ; les autres problèmes (calendrier, carte agent, évènements en
échec) sont des **avertissements** et la chaîne continue.

Le module ne dépend pas de Streamlit : le résultat (`ResultatSemiAuto`) est
sérialisable (`to_dict`/`from_dict`) pour reprendre après le renouvellement de
la session portail.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from .ca import annoter_et_ranger_ca, resoudre_ca
from .calendrier import dossier_calendrier, ecrire_calendrier_sans_echec, evenements_ics, lignes_calendrier
from .depots import charger_journee, chemin_journee, info_gd
from .journee import lignes_de_service
from .portail import PortailClient, PortailError, SessionExpiredError
from .preparation import (
    ResultatRafraichissement,
    finaliser_rapports,
    fusionner_rafraichissements,
    importer_journee_portail,
    rafraichir_evenements_journee,
    rafraichir_gd_journee,
)

ETAPES = ("journee", "calendrier", "carte_agent", "gauche_droite", "evenements", "rapport_v2")
LIBELLES = {
    "journee": "Importer la journée",
    "calendrier": "Générer le calendrier (.ics)",
    "carte_agent": "Importer et annoter la carte agent",
    "gauche_droite": "Importer les Gauche-Droite manquants ou périmés",
    "evenements": "Importer les évènements",
    "rapport_v2": "Générer le rapport journalier v2",
}
# Un échec de ces étapes n'empêche pas les suivantes (avertissement).
NON_BLOQUANTES = frozenset({"calendrier", "carte_agent", "evenements"})

STATUTS_ARRET = ("bloque", "session_expiree")


@dataclass
class ResultatEtape:
    """statut : ok | ignore | avertissement | bloque | session_expiree."""

    etape: str
    statut: str
    message: str = ""
    details: list[str] = field(default_factory=list)
    restantes: list[tuple[str, str]] = field(default_factory=list)
    donnees: dict = field(default_factory=dict)


@dataclass
class ResultatSemiAuto:
    date: str
    etapes: list[ResultatEtape] = field(default_factory=list)
    reprise_a: str | None = None   # étape où la chaîne s'est arrêtée ; None = terminée

    @property
    def termine(self) -> bool:
        return self.reprise_a is None

    @property
    def session_expiree(self) -> bool:
        return any(e.statut == "session_expiree" for e in self.etapes)

    @property
    def bloque(self) -> bool:
        return any(e.statut == "bloque" for e in self.etapes)

    @property
    def avertissements(self) -> list[ResultatEtape]:
        return [e for e in self.etapes if e.statut == "avertissement"]

    def etape(self, nom: str) -> ResultatEtape | None:
        return next((e for e in self.etapes if e.etape == nom), None)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ResultatSemiAuto":
        return cls(
            date=data.get("date", ""),
            etapes=[
                ResultatEtape(
                    etape=e["etape"], statut=e["statut"], message=e.get("message", ""),
                    details=list(e.get("details", [])),
                    restantes=[tuple(r) for r in e.get("restantes", [])],
                    donnees=dict(e.get("donnees", {})),
                )
                for e in data.get("etapes", [])
            ],
            reprise_a=data.get("reprise_a"),
        )


def _premiere_ligne(texte: str) -> str:
    return next((ligne.strip() for ligne in (texte or "").splitlines() if ligne.strip()), "")


def executer_semi_auto(
    date_cible: date | str,
    *,
    precedent: ResultatSemiAuto | None = None,
    sans_portail: bool = False,
    client: PortailClient | None = None,
    rapports_dir: Path | None = None,
    niveau_v2: str = "standard",
    progression: Callable[[str, str, str], None] | None = None,
) -> ResultatSemiAuto:
    """Enchaîne les étapes de préparation de la journée `date_cible`.

    precedent    — résultat d'un passage interrompu : on reprend à `reprise_a` en
                   conservant les étapes déjà faites.
    sans_portail — poursuit sans le portail à l'étape évènements : les fichiers
                   présents sont utilisés et l'étape devient un avertissement.
    progression  — rappel `(étape, statut, message)` ; statut « demarre » au début
                   de chaque étape.
    """
    date_str = date_cible.isoformat() if isinstance(date_cible, date) else str(date_cible)
    jour = date.fromisoformat(date_str)
    chemin = chemin_journee(date_str)

    resultat = ResultatSemiAuto(date_str)
    debut = ETAPES[0]
    anterieurs: dict[str, ResultatEtape] = {}
    if precedent and precedent.date == date_str and precedent.reprise_a in ETAPES:
        anterieurs = {e.etape: e for e in precedent.etapes}
        debut = precedent.reprise_a
        if debut != "journee" and not chemin.exists():
            debut = "journee"
        resultat.etapes = [e for e in precedent.etapes if ETAPES.index(e.etape) < ETAPES.index(debut)]

    ctx: dict = {"calendrier": []}

    def client_portail() -> PortailClient:
        nonlocal client
        if client is None:
            client = PortailClient()
        return client

    def expire(message: str = "Session portail expirée — renouvellement requis.", **kw) -> ResultatEtape:
        return ResultatEtape(ctx["etape"], "session_expiree", message, **kw)

    def journee() -> dict:
        if "journee" not in ctx:
            ctx["journee"] = charger_journee(chemin)
        return ctx["journee"]

    def paires() -> list[tuple[str, str]]:
        return lignes_de_service(journee())

    # ── étapes ────────────────────────────────────────────────────────────────
    def etape_journee() -> ResultatEtape:
        try:
            c = client_portail()
        except (FileNotFoundError, SessionExpiredError):
            return expire()
        res = importer_journee_portail(date_str, client=c)
        if res.session_expiree:
            return expire()
        if not res.succes:
            return ResultatEtape(
                "journee", "bloque", _premiere_ligne(res.message) or "Échec de l'import de la journée.",
                details=(res.message or "").splitlines()[1:],
            )
        ctx["calendrier"] = list(res.calendrier)
        ctx.pop("journee", None)   # recharger depuis le fichier écrit
        return ResultatEtape(
            "journee", "ok", f"Journée du {date_str} " + ("importée." if res.modifie else "à jour (inchangée)."),
        )

    def etape_calendrier() -> ResultatEtape:
        j = journee()
        if not evenements_ics(j):
            return ResultatEtape("calendrier", "ignore", "Aucune pièce de travail avec heures.")
        chemins, erreur = list(ctx["calendrier"]), ""
        if not chemins:   # rattrapage : l'écriture à l'import a échoué ou n'a pas eu lieu
            chemins, erreur = ecrire_calendrier_sans_echec(j, dossier_calendrier(chemin))
        details = lignes_calendrier(chemins, erreur)
        if erreur or not chemins:
            return ResultatEtape("calendrier", "avertissement", "Calendrier non généré.", details=details)
        return ResultatEtape("calendrier", "ok", f"{len(chemins)} fichier(s) .ics.", details=details)

    def etape_carte_agent() -> ResultatEtape:
        j = journee()
        if not evenements_ics(j) and not paires():
            return ResultatEtape("carte_agent", "ignore", "Aucune pièce de travail.")
        numero = j.get("journee_numero")
        info = resoudre_ca(jour, numero)
        if info.get("annotee"):
            return ResultatEtape("carte_agent", "ignore", "Carte agent déjà présente (réutilisée).")
        try:
            pdf = client_portail().fetch_carte_agent(date_str)
        except (FileNotFoundError, SessionExpiredError):
            return expire()
        except PortailError as exc:
            return ResultatEtape("carte_agent", "avertissement", str(exc))
        res = annoter_et_ranger_ca(
            pdf, jour, nom_source=f"carte-agent-{date_str}.pdf", journee_numero=numero,
            remplacer=bool(info.get("brute")),
        )
        details = list(res.avertissements) + ([res.detail] if res.detail else [])
        if res.succes:
            return ResultatEtape("carte_agent", "ok", res.message, details=details)
        return ResultatEtape("carte_agent", "avertissement", res.message, details=details)

    def etape_gauche_droite() -> ResultatEtape:
        liste = paires()
        if not liste:
            return ResultatEtape("gauche_droite", "ignore", "Aucune ligne de service.")
        a_jour = lambda l, d: info_gd(l, d)["fresh"]  # noqa: E731
        if all(a_jour(l, d) for l, d in liste):
            return ResultatEtape("gauche_droite", "ignore", "Tous les G-D sont présents et à jour.")
        try:
            c = client_portail()
        except (FileNotFoundError, SessionExpiredError):
            return expire()
        res = rafraichir_gd_journee(journee(), client=c)
        details = [
            f"{'✅' if l.succes else '❌'} {l.ligne} {l.direction}"
            + (f" — {_premiere_ligne(l.message)}" if not l.succes else "")
            for l in res.lignes
        ]
        if res.session_expiree:
            return expire(details=details)
        manquants = [f"{l} {d}" for l, d in liste if not info_gd(l, d)["exists"]]
        if manquants:
            return ResultatEtape(
                "gauche_droite", "bloque", "G-D manquants : " + ", ".join(manquants), details=details,
            )
        if not res.succes_complet or not all(a_jour(l, d) for l, d in liste):
            return ResultatEtape(
                "gauche_droite", "avertissement", "Certains G-D n'ont pas pu être rafraîchis.",
                details=details,
            )
        return ResultatEtape("gauche_droite", "ok", f"{len(res.lignes)} G-D récupéré(s).", details=details)

    def etape_evenements() -> ResultatEtape:
        liste = paires()
        if not liste:
            return ResultatEtape("evenements", "ignore", "Aucune ligne de service.")
        deja = anterieurs.get("evenements")
        if sans_portail:
            return ResultatEtape(
                "evenements", "avertissement",
                "Session non renouvelée — évènements déjà présents utilisés.",
                details=deja.details if deja else [],
            )
        precedent_res = (
            ResultatRafraichissement.from_dict(deja.donnees["resultat"])
            if deja and deja.donnees.get("resultat") else None
        )
        try:
            c = client_portail()
        except (FileNotFoundError, SessionExpiredError):
            return expire()
        nouveau = rafraichir_evenements_journee(
            journee(), paires=precedent_res.restantes if precedent_res else None, client=c,
        )
        total = fusionner_rafraichissements(precedent_res, nouveau)
        details = [
            f"{'✅' if l.succes else '❌'} {l.ligne} {l.direction}"
            + (" — modifié" if l.modifie else "")
            + ("" if l.succes else f" — {_premiere_ligne(l.message)}")
            for l in total.lignes
        ]
        donnees = {"resultat": total.to_dict()}
        if nouveau.session_expiree:
            return expire(details=details, restantes=list(total.restantes), donnees=donnees)
        if not total.succes_complet:
            return ResultatEtape(
                "evenements", "avertissement",
                "Récupération incomplète — évènements déjà présents utilisés.",
                details=details, donnees=donnees,
            )
        return ResultatEtape(
            "evenements", "ok", f"{len(total.lignes)} ligne(s) vérifiée(s)"
            + (" (évènements modifiés)." if total.modifie else "."),
            details=details, donnees=donnees,
        )

    def etape_rapport_v2() -> ResultatEtape:
        if not paires():
            return ResultatEtape("rapport_v2", "ignore", "Aucune ligne de service.")
        finals = finaliser_rapports(
            chemin, niveau_v2=niveau_v2, rapports_dir=rapports_dir, variantes=("v2",),
        )
        r = finals[0]
        if r.statut == "genere":
            return ResultatEtape("rapport_v2", "ok", f"Rapport v2 {niveau_v2} généré.")
        if r.statut == "ignore":
            return ResultatEtape("rapport_v2", "ignore", "Rapport v2 déjà à jour.")
        return ResultatEtape("rapport_v2", "bloque", _premiere_ligne(r.message) or "Rapport v2 non généré.")

    fonctions = {
        "journee": etape_journee, "calendrier": etape_calendrier,
        "carte_agent": etape_carte_agent, "gauche_droite": etape_gauche_droite,
        "evenements": etape_evenements, "rapport_v2": etape_rapport_v2,
    }

    for nom in ETAPES[ETAPES.index(debut):]:
        ctx["etape"] = nom
        if progression:
            progression(nom, "demarre", LIBELLES[nom])
        try:
            etape = fonctions[nom]()
        except Exception as exc:  # noqa: BLE001 — une étape ne doit jamais faire planter la page
            etape = ResultatEtape(
                nom, "avertissement" if nom in NON_BLOQUANTES else "bloque",
                f"{type(exc).__name__} : {exc}",
            )
        resultat.etapes.append(etape)
        if progression:
            progression(nom, etape.statut, etape.message)
        if etape.statut in STATUTS_ARRET:
            resultat.reprise_a = nom
            break
    return resultat
