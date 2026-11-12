"""Orchestration métier de la préparation d'une journée de travail."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable, Iterable

from . import depots
from .depots import (
    DATA_DIR, EVENTS_DIR, GD_DIR,
    GTFS_DIR, GTFS_MANIFEST, RAPPORTS_DIR,
    charger_journee, chemin_evenements, chemin_gd,
    chemin_journee, info_gd, sauvegarder_journee,
)
from .calendrier import dossier_calendrier, ecrire_calendrier_sans_echec, lignes_calendrier
from .journal import ecrire_bloc
from .journee import lignes_de_service
from .evenements import (
    evenements_modifies, evenements_retires, resumer_changements_evenements,
)
from .portail import PortailClient, PortailError, SessionExpiredError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _rapports_dir() -> Path:
    """Répertoire des rapports : session (thread) si active, sinon constante."""
    return depots.repertoire_prive_contexte("rapports") or RAPPORTS_DIR


@dataclass
class ResultatLigneEvenements:
    ligne: str
    direction: str
    succes: bool
    modifie: bool = False
    message: str = ""
    changements: list[str] = field(default_factory=list)
    evenements_retires: list[dict] = field(default_factory=list)
    evenements_modifies: list[dict] = field(default_factory=list)


@dataclass
class ResultatRafraichissement:
    lignes: list[ResultatLigneEvenements] = field(default_factory=list)
    restantes: list[tuple[str, str]] = field(default_factory=list)
    session_expiree: bool = False

    @property
    def succes_complet(self) -> bool:
        return not self.session_expiree and not self.restantes and all(
            ligne.succes for ligne in self.lignes
        )

    @property
    def modifie(self) -> bool:
        return any(ligne.modifie for ligne in self.lignes)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ResultatRafraichissement":
        return cls(
            lignes=[ResultatLigneEvenements(**item) for item in data.get("lignes", [])],
            restantes=[tuple(item) for item in data.get("restantes", [])],
            session_expiree=bool(data.get("session_expiree")),
        )


def fusionner_rafraichissements(
    precedent: ResultatRafraichissement | None,
    suivant: ResultatRafraichissement,
) -> ResultatRafraichissement:
    """Fusionne une reprise sans retraiter les résultats déjà obtenus."""
    if precedent is None:
        return suivant
    return ResultatRafraichissement(
        lignes=precedent.lignes + suivant.lignes,
        restantes=suivant.restantes,
        session_expiree=suivant.session_expiree,
    )


def _traiter_ligne(client: PortailClient, ligne: str, direction: str, log: bool) -> ResultatLigneEvenements:
    """Récupère, compare et sauvegarde une ligne/direction."""
    # Import tardif : le parseur reste compatible avec son CLI historique.
    from scripts.parse_event import PortailEventParser

    try:
        raw = client.fetch_detours(ligne, direction)
    except SessionExpiredError:
        raise
    except PortailError as exc:
        return ResultatLigneEvenements(ligne, direction, False, message=str(exc))

    parser = PortailEventParser.from_portal_json(json.dumps(raw), ligne, direction)
    if parser.errors:
        message = parser.get_summary()
        if log:
            parser.append_log(message)
        return ResultatLigneEvenements(ligne, direction, False, message=message)

    avant = parser.load_existing_events().get("detours", [])
    saved, changed = parser.save_json()
    changements = _decrire_changements(avant, parser.events) if changed else []
    retires = evenements_retires(avant, parser.events) if changed else []
    modifies = evenements_modifies(avant, parser.events) if changed else []
    # Un appel valide sans événement matérialise un fichier vide, mais ne rend
    # pas un rapport obsolète si le contenu métier demeure [].
    path = chemin_evenements(ligne, direction)
    if saved and not parser.events and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(parser.to_fichier().to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    message = parser.get_summary()
    if log:
        parser.append_log(message)
    return ResultatLigneEvenements(
        ligne=ligne,
        direction=direction,
        succes=saved,
        modifie=changed,
        message=message,
        changements=changements,
        evenements_retires=retires,
        evenements_modifies=modifies,
    )


def _decrire_changements(avant: list[dict], apres: list[dict]) -> list[str]:
    """Résumé structuré par ID, y compris les doublons légitimes d'un événement."""
    return resumer_changements_evenements(avant, apres)


