"""chauffeur.gd — domaine Gauche-Droite : alignement G-D/arrêts et détours.

Pipeline pur (sans I/O fichier) anciennement dans rapport_gd.py :
  build_rows → annotate_events → apply_gd_detours → insert_added_stops_inline
  (+ filter_rows_by_stop_range, _select_parcours, parse_description_gd)
  → rows_de_rendu.

Modèle : tout le pipeline travaille sur une **séquence linéaire** où chaque
instruction G-D et chaque arrêt GTFS occupent leur propre ligne (un arrêt vient
après sa manœuvre, il ne la partage pas). Les détours et les arrêts ajoutés
s'insèrent donc entre l'instruction et l'arrêt sans ambiguïté. La mise en page
à deux colonnes (instruction + 1er arrêt sur une même ligne) n'est refaite
qu'à la toute fin par `rows_de_rendu`, pour les rendus.

rapport_gd conserve son rendu HTML/MD et délègue ces transformations ici.
La normalisation de rue vit dans chauffeur.matching.
"""
from __future__ import annotations

import re

from .appariement import apparier, rows_depuis_appariement
from .matching import normalize_street, stops_match


def _select_parcours(all_parcours, hint):
    """Choisit un parcours selon un mot-clé dans le nom, ou le premier par défaut.
    Accepte list[ParcoursGD] ou list[dict]."""
    def _name(p):
        return (p.name if hasattr(p, "name") else p.get("name", "")) or ""

    if hint and all_parcours:
        h = hint.strip().lower()
        for p in all_parcours:
            if h in _name(p).lower():
                return p
        print(f"  ⚠ Parcours '{hint}' introuvable — utilisation du premier parcours.")
    return all_parcours[0] if all_parcours else {}


# ── Alignement G-D / arrêts ───────────────────────────────────────────────────

def extract_street(instruction):
    """'Gauche - Lafleur' → 'lafleur'"""
    parts = instruction.split(" - ", 1)
    return parts[1].strip().lower() if len(parts) == 2 else instruction.lower()


def build_rows(gd_instructions, stops_ordered, stop_names):
    """
    Aligne les instructions G-D avec les arrêts GTFS.
    Retourne la séquence linéaire : une ligne par instruction ({gd, seq=None,
    stop_id=None, …}) puis une ligne par arrêt ({gd="", seq, stop_id,
    stop_name, stop_code}). Rien n'est fusionné : voir `rows_de_rendu`.

    Délègue à `chauffeur.appariement.apparier` (alignement global monotone,
    voir ce module) : chaque arrêt est rattaché à une instruction, les
    instructions sans arrêt (virages, autoroutes) sont émises seules, dans
    l'ordre. Sans instruction, les arrêts sont émis sans cellule G-D.
    """
    if not gd_instructions:
        rows = [{"gd": "", "seq": seq, "stop_id": sid} for seq, sid in stops_ordered]
        for r in rows:
            s = stop_names.get(r["stop_id"], {})
            r["stop_code"] = s.get("code", "")
            r["stop_name"] = s.get("name", "")
        return rows
    resultat = apparier(gd_instructions, stops_ordered, stop_names)
    return rows_depuis_appariement(gd_instructions, resultat, stop_names)


def _code_arret(r) -> str:
    """Code d'arrêt d'une ligne : celui que les évènements citent (`id`)."""
    return str(r.get("stop_code") or r.get("stop_id") or "")


def _est_instruction(r) -> bool:
    """Instruction G-D régulière : ni étape de détour, ni arrêt, ni arrêt ajouté."""
    return bool(r.get("gd")) and not r.get("detour_added") \
        and not r.get("stop_id") and not r.get("added_inline")


def rows_de_rendu(rows):
    """Mise en page à deux colonnes de la séquence linéaire (étape finale).

    Une instruction immédiatement suivie de son arrêt les partage sur une même
    ligne ; si un détour ou un arrêt ajouté s'intercale, ils restent séparés.
    L'état de chaque moitié reste distinct : `detour_removed` vient de
    l'instruction, `cancelled` de l'arrêt. Ne modifie pas `rows`.
    """
    out = []
    i = 0
    while i < len(rows):
        r = rows[i]
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if (_est_instruction(r) and nxt is not None and nxt.get("stop_id")
                and not nxt.get("gd")):
            fusion = dict(nxt)
            fusion["gd"] = r["gd"]
            if r.get("detour_removed"):
                fusion["detour_removed"] = True
            out.append(fusion)
            i += 2
        else:
            out.append(r)
            i += 1
    return out


def filter_rows_by_stop_range(rows, arret_debut, arret_fin):
    """
    Tronque la liste de lignes selon les codes d'arrêt de départ et de fin.
    Si un code n'est pas trouvé, un avertissement est émis et la borne est ignorée.
    """
    if not arret_debut and not arret_fin:
        return rows

    start_idx = 0
    end_idx = len(rows) - 1

    if arret_debut:
        found = next(
            (i for i, r in enumerate(rows) if r.get("stop_code") == str(arret_debut)),
            None,
        )
        if found is not None:
            start_idx = found
            # L'instruction qui mène à cet arrêt reste dans le tableau.
            if found > 0 and _est_instruction(rows[found - 1]):
                start_idx = found - 1
        else:
            print(f"  ⚠ Arrêt de départ '{arret_debut}' introuvable dans les arrêts GTFS — borne ignorée.")

    if arret_fin:
        found = next(
            (i for i, r in enumerate(rows) if r.get("stop_code") == str(arret_fin)),
            None,
        )
        if found is not None:
            end_idx = found
        else:
            print(f"  ⚠ Arrêt de fin '{arret_fin}' introuvable dans les arrêts GTFS — borne ignorée.")

    return rows[start_idx : end_idx + 1]


