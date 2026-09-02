"""Accès au portail employé STM avec session HTTP persistante."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile

import requests

BASE_URL = "https://employe.stm.info"
SESSION_PATH = Path(__file__).resolve().parent.parent / "data" / "session" / "cookies.json"
SENS_MAP = {"est": "E", "ouest": "W", "nord": "N", "sud": "S"}


class SessionExpiredError(Exception):
    """Session portail expirée ou absente."""


class PortailError(Exception):
    """Erreur réseau ou réponse inattendue du portail."""


@dataclass(frozen=True)
class EtatSessionPortail:
    """État non sensible de la session; ne contient jamais les cookies."""

    statut: str
    message: str
    enregistree_le: str | None = None
    verifiee_le: str | None = None


def _parse_cookie_string(cookie_str: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies


def _cookie_string(http: requests.Session) -> str:
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in http.cookies)


def load_session(path: Path = SESSION_PATH) -> dict:
    path = Path(path)
    # Corrige aussi les anciens fichiers créés avant le stockage sécurisé.
    os.chmod(path, 0o600)
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_session(data: dict, path: Path) -> None:
    """Écrit atomiquement un secret lisible uniquement par son propriétaire."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".cookies-", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(tmp_name).unlink(missing_ok=True)
        raise


def save_session(cookie_string: str, path: Path = SESSION_PATH) -> None:
    """Sauvegarde une chaîne de cookies brute sans jamais la journaliser."""
    cookie_string = cookie_string.strip()
    if not cookie_string:
        raise ValueError("La chaîne de cookies est vide.")
    _write_session(
        {
            "cookies": cookie_string,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "last_validated_at": None,
            "status": "non_verifiee",
        },
        Path(path),
    )


def etat_session(session_path: Path = SESSION_PATH) -> EtatSessionPortail:
    """Retourne l'état local, sans effectuer d'appel réseau."""
    try:
        data = load_session(session_path)
    except FileNotFoundError:
        return EtatSessionPortail("absente", "Aucune session enregistrée")
    except Exception:
        return EtatSessionPortail("expiree", "Fichier de session illisible")
    statut = data.get("status", "non_verifiee")
    message = {
        "valide": "Session valide lors de la dernière vérification",
        "expiree": "Session expirée — renouvellement requis",
    }.get(statut, "Session enregistrée, validité à vérifier")
    return EtatSessionPortail(
        statut,
        message,
        data.get("saved_at"),
        data.get("last_validated_at"),
    )


def _build_http_session(cookie_string: str) -> requests.Session:
    http = requests.Session()
    http.cookies.update(_parse_cookie_string(cookie_string))
    http.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Referer": f"{BASE_URL}/listeBus",
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    return http


def _get_csrf_token(http: requests.Session) -> str:
    try:
        response = http.get(f"{BASE_URL}/listeBus", timeout=15, allow_redirects=True)
    except requests.RequestException as exc:
        raise PortailError(f"Erreur réseau pendant la validation : {exc}") from exc
    if response.status_code in (401, 403) or not response.url.startswith(f"{BASE_URL}/listeBus"):
        raise SessionExpiredError("Session expirée — connexion au portail requise")
    if response.status_code != 200:
        raise PortailError(f"Erreur HTTP {response.status_code} pendant la validation")
    match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', response.text)
    if not match:
        raise PortailError("Token CSRF introuvable dans la page listeBus")
    return match.group(1)


class PortailClient:
    """Client persistant pour valider et interroger plusieurs lignes."""

    def __init__(
        self,
        session_path: Path = SESSION_PATH,
        *,
        cookie_string: str | None = None,
        persister: bool = True,
    ):
        self.session_path = Path(session_path)
        self.persister = persister
        self._source = load_session(self.session_path) if cookie_string is None else {
            "cookies": cookie_string.strip(),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "last_validated_at": None,
            "status": "non_verifiee",
        }
        if not self._source.get("cookies"):
            raise SessionExpiredError("Aucune session enregistrée")
        self.http = _build_http_session(self._source["cookies"])
        self.csrf_token: str | None = None
        self.verifiee_le: str | None = None

    def _persist(self, statut: str = "valide") -> None:
        if not self.persister:
            return
        cookies = _cookie_string(self.http) or self._source["cookies"]
        _write_session(
            {
                "cookies": cookies,
                "saved_at": self._source.get("saved_at")
                or datetime.now().isoformat(timespec="seconds"),
                "last_validated_at": self.verifiee_le,
                "status": statut,
            },
            self.session_path,
        )

    def verifier(self) -> EtatSessionPortail:
        try:
            self.csrf_token = _get_csrf_token(self.http)
        except SessionExpiredError:
            self._persist("expiree")
            raise
        self.http.headers["X-CSRF-Token"] = self.csrf_token
        self.verifiee_le = datetime.now().isoformat(timespec="seconds")
        self._persist()
        return EtatSessionPortail(
            "valide", "Session active", self._source.get("saved_at"), self.verifiee_le
        )

    def fetch_detours(self, ligne: str, sens: str) -> dict:
        code_sens = SENS_MAP.get((sens or "").lower())
        if not code_sens:
            raise PortailError(f"Sens non reconnu : '{sens}'. Valeurs valides : {list(SENS_MAP)}")
        if self.csrf_token is None:
            self.verifier()
        url = f"{BASE_URL}/resume-journee/panel/detour/{ligne}/{code_sens}"
        try:
            response = self.http.get(url, timeout=15, allow_redirects=True)
        except requests.RequestException as exc:
            raise PortailError(f"Erreur réseau pour {ligne} {sens} : {exc}") from exc
        if response.status_code in (401, 403) or not response.url.startswith(
            f"{BASE_URL}/resume-journee/"
        ):
            self._persist("expiree")
            raise SessionExpiredError("Session expirée pendant la récupération")
        if response.status_code != 200:
            raise PortailError(f"Erreur HTTP {response.status_code} pour {ligne} {sens}")
        try:
            payload = response.json()
        except Exception as exc:
            raise PortailError(f"Réponse non-JSON pour {ligne} {sens}") from exc
        self._persist()
        return payload


def valider_et_sauvegarder_session(
    cookie_string: str, session_path: Path = SESSION_PATH
) -> tuple[bool, str]:
    """Valide un candidat en mémoire et ne le sauvegarde qu'après succès."""
    try:
        client = PortailClient(session_path, cookie_string=cookie_string, persister=False)
        state = client.verifier()
        _write_session(
            {
                "cookies": _cookie_string(client.http) or cookie_string.strip(),
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "last_validated_at": state.verifiee_le,
                "status": "valide",
            },
            Path(session_path),
        )
        return True, "Session validée et enregistrée"
    except (SessionExpiredError, PortailError, ValueError) as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Erreur réseau : {exc}"


def fetch_detours(ligne: str, sens: str, session_path: Path = SESSION_PATH) -> dict:
    """Façade compatible pour une récupération isolée."""
    client = PortailClient(session_path)
    client.verifier()
    return client.fetch_detours(ligne, sens)


def is_session_valid(session_path: Path = SESSION_PATH) -> tuple[bool, str]:
    """Valide la session enregistrée par un appel réel au portail."""
    try:
        state = PortailClient(session_path).verifier()
        return True, f"{state.message} (vérifiée le {state.verifiee_le})"
    except FileNotFoundError:
        return False, "Aucune session enregistrée"
    except (SessionExpiredError, PortailError) as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Erreur réseau : {exc}"
