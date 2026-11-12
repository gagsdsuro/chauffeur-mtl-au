"""chauffeur.registre_appariement — appariements G-D ↔ GTFS persistés (flotte).

Un fichier commun par parcours : `data/Appariements/<ligne>_<direction>_<id>.json`
(voir `depots.chemin_appariement`). Il ne stocke pas les lignes du rapport
mais la fonction monotone `seq → étape` (avec source auto|manuel et
confiance), les instructions G-D qu'elle référence et deux empreintes :

  • `empreinte_gd`   — terminus + séquence d'instructions du parcours ;
  • `empreinte_gtfs` — séquence ordonnée des stop_id.

Statuts :
  auto         calcul automatique sans incertitude ;
  incertain    calcul automatique avec des blocs à réviser ;
  valide       révisé et validé par un chauffeur (`valide_par`, `valide_le`) ;
  a_revalider  une source a changé depuis un choix humain : les choix encore
               applicables ont été reportés, un humain doit reconfirmer.

Écritures : atomiques, `.bak` du précédent, verrou de processus et contrôle
de version optimiste (`version` attendue) — le fichier est modifiable par
tous les chauffeurs. Journal commun : `data/log/appariement.log`.
"""
from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import appariement as algo
from . import depots
from .journal import ecrire_bloc

_verrou = threading.Lock()


class ConflitAppariement(RuntimeError):
    """Le fichier a été modifié par quelqu'un d'autre depuis sa lecture."""


def _maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ── Lecture / écriture ────────────────────────────────────────────────────────