def annotate_events(rows, events):
    """
    Ajoute les annotations d'événements aux lignes du tableau.
    Chaque ligne annulée reçoit une liste d'objets :
      {"label": str, "effectif": str}

    Retourne (rows, added, orphan_events) où orphan_events contient les
    événements dont aucun arrêt annulé ne figure dans le trajet GTFS
    sélectionné (ils sont affichés dans une section "Alertes" séparée).
    """
    cancelled_ids = {}   # stop_id -> list of {label, effectif}
    added = []           # arrêts ajoutés avec descriptions
    codes_in_rows = {_code_arret(r) for r in rows if r.get("stop_id")}

    for e in events:
        titre       = e.get("titre", "")
        motif       = e.get("motif", "")
        effectif    = (e.get("effectif") or "").strip()
        desc        = e.get("description_gd", "") or ""
        commentaire = e.get("commentaire", "") or ""
        label = f"{titre} ({motif})"
        if desc:
            label += f" — G-D: {desc}"
        if commentaire:
            label += f" — {commentaire}"

        for a in e.get("arrets_annules", []):
            cancelled_ids.setdefault(a["id"], []).append({
                "label":          label,
                "short_label":    f"{titre} ({motif})",
                "effectif":       effectif,
                "nom_evt":        a.get("nom", ""),
                "evenement_id":   e.get("evenement_id", ""),
                "commentaire":    commentaire,
                "type_evenement": titre.lower(),
            })
        for rang, a in enumerate(e.get("arrets_ajoutes", [])):
            name = a if isinstance(a, str) else a.get("nom", "")
            code = "" if isinstance(a, str) else str(a.get("id", "") or "")
            added.append({"name": name, "id": code, "rang": rang, "label": label,
                          "short_label": f"{titre} ({motif})",
                          "commentaire": commentaire, "effectif": effectif,
                          "evenement_id": e.get("evenement_id", "")})

    for r in rows:
        code = _code_arret(r) if r.get("stop_id") else ""
        if code and code in cancelled_ids:
            r["cancelled"] = cancelled_ids[code]
        else:
            r["cancelled"] = []

    # Événements dont les arrêts annulés ne figurent pas dans le trajet GTFS
    orphan_events = []
    for e in events:
        arrets = e.get("arrets_annules", [])
        if arrets and not any(a["id"] in codes_in_rows for a in arrets):
            orphan_events.append(e)

    return rows, added, orphan_events


# ── Intégration G-D des détours ───────────────────────────────────────────────

# Retour à la route régulière : « R.R. », « RR », « R/R », « VRR », « ROUTE RÉGULIÈRE ».
_RR_RE = re.compile(r'^(?:R[./\s]?R\.?|VRR|ROUTE\s+R[ÉE]GULI[ÈE]RE)$', re.IGNORECASE)


def parse_description_gd(desc: str):
    """
    Tente de parser une description_gd en liste d'instructions normalisées.
    Retourne ["Via - X", "Gauche - Y", ...] ou None (texte libre).
    """
    if not desc:
        return None
    if not re.search(r'\b(VIA\s+\w|G[/.\s]\w|D[/.\s]\w)', desc, re.IGNORECASE):
        return None

    if '\n' in desc:
        raw = [l.strip() for l in desc.split('\n') if l.strip()]
    else:
        raw = re.split(r'(?=\bVIA\b|\bG[/.\s]|\bD[/.\s])', desc.strip(), flags=re.IGNORECASE)
        raw = [p.strip() for p in raw if p.strip()]

    instructions = []
    for part in raw:
        part = part.strip().rstrip('.')
        if not part or re.fullmatch(r'[*\s]+', part):
            continue   # séparateur décoratif (« *** »)
        m = re.match(r'^VIA\s+(.+)$', part, re.IGNORECASE)
        if m:
            text = m.group(1).strip()
            instructions.append("Via - R.R." if _RR_RE.match(text) else f"Via - {text}")
            continue
        m = re.match(r'^G[/.\s]\s*(.+)$', part, re.IGNORECASE)
        if m:
            instructions.append(f"Gauche - {m.group(1).strip()}")
            continue
        m = re.match(r'^D[/.\s]\s*(.+)$', part, re.IGNORECASE)
        if m:
            instructions.append(f"Droite - {m.group(1).strip()}")
            continue
        instructions.append(f"Via - {part}")

    return instructions if instructions else None


