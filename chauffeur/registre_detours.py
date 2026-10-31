"""chauffeur.registre_detours — appariement des détours (évènements) persisté (flotte).

Un même détour revient de façon intermittente dans l'année sous un autre numéro
d'évènement, mais son ancrage dans le parcours reste le même. Le registre garde
donc les décisions humaines sous une **signature de détour** qui ignore le
numéro d'évènement, les dates, le motif et l'effectif :

    signature = hash(ligne, direction, description G-D normalisée,
                     arrêts annulés, arrêts ajoutés)

Un fichier commun par ligne/direction : `data/Appariements/detours/<ligne>_<direction>.json`
(voir `depots.chemin_detours`) :

    {"ligne", "direction", "version", "detours": {signature: entrée}}

Entrée : `statut`, `titre`, `description_gd`, `arrets_annules`, `arrets_ajoutes`,
`evenement_ids` (ceux qui l'ont portée), `parcours` (ids touchés),
`diagnostics` (ce que le pipeline n'a pas su décider seul), `choix` et
`valide_par`/`valide_le`. Statuts :

  incertain    le pipeline a produit des diagnostics : à réviser ;
  valide       un chauffeur a fixé l'ancrage/l'ordre (`choix`, voir chauffeur.gd) ;
               il est imposé au pipeline, qui ne le recalcule jamais ;
  a_revalider  un choix ne s'applique plus (G-D modifié) : le calcul automatique
               reprend, un humain doit reconfirmer ;
  auto         choix retiré, plus rien d'imposé (conservé comme trace).

Un détour que le pipeline place sans rien signaler n'est pas enregistré.
Écritures : atomiques, `.bak`, verrou et contrôle de version optimiste (même
mécanique que `registre_appariement`). Journal commun : `data/log/appariement.log`.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import unicodedata
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path

from . import depots
from .gd import (
    annotate_events, apply_gd_detours, cle_arret_ajoute, event_applicable_to_parcours,
    insert_added_stops_inline, message_diagnostic, parse_description_gd,
)
from .journal import ecrire_bloc
from .registre_appariement import (
    ConflitAppariement, _parcours_uniques, appariement_pour_rapport,
)

_verrou = threading.Lock()
ETAT_A_REVISER = ("incertain", "a_revalider")


def _maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ── Signature ─────────────────────────────────────────────────────────────────

def _texte_norm(texte) -> str:
    """Minuscules sans accents, ponctuation et espaces répétés écartés."""
    brut = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", brut.lower()).split())


def signature_detour(ligne: str, direction: str, evenement: dict) -> str:
    """Identité d'un détour, indépendante du numéro d'évènement et des dates.

    Deux évènements portant les mêmes arrêts et la même description G-D (R/R,
    R.R. et « route régulière » équivalents) ont la même signature ; l'ordre
    des arrêts n'y entre pas (c'est précisément ce qu'un humain peut corriger).
    """
    desc = evenement.get("description_gd") or ""
    instructions = parse_description_gd(desc)
    corps = [_texte_norm(i) for i in instructions] if instructions else [_texte_norm(desc)]
    annules = sorted(str(a.get("id", "")) for a in evenement.get("arrets_annules", []))
    ajoutes = sorted(
        cle_arret_ajoute({"id": "" if isinstance(a, str) else a.get("id", ""),
                          "name": a if isinstance(a, str) else a.get("nom", "")})
        for a in evenement.get("arrets_ajoutes", []))
    charge = json.dumps([str(ligne).lower(), direction.lower(), corps, annules, ajoutes],
                        ensure_ascii=True)
    return hashlib.sha1(charge.encode()).hexdigest()[:12]


# ── Lecture / écriture ────────────────────────────────────────────────────────

def charger_detours(ligne: str, direction: str, detours_dir: Path | None = None) -> dict | None:
    path = depots.chemin_detours(ligne, direction, detours_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sauvegarder_detours(contenu: dict, version_attendue: int | None,
                        detours_dir: Path | None = None) -> dict:
    """Écrit `contenu` si la version sur disque est encore `version_attendue`.

    `version_attendue=None` : création. Lève ConflitAppariement sinon.
    """
    path = depots.chemin_detours(contenu["ligne"], contenu["direction"], detours_dir)
    with _verrou:
        actuel = charger_detours(contenu["ligne"], contenu["direction"], detours_dir)
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


def _vide(ligne: str, direction: str) -> dict:
    return {"ligne": str(ligne).lower(), "direction": direction.lower(),
            "version": None, "detours": {}}


def lister_detours(detours_dir: Path | None = None) -> dict:
    """{(ligne, direction): contenu} de tous les fichiers de détours."""
    resultat = {}
    for path in sorted((detours_dir or depots.repertoire_detours()).glob("*.json")):
        try:
            c = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        resultat[(c.get("ligne"), c.get("direction"))] = c
    return resultat


# ── Choix humains ─────────────────────────────────────────────────────────────

def _verifier_ref(ref, nom: str) -> None:
    if not (isinstance(ref, dict) and ref.get("type") in ("instruction", "arret")
            and ref.get("cle") and int(ref.get("occurrence") or 0) >= 1):
        raise ValueError(f"{nom} invalide : {ref!r}")


def verifier_choix(choix: dict) -> dict:
    """Valide la forme d'un choix (voir chauffeur.gd) et le retourne normalisé."""
    choix = dict(choix or {})
    if choix.get("debut"):
        _verifier_ref(choix["debut"], "début du détour")
        if choix.get("fin"):
            _verifier_ref(choix["fin"], "fin du barrage")
    else:
        choix["debut"] = choix["fin"] = None
    ajoutes = choix.get("arrets_ajoutes")
    if ajoutes is not None:
        for i, a in enumerate(ajoutes):
            if not a.get("cle") or int(a.get("etape", -1)) < 0:
                raise ValueError(f"arrêt ajouté {i + 1} invalide : {a!r}")
        choix["arrets_ajoutes"] = [{"cle": a["cle"], "etape": int(a["etape"]),
                                    "avant": bool(a.get("avant"))} for a in ajoutes]
    if not (choix["debut"] or choix.get("arrets_ajoutes")):
        raise ValueError("choix vide : ni début de détour, ni arrêts ajoutés")
    return choix