def rafraichir_evenements_journee(
    journee: dict,
    *,
    restantes_seulement: bool = False,
    paires: Iterable[tuple[str, str]] | None = None,
    client: PortailClient | None = None,
    log: bool = True,
) -> ResultatRafraichissement:
    """Rafraîchit un lot avec une seule validation et une seule session HTTP."""
    liste = list(paires) if paires is not None else lignes_de_service(
        journee, restantes_seulement=restantes_seulement
    )
    if not liste:
        return ResultatRafraichissement()
    try:
        client = client or PortailClient()
        client.verifier()
    except (FileNotFoundError, SessionExpiredError):
        return ResultatRafraichissement(restantes=liste, session_expiree=True)
    except PortailError as exc:
        return ResultatRafraichissement(
            lignes=[ResultatLigneEvenements(liste[0][0], liste[0][1], False, message=str(exc))],
            restantes=liste[1:],
        )

    resultat = ResultatRafraichissement()
    for index, (ligne, direction) in enumerate(liste):
        try:
            resultat.lignes.append(_traiter_ligne(client, ligne, direction, log))
        except SessionExpiredError:
            resultat.session_expiree = True
            resultat.restantes = liste[index:]
            break
    return resultat


@dataclass
class ResultatImportationJournee:
    succes: bool
    date: str
    modifie: bool = False
    message: str = ""
    chemin: Path | None = None
    session_expiree: bool = False
    calendrier: list[Path] = field(default_factory=list)


def importer_journee_portail(
    date_cible: date | str,
    *,
    client: PortailClient | None = None,
    log: bool = True,
) -> ResultatImportationJournee:
    """Récupère, valide et sauvegarde une journée depuis le portail employé."""
    date_str = date_cible.isoformat() if isinstance(date_cible, date) else str(date_cible)
    try:
        date.fromisoformat(date_str)
    except ValueError:
        return ResultatImportationJournee(False, date_str, message="Date ISO invalide")
    try:
        client = client or PortailClient()
        client.verifier()
        payload = client.fetch_journee(date_str)
    except (FileNotFoundError, SessionExpiredError):
        return ResultatImportationJournee(False, date_str, session_expiree=True)
    except PortailError as exc:
        return ResultatImportationJournee(False, date_str, message=str(exc))

    from scripts.parse_journee import JourneeParser

    parser = JourneeParser.from_portal_json(payload, date_str)
    journee = parser.parse()
    if journee is None:
        message = parser.get_summary()
        if log:
            ecrire_bloc("parse_journee", message)
        return ResultatImportationJournee(False, date_str, message=message)

    path = chemin_journee(date_str)
    avant = charger_journee(path) if path.exists() else None
    contenu = journee.to_dict()
    sauvegarder_journee(path, contenu)
    calendrier, erreur = ecrire_calendrier_sans_echec(contenu, dossier_calendrier(path))
    message = "\n".join(
        [parser.get_summary(journee, path), *lignes_calendrier(calendrier, erreur)]
    )
    if log:
        ecrire_bloc("parse_journee", message)
    return ResultatImportationJournee(
        True, date_str, modifie=avant != contenu, message=message, chemin=path,
        calendrier=calendrier,
    )


@dataclass
class ResultatLigneGD:
    ligne: str
    direction: str
    succes: bool
    modifie: bool = False
    message: str = ""


@dataclass
class ResultatRafraichissementGD:
    lignes: list[ResultatLigneGD] = field(default_factory=list)
    restantes: list[tuple[str, str]] = field(default_factory=list)
    session_expiree: bool = False

    @property
    def succes_complet(self) -> bool:
        return not self.session_expiree and not self.restantes and all(
            ligne.succes for ligne in self.lignes
        )

    @property
    def modifie(self) -> bool:
        return any(ligne.modifie for ligne in self.lignes)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ResultatRafraichissementGD":
        return cls(
            lignes=[ResultatLigneGD(**item) for item in data.get("lignes", [])],
            restantes=[tuple(item) for item in data.get("restantes", [])],
            session_expiree=bool(data.get("session_expiree")),
        )


def fusionner_rafraichissements_gd(
    precedent: ResultatRafraichissementGD | None,
    suivant: ResultatRafraichissementGD,
) -> ResultatRafraichissementGD:
    """Fusionne une reprise G-D sans retraiter les lignes déjà réussies."""
    if precedent is None:
        return suivant
    return ResultatRafraichissementGD(
        lignes=precedent.lignes + suivant.lignes,
        restantes=suivant.restantes,
        session_expiree=suivant.session_expiree,
    )


def _traiter_gd(
    client: PortailClient, ligne: str, direction: str, log: bool
) -> ResultatLigneGD:
    from scripts.parse_gd import GDParser

    try:
        payload = client.fetch_gd(ligne, direction)
    except SessionExpiredError:
        raise
    except PortailError as exc:
        return ResultatLigneGD(ligne, direction, False, message=str(exc))

    path = chemin_gd(ligne, direction, GD_DIR)
    try:
        avant = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, json.JSONDecodeError):
        avant = None
    parser = GDParser.from_portal_json(payload, ligne, direction, gd_dir=GD_DIR)
    contenu = parser.parse()
    if contenu is None:
        message = "❌ " + ("; ".join(parser.errors) or "Échec du parsing G-D")
        if log:
            ecrire_bloc("parse_gd", message)
        return ResultatLigneGD(ligne, direction, False, message=message)
    if log:
        ecrire_bloc("parse_gd", parser.report)
    return ResultatLigneGD(
        ligne, direction, True, modifie=avant != contenu, message=parser.report
    )