def event_applicable_to_parcours(event: dict, stop_ids_in_rows: set | None,
                                  gd_instructions: list) -> bool:
    """Détermine si un évènement est applicable à un parcours spécifique.

    Règle 1 — avec arrets_annules :
      Au moins un arrêt annulé doit figurer dans les stops GTFS de ce parcours.
      stop_ids_in_rows=None = arrêts GTFS inconnus (GTFS absent ou en erreur) →
      présumé applicable (fail-safe : ne jamais cacher un évènement faute de
      données). Un set() vide, lui, signifie « le GTFS a parlé : aucun arrêt ».

    Règle 2 — détour sans arrêt annulé :
      Les deux bornes du détour doivent chacune figurer dans les instructions G-D :
      • 2a : première instruction Via (rue empruntée par le détour).
      • 2b : instruction juste avant R.R. (rue de rejointe au parcours normal).
      Si une borne est absente de la description (cas indécidable), on inclut
      l'évènement par prudence. Les deux bornes connues doivent toutes deux matcher.
    """
    cancelled = event.get("arrets_annules", [])
    if cancelled:
        if stop_ids_in_rows is None:
            return True
        return any(a["id"] in stop_ids_in_rows for a in cancelled)

    desc = (event.get("description_gd") or "").strip()
    if not desc:
        return True

    parsed = parse_description_gd(desc)
    if not parsed:
        return True

    gd_streets = {normalize_street(extract_street(i)) for i in gd_instructions}

    def _in_gd(norm: str) -> bool:
        # Exact ou suffixe : "gauchetiere" ↔ "de la gauchetiere"
        return norm in gd_streets or any(s.endswith(" " + norm) for s in gd_streets)

    # 2a : première Via non-R.R.
    via_norm = None
    for instr in parsed:
        street = extract_street(instr)
        if instr.lower().startswith("via") and not _RR_RE.match(street):
            via_norm = normalize_street(street)
            break

    # 2b : instruction juste avant R.R.
    before_rr_norm = None
    for i, instr in enumerate(parsed):
        if _RR_RE.match(extract_street(instr)):
            if i > 0:
                before_rr_norm = normalize_street(extract_street(parsed[i - 1]))
            break

    # Les deux bornes connues doivent figurer dans les instructions G-D.
    for norm in (via_norm, before_rr_norm):
        if norm is not None and not _in_gd(norm):
            return False
    return True


def _regular_steps(rows: list) -> list:
    """Indices des étapes G-D régulières (avec une rue), hors étapes de détour."""
    return [i for i, r in enumerate(rows)
            if r.get("gd") and not r.get("detour_added")]


def _ancrer_detour(rows: list, instructions: list, max_gap: int = 2):
    """
    Détour sans arrêt annulé : on ne peut pas ancrer sur un arrêt contourné.
    On ancre sur les rues d'entrée et de rejointe lues dans la description_gd :

      - rue d'entrée   = 1re instruction du détour ;
      - rue de rejointe = dernière instruction *avant* le « R.R. » final.

    Règle :
      1. ancre = dernière étape G-D régulière matchant la rue d'entrée et située
         avant la 1re étape matchant la rue de rejointe (gère les parcours qui
         passent 2× la même rue, ex. Bonaventure) ;
      2. fin du contournement = dernier match de la rue de rejointe dans la
         *grappe contiguë* qui suit (tolérance de `max_gap` étapes « connecteur »
         non-matchantes, ex. « carrefour giratoire »), pour ne pas avaler une
         réapparition lointaine de la même rue. Ne pas prolonger cette grappe
         à travers un arrêt non repris explicitement par le détour (code cité
         ou nom complet égal à une étape), même si sa ligne G-D est vide ;
      3. le détour s'insère APRÈS l'ancre et ses arrêts (juste avant l'instruction
         suivante, la 1re contournée) et barre les étapes (ancre, fin].

    Retourne (insert_pos, bypass_end, raison). bypass_end == -1 si rien n'est
    barré (ancre seule, comportement conservateur). Faute d'ancre exploitable,
    retombe sur (0, -1) — insertion en tête, ancien comportement. `raison`
    vaut None quand l'ancrage est complet, sinon « description_vide »,
    « entree_introuvable » (début du détour absent du G-D) ou
    « rejointe_introuvable » (retour au parcours régulier absent) : l'échec
    n'est plus silencieux, l'appelant peut le signaler.
    """
    if not instructions:
        return 0, -1, "description_vide"
    entry_street = extract_street(instructions[0])
    reg = _regular_steps(rows)
    if not reg or not entry_street:
        return 0, -1, "entree_introuvable"

    # Rue de rejointe = dernière instruction nommée avant le « R.R. » final.
    exit_street = ""
    for instr in reversed(instructions):
        st = extract_street(instr)
        if _RR_RE.match(st.upper()):
            continue
        exit_street = st
        break

    def matches(i, street):
        return bool(street) and stops_match(extract_street(rows[i]["gd"]), street)

    first_exit = next((i for i in reg if matches(i, exit_street)), None)

    entry_hits = [i for i in reg if matches(i, entry_street)]
    if not entry_hits:
        return 0, -1, "entree_introuvable"
    if first_exit is not None:
        before = [i for i in entry_hits if i < first_exit]
        anchor = before[-1] if before else entry_hits[0]
    else:
        anchor = entry_hits[0]

    # Les arrêts de l'instruction d'entrée la suivent : le détour vient après eux.
    insert_pos = anchor + 1
    while insert_pos < len(rows) and not _est_instruction(rows[insert_pos]) \
            and not rows[insert_pos].get("detour_added"):
        insert_pos += 1

    # Pas de rejointe exploitable → insertion seule, rien barré.
    if first_exit is None or first_exit <= anchor:
        return insert_pos, -1, "rejointe_introuvable"

    # Grappe contiguë de la rue de rejointe après l'ancre.
    rues_detour = {normalize_street(extract_street(instr)) for instr in instructions}
    codes_detour = set(re.findall(r"\b\d{5}\b", "\n".join(instructions)))
    def arret_repris(r):
        code = _code_arret(r)
        nom = normalize_street(r.get("stop_name") or "")
        return code in codes_detour or bool(nom and nom in rues_detour)

    bypass_end = first_exit
    gap = 0
    for i in range(first_exit + 1, len(rows)):
        r = rows[i]
        if r.get("detour_added") or r.get("added_inline"):
            continue
        # Une boucle de desserte (Cardinal → Gare Dorval Nord → Cardinal)
        # n'est pas un simple raccord. Examiner aussi les arrêts sans G-D.
        if r.get("stop_id") or r.get("stop_code"):
            if not arret_repris(r):
                break
        if not r.get("gd"):
            continue
        # Instruction suivie d'un arrêt non repris : la boucle de desserte
        # commence avec elle, elle n'est pas un raccord du détour.
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if nxt is not None and (nxt.get("stop_id") or nxt.get("stop_code")) \
                and not arret_repris(nxt):
            break
        if matches(i, exit_street):
            bypass_end = i
            gap = 0
        else:
            gap += 1
            if gap > max_gap:
                break
    return insert_pos, bypass_end, None


