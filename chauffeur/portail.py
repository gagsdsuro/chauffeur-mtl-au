"""Accès au portail employé STM (employe.stm.info).

Gestion de session semi-manuelle : l'utilisateur extrait ses cookies depuis
les DevTools du navigateur après login + 2FA, puis les stocke via save_session().
Les appels au endpoint détour réutilisent cette session jusqu'à expiration.

Dépendance : requests (déjà présente pour fetch_gtfs.py).
"""

import json
import re
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "https://employe.stm.info"
SESSION_PATH = Path(__file__).resolve().parent.parent / "data" / "session" / "cookies.json"

# Mapping direction interne (minuscule) → code URL portail
SENS_MAP = {"est": "E", "ouest": "W", "nord": "N", "sud": "S"}


class SessionExpiredError(Exception):
    """Session portail expirée ou absente — l'utilisateur doit renouveler ses cookies."""


class PortailError(Exception):
    """Erreur générique lors d'un appel au portail (réseau, format inattendu)."""


# ---------------------------------------------------------------------------
# Gestion de session
# ---------------------------------------------------------------------------

def _parse_cookie_string(cookie_str: str) -> dict:
    """Convertit une chaîne de cookies (format HTTP/DevTools) en dict."""
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            cookies[k.strip()] = v.strip()
    return cookies


def load_session(path: Path = SESSION_PATH) -> dict:
    """Charge la session depuis le fichier JSON.

    Raises:
        FileNotFoundError: Si aucune session n'a encore été enregistrée.
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_session(cookie_string: str, path: Path = SESSION_PATH) -> None:
    """Sauvegarde les cookies (chaîne brute copiée depuis les DevTools) dans le fichier de session.

    Le fichier est créé dans data/session/ (gitignorée via data/).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "cookies": cookie_string.strip(),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Requêtes HTTP internes
# ---------------------------------------------------------------------------

def _build_http_session(cookie_string: str) -> requests.Session:
    s = requests.Session()
    s.cookies.update(_parse_cookie_string(cookie_string))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Referer": f"{BASE_URL}/listeBus",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def _get_csrf_token(http: requests.Session) -> str:
    """Récupère le token CSRF depuis la page listeBus.

    Raises:
        SessionExpiredError: Si le portail redirige vers la page de login.
        PortailError: Si le meta csrf-token est introuvable dans le HTML.
    """
    resp = http.get(f"{BASE_URL}/listeBus", timeout=15, allow_redirects=True)
    if not resp.url.startswith(f"{BASE_URL}/listeBus"):
        raise SessionExpiredError(
            "Session expirée — redirection vers le login détectée"
        )
    m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', resp.text)
    if not m:
        raise PortailError("Token CSRF introuvable dans la page listeBus")
    return m.group(1)


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def fetch_detours(ligne: str, sens: str, session_path: Path = SESSION_PATH) -> dict:
    """Récupère le panneau détour pour une ligne/sens depuis le portail STM.

    Args:
        ligne:  Numéro de ligne (ex. "10", "125").
        sens:   Direction en minuscule (ex. "sud", "est", "ouest", "nord").

    Returns:
        JSON brut du portail : {"countDeviations": N, "html": "<fragment>"}.

    Raises:
        SessionExpiredError: Session absente, expirée ou accès refusé.
        PortailError:        Sens invalide, erreur HTTP, réponse non-JSON.
    """
    try:
        session_data = load_session(session_path)
    except FileNotFoundError:
        raise SessionExpiredError(
            "Aucune session enregistrée — saisir les cookies depuis le navigateur"
        )

    code_sens = SENS_MAP.get(sens.lower())
    if not code_sens:
        raise PortailError(
            f"Sens non reconnu : '{sens}'. Valeurs valides : {list(SENS_MAP)}"
        )

    http = _build_http_session(session_data["cookies"])
    csrf = _get_csrf_token(http)
    http.headers["X-CSRF-Token"] = csrf

    url = f"{BASE_URL}/resume-journee/panel/detour/{ligne}/{code_sens}"
    resp = http.get(url, timeout=15)

    if resp.status_code in (401, 403):
        raise SessionExpiredError(
            f"Accès refusé (HTTP {resp.status_code}) — session expirée"
        )
    if resp.status_code != 200:
        raise PortailError(f"Erreur HTTP {resp.status_code} pour {url}")

    try:
        return resp.json()
    except Exception as exc:
        raise PortailError(f"Réponse non-JSON du portail : {exc}") from exc


def is_session_valid(session_path: Path = SESSION_PATH) -> tuple[bool, str]:
    """Vérifie si la session est active (GET /listeBus sans redirection).

    Returns:
        (valide, message_lisible)
    """
    try:
        session_data = load_session(session_path)
    except FileNotFoundError:
        return False, "Aucune session enregistrée"

    try:
        http = _build_http_session(session_data["cookies"])
        _get_csrf_token(http)
        saved_at = session_data.get("saved_at", "?")
        return True, f"Session active (enregistrée le {saved_at})"
    except SessionExpiredError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Erreur réseau : {exc}"
