#!/usr/bin/env python3
"""Gauche-Droite Parser"""

import re
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chauffeur.depots import sauvegarder_gd  # noqa: E402
from chauffeur.journal import ecrire_bloc  # noqa: E402
from chauffeur.registre_appariement import synchroniser_ligne  # noqa: E402
from chauffeur.registre_detours import synchroniser_evenements_ligne  # noqa: E402
from chauffeur.portail import texte_visible_html  # noqa: E402


class GDParser:
    """Parser pour donnees brutes Gauche-Droite"""

    VALID_DIRECTIONS = {"est", "ouest", "nord", "sud"}
    # Que faire des parcours du fichier existant absents du texte importé :
    #   "remplacer" : le fichier devient exactement le texte importé (import
    #                 complet d'une ligne/direction, ex. portail) ;
    #   "fusionner" : les parcours importés remplacent ceux de même id, les
    #                 autres sont conservés (collage d'un ou de quelques parcours).
    MODES = ("remplacer", "fusionner")
    # scripts/ -> racine du projet (~/chauffeur-mtl-au)
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR = PROJECT_ROOT / "data"
    GD_DIR = DATA_DIR / "Gauche-Droite"

    # Lignes a ignorer dans un bloc de parcours
    SKIP_PATTERNS = ("Imprimer", "Date de mise à jour", "Date de mise a jour")

    def __init__(self, raw_data: str, gd_dir: Path | None = None):
        self.raw_data = raw_data
        self.gd_dir = Path(gd_dir) if gd_dir is not None else self.GD_DIR
        self.ligne = None
        self.direction = None
        self.parcours = []
        self.errors = []
        self.avertissements: list[str] = []
        self.report = ""
        self.appariements: list[str] = []
        self.detours: list[str] = []
        self._expected_ligne: str | None = None
        self._expected_direction: str | None = None
        self._analyse: bool | None = None
        self.mode = "remplacer"
        self.parcours_conserves: list[Dict] = []

    @classmethod
    def from_portal_json(
        cls, payload: dict, ligne: str, direction: str, gd_dir: Path | None = None
    ) -> "GDParser":
        """Construit le parseur depuis le HTML sémantique de `/listeBus`."""
        html = payload.get("html") if isinstance(payload, dict) else None
        if not isinstance(html, str):
            parser = cls("", gd_dir=gd_dir)
            parser.errors.append("Réponse G-D du portail invalide")
            return parser

        texte = texte_visible_html(html, ids_ignores={"leftright-panel"})
        lignes = texte.splitlines()
        normalisees: list[str] = []
        i = 0
        while i < len(lignes):
            courant = lignes[i].strip()
            if courant.startswith("Parcours ") and i + 1 < len(lignes):
                suivant = lignes[i + 1].strip()
                if re.fullmatch(r"ID\s*\d+", suivant, re.IGNORECASE):
                    normalisees.append(courant + suivant)
                    i += 2
                    continue
            if i + 1 < len(lignes) and re.fullmatch(r"\d{5}", lignes[i + 1].strip()):
                normalisees.append(f"{courant} {lignes[i + 1].strip()}")
                i += 2
                continue
            normalisees.append(courant)
            i += 1

        parser = cls("\n".join(normalisees), gd_dir=gd_dir)
        parser._expected_ligne = str(ligne).lower()
        parser._expected_direction = (direction or "").lower()
        return parser

    def analyser(self) -> bool:
        """Lit l'en-tête et les parcours du texte, sans rien écrire. Idempotent."""
        if self._analyse is None:
            self._analyse = (not self.errors and self._extract_header()
                             and self._parse_parcours())
        return self._analyse

    def parcours_retires(self) -> list[Dict]:
        """Parcours du fichier existant (par id) absents du texte importé : ils
        disparaîtraient d'un import en mode « remplacer ». [] si le fichier est
        nouveau ou si l'analyse échoue."""
        if not self.analyser():
            return []
        ids = {p["id"] for p in self.parcours}
        return [p for p in self._parcours_existants() if p["id"] not in ids]

    def parse(self, mode: str = "remplacer"):
        """Importe le texte dans gd<ligne>_<direction>.json (voir `MODES`)."""
        if mode not in self.MODES:
            raise ValueError(f"Mode d'import inconnu : {mode!r} (attendu : {', '.join(self.MODES)})")
        self.mode = mode
        if self.errors:
            return None
        if not self.analyser():
            return None
        existing_data = self._load_existing_file()
        a_ecrire = self._parcours_a_ecrire()
        summary = self._generate_summary(existing_data)
        json_data = self._generate_json(a_ecrire)
        if not self._save_file(json_data):
            return None
        self.report = self._format_report(summary)
        # Appariement G-D ↔ GTFS des parcours modifiés (non bloquant), à côté
        # du répertoire G-D du parseur — commun à tous les chemins d'import
        # (CLI, portail, collage dans l'app), qui affichent et journalisent le rapport.
        self.appariements = synchroniser_ligne(self.ligne, self.direction, gd_dir=self.gd_dir)
        if self.appariements:
            self.report += "\n[APPARIEMENT]\n" + "\n".join(
                f"   {m}" for m in self.appariements) + "\n"
        # Un nouveau G-D peut rendre inapplicable un choix de détour validé.
        self.detours = synchroniser_evenements_ligne(
            self.ligne, self.direction, base=Path(self.gd_dir).parent)
        if self.detours:
            self.report += "\n[APPARIEMENT DÉTOURS]\n" + "\n".join(
                f"   {m}" for m in self.detours) + "\n"
        return json_data

    def _filename(self) -> str:
        return f"gd{self.ligne}_{self.direction}.json"

    def _extract_header(self) -> bool:
        header_match = re.search(r'Gauche-Droite\s*/\s*(\d+e?)\s+(est|ouest|nord|sud)',
                                 self.raw_data, re.IGNORECASE)
        if not header_match:
            self.errors.append("Format header invalide")
            return False
        self.ligne = header_match.group(1).lower()
        self.direction = header_match.group(2).lower()
        if self.direction not in self.VALID_DIRECTIONS:
            self.errors.append(f"Direction non reconnue: {self.direction}")
            return False
        if self._expected_ligne is not None and self.ligne != self._expected_ligne:
            self.errors.append(
                f"Ligne retournée inattendue: {self.ligne}, attendu {self._expected_ligne}"
            )
            return False
        if (
            self._expected_direction is not None
            and self.direction != self._expected_direction
        ):
            self.errors.append(
                f"Direction retournée inattendue: {self.direction}, "
                f"attendu {self._expected_direction}"
            )
            return False
        return True

    def _parse_parcours(self) -> bool:
        # Les parcours sont delimites par une ligne "Parcours <nom>ID <n>"
        blocks = re.split(r'\n(?=Parcours\s)', self.raw_data)
        default_id = 0
        for block in blocks:
            first = next((l.strip() for l in block.split('\n') if l.strip()), '')
            if not (first.startswith('Parcours') and 'ID' in first):
                continue
            default_id += 1
            parcours = self._parse_single_parcours(block, default_id)
            if parcours is None:
                return False
            self._ajouter_parcours(parcours)
        if not self.parcours:
            self.errors.append("Aucun parcours trouve")
            return False
        return True

    def _ajouter_parcours(self, parcours: Dict) -> None:
        """Ajoute un parcours en écartant les doublons du collage source.

        Un même bloc « Parcours … ID n » présent deux fois à l'identique
        (collage répété, export portail doublé) n'est gardé qu'une fois. Un
        même id au contenu différent est conservé, mais signalé : c'est une
        anomalie de la source à examiner, pas un doublon à trancher en silence.
        """
        memes_id = [p for p in self.parcours if p["id"] == parcours["id"]]
        if parcours in memes_id:
            self.avertissements.append(
                f"Parcours ID {parcours['id']} ({parcours['name']}) present en double "
                f"a l'identique dans la source : une seule copie conservee")
            return
        if memes_id:
            self.avertissements.append(
                f"Parcours ID {parcours['id']} present plusieurs fois avec un contenu "
                f"different ({parcours['name']}) : toutes les versions sont conservees, "
                f"verifier la source")
        self.parcours.append(parcours)

    def _parse_single_parcours(self, block: str, default_id: int) -> Optional[Dict]:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            return None
        # Premiere ligne: "Parcours <nom>ID <n>" (nom et ID colles)
        name_match = re.match(r'(Parcours\s+\w+(?:\s+\w+)*)\s*ID', lines[0])
        id_match = re.search(r'ID\s*(\d+)', lines[0])
        if not name_match:
            self.errors.append(f"Format invalide: {lines[0]}")
            return None
        name = name_match.group(1).strip()
        parcours_id = int(id_match.group(1)) if id_match else default_id

        # Stations: lignes terminees par un code a 5 chiffres
        # La premiere est le depart, la derniere l'arrivee.
        stations = []
        for line in lines:
            station_match = re.match(r'^(.+?)\s+(\d{5})$', line)
            if station_match:
                stations.append((station_match.group(1).strip(), int(station_match.group(2))))
        if len(stations) < 2:
            self.errors.append(f"Parcours {parcours_id}: depart/arrivee introuvable")
            return None
        start, start_code = stations[0]
        end, end_code = stations[-1]

        # Directions: lignes Gauche/Droite/Via
        directions = []
        for line in lines:
            if any(pattern in line for pattern in self.SKIP_PATTERNS):
                continue
            dir_match = re.match(r'^(Gauche|Droite|Via)\s*-\s*(.+)$', line, re.IGNORECASE)
            if dir_match:
                dir_type = dir_match.group(1).capitalize()
                dir_name = dir_match.group(2).strip()
                directions.append(f"{dir_type} - {dir_name}")
        if not directions:
            self.errors.append(f"Parcours {parcours_id}: Aucune direction")
            return None
        return {
            "id": parcours_id,
            "name": name,
            "start": start,
            "start_code": start_code,
            "end": end,
            "end_code": end_code,
            "direction": directions
        }

    def _load_existing_file(self) -> Optional[Dict]:
        filepath = self.gd_dir / self._filename()
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _parcours_existants(self) -> list[Dict]:
        existant = self._load_existing_file()
        return list((existant or {}).get("routes", [{}])[0].get("parcours", []))

    @staticmethod
    def _par_id(parcours: list[Dict]) -> Dict:
        """{id: [versions]} dans l'ordre : un même id peut avoir plusieurs versions."""
        par_id: Dict = {}
        for p in parcours:
            par_id.setdefault(p["id"], []).append(p)
        return par_id

    def _parcours_a_ecrire(self) -> list[Dict]:
        """Contenu du fichier après import. En mode « fusionner », les parcours
        importés remplacent ceux de même id à leur place ; les autres parcours
        existants sont conservés ; les ids nouveaux sont ajoutés à la fin."""
        self.parcours_conserves = []
        if self.mode != "fusionner":
            return list(self.parcours)
        nouveaux = self._par_id(self.parcours)
        fusion: list[Dict] = []
        places: set = set()
        for ancien in self._parcours_existants():
            if ancien["id"] not in nouveaux:
                fusion.append(ancien)
                self.parcours_conserves.append(ancien)
            elif ancien["id"] not in places:
                fusion.extend(nouveaux[ancien["id"]])
                places.add(ancien["id"])
        for id_, versions in nouveaux.items():
            if id_ not in places:
                fusion.extend(versions)
        return fusion

    def _generate_summary(self, existing_data: Optional[Dict]) -> Dict:
        """Changements par id de parcours (la clé partout dans le projet)."""
        summary = {
            "status": "created" if not existing_data else "updated",
            "changes": []
        }
        if not existing_data:
            return summary
        anciens = self._par_id(existing_data.get("routes", [{}])[0].get("parcours", []))
        nouveaux = self._par_id(self.parcours)
        for id_, old_versions in anciens.items():
            if id_ not in nouveaux:
                if self.mode == "fusionner":
                    continue   # conservé tel quel : rien à signaler comme changement
                old_p = old_versions[0]
                summary["changes"].append(
                    f"Parcours {id_} ({old_p['name']}): "
                    f"-SUPPRIME ({old_p['start']} -> {old_p['end']})"
                )
                continue
            new_versions = nouveaux[id_]
            if old_versions == new_versions:
                continue
            old_p, new_p = old_versions[0], new_versions[0]
            changes = []
            if len(old_versions) != len(new_versions):
                changes.append(f"versions: {len(old_versions)} -> {len(new_versions)}")
            if old_p["name"] != new_p["name"]:
                changes.append(f"nom: '{old_p['name']}' -> '{new_p['name']}'")
            if (old_p["start_code"], old_p["end_code"]) != (new_p["start_code"], new_p["end_code"]):
                changes.append(f"trajet: {old_p['start']} -> {old_p['end']} devient "
                               f"{new_p['start']} -> {new_p['end']}")
            if len(old_p["direction"]) != len(new_p["direction"]):
                changes.append(f"directions: {len(old_p['direction'])} -> {len(new_p['direction'])}")
            elif old_p["direction"] != new_p["direction"]:
                changes.append("directions modifiees")
            if not changes:
                changes.append("contenu modifie")
            summary["changes"].append(
                f"Parcours {id_} ({new_p['start']} -> {new_p['end']}): {', '.join(changes)}"
            )
        for id_, new_versions in nouveaux.items():
            if id_ not in anciens:
                new_p = new_versions[0]
                summary["changes"].append(
                    f"Parcours {id_} ({new_p['name']}): "
                    f"+NOUVEAU ({new_p['start']} -> {new_p['end']}, {len(new_p['direction'])} directions)"
                )
        return summary

    def _generate_json(self, parcours: Optional[list[Dict]] = None) -> Dict:
        return {
            "ligne": self.ligne,
            "direction": self.direction,
            "routes": [
                {
                    "line_number": self.ligne,
                    "direction": self.direction.capitalize(),
                    "parcours": self.parcours if parcours is None else parcours
                }
            ]
        }

    def _save_file(self, json_data: Dict) -> bool:
        filepath = self.gd_dir / self._filename()
        try:
            sauvegarder_gd(filepath, json_data)
            return True
        except Exception as e:
            self.errors.append(f"Erreur sauvegarde: {e}")
            return False

    def _format_report(self, summary: Dict) -> str:
        lines = ["\n" + "="*60, "RAPPORT: Importer Gauche-Droite", "="*60]
        if self.errors:
            lines.append("\n[ERREURS]:")
            for error in self.errors:
                lines.append(f"  - {error}")
            return "\n".join(lines)
        filename = self._filename()
        if self.avertissements:
            lines.append("\n[AVERTISSEMENTS]:")
            for avertissement in self.avertissements:
                lines.append(f"  - {avertissement}")
        if summary["status"] == "created":
            lines.append(f"\n[OK] Nouveau Gauche-Droite cree: {filename}")
            lines.append(f"   Ligne: {self.ligne}")
            lines.append(f"   Direction: {self.direction}")
            lines.append(f"   Parcours crees: {len(self.parcours)}")
        else:
            lines.append(f"\n[OK] Fichier mis a jour: {filename}")
            lines.append(f"   Ligne: {self.ligne}")
            lines.append(f"   Direction: {self.direction}")
            lines.append(f"   Total parcours: {len(self.parcours) + len(self.parcours_conserves)}")
            if self.parcours_conserves:
                lines.append("   Parcours conserves (absents du collage, mode fusion): "
                             + ", ".join(f"ID {p['id']}" for p in self.parcours_conserves))
        if summary["changes"]:
            lines.append(f"\n[CHANGEMENTS] ({len(summary['changes'])}):")
            for change in summary["changes"]:
                lines.append(f"   - {change}")
        else:
            if summary["status"] != "created":
                lines.append("\n[OK] Aucun changement detecte")
        lines.append(f"\n[LOCALISATION] {self.gd_dir}")
        lines.append("="*60 + "\n")
        return "\n".join(lines)

