#!/usr/bin/env python3
"""
STM Event Data Parser & Importer
Parses raw STM event text and generates/updates JSON files.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional


class STMEventParser:

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR = PROJECT_ROOT / "data"
    EVENTS_DIR = DATA_DIR / "Events"

    def __init__(self, raw_text: str):
        self.raw_text = raw_text
        self.events_dir = self.EVENTS_DIR
        self.ligne = None
        self.direction = None
        self.events = []
        self.errors = []
        self.warnings = []
        self.no_changes = False

    def extract_ligne_direction(self) -> Tuple[Optional[str], Optional[str]]:
        pattern = r'(?:Détour|Évènement)s?\s*/\s*(\d+)\s+(Est|Ouest|Nord|Sud)'
        match = re.search(pattern, self.raw_text, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2).lower()
        pattern = r'[Ll]igne\s+(\d+)\s+(Est|Ouest|Nord|Sud)'
        match = re.search(pattern, self.raw_text, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2).lower()
        self.errors.append("❌ Impossible d'extraire la ligne et direction. Format attendu: 'Détour / 358 Est'")
        return None, None

    def parse_date_time(self, date_str: str) -> Optional[str]:
        if not date_str or date_str.lower().strip() == "non définie":
            return None
        try:
            dt = datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M")
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            self.errors.append(f"❌ Format de date invalide: '{date_str}'. Attendu: 'YYYY-MM-DD HH:MM'")
            return None

    def parse_arrets(self, arrets_text: str) -> List[Dict[str, str]]:
        if not arrets_text or not arrets_text.strip():
            return []
        arrets = []
        for line in arrets_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Strip bullet prefix: "* 57263 - ..." or "- 57263 - ..."
            line = re.sub(r'^\*\s*|^-\s*(?=\d)', '', line)
            match = re.match(r'(\d+)\s*-\s*(.+)', line)
            if match:
                arrets.append({"id": match.group(1), "nom": match.group(2).strip()})
            else:
                self.warnings.append(f"⚠️ Format d'arrêt non reconnu: '{line}'")
        return arrets

    def parse_event(self, event_text: str) -> Optional[Dict]:
        event = {}

        title_match = re.search(r'Évènement\s*-\s*(\d+)\s*-\s*(.+)', event_text, re.IGNORECASE)
        if not title_match:
            self.errors.append("❌ Format d'événement invalide: devrait commencer par 'Évènement - ID - Type'")
            return None

        event['evenement_id'] = title_match.group(1)
        event['titre'] = title_match.group(2).strip()

        def extract_field(label, stop_labels):
            """Extract field value — handles value on same line or next line."""
            pat = rf'{label}\s+(.+?)(?=\n(?:{stop_labels})|\n\n|$)'
            m = re.search(pat, event_text, re.IGNORECASE | re.DOTALL)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
            pat2 = rf'{label}\s*\n\s*(.+?)(?=\n(?:{stop_labels})|\n\n|$)'
            m2 = re.search(pat2, event_text, re.IGNORECASE | re.DOTALL)
            if m2:
                return m2.group(1).strip()
            return None

        event['motif'] = extract_field(r'Motif', r'Date|Effectif|Arrêt|Description|Commentaire')

        date_debut = extract_field(r'Date\s*/\s*heure début', r'Date|Effectif|Arrêt|Description|Commentaire')
        event['date_heure_debut'] = self.parse_date_time(date_debut)

        date_fin = extract_field(r'Date\s*/\s*heure de fin', r'Effectif|Arrêt|Description|Commentaire')
        event['date_heure_fin'] = self.parse_date_time(date_fin if date_fin else "non définie")

        event['effectif'] = extract_field(r'Effectif', r'Arrêt|Description|Commentaire')

        # Arrêts annulés
        arrets_match = re.search(
            r'Arrêt\(s\)\s*\n?((?:\s*\*[^\n]+\n?)+|.+?)(?=\nDescription|\nCommentaire|\nArrêt\(s\)\s+ajouté|$)',
            event_text, re.IGNORECASE | re.DOTALL
        )
        event['arrets_annules'] = self.parse_arrets(arrets_match.group(1)) if arrets_match else []

        # Description Gauche-Droite
        desc_gd_match = re.search(
            r'Description\s+Gauche-Droite\s*\n?\s*(.+?)(?=\nCommentaire|\nArrêt\(s\)\s+ajouté|$)',
            event_text, re.IGNORECASE | re.DOTALL
        )
        if desc_gd_match:
            gd_lines = [l.strip() for l in desc_gd_match.group(1).strip().split('\n') if l.strip()]
            event['description_gd'] = ' '.join(gd_lines) if gd_lines else None
        else:
            event['description_gd'] = None

        # Commentaire et arrêts ajoutés
        comment_match = re.search(r'Commentaire\s*\n?\s*(.+?)$', event_text, re.IGNORECASE | re.DOTALL)
        if comment_match:
            comment_full = comment_match.group(1).strip()
            ajoutes_split = re.split(r"Arrêt\(s\)\s+ajouté\(s\)\s*:", comment_full, flags=re.IGNORECASE)
            event['commentaire'] = ajoutes_split[0].strip() or None
            if len(ajoutes_split) > 1:
                event['arrets_ajoutes'] = [l.strip().lstrip('*').strip() for l in ajoutes_split[1].strip().split('\n') if l.strip()]
            else:
                event['arrets_ajoutes'] = []
        else:
            event['commentaire'] = None
            ajoutes_match = re.search(r"Arrêt\(s\)\s+ajouté\(s\)\s*:\s*(.+?)$", event_text, re.IGNORECASE | re.DOTALL)
            event['arrets_ajoutes'] = [l.strip().lstrip('*').strip() for l in ajoutes_match.group(1).strip().split('\n') if l.strip()] if ajoutes_match else []

        # Validation champs obligatoires
        for field, label in [('evenement_id', 'ID'), ('titre', 'titre'), ('motif', 'motif'), ('effectif', 'effectif')]:
            if not event.get(field):
                self.errors.append(f"❌ Événement: {label} manquant")
                return None
        if not event.get('date_heure_debut'):
            self.errors.append(f"❌ Événement {event['evenement_id']}: date/heure début invalide")
            return None

        return event

    def parse_all(self) -> bool:
        self.ligne, self.direction = self.extract_ligne_direction()
        if not self.ligne or not self.direction:
            return False

        # Split by event blocks — handles numbered "1. Évènement" and plain "Évènement"
        event_blocks = re.split(r'\n\s*(?:\d+\.\s*)?(?=Évènement\s*-)', self.raw_text)

        for block in event_blocks:
            if 'Évènement' not in block:
                continue
            event = self.parse_event(block)
            if event:
                self.events.append(event)

        if not self.events:
            self.errors.append("❌ Aucun événement trouvé dans le texte")
            return False

        return len(self.errors) == 0

    def load_existing_events(self) -> Dict:
        filename = f"{self.ligne}_{self.direction}.json"
        filepath = self.events_dir / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.warnings.append(f"⚠️ Erreur lecture fichier existant: {e}")
        return {"ligne": self.ligne, "direction": self.direction, "detours": []}

    def merge_events(self, existing_data: Dict) -> Tuple[List[Dict], bool]:
        """Input is authoritative: replaces the full list. Returns (new_list, changed)."""
        existing_detours = existing_data.get('detours', [])
        existing_ids = {e['evenement_id']: e for e in existing_detours}
        new_ids = {e['evenement_id'] for e in self.events}

        for old_event in existing_detours:
            if old_event['evenement_id'] not in new_ids:
                self.warnings.append(f"🗑️ Événement {old_event['evenement_id']} retiré")

        for new_event in self.events:
            eid = new_event['evenement_id']
            if eid in existing_ids and existing_ids[eid] != new_event:
                self.warnings.append(f"⚠️ Événement {eid} remplacé")

        changed = self.events != existing_detours
        return self.events, changed

    def save_json(self) -> Tuple[bool, bool]:
        """Save events. Returns (success, changed)."""
        self.events_dir.mkdir(parents=True, exist_ok=True)
        existing = self.load_existing_events()
        merged_events, changed = self.merge_events(existing)

        if not changed:
            self.no_changes = True
            return True, False

        self.no_changes = False
        output = {"ligne": self.ligne, "direction": self.direction, "detours": merged_events}
        filename = f"{self.ligne}_{self.direction}.json"
        filepath = self.events_dir / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            return True, True
        except Exception as e:
            self.errors.append(f"❌ Erreur sauvegarde: {e}")
            return False, False

    def get_summary(self) -> str:
        lines = []

        if self.errors:
            lines.append("❌ Erreurs détectées - données non sauvegardées:")
            for error in self.errors:
                lines.append(f"  {error}")
            return "\n".join(lines)

        suffix = " — aucun changement" if self.no_changes else ""
        lines.append(f"✅ Ligne {self.ligne.upper()} {self.direction.capitalize()} - {len(self.events)} événement(s) traité(s){suffix}")

        for event in self.events:
            arrets_info = ""
            if event.get('arrets_annules'):
                stop_ids = ", ".join(s['id'] for s in event['arrets_annules'])
                arrets_info = f" ({stop_ids})"
            if event.get('arrets_ajoutes'):
                arrets_info += f" [+{len(event['arrets_ajoutes'])} ajouté(s)]"
            lines.append(f"  • {event['evenement_id']} — {event['titre']}{arrets_info}")

        if self.warnings:
            lines.append("")
            for w in self.warnings:
                lines.append(f"  {w}")

        filename = f"{self.ligne}_{self.direction}.json"
        if self.no_changes:
            lines.append(f"\n📁 Inchangé: data/Events/{filename}")
        else:
            lines.append(f"\n📁 Sauvegardé: data/Events/{filename}")

        return "\n".join(lines)


def split_sections(raw_text: str) -> List[str]:
    """Découpe l'entrée en sections, une par en-tête Détours/Évènements / <ligne> <direction>."""
    pattern = re.compile(
        r'(?:Détour|Évènement)s?\s*/\s*\d+\s+(?:Est|Ouest|Nord|Sud)',
        re.IGNORECASE
    )
    matches = list(pattern.finditer(raw_text))
    if not matches:
        return []
    sections = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        sections.append(raw_text[start:end])
    return sections


def main():
    import argparse
    arg_parser = argparse.ArgumentParser(
        description="Importe des données brutes d'évènements STM depuis stdin "
                    "vers des fichiers <ligne>_<direction>.json.")
    arg_parser.add_argument("--json", action="store_true",
                            help="Affiche aussi le JSON complet sur stdout "
                                 "(par défaut: rapport seulement).")
    args = arg_parser.parse_args()

    raw_text = sys.stdin.read()

    sections = split_sections(raw_text) or [raw_text]
    results = []
    failed = False

    for section in sections:
        parser = STMEventParser(section)
        success = parser.parse_all()

        if success:
            saved, _ = parser.save_json()
            if not saved:
                success = False

        print(parser.get_summary())

        if success:
            results.append({"ligne": parser.ligne, "direction": parser.direction, "detours": parser.events})
        else:
            failed = True

    if results and args.json:
        output = results if len(results) > 1 else results[0]
        print(json.dumps(output, indent=2, ensure_ascii=False))

    sys.exit(1 if failed or not results else 0)


if __name__ == "__main__":
    main()
