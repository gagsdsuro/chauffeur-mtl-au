"""chauffeur.depots — dépôts de données locaux (data/) : chemins et chargement.

Source unique des conventions de nommage des fichiers de données
(gd<ligne>_<direction>.json, <ligne>_<direction>.json, journee-YYYY-MM-DD.json)
et de leur lecture, partagée entre les scripts et l'app Streamlit.

Chaque fonction accepte un répertoire optionnel (défaut = constante du module)
pour permettre des tests hermétiques sur des fichiers gelés.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .evenements import applicable_a_la_date
from .matricule import MATRICULE_MAX, MATRICULE_MIN, matricule_valide

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ── Isolation par matricule ───────────────────────────────────────────────────
# Deux familles de données :
#   • flotte (partagée par tous les chauffeurs) : G-D, événements, GTFS ;
#   • personnelles : journées, cartes agent, notes, rapports, logs, session
#     portail → `data/<matricule>/<dossier>` quand CHAUFFEUR_MATRICULE est
#     défini, sinon aux emplacements historiques data/<dossier> (legacy).
#
# Le matricule effectif est résolu à l'usage dans cet ordre :
#   1. contexte par thread (app Streamlit : matricule de la session, vu par
#      `definir_matricule_contexte` en tête de page) ;
#   2. environnement CHAUFFEUR_MATRICULE (CLI, Docker) ;
#   3. repli legacy (pas de matricule) — sauf en mode strict.
#
# Les constantes du module (JOURNEES_DIR, CA_DIR, …) restent figées à l'import
# à partir de l'environnement : elles servent au CLI et aux tests. Dans l'app,
# les pages passent par `repertoire_prive`/`bootstrap` (contexte de session).

_local_thread = threading.local()


def matricule_contexte() -> str | None:
    """Matricule de la session Streamlit en cours (thread), ou None."""
    return getattr(_local_thread, "matricule", None)


def definir_matricule_contexte(matricule: str | None) -> None:
    """Fixe le matricule de la session pour le thread courant (app).

    À appeler en tête de chaque page. `None` réactive le comportement
    legacy/environnement pour ce thread.
    """
    if matricule is not None and not matricule_valide(matricule):
        raise ValueError(
            f"Matricule invalide : {matricule!r}"
            f" (attendu : {MATRICULE_MIN}-{MATRICULE_MAX}, 5 chiffres)"
        )
    _local_thread.matricule = matricule


def effacer_matricule_contexte() -> None:
    """Réactive la résolution legacy/environnement pour ce thread."""
    definir_matricule_contexte(None)


@contextmanager
def contexte_matricule(matricule: str | None) -> Iterator[None]:
    """Bloc où le matricule courant du thread est `matricule` (tests)."""
    precedent = getattr(_local_thread, "matricule", None)
    definir_matricule_contexte(matricule)
    try:
        yield
    finally:
        definir_matricule_contexte(precedent)


def mode_strict() -> bool:
    """True si CHAUFFEUR_MATRICULE est rendu obligatoire (CHAUFFEUR_MODE_STRICT=1).

    Mode strict explicite (opt-in) : sans matricule (session ou env) et sans
    contexte, la résolution d'un répertoire privé lève ValueError au lieu de
    replier sur les emplacements legacy.
    """
    return os.environ.get("CHAUFFEUR_MODE_STRICT") == "1"


def matricule_courant() -> str | None:
    """Matricule de l'environnement CHAUFFEUR_MATRICULE (None si absent).

    Une variable définie mais invalide lève ValueError : refus explicite
    plutôt qu'un repli legacy silencieux qui isolerait mal les données.
    """
    valeur = os.environ.get("CHAUFFEUR_MATRICULE", "")
    if not valeur:
        return None
    if not matricule_valide(valeur):
        raise ValueError(
            f"CHAUFFEUR_MATRICULE invalide : {valeur!r}"
            f" (attendu : {MATRICULE_MIN}-{MATRICULE_MAX}, 5 chiffres)"
        )
    return valeur


def matricule_effectif() -> str | None:
    """Matricule courant dans l'ordre contexte-thread puis environnement.

    Aucun matricule en mode strict → ValueError : le repli legacy est refusé.
    """
    mat = matricule_contexte()
    if mat is None:
        mat = matricule_courant()
    if mat is None and mode_strict():
        raise ValueError(
            "CHAUFFEUR_MODE_STRICT=1 impose un matricule : "
            "connectez-vous dans l'app ou définissez CHAUFFEUR_MATRICULE."
        )
    return mat


def repertoire_prive_contexte(sous_dossier: str) -> Path | None:
    """Répertoire privé du matricule de session (thread), sinon None.

    Permet aux modules de domaine de résoudre le répertoire de la session en
    cours sans ignorer le repli legacy quand aucune session n'est active.
    """
    mat = matricule_contexte()
    if mat is None:
        return None
    return repertoire_prive(sous_dossier, mat)


def repertoire_utilisateur(matricule: str | None = None) -> Path:
    """data/<matricule> (isolation) ou data/ (legacy) selon le matricule.

    Sans matricule explicite, le matricule effectif (contexte puis env) est
    utilisé — le mode strict interdisant alors le repli legacy.
    """
    if matricule is None:
        matricule = matricule_effectif()
    if matricule is None:
        return DATA_DIR
    if not matricule_valide(matricule):
        raise ValueError(
            f"Matricule invalide : {matricule!r}"
            f" (attendu : {MATRICULE_MIN}-{MATRICULE_MAX}, 5 chiffres)"
        )
    return DATA_DIR / matricule


def repertoire_prive(sous_dossier: str, matricule: str | None = None) -> Path:
    """Répertoire privé `data/<matricule>/<sous_dossier>`, ou data/<dossier>."""
    if not sous_dossier or "/" in sous_dossier or "\\" in sous_dossier:
        raise ValueError(f"Sous-dossier invalide : {sous_dossier!r}")
    return repertoire_utilisateur(matricule) / sous_dossier


# ── Répertoires canoniques ────────────────────────────────────────────────────
# Constantes figées à l'import depuis l'environnement (CLI, tests et Docker) :
# env CHAUFFEUR_MATRICULE → data/<matricule>/<dossier>, sinon data/<dossier>.
# Elles n'appliquent PAS le mode strict (le strict est évalué à l'usage, par
# `repertoire_prive`), pour que l'app puisse ouvrir sa page de connexion.
# Dans l'app Streamlit, le matricule de session prime : passer par
# `repertoire_prive(...)` ou par bootstrap (accesseurs) plutôt que par ces
# constantes pour les répertoires privés.

def _repertoire_prive_defaut(sous_dossier: str) -> Path:
    """data/<dossier> ou data/<CHAUFFEUR_MATRICULE>/<dossier> (env à l'import)."""
    mat = matricule_courant()
    return (DATA_DIR / mat / sous_dossier) if mat else (DATA_DIR / sous_dossier)


GD_DIR       = DATA_DIR / "Gauche-Droite"     # partagé (flotte)
EVENTS_DIR   = DATA_DIR / "Events"            # partagé (flotte)
JOURNEES_DIR = _repertoire_prive_defaut("journees")   # privé
CA_DIR       = _repertoire_prive_defaut("ca")         # privé
NOTES_DIR    = _repertoire_prive_defaut("notes")      # privé
RAPPORTS_DIR = _repertoire_prive_defaut("rapports")   # privé
LOG_DIR      = _repertoire_prive_defaut("log")        # privé (personnel)
LOG_DIR_COMMUN = DATA_DIR / "log"                     # partagé (flotte) : imports G-D/Événements/GTFS
SESSION_DIR  = _repertoire_prive_defaut("session")    # privé
SESSION_PATH = SESSION_DIR / "cookies.json"   # privé
GTFS_DIR      = DATA_DIR / "gtfs" / "gtfs_stm"        # partagé (flotte)
GTFS_MANIFEST = DATA_DIR / "gtfs" / "gtfs_manifest.json"

# Seuils de fraîcheur (règles métier, partagés UI/scripts)
FRAICHEUR_GTFS_JOURS = 7    # GTFS statique : mise à jour hebdomadaire STM
FRAICHEUR_GD_JOURS   = 90   # fichiers Gauche-Droite : ré-import périodique


# ── Chemins canoniques ────────────────────────────────────────────────────────

def chemin_gd(ligne: str, direction: str, gd_dir: Path | None = None) -> Path:
    """gd<ligne>_<direction>.json (ligne et direction en minuscules)."""
    return (gd_dir or GD_DIR) / f"gd{str(ligne).lower()}_{(direction or '').lower()}.json"


def chemin_evenements(ligne: str, direction: str,
                      events_dir: Path | None = None) -> Path:
    """<ligne>_<direction>.json (sans préfixe, direction minuscule)."""
    return (events_dir or EVENTS_DIR) / f"{ligne}_{(direction or '').lower()}.json"


def repertoire_appariements(gd_dir: Path | None = None) -> Path:
    """Appariements G-D ↔ GTFS (flotte) : toujours à côté des G-D qu'ils décrivent.

    `data/Gauche-Droite/` → `data/Appariements/`. Un GD_DIR redirigé (tests)
    redirige donc aussi les appariements.
    """
    return (gd_dir or GD_DIR).parent / "Appariements"


def chemin_appariement(ligne: str, direction: str, id_parcours,
                       appariements_dir: Path | None = None) -> Path:
    """<ligne>_<direction>_<id>.json (ligne et direction en minuscules)."""
    return ((appariements_dir or repertoire_appariements())
            / f"{str(ligne).lower()}_{(direction or '').lower()}_{id_parcours}.json")


def repertoire_detours(gd_dir: Path | None = None) -> Path:
    """Appariements des détours (flotte) : `data/Appariements/detours/`."""
    return repertoire_appariements(gd_dir) / "detours"


def chemin_detours(ligne: str, direction: str, detours_dir: Path | None = None) -> Path:
    """<ligne>_<direction>.json : tous les détours appariés de cette ligne/direction."""
    return ((detours_dir or repertoire_detours())
            / f"{str(ligne).lower()}_{(direction or '').lower()}.json")


def chemin_journee(date_str: str, journees_dir: Path | None = None) -> Path:
    """journee-YYYY-MM-DD.json."""
    return (journees_dir or repertoire_prive("journees")) / f"journee-{date_str}.json"


# ── Chargement ────────────────────────────────────────────────────────────────

def charger_journee(path: Path) -> dict:
    """Charge un fichier journée JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sauvegarder_json_atomique(path: Path, contenu: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(contenu, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(tmp_name).unlink(missing_ok=True)
        raise


def sauvegarder_journee(path: Path, journee: dict) -> None:
    """Écrit atomiquement une journée JSON selon les conventions du dépôt."""
    _sauvegarder_json_atomique(path, journee)


def sauvegarder_gd(path: Path, gd: dict) -> None:
    """Écrit atomiquement un fichier G-D JSON selon les conventions du dépôt."""
    _sauvegarder_json_atomique(path, gd)


def lister_journees_fenetre(
    reference: date | None = None,
    jours_avant: int = 2,
    jours_apres: int = 5,
    journees_dir: Path | None = None,
) -> list[tuple[date, Path]]:
    """Journées existantes dans la fenêtre inclusive J-avant à J+après.

    Les entrées invalides sont ignorées et le résultat est chronologique.
    """
    reference = reference or date.today()
    debut = reference - timedelta(days=jours_avant)
    fin = reference + timedelta(days=jours_apres)
    resultats: list[tuple[date, Path]] = []
    for path in (journees_dir or repertoire_prive("journees")).glob("journee-*.json"):
        try:
            jour = date.fromisoformat(path.stem.removeprefix("journee-"))
        except ValueError:
            continue
        if debut <= jour <= fin:
            resultats.append((jour, path))
    return sorted(resultats)


def charger_gd(ligne: str, direction: str, id_parcours=None,
               gd_dir: Path | None = None) -> tuple[list, dict | None]:
    """Retourne (instructions, parcours) du fichier G-D, ou ([], None) si absent.

    Le parcours est sélectionné par son id ; repli sur le premier parcours si
    l'id est absent du fichier (ou None).
    """
    path = chemin_gd(ligne, direction, gd_dir)
    if not path.exists():
        return [], None
    data = json.loads(path.read_text(encoding="utf-8"))
    all_p = (data.get("routes") or [{}])[0].get("parcours", [])
    if not all_p:
        return [], None
    parcours = next((p for p in all_p if p.get("id") == id_parcours), all_p[0])
    return parcours.get("direction", []), parcours


def charger_evenements(ligne: str, direction: str,
                       events_dir: Path | None = None) -> list:
    """Liste brute des évènements (clé "detours") de la ligne/direction, [] si absent."""
    path = chemin_evenements(ligne, direction, events_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("detours", [])


def evenements_pour_date(ligne: str, direction: str, jour: date,
                         events_dir: Path | None = None) -> list:
    """Évènements de la ligne/direction valides à cette date (filtre date seulement)."""
    return [e for e in charger_evenements(ligne, direction, events_dir)
            if applicable_a_la_date(e, jour)]


# ── Fraîcheur des dépôts ──────────────────────────────────────────────────────

def _fmt_mtime(path: Path) -> str:
    """Date/heure de modification du fichier, ou '–' s'il n'existe pas."""
    if not path.exists():
        return "–"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _fmt_iso(value: str) -> str:
    """Horodatage ISO 8601 → 'YYYY-MM-DD HH:MM', ou la valeur brute si invalide."""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return value


def info_gd(ligne: str, direction: str,
            max_age_days: int = FRAICHEUR_GD_JOURS,
            gd_dir: Path | None = None) -> dict:
    """Info de fraîcheur d'un fichier Gauche-Droite.

    Les JSON G-D ne contiennent aucune date : la fraîcheur est basée sur le
    mtime du fichier. Un fichier ré-importé sans changement paraîtra « frais ».

    Champs retournés :
      exists    — True si le fichier existe (bool)
      path      — chemin du fichier (Path) ou None
      age_days  — âge en jours entiers (int) ou None si absent
      fresh     — True si présent et age_days <= max_age_days (bool)
    """
    path = chemin_gd(ligne, direction, gd_dir)
    if not path.exists():
        return {"exists": False, "path": None, "age_days": None, "fresh": False}
    age_days = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).days
    return {
        "exists":   True,
        "path":     path,
        "age_days": age_days,
        "fresh":    age_days <= max_age_days,
    }


def info_gtfs(data_dir: Path | None = None) -> dict:
    """Métadonnées de fraîcheur GTFS statique et temps réel.

    Champs retournés :
      static_ts       — date lisible du dernier téléchargement (str)
      static_age_days — âge en jours entiers (int) ou None si inconnu
      rt_ts           — date lisible du dernier RT (str)
      rt_pb           — chemin du fichier protobuf RT (Path)
      rt_avail        — True si le fichier RT existe (bool)
    """
    data_dir = data_dir or DATA_DIR
    static_manifest = data_dir / "gtfs" / "gtfs_manifest.json"
    rt_manifest     = data_dir / "gtfs_rt" / "gtfs_rt_manifest.json"
    rt_pb_path      = data_dir / "gtfs_rt" / "response_vehiclePositions.pb"

    static_ts       = "–"
    static_age_days = None
    if static_manifest.exists():
        try:
            m = json.loads(static_manifest.read_text(encoding="utf-8"))
            raw_date = m.get("last_update") or m.get("downloaded_at")
            if raw_date:
                static_ts = _fmt_iso(raw_date)
                try:
                    dt = datetime.fromisoformat(raw_date)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    static_age_days = (datetime.now(timezone.utc) - dt).days
                except Exception:
                    pass
            else:
                static_ts = _fmt_mtime(static_manifest)
        except Exception:
            static_ts = _fmt_mtime(static_manifest)

    rt_ts = "–"
    if rt_manifest.exists():
        try:
            m = json.loads(rt_manifest.read_text(encoding="utf-8"))
            rt_ts = _fmt_iso(m["last_update"]) if m.get("last_update") else _fmt_mtime(rt_manifest)
        except Exception:
            rt_ts = _fmt_mtime(rt_manifest)

    return {
        "static_ts":       static_ts,
        "static_age_days": static_age_days,
        "rt_ts":           rt_ts,
        "rt_pb":           rt_pb_path,
        "rt_avail":        rt_pb_path.exists(),
    }
