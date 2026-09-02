#!/usr/bin/env python3
"""Tests hermétiques de la session persistante du portail STM."""

import json
import stat
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import chauffeur.portail as portail  # noqa: E402


class Reponse:
    def __init__(self, url, status=200, text="", payload=None):
        self.url = url
        self.status_code = status
        self.text = text
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class SessionFausse:
    def __init__(self, cookies, reponses):
        self.cookies = requests.cookies.RequestsCookieJar()
        self.cookies.update(portail._parse_cookie_string(cookies))
        self.headers = {}
        self.reponses = list(reponses)
        self.appels = []

    def get(self, url, **kwargs):
        self.appels.append(url)
        return self.reponses.pop(0)


def main() -> int:
    echecs = []
    original_build = portail._build_http_session
    try:
        with tempfile.TemporaryDirectory() as tmp:
            session_path = Path(tmp) / "session" / "cookies.json"
            portail.save_session("laravel_session=secret", session_path)
            mode = stat.S_IMODE(session_path.stat().st_mode)
            if mode != 0o600:
                echecs.append(f"permissions cookies: {oct(mode)}, attendu 0o600")

            fake = SessionFausse(
                "laravel_session=secret",
                [
                    Reponse(
                        f"{portail.BASE_URL}/listeBus", text='<meta name="csrf-token" content="abc">'
                    ),
                    Reponse(
                        f"{portail.BASE_URL}/resume-journee/panel/detour/24/E",
                        payload={"countDeviations": 0, "html": ""},
                    ),
                ],
            )
            fake.cookies.set("rotation", "nouvelle")
            portail._build_http_session = lambda _: fake
            client = portail.PortailClient(session_path)
            etat = client.verifier()
            payload = client.fetch_detours("24", "est")
            if etat.statut != "valide" or payload.get("countDeviations") != 0:
                echecs.append("validation/récupération valide non reconnue")
            saved = json.loads(session_path.read_text(encoding="utf-8"))
            if "rotation=nouvelle" not in saved.get("cookies", ""):
                echecs.append("cookie tourné non persisté")
            if portail.etat_session(session_path).statut != "valide":
                echecs.append("état valide non exposé après vérification")
            if len(fake.appels) != 2:
                echecs.append("la session a été revalidée pour chaque ligne")

            redirect = SessionFausse(
                "laravel_session=secret",
                [Reponse(f"{portail.BASE_URL}/login", text="connexion")],
            )
            portail._build_http_session = lambda _: redirect
            ok, message = portail.is_session_valid(session_path)
            if ok or "secret" in message:
                echecs.append("redirection de connexion ou fuite du cookie mal gérée")
            if portail.etat_session(session_path).statut != "expiree":
                echecs.append("expiration non conservée dans l'état de session")

            sans_csrf = SessionFausse(
                "laravel_session=nouveau",
                [Reponse(f"{portail.BASE_URL}/listeBus", text="<html></html>")],
            )
            portail._build_http_session = lambda _: sans_csrf
            avant = session_path.read_bytes()
            ok, _ = portail.valider_et_sauvegarder_session(
                "laravel_session=candidat", session_path
            )
            if ok or session_path.read_bytes() != avant:
                echecs.append("un candidat invalide a écrasé la session enregistrée")
    finally:
        portail._build_http_session = original_build

    if echecs:
        print("✗ test_portail")
        for erreur in echecs:
            print(f"    {erreur}")
        return 1
    print("✓ session portail (validation, rotation, permissions, absence de fuite)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