def split_sections(raw_data: str) -> List[str]:
    """Decoupe l'entree en sections, une par couple (ligne, direction).

    L'export du portail repete l'en-tete 'Gauche-Droite / <ligne> <direction>' devant
    chaque parcours, meme quand plusieurs parcours appartiennent a la meme
    ligne/direction (ex. Parcours principal + Parcours secondaire colles l'un
    apres l'autre). Les sections partageant le meme couple sont donc fusionnees
    en une seule, pour que tous leurs parcours atterrissent dans le meme
    fichier au lieu de s'ecraser les uns les autres.
    """
    pattern = re.compile(r'Gauche-Droite\s*/\s*(\d+e?)\s+(est|ouest|nord|sud)',
                         re.IGNORECASE)
    matches = list(pattern.finditer(raw_data))
    if not matches:
        return []
    parcours_re = re.compile(r'^Parcours\s', re.MULTILINE)
    groups: Dict[tuple, List[str]] = {}
    order: List[tuple] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_data)
        text = raw_data[start:end]
        key = (match.group(1).lower(), match.group(2).lower())
        if key not in groups:
            groups[key] = [text]
            order.append(key)
        else:
            # Sections suivantes du meme groupe : retirer l'en-tete repete
            # (Gauche-Droite / ..., Imprimer, Date de mise a jour) avant de
            # fusionner, sinon ce texte se fait mal interpreter comme une
            # instruction G-D (ex. "Gauche-Droite / 24 Est" matche le pattern
            # "Gauche - <rue>").
            pm = parcours_re.search(text)
            groups[key].append(text[pm.start():] if pm else text)
    return ["\n".join(groups[key]) for key in order]

