#!/usr/bin/env python3
"""
test_registre_appariement.py — Tests de chauffeur.registre_appariement

Hermétique : répertoire temporaire pour les appariements, les G-D et le
journal commun ; entrées G-D/GTFS reprises du cas figé 811-ouest-13.

Couvre : création et idempotence, validation (statut, auteur, .bak,
sources manuel/confirme),
contrôle de version optimiste (conflits), refus de valider une séquence
GTFS périmée (arrêt absent des noms), G-D modifié → « à revalider » avec
choix humains reportés, GTFS modifié lu par le rapport sans écriture,
recalcul sur changement de VERSION_ALGO, boucle (même stop_id deux fois),
gestes de révision (modifier_ancres), parcours renuméroté (choix repris)
puis retiré du G-D (archivé dans orphelins/),
déclencheur non bloquant sans GTFS.

Usage : python3 tests/test_registre_appariement.py   (code de sortie 0 si tout passe)
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur import appariement as algo  # noqa: E402
from chauffeur import journal  # noqa: E402
from chauffeur import registre_appariement as reg  # noqa: E402

CAS = ROOT / "tests" / "cas_appariement" / "811-ouest-13"
PARCOURS = json.loads((CAS / "parcours.json").read_text(encoding="utf-8"))
GTFS = json.loads((CAS / "gtfs_stops.json").read_text(encoding="utf-8"))
STOPS = [tuple(x) for x in GTFS["stops"]]
NOMS = GTFS["stop_names"]
L, D = "811", "ouest"


def verifier(erreurs: list, condition: bool, message: str) -> None:
    if not condition:
        erreurs.append(message)


def scenario(rep: Path) -> list:
    e = []
    app_dir = rep / "Appariements"

    # Création puis idempotence.
    c, action = reg.synchroniser_parcours(L, D, PARCOURS, STOPS, NOMS, app_dir)
    verifier(e, action == "cree" and c["statut"] == "auto" and c["version"] == 1,
             f"création : {action} {c['statut']} v{c['version']}")
    verifier(e, (app_dir / "811_ouest_13.json").exists(), "fichier 811_ouest_13.json absent")
    _, action = reg.synchroniser_parcours(L, D, PARCOURS, STOPS, NOMS, app_dir)
    verifier(e, action == "inchange", f"resynchronisation identique : {action}")

    # Validation humaine : seq 1 forcé sur l'étape 1 (au lieu de 0).
    c = reg.valider_appariement(L, D, PARCOURS, STOPS, NOMS, {1: 1}, "40001", 1, app_dir)
    verifier(e, c["statut"] == "valide" and c["valide_par"] == "40001" and c["version"] == 2,
             f"validation : {c['statut']} {c['valide_par']} v{c['version']}")
    verifier(e, c["arrets"][0]["etape"] == 1, "ancre {1: 1} non respectée")
    sources = [a["source"] for a in c["arrets"]]
    verifier(e, sources[0] == "manuel" and set(sources[1:]) == {"confirme"},
             f"sources après validation : {sources[:3]}… (fixé = manuel, reste = confirme)")
    verifier(e, reg.ancres_courantes(c) == {1: 1}, f"ancres courantes : {reg.ancres_courantes(c)}")
    verifier(e, (app_dir / "811_ouest_13.json.bak").exists(), ".bak absent")
    log = rep / "log" / "appariement.log"
    verifier(e, log.exists() and "40001" in log.read_text(encoding="utf-8"),
             "validation non journalisée dans le journal commun")

    # Conflits de version.
    for version, cas in ((1, "version périmée"), (None, "création sur fichier existant")):
        try:
            reg.valider_appariement(L, D, PARCOURS, STOPS, NOMS, {}, "99999", version, app_dir)
            e.append(f"conflit non détecté : {cas}")
        except reg.ConflitAppariement:
            pass

    # Séquence d'une ancienne version GTFS (arrêt disparu des noms) : refus.
    noms_sans = {k: v for k, v in NOMS.items() if k != "53039"}
    try:
        reg.valider_appariement(L, D, PARCOURS, STOPS, noms_sans, {}, "40001", 2, app_dir)
        e.append("validation acceptée avec un arrêt absent du GTFS courant")
    except ValueError:
        pass
    verifier(e, reg.charger_appariement(L, D, 13, app_dir)["version"] == 2,
             "validation refusée : rien ne doit être écrit")

    # Validé + réimport identique → inchangé (un validé n'est jamais recalculé).
    _, action = reg.synchroniser_parcours(L, D, PARCOURS, STOPS, NOMS, app_dir)
    verifier(e, action == "inchange", f"validé réimporté à l'identique : {action}")

    # Rapport : appariement validé et à jour → utilisé tel quel.
    rows, info = reg.appariement_pour_rapport(L, D, PARCOURS, STOPS, NOMS, app_dir)
    verifier(e, info == {"statut": "valide", "blocs": 0, "a_jour": True}, f"rapport : {info}")
    verifier(e, rows[1]["gd"] == PARCOURS["direction"][1] and rows[2]["stop_id"] == "62138",
             "rapport : ancre validée non reprise dans rows (arrêt après l'instruction 1)")

    # GTFS modifié (arrêt 53039 retiré) : le rapport recalcule sans écrire.
    stops_moins = [s for s in STOPS if s[1] != "53039"]
    _, info = reg.appariement_pour_rapport(L, D, PARCOURS, stops_moins, NOMS, app_dir)
    verifier(e, info["statut"] == "a_revalider" and not info["a_jour"], f"GTFS modifié : {info}")
    verifier(e, reg.charger_appariement(L, D, 13, app_dir)["version"] == 2,
             "le rapport ne doit jamais écrire")

    # G-D modifié (instruction insérée en tête) → à revalider, choix décalés.
    parcours2 = copy.deepcopy(PARCOURS)
    parcours2["direction"].insert(0, "Via - Joseph-Daoust")
    c, action = reg.synchroniser_parcours(L, D, parcours2, STOPS, NOMS, app_dir)
    verifier(e, action == "a_revalider" and c["statut"] == "a_revalider" and c["version"] == 3,
             f"G-D modifié : {action} {c['statut']} v{c['version']}")
    verifier(e, c["arrets"][0]["etape"] == 2 and c["arrets"][0]["source"] == "manuel",
             f"choix humain non reporté : seq 1 → étape {c['arrets'][0]['etape']}")
    verifier(e, c.get("choix_abandonnes") == 0, f"choix abandonnés : {c.get('choix_abandonnes')}")
    return e


def recalcul_version_algo(rep: Path) -> list:
    e = []
    app_dir = rep / "Appariements"
    reg.synchroniser_parcours(L, D, PARCOURS, STOPS, NOMS, app_dir)
    original = algo.VERSION_ALGO
    algo.VERSION_ALGO = original + 1
    try:
        _, action = reg.synchroniser_parcours(L, D, PARCOURS, STOPS, NOMS, app_dir)
    finally:
        algo.VERSION_ALGO = original
    verifier(e, action == "recalcule", f"changement de VERSION_ALGO : {action}")
    return e


def boucle() -> list:
    """62138 est le 1er et le dernier arrêt : le report distingue les occurrences."""
    ancien = {"instructions": PARCOURS["direction"],
              "arrets": [{"seq": s, "stop_id": sid, "etape": 0 if s == 1 else 16, "source": "manuel"}
                         for s, sid in (STOPS[0], STOPS[-1])]}
    ancres, abandonnes = algo.reporter_ancres(ancien, PARCOURS["direction"], STOPS)
    return [] if ancres == {1: 0, 24: 16} and abandonnes == 0 else [f"boucle : {ancres}, {abandonnes}"]


def gestes_revision() -> list:
    """modifier_ancres : déplacer, fixer, libérer, refuser un ordre impossible."""
    e = []
    instr = PARCOURS["direction"]
    etapes = {a["seq"]: a["etape"] for a in algo.apparier(instr, STOPS, NOMS)["arrets"]}
    a = reg.modifier_ancres({}, [(2, 3, None)], etapes, instr, STOPS, NOMS)
    verifier(e, a == {2: 3}, f"déplacer : {a}")
    a = reg.modifier_ancres(a, [(5, None, True)], etapes, instr, STOPS, NOMS)
    verifier(e, a == {2: 3, 5: etapes[5]}, f"fixer : {a}")
    a = reg.modifier_ancres(a, [(2, None, False)], etapes, instr, STOPS, NOMS)
    verifier(e, a == {5: etapes[5]}, f"libérer : {a}")
    try:
        reg.modifier_ancres(a, [(4, 14, None)], etapes, instr, STOPS, NOMS)
        e.append("ordre impossible accepté (seq 4 après seq 5 fixé)")
    except ValueError:
        pass
    return e


def _gtfs_minimal(dossier: Path) -> Path:
    """GTFS réduit au cas 811 ouest : juste ce que lisent stops_for_parcours/stop_names."""
    dossier.mkdir(parents=True)
    lignes = ["stop_id,stop_code,stop_name"] + [
        f'{sid},{v["code"]},"{v["name"]}"' for sid, v in NOMS.items()]
    (dossier / "stops.txt").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    (dossier / "routes.txt").write_text("route_id,route_short_name\n811,811\n", encoding="utf-8")
    (dossier / "trips.txt").write_text(
        "route_id,direction_id,trip_headsign,trip_id,shape_id\n811,1,Ouest,t1,811_13\n",
        encoding="utf-8")
    (dossier / "stops_index.json").write_text(
        json.dumps({"811|1": [list(s) for s in STOPS]}), encoding="utf-8")
    return dossier


def renumerotation(rep: Path) -> list:
    """Parcours renuméroté (22 est : id 1 → 9) puis retiré : rien ne se perd."""
    e = []
    gd_dir, gtfs_dir = rep / "Gauche-Droite", _gtfs_minimal(rep / "gtfs")
    app_dir = rep / "Appariements"
    gd_dir.mkdir()

    def ecrire_gd(*parcours):
        (gd_dir / "gd811_ouest.json").write_text(json.dumps(
            {"ligne": L, "direction": D, "routes": [{"parcours": list(parcours)}]}), encoding="utf-8")

    ecrire_gd(PARCOURS)
    reg.synchroniser_ligne(L, D, gd_dir=gd_dir, gtfs_dir=gtfs_dir)
    reg.valider_appariement(L, D, PARCOURS, STOPS, NOMS, {1: 1}, "40001", 1, app_dir)

    ecrire_gd(dict(PARCOURS, id=20))                         # même contenu, nouvel id
    messages = reg.synchroniser_ligne(L, D, gd_dir=gd_dir, gtfs_dir=gtfs_dir)
    nouveau = reg.charger_appariement(L, D, 20, app_dir)
    verifier(e, nouveau is not None and nouveau["statut"] == "a_revalider"
             and nouveau.get("herite_de") == 13, f"renumérotation : {nouveau and nouveau['statut']}")
    verifier(e, reg.ancres_courantes(nouveau) == {1: 1},
             f"choix humain non repris : {reg.ancres_courantes(nouveau)}")
    verifier(e, any("repris de l'id 13" in m for m in messages), f"message de reprise : {messages}")
    verifier(e, not (app_dir / "811_ouest_13.json").exists()
             and (app_dir / "orphelins" / "811_ouest_13.json").exists()
             and (app_dir / "orphelins" / "811_ouest_13.json.bak").exists(),
             "l'ancien appariement (et son .bak) doit être archivé dans orphelins/")
    verifier(e, (L, D, 13) not in reg.lister_appariements(app_dir), "orphelin encore listé")

    autre = dict(PARCOURS, id=21, direction=PARCOURS["direction"][:-1])   # parcours différent
    ecrire_gd(autre)
    messages = reg.synchroniser_ligne(L, D, gd_dir=gd_dir, gtfs_dir=gtfs_dir)
    nouveau = reg.charger_appariement(L, D, 21, app_dir)
    verifier(e, nouveau is not None and nouveau.get("herite_de") is None,
             "empreinte G-D différente : pas de reprise")
    verifier(e, (app_dir / "orphelins" / "811_ouest_20.json").exists()
             and any("retiré du G-D" in m for m in messages), f"archivage id 20 : {messages}")
    return e


def sans_gtfs(rep: Path) -> list:
    gd_dir = rep / "Gauche-Droite"
    gd_dir.mkdir()
    (gd_dir / "gd811_ouest.json").write_text(json.dumps(
        {"ligne": L, "direction": D, "routes": [{"parcours": [PARCOURS]}]}), encoding="utf-8")
    messages = reg.synchroniser_ligne(L, D, gd_dir=gd_dir, gtfs_dir=rep / "gtfs-absent")
    ok = len(messages) == 1 and "GTFS absent" in messages[0]
    ok = ok and not (rep / "Appariements").exists()
    return [] if ok else [f"sans GTFS : {messages}"]


def main() -> int:
    original_log = journal.LOG_DIR_COMMUN
    echecs = 0
    try:
        for nom, test in (("scénario complet", scenario), ("VERSION_ALGO", recalcul_version_algo),
                          ("boucle", None), ("gestes de révision", None),
                          ("renumérotation et retrait", renumerotation),
                          ("sans GTFS", sans_gtfs)):
            with tempfile.TemporaryDirectory() as tmp:
                rep = Path(tmp)
                journal.LOG_DIR_COMMUN = rep / "log"
                if test is None:
                    erreurs = boucle() if nom == "boucle" else gestes_revision()
                else:
                    erreurs = test(rep)
            print(("✅" if not erreurs else "❌") + f" {nom}")
            for err in erreurs:
                print("   ", err)
            echecs += bool(erreurs)
    finally:
        journal.LOG_DIR_COMMUN = original_log
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
