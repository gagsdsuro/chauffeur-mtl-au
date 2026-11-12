#!/usr/bin/env python3
"""
parse_journee.py — Importe le texte brut du « Détail de ma journée »
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
from chauffeur.depots import (  # noqa: E402
    JOURNEES_DIR as DEPOTS_JOURNEES_DIR, sauvegarder_journee,
)
from chauffeur.calendrier import (  # noqa: E402
    dossier_calendrier, ecrire_calendrier_sans_echec, lignes_calendrier,
)
from chauffeur.journal import ecrire_bloc  # noqa: E402
from chauffeur.journee import parser_sommaire_absence  # noqa: E402
from chauffeur.modeles import Journee  # noqa: E402
from chauffeur.portail import texte_visible_html  # noqa: E402


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
PERSONNE_SANS_MATRICULE_RE = re.compile(r'^(.+?)\s*-\s*$')


def _attributs_balise(balise: str) -> dict[str, str]:
    return {
        nom.lower(): valeur1 or valeur2
        for nom, valeur1, valeur2 in re.findall(
            r'([\w-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', balise
        )
    }


def _ancres_sommaires(html: str) -> list[str]:
    ancres = []
    for balise in re.findall(r"<a\b[^>]*>", html or "", re.IGNORECASE):
        attrs = _attributs_balise(balise)
        classes = attrs.get("class", "").split()
        href = attrs.get("href", "")
        if "work-piece-summary-link" in classes and href.startswith("#"):
            ancres.append(href[1:])
    return ancres


def _ancres_details(html: str) -> list[str]:
    ancres = []
    for balise in re.findall(r"<h2\b[^>]*>", html or "", re.IGNORECASE):
        attrs = _attributs_balise(balise)
        if "trips-item-heading" in attrs.get("class", "").split() and attrs.get("id"):
            ancres.append(attrs["id"])
    return ancres


def _date_from_text(text: str) -> str | None:
    m = re.search(r'Mis à jour le\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
    if not m:
        return None
    jour, mois, annee = m.group(1), m.group(2).lower(), m.group(3)
    mois_num = MOIS_FR.get(mois)
    return f"{annee}-{mois_num}-{int(jour):02d}" if mois_num else None


def _day_offset_from_text(text: str) -> int:
    """Retourne +1 si 'Demain', -1 si 'Hier', 0 sinon (la journée affichée ≠ date de mise à jour)."""
    m = re.search(r'(Hier|Demain)\s*\d{4,6}', text)
    if not m:
        return 0
    return -1 if m.group(1) == "Hier" else 1


def _split_stop_time(line: str) -> tuple[str, str | None]:
    """Sépare 'Montgomery / Sherbrooke13:49' → ('Montgomery / Sherbrooke', '13:49')."""
    m = re.search(r'(\d{1,2}:\d{2})$', line)
    if m:
        return line[:m.start()].strip(), m.group(1)
    return line.strip(), None


def _lire_arret(block_lines: list[str], index: int) -> tuple[dict, int]:
    """Lit un arrêt dont l'heure peut être collée ou sur la ligne suivante."""
    arret, heure = _split_stop_time(block_lines[index])
    index += 1
    if heure is None and index < len(block_lines):
        suivant = block_lines[index].strip()
        if re.fullmatch(r"\d{1,2}:\d{2}", suivant):
            heure = suivant
            index += 1
    return {"arret": arret, "heure": heure}, index


def _lire_personne(block_lines: list[str], index: int) -> tuple[dict | None, int]:
    """Lit « Nom - matricule », même si le HTML sépare ses trois parties."""
    morceaux: list[str] = []
    while index < len(block_lines):
        ligne = block_lines[index].strip()
        if (
            RELEVE_RE.match(ligne)
            or RELEVE_PAR_RE.match(ligne)
            or SEGMENT_RE.match(ligne)
            or ligne.startswith(("Détails", "Haut-le-pied", "Sortie", "Entrée"))
        ):
            break

        morceaux.append(ligne)
        index += 1
        personne = PERSONNE_RE.match(" ".join(morceaux))
        if personne:
            return {
                "nom": personne.group(1).strip(),
                "matricule": personne.group(2),
            }, index
        # Le portail utilise aussi « Relève à confirmer - ». Il faut attendre
        # de savoir si la ligne suivante contient un matricule séparé avant de
        # conclure qu'il est réellement absent.
        sans_matricule = PERSONNE_SANS_MATRICULE_RE.match(" ".join(morceaux))
        prochain_est_matricule = (
            index < len(block_lines)
            and bool(re.fullmatch(r"\d+", block_lines[index].strip()))
        )
        if sans_matricule and not prochain_est_matricule:
            return {
                "nom": sans_matricule.group(1).strip(),
                "matricule": "",
            }, index

    return None, index