def rafraichir_gd_journee(
    journee: dict,
    *,
    paires: Iterable[tuple[str, str]] | None = None,
    manquants_ou_perimes_seulement: bool = True,
    client: PortailClient | None = None,
    log: bool = True,
) -> ResultatRafraichissementGD:
    """Récupère les G-D utiles à une journée avec une seule session HTTP."""
    liste = list(paires) if paires is not None else lignes_de_service(journee)
    liste = list(dict.fromkeys((str(l), str(d).lower()) for l, d in liste))
    if manquants_ou_perimes_seulement and paires is None:
        liste = [
            (ligne, direction)
            for ligne, direction in liste
            if not info_gd(ligne, direction, gd_dir=GD_DIR)["fresh"]
        ]
    if not liste:
        return ResultatRafraichissementGD()
    try:
        client = client or PortailClient()
        client.verifier()
    except (FileNotFoundError, SessionExpiredError):
        return ResultatRafraichissementGD(restantes=liste, session_expiree=True)
    except PortailError as exc:
        return ResultatRafraichissementGD(
            lignes=[ResultatLigneGD(liste[0][0], liste[0][1], False, message=str(exc))],
            restantes=liste[1:],
        )

    resultat = ResultatRafraichissementGD()
    for index, (ligne, direction) in enumerate(liste):
        try:
            resultat.lignes.append(_traiter_gd(client, ligne, direction, log))
        except SessionExpiredError:
            resultat.session_expiree = True
            resultat.restantes = liste[index:]
            break
    return resultat


@dataclass(frozen=True)
class EtatRapport:
    variante: str
    statut: str
    chemin: Path
    empreinte: str


@dataclass
class ResultatRapport:
    variante: str
    statut: str
    message: str
    chemin: Path | None = None


def _ajouter_fichier(hash_: "hashlib._Hash", label: str, path: Path) -> None:
    hash_.update(label.encode("utf-8"))
    hash_.update(b"\0")
    if path.exists():
        contenu = path.read_bytes()
        if path.suffix.lower() == ".json":
            try:
                contenu = json.dumps(
                    json.loads(contenu.decode("utf-8")),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        hash_.update(contenu)
    else:
        hash_.update(b"<absent>")
    hash_.update(b"\0")


def empreinte_sources(journee_path: Path, variante: str, niveau: str | None = None) -> str:
    """Empreinte du contenu réellement susceptible d'influencer un rapport."""
    journee_path = Path(journee_path)
    journee = charger_journee(journee_path)
    digest = hashlib.sha256()
    digest.update(f"{variante}:{niveau or ''}\0".encode("utf-8"))
    _ajouter_fichier(digest, "journee", journee_path)
    paires = lignes_de_service(journee)
    for ligne, direction in sorted(paires):
        _ajouter_fichier(digest, f"gd:{ligne}:{direction}", chemin_gd(ligne, direction))
    if variante == "journalier":
        for ligne in sorted({ligne for ligne, _ in paires}):
            fichiers = sorted(EVENTS_DIR.glob(f"{ligne}_*.json"))
            if not fichiers:
                _ajouter_fichier(digest, f"events:{ligne}", EVENTS_DIR / f".{ligne}-absent")
            for path in fichiers:
                _ajouter_fichier(digest, f"events:{path.name}", path)
    else:
        for ligne, direction in sorted(paires):
            _ajouter_fichier(
                digest, f"events:{ligne}:{direction}", chemin_evenements(ligne, direction)
            )
        _ajouter_fichier(digest, "gtfs", GTFS_MANIFEST)
    return digest.hexdigest()


def chemin_manifeste_rapports(date_str: str, rapports_dir: Path | None = None) -> Path:
    return Path(rapports_dir or _rapports_dir()) / f"rapport-etat-{date_str}.json"


def _charger_manifeste(path: Path) -> dict:
    if not path.exists():
        return {"rapports": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"rapports": {}}


def etat_rapport(
    journee_path: Path,
    variante: str,
    *,
    niveau: str | None = None,
    rapports_dir: Path | None = None,
) -> EtatRapport:
    journee = charger_journee(journee_path)
    date_str = journee.get("date") or Path(journee_path).stem.removeprefix("journee-")
    rapports_dir = rapports_dir or _rapports_dir()
    if variante == "journalier":
        output = Path(rapports_dir) / f"rapport-{date_str}.pdf"
        key = "journalier"
    else:
        niveau = niveau or "standard"
        output = Path(rapports_dir) / f"rapport-v2-{date_str}-{niveau}.html"
        key = f"v2_{niveau}"
    fingerprint = empreinte_sources(journee_path, variante, niveau)
    record = _charger_manifeste(chemin_manifeste_rapports(date_str, rapports_dir)).get(
        "rapports", {}
    ).get(key, {})
    if not output.exists():
        statut = "absent"
    elif record.get("empreinte") == fingerprint:
        statut = "a_jour"
    else:
        statut = "obsolete"
    return EtatRapport(key, statut, output, fingerprint)


def marquer_rapport_a_jour(
    journee_path: Path, etat: EtatRapport, rapports_dir: Path | None = None
) -> None:
    journee = charger_journee(journee_path)
    date_str = journee.get("date") or Path(journee_path).stem.removeprefix("journee-")
    path = chemin_manifeste_rapports(date_str, rapports_dir)
    data = _charger_manifeste(path)
    data.setdefault("rapports", {})[etat.variante] = {
        "empreinte": etat.empreinte,
        "fichier": etat.chemin.name,
        "genere_le": datetime.now().isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _generer_journalier(journee_path: Path, output: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "gen_rapport.py"), "--journee", str(journee_path),
         "--output", str(output)],
        capture_output=True,
        text=True,
    )
    message = result.stdout + ("\n" + result.stderr if result.stderr else "")
    return result.returncode == 0 and output.exists(), message.strip()