def _anchor_detour_span(rows: list, instructions: list, max_gap: int = 2):
    """(insert_pos, bypass_end) de `_ancrer_detour`, sans la raison d'échec."""
    return _ancrer_detour(rows, instructions, max_gap)[:2]


# ── Choix humains imposés au pipeline ────────────────────────────────────────
#
# Un choix (voir chauffeur.registre_detours) remplace l'heuristique d'ancrage :
#   {"debut": ref | None, "fin": ref | None,
#    "arrets_ajoutes": [{"cle": str, "etape": int, "avant": bool}] | None}
# où `ref` désigne un élément de la séquence linéaire, indépendamment de sa
# position (elle change quand un autre détour s'insère) :
#   {"type": "instruction" | "arret", "cle": texte G-D | code d'arrêt,
#    "occurrence": n}   (n-ième élément identique, à partir de 1).
# `debut` = le détour s'insère AVANT cet élément ; `fin` = dernier élément
# barré (inclus), None = rien n'est barré. Sans `debut`, l'ancrage reste
# automatique. `arrets_ajoutes` donne l'ordre et l'étape (rang parmi les
# étapes du détour, à partir de 0) de chaque arrêt ajouté, désigné par son code
# ou, à défaut, par son nom normalisé (`cle_arret_ajoute`).

def _cle_ref(r: dict):
    """(type, clé) d'une ligne de la séquence linéaire, ou None (détour, arrêt ajouté)."""
    if r.get("detour_added") or r.get("added_inline"):
        return None
    if r.get("stop_id"):
        return "arret", _code_arret(r)
    if r.get("gd"):
        return "instruction", r["gd"]
    return None


def reference_ligne(rows: list, i: int) -> dict | None:
    """Référence stable de la ligne `i` (None pour un détour ou un arrêt ajouté)."""
    cle = _cle_ref(rows[i])
    if cle is None:
        return None
    occurrence = sum(1 for r in rows[:i + 1] if _cle_ref(r) == cle)
    return {"type": cle[0], "cle": cle[1], "occurrence": occurrence}


def resoudre_ref(rows: list, ref: dict | None) -> int | None:
    """Index de la ligne désignée par `ref`, ou None si elle n'existe plus."""
    if not ref:
        return None
    cible, n = (ref.get("type"), ref.get("cle")), int(ref.get("occurrence") or 1)
    vus = 0
    for i, r in enumerate(rows):
        if _cle_ref(r) == cible:
            vus += 1
            if vus == n:
                return i
    return None


def cle_arret_ajoute(stop_info: dict) -> str:
    """Clé d'un arrêt ajouté : son code à 5 chiffres, sinon son nom normalisé."""
    code = (stop_info.get("id") or "").strip()
    return code if _STOP_CODE_RE.match(code) else normalize_street(stop_info.get("name", ""))


def _diag(event: dict, type_: str, raison: str = "", **extra) -> dict:
    """Entrée de diagnostic : ce que le pipeline n'a pas pu décider seul."""
    return {"evenement_id": event.get("evenement_id", ""),
            "titre": event.get("titre", ""), "type": type_, "raison": raison, **extra}


