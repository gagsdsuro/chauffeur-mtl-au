"""chauffeur.depots — dépôts de données locaux (data/) : chemins et chargement.

Source unique des conventions de nommage des fichiers de données
(gd<ligne>_<direction>.json, <ligne>_<direction>.json, journee-YYYY-MM-DD.json)
et de leur lecture, partagée entre les scripts et l'app Streamlit.

Chaque fonction accepte un répertoire optionnel (défaut = constante du module)
pour permettre des tests hermétiques sur des fichiers gelés.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .evenements import applicable_a_la_date

DATA_DIR     = Path(__file__).resolve().parent.parent / "data"
GD_DIR       = DATA_DIR / "Gauche-Droite"
EVENTS_DIR   = DATA_DIR / "Events"
JOURNEES_DIR = DATA_DIR / "journees"
CA_DIR       = DATA_DIR / "ca"

# Seuils de fraîcheur (règles métier, partagés UI/scripts)
FRAICHEUR_GTFS_JOURS = 7    # GTFS statique : mise à jour hebdomadaire STM
FRAICHEUR_GD_JOURS   = 90   # fichiers Gauche-Droite : ré-import périodique


# ── Chemins canoniques ────────────────────────────────────────────────────────

def chemin_gd(ligne: str, direction: str, gd_dir: Path | None = None) -> Path:
    """gd<ligne>_<direction>.json (direction minuscule)."""
    return (gd_dir or GD_DIR) / f"gd{ligne}_{(direction or '').lower()}.json"


def chemin_evenements(ligne: str, direction: str,
                      events_dir: Path | None = None) -> Path:
    """<ligne>_<direction>.json (sans préfixe, direction minuscule)."""
    return (events_dir or EVENTS_DIR) / f"{ligne}_{(direction or '').lower()}.json"


def chemin_journee(date_str: str, journees_dir: Path | None = None) -> Path:
    """journee-YYYY-MM-DD.json."""
    return (journees_dir or JOURNEES_DIR) / f"journee-{date_str}.json"


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
    for path in (journees_dir or JOURNEES_DIR).glob("journee-*.json"):
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