class JourneeParser:

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR     = PROJECT_ROOT / "data"
    JOURNEES_DIR = DEPOTS_JOURNEES_DIR

    def __init__(self, raw_text: str, date_str: str | None = None):
        self.raw_text = raw_text.replace('\r\n', '\n').replace('\r', '\n')
        self.errors   = []
        self.calendrier: list[Path] = []
        self.erreur_calendrier = ""
        self._ancres_sommaire: list[str] = []
        self._ancres_detail: list[str] = []
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

    @classmethod
    def from_portal_json(cls, payload: dict, date_str: str) -> "JourneeParser":
        """Construit le parseur depuis la réponse JSON de `/resume-journee`."""
        if not isinstance(payload, dict):
            parser = cls("", date_str=date_str)
            parser.errors.append("❌ Réponse portail invalide")
            return parser
        journee_html = payload.get("journeeHtml")
        voyages_html = payload.get("voyagesHtml")
        if not isinstance(journee_html, str) or not isinstance(voyages_html, str):
            parser = cls("", date_str=date_str)
            parser.errors.append("❌ Blocs HTML de la journée introuvables")
            return parser
        texte = texte_visible_html(journee_html) + "\n" + texte_visible_html(voyages_html)
        parser = cls(texte, date_str=date_str)
        parser._ancres_sommaire = _ancres_sommaires(journee_html)
        parser._ancres_detail = _ancres_details(voyages_html)
        if payload.get("date") != date_str:
            parser.errors.append(
                f"❌ Date retournée inattendue : {payload.get('date')!r}, attendu {date_str}"
            )
        return parser

    # ── En-tête ────────────────────────────────────────────────────────────────

    def _parse_header(self) -> dict:
        t = self.raw_text
        h = {}

        m = re.search(
            r"(?:Hier|Aujourd'hui|Demain)?\s*(\d{4,6})\s*-\s*([\w ,-]+?)(?=\n|$)",
            t,
        )
        if m:
            h["garage_id"] = m.group(1)
            h["garage"]    = m.group(2).strip()

        m = re.search(r'Journée\s*(\d+)', t)
        if m:
            h["journee_numero"] = int(m.group(1))

        m = re.search(r'Temps travaillé\s*(\d+:\d{2})', t)
        if m:
            h["temps_travaille"] = m.group(1)

        m = re.search(r'Temps supplémentaire\s*(\d+:\d{2})', t)
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
            Sommaire24 - 1538013--3:18Horaire    ← bus 38013
            Sommaire24 - 02--4:12Horaire         ← pas encore de bus ("--" combiné)
            Sommaire769 - 01----7:02Horaire      ← pas encore de bus ("--" bus + "--" emplacement)
            Sommaire136 - 2538023631:44Horaire   ← bus 38023, emplacement 63
                                                    à la place du "--" habituel
        Le numéro d'autobus (5 chiffres) est soit présent, soit remplacé par
        un "--" littéral (format observé depuis juillet 2026). Il est suivi
        du séparateur avant la durée : "--" (littéral, emplacement inconnu)
        ou un numéro d'emplacement du bus dans le garage (2 chiffres, non
        retenu — sans utilité pour l'application).
        Suivi de : Prise / <heure> / Lieu / <code> / Début / <heure> / Fin / <heure> / Lieu / <code>
        """
        sommaires = []
        lines = [l for l in self.raw_text.split('\n')]

        i = 0
        while i < len(lines):
            raw_line = lines[i]
            line = raw_line.strip()
            if not line.startswith("Sommaire"):
                i += 1
                continue

            # Le HTML et Firefox séparent parfois Sommaire, identifiant, bus,
            # durée, Continu et Horaire sur plusieurs lignes.
            morceaux = [line]
            fin_entete = i
            while "Horaire" not in "".join(morceaux) and fin_entete + 1 < len(lines):
                prochain = lines[fin_entete + 1].strip()
                if prochain.startswith("Sommaire") or prochain.startswith("Détails"):
                    break
                fin_entete += 1
                if prochain:
                    morceaux.append(prochain)
            entete = "".join(morceaux)
            if re.match(r"^Sommaire\s*Absence", entete, re.IGNORECASE):
                j = fin_entete + 1
                while j < len(lines) and not lines[j].strip().startswith(("Sommaire", "Détails")):
                    j += 1
                try:
                    s = parser_sommaire_absence(entete, lines[fin_entete + 1:j])
                except ValueError as exc:
                    self.errors.append(f"❌ {exc}")
                    return []
                if len(sommaires) < len(self._ancres_sommaire):
                    s["_ancre"] = self._ancres_sommaire[len(sommaires)]
                sommaires.append(s)
                i = j
                continue
            # \d{1,3} pour le numéro de pièce (01, 02, … 15, etc.)
            # (?:(\d{5})|--)? pour le numéro d'autobus : 5 chiffres, ou "--"
            # littéral si pas encore assigné (optionnel dans les deux cas)
            # (?:--|\d{2}) pour le séparateur : "--" littéral, ou numéro
            # d'emplacement (même largeur que "--", 2 caractères)
            m = re.match(
                r'^Sommaire(\d+\s*-\s*\d{1,3})(?:(\d{5})|--)?'
                r'(?:--|\d{2})(\d{1,2}:\d{2})(Continu)?Horaire$',
                entete,
                re.IGNORECASE,
            )
            if not m:
                i = fin_entete + 1
                continue

            piece_id    = re.sub(r'\s+', '', m.group(1))   # "24-15"
            num_autobus = m.group(2) or None
            duree       = m.group(3)

            s = {
                "id": piece_id,
                "type_horaire": "continu" if m.group(4) else "horaire",
                "numero_autobus": num_autobus,
                "duree": duree,
            }
            if len(sommaires) < len(self._ancres_sommaire):
                s["_ancre"] = self._ancres_sommaire[len(sommaires)]

            # Extrait le bloc Prise/Lieu/Début/Fin/Lieu qui suit
            sched_keys   = ["prise",  "lieu_prise", "debut",  "fin",  "lieu_fin"]
            sched_labels = ["Prise",  "Lieu",       "Début",  "Fin",  "Lieu"]
            ki, j = 0, fin_entete + 1
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
            i = max(j, fin_entete + 1)

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
                personne, i = _lire_personne(block_lines, i + 1)
                if personne:
                    releve["je_releve"] = personne
                continue

            if RELEVE_PAR_RE.match(line):
                personne, i = _lire_personne(block_lines, i + 1)
                if personne:
                    releve["je_suis_releve_par"] = personne
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
                # Le portail insère parfois les instructions du G-D (ex.
                # « 53753 - [V] Pierre-De Coubertin, … ») entre l'en-tête
                # et « Départ et arrivé : ». On avance jusqu'au libellé pour
                # que l'import automatique et le collage manuel donnent les
                # mêmes heures début et fin. Sans le libellé, aucun arrêt.
                while (
                    i < len(block_lines)
                    and "Départ et arrivé" not in block_lines[i]
                ):
                    i += 1
                if i < len(block_lines):
                    i += 1
                if i < len(block_lines):
                    trajet["depart"], i = _lire_arret(block_lines, i)
                if i < len(block_lines):
                    trajet["arrivee"], i = _lire_arret(block_lines, i)
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
                    trajet["depart"], i = _lire_arret(block_lines, i)

                if i < len(block_lines):
                    trajet["arrivee"], i = _lire_arret(block_lines, i)

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

    def _parse_details(self) -> dict[tuple[str, object], tuple[list[dict], dict | None]]:
        lines = self.raw_text.split('\n')
        markers: list[tuple[int, str]] = []

        for idx, line in enumerate(lines):
            m = re.match(r'^Détails\s+(Absence|\d+\s*-\s*\d+)\s*$', line.strip(), re.IGNORECASE)
            if m:
                pid = re.sub(r'\s+', '', m.group(1))
                markers.append((idx, "Absence" if pid.lower() == "absence" else pid))

        details: dict[tuple[str, int], tuple] = {}
        occurrences: dict[str, int] = {}
        for k, (start_idx, piece_id) in enumerate(markers):
            end_idx = markers[k + 1][0] if k + 1 < len(markers) else len(lines)
            block   = [l.strip() for l in lines[start_idx + 1:end_idx] if l.strip()]
            trajets, releve = self._parse_piece_block(block)
            occurrence = occurrences.get(piece_id, 0)
            details[(piece_id, occurrence)] = (trajets, releve)
            if k < len(self._ancres_detail):
                details[("ancre", self._ancres_detail[k])] = (trajets, releve)
            occurrences[piece_id] = occurrence + 1

        return details

    # ── Assemblage ─────────────────────────────────────────────────────────────

    def parse(self) -> Journee | None:
        if self.errors:
            return None
        header = self._parse_header()
        if not header.get("garage_id"):
            self.errors.append("❌ Impossible d'extraire l'identifiant de garage")
            return None

        sommaires = self._parse_sommaires()
        if self.errors:
            return None
        if not sommaires:
            self.errors.append("❌ Aucun sommaire (Sommaire…Horaire) trouvé")
            return None

        details = self._parse_details()

        pieces = []
        occurrences: dict[str, int] = {}
        for s in sommaires:
            pid = s["id"]
            occurrence = occurrences.get(pid, 0)
            occurrences[pid] = occurrence + 1
            cle_ancre = ("ancre", s.get("_ancre"))
            traj, releve = details.get(
                cle_ancre,
                details.get((pid, occurrence), ([], None)),
            )
            if s.get("type_horaire") == "absence":
                traj, releve = [], None
            pieces.append({
                "id":              pid,
                "type_horaire":    s.get("type_horaire", "horaire"),
                **({"motif_absence": s["motif_absence"]} if "motif_absence" in s else {}),
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
            "garage_id":            header.get("garage_id"),
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
        contenu = journee.to_dict()
        sauvegarder_journee(out, contenu)
        self.calendrier, self.erreur_calendrier = ecrire_calendrier_sans_echec(
            contenu, dossier_calendrier(out)
        )
        return out

    def get_summary(self, journee: Journee | None = None, saved_path: Path | None = None) -> str:
        if self.errors:
            return "❌ Erreurs :\n" + "\n".join(f"  {e}" for e in self.errors)

        lines = [f"✅ Journée du {self.date_str}"]
        if journee:
            lines.append(
                f"   Garage {journee.garage_id} — {journee.garage or '?'} "
                f"| Journée n°{journee.journee_numero or '?'} "
                f"| {journee.temps_travaille or '?'} travaillé"
            )
            from chauffeur.modeles import TrajetService, TrajetHlp
            for p in journee.pieces:
                if p.type_horaire == "absence":
                    lines.append(
                        f"   Pièce Absence : {p.debut} → {p.fin} ({p.duree}), {p.motif_absence}"
                    )
                    continue
                bus   = p.numero_autobus or "–"
                ntraj = sum(1 for t in p.trajets if isinstance(t, TrajetService))
                nhlp  = sum(1 for t in p.trajets if isinstance(t, TrajetHlp))
                lines.append(
                    f"   Pièce {p.id}{' (TS)' if p.type_horaire == 'continu' else ''} : bus {bus}, "
                    f"{p.debut} → {p.fin}, "
                    f"{ntraj} voyage(s), {nhlp} HLP"
                )
        if saved_path:
            lines.append(f"\n📁 Sauvegardé : data/journees/{saved_path.name}")
            lines += lignes_calendrier(self.calendrier, self.erreur_calendrier)
        return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Importe le texte brut du « Détail de ma journée » "
                    "vers data/journees/journee-YYYY-MM-DD.json."
    )
    ap.add_argument("--date", help="Date de la journée (YYYY-MM-DD). "
                    "Déduit du texte si absent, sinon date du jour.")
    ap.add_argument("--json", action="store_true",
                    help="Affiche le JSON complet sur stdout.")
    ap.add_argument("--log", action="store_true",
                    help="Sauvegarde la sortie dans data/log/parse_journee.log (append).")
    args = ap.parse_args()

    raw    = sys.stdin.read()
    parser = JourneeParser(raw, date_str=args.date)
    result = parser.parse()

    if result:
        saved   = parser.save(result)
        summary = parser.get_summary(result, saved)
        print(summary)
        if args.log:
            ecrire_bloc("parse_journee", summary)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        summary = parser.get_summary()
        print(summary)
        if args.log:
            ecrire_bloc("parse_journee", summary)
        sys.exit(1)


if __name__ == "__main__":
    main()