def apply_gd_detours(rows: list, events: list, diagnostics: list | None = None,
                     choix=None) -> list:
    """
    Pour chaque événement avec une description_gd parseable :
    - Insère les étapes du détour avant le premier arrêt annulé (detour_added=True)
    - Marque les instructions G-D régulières contournées (detour_removed=True)

    Détour SANS arrêt annulé : ancrage par rues d'entrée/rejointe via
    _anchor_detour_span (le détour se place après l'étape correspondant à sa
    1re instruction et barre les étapes contournées jusqu'à la rejointe).

    `diagnostics` (liste optionnelle, complétée en place) reçoit un `_diag` pour
    chaque détour que le pipeline n'a pas su placer ou borner seul — plutôt que
    d'échouer en silence : description illisible, début ou retour du détour
    introuvables dans le G-D.

    `choix` (callable évènement → choix humain ou None, voir plus haut) impose
    le début du détour et la fin du barrage ; un choix qui ne s'applique plus
    (G-D modifié) est signalé et l'ancrage redevient automatique.
    """
    for event in events:
        desc = event.get("description_gd") or ""
        instructions = parse_description_gd(desc)
        if not instructions:
            if desc.strip() and diagnostics is not None:
                diagnostics.append(_diag(event, "description_non_interpretee"))
            continue

        cancelled_codes = {a["id"] for a in event.get("arrets_annules", [])}

        cancelled_positions = [
            i for i, r in enumerate(rows)
            if r.get("stop_id") and _code_arret(r) in cancelled_codes
        ]

        impose = None
        decision = choix(event) if choix else None
        if decision and decision.get("debut"):
            debut = resoudre_ref(rows, decision["debut"])
            fin = resoudre_ref(rows, decision["fin"]) if decision.get("fin") else None
            if debut is None or (decision.get("fin") and fin is None):
                if diagnostics is not None:
                    diagnostics.append(_diag(event, "choix_inapplicable", "element_introuvable"))
            else:
                impose = (debut, fin if fin is not None else debut - 1)

        if impose:
            first_pos, last_pos = impose
        elif cancelled_positions:
            first_pos = cancelled_positions[0]
            last_pos  = cancelled_positions[-1]

            # L'instruction qui mène au premier arrêt annulé : si c'est la rue
            # que le détour emprunte en premier (« Droite - Beaubien » puis
            # « VIA BEAUBIEN »), on roule déjà dessus — le détour s'insère entre
            # elle et l'arrêt, et elle reste valide. Sinon c'est la manœuvre
            # contournée : le détour la précède et la barre.
            if first_pos > 0 and _est_instruction(rows[first_pos - 1]):
                entree = extract_street(instructions[0])
                if not (entree and stops_match(
                        extract_street(rows[first_pos - 1]["gd"]), entree)):
                    first_pos -= 1

            # Étendre last_pos pour inclure les instructions G-D sans arrêt GTFS
            # qui suivent immédiatement le dernier arrêt annulé.
            # Ex. : "Gauche - Clément" dont le stop a été consommé par une
            # instruction précédente ("Droite - Clément") et qui se retrouve
            # sans arrêt → tombe en dehors de la plage sans cette extension.
            # L'instruction qui mène à un arrêt régulier non annulé appartient
            # à la suite régulière : l'extension s'arrête avant elle.
            i = last_pos + 1
            while i < len(rows):
                if _code_arret(rows[i]) and rows[i].get("stop_id") \
                        and _code_arret(rows[i]) not in cancelled_codes:
                    break  # premier arrêt régulier non annulé : fin de la zone
                nxt = rows[i + 1] if i + 1 < len(rows) else None
                if (_est_instruction(rows[i]) and nxt is not None and nxt.get("stop_id")
                        and _code_arret(nxt) not in cancelled_codes):
                    break
                last_pos = i
                i += 1
        else:
            first_pos, last_pos, raison = _ancrer_detour(rows, instructions)
            if raison and diagnostics is not None:
                diagnostics.append(_diag(event, "detour_non_ancre", raison))

        # Toutes les instructions G-D dans la plage sont contournées,
        # y compris celles associées à un arrêt annulé.
        if last_pos >= first_pos:
            for i in range(first_pos, last_pos + 1):
                r = rows[i]
                if r.get("gd") and not r.get("detour_added"):
                    r["detour_removed"] = True

        label = event.get("titre", "")
        detour_rows = [
            {
                "gd": instr,
                "seq": None,
                "stop_id": None,
                "stop_code": "",
                "stop_name": "",
                "cancelled": [],
                "detour_added": True,
                "detour_label": label if i == 0 else "",
                "evenement_id": event.get("evenement_id", ""),
                "effectif": event.get("effectif", "") if i == 0 else "",
            }
            for i, instr in enumerate(instructions)
        ]

        rows = rows[:first_pos] + detour_rows + rows[first_pos:]

    return rows


# ── Placement inline des arrêts ajoutés ──────────────────────────────────────

_STOP_CODE_RE = re.compile(r'^\d{5}$')

# Un nom qui commence par l'un de ces mots désigne un lieu (station de métro,
# terminus), pas la rue sur laquelle l'arrêt est planté.
_LIEU_PREFIXES = {"station", "terminus"}


