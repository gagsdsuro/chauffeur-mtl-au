"""chauffeur.appariement — appariement G-D ↔ arrêts GTFS par alignement global.

Modèle : la séquence d'arrêts GTFS (seq 1…N) et la séquence d'instructions G-D
sont toutes deux figées. Un appariement est donc une **fonction monotone**
`etape[seq]` (index d'instruction G-D, non décroissant le long du parcours) :
chaque arrêt est présent une et une seule fois, aucun ne peut être dupliqué ni
oublié, et une boucle (même stop_id en début et en fin) ne pose aucun problème
puisque la clé est `seq`.

Contrairement à l'ancien alignement glouton de `chauffeur.gd.build_rows` (un
seul faux appariement — « Station Assomption (Assomption/Chauveau) » attiré par
« Gauche - Chauveau » sept étapes plus loin — entraînait tout le reste du
parcours), on maximise un score **global** par programmation dynamique. Le même
calcul (avant/arrière) donne, pour chaque arrêt, l'écart entre la meilleure
solution et la meilleure solution où cet arrêt serait ailleurs : c'est la
**confiance**, et un écart faible lève une incertitude au lieu d'échouer
silencieusement.

Les choix humains entrent comme **ancres** (`{seq: etape}`) : l'alignement est
recalculé autour d'elles, ce qui donne « relancer l'automatique à partir d'ici ».

Module pur (aucune I/O) : la persistance et l'UI vivent ailleurs.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re

from .matching import normalize_street

# Incrémenter à tout changement du barème ou de l'algorithme : les
# appariements automatiques persistés (sans choix humain) seront recalculés.
VERSION_ALGO = 1

# ── Barème ────────────────────────────────────────────────────────────────────
SCORE_LIEU = 14          # instruction nommant un lieu (« Terminus X ») cité par l'arrêt
SCORE_PRINCIPALE = 10    # rue de l'instruction = rue principale de l'arrêt
SCORE_TRANSVERSALE = 4   # rue de l'instruction = rue transversale de l'arrêt
SCORE_CONTEXTE = 5       # bonus : « vers <transversale> » précède l'instruction
SCORE_MENTION = 2        # rue de l'instruction mentionnée ailleurs dans le nom
PENALITE_RANG = 0.001    # par rang d'instruction : à égalité, l'arrêt reste sur la rue courante
PENALITE_BORNE = 0.5     # départ hors 1re instruction / arrivée hors dernière

# En deçà de cet écart, un autre placement est presque aussi plausible.
SEUIL_INCERTITUDE = 3.0

_NEG = float("-inf")
_PREFIXES_LIEU = {"terminus", "station", "gare", "aeroport", "metro"}
_CONNECTEUR = re.compile(r"^(?:carrefour giratoire|giratoire|rond point)\b")
_PARTICULES = re.compile(r"^(?:de la|de l|du|des|de|d|l|la|le|les)\s+")


# ── Normalisation ─────────────────────────────────────────────────────────────

def _est_lieu(cle: str) -> bool:
    """« station radisson » oui, « metropolitain » non (mot entier)."""
    return bool(cle) and cle.split()[0] in _PREFIXES_LIEU


def cle_rue(texte: str) -> str:
    """Clé de comparaison d'une rue : normalisée, sans particule initiale.

    « de l'Assomption » → « assomption », « de la Côte-de-Liesse » →
    « cote de liesse », « St-Laurent » → « saint laurent ».
    """
    s = normalize_street(texte.replace("’", " ").replace("'", " ").replace(".", " "))
    s = re.sub(r"\s+", " ", s).strip()
    prev = None
    while prev != s:
        prev, s = s, _PARTICULES.sub("", s)
    return s


def _rue_instruction(instruction: str) -> str:
    """'Gauche - Lafleur' → 'Lafleur' (texte brut après le sens)."""
    parts = instruction.split(" - ", 1)
    return parts[1].strip() if len(parts) == 2 else instruction.strip()


def _cibles_vers(rue: str) -> list | None:
    """Cibles d'une bretelle, ou None si l'instruction n'en est pas une.

    « vers aut. 40 Est/ St-Laurent/ St-Denis » → ['aut 40 est', 'saint laurent', …]
    « sortie 5 - Île-des-Soeurs »               → ['ile des soeurs']
    « entrée aut. 20 Est/ Maple »               → ['aut 20 est', 'maple']

    Une bretelle n'a pas d'arrêt : elle nomme la destination, pas la rue
    où l'on s'arrête (la station Île-des-Soeurs n'est pas sur la sortie 5).
    """
    texte = rue.strip()
    m = re.match(r"^vers\s+(.+)$", texte, re.IGNORECASE)
    if m:
        reste = m.group(1)
    else:
        m = re.match(r"^(?:sortie|entr[ée]e)\b\s*(.*)$", texte, re.IGNORECASE)
        if not m:
            return None
        # « sortie 57-N - chemin de la Pointe-nord » : la destination suit « - ».
        reste = m.group(1).split(" - ", 1)[1] if " - " in m.group(1) else m.group(1)
    cibles = []
    for morceau in reste.split("/"):
        morceau = re.sub(r"\bdir\.?\s*[nseo]\.?\s*$", "", morceau.strip(), flags=re.IGNORECASE)
        morceau = re.sub(r"^vers\s+", "", morceau.strip(), flags=re.IGNORECASE)
        cle = cle_rue(morceau)
        if cle:
            cibles.append(cle)
    return cibles


def _analyser_arret(nom: str) -> dict:
    """Décompose un nom d'arrêt GTFS en indices exploitables.

    Les parenthèses donnent la position réelle quand elles contiennent une
    intersection (« Station De la Savane (Décarie / de Sorel) ») ; sinon elles
    nomment un lieu (« (Terminus Radisson Sud », parfois tronqué sans « ) »).
    """
    principale = transversale = None
    lieu = ""
    paren = re.search(r"\(([^)]*)\)?", nom)
    dehors = nom
    if paren:
        dedans = paren.group(1)
        dehors = (nom[:paren.start()] + " " + nom[paren.end():]).strip()
        rues = [cle_rue(p) for p in dedans.split("/") if cle_rue(p)]
        if len(rues) >= 2:
            principale, transversale = rues[0], rues[1]
            lieu = cle_rue(dehors)
        else:
            lieu = cle_rue(dedans)
    if principale is None:
        rues = [cle_rue(p) for p in dehors.split("/") if cle_rue(p)]
        if rues and not _est_lieu(rues[0]):
            principale = rues[0]
            transversale = rues[1] if len(rues) > 1 else None
        elif rues:
            lieu = (lieu + " " + rues[0]).strip()
    return {
        "principale": principale,
        "transversale": transversale,
        "lieu": lieu,
        "complet": cle_rue(nom.replace("/", " ")),
    }


# ── Score local ───────────────────────────────────────────────────────────────

def _preparer_instructions(instructions: list) -> list:
    infos = []
    for instr in instructions:
        rue = _rue_instruction(instr)
        vers = _cibles_vers(rue)
        # « Berri (desserte) » → berri ; « du Bord-du-Lac - Lakeshore » : deux
        # noms d'une même rue, chacun peut figurer dans le nom de l'arrêt.
        sans_paren = re.sub(r"\([^)]*\)", " ", rue)
        cles = {c for c in (cle_rue(x) for x in sans_paren.split(" - ")) if c}
        infos.append({"cle": cle_rue(sans_paren), "cles": cles, "vers": vers})
    # Contexte : cibles des bretelles « vers … » qui précèdent chaque instruction.
    for k, info in enumerate(infos):
        contexte = set()
        j = k - 1
        while j >= 0 and infos[j]["vers"] is not None:
            contexte.update(infos[j]["vers"])
            j -= 1
        info["contexte"] = contexte
    return infos


def _score_local(arret: dict, instr: dict) -> float:
    """Plausibilité qu'un arrêt soit desservi pendant une instruction."""
    if instr["vers"] is not None:
        return 0.0          # une bretelle n'a pas d'arrêt : l'arrêt est sur la rue suivante
    cle = instr["cle"]
    if not cle:
        return 0.0
    if _est_lieu(cle):
        # Lieu ↔ lieu : « Terminus Jean-Drapeau » ↔ « Station Jean-Drapeau ».
        coeur = cle.split(" ", 1)[1] if " " in cle else ""
        # Comparé au lieu de l'arrêt seulement : « Terminus Dorval » ne doit
        # pas attirer les arrêts « Dorval / Carson » plantés sur la rue Dorval.
        if len(coeur) >= 4 and coeur in arret["lieu"]:
            return SCORE_LIEU
        return 0.0
    cles = instr["cles"]
    if arret["principale"] in cles:
        bonus = SCORE_CONTEXTE if arret["transversale"] in instr["contexte"] else 0
        return SCORE_PRINCIPALE + bonus
    if arret["transversale"] in cles:
        return SCORE_TRANSVERSALE
    if any(len(c) >= 5 and c in arret["complet"] for c in cles):
        return SCORE_MENTION
    return 0.0


# ── Alignement ────────────────────────────────────────────────────────────────

def _passe(locaux: list, m: int) -> list:
    """F[s][k] : meilleur score des arrêts 0..s avec l'arrêt s à l'étape k."""
    F = []
    for s, loc in enumerate(locaux):
        if s == 0:
            F.append(list(loc))
            continue
        prec = F[-1]
        ligne = [_NEG] * m
        meilleur = _NEG              # max_{j<=k} prec[j]
        for k in range(m):
            meilleur = max(meilleur, prec[k])
            ligne[k] = meilleur + loc[k] if meilleur > _NEG and loc[k] > _NEG else _NEG
        F.append(ligne)
    return F


def apparier(instructions: list, stops_ordered: list, stop_names: dict,
             ancres: dict | None = None) -> dict:
    """Aligne les arrêts GTFS sur les instructions G-D.

    instructions   : liste d'instructions « Sens - Rue » du parcours
    stops_ordered  : [(seq, stop_id), …] dans l'ordre GTFS
    stop_names     : {stop_id: {"code", "name"}}
    ancres         : {seq: etape} imposés par l'humain (respectés tels quels)

    Retourne {"arrets": [{seq, stop_id, etape, score, confiance, source}],
              "incertitudes": [{seq, stop_id, etapes_possibles, raison}]}.
    Lève ValueError si les ancres violent la monotonie.
    """
    ancres = {int(k): int(v) for k, v in (ancres or {}).items()}
    m, n = len(instructions), len(stops_ordered)
    if not m or not n:
        return {"arrets": [], "incertitudes": [], "blocs": []}

    precedent = -1
    for seq, _ in stops_ordered:
        if seq in ancres:
            e = ancres[seq]
            if not 0 <= e < m or e < precedent:
                raise ValueError(f"ancre seq {seq} → étape {e} non monotone")
            precedent = e

    infos = _preparer_instructions(instructions)
    arrets = [_analyser_arret(stop_names.get(sid, {}).get("name", ""))
              for _, sid in stops_ordered]
    bruts, locaux = [], []
    for s, ((seq, _), arret) in enumerate(zip(stops_ordered, arrets)):
        brut = [_score_local(arret, info) for info in infos]
        bruts.append(brut)
        # Préférence minime pour l'étape la plus tôt : un arrêt sans indice
        # reste sur la rue courante au lieu d'anticiper le virage suivant.
        loc = [v - PENALITE_RANG * k for k, v in enumerate(brut)]
        # Bornes : le parcours part de la 1re instruction et finit à la dernière.
        if s == 0:
            loc = [v - (PENALITE_BORNE if k > 0 else 0) for k, v in enumerate(loc)]
        if s == n - 1:
            loc = [v - (PENALITE_BORNE if k < m - 1 else 0) for k, v in enumerate(loc)]
        if seq in ancres:
            loc = [v if k == ancres[seq] else _NEG for k, v in enumerate(loc)]
        locaux.append(loc)

    avant = _passe(locaux, m)
    arriere = [ligne[::-1] for ligne in _passe([l[::-1] for l in locaux[::-1]], m)[::-1]]
    # arriere[s][k] : meilleur score des arrêts s..n-1, arrêt s à l'étape k
    # (pénalité d'avance symétrique : la passe inversée compte les mêmes avances).

    total = [[a + b - l if a > _NEG and b > _NEG else _NEG
              for a, b, l in zip(avant[s], arriere[s], locaux[s])]
             for s in range(n)]

    # Retour arrière depuis le dernier arrêt (à égalité stricte, l'étape la plus tôt).
    etapes = [0] * n
    fin = avant[-1]
    etapes[-1] = max(range(m), key=lambda k: (fin[k], -k))
    for s in range(n - 1, 0, -1):
        k, prec = etapes[s], avant[s - 1]
        etapes[s - 1] = max(range(k + 1),
                            key=lambda j: (prec[j], -j))
    if avant[-1][etapes[-1]] == _NEG:
        raise ValueError("aucun alignement compatible avec les ancres")

    # Classes d'équivalence : instructions consécutives sur une même rue
    # (« Gauche - Cavendish » puis « Via - Cavendish »). Hésiter entre elles
    # ne change rien pour le chauffeur : ce n'est pas une incertitude.
    # Un giratoire entre deux tronçons d'une même rue ne la coupe pas.
    classe, c, reference = [], -1, set()
    for info in infos:
        if _CONNECTEUR.match(info["cle"]):
            classe.append(max(c, 0))
            continue
        if not info["cles"] & reference:
            c += 1
        classe.append(c)
        reference = info["cles"]

    resultat, incertitudes = [], []
    for s, (seq, sid) in enumerate(stops_ordered):
        k = etapes[s]
        meilleur = total[s][k]
        autres = [v for j, v in enumerate(total[s]) if classe[j] != classe[k] and v > _NEG]
        ecart = meilleur - max(autres) if autres else float("inf")
        manuel = seq in ancres
        confiance = 1.0 if manuel else round(min(1.0, ecart / (2 * SEUIL_INCERTITUDE)), 2)
        resultat.append({
            "seq": seq, "stop_id": sid, "etape": k,
            "score": bruts[s][k], "confiance": confiance,
            "source": "manuel" if manuel else "auto",
        })
        if manuel:
            continue
        possibles = [j for j, v in enumerate(total[s])
                     if v > _NEG and meilleur - v < SEUIL_INCERTITUDE]
        if len({classe[j] for j in possibles}) < 2:
            continue                       # une seule rue plausible : rien à demander
        borne = (s == 0 and k == 0) or (s == n - 1 and k == m - 1)
        raison = None
        if bruts[s][k] <= 0:
            if borne:
                continue                   # terminus sans indice : placé au départ/à l'arrivée
            raison = "aucun_indice"
        elif ecart < SEUIL_INCERTITUDE:
            raison = "ambigu"
        if raison:
            incertitudes.append({"seq": seq, "stop_id": sid, "etape": k,
                                 "etapes_possibles": possibles, "raison": raison})
    return {"arrets": resultat, "incertitudes": incertitudes,
            "blocs": blocs_incertains(incertitudes, stops_ordered)}


def blocs_incertains(incertitudes: list, stops_ordered: list) -> list:
    """Regroupe les incertitudes d'arrêts consécutifs : une question par segment.

    Quinze arrêts « Côte-de-Liesse / … » hésitant entre deux « Via -
    Côte-de-Liesse » ne posent qu'une question : où le groupe bascule-t-il ?
    Deux voisins ne sont fusionnés que si leurs étapes possibles se recoupent.
    Retourne [{"seqs": [...], "etapes_possibles": [...], "raisons": [...]}].
    """
    rang = {seq: i for i, (seq, _) in enumerate(stops_ordered)}
    blocs, dernier = [], None
    for inc in incertitudes:
        r = rang[inc["seq"]]
        if (blocs and dernier == r - 1
                and set(blocs[-1]["etapes_possibles"]) & set(inc["etapes_possibles"])):
            bloc = blocs[-1]
            bloc["seqs"].append(inc["seq"])
            bloc["etapes_possibles"] = sorted(set(bloc["etapes_possibles"]) | set(inc["etapes_possibles"]))
            if inc["raison"] not in bloc["raisons"]:
                bloc["raisons"].append(inc["raison"])
        else:
            blocs.append({"seqs": [inc["seq"]],
                          "etapes_possibles": list(inc["etapes_possibles"]),
                          "raisons": [inc["raison"]]})
        dernier = r
    return blocs


def rows_depuis_appariement(instructions: list, appariement: dict, stop_names: dict) -> list:
    """Séquence linéaire instruction / arrêt, une ligne par élément.

    Chaque instruction est émise dans l'ordre, suivie de ses arrêts : une ligne
    d'instruction (`gd` seul), puis une ligne par arrêt (`gd` vide). Instruction
    et arrêt ne sont **jamais** fusionnés ici : un arrêt vient après sa
    manœuvre, il ne la partage pas. Les détours et arrêts ajoutés s'insèrent
    entre les deux sans ambiguïté ; `chauffeur.gd.rows_de_rendu` refait la mise
    en page à deux colonnes (instruction + 1er arrêt sur une ligne) en dernier.
    """
    par_etape: dict[int, list] = {}
    for a in appariement["arrets"]:
        par_etape.setdefault(a["etape"], []).append(a)
    rows = []
    for k, instr in enumerate(instructions):
        rows.append({"gd": instr, "seq": None, "stop_id": None})
        for a in par_etape.get(k, []):
            rows.append({"gd": "", "seq": a["seq"], "stop_id": a["stop_id"]})
    for r in rows:
        s = stop_names.get(r["stop_id"], {}) if r["stop_id"] else {}
        r["stop_code"] = s.get("code", "")
        r["stop_name"] = s.get("name", "")
    return rows


# ── Empreintes et report des ancres ──────────────────────────────────────────

def _hash(obj) -> str:
    brut = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]


