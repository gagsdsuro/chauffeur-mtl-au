#!/usr/bin/env python3
"""Parse la réponse 'détour' du portail STM (employe.stm.info).

Entrée : la réponse brute du endpoint /resume-journee/panel/detour/{ligne}/{sens},
         soit un JSON {"countDeviations": N, "html": "<fragment>"}.
Sortie : un dict structuré (ligne, sens, événements).

Aucune dépendance externe — lib standard uniquement.
"""
import json
import re
import sys
from html.parser import HTMLParser
from html import unescape


# --- Mini arbre DOM via html.parser ---------------------------------------
class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []          # mélange de _Node et de str (texte)
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


# balises auto-fermantes — pas de fermeture attendue
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


def _build(html):
    b = _TreeBuilder()
    b.feed(html)
    return b.root


# --- Extraction des lignes en respectant les <br> -------------------------
def _lines_br(dd):
    """Découpe un <dd> en lignes, les <br> servant de séparateurs."""
    parts, buf = [], []
    for c in dd.children:
        if isinstance(c, _Node) and c.tag == "br":
            parts.append("".join(buf)); buf = []
        elif isinstance(c, str):
            buf.append(c)
        else:
            buf.append(c.text())
    parts.append("".join(buf))
    return [unescape(p).strip() for p in
            "\n".join(parts).splitlines() if p.strip()]


# --- Parser principal ------------------------------------------------------
def parse(raw: str) -> dict:
    data = json.loads(raw)
    root = _build(data.get("html", ""))

    # Titre : "Détour / 10 Sud"
    h2 = root.find("h2")
    titre = h2.text() if h2 else ""
    ligne = sens = None
    m = re.search(r"/\s*(\w+)\s+(\w+)", titre)
    if m:
        ligne, sens = m.group(1), m.group(2)

    evenements = []
    for li in root.find_all("li", "on-off-canvas-panel-item"):
        ev = {
            "numero": None, "type": None, "motif": None,
            "date_debut": None, "date_fin": None, "effectif": None,
            "arrets": [], "description_gd": [], "commentaire": None,
        }

        h3 = li.find("h3")
        entete = h3.text() if h3 else ""
        parts = [p.strip() for p in entete.split(" - ", 2)]
        if len(parts) == 3:
            ev["numero"], ev["type"] = parts[1], parts[2]

        # Paires terme/valeur de premier niveau seulement
        for dl in li.find_all("dl", "on-off-canvas-panel-definition", direct=True):
            dt = dl.find("dt")
            dd = dl.find("dd")
            if not dt or not dd:
                continue
            terme = dt.text()

            if terme == "Motif":
                ev["motif"] = dd.text()
            elif terme.startswith("Date") and "début" in terme:
                ev["date_debut"] = dd.text()
            elif terme.startswith("Date") and "fin" in terme:
                v = dd.text()
                ev["date_fin"] = None if v.lower().startswith("non") else v
            elif terme == "Effectif":
                ev["effectif"] = dd.text()
            elif terme.startswith("Arrêt"):
                for item in dd.find_all("li", "on-off-canvas-panel-description-item"):
                    t = item.text()
                    a = re.match(r"(\d+)\s*-\s*(.+)", t)
                    ev["arrets"].append(
                        {"code": a.group(1), "nom": a.group(2).strip()} if a
                        else {"code": None, "nom": t}
                    )
            elif "Gauche-Droite" in terme:
                ev["description_gd"] = _lines_br(dd)
            elif terme == "Commentaire":
                ev["commentaire"] = "\n".join(_lines_br(dd))

        evenements.append(ev)

    return {
        "ligne": ligne,
        "sens": sens,
        "count_deviations": data.get("countDeviations", len(evenements)),
        "evenements": evenements,
    }


if __name__ == "__main__":
    raw = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    print(json.dumps(parse(raw), ensure_ascii=False, indent=2))