def _split_intersection(texte: str):
    """Découpe « Rue A / Rue B » en rues normalisées, ou None si ce n'en est pas une.

    Rejette les indicateurs de quadrant que le portail accole aux noms d'arrêts
    (« (N/O) », « (S/E) ») : ils ont la forme d'une intersection mais leurs
    membres sont des lettres isolées.
    """
    parts = [normalize_street(re.sub(r'\b\d{5}\b', ' ', p)) for p in texte.split("/")]
    parts = [p for p in parts if p]
    if len(parts) < 2 or any(len(p) < 3 for p in parts):
        return None
    return parts


def _parse_added_stop(name: str):
    """
    Extrait (rue_principale, rue_transversale) normalisées depuis le nom
    d'un arrêt ajouté, ou (None, None) si le nom ne désigne aucune rue.

    Le nom d'une station nomme la station, pas la rue où l'arrêt est planté :
    « Station Sherbrooke » est sur Berri. Or une station porte presque toujours
    le nom d'une rue que la ligne emprunte pour de vrai — s'y fier place l'arrêt
    au mauvais coin sans le moindre signal d'erreur. Le portail donne la position
    réelle entre parenthèses (même convention que matching.stop_tokens) : on la
    lit en priorité, et faute d'intersection exploitable on renonce à placer
    l'arrêt plutôt que de deviner — il ressort alors dans les alertes.

    "Temp. - Clément / Lafleur"                     → ("clement", "lafleur")
    "56472 - Notre-Dame / Saint-Pierre"             → ("notre dame", "saint pierre")
    "Temp. - De Rouen /Bourbonnière (N/E)"          → ("de rouen", "bourbonniere")
    "Station Papineau (Cartier / Sainte-Catherine)" → ("cartier", "sainte catherine")
    "Station Sherbrooke (Édicule Est)"              → (None, None)
    """
    m = re.match(r'^(?:Temp\.|[\d]+)\s*[-–]\s*(.+)$', name, re.IGNORECASE)
    clean = (m.group(1) if m else name).strip()

    paren = re.search(r'\(([^)]*)\)', clean)
    if paren:
        rues = _split_intersection(paren.group(1))
        if rues:
            return rues[0], rues[1]
        clean = re.sub(r'\([^)]*\)', " ", clean).strip()

    rues = _split_intersection(clean)
    if rues:
        return rues[0], rues[1]

    seul = normalize_street(clean)
    if not seul or seul.split()[0] in _LIEU_PREFIXES:
        return None, None
    return seul, None


def _anchor_added_by_code(rows: list, stop_info: dict):
    """
    Ancre un arrêt ajouté sur l'étape de détour qui cite son code d'arrêt.

    Les descriptions_gd nomment souvent le terminus temporaire avec son code :
    « TERMINUS TEMPORAIRE STATION SHERBROOKE (52506) », « ... ARRÊT 53016 ».
    C'est une ancre exacte, là où l'appariement par nom de rue ne peut que
    supposer — on la préfère donc systématiquement.

    Position : un terminus temporaire est le départ ou l'arrivée du détour.
    Cité par la 1re étape, c'est le point de départ → l'arrêt la précède ; cité
    plus loin, on l'atteint au terme de la manœuvre → l'arrêt la suit.

    Retourne (index, avant) ou None si le code est absent des étapes du détour.
    """
    code  = (stop_info.get("id") or "").strip()
    ev_id = stop_info.get("evenement_id", "")
    if not _STOP_CODE_RE.match(code):
        return None

    etapes = [i for i, r in enumerate(rows)
              if r.get("detour_added") and r.get("gd")
              and (not ev_id or r.get("evenement_id", "") == ev_id)]
    for rang, i in enumerate(etapes):
        if re.search(rf'\b{code}\b', rows[i]["gd"]):
            return i, rang == 0
    return None


def _added_row(stop_info: dict) -> dict:
    """Ligne de tableau pour un arrêt ajouté placé inline."""
    return {
        "gd": "",
        "seq": None,
        "stop_id": None,
        "stop_code": "",
        "stop_name": stop_info["name"],
        "cancelled": [],
        "added_inline":  True,
        "added_label":   stop_info.get("label", ""),
        "added_short_label": stop_info.get("short_label", ""),
        "commentaire":   stop_info.get("commentaire", ""),
        "effectif":      stop_info.get("effectif", ""),
        "evenement_id":  stop_info.get("evenement_id", ""),
    }


def _apres_arrets_ajoutes(rows: list, idx: int, stop_info: dict) -> int:
    """Position d'insertion juste après l'étape `idx`, derrière les arrêts du
    même événement déjà posés sur cette ancre : plusieurs arrêts qui s'ancrent
    sur la même étape gardent l'ordre de `arrets_ajoutes` (sans quoi chacun
    passerait devant le précédent)."""
    ev_id = stop_info.get("evenement_id", "")
    pos = idx + 1
    while (pos < len(rows) and rows[pos].get("added_inline")
           and rows[pos].get("evenement_id", "") == ev_id):
        pos += 1
    return pos