def _entree(ligne: str, direction: str, evenement: dict) -> dict:
    return {
        "titre": evenement.get("titre", ""),
        "description_gd": evenement.get("description_gd") or "",
        "arrets_annules": sorted(str(a.get("id", "")) for a in evenement.get("arrets_annules", [])),
        "arrets_ajoutes": [{"id": "", "nom": a} if isinstance(a, str)
                           else {"id": str(a.get("id", "") or ""), "nom": a.get("nom", "")}
                           for a in evenement.get("arrets_ajoutes", [])],
        "arrets_annules_noms": {str(a.get("id", "")): a.get("nom", "")
                                for a in evenement.get("arrets_annules", [])},
        "evenement_ids": [evenement.get("evenement_id", "")],
        "parcours": [], "diagnostics": [], "choix": None,
        "valide_par": None, "valide_le": None,
    }


def evenement_depuis_entree(entree: dict) -> dict:
    """Évènement minimal reconstruit d'une entrée (l'original n'est plus dans les
    fichiers d'évènements) : de quoi rejouer le pipeline et retrouver sa signature."""
    noms = entree.get("arrets_annules_noms", {})
    return {"evenement_id": (entree.get("evenement_ids") or [""])[0],
            "titre": entree.get("titre", ""), "motif": "", "effectif": "",
            "description_gd": entree.get("description_gd", ""),
            "arrets_annules": [{"id": i, "nom": noms.get(i, "")}
                               for i in entree.get("arrets_annules", [])],
            "arrets_ajoutes": [dict(a) for a in entree.get("arrets_ajoutes", [])]}


def valider_detour(ligne: str, direction: str, evenement: dict, choix: dict, par: str,
                   version_attendue: int | None, detours_dir: Path | None = None) -> dict:
    """Enregistre le choix d'un chauffeur pour ce détour (statut « valide »).

    Lève ValueError si le choix est mal formé et ConflitAppariement si le
    fichier a changé depuis sa lecture. Retourne le contenu écrit.
    """
    choix = verifier_choix(choix)
    signature = signature_detour(ligne, direction, evenement)
    contenu = charger_detours(ligne, direction, detours_dir) or _vide(ligne, direction)
    entree = contenu["detours"].get(signature) or _entree(ligne, direction, evenement)
    ids = set(entree.get("evenement_ids", [])) | {evenement.get("evenement_id", "")}
    entree.update(statut="valide", choix=choix, valide_par=par, valide_le=_maintenant(),
                  evenement_ids=sorted(i for i in ids if i), diagnostics=[])
    contenu["detours"][signature] = entree
    contenu = sauvegarder_detours(contenu, version_attendue, detours_dir)
    ecrire_bloc("appariement",
                f"détour {ligne} {direction} {signature} (évènement "
                f"{evenement.get('evenement_id', '?')}) — validé par {par} "
                f"(version {contenu['version']})")
    return contenu


def retirer_choix(ligne: str, direction: str, signature: str, par: str,
                  version_attendue: int | None, detours_dir: Path | None = None) -> dict:
    """Retire le choix imposé : le détour redevient automatique (trace conservée)."""
    contenu = charger_detours(ligne, direction, detours_dir)
    if not contenu or signature not in contenu["detours"]:
        raise ValueError(f"détour {signature} inconnu")
    contenu["detours"][signature].update(statut="auto", choix=None,
                                         valide_par=None, valide_le=None)
    contenu = sauvegarder_detours(contenu, version_attendue, detours_dir)
    ecrire_bloc("appariement", f"détour {ligne} {direction} {signature} — choix retiré par {par}")
    return contenu