def charger_appariement(ligne: str, direction: str, id_parcours,
                        appariements_dir: Path | None = None) -> dict | None:
    path = depots.chemin_appariement(ligne, direction, id_parcours, appariements_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sauvegarder_appariement(contenu: dict, version_attendue: int | None,
                            appariements_dir: Path | None = None) -> dict:
    """Écrit `contenu` si la version sur disque est encore `version_attendue`.

    `version_attendue=None` : création (refusée si un fichier existe déjà).
    Retourne le contenu écrit (version incrémentée). Lève ConflitAppariement.
    """
    path = depots.chemin_appariement(contenu["ligne"], contenu["direction"],
                                     contenu["id_parcours"], appariements_dir)
    with _verrou:
        actuel = charger_appariement(contenu["ligne"], contenu["direction"],
                                     contenu["id_parcours"], appariements_dir)
        version_disque = actuel.get("version") if actuel else None
        if version_disque != version_attendue:
            raise ConflitAppariement(
                f"{path.name} : version {version_disque} sur disque, "
                f"{version_attendue} attendue — recharger avant d'enregistrer")
        if path.exists():
            shutil.copy2(path, path.with_suffix(".json.bak"))
        contenu = dict(contenu, version=(version_disque or 0) + 1)
        depots._sauvegarder_json_atomique(path, contenu)
    return contenu


# ── Construction ──────────────────────────────────────────────────────────────

def _contenu(ligne, direction, parcours, stops, resultat, statut, base=None) -> dict:
    base = base or {}
    return {
        "ligne": str(ligne).lower(),
        "direction": direction.lower(),
        "id_parcours": parcours.get("id"),
        "parcours_nom": parcours.get("name", ""),
        "statut": statut,
        "version": base.get("version"),
        "version_algo": algo.VERSION_ALGO,
        "empreinte_gd": algo.empreinte_gd(parcours),
        "empreinte_gtfs": algo.empreinte_gtfs(stops),
        "genere_le": _maintenant(),
        "valide_par": base.get("valide_par") if statut == "valide" else None,
        "valide_le": base.get("valide_le") if statut == "valide" else None,
        "instructions": list(parcours.get("direction", [])),
        "arrets": resultat["arrets"],
        "incertitudes": resultat["incertitudes"],
        "blocs": resultat["blocs"],
    }


def _a_des_choix_humains(contenu: dict) -> bool:
    return contenu.get("statut") in ("valide", "a_revalider") or any(
        a.get("source") == "manuel" for a in contenu.get("arrets", []))


def est_a_jour(contenu: dict, parcours: dict, stops: list) -> bool:
    """Les deux empreintes correspondent encore aux sources."""
    return (contenu.get("empreinte_gd") == algo.empreinte_gd(parcours)
            and contenu.get("empreinte_gtfs") == algo.empreinte_gtfs(stops))


def calculer(ligne: str, direction: str, parcours: dict, stops: list, noms: dict,
             existant: dict | None = None) -> tuple[dict, str]:
    """Appariement à jour pour ces sources, sans écrire. Retourne (contenu, action).

    action : « inchange » (l'existant reste valable), « cree », « recalcule »
    (automatique, aucun choix humain à préserver) ou « a_revalider » (choix
    humains reportés sur les nouvelles sources).
    """
    instructions = parcours.get("direction", [])
    if existant and est_a_jour(existant, parcours, stops):
        humain = _a_des_choix_humains(existant)
        if humain or existant.get("version_algo") == algo.VERSION_ALGO:
            return existant, "inchange"

    if existant and _a_des_choix_humains(existant):
        ancres, abandonnes = algo.reporter_ancres(existant, instructions, stops)
        resultat = algo.apparier(instructions, stops, noms, ancres=ancres)
        contenu = _contenu(ligne, direction, parcours, stops, resultat, "a_revalider", existant)
        contenu["choix_abandonnes"] = abandonnes
        return contenu, "a_revalider"

    resultat = algo.apparier(instructions, stops, noms)
    statut = "incertain" if resultat["blocs"] else "auto"
    return (_contenu(ligne, direction, parcours, stops, resultat, statut, existant),
            "recalcule" if existant else "cree")


def synchroniser_parcours(ligne: str, direction: str, parcours: dict, stops: list,
                          noms: dict, appariements_dir: Path | None = None,
                          heritage: dict | None = None) -> tuple[dict, str]:
    """Calcule et persiste l'appariement si les sources ont changé.

    `heritage` : appariement révisé d'un parcours disparu du G-D (même
    empreinte G-D — parcours renuméroté par le transporteur). S'il n'existe encore
    aucun appariement pour ce parcours, ses choix humains sont reportés et le
    résultat passe « à revalider » (action « herite ») au lieu de repartir de zéro.
    """
    existant = charger_appariement(ligne, direction, parcours.get("id"), appariements_dir)
    if existant is None and heritage is not None:
        instructions = parcours.get("direction", [])
        ancres, abandonnes = algo.reporter_ancres(heritage, instructions, stops)
        resultat = algo.apparier(instructions, stops, noms, ancres=ancres)
        contenu = _contenu(ligne, direction, parcours, stops, resultat, "a_revalider")
        contenu.update(herite_de=heritage.get("id_parcours"), choix_abandonnes=abandonnes)
        return sauvegarder_appariement(contenu, None, appariements_dir), "herite"
    contenu, action = calculer(ligne, direction, parcours, stops, noms, existant)
    if action != "inchange":
        contenu = sauvegarder_appariement(
            contenu, existant.get("version") if existant else None, appariements_dir)
    return contenu, action


def valider_appariement(ligne: str, direction: str, parcours: dict, stops: list,
                        noms: dict, ancres: dict, par: str, version_attendue: int | None,
                        appariements_dir: Path | None = None) -> dict:
    """Enregistre la révision humaine de tout le parcours.

    `ancres` ({seq: etape}) porte les arrêts fixés par l'humain (source
    « manuel ») ; les autres sont recalculés autour puis acceptés tels quels
    (source « confirme ») — c'est l'ensemble que le chauffeur a sous les yeux
    au moment de valider. Si une source change plus tard, seuls les choix
    « manuel » sont reportés : le reste est recalculé puis reconfirmé.
    Lève ValueError si un arrêt de `stops` est absent de `noms` (versions
    GTFS mélangées) et ConflitAppariement si le fichier a changé entre-temps.
    """
    inconnus = [sid for _, sid in stops if sid not in noms]
    if inconnus:
        # Séquence et noms d'arrêts de deux versions GTFS différentes : ne
        # jamais figer comme « validé » un parcours qui cite des arrêts disparus.
        raise ValueError(f"arrêt(s) absent(s) du GTFS courant : {', '.join(inconnus)} — "
                         "séquence GTFS périmée, recharger la page")
    ancres = {int(k): int(v) for k, v in ancres.items()}
    resultat = algo.apparier(parcours.get("direction", []), stops, noms, ancres=ancres)
    for a in resultat["arrets"]:
        a["source"] = "manuel" if a["seq"] in ancres else "confirme"
        a["confiance"] = 1.0
    resultat["incertitudes"], resultat["blocs"] = [], []
    base = {"version": version_attendue, "valide_par": par, "valide_le": _maintenant()}
    contenu = _contenu(ligne, direction, parcours, stops, resultat, "valide", base)
    contenu = sauvegarder_appariement(contenu, version_attendue, appariements_dir)
    ecrire_bloc("appariement",
                f"{ligne} {direction} id {parcours.get('id')} — validé par {par} "
                f"(version {contenu['version']}, {len(ancres)} arrêt(s) déplacé(s))")
    return contenu


def ancres_courantes(contenu: dict | None) -> dict:
    """{seq: etape} des choix humains explicites d'un appariement."""
    return {a["seq"]: a["etape"] for a in (contenu or {}).get("arrets", [])
            if a.get("source") == "manuel"}


def modifier_ancres(ancres: dict, changements: list, etapes: dict,
                    instructions: list, stops: list, noms: dict) -> dict:
    """Applique des gestes de révision et retourne les nouvelles ancres.

    changements : [(seq, etape, fixe)] — `etape` (int) déplace et fixe l'arrêt ;
    sinon `fixe` True le fige à son étape actuelle (`etapes[seq]`), False le
    rend à l'automatique. Lève ValueError si l'ordre du parcours serait rompu
    (un arrêt placé avant, dans le G-D, un arrêt qui le précède).
    """
    nouvelles = dict(ancres)
    for seq, etape, fixe in changements:
        if etape is not None:
            nouvelles[seq] = int(etape)
        elif fixe is True:
            nouvelles[seq] = etapes[seq]
        elif fixe is False:
            nouvelles.pop(seq, None)
    algo.apparier(instructions, stops, noms, ancres=nouvelles)   # valide l'ordre
    return nouvelles


def parcours_a_reviser(groupes: list, gd_dir: Path | None = None) -> list[str]:
    """Libellés « 460 est id 24 » des groupes d'une journée dont l'appariement
    enregistré est incertain ou à revalider. Un parcours sans appariement
    (GTFS qui ne connaît pas la ligne) n'est pas révisable : il n'est pas listé."""
    libelles = []
    for g in groupes:
        _, parcours = depots.charger_gd(g["ligne"], g["direction"], g.get("id_parcours"), gd_dir)
        if not parcours:
            continue
        pid = parcours.get("id")
        contenu = charger_appariement(g["ligne"], g["direction"], pid,
                                      depots.repertoire_appariements(gd_dir))
        if contenu and contenu.get("statut") in ("incertain", "a_revalider"):
            libelles.append(f"{g['ligne']} {g['direction']} id {pid}")
    return list(dict.fromkeys(libelles))


def lister_appariements(appariements_dir: Path | None = None) -> dict:
    """{(ligne, direction, id_parcours): contenu} de tous les appariements stockés."""
    resultat = {}
    for path in sorted((appariements_dir or depots.repertoire_appariements()).glob("*.json")):
        try:
            c = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        resultat[(c.get("ligne"), c.get("direction"), c.get("id_parcours"))] = c
    return resultat


# ── Usage par le rapport ──────────────────────────────────────────────────────

def appariement_pour_rapport(ligne: str, direction: str, parcours: dict, stops: list,
                             noms: dict, appariements_dir: Path | None = None) -> tuple[list, dict]:
    """(séquence de lignes non fusionnées de build_rows, info) — lecture seule, jamais bloquant.

    info = {"statut", "blocs", "a_jour"} : le rapport s'en sert pour avertir
    quand l'appariement est incertain, à revalider ou pas encore persisté.
    """
    instructions = parcours.get("direction", [])
    existant = charger_appariement(ligne, direction, parcours.get("id"), appariements_dir)
    contenu, action = calculer(ligne, direction, parcours, stops, noms, existant)
    rows = algo.rows_depuis_appariement(instructions, contenu, noms)
    return rows, {"statut": contenu["statut"], "blocs": len(contenu.get("blocs", [])),
                  "a_jour": action == "inchange"}


# ── Déclencheurs (import G-D, mise à jour GTFS) ──────────────────────────────

def _parcours_uniques(gd: dict) -> list:
    vus, uniques = set(), []
    for p in (gd.get("routes") or [{}])[0].get("parcours", []):
        if p.get("id") not in vus:
            vus.add(p.get("id"))
            uniques.append(p)
    return uniques


ORPHELINS = "orphelins"


def archiver_appariement(ligne: str, direction: str, id_parcours,
                         appariements_dir: Path | None = None) -> Path:
    """Déplace l'appariement d'un parcours retiré du G-D vers `orphelins/`.

    Jamais de suppression : un travail de révision reste récupérable. Une
    archive existante n'est pas écrasée (suffixe horodaté).
    """
    source = depots.chemin_appariement(ligne, direction, id_parcours, appariements_dir)
    dossier = source.parent / ORPHELINS
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / source.name
    if cible.exists():
        cible = dossier / f"{source.stem}-{datetime.now():%Y%m%d%H%M%S}.json"
    with _verrou:
        shutil.move(source, cible)
        bak = source.with_suffix(".json.bak")
        if bak.exists():
            shutil.move(bak, cible.with_suffix(".json.bak"))
    return cible


def lister_parcours_gd(gd_dir: Path | None = None) -> list[tuple[str, str, dict]]:
    """[(ligne, direction, parcours)] de tous les fichiers G-D (ids dédoublonnés)."""
    resultat = []
    for path in sorted((gd_dir or depots.GD_DIR).glob("gd*_*.json")):
        ligne, _, direction = path.stem.removeprefix("gd").partition("_")
        try:
            gd = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        resultat += [(ligne, direction, p) for p in _parcours_uniques(gd)]
    return resultat


def synchroniser_ligne(ligne: str, direction: str, gd_dir: Path | None = None,
                       gtfs_dir: Path | None = None, noms: dict | None = None,
                       log: bool = False) -> list[str]:
    """Met à jour les appariements de tous les parcours d'un fichier G-D.

    Non bloquant : toute erreur (GTFS absent, ligne inconnue) devient un
    message. Retourne les messages lisibles (un par parcours touché).
    """
    from .gtfs import stop_names, stops_for_parcours

    gtfs_dir = Path(gtfs_dir or depots.GTFS_DIR)
    appariements_dir = depots.repertoire_appariements(gd_dir)
    path = depots.chemin_gd(ligne, direction, gd_dir)
    messages = []
    try:
        gd = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"⚠ Appariement {ligne} {direction} : G-D illisible ({exc})"]
    if not (gtfs_dir / "stops.txt").exists():
        return [f"⚠ Appariement {ligne} {direction} : GTFS absent, non calculé"]
    try:
        noms = noms if noms is not None else stop_names(gtfs_dir)
    except OSError as exc:
        return [f"⚠ Appariement {ligne} {direction} : GTFS illisible ({exc})"]

    uniques = _parcours_uniques(gd)
    ids = {p.get("id") for p in uniques}
    orphelins = {pid: c for (l, d, pid), c in lister_appariements(appariements_dir).items()
                 if l == str(ligne).lower() and d == direction.lower() and pid not in ids}

    for parcours in uniques:
        pid = parcours.get("id")
        empreinte = algo.empreinte_gd(parcours)
        heritage = next((c for c in orphelins.values()
                         if c.get("empreinte_gd") == empreinte and _a_des_choix_humains(c)), None)
        try:
            stops = stops_for_parcours(gtfs_dir, ligne, direction, pid)
            contenu, action = synchroniser_parcours(ligne, direction, parcours, stops,
                                                    noms, appariements_dir, heritage)
        except Exception as exc:  # noqa: BLE001 — jamais bloquant pour l'import
            messages.append(f"⚠ Appariement {ligne} {direction} id {pid} : {exc}")
            continue
        if action == "inchange":
            continue
        blocs = len(contenu.get("blocs", []))
        detail = {
            "cree": "créé", "recalcule": "recalculé",
            "a_revalider": "à revalider (source modifiée depuis la validation)",
            "herite": f"repris de l'id {contenu.get('herite_de')} (parcours renuméroté), "
                      "à revalider",
        }[action]
        suite = f", {blocs} segment(s) à réviser" if blocs else ""
        alerte = blocs or action in ("a_revalider", "herite")
        messages.append(f"{'⚠' if alerte else '✅'} "
                        f"Appariement {ligne} {direction} id {pid} : {detail}{suite}")

    for pid in orphelins:
        try:
            archiver_appariement(ligne, direction, pid, appariements_dir)
        except OSError as exc:
            messages.append(f"⚠ Appariement {ligne} {direction} id {pid} : archivage impossible ({exc})")
            continue
        messages.append(f"🗃 Appariement {ligne} {direction} id {pid} : parcours retiré du G-D, "
                        f"archivé dans {ORPHELINS}/")
    if log and messages:
        ecrire_bloc("appariement", "\n".join(messages))
    return messages


def synchroniser_tout(gd_dir: Path | None = None, gtfs_dir: Path | None = None,
                      log: bool = False) -> list[str]:
    """Après une mise à jour GTFS : revérifie tous les fichiers G-D."""
    from .gtfs import stop_names

    gtfs_dir = Path(gtfs_dir or depots.GTFS_DIR)
    if not (gtfs_dir / "stops.txt").exists():
        return ["⚠ Appariements : GTFS absent, non calculés"]
    noms = stop_names(gtfs_dir)
    messages = []
    for ligne, direction in sorted({(l, d) for l, d, _ in lister_parcours_gd(gd_dir)}):
        messages += synchroniser_ligne(ligne, direction, gd_dir, gtfs_dir, noms=noms)
    if log and messages:
        ecrire_bloc("appariement", "\n".join(messages))
    return messages
