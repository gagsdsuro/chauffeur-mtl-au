"""chauffeur.periodes — calendrier de référence (listes, variations, fériés)
et dérivation de l'identité d'une carte agent à partir d'une date.

Une carte agent (CA) n'est pas identifiée par sa seule date : le même numéro
peut désigner des cartes différentes selon la liste (période de 9-12 semaines
débutant un lundi) et le jour-type (semaine/samedi/dimanche/variation). Ce
module dérive cette identité à partir du calendrier de référence publié par
le transporteur (data/reference/periodes_<année>.json), sans dépendre du contenu
du PDF (qui ne porte aucun champ liste/jour-type).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

REFERENCE_DIR = Path(__file__).parent.parent / "data" / "reference"


def _lundi(d: date) -> date:
    return d - timedelta(days=d.weekday())


@lru_cache(maxsize=None)
def charger_periodes(annee: int) -> dict:
    """Charge data/reference/periodes_<année>.json."""
    path = REFERENCE_DIR / f"periodes_{annee}.json"
    ancien = REFERENCE_DIR / f"periodes_stm_{annee}.json"  # nom historique, lu en repli
    if not path.exists() and ancien.exists():
        path = ancien
    if not path.exists():
        raise FileNotFoundError(
            f"Calendrier de référence introuvable pour {annee} : {path}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _calendrier(annee: int) -> dict | None:
    """Calendrier de l'année, ou None s'il n'existe pas."""
    try:
        return charger_periodes(annee)
    except FileNotFoundError:
        return None


def jour_type_semaine(d: date) -> str:
    """« semaine » / « samedi » / « dimanche » selon le jour de la semaine seul
    (ne tient pas compte des fériés ni des variations — cf. identite_ca)."""
    wd = d.weekday()
    if wd == 5:
        return "samedi"
    if wd == 6:
        return "dimanche"
    return "semaine"


def identite_ca(d: date, numero: str) -> tuple[str, str, str]:
    """(numero, groupe_id, jour_type) pour une date donnée.

    Règles (confirmées avec l'utilisateur, cf. mémoire projet) :
      - Jour férié isolé (même dans une semaine de liste par ailleurs
        normale) : groupe_id = date ISO exacte du férié, jour_type=variation.
      - Semaine de variation (relâche, construction, Noël/jour de l'an) :
        groupe_id = « V<lundi ISO> » — une identité par semaine du bloc,
        même pour un bloc multi-semaines. jour_type=variation.
      - Semaine normale d'une liste active : groupe_id = « L<lundi ISO du
        début de liste> », jour_type = semaine/samedi/dimanche.
    """
    cal = charger_periodes(d.year)
    iso = d.isoformat()

    if iso in cal.get("feries", []):
        return numero, iso, "variation"

    lundi = _lundi(d).isoformat()
    # Une semaine (lundi → dimanche) relève du calendrier de l'année de son
    # lundi : le dimanche 2027-01-03 fait partie de la semaine « Jour de l'an »
    # déclarée dans le calendrier 2026. Absent, ce calendrier est ignoré.
    cals = [cal] if _lundi(d).year == d.year else [cal, _calendrier(_lundi(d).year)]
    cals = [c for c in cals if c]

    for c in cals:
        for bloc in c.get("variations", []):
            if bloc["debut"] == lundi:
                return numero, f"V{lundi}", "variation"

    listes = sorted((l for c in cals for l in c.get("listes", [])),
                    key=lambda l: l["debut"], reverse=True)
    for liste in listes:
        if lundi >= liste["debut"]:
            return numero, f"L{liste['debut']}", jour_type_semaine(d)

    raise ValueError(
        f"Aucune liste ne couvre la date {d} — calendrier {d.year} incomplet ?"
    )


def nom_ca(numero: str, groupe_id: str, jour_type: str, *, annotee: bool = False) -> str:
    """Nom de fichier PDF pour une identité de carte agent (brute ou annotée).

    Remplace le nommage par date (carte-agent-YYYY-MM-DD.pdf) : deux journées
    partageant la même identité (numéro + groupe_id + jour_type) partagent le
    même fichier, sans comparaison de contenu.
    """
    suffixe = "-annotee" if annotee else ""
    return f"{numero}_{groupe_id}_{jour_type}{suffixe}.pdf"


# Navigation des fichiers : intervalles de listes, indépendants de l'identité CA.


@dataclass(frozen=True)
class PeriodeListe:
    debut: date
    fin: date

    @property
    def cle(self) -> str:
        return self.debut.isoformat()

    @property
    def libelle(self) -> str:
        return f"{self.debut:%d/%m/%Y} – {self.fin:%d/%m/%Y}"


@lru_cache(maxsize=8)
def _calendriers_fichiers(signature: tuple) -> tuple:
    return tuple(json.loads(Path(nom).read_text(encoding="utf-8"))
                 for nom, _, _ in signature)


def calendriers_fichiers(reference_dir: Path | None = None) -> tuple:
    """Petit cache invalidé par ajout, suppression ou modification du calendrier."""
    dossier = reference_dir if reference_dir is not None else REFERENCE_DIR
    signature = tuple((str(p.resolve()), p.stat().st_mtime_ns, p.stat().st_size)
                      for p in sorted(dossier.glob("periodes_*.json")))
    return _calendriers_fichiers(signature)


def listes_fichiers(reference_dir: Path | None = None) -> list[PeriodeListe]:
    calendriers = calendriers_fichiers(reference_dir)
    annees = {int(c["annee"]) for c in calendriers}
    debuts = sorted({date.fromisoformat(l["debut"])
                     for c in calendriers for l in c.get("listes", [])})
    periodes = []
    for i, debut in enumerate(debuts):
        # Ne jamais traverser une année dont le calendrier est absent.
        derniere_annee = debut.year
        while derniere_annee + 1 in annees:
            derniere_annee += 1
        fin = date(derniere_annee, 12, 31)
        if i + 1 < len(debuts):
            fin = min(fin, debuts[i + 1] - timedelta(days=1))
        periodes.append(PeriodeListe(debut, fin))
    return periodes


def periode_pour_date(jour: date, reference_dir: Path | None = None) -> PeriodeListe | None:
    return next((p for p in listes_fichiers(reference_dir)
                 if p.debut <= jour <= p.fin), None)


def regime_pour_date(jour: date, reference_dir: Path | None = None) -> str:
    cal = next((c for c in calendriers_fichiers(reference_dir)
                if int(c["annee"]) == jour.year), None)
    if cal is None:
        return "indetermine"
    if jour.isoformat() in cal.get("feries", []):
        return "ferie"
    lundi = _lundi(jour)
    # La semaine relève du calendrier de l'année de son lundi (cf. identite_ca).
    cal_semaine = cal if lundi.year == jour.year else next(
        (c for c in calendriers_fichiers(reference_dir) if int(c["annee"]) == lundi.year), None)
    if cal_semaine and any(v["debut"] == lundi.isoformat()
                           for v in cal_semaine.get("variations", [])):
        return "variation"
    return "normal"