# ── Usage par le rapport ──────────────────────────────────────────────────────

def fournisseurs(ligne: str, direction: str, detours_dir: Path | None = None,
                 events_dir: Path | None = None):
    """(choix, choix_arrets) à passer à `apply_gd_detours`/`insert_added_stops_inline`.

    Seuls les détours « valide » sont imposés ; lecture seule. (None, None) s'il
    n'y en a aucun — le pipeline reste alors entièrement automatique. Les
    évènements du fichier `events_dir` rattachent un numéro d'évènement à sa
    signature : un détour qui revient sous un nouveau numéro retrouve son choix.
    """
    contenu = charger_detours(ligne, direction, detours_dir)
    entrees = {s: e["choix"] for s, e in (contenu or {}).get("detours", {}).items()
               if e.get("statut") == "valide" and e.get("choix")}
    if not entrees:
        return None, None

    ids: dict = {s: set(contenu["detours"][s].get("evenement_ids", [])) for s in entrees}
    for e in depots.charger_evenements(ligne, direction, events_dir):
        signe = signature_detour(ligne, direction, e)
        if signe in ids:
            ids[signe].add(e.get("evenement_id", ""))

    par_evenement: dict = {}   # (evenement_id, clé d'arrêt) -> {rang, etape, avant}
    for s, ch in entrees.items():
        for rang, a in enumerate(ch.get("arrets_ajoutes") or []):
            for ev_id in ids[s]:
                par_evenement[(ev_id, a["cle"])] = {"rang": rang, "etape": a["etape"],
                                                    "avant": a["avant"]}

    def choix(evenement):
        return entrees.get(signature_detour(ligne, direction, evenement))

    def choix_arrets(stop_info):
        return par_evenement.get((stop_info.get("evenement_id", ""), cle_arret_ajoute(stop_info)))

    return choix, choix_arrets


# ── Synchronisation (import d'évènements, G-D) ───────────────────────────────

def non_expire(evenement: dict, jour: date) -> bool:
    """L'évènement n'est pas terminé à cette date (début futur compris)."""
    try:
        fin = evenement.get("date_heure_fin")
        return not fin or datetime.fromisoformat(fin).date() >= jour
    except (ValueError, TypeError):
        return True


