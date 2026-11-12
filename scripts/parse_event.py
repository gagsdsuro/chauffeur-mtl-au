#!/usr/bin/env python3
"""
Event Data Parser & Importer
Parses raw event text and generates/updates JSON files.
"""

import json
import re
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from chauffeur.journal import ecrire_bloc  # noqa: E402
from chauffeur.modeles import FichierEvenements, Evenement  # noqa: E402
from chauffeur.evenements import comparer_evenements  # noqa: E402
from chauffeur.registre_detours import synchroniser_evenements_ligne  # noqa: E402
from chauffeur.presentation_evenements import (  # noqa: E402
    formater_evenement_modifie, formater_evenement_retire,
)


# ---------------------------------------------------------------------------
# Mini-arbre DOM — pour parser le fragment HTML retourné par le portail employé
# ---------------------------------------------------------------------------

class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []
        self.parent = parent

    def cls(self):
        return self.attrs.get("class", "") or ""

    def text(self):
        out = []
        for c in self.children:
            out.append(c if isinstance(c, str) else c.text())
        return re.sub(r"\s+", " ", "".join(out)).strip()

    def find(self, tag, cls=None):
        for n in self.iter():
            if n.tag == tag and (cls is None or cls in n.cls().split()):
                return n
        return None

    def find_all(self, tag, cls=None, direct=False):
        src = self.children if direct else self.iter()
        return [n for n in src
                if isinstance(n, _Node) and n.tag == tag
                and (cls is None or cls in n.cls().split())]

    def iter(self):
        for c in self.children:
            if isinstance(c, _Node):
                yield c
                yield from c.iter()


_VOID = {"br", "hr", "img", "input", "meta", "link"}


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        if data.strip():
            self.cur.children.append(data)


def _build_dom(html: str) -> _Node:
    b = _TreeBuilder()
    b.feed(html)
    return b.root


def _lines_br(dd: _Node) -> list:
    """Découpe un <dd> en lignes en traitant les <br> comme séparateurs."""
    parts, buf = [], []
    for c in dd.children:
        if isinstance(c, _Node) and c.tag == "br":
            parts.append("".join(buf))
            buf = []
        elif isinstance(c, str):
            buf.append(c)
        else:
            buf.append(c.text())
    parts.append("".join(buf))
    return [unescape(p).strip() for p in "\n".join(parts).splitlines() if p.strip()]


# ---------------------------------------------------------------------------