def _generer_v2(journee_path: Path, output: Path, niveau: str) -> tuple[bool, str]:
    try:
        from scripts.gen_rapport_v2 import generer_rapport
        generer_rapport(journee_path, fmt="html", output=output, niveau=niveau)
        return output.exists(), f"Rapport v2 {niveau} généré."
    except Exception as exc:
        return False, str(exc)


def generer_v2_et_marquer(
    journee_path: Path,
    *,
    niveau: str = "détaillé",
    rapports_dir: Path | None = None,
) -> ResultatRapport:
    """Force une génération v2 et mémorise l'empreinte effectivement utilisée."""
    etat = etat_rapport(journee_path, "v2", niveau=niveau, rapports_dir=rapports_dir)
    if not GTFS_DIR.exists():
        return ResultatRapport("v2", "bloque", "GTFS statique absent", etat.chemin)
    ok, message = _generer_v2(journee_path, etat.chemin, niveau)
    if ok:
        # Recalcul après génération pour couvrir une source modifiée pendant le travail.
        etat = etat_rapport(journee_path, "v2", niveau=niveau, rapports_dir=rapports_dir)
        marquer_rapport_a_jour(journee_path, etat, rapports_dir)
    return ResultatRapport("v2", "genere" if ok else "erreur", message, etat.chemin)


def finaliser_rapports(
    journee_path: Path,
    *,
    niveau_v2: str = "standard",
    rapports_dir: Path | None = None,
    generateur_journalier: Callable[[Path, Path], tuple[bool, str]] | None = None,
    generateur_v2: Callable[[Path, Path, str], tuple[bool, str]] | None = None,
    variantes: Iterable[str] = ("journalier", "v2"),
) -> list[ResultatRapport]:
    """Génère uniquement les variantes absentes ou obsolètes.

    `variantes` restreint les rapports traités (« journalier », « v2 »).
    """
    variantes = set(variantes)
    rapports_dir = Path(rapports_dir or _rapports_dir())
    rapports_dir.mkdir(parents=True, exist_ok=True)
    resultats: list[ResultatRapport] = []
    if "journalier" in variantes:
        etat_j = etat_rapport(journee_path, "journalier", rapports_dir=rapports_dir)
        if etat_j.statut == "a_jour":
            resultats.append(ResultatRapport("journalier", "ignore", "Rapport déjà à jour", etat_j.chemin))
        else:
            ok, message = (generateur_journalier or _generer_journalier)(journee_path, etat_j.chemin)
            if ok:
                marquer_rapport_a_jour(journee_path, etat_j, rapports_dir)
            resultats.append(ResultatRapport("journalier", "genere" if ok else "erreur", message, etat_j.chemin))
    if "v2" not in variantes:
        return resultats

    etat_v2 = etat_rapport(
        journee_path, "v2", niveau=niveau_v2, rapports_dir=rapports_dir
    )
    if not GTFS_DIR.exists():
        resultats.append(ResultatRapport("v2", "bloque", "GTFS statique absent", etat_v2.chemin))
    elif etat_v2.statut == "a_jour":
        resultats.append(ResultatRapport("v2", "ignore", "Rapport déjà à jour", etat_v2.chemin))
    else:
        ok, message = (generateur_v2 or _generer_v2)(journee_path, etat_v2.chemin, niveau_v2)
        if ok:
            marquer_rapport_a_jour(journee_path, etat_v2, rapports_dir)
        resultats.append(ResultatRapport("v2", "genere" if ok else "erreur", message, etat_v2.chemin))
    return resultats