def synchroniser_evenements_ligne(ligne: str, direction: str, base: Path | None = None,
                                  noms: dict | None = None, jour: date | None = None,
                                  log: bool = False) -> list[str]:
    """Enregistre les détours à réviser d'une ligne/direction (non bloquant).

    `base` = répertoire `data/` (Events, Gauche-Droite, gtfs et Appariements en
    sont les voisins : un `base` redirigé garde les tests hermétiques). Pour chaque
    parcours du G-D et chaque évènement non expiré qui le touche, rejoue le
    pipeline avec diagnostics :
      • diagnostics → entrée « incertain » (créée ou mise à jour) ;
      • plus de diagnostics → l'entrée « incertain » disparaît ;
      • choix « valide » devenu inapplicable → « a_revalider » ;
      • les entrées « valide » et « a_revalider » ne sont jamais écrasées.
    Retourne les messages lisibles (un par entrée nouvelle ou modifiée).
    """
    from .gtfs import stop_names, stops_for_parcours

    base = Path(base or depots.DATA_DIR)
    events_dir, gd_dir, gtfs_dir = base / "Events", base / "Gauche-Droite", base / "gtfs" / "gtfs_stm"
    detours_dir = depots.repertoire_detours(gd_dir)
    appariements_dir = depots.repertoire_appariements(gd_dir)
    jour = jour or date.today()

    evenements = [e for e in depots.charger_evenements(ligne, direction, events_dir)
                  if non_expire(e, jour)]
    path_gd = depots.chemin_gd(ligne, direction, gd_dir)
    if not evenements or not path_gd.exists():
        return []
    if not (gtfs_dir / "stops.txt").exists():
        return [f"⚠ Détours {ligne} {direction} : GTFS absent, non vérifiés"]
    try:
        gd = json.loads(path_gd.read_text(encoding="utf-8"))
        noms = noms if noms is not None else stop_names(gtfs_dir)
    except (OSError, ValueError) as exc:
        return [f"⚠ Détours {ligne} {direction} : données illisibles ({exc})"]

    contenu = charger_detours(ligne, direction, detours_dir)
    version = contenu.get("version") if contenu else None
    contenu = contenu or _vide(ligne, direction)
    avant = deepcopy(contenu["detours"])
    choix, choix_arrets = fournisseurs(ligne, direction, detours_dir)

    constats: dict = {}   # signature -> {"evenement", "ids", "parcours", "diag", "inapplicable"}
    for parcours in _parcours_uniques(gd):
        instructions = parcours.get("direction", [])
        try:
            stops = stops_for_parcours(gtfs_dir, ligne, direction, parcours.get("id"))
            rows, _ = appariement_pour_rapport(ligne, direction, parcours, stops, noms,
                                               appariements_dir)
        except Exception:  # noqa: BLE001 — ligne inconnue du GTFS : rien à vérifier
            continue
        codes = {r.get("stop_code") or r["stop_id"] for r in rows if r.get("stop_id")}
        for e in evenements:
            if not event_applicable_to_parcours(e, codes, instructions):
                continue
            diag: list = []
            lignes, ajoutes, _ = annotate_events(deepcopy(rows), [e])
            lignes = apply_gd_detours(lignes, [e], diag, choix)
            insert_added_stops_inline(lignes, ajoutes, diag, choix_arrets)
            c = constats.setdefault(signature_detour(ligne, direction, e), {
                "evenement": e, "ids": set(), "parcours": set(), "diag": [], "inapplicable": False})
            c["ids"].add(e.get("evenement_id", ""))
            c["parcours"].add(parcours.get("id"))
            for d in diag:
                if d["type"] == "choix_inapplicable":
                    c["inapplicable"] = True
                else:
                    c["diag"].append(message_diagnostic(d))

    messages = []
    for signature, c in constats.items():
        existante = contenu["detours"].get(signature)
        diagnostics = list(dict.fromkeys(c["diag"]))
        base_entree = existante or _entree(ligne, direction, c["evenement"])
        ids = sorted(i for i in set(base_entree.get("evenement_ids", [])) | c["ids"] if i)
        statut = (existante or {}).get("statut")
        if statut == "valide" and c["inapplicable"]:
            statut = "a_revalider"
        elif statut in (None, "incertain", "auto") and diagnostics:
            statut = "incertain"
        elif statut in (None, "incertain", "auto"):
            contenu["detours"].pop(signature, None)    # rien à réviser (plus)
            continue
        base_entree.update(statut=statut, evenement_ids=ids,
                           parcours=sorted(p for p in c["parcours"] if p is not None),
                           diagnostics=diagnostics if statut == "incertain"
                           else base_entree.get("diagnostics", []))
        contenu["detours"][signature] = base_entree
    try:
        if contenu["detours"] != avant:
            sauvegarder_detours(contenu, version, detours_dir)
    except (ConflitAppariement, OSError) as exc:
        return [f"⚠ Détours {ligne} {direction} : non enregistrés ({exc})"]

    for signature, entree in contenu["detours"].items():
        if entree == avant.get(signature) or entree.get("statut") not in ETAT_A_REVISER:
            continue
        evt = ", ".join(entree.get("evenement_ids", [])[:3])
        detail = "à revalider (le choix ne s'applique plus au G-D)" \
            if entree["statut"] == "a_revalider" else "à réviser : " + " ; ".join(entree["diagnostics"][:2])
        messages.append(f"⚠ Détour {ligne} {direction} {signature} (évènement {evt}) : {detail}")
    if log and messages:
        ecrire_bloc("appariement", "\n".join(messages))
    return messages


def detours_a_reviser(groupes: list, jour: date, base: Path | None = None) -> list[str]:
    """Libellés « 445 est — évènement 11380915 » des détours à réviser touchant
    les groupes d'une journée (évènements actifs ce jour, entrée incertain ou à revalider)."""
    base = Path(base or depots.DATA_DIR)
    events_dir, gd_dir = base / "Events", base / "Gauche-Droite"
    detours_dir = depots.repertoire_detours(gd_dir)
    libelles = []
    for g in groupes:
        ligne, direction = g["ligne"], g["direction"]
        contenu = charger_detours(ligne, direction, detours_dir)
        if not contenu:
            continue
        for e in depots.evenements_pour_date(ligne, direction, jour, events_dir):
            entree = contenu["detours"].get(signature_detour(ligne, direction, e))
            if entree and entree.get("statut") in ETAT_A_REVISER:
                libelles.append(f"{ligne} {direction} — évènement {e.get('evenement_id', '?')}")
    return list(dict.fromkeys(libelles))


def synchroniser_tout_detours(base: Path | None = None, jour: date | None = None,
                              log: bool = False) -> list[str]:
    """Revérifie les détours de tous les fichiers d'évènements (après GTFS ou G-D)."""
    base = Path(base or depots.DATA_DIR)
    messages = []
    for path in sorted((base / "Events").glob("*_*.json")):
        ligne, _, direction = path.stem.partition("_")
        messages += synchroniser_evenements_ligne(ligne, direction, base=base, jour=jour)
    if log and messages:
        ecrire_bloc("appariement", "\n".join(messages))
    return messages