def empreinte_gd(parcours: dict) -> str:
    """Empreinte de ce qui conditionne l'appariement côté G-D.

    Terminus et séquence d'instructions — pas le nom ni la date de mise à
    jour : un G-D réimporté à l'identique ne périme pas l'appariement.
    """
    return _hash([str(parcours.get("start_code", "")), str(parcours.get("end_code", "")),
                  list(parcours.get("direction", []))])


def empreinte_gtfs(stops_ordered: list) -> str:
    """Empreinte de la séquence ordonnée des arrêts GTFS du parcours."""
    return _hash([[int(seq), str(sid)] for seq, sid in stops_ordered])


def _cles_occurrence(stops_ordered: list) -> list:
    """(stop_id, n-ième occurrence) : distingue les deux passages d'une boucle."""
    vus: dict = {}
    cles = []
    for _, sid in stops_ordered:
        vus[sid] = vus.get(sid, 0) + 1
        cles.append((str(sid), vus[sid]))
    return cles


def reporter_ancres(ancien: dict, instructions: list, stops_ordered: list) -> tuple[dict, int]:
    """Transpose les choix manuels d'un appariement périmé sur les nouvelles sources.

    Un choix survit si son arrêt existe encore (même stop_id, même occurrence)
    et si son instruction se retrouve dans la portion inchangée du G-D
    (alignement difflib des textes d'instructions). Les choix devenus non
    monotones sont abandonnés. Retourne (ancres {seq: etape}, nb_abandonnés).
    """
    anciennes_instr = ancien.get("instructions", [])
    correspondance = {}
    sm = difflib.SequenceMatcher(a=anciennes_instr, b=list(instructions), autojunk=False)
    for bloc in sm.get_matching_blocks():
        for i in range(bloc.size):
            correspondance[bloc.a + i] = bloc.b + i

    anciens = ancien.get("arrets", [])
    cles_anciennes = _cles_occurrence([(a["seq"], a["stop_id"]) for a in anciens])
    nouveau_seq = dict(zip(_cles_occurrence(stops_ordered), (seq for seq, _ in stops_ordered)))

    candidats, abandonnes = [], 0
    for a, cle in zip(anciens, cles_anciennes):
        if a.get("source") != "manuel":
            continue
        seq, etape = nouveau_seq.get(cle), correspondance.get(a["etape"])
        if seq is None or etape is None:
            abandonnes += 1
        else:
            candidats.append((seq, etape))

    ancres, precedent = {}, -1
    for seq, etape in sorted(candidats):
        if etape < precedent:
            abandonnes += 1
            continue
        ancres[seq] = etape
        precedent = etape
    return ancres, abandonnes
