#!/usr/bin/env python3
"""STM Gauche-Droite Parser"""

import re
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional

class GDParser:
    """Parser pour donnees brutes Gauche-Droite"""

    VALID_DIRECTIONS = {"est", "ouest", "nord", "sud"}
#    PROJECT_ROOT = Path(__file__).parent.parent.parent  # Up to Chauffeur STM/
    PROJECT_ROOT = Path(__file__).resolve().parent
#    GD_DIR = PROJECT_ROOT / "Données" / "Gauche-Droite"
    GD_DIR = PROJECT_ROOT

    # Lignes a ignorer dans un bloc de parcours
    SKIP_PATTERNS = ("Imprimer", "Date de mise à jour", "Date de mise a jour")

    def __init__(self, raw_data: str):
        self.raw_data = raw_data
        self.ligne = None
        self.direction = None
        self.parcours = []
        self.errors = []

    def parse(self):
        if not self._extract_header():
            return None
        if not self._parse_parcours():
            return None
        existing_data = self._load_existing_file()
        summary = self._generate_summary(existing_data)
        json_data = self._generate_json()
        self._save_file(json_data)
        self._print_report(summary)
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
            self.parcours.append(parcours)
        if not self.parcours:
            self.errors.append("Aucun parcours trouve")
            return False
        return True

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
        filepath = self.GD_DIR / self._filename()
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _generate_summary(self, existing_data: Optional[Dict]) -> Dict:
        summary = {
            "status": "created" if not existing_data else "updated",
            "changes": []
        }
        if not existing_data:
            return summary
        existing_parcours_list = existing_data.get("routes", [{}])[0].get("parcours", [])
        existing_by_endpoints = {
            (p["start_code"], p["end_code"]): p for p in existing_parcours_list
        }
        new_by_endpoints = {
            (p["start_code"], p["end_code"]): p for p in self.parcours
        }
        for endpoints, old_p in existing_by_endpoints.items():
            if endpoints in new_by_endpoints:
                new_p = new_by_endpoints[endpoints]
                changes = []
                if old_p["name"] != new_p["name"]:
                    changes.append(f"nom: '{old_p['name']}' -> '{new_p['name']}'")
                if len(old_p["direction"]) != len(new_p["direction"]):
                    changes.append(f"directions: {len(old_p['direction'])} -> {len(new_p['direction'])}")
                if old_p["direction"] != new_p["direction"]:
                    if not any("directions" in c for c in changes):
                        changes.append("directions modifiees")
                if changes:
                    summary["changes"].append(
                        f"Parcours {old_p['id']} ({old_p['start']} -> {old_p['end']}): "
                        f"{', '.join(changes)}"
                    )
        for endpoints, new_p in new_by_endpoints.items():
            if endpoints not in existing_by_endpoints:
                summary["changes"].append(
                    f"Parcours {new_p['id']} ({new_p['name']}): "
                    f"+NOUVEAU ({new_p['start']} -> {new_p['end']}, {len(new_p['direction'])} directions)"
                )
        for endpoints, old_p in existing_by_endpoints.items():
            if endpoints not in new_by_endpoints:
                summary["changes"].append(
                    f"Parcours {old_p['id']} ({old_p['name']}): "
                    f"-SUPPRIME ({old_p['start']} -> {old_p['end']})"
                )
        return summary

    def _generate_json(self) -> Dict:
        return {
            "ligne": self.ligne,
            "direction": self.direction,
            "routes": [
                {
                    "line_number": self.ligne,
                    "direction": self.direction,
                    "parcours": self.parcours
                }
            ]
        }

    def _save_file(self, json_data: Dict) -> bool:
        filepath = self.GD_DIR / self._filename()
        try:
            self.GD_DIR.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.errors.append(f"Erreur sauvegarde: {e}")
            return False

    def _print_report(self, summary: Dict):
        print("\n" + "="*60)
        print("RAPPORT: STM Importer Gauche-Droite")
        print("="*60)
        if self.errors:
            print("\n[ERREURS]:")
            for error in self.errors:
                print(f"  - {error}")
            return
        filename = self._filename()
        if summary["status"] == "created":
            print(f"\n[OK] Nouveau Gauche-Droite cree: {filename}")
            print(f"   Ligne: {self.ligne}")
            print(f"   Direction: {self.direction}")
            print(f"   Parcours crees: {len(self.parcours)}")
        else:
            print(f"\n[OK] Fichier mis a jour: {filename}")
            print(f"   Ligne: {self.ligne}")
            print(f"   Direction: {self.direction}")
            print(f"   Total parcours: {len(self.parcours)}")
        if summary["changes"]:
            print(f"\n[CHANGEMENTS] ({len(summary['changes'])}):")
            for change in summary["changes"]:
                print(f"   - {change}")
        else:
            if summary["status"] != "created":
                print("\n[OK] Aucun changement detecte")
        print(f"\n[LOCALISATION] {self.GD_DIR}")
        print("="*60 + "\n")

def split_sections(raw_data: str) -> List[str]:
    """Decoupe l'entree en sections, une par en-tete Gauche-Droite."""
    pattern = re.compile(r'Gauche-Droite\s*/\s*\d+e?\s+(?:est|ouest|nord|sud)',
                         re.IGNORECASE)
    matches = list(pattern.finditer(raw_data))
    if not matches:
        return []
    sections = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_data)
        sections.append(raw_data[start:end])
    return sections

def main():
    arg_parser = argparse.ArgumentParser(
        description="Importe des donnees brutes Gauche-Droite (STM) depuis stdin "
                    "vers des fichiers gd<ligne>_<direction>.json.")
    arg_parser.add_argument("--json", action="store_true",
                            help="Affiche aussi le JSON complet sur stdout "
                                 "(par defaut: rapport seulement).")
    args = arg_parser.parse_args()

    raw_data = sys.stdin.read()
    sections = split_sections(raw_data) or [raw_data]
    results = []
    failed = False
    for section in sections:
        parser = GDParser(section)
        json_data = parser.parse()
        if json_data:
            results.append(json_data)
        else:
            failed = True
            print(json.dumps({"errors": parser.errors}, indent=2, ensure_ascii=False),
                  file=sys.stderr)
    if results and args.json:
        output = results if len(results) > 1 else results[0]
        print(json.dumps(output, indent=2, ensure_ascii=False))
    sys.exit(1 if failed or not results else 0)

if __name__ == "__main__":
    main()
