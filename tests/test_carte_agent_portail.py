#!/usr/bin/env python3
"""Tests hermétiques du téléchargement de la carte agent depuis le portail."""

import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import chauffeur.portail as portail  # noqa: E402

FRAGMENT = (ROOT / "tests" / "cas_portail" / "journee_carte_agent.html").read_text(
    encoding="utf-8"
)
LIEN = f"{portail.BASE_URL}/carte-agent/2026-11-09/recuperer/JETONMASQUE0123456789"


class Reponse:
    def __init__(self, url, status=200, text="", payload=None, content=b""):
        self.url = url
        self.status_code = status
        self.text = text
        self.content = content
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class SessionFausse:
    def __init__(self, reponses):
        self.cookies = requests.cookies.RequestsCookieJar()
        self.headers = {}
        self.reponses = list(reponses)
        self.appels = []

    def get(self, url, **kwargs):
        self.appels.append(url)
        return self.reponses.pop(0)


def _journee(html):
    return Reponse(
        f"{portail.BASE_URL}/resume-journee?date=2026-11-09",
        payload={"date": "2026-11-09", "journeeHtml": html, "voyagesHtml": ""},
    )


def _csrf():
    return Reponse(f"{portail.BASE_URL}/listeBus", text='<meta name="csrf-token" content="abc">')


def _client(tmp, reponses):
    fausse = SessionFausse(reponses)
    portail._build_http_session = lambda _: fausse
    chemin = Path(tmp) / "session" / "cookies.json"
    portail.save_session("laravel_session=secret", chemin)
    return portail.PortailClient(chemin), fausse


def _erreur(client, type_attendu):
    try:
        client.fetch_carte_agent("2026-11-09")
    except type_attendu as exc:
        return exc
    except Exception as exc:  # noqa: BLE001
        return exc
    return None


def main() -> int:
    echecs = []

    # ── lien_carte_agent (fonction pure) ────────────────────────────────────
    if portail.lien_carte_agent(FRAGMENT, "2026-11-09") != LIEN:
        echecs.append("lien du bouton « Carte Agent » non reconnu dans le fragment figé")
    inverse = (
        '<a href="%s" id="btnCarteAgent" class="x">carte</a>' % LIEN
    )
    if portail.lien_carte_agent(inverse, "2026-11-09") != LIEN:
        echecs.append("ordre d'attributs inversé non reconnu")
    if portail.lien_carte_agent(FRAGMENT, "2026-11-10") is not None:
        echecs.append("lien d'une autre date accepté")
    if portail.lien_carte_agent('<a id="btnLR" href="#">x</a>', "2026-11-09") is not None:
        echecs.append("absence de bouton « Carte Agent » mal gérée")
    etranger = FRAGMENT.replace(portail.BASE_URL, "https://exemple.invalide")
    if portail.lien_carte_agent(etranger, "2026-11-09") is not None:
        echecs.append("lien vers un autre hôte accepté (fuite possible des cookies)")
    if portail.lien_carte_agent("", "2026-11-09") is not None:
        echecs.append("HTML vide mal géré")

    original = portail._build_http_session
    try:
        with tempfile.TemporaryDirectory() as tmp:
            # ── PDF valide ──────────────────────────────────────────────────
            client, fausse = _client(tmp, [
                _csrf(), _journee(FRAGMENT),
                Reponse(LIEN, content=b"%PDF-1.7 \n%contenu"),
            ])
            pdf = client.fetch_carte_agent("2026-11-09")
            if not pdf.startswith(b"%PDF"):
                echecs.append("PDF non retourné")
            if fausse.appels[-1] != LIEN:
                echecs.append(f"URL de carte agent inattendue : {fausse.appels[-1]}")

            # ── lien absent ─────────────────────────────────────────────────
            client, _ = _client(tmp, [_csrf(), _journee("<div></div>")])
            exc = _erreur(client, portail.PortailError)
            if not isinstance(exc, portail.PortailError) or isinstance(
                exc, portail.SessionExpiredError
            ):
                echecs.append(f"lien absent : PortailError attendue, obtenu {exc!r}")

            # ── redirection vers la connexion ───────────────────────────────
            client, _ = _client(tmp, [
                _csrf(), _journee(FRAGMENT),
                Reponse(f"{portail.BASE_URL}/login", text="connexion"),
            ])
            exc = _erreur(client, portail.SessionExpiredError)
            if not isinstance(exc, portail.SessionExpiredError):
                echecs.append(f"redirection : SessionExpiredError attendue, obtenu {exc!r}")
            if portail.etat_session(Path(tmp) / "session" / "cookies.json").statut != "expiree":
                echecs.append("expiration non conservée dans l'état de session")

            # ── 401 ─────────────────────────────────────────────────────────
            client, _ = _client(tmp, [_csrf(), _journee(FRAGMENT), Reponse(LIEN, status=401)])
            exc = _erreur(client, portail.SessionExpiredError)
            if not isinstance(exc, portail.SessionExpiredError):
                echecs.append(f"401 : SessionExpiredError attendue, obtenu {exc!r}")

            # ── HTTP 500 ────────────────────────────────────────────────────
            client, _ = _client(tmp, [_csrf(), _journee(FRAGMENT), Reponse(LIEN, status=500)])
            exc = _erreur(client, portail.PortailError)
            if not isinstance(exc, portail.PortailError) or isinstance(
                exc, portail.SessionExpiredError
            ):
                echecs.append(f"HTTP 500 : PortailError attendue, obtenu {exc!r}")

            # ── HTML au lieu d'un PDF ───────────────────────────────────────
            client, _ = _client(tmp, [
                _csrf(), _journee(FRAGMENT), Reponse(LIEN, content=b"<html>erreur</html>"),
            ])
            exc = _erreur(client, portail.PortailError)
            if not isinstance(exc, portail.PortailError) or isinstance(
                exc, portail.SessionExpiredError
            ):
                echecs.append(f"contenu non PDF : PortailError attendue, obtenu {exc!r}")
    finally:
        portail._build_http_session = original

    if echecs:
        print("✗ test_carte_agent_portail")
        for erreur in echecs:
            print(f"    {erreur}")
        return 1
    print("✓ carte agent portail (lien, PDF, expiration, garde-fous hôte/contenu)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