def libelle_retraits(parser: "GDParser") -> str:
    """« Ligne 24 est : ID 21 (Parcours principal), ID 22 » — parcours qu'un
    import en mode « remplacer » ferait disparaître."""
    return f"Ligne {parser.ligne} {parser.direction} : " + ", ".join(
        f"ID {p['id']} ({p['name']})" for p in parser.parcours_retires())


def main():
    arg_parser = argparse.ArgumentParser(
        description="Importe des donnees brutes Gauche-Droite (portail employé) depuis stdin "
                    "vers des fichiers gd<ligne>_<direction>.json.")
    arg_parser.add_argument("--json", action="store_true",
                            help="Affiche aussi le JSON complet sur stdout "
                                 "(par defaut: rapport seulement).")
    arg_parser.add_argument("--log", action="store_true",
                            help="Sauvegarde la sortie dans data/log/parse_gd.log (append).")
    mode_grp = arg_parser.add_mutually_exclusive_group()
    mode_grp.add_argument("--fusionner", dest="mode", action="store_const", const="fusionner",
                          help="Les parcours collés remplacent ceux de meme ID ; les autres "
                               "parcours du fichier sont conserves.")
    mode_grp.add_argument("--remplacer", dest="mode", action="store_const", const="remplacer",
                          help="Le fichier devient exactement le texte colle (les parcours "
                               "absents du collage sont retires).")
    args = arg_parser.parse_args()

    raw_data = sys.stdin.read()
    sections = split_sections(raw_data) or [raw_data]
    results = []
    failed = False
    for section in sections:
        parser = GDParser(section)
        # Confirmation (non interactive) : sans --fusionner/--remplacer, un import
        # qui retirerait des parcours du fichier existant est refuse.
        if args.mode is None and parser.parcours_retires():
            failed = True
            erreurs = json.dumps({"errors": [
                "Import refuse, aucun fichier modifie. Parcours absents du collage : "
                + libelle_retraits(parser)
                + ". Relancer avec --fusionner (les conserver) ou --remplacer (les retirer)."
            ]}, indent=2, ensure_ascii=False)
            print(erreurs, file=sys.stderr)
            if args.log:
                ecrire_bloc("parse_gd", erreurs)
            continue
        json_data = parser.parse(args.mode or "remplacer")
        if json_data:
            print(parser.report)
            if args.log:
                ecrire_bloc("parse_gd", parser.report)
            results.append(json_data)
        else:
            failed = True
            erreurs = json.dumps({"errors": parser.errors}, indent=2, ensure_ascii=False)
            print(erreurs, file=sys.stderr)
            if args.log:
                ecrire_bloc("parse_gd", erreurs)
    if results and args.json:
        output = results if len(results) > 1 else results[0]
        print(json.dumps(output, indent=2, ensure_ascii=False))
    sys.exit(1 if failed or not results else 0)

if __name__ == "__main__":
    main()