def _anchor_added_by_streets(rows: list, ev_id: str,
                             main_street: str, cross_street):
    """
    Cherche l'index de la ligne detour_added (du même événement) où poser un
    arrêt ajouté circulant sur `main_street` : retourne (index, ambigu), ou
    (None, False) si aucune ne correspond. `ambigu` vaut True quand plusieurs
    étapes conviennent et que rien ne permet de choisir (dernier candidat pris).

    Candidats : les instructions de détour dont la rue ≈ main_street. Parmi
    elles, préfère celle immédiatement suivie d'une instruction sur la rue
    transversale (= on est au bon coin de rue) ; à défaut, la dernière.
    """
    candidates = []
    for i, r in enumerate(rows):
        if not r.get("detour_added") or not r.get("gd"):
            continue
        if ev_id and r.get("evenement_id", "") != ev_id:
            continue
        instr_street = normalize_street(extract_street(r["gd"]))
        if main_street in instr_street or instr_street in main_street:
            candidates.append(i)

    if not candidates:
        return None, False

    if cross_street:
        # Préfère le candidat suivi d'une instruction sur la rue transversale
        # (du même événement).
        for idx in candidates:
            j = idx + 1
            while (j < len(rows) and rows[j].get("detour_added")
                   and rows[j].get("evenement_id", "") == rows[idx].get("evenement_id", "")
                   and not rows[j].get("gd")):
                j += 1
            if (j < len(rows) and rows[j].get("detour_added")
                    and rows[j].get("evenement_id", "") == rows[idx].get("evenement_id", "")
                    and rows[j].get("gd")):
                next_street = normalize_street(extract_street(rows[j]["gd"]))
                if cross_street in next_street or next_street in cross_street:
                    return idx, False

    return candidates[-1], len(candidates) > 1  # dernier candidat sur cette rue


def insert_added_stops_inline(rows: list, added: list,
                              diagnostics: list | None = None,
                              choix_arrets=None) -> tuple:
    """
    Tente de placer chaque arrêt ajouté directement dans le tableau, par ordre
    de fiabilité décroissante des ancres :

      0. Code d'arrêt cité dans une étape du détour (_anchor_added_by_code) :
         ancre exacte, elle l'emporte sur tout appariement de nom.
      1. Sinon, cherche les lignes detour_added dont la rue correspond à la rue
         principale de l'arrêt (_parse_added_stop, qui sait qu'une station n'est
         pas sur la rue dont elle porte le nom).
      2. Parmi elles, préfère celle immédiatement suivie d'une instruction
         sur la rue transversale (= on est au bon coin de rue).
      3. Insère un arrêt vert juste après cette instruction.

    L'arrêt « A / B » nomme d'ordinaire d'abord la rue qu'emprunte la ligne,
    mais un détour peut réquisitionner un arrêt situé sur une rue perpendiculaire
    au parcours régulier de cet arrêt : « Joliette / de Rouen » desservi par un
    détour circulant sur de Rouen. Si la 1re rue n'ancre nulle part, on réessaie
    donc avec la rue transversale comme rue empruntée (les rôles échangés) plutôt
    que d'abandonner l'arrêt.

    Retourne (rows_mis_à_jour, still_added) où still_added contient les
    arrêts qui n'ont pas pu être positionnés inline.

    `diagnostics` (liste optionnelle, complétée en place) reçoit un diagnostic
    par arrêt non placé, par ancre ambiguë et par groupe d'arrêts posés sur une
    même étape (leur ordre relatif n'est alors connu que par l'événement).

    `choix_arrets` (callable arrêt ajouté → {"rang", "etape", "avant"} ou None,
    voir « Choix humains ») impose l'étape du détour sur laquelle un arrêt se
    pose et l'ordre des arrêts ainsi choisis ; les autres restent automatiques.
    """
    still_added = []
    imposes = [choix_arrets(a) if choix_arrets else None for a in added]
    if any(imposes):
        # Les arrêts à choix reprennent, dans l'ordre de leur rang, les places
        # qu'ils occupaient dans la liste : le reste ne bouge pas.
        places = [i for i, c in enumerate(imposes) if c]
        ordonnes = sorted(places, key=lambda i: (added[i].get("evenement_id", ""),
                                                 imposes[i]["rang"]))
        nouveaux, nouveaux_choix = list(added), list(imposes)
        for place, source in zip(places, ordonnes):
            nouveaux[place], nouveaux_choix[place] = added[source], imposes[source]
        added, imposes = nouveaux, nouveaux_choix
    groupes: dict = {}   # (evenement_id, id de l'étape) -> (étape, [noms])

    def diag(stop_info, type_, raison, **extra):
        if diagnostics is not None:
            diagnostics.append({"evenement_id": stop_info.get("evenement_id", ""),
                                "titre": stop_info.get("short_label", ""),
                                "type": type_, "raison": raison,
                                "arret": stop_info["name"], **extra})

    for stop_info, impose in zip(added, imposes):
        name = stop_info["name"]

        if impose:
            ev_id = stop_info.get("evenement_id", "")
            etapes = [i for i, r in enumerate(rows)
                      if r.get("detour_added") and r.get("gd")
                      and (not ev_id or r.get("evenement_id", "") == ev_id)]
            if 0 <= impose["etape"] < len(etapes):
                idx = etapes[impose["etape"]]
                pos = idx if impose.get("avant") else _apres_arrets_ajoutes(rows, idx, stop_info)
                rows = rows[:pos] + [_added_row(stop_info)] + rows[pos:]
                continue
            diag(stop_info, "choix_inapplicable", "etape_introuvable")

        ancre = _anchor_added_by_code(rows, stop_info)
        if ancre is not None:
            idx, avant = ancre
            pos = idx if avant else _apres_arrets_ajoutes(rows, idx, stop_info)
            rows = rows[:pos] + [_added_row(stop_info)] + rows[pos:]
            continue

        main_street, cross_street = _parse_added_stop(name)
        if not main_street:
            still_added.append(stop_info)
            diag(stop_info, "arret_ajoute_non_place", "nom_sans_rue")
            continue

        # Restreindre à l'événement d'origine évite qu'un arrêt ajouté atterrisse
        # dans le détour d'un autre événement (deux détours peuvent partager un nom
        # de rue, ex. « Gauche Ste-Catherine »).
        ev_id = stop_info.get("evenement_id", "")
        best_idx, ambigu = _anchor_added_by_streets(rows, ev_id, main_street, cross_street)
        if best_idx is None and cross_street:
            # La 1re rue n'ancre nulle part : l'arrêt est peut-être réquisitionné
            # par un détour circulant sur sa rue transversale (rôles échangés).
            best_idx, ambigu = _anchor_added_by_streets(rows, ev_id, cross_street, main_street)

        if best_idx is not None:
            if ambigu:
                diag(stop_info, "arret_ajoute_ancre_incertaine", "plusieurs_etapes_possibles")
            etape = rows[best_idx]
            groupes.setdefault((ev_id, id(etape)), (etape, []))[1].append(stop_info)
            pos = _apres_arrets_ajoutes(rows, best_idx, stop_info)
            rows = rows[:pos] + [_added_row(stop_info)] + rows[pos:]
        else:
            still_added.append(stop_info)
            raison = "aucune_etape_correspondante" if any(
                r.get("detour_added") and (not ev_id or r.get("evenement_id", "") == ev_id)
                for r in rows) else "evenement_sans_detour"
            diag(stop_info, "arret_ajoute_non_place", raison)

    for etape, arrets in groupes.values():
        if len(arrets) > 1:
            diag(arrets[0], "arrets_ajoutes_ordre_incertain", "meme_etape",
                 arrets=[a["name"] for a in arrets], etape=etape["gd"])

    return rows, still_added


