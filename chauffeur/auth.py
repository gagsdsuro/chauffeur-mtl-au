"""chauffeur.auth — authentification locale par PIN (fichier users.json).

Chaque compte est identifié par un matricule (cf. chauffeur.matricule).
Le PIN ne circule et n'est jamais stocké en clair : seul un hachage scrypt
(+ sel aléatoire) est conservé dans `data/users.json` (permissions 0600,
partagé entre chauffeurs). Le premier compte créé devient Chauffeur-admin ;
les suivants, Chauffeur.

Verrouillage : au-delà de TENTATIVES_MAX échecs consécutifs, le compte est
suspendu VERROU_SECONDES. Un PIN valide réinitialise le compteur.

Résolution du fichier : `chemin_users(data_dir=None)` → data/users.json —
paramétrable pour les tests hermétiques.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Iterator

from .depots import DATA_DIR
from .matricule import matricule_valide

ROLE_CHAUFFEUR = "Chauffeur"
ROLE_ADMIN = "Chauffeur-admin"
ROLES = (ROLE_CHAUFFEUR, ROLE_ADMIN)

PIN_MIN = 4        # chiffres minimum pour un PIN
PIN_MAX = 8        # chiffres maximum pour un PIN
_PIN_RE = re.compile(rf"^\d{{{PIN_MIN},{PIN_MAX}}}$")

TENTATIVES_MAX = 5        # échecs consécutifs avant verrouillage
VERROU_SECONDES = 300     # durée du verrouillage (5 min)

# Paramètres scrypt : protocole cohérent entre création et vérification.
_N = 1 << 14
_R = 8
_P = 1
_DKLEN = 32

_lock = threading.Lock()


def pin_valide(pin: str | None) -> bool:
    """PIN acceptable : 4 à 8 chiffres."""
    return isinstance(pin, str) and bool(_PIN_RE.match(pin))


def chemin_users(data_dir: Path | None = None) -> Path:
    """data/users.json — le fichier de comptes est partagé par tous."""
    return (data_dir or DATA_DIR) / "users.json"


# ── Sérialisation ─────────────────────────────────────────────────────────────

def charger_comptes(users_path: Path | None = None) -> dict:
    """Dictionnaire brut des comptes matricule → {sel, hash, role, …}.

    Un fichier absent → {}. Un fichier illisible ou non-JSON → ValueError
    (ne jamais écraser un registre corrompu sans le voir).
    """
    path = Path(users_path or chemin_users())
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Registre des comptes illisible : {path}") from exc


def _sauvegarder_comptes(comptes: dict, users_path: Path | None = None) -> None:
    """Écrit atomiquement le registre avec permissions 0600."""
    path = Path(users_path or chemin_users())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".users-", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(comptes, handle, indent=2, ensure_ascii=False)
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


def comptes_configure(users_path: Path | None = None) -> bool:
    """True si au moins un compte existe (l'authentification est active)."""
    return bool(charger_comptes(users_path))


def lister_matricules(users_path: Path | None = None) -> list[str]:
    """Matricules enregistrés, triés."""
    return sorted(charger_comptes(users_path))


# ── Hachage ───────────────────────────────────────────────────────────────────

def _hacher(pin: str, sel: bytes) -> bytes:
    return hashlib.scrypt(
        pin.encode("utf-8"), salt=sel, n=_N, r=_R, p=_P, dklen=_DKLEN
    )


def _nouveau_sel() -> bytes:
    return os.urandom(16)


def _verifier_hash(pin: str, sel: bytes, attendu: bytes) -> bool:
    try:
        obtenu = _hacher(pin, sel)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(obtenu, attendu)


# ── Gestion des comptes ───────────────────────────────────────────────────────

@contextmanager
def _comptes_verrouilles(users_path: Path) -> Iterator[dict]:
    """Lecture-modification-écriture atomique du registre (sous verrou)."""
    with _lock:
        comptes = charger_comptes(users_path)
        yield comptes
        _sauvegarder_comptes(comptes, users_path)


def _verrou_active(verrou_jusqua: str | None) -> bool:
    if not verrou_jusqua:
        return False
    try:
        fin = datetime.fromisoformat(verrou_jusqua)
    except ValueError:
        return False   # verrou corrompu : ignoré, compteur de tentatives l'emporte
    return datetime.now() < fin


def _verifier_operateur(comptes: dict, operateur: str | None) -> None:
    """Lève ValueError si `operateur` n'est pas un Chauffeur-admin enregistré."""
    info = comptes.get(operateur or "")
    if info is None:
        raise ValueError(f"Opérateur {operateur!r} inconnu.")
    if info.get("role") != ROLE_ADMIN:
        raise ValueError("Opération réservée aux Chauffeur-admin.")


def creer_compte(
    matricule: str,
    pin: str,
    nom: str | None = None,
    role: str | None = None,
    operateur: str | None = None,
    users_path: Path | None = None,
) -> dict:
    """Crée un compte PIN pour `matricule`.

    * Aucun compte existant → le premier sera **Chauffeur-admin** (obligatoire).
    * `role` explicite : « Chauffeur » ou « Chauffeur-admin ». Créer un nouveau
      Chauffeur-admin exige un `operateur` Chauffeur-admin (succession).
    * `operateur` absent et `role` non précisé → Chauffeur (création utilitaire).

    Lève ValueError si le matricule ou le PIN est invalide, si le compte
    existe déjà, si le rôle est inconnu, ou si l'opérateur n'a pas l'autorité
    requise. Retourne l'entrée créée (sans le hash).
    """
    if not matricule_valide(matricule):
        raise ValueError(f"Matricule invalide : {matricule!r}")
    if not pin_valide(pin):
        raise ValueError(
            f"PIN invalide : attendu {PIN_MIN} à {PIN_MAX} chiffres."
        )
    if role is not None and role not in ROLES:
        raise ValueError(f"Rôle inconnu : {role!r}")
    path = Path(users_path or chemin_users())
    with _comptes_verrouilles(path) as comptes:
        if matricule in comptes:
            raise ValueError(f"Compte déjà existant pour {matricule}.")
        nouvel_admin = not comptes
        if nouvel_admin:
            role_final = ROLE_ADMIN
        elif role is None:
            role_final = ROLE_CHAUFFEUR
        else:
            role_final = role
            if role_final == ROLE_ADMIN:
                _verifier_operateur(comptes, operateur)
        sel = _nouveau_sel()
        comptes[matricule] = {
            "nom": nom,
            "role": role_final,
            "sel": sel.hex(),
            "hash": _hacher(pin, sel).hex(),
            "creer_le": datetime.now().isoformat(timespec="seconds"),
            "tentatives": 0,
            "verrou_jusqua": None,
        }
    return {k: v for k, v in comptes[matricule].items() if k not in {"sel", "hash"}}


def revoquer_compte(
    matricule: str,
    operateur: str,
    users_path: Path | None = None,
) -> bool:
    """Retire le compte `matricule` de façon administrée (True si existant).

    Auto-gestion stricte : seul un Chauffeur-admin peut révoquer, jamais un
    autre Chauffeur-admin (autorité non modifiable par autrui) ni soi-même.
    """
    path = Path(users_path or chemin_users())
    with _comptes_verrouilles(path) as comptes:
        _verifier_operateur(comptes, operateur)
        compte = comptes.get(matricule)
        if compte is None:
            return False
        if compte.get("role") == ROLE_ADMIN:
            raise ValueError(
                "L'autorité d'un Chauffeur-admin n'est modifiable que par lui-même."
            )
        if matricule == operateur:
            raise ValueError("Impossible de révoquer son propre compte.")
        comptes.pop(matricule)
    return True


def compte_info(matricule: str, users_path: Path | None = None) -> dict | None:
    """Infos publiques du compte (nom, rôle, créé le), ou None si absent."""
    compte = charger_comptes(users_path).get(matricule)
    if compte is None:
        return None
    return {
        "nom": compte.get("nom"),
        "role": compte.get("role", ROLE_CHAUFFEUR),
        "creer_le": compte.get("creer_le"),
    }


def role(matricule: str, users_path: Path | None = None) -> str | None:
    """Rôle du compte (Chauffeur | Chauffeur-admin), ou None si absent."""
    info = compte_info(matricule, users_path)
    return info["role"] if info else None


def lister_comptes(users_path: Path | None = None) -> list[dict]:
    """Infos publiques de tous les comptes, triés par matricule.

    Chaque entrée : {matricule, nom, role, creer_le, verrouille}.
    """
    registre = charger_comptes(users_path)
    return [
        {
            "matricule": matricule,
            "nom": donnees.get("nom"),
            "role": donnees.get("role", ROLE_CHAUFFEUR),
            "creer_le": donnees.get("creer_le"),
            "verrouille": _verrou_active(donnees.get("verrou_jusqua", None)),
        }
        for matricule, donnees in sorted(registre.items())
    ]


def est_verrouille(matricule: str, users_path: Path | None = None) -> bool:
    """True si le compte est actuellement suspendu (verrouillage)."""
    compte = charger_comptes(users_path).get(matricule)
    return _verrou_active(compte.get("verrou_jusqua", None)) if compte else False


# ── Authentification ──────────────────────────────────────────────────────────

def verifier_pin(
    matricule: str, pin: str, users_path: Path | None = None
) -> tuple[bool, str]:
    """Vérifie un candidat (matricule, PIN) et gère le verrouillage.

    Retourne (True, message) si accepté, (False, message) sinon — le message
    précise « matricule inconnu », « compte verrouillé » (avec le délai
    restant) ou « PIN incorrect ».
    """
    path = Path(users_path or chemin_users())
    with _comptes_verrouilles(path) as comptes:
        compte = comptes.get(matricule)
        if compte is None:
            return False, f"Matricule {matricule!r} inconnu."
        if _verrou_active(compte.get("verrou_jusqua", None)):
            fin = datetime.fromisoformat(compte["verrou_jusqua"])
            reste = max(1, int((fin - datetime.now()).total_seconds()))
            return False, f"Compte verrouillé — réessayez dans {reste} s."
        if not matricule_valide(matricule) or not pin_valide(pin):
            raise ValueError("Candidat invalide : matricule ou PIN illisibles.")
        sel = bytes.fromhex(compte["sel"]) if isinstance(compte.get("sel"), str) else b""
        attendu = bytes.fromhex(compte["hash"]) if isinstance(compte.get("hash"), str) else b""
        if sel and attendu and _verifier_hash(pin, sel, attendu):
            compte["tentatives"] = 0
            compte["verrou_jusqua"] = None
            retour = True, "Authentification réussie."
        else:
            compte["tentatives"] = compte.get("tentatives", 0) + 1
            if compte["tentatives"] >= TENTATIVES_MAX:
                compte["verrou_jusqua"] = (
                    datetime.now() + timedelta(seconds=VERROU_SECONDES)
                ).isoformat(timespec="seconds")
                compte["tentatives"] = 0
                retour = (False, f"Trop de tentatives — compte verrouillé "
                                  f"{VERROU_SECONDES // 60} min.")
            else:
                reste = TENTATIVES_MAX - compte["tentatives"]
                retour = False, f"PIN incorrect — {reste} tentative(s) restante(s)."
        return retour


def changer_pin(
    matricule: str, pin: str, nouveau_pin: str, users_path: Path | None = None
) -> bool:
    """Change le PIN après vérification de l'ancien (True si réussi)."""
    if not pin_valide(nouveau_pin):
        raise ValueError(
            f"Nouveau PIN invalide : attendu {PIN_MIN} à {PIN_MAX} chiffres."
        )
    ok, message = verifier_pin(matricule, pin, users_path)
    if not ok:
        raise ValueError(message)
    path = Path(users_path or chemin_users())
    with _comptes_verrouilles(path) as comptes:
        compte = comptes[matricule]
        sel = _nouveau_sel()
        compte["sel"] = sel.hex()
        compte["hash"] = _hacher(nouveau_pin, sel).hex()
        compte["tentatives"] = 0
        compte["verrou_jusqua"] = None
    return True


# ── Opérations administrées (auto-gestion stricte des autorités) ─────────────

def changer_role(
    matricule: str,
    operateur: str,
    nouveau_role: str,
    users_path: Path | None = None,
) -> dict:
    """Change le rôle d'un compte (retourne ses infos publiques).

    Auto-gestion stricte (« seul à changer sa propre autorité ») :
    * `operateur` doit être Chauffeur-admin ;
    * modifier l'autorité d'**un autre** Chauffeur-admin est refusé
      (promotion comme destitution) ;
    * auto-destitution permise, sauf si `operateur` est le **dernier** admin
      (anti-verrouillage du système).
    """
    if nouveau_role not in ROLES:
        raise ValueError(f"Rôle inconnu : {nouveau_role!r}")
    path = Path(users_path or chemin_users())
    with _comptes_verrouilles(path) as comptes:
        _verifier_operateur(comptes, operateur)
        compte = comptes.get(matricule)
        if compte is None:
            raise ValueError(f"Compte inconnu : {matricule!r}")
        actuel = compte.get("role", ROLE_CHAUFFEUR)
        if actuel == nouveau_role:
            raise ValueError(f"{matricule} est déjà {nouveau_role}.")
        if matricule != operateur and actuel == ROLE_ADMIN:
            raise ValueError(
                "L'autorité d'un Chauffeur-admin n'est modifiable que par lui-même."
            )
        if matricule == operateur and nouveau_role == ROLE_CHAUFFEUR:
            nb_admins = sum(
                1 for c in comptes.values() if c.get("role") == ROLE_ADMIN
            )
            if nb_admins <= 1:
                raise ValueError(
                    "Impossible de destituer le dernier Chauffeur-admin."
                )
        compte["role"] = nouveau_role
    return compte_info(matricule, users_path) or {}


def reinitialiser_pin(
    matricule: str,
    nouveau_pin: str,
    operateur: str,
    users_path: Path | None = None,
) -> None:
    """Définit le PIN de `matricule` sans connaître l'ancien (admin).

    Effective aussi un déverrouillage (compteur et verrou remis à zéro).
    """
    if not pin_valide(nouveau_pin):
        raise ValueError(
            f"Nouveau PIN invalide : attendu {PIN_MIN} à {PIN_MAX} chiffres."
        )
    path = Path(users_path or chemin_users())
    with _comptes_verrouilles(path) as comptes:
        _verifier_operateur(comptes, operateur)
        compte = comptes.get(matricule)
        if compte is None:
            raise ValueError(f"Compte inconnu : {matricule!r}")
        sel = _nouveau_sel()
        compte["sel"] = sel.hex()
        compte["hash"] = _hacher(nouveau_pin, sel).hex()
        compte["tentatives"] = 0
        compte["verrou_jusqua"] = None


def deverrouiller_compte(
    matricule: str,
    operateur: str,
    users_path: Path | None = None,
) -> None:
    """Lève le verrouillage temporaire d'un compte (admin)."""
    path = Path(users_path or chemin_users())
    with _comptes_verrouilles(path) as comptes:
        _verifier_operateur(comptes, operateur)
        compte = comptes.get(matricule)
        if compte is None:
            raise ValueError(f"Compte inconnu : {matricule!r}")
        compte["tentatives"] = 0
        compte["verrou_jusqua"] = None