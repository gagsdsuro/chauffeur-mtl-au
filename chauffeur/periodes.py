"""chauffeur.periodes — calendrier de référence STM (listes, variations, fériés)
et dérivation de l'identité d'une carte agent à partir d'une date.

Une carte agent (CA) n'est pas identifiée par sa seule date : le même numéro
peut désigner des cartes différentes selon la liste (période de 9-12 semaines
débutant un lundi) et le jour-type (semaine/samedi/dimanche/variation). Ce
module dérive cette identité à partir du calendrier de référence publié par
la STM (data/reference/periodes_stm_<année>.json), sans dépendre du contenu
du PDF (qui ne porte aucun champ liste/jour-type).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

REFERENCE_DIR = Path(__file__).parent.parent / "data" / "reference"


def _lundi(d: date) -> date:
    return d - timedelta(days=d.weekday())


@lru_cache(maxsize=None)
def charger_periodes(annee: int) -> dict:
    """Charge data/reference/periodes_stm_<année>.json."""
    path = REFERENCE_DIR / f"periodes_stm_{annee}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Calendrier de référence STM introuvable pour {annee} : {path}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


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

    for bloc in cal.get("variations", []):
        if bloc["debut"] == lundi:
            return numero, f"V{lundi}", "variation"

    listes = sorted(cal.get("listes", []), key=lambda l: l["debut"], reverse=True)
    for liste in listes:
        if lundi >= liste["debut"]:
            return numero, f"L{liste['debut']}", jour_type_semaine(d)

    raise ValueError(
        f"Aucune liste STM ne couvre la date {d} — calendrier {d.year} incomplet ?"
    )


def nom_ca(numero: str, groupe_id: str, jour_type: str, *, annotee: bool = False) -> str:
    """Nom de fichier PDF pour une identité de carte agent (brute ou annotée).

    Remplace le nommage par date (carte-agent-YYYY-MM-DD.pdf) : deux journées
    partageant la même identité (numéro + groupe_id + jour_type) partagent le
    même fichier, sans comparaison de contenu.
    """
    suffixe = "-annotee" if annotee else ""
    return f"{numero}_{groupe_id}_{jour_type}{suffixe}.pdf"
