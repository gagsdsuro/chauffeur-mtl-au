#!/usr/bin/env python3
"""
Télécharge les données GTFS temps réel STM (tripUpdates + vehiclePositions).

Endpoints:
  - /v2/tripUpdates      → Données de ponctualité et retards par voyage
  - /v2/vehiclePositions → Positions GPS des véhicules en service

Fréquence: toutes les 2h de 12h à 20h (géré par le planificateur Windows)
Rétention: aucune — les fichiers .pb sont écrasés à chaque exécution
Sortie:    data/gtfs_rt/response_tripUpdates.pb
           data/gtfs_rt/response_vehiclePositions.pb

Sécurité: la clé API est chargée via SecretsManager (jamais en clair dans le code)
"""

import sys
import json
from datetime import datetime
from pathlib import Path

import requests

# ── Chemins ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR   = PROJECT_ROOT / "data" / "gtfs_rt"

sys.path.insert(0, str(PROJECT_ROOT))
from chauffeur.journal import ecrire_ligne  # noqa: E402

# ── Endpoints GTFS-RT STM ──────────────────────────────────────────────────────
BASE_URL  = "https://api.stm.info/pub/od/gtfs-rt/ic/v2"
ENDPOINTS = {
    "tripUpdates":      f"{BASE_URL}/tripUpdates",
    "vehiclePositions": f"{BASE_URL}/vehiclePositions",
    # "alerts":           f"{BASE_URL}/alerts",  # Non disponible sur l'API STM
}


# ── Logging ────────────────────────────────────────────────────────────────────
def log(message: str, level: str = "INFO") -> None:
    print(ecrire_ligne("fetch_gtfs_rt", message, level))


# ── Chargement de la clé API ───────────────────────────────────────────────────
SECRETS_FILE = PROJECT_ROOT / "Installation" / "config" / "secrets.json"

def get_api_key() -> str:
    """
    Charge la clé API du portail développeurs temps réel.
    Priorité: Installation/config/secrets.json (stm_api_key_rt) → variable d'environnement STM_API_KEY_RT
    """
    import os
    # 1. Fichier secrets.json
    if SECRETS_FILE.exists():
        try:
            secrets = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            key = secrets.get("stm_api_key_rt", "").strip()
            if key:
                log(f"Clé API chargée depuis {SECRETS_FILE}")
                return key
        except Exception as e:
            log(f"Erreur lecture {SECRETS_FILE}: {e}", "WARNING")

    # 2. Variable d'environnement
    key = os.environ.get("STM_API_KEY_RT", "").strip()
    if key:
        log("Clé API chargée depuis variable d'environnement STM_API_KEY_RT")
        return key

    raise ValueError(
        "Clé API temps réel STM introuvable.\n"
        f"  Option 1 : remplir {SECRETS_FILE}  (clé: stm_api_key_rt)\n"
        "  Option 2 : définir la variable d'environnement STM_API_KEY_RT"
    )


# ── Téléchargement d'un endpoint ───────────────────────────────────────────────
def fetch_endpoint(name: str, url: str, api_key: str, timeout: int = 30) -> bytes:
    """
    Télécharge un flux GTFS-RT (protobuf) depuis l'API STM.
    Lève une exception en cas d'erreur HTTP ou réseau.
    """
    headers = {
        "accept":  "application/x-protobuf",
        "apiKey":  api_key,
    }
    log(f"[{name}] Requête → {url}")
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()

    size_kb = len(response.content) / 1024
    log(f"[{name}] Reçu {size_kb:.1f} KB (HTTP {response.status_code})")
    return response.content


# ── Sauvegarde ─────────────────────────────────────────────────────────────────
def save_pb(name: str, data: bytes) -> Path:
    """Écrase le fichier .pb existant (pas d'historique conservé)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"response_{name}.pb"
    output_file.write_bytes(data)
    log(f"[{name}] Sauvegardé → {output_file.name}")
    return output_file


# ── Manifest ───────────────────────────────────────────────────────────────────
def update_manifest(results: dict) -> None:
    """Met à jour le fichier manifest avec les métadonnées du dernier téléchargement."""
    manifest_file = OUTPUT_DIR / "gtfs_rt_manifest.json"
    manifest = {
        "last_update": datetime.now().isoformat(),
        "endpoints":   results,
    }
    manifest_file.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    log("Manifest mis à jour → gtfs_rt_manifest.json")


# ── Point d'entrée ─────────────────────────────────────────────────────────────
def main() -> bool:
    log("=" * 70)
    log("DÉBUT : Téléchargement GTFS temps réel STM")
    log("=" * 70)

    # Charger la clé API
    try:
        api_key = get_api_key()
        log("Clé API chargée avec succès")
    except Exception as e:
        log(f"Impossible de charger la clé API : {e}", "ERROR")
        log("=" * 70)
        return False

    # Télécharger et sauvegarder chaque endpoint
    results = {}
    success_count = 0

    for name, url in ENDPOINTS.items():
        try:
            data = fetch_endpoint(name, url, api_key)
            output_file = save_pb(name, data)
            results[name] = {
                "status":      "success",
                "size_bytes":  len(data),
                "file":        output_file.name,
                "timestamp":   datetime.now().isoformat(),
            }
            success_count += 1

        except requests.exceptions.HTTPError as e:
            log(f"[{name}] Erreur HTTP : {e}", "ERROR")
            results[name] = {"status": "http_error", "error": str(e)}

        except requests.exceptions.ConnectionError as e:
            log(f"[{name}] Erreur réseau : {e}", "ERROR")
            results[name] = {"status": "network_error", "error": str(e)}

        except requests.exceptions.Timeout:
            log(f"[{name}] Timeout dépassé", "ERROR")
            results[name] = {"status": "timeout"}

        except Exception as e:
            log(f"[{name}] Erreur inattendue : {e}", "ERROR")
            results[name] = {"status": "error", "error": str(e)}

    # Manifest
    try:
        update_manifest(results)
    except Exception as e:
        log(f"Erreur manifest : {e}", "WARNING")

    # Résumé
    total = len(ENDPOINTS)
    log("=" * 70)
    if success_count == total:
        log(f"SUCCÈS : {success_count}/{total} endpoints téléchargés")
    else:
        log(f"PARTIEL : {success_count}/{total} endpoints réussis", "WARNING")
    log("=" * 70)

    return success_count == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
