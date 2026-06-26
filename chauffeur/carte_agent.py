"""chauffeur.carte_agent — parser texte unifié de la carte agent HASTUS (PDF).

Extrait les trajets de service à partir du texte brut de la carte agent.
Le modèle CarteAgent (cf. modeles) porte les heures et expose `segments_par_ligne` /
`time_ranges_par_ligne`. Le parsing GÉOMÉTRIQUE (positions bbox pour l'annotation)
reste dans scripts/carte_agent_stm.py ; les données structurées sont lues depuis
les fichiers journée JSON (scripts/parse_journee.py).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .modeles import CarteAgent, Hlp, Segment, Trajet

# En-tête de trajet : « 168 / … » ou « 168 - P / … » (la désignation « - P »,
# « - 05 »… est optionnelle ; l'exiger ferait disparaître des lignes du rapport).
_TRIP_HEADER = r"[a-z]?\d+(?:\s+-\s+\w+)?\s+/"
_HEADER_RE   = re.compile(r"[a-z]?(\d+)(?:\s+-\s+(\w+))?\s+/")
_SERVICE_RE  = re.compile(r"/\s*-?\s*/\s*(.+)$")
_PURE_TIME   = re.compile(r"^\d{1,2}:\d{2}$")
_END_TIME    = re.compile(r"^(.+?)\s*(\d{2}:\d{2})$")


def parse_trajets(page1_text: str) -> list[Trajet]:
    """Découpe la page 1 en blocs de trajet et en extrait (terminus + heures).

    Format PyMuPDF (fitz) : chaque heure est sur sa propre ligne, sauf quand le
    nom d'arrêt est trop long — l'heure est alors collée à la fin de la ligne.
    """
    trajets: list[Trajet] = []
    blocks = re.split(rf"\n(?={_TRIP_HEADER}|hlp\d|GARAGE)", page1_text)

    for block in blocks:
        m = _HEADER_RE.match(block)
        if not m:
            continue
        ligne, designation = m.group(1), (m.group(2) or "")
        first_line = block.split("\n", 1)[0]
        ms = _SERVICE_RE.search(first_line)
        service = ms.group(1).strip() if ms else ""

        lines = [l.strip() for l in block.split("\n") if l.strip()]

        items: list[dict] = []
        for line in lines[1:]:          # saute l'en-tête
            if _PURE_TIME.match(line):
                items.append({"type": "time", "time": line, "stop": None})
            else:
                mt = _END_TIME.match(line)
                if mt:
                    items.append({"type": "stop_time", "time": mt.group(2),
                                  "stop": mt.group(1).strip()})
                else:
                    items.append({"type": "stop", "time": None, "stop": line})

        timed = [(i, it["time"]) for i, it in enumerate(items) if it["time"]]
        if len(timed) < 2:
            continue
        debut_i, debut_time = timed[0]
        fin_i,   fin_time   = timed[-1]

        # Terminus de départ : premier stop après la première heure ; si la première
        # heure est collée à un stop, c'est ce stop.
        debut_stop = None
        for j in range(debut_i + 1, len(items)):
            if items[j]["stop"] and len(items[j]["stop"]) > 2:
                debut_stop = items[j]["stop"]
                break
        if items[debut_i]["type"] == "stop_time":
            debut_stop = items[debut_i]["stop"]

        # Terminus d'arrivée : stop collé à la dernière heure, sinon dernier stop avant.
        fin_stop = None
        if items[fin_i]["type"] == "stop_time":
            fin_stop = items[fin_i]["stop"]
        else:
            for j in range(fin_i - 1, -1, -1):
                if items[j]["stop"] and len(items[j]["stop"]) > 2:
                    fin_stop = items[j]["stop"]
                    break

        trajets.append(Trajet(
            ligne=ligne, designation=designation, service=service,
            segment=Segment(debut_stop=debut_stop or "", fin_stop=fin_stop or "",
                            debut=debut_time, fin=fin_time),
        ))

    return trajets


def parse_lignes(page1_text: str) -> list[str]:
    """Numéros de ligne travaillés, dans l'ordre d'apparition, sans doublon.

    Ancré en début de ligne (^) pour ne pas capter « hlp1 »/« hlp2 ». Indépendant
    des trajets : une ligne sans heures exploitables y figure quand même."""
    seen: list[str] = []
    for m in re.finditer(rf"^{_TRIP_HEADER}", page1_text, re.MULTILINE):
        num = re.match(r"[a-z]?(\d+)", m.group(0)).group(1)
        if num not in seen:
            seen.append(num)
    return seen


def parse_meta(page1_text: str) -> dict:
    """Métadonnées : assignation, date, voiture, lieu/heures de prise, garage."""
    meta = {"assignation": "", "date": None, "voiture": "",
            "lieu_debut": "", "heure_debut": "", "heure_fin": "", "garage": ""}

    m = re.search(r"^(\d{3,4})\s", page1_text, re.MULTILINE)
    if m:
        meta["assignation"] = m.group(1)

    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", page1_text)
    if m:
        meta["date"] = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # Ligne du tableau shift (fitz mélange les colonnes) : voiture = dernier « NN - NN ».
    shift_m = re.search(r"[A-Z]\w+\s+\d+\d{2}:\d{2}.+?(\d+\s*-\s*\d+)\s*$",
                        page1_text, re.MULTILINE)
    if shift_m:
        meta["voiture"] = shift_m.group(1).replace(" ", "")

    lieu_m = re.search(r"([A-Z]\d+)\s+\d+\d{2}:\d{2}", page1_text)
    if lieu_m:
        meta["lieu_debut"] = lieu_m.group(1)

    times = re.findall(r"(?<!\d)(\d{2}:\d{2})", shift_m.group(0) if shift_m else "")
    if len(times) >= 2:
        meta["heure_debut"], meta["heure_fin"] = times[0], times[1]

    m = re.search(r"GARAGE\s+(\S+)", page1_text, re.IGNORECASE)
    if m:
        meta["garage"] = m.group(1).capitalize()

    return meta


def parse_hlp(page2_text: str) -> list[Hlp]:
    """Trajets haut-le-pied de la page 2 (instructions possiblement multi-lignes)."""
    hlp: list[Hlp] = []
    for m in re.finditer(
        r"(hlp\d+):\s+(\d+)\s+-\s+(.+?)(?=\n\s*hlp\d+:|\n\s*Page:|\Z)",
        page2_text, re.DOTALL | re.IGNORECASE,
    ):
        raw = re.sub(r"\s+", " ", m.group(3)).strip()
        code_fin_m = re.search(r"-\s*(\d+)\s*$", raw)
        code_fin = code_fin_m.group(1) if code_fin_m else ""
        raw = re.sub(r"\s*-\s*\d+\s*$", "", raw)
        instr = re.sub(r"\[V\]", "Via", raw)
        instr = re.sub(r"\[G\]", "Gauche", instr)
        instr = re.sub(r"\[D\]", "Droite", instr)
        hlp.append(Hlp(id=m.group(1), instructions=instr,
                       code_debut=m.group(2), code_fin=code_fin))
    return hlp


def parse_carte(pdf_path: Path) -> CarteAgent:
    """Point d'entrée : lit le PDF et retourne le modèle CarteAgent complet."""
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ImportError(
            "PyMuPDF requis. Exécute: pip install pymupdf --break-system-packages"
        ) from e

    doc = fitz.open(str(pdf_path))
    page1 = doc[0].get_text() if len(doc) > 0 else ""
    page2 = doc[1].get_text() if len(doc) > 1 else ""
    doc.close()

    meta = parse_meta(page1)
    return CarteAgent(
        assignation=meta["assignation"], date=meta["date"], voiture=meta["voiture"],
        lieu_debut=meta["lieu_debut"], heure_debut=meta["heure_debut"],
        heure_fin=meta["heure_fin"], garage=meta["garage"],
        lignes=parse_lignes(page1),
        trajets=parse_trajets(page1),
        hlp=parse_hlp(page2),
    )
