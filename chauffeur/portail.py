"""Accès au portail employé avec session HTTP persistante."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile

import requests

from . import depots
from .depots import SESSION_PATH

BASE_URL = "https://employe.stm.info"
SENS_MAP = {"est": "E", "ouest": "W", "nord": "N", "sud": "S"}


def _session_path_courant() -> Path:
    """Cookie de session portail : dossier de session du thread (app) sinon défaut."""
    dossier = depots.repertoire_prive_contexte("session")
    if dossier is not None:
        return dossier / "cookies.json"
    return SESSION_PATH


class _ExtracteurTexteHTML(HTMLParser):
    """Extrait le texte visible d'un fragment HTML sans dépendance externe."""

    BLOCS = {
        "article", "br", "dd", "div", "dl", "dt", "h1", "h2", "h3", "h4",
        "li", "ol", "p", "section", "span", "table", "tbody", "td", "th", "tr", "ul",
    }

    def __init__(self, ids_ignores: set[str]):
        super().__init__(convert_charrefs=True)
        self.ids_ignores = ids_ignores
        self.morceaux: list[str] = []
        self.profondeur_ignoree = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributs = dict(attrs)
        if self.profondeur_ignoree:
            self.profondeur_ignoree += 1
        elif tag in {"script", "style"} or attributs.get("id") in self.ids_ignores:
            self.profondeur_ignoree = 1
        elif tag in self.BLOCS:
            self.morceaux.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.profondeur_ignoree and tag in self.BLOCS:
            self.morceaux.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.profondeur_ignoree:
            self.profondeur_ignoree -= 1
        elif tag in self.BLOCS:
            self.morceaux.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.profondeur_ignoree:
            self.morceaux.append(data)

    def texte(self) -> str:
        lignes = []
        for ligne in "".join(self.morceaux).splitlines():
            propre = re.sub(r"\s+", " ", ligne).strip()
            if propre:
                lignes.append(propre)
        return "\n".join(lignes)


def texte_visible_html(source: str, *, ids_ignores: set[str] | None = None) -> str:
    """Convertit le HTML du portail en lignes de texte visibles et stables."""
    extracteur = _ExtracteurTexteHTML(set(ids_ignores or ()))
    extracteur.feed(source or "")
    return extracteur.texte()