# ── Diagnostics lisibles ──────────────────────────────────────────────────────

def etapes_des_arrets_ajoutes(rows: list) -> list:
    """[(ligne d'arrêt ajouté, étape, avant)] telles que le pipeline les a posées.

    `etape` = rang (à partir de 0) de l'étape de détour du même évènement qui
    précède l'arrêt, `avant` False ; un arrêt posé avant la 1re étape donne
    (0, True). Sert à préremplir un choix humain avec ce que l'automatique a fait.
    """
    resultat, rang = [], {}
    for r in rows:
        ev = r.get("evenement_id", "")
        if r.get("detour_added") and r.get("gd"):
            rang[ev] = rang.get(ev, -1) + 1
        elif r.get("added_inline"):
            courant = rang.get(ev)
            resultat.append((r, 0 if courant is None else courant, courant is None))
    return resultat


def message_diagnostic(d: dict) -> str:
    """Texte lisible d'un diagnostic (`_diag` ou diagnostic d'arrêt ajouté)."""
    ev = f"Évènement {d.get('evenement_id') or '?'}"
    if d.get("titre"):
        ev += f" ({d['titre']})"
    t, raison = d.get("type"), d.get("raison")
    if t == "description_non_interpretee":
        return f"{ev} : description G-D illisible, détour non placé."
    if raison == "entree_introuvable":
        return f"{ev} : début du détour introuvable dans le G-D, détour placé en tête du parcours."
    if raison == "rejointe_introuvable":
        return f"{ev} : retour à la route régulière introuvable dans le G-D, détour placé sans rien barrer."
    if raison == "description_vide":
        return f"{ev} : description G-D vide, détour non placé."
    if t == "arret_ajoute_non_place":
        motif = {"nom_sans_rue": "le nom ne désigne aucune rue",
                 "aucune_etape_correspondante": "aucune étape du détour sur sa rue",
                 "evenement_sans_detour": "le détour n'a pas pu être décrit"}.get(raison, raison)
        return f"{ev} : arrêt ajouté « {d.get('arret', '')} » non placé ({motif})."
    if t == "arret_ajoute_ancre_incertaine":
        return f"{ev} : arrêt ajouté « {d.get('arret', '')} » posé sur l'une de plusieurs étapes possibles."
    if t == "arrets_ajoutes_ordre_incertain":
        noms = ", ".join(d.get("arrets", []))
        return f"{ev} : arrêts ajoutés ({noms}) sur une même étape, ordre à vérifier."
    if t == "choix_inapplicable":
        return (f"{ev} : le choix enregistré ne s'applique plus à ce parcours "
                "(G-D modifié), calcul automatique.")
    if t == "hors_trajet":
        return f"{ev} : aucun de ses arrêts annulés ne figure sur ce parcours."
    return f"{ev} : {t or raison}."
