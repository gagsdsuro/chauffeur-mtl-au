#!/usr/bin/env python3
"""
parse_journee.py — Importe le texte brut du « Détail de ma journée » STM
                   vers data/journees/journee-YYYY-MM-DD.json

Usage :
    python3 scripts/parse_journee.py --date 2026-06-17 < raw.txt
    python3 scripts/parse_journee.py --json < raw.txt
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chauffeur.modeles import Journee  # noqa: E402


MOIS_FR = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12",
}

SEGMENT_RE    = re.compile(r'^(\d+\w*)\s+(Est|Ouest|Nord|Sud)$', re.IGNORECASE)
ID_RE         = re.compile(r'^ID\s+(\d+)$', re.IGNORECASE)
NOTE_RE       = re.compile(r'^\d+\s*note\(s\)\s+de\s+voyages?\s*:', re.IGNORECASE)
RELEVE_RE     = re.compile(r'^Je relève\s*:', re.IGNORECASE)
RELEVE_PAR_RE = re.compile(r'^Je suis relevé par\s*:', re.IGNORECASE)
PERSONNE_RE   = re.compile(r'^(.+?)\s*-\s*(\d+)$')


def _date_from_text(text: str) -> str | None:
    m = re.search(r'Mis à jour le\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
    if not m:
        return None
    jour, mois, annee = m.group(1), m.group(2).lower(), m.group(3)
    mois_num = MOIS_FR.get(mois)
    return f"{annee}-{mois_num}-{int(jour):02d}" if mois_num else None


def _day_offset_from_text(text: str) -> int:
    """Retourne +1 si 'Demain', -1 si 'Hier', 0 sinon (la journée affichée ≠ date de mise à jour)."""
    m = re.search(r'(Hier|Demain)\d{4,6}', text)
    if not m:
        return 0
    return -1 if m.group(1) == "Hier" else 1


def _split_stop_time(line: str) -> tuple[str, str | None]:
    """Sépare 'Montgomery / Sherbrooke13:49' → ('Montgomery / Sherbrooke', '13:49')."""
    m = re.search(r'(\d{1,2}:\d{2})$', line)
    if m:
        return line[:m.start()].strip(), m.group(1)
    return line.strip(), None


class JourneeParser:

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR     = PROJECT_ROOT / "data"
    JOURNEES_DIR = DATA_DIR / "journees"

    def __init__(self, raw_text: str, date_str: str | None = None):
        self.raw_text = raw_text.replace('\r\n', '\n').replace('\r', '\n')
        self.errors   = []
        if date_str:
            self.date_str = date_str
        else:
            base = _date_from_text(self.raw_text)
            if base:
                offset = _day_offset_from_text(self.raw_text)
                self.date_str = (
                    (datetime.fromisoformat(base) + timedelta(days=offset)).strftime("%Y-%m-%d")
                    if offset else base
                )
            else:
                self.date_str = datetime.now().strftime("%Y-%m-%d")

    # ── En-tête ────────────────────────────────────────────────────────────────

    def _parse_header(self) -> dict:
        t = self.raw_text
        h = {}

        m = re.search(r"(?:Hier|Aujourd'hui)?(\d{4,6})\s*-\s*([\w ,-]+?)(?=\n|$)", t)
        if m:
            h["employe_id"] = m.group(1)
            h["garage"]     = m.group(2).strip()

        m = re.search(r'Journée(\d+)', t)
        if m:
            h["journee_numero"] = int(m.group(1))

        m = re.search(r'Temps travaillé(\d+:\d{2})', t)
        if m:
            h["temps_travaille"] = m.group(1)

        m = re.search(r'Temps supplémentaire(\d+:\d{2})', t)
        if m:
            h["temps_supplementaire"] = m.group(1)

        m = re.search(
            r'Mis à jour le\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{2}:\d{2})',
            t, re.IGNORECASE
        )
        if m:
            mois_num = MOIS_FR.get(m.group(2).lower())
            if mois_num:
                h["mis_a_jour"] = f"{m.group(3)}-{mois_num}-{int(m.group(1)):02d}T{m.group(4)}"

        return h

    # ── Sommaires ──────────────────────────────────────────────────────────────

    def _parse_sommaires(self) -> list[dict]:
        """
        Chaque ligne Sommaire ressemble à (labels et valeurs collés) :
            Sommaire24 - 1538013--3:18Horaire   ← bus 38013
            Sommaire24 - 02--4:12Horaire        ← pas encore de bus (--)
            Sommaire136 - 2538023631:44Horaire  ← bus 38023, emplacement 63
                                                   à la place du "--" habituel
        Le séparateur avant la durée est soit "--" (littéral, emplacement
        inconnu), soit un numéro d'emplacement du bus dans le garage (1-2
        chiffres, non retenu — sans utilité pour l'application).
        Suivi de : Prise / <heure> / Lieu / <code> / Début / <heure> / Fin / <heure> / Lieu / <code>
        """
        sommaires = []
        lines = [l for l in self.raw_text.split('\n')]

        for i, raw_line in enumerate(lines):
            line = raw_line.strip()
            # \d{1,3} pour le numéro de pièce (01, 02, … 15, etc.)
            # (\d{5})? pour le numéro d'autobus (5 chiffres, optionnel)
            # (?:--|\d{2}) pour le séparateur : "--" littéral, ou numéro
            # d'emplacement (même largeur que "--", 2 caractères)
            m = re.match(
                r'^Sommaire(\d+\s*-\s*\d{1,3})(\d{5})?(?:--|\d{2})(\d{1,2}:\d{2})Horaire$',
                line
            )
            if not m:
                continue

            piece_id    = re.sub(r'\s+', '', m.group(1))   # "24-15"
            num_autobus = m.group(2) or None
            duree       = m.group(3)

            s = {"id": piece_id, "numero_autobus": num_autobus, "duree": duree}

            # Extrait le bloc Prise/Lieu/Début/Fin/Lieu qui suit
            sched_keys   = ["prise",  "lieu_prise", "debut",  "fin",  "lieu_fin"]
            sched_labels = ["Prise",  "Lieu",       "Début",  "Fin",  "Lieu"]
            ki, j = 0, i + 1
            while j < len(lines) and ki < len(sched_labels):
                l = lines[j].strip()
                if not l:
                    j += 1
                    continue
                # Arrêter si on tombe sur le prochain Sommaire ou un Détails
                if l.startswith("Sommaire") or l.startswith("Détails"):
                    break
                if l == sched_labels[ki]:
                    j += 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines):
                        s[sched_keys[ki]] = lines[j].strip()
                        j += 1
                    ki += 1
                else:
                    j += 1

            sommaires.append(s)

        return sommaires

    # ── Détails ────────────────────────────────────────────────────────────────

    def _parse_piece_block(self, block_lines: list[str]) -> tuple[list[dict], dict | None]:
        """Parse les trajets et la relève à partir des lignes d'un bloc de pièce."""
        trajets: list[dict] = []
        releve: dict = {}
        i = 0

        while i < len(block_lines):
            line = block_lines[i]

            # ── Relève ──────────────────────────────────────────────────────
            if RELEVE_RE.match(line):
                i += 1
                if i < len(block_lines):
                    pm = PERSONNE_RE.match(block_lines[i])
                    if pm:
                        releve["je_releve"] = {
                            "nom": pm.group(1).strip(), "matricule": pm.group(2)
                        }
                    i += 1
                continue

            if RELEVE_PAR_RE.match(line):
                i += 1
                if i < len(block_lines):
                    pm = PERSONNE_RE.match(block_lines[i])
                    if pm:
                        releve["je_suis_releve_par"] = {
                            "nom": pm.group(1).strip(), "matricule": pm.group(2)
                        }
                    i += 1
                continue

            # ── Haut-le-pied / Sortie (garage→service) / Entrée (service→garage) ──
            hlp_type = None
            if line.startswith("Haut-le-pied"):
                hlp_type = "haut_le_pied"
            elif line.startswith("Sortie"):
                hlp_type = "sortie"
            elif line.startswith("Entrée"):
                hlp_type = "entree"
            if hlp_type is not None:
                trajet: dict = {
                    "type": hlp_type, "ligne": None,
                    "direction": None, "id_parcours": None, "detour": False,
                }
                i += 1
                if i < len(block_lines) and "Départ et arrivé" in block_lines[i]:
                    i += 1
                if i < len(block_lines):
                    arret, heure = _split_stop_time(block_lines[i])
                    trajet["depart"] = {"arret": arret, "heure": heure}
                    i += 1
                if i < len(block_lines):
                    arret, heure = _split_stop_time(block_lines[i])
                    trajet["arrivee"] = {"arret": arret, "heure": heure}
                    i += 1
                trajets.append(trajet)
                continue

            # ── Segment de service "24 Ouest" / "85 Est" ─────────────────────
            sm = SEGMENT_RE.match(line)
            if sm:
                trajet = {
                    "type":        "service",
                    "ligne":       sm.group(1),
                    "direction":   sm.group(2).lower(),
                    "id_parcours": None,
                    "detour":      False,
                }
                i += 1

                if i < len(block_lines):
                    idm = ID_RE.match(block_lines[i])
                    if idm:
                        trajet["id_parcours"] = int(idm.group(1))
                        i += 1

                if i < len(block_lines) and "Départ et arrivé" in block_lines[i]:
                    i += 1

                if i < len(block_lines):
                    arret, heure = _split_stop_time(block_lines[i])
                    trajet["depart"] = {"arret": arret, "heure": heure}
                    i += 1

                if i < len(block_lines):
                    arret, heure = _split_stop_time(block_lines[i])
                    trajet["arrivee"] = {"arret": arret, "heure": heure}
                    i += 1

                if i < len(block_lines) and "Informations supplémentaires" in block_lines[i]:
                    i += 1
                    if i < len(block_lines) and "Détour" in block_lines[i]:
                        trajet["detour"] = True
                        i += 1

                # Notes de voyage (ex : "1note(s) de voyages :")
                if i < len(block_lines) and NOTE_RE.match(block_lines[i]):
                    i += 1
                    notes: list[str] = []
                    while i < len(block_lines):
                        nl = block_lines[i]
                        if (SEGMENT_RE.match(nl) or nl.startswith("Haut-le-pied")
                                or RELEVE_RE.match(nl) or RELEVE_PAR_RE.match(nl)):
                            break
                        if nl:
                            notes.append(nl)
                        i += 1
                    if notes:
                        trajet["notes_voyage"] = notes

                trajets.append(trajet)
                continue

            i += 1

        return trajets, releve or None

    def _parse_details(self) -> dict[str, tuple[list[dict], dict | None]]:
        lines = self.raw_text.split('\n')
        markers: list[tuple[int, str]] = []

        for idx, line in enumerate(lines):
            m = re.match(r'^Détails\s+(\d+\s*-\s*\d+)\s*$', line.strip(), re.IGNORECASE)
            if m:
                markers.append((idx, re.sub(r'\s+', '', m.group(1))))

        details: dict[str, tuple] = {}
        for k, (start_idx, piece_id) in enumerate(markers):
            end_idx = markers[k + 1][0] if k + 1 < len(markers) else len(lines)
            block   = [l.strip() for l in lines[start_idx + 1:end_idx] if l.strip()]
            trajets, releve = self._parse_piece_block(block)
            details[piece_id] = (trajets, releve)

        return details

    # ── Assemblage ─────────────────────────────────────────────────────────────

    def parse(self) -> Journee | None:
        header = self._parse_header()
        if not header.get("employe_id"):
            self.errors.append("❌ Impossible d'extraire l'identifiant employé")
            return None

        sommaires = self._parse_sommaires()
        if not sommaires:
            self.errors.append("❌ Aucun sommaire (Sommaire…Horaire) trouvé")
            return None

        details = self._parse_details()

        pieces = []
        for s in sommaires:
            pid = s["id"]
            traj, releve = details.get(pid, ([], None))
            pieces.append({
                "id":              pid,
                "numero_autobus":  s.get("numero_autobus"),
                "duree":           s.get("duree"),
                "prise":           s.get("prise"),
                "lieu_prise":      s.get("lieu_prise"),
                "debut":           s.get("debut"),
                "fin":             s.get("fin"),
                "lieu_fin":        s.get("lieu_fin"),
                "releve":          releve,
                "trajets":         traj,
            })

        raw = {
            "date":                 self.date_str,
            "employe_id":           header.get("employe_id"),
            "garage":               header.get("garage"),
            "journee_numero":       header.get("journee_numero"),
            "temps_travaille":      header.get("temps_travaille"),
            "temps_supplementaire": header.get("temps_supplementaire"),
            "mis_a_jour":           header.get("mis_a_jour"),
            "pieces":               pieces,
        }
        return Journee.from_dict(raw)

    def save(self, journee: Journee) -> Path:
        self.JOURNEES_DIR.mkdir(parents=True, exist_ok=True)
        out = self.JOURNEES_DIR / f"journee-{self.date_str}.json"
        out.write_text(json.dumps(journee.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return out

    def get_summary(self, journee: Journee | None = None, saved_path: Path | None = None) -> str:
        if self.errors:
            return "❌ Erreurs :\n" + "\n".join(f"  {e}" for e in self.errors)

        lines = [f"✅ Journée du {self.date_str}"]
        if journee:
            lines.append(
                f"   Employé {journee.employe_id} — {journee.garage or '?'} "
                f"| Journée n°{journee.journee_numero or '?'} "
                f"| {journee.temps_travaille or '?'} travaillé"
            )
            from chauffeur.modeles import TrajetService, TrajetHlp
            for p in journee.pieces:
                bus   = p.numero_autobus or "–"
                ntraj = sum(1 for t in p.trajets if isinstance(t, TrajetService))
                nhlp  = sum(1 for t in p.trajets if isinstance(t, TrajetHlp))
                lines.append(
                    f"   Pièce {p.id} : bus {bus}, "
                    f"{p.debut} → {p.fin}, "
                    f"{ntraj} voyage(s), {nhlp} HLP"
                )
        if saved_path:
            lines.append(f"\n📁 Sauvegardé : data/journees/{saved_path.name}")
        return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Importe le texte brut du « Détail de ma journée » STM "
                    "vers data/journees/journee-YYYY-MM-DD.json."
    )
    ap.add_argument("--date", help="Date de la journée (YYYY-MM-DD). "
                    "Déduit du texte si absent, sinon date du jour.")
    ap.add_argument("--json", action="store_true",
                    help="Affiche le JSON complet sur stdout.")
    args = ap.parse_args()

    raw    = sys.stdin.read()
    parser = JourneeParser(raw, date_str=args.date)
    result = parser.parse()

    if result:
        saved = parser.save(result)
        print(parser.get_summary(result, saved))
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(parser.get_summary())
        sys.exit(1)


if __name__ == "__main__":
    main()