class _ExtracteurLienCarteAgent(HTMLParser):
    """Relève le `href` de l'ancre `#btnCarteAgent` (ordre d'attributs libre)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a" or self.href is not None:
            return
        attributs = dict(attrs)
        if attributs.get("id") == "btnCarteAgent":
            self.href = attributs.get("href")


def lien_carte_agent(journee_html: str, date_str: str) -> str | None:
    """Lien « Carte Agent » de la journée, ou None s'il est absent ou suspect.

    Le jeton du lien est propre à la journée : on le lit dans la page. Le lien
    n'est retenu que s'il pointe vers le portail et vers la date demandée, pour
    que les cookies de session ne partent jamais vers un autre hôte.
    """
    extracteur = _ExtracteurLienCarteAgent()
    extracteur.feed(journee_html or "")
    href = (extracteur.href or "").strip()
    if href.startswith(f"{BASE_URL}/carte-agent/{date_str}/recuperer/"):
        return href
    return None


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


def load_session(path: Path | None = None) -> dict:
    path = Path(path or _session_path_courant())
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


def save_session(cookie_string: str, path: Path | None = None) -> None:
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
        Path(path or _session_path_courant()),
    )


def etat_session(session_path: Path | None = None) -> EtatSessionPortail:
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
        session_path: Path | None = None,
        *,
        cookie_string: str | None = None,
        persister: bool = True,
    ):
        self.session_path = Path(session_path or _session_path_courant())
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

    def _fetch_json(self, url: str, contexte: str, prefixe_attendu: str) -> dict:
        if self.csrf_token is None:
            self.verifier()
        try:
            response = self.http.get(url, timeout=15, allow_redirects=True)
        except requests.RequestException as exc:
            raise PortailError(f"Erreur réseau pour {contexte} : {exc}") from exc
        if response.status_code in (401, 403) or not response.url.startswith(prefixe_attendu):
            self._persist("expiree")
            raise SessionExpiredError("Session expirée pendant la récupération")
        if response.status_code != 200:
            raise PortailError(f"Erreur HTTP {response.status_code} pour {contexte}")
        try:
            payload = response.json()
        except Exception as exc:
            raise PortailError(f"Réponse non-JSON pour {contexte}") from exc
        if not isinstance(payload, dict):
            raise PortailError(f"Réponse JSON inattendue pour {contexte}")
        self._persist()
        return payload

    def fetch_detours(self, ligne: str, sens: str) -> dict:
        code_sens = SENS_MAP.get((sens or "").lower())
        if not code_sens:
            raise PortailError(f"Sens non reconnu : '{sens}'. Valeurs valides : {list(SENS_MAP)}")
        url = f"{BASE_URL}/resume-journee/panel/detour/{ligne}/{code_sens}"
        return self._fetch_json(
            url, f"{ligne} {sens}", f"{BASE_URL}/resume-journee/"
        )

    def fetch_journee(self, date_cible: date | str) -> dict:
        """Récupère le sommaire et les voyages de la date ISO demandée."""
        date_str = date_cible.isoformat() if isinstance(date_cible, date) else str(date_cible)
        try:
            date.fromisoformat(date_str)
        except ValueError as exc:
            raise PortailError(f"Date de journée invalide : {date_str}") from exc
        url = f"{BASE_URL}/resume-journee?date={date_str}"
        return self._fetch_json(url, f"la journée du {date_str}", f"{BASE_URL}/resume-journee")

    def fetch_gd(self, ligne: str, sens: str) -> dict:
        """Récupère tous les parcours G-D courants d'une ligne/direction."""
        code_sens = SENS_MAP.get((sens or "").lower())
        if not code_sens:
            raise PortailError(f"Sens non reconnu : '{sens}'. Valeurs valides : {list(SENS_MAP)}")
        url = f"{BASE_URL}/resume-journee/panel/chemin/{ligne}/{code_sens}/undefined"
        return self._fetch_json(
            url, f"le G-D {ligne} {sens}", f"{BASE_URL}/resume-journee/"
        )

    def fetch_carte_agent(self, date_cible: date | str) -> bytes:
        """Télécharge le PDF brut de la carte agent de la journée (bouton « Carte Agent »)."""
        date_str = date_cible.isoformat() if isinstance(date_cible, date) else str(date_cible)
        payload = self.fetch_journee(date_str)
        html = payload.get("journeeHtml")
        lien = lien_carte_agent(html if isinstance(html, str) else "", date_str)
        if not lien:
            raise PortailError(f"Aucune carte agent publiée pour le {date_str}")
        prefixe = f"{BASE_URL}/carte-agent/"
        try:
            response = self.http.get(lien, timeout=30, allow_redirects=True)
        except requests.RequestException as exc:
            raise PortailError(f"Erreur réseau pour la carte agent du {date_str} : {exc}") from exc
        if response.status_code in (401, 403) or not response.url.startswith(prefixe):
            self._persist("expiree")
            raise SessionExpiredError("Session expirée pendant la récupération")
        if response.status_code != 200:
            raise PortailError(
                f"Erreur HTTP {response.status_code} pour la carte agent du {date_str}"
            )
        contenu = response.content
        if not contenu.startswith(b"%PDF"):
            raise PortailError(f"La carte agent du {date_str} n'est pas un PDF")
        self._persist()
        return contenu


def valider_et_sauvegarder_session(
    cookie_string: str, session_path: Path | None = None
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
            Path(session_path or _session_path_courant()),
        )
        return True, "Session validée et enregistrée"
    except (SessionExpiredError, PortailError, ValueError) as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Erreur réseau : {exc}"


def fetch_detours(ligne: str, sens: str, session_path: Path | None = None) -> dict:
    """Façade compatible pour une récupération isolée."""
    client = PortailClient(session_path)
    client.verifier()
    return client.fetch_detours(ligne, sens)


def is_session_valid(session_path: Path | None = None) -> tuple[bool, str]:
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