class PortailEventParser:

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR = PROJECT_ROOT / "data"
    EVENTS_DIR = DATA_DIR / "Events"

    def __init__(self, raw_text: str, verbose: bool = True):
        self.raw_text = raw_text
        self.verbose = verbose
        self.events_dir = self.EVENTS_DIR
        self.ligne = None
        self.direction = None
        self.events = []
        self.errors = []
        self.warnings = []
        self.no_changes = False
        self.detours: list = []

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

    def _parse_arrets(self, arrets_text: str) -> List[Dict[str, str]]:
        """Comme parse_arrets() mais accepte les lignes sans code d'arrêt (id vide)."""
        if not arrets_text or not arrets_text.strip():
            return []
        arrets = []
        for line in arrets_text.split('\n'):
            line = re.sub(r'^\*\s*|^-\s*(?=\d)', '', line.strip())
            if not line:
                continue
            m = re.match(r'(\d+)\s*-\s*(.+)', line)
            if m:
                arrets.append({"id": m.group(1), "nom": m.group(2).strip()})
            else:
                arrets.append({"id": "", "nom": line})
        return arrets

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

        # Arrêts annulés : capture ligne-par-ligne jusqu'au prochain en-tête de
        # section (Description / Commentaire / Arrêt(s) ajouté). S'arrête net même
        # quand la section est vide — ex. « Détour sans annulation » où « Arrêt(s) »
        # est immédiatement suivi de « Description Gauche-Droite » — au lieu d'avaler
        # le bloc virage-par-virage et de produire des avertissements parasites.
        arrets_match = re.search(
            r'Arrêt\(s\)[^\S\n]*\n'
            r'((?:(?!\s*(?:Description|Commentaire|Arrêt\(s\)\s+ajouté))[^\n]*\n?)*)',
            event_text, re.IGNORECASE
        )
        event['arrets_annules'] = self.parse_arrets(arrets_match.group(1)) if arrets_match else []

        # Description Gauche-Droite
        desc_gd_match = re.search(
            r'Description\s+Gauche-Droite\s*\n?\s*(.+?)(?=\nCommentaire|\nArrêt\(s\)\s+ajouté|$)',
            event_text, re.IGNORECASE | re.DOTALL
        )
        if desc_gd_match:
            gd_lines = [l.strip() for l in desc_gd_match.group(1).strip().split('\n') if l.strip()]
            event['description_gd'] = '\n'.join(gd_lines) if gd_lines else None
        else:
            event['description_gd'] = None

        # Commentaire et arrêts ajoutés
        comment_match = re.search(r'Commentaire\s*\n?\s*(.+?)$', event_text, re.IGNORECASE | re.DOTALL)
        if comment_match:
            comment_full = comment_match.group(1).strip()
            ajoutes_split = re.split(r"Arrêt\(s\)\s+ajouté\(s\)\s*:", comment_full, flags=re.IGNORECASE)
            event['commentaire'] = ajoutes_split[0].strip() or None
            if len(ajoutes_split) > 1:
                event['arrets_ajoutes'] = self._parse_arrets(ajoutes_split[1])
            else:
                event['arrets_ajoutes'] = []
        else:
            event['commentaire'] = None
            ajoutes_match = re.search(r"Arrêt\(s\)\s+ajouté\(s\)\s*:\s*(.+?)$", event_text, re.IGNORECASE | re.DOTALL)
            event['arrets_ajoutes'] = self._parse_arrets(ajoutes_match.group(1)) if ajoutes_match else []

        # Validation champs obligatoires
        for field, label in [('evenement_id', 'ID'), ('titre', 'titre'), ('motif', 'motif'), ('effectif', 'effectif')]:
            if not event.get(field):
                self.errors.append(f"❌ Événement: {label} manquant")
                return None
        if not event.get('date_heure_debut'):
            self.errors.append(f"❌ Événement {event['evenement_id']}: date/heure début invalide")
            return None

        return event

    def _parse_portal_item(self, li: _Node) -> Optional[Dict]:
        """Extrait et normalise un événement depuis un <li> du fragment HTML portail."""
        ev: Dict = {}

        h3 = li.find("h3")
        parts = [p.strip() for p in (h3.text() if h3 else "").split(" - ", 2)]
        if len(parts) == 3:
            ev["evenement_id"] = parts[1]
            ev["titre"] = parts[2]
        else:
            self.errors.append("❌ En-tête d'événement non reconnu dans le HTML portail")
            return None

        for dl in li.find_all("dl", "on-off-canvas-panel-definition", direct=True):
            dt = dl.find("dt")
            dd = dl.find("dd")
            if not dt or not dd:
                continue
            terme = dt.text()

            if terme == "Motif":
                ev["motif"] = dd.text()
            elif terme.startswith("Date") and "début" in terme:
                ev["date_heure_debut"] = self.parse_date_time(dd.text())
            elif terme.startswith("Date") and "fin" in terme:
                v = dd.text()
                ev["date_heure_fin"] = None if v.lower().startswith("non") else self.parse_date_time(v)
            elif terme == "Effectif":
                ev["effectif"] = dd.text()
            elif terme.startswith("Arrêt") and "ajouté" not in terme.lower():
                arrets = []
                for item in dd.find_all("li", "on-off-canvas-panel-description-item"):
                    t = item.text()
                    m = re.match(r"(\d+)\s*-\s*(.+)", t)
                    arrets.append({"id": m.group(1), "nom": m.group(2).strip()} if m else {"id": "", "nom": t})
                ev["arrets_annules"] = arrets
            elif "Gauche-Droite" in terme:
                lines = _lines_br(dd)
                ev["description_gd"] = "\n".join(lines) if lines else None
            elif terme == "Commentaire":
                commentaire_raw = "\n".join(_lines_br(dd))
                split = re.split(r"Arrêt\(s\)\s+ajouté\(s\)\s*:", commentaire_raw, flags=re.IGNORECASE)
                ev["commentaire"] = split[0].strip() or None
                ev["arrets_ajoutes"] = self._parse_arrets(split[1]) if len(split) > 1 else []

        ev.setdefault("arrets_annules", [])
        ev.setdefault("arrets_ajoutes", [])
        ev.setdefault("description_gd", None)
        ev.setdefault("commentaire", None)

        for field, label in [("evenement_id", "ID"), ("titre", "titre"), ("motif", "motif"), ("effectif", "effectif")]:
            if not ev.get(field):
                self.errors.append(f"❌ Événement: {label} manquant")
                return None
        if not ev.get("date_heure_debut"):
            self.errors.append(f"❌ Événement {ev.get('evenement_id', '?')}: date/heure début invalide")
            return None

        return ev

    @classmethod
    def from_portal_json(cls, raw: str, ligne: str, direction: str,
                         verbose: bool = True) -> "PortailEventParser":
        """Construit un parser depuis la réponse brute du portail employé.

        Args:
            raw:       JSON brut : {"countDeviations": N, "html": "<fragment>"}.
            ligne:     Numéro de ligne (ex. "10").
            direction: Direction en minuscule (ex. "sud").
        """
        data = json.loads(raw)
        root = _build_dom(data.get("html", ""))

        instance = cls("", verbose=verbose)
        instance.ligne = ligne
        instance.direction = direction.lower()

        for li in root.find_all("li", "on-off-canvas-panel-item"):
            ev = instance._parse_portal_item(li)
            if ev:
                instance.events.append(ev)

        return instance

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
        """Input is authoritative: replaces the full list. Returns (new_list, changed).

        Un même evenement_id peut apparaître plusieurs fois (plages horaires distinctes).
        La comparaison se fait par groupe d'ID, pas événement par événement.
        """
        existing_detours = existing_data.get('detours', [])
        comparaison = comparer_evenements(existing_detours, self.events)

        # Événements retirés (ID entièrement absent de la nouvelle liste).
        # Chaque variante est détaillée : un même ID peut légitimement porter
        # plusieurs plages horaires ou types d'impact.
        for eid, old_evts, _ in comparaison["retires"]:
            if self.verbose:
                self.warnings.extend(formater_evenement_retire(e) for e in old_evts)
            else:
                self.warnings.append(f"🗑️ Événement {eid} retiré")

        # Événements modifiés (groupe différent pour le même ID)
        for eid, old_evts, new_evts in comparaison["modifies"]:
            if self.verbose:
                self.warnings.append(
                    formater_evenement_modifie(eid, old_evts, new_evts)
                )
            else:
                self.warnings.append(f"⚠️ Événement {eid} remplacé")

        changed = self.events != existing_detours
        return self.events, changed

    def to_fichier(self) -> FichierEvenements:
        """Retourne les évènements courants sous forme de FichierEvenements typé."""
        return FichierEvenements(
            ligne=self.ligne,
            direction=self.direction,
            detours=[Evenement.from_dict(e) for e in self.events],
        )

    def save_json(self) -> Tuple[bool, bool]:
        """Save events. Returns (success, changed)."""
        self.events_dir.mkdir(parents=True, exist_ok=True)
        existing = self.load_existing_events()
        merged_events, changed = self.merge_events(existing)

        if not changed:
            self.no_changes = True
            return True, False

        self.no_changes = False
        fichier = FichierEvenements(
            ligne=self.ligne,
            direction=self.direction,
            detours=[Evenement.from_dict(e) for e in merged_events],
        )
        filename = f"{self.ligne}_{self.direction}.json"
        filepath = self.events_dir / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(fichier.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.errors.append(f"❌ Erreur sauvegarde: {e}")
            return False, False
        # Détours que le pipeline ne sait pas ancrer seul (non bloquant) : à réviser
        # dans la page Détours. `events_dir.parent` = data/ (voisins : G-D, GTFS).
        self.detours = synchroniser_evenements_ligne(
            self.ligne, self.direction, base=self.events_dir.parent)
        return True, True

    def append_log(self, summary: str, log_dir: Path | None = None) -> None:
        """Sauvegarde le résumé en append dans data/log/parse_event.log."""
        ecrire_bloc("parse_event", summary, log_dir)

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
                lines.extend(f"  {part}" for part in w.splitlines())

        if self.detours:
            lines.append("")
            lines.append("[APPARIEMENT DÉTOURS]")
            lines.extend(f"  {m}" for m in self.detours)

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
        description="Importe des données brutes d'évènements du portail depuis stdin "
                    "vers des fichiers <ligne>_<direction>.json.")
    arg_parser.add_argument("--json", action="store_true",
                            help="Affiche aussi le JSON complet sur stdout "
                                 "(par défaut: rapport seulement).")
    arg_parser.add_argument("--no-verbose", dest="verbose", action="store_false",
                            help="Masque les détails des événements retirés/remplacés.")
    arg_parser.set_defaults(verbose=True)
    arg_parser.add_argument("--log", action="store_true",
                            help="Sauvegarde la sortie dans data/log/parse_event.log (append).")
    args = arg_parser.parse_args()

    raw_text = sys.stdin.read()

    sections = split_sections(raw_text) or [raw_text]
    results = []
    failed = False

    for section in sections:
        parser = PortailEventParser(section, verbose=args.verbose)
        success = parser.parse_all()

        if success:
            saved, _ = parser.save_json()
            if not saved:
                success = False

        summary = parser.get_summary()
        print(summary)
        if args.log:
            parser.append_log(summary)

        if success:
            results.append(parser.to_fichier().to_dict())
        else:
            failed = True

    if results and args.json:
        output = results if len(results) > 1 else results[0]
        print(json.dumps(output, indent=2, ensure_ascii=False))

    sys.exit(1 if failed or not results else 0)


if __name__ == "__main__":
    main()
