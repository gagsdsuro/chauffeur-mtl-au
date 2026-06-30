"""chauffeur.gd — domaine Gauche-Droite : alignement G-D/arrêts et détours.

Pipeline pur (sans I/O fichier) anciennement dans rapport_gd.py :
  build_rows → annotate_events → apply_gd_detours → insert_added_stops_inline
  (+ filter_rows_by_stop_range, _select_parcours, parse_description_gd).

rapport_gd conserve son rendu HTML/MD et délègue ces transformations ici.
La normalisation de rue vit dans chauffeur.matching.
"""
from __future__ import annotations

import re

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
    Aligne les instructions G-D avec les arrêts GTFS par correspondance de rue.
    Retourne une liste de dicts : {gd, seq, stop_id, stop_name, stop_code}

    Alignement à deux pointeurs (instructions / arrêts), tous deux monotones :
      - Pour chaque arrêt, on cherche la première instruction restante dont la rue
        figure dans le nom de l'arrêt. On compare d'abord à la **rue principale**
        (avant le « / »), pour qu'un arrêt « René-Lévesque / Berlioz » s'associe à
        « Droite - René-Lévesque » plutôt qu'à « Droite - Berlioz ».
      - Les instructions sautées (segments sans arrêt GTFS : autoroutes, virages)
        sont émises sans arrêt, dans l'ordre.
      - Un arrêt qui ne correspond à aucune instruction restante (terminus/stations
        nommés différemment, ex. « Station McGill ») est rattaché au groupe courant
        (l'instruction active la plus récente), sans bloquer l'alignement.
    """
    streets = [extract_street(instr) for instr in gd_instructions]
    n_instr = len(gd_instructions)
    n_stops = len(stops_ordered)

    def _match_index(name_low, start):
        """Première instruction >= start dont la rue est dans le nom (rue principale d'abord)."""
        primary = name_low.split(" / ", 1)[0]
        for haystack in (primary, name_low):
            for k in range(start, n_instr):
                if streets[k] and streets[k] in haystack:
                    return k
        return None

    rows = []
    cur = -1            # instruction active (dernier appariement), -1 si aucune
    emitted = -1        # index de la dernière instruction déjà écrite

    for seq, sid in stops_ordered:
        name_low = stop_names.get(sid, {}).get("name", "").lower()
        search_start = cur if cur >= 0 else 0
        j = _match_index(name_low, search_start)

        if j is None:
            # Arrêt orphelin : rattaché au groupe courant (cellule G-D vide).
            rows.append({"gd": "", "seq": seq, "stop_id": sid})
            continue

        if j == cur:
            # Même rue que l'instruction active : arrêt groupé.
            rows.append({"gd": "", "seq": seq, "stop_id": sid})
            continue

        # Nouvelle instruction : émet d'abord les instructions sautées (sans arrêt).
        for k in range(emitted + 1, j):
            rows.append({"gd": gd_instructions[k], "seq": None, "stop_id": None})
        rows.append({"gd": gd_instructions[j], "seq": seq, "stop_id": sid})
        emitted = j
        cur = j

    # Instructions restantes sans arrêt
    for k in range(emitted + 1, n_instr):
        rows.append({"gd": gd_instructions[k], "seq": None, "stop_id": None})

    # Enrichissement avec les noms
    for r in rows:
        if r["stop_id"]:
            s = stop_names.get(r["stop_id"], {})
            r["stop_code"] = s.get("code", "")
            r["stop_name"] = s.get("name", "")
        else:
            r["stop_code"] = ""
            r["stop_name"] = ""
    return rows


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
    stop_ids_in_rows = {r["stop_id"] for r in rows if r.get("stop_id")}

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
        for a in e.get("arrets_ajoutes", []):
            name = a if isinstance(a, str) else a.get("nom", "")
            added.append({"name": name, "label": label, "effectif": effectif,
                          "evenement_id": e.get("evenement_id", "")})

    for r in rows:
        sid = r.get("stop_id")
        if sid and sid in cancelled_ids:
            r["cancelled"] = cancelled_ids[sid]
        else:
            r["cancelled"] = []

    # Événements dont les arrêts annulés ne figurent pas dans le trajet GTFS
    orphan_events = []
    for e in events:
        arrets = e.get("arrets_annules", [])
        if arrets and not any(a["id"] in stop_ids_in_rows for a in arrets):
            orphan_events.append(e)

    return rows, added, orphan_events


# ── Intégration G-D des détours ───────────────────────────────────────────────

_RR_RE = re.compile(r'^R[.\s]?R\.?$', re.IGNORECASE)


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


def event_applicable_to_parcours(event: dict, stop_ids_in_rows: set,
                                  gd_instructions: list) -> bool:
    """Détermine si un évènement est applicable à un parcours spécifique.

    Règle 1 — avec arrets_annules :
      Au moins un arrêt annulé doit figurer dans les stops GTFS de ce parcours.

    Règle 2 — détour sans arrêt annulé :
      Les deux bornes du détour doivent chacune figurer dans les instructions G-D :
      • 2a : première instruction Via (rue empruntée par le détour).
      • 2b : instruction juste avant R.R. (rue de rejointe au parcours normal).
      Si une borne est absente de la description (cas indécidable), on inclut
      l'évènement par prudence. Les deux bornes connues doivent toutes deux matcher.
    """
    cancelled = event.get("arrets_annules", [])
    if cancelled:
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


def _anchor_detour_span(rows: list, instructions: list, max_gap: int = 2):
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
         réapparition lointaine de la même rue ;
      3. le détour s'insère APRÈS l'ancre et barre les étapes (ancre, fin].

    Retourne (insert_pos, bypass_end). bypass_end == -1 si rien n'est barré
    (ancre seule, comportement conservateur). Faute d'ancre exploitable,
    retombe sur (0, -1) — insertion en tête, ancien comportement.
    """
    if not instructions:
        return 0, -1
    entry_street = extract_street(instructions[0])
    reg = _regular_steps(rows)
    if not reg or not entry_street:
        return 0, -1

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
        return 0, -1
    if first_exit is not None:
        before = [i for i in entry_hits if i < first_exit]
        anchor = before[-1] if before else entry_hits[0]
    else:
        anchor = entry_hits[0]

    insert_pos = anchor + 1

    # Pas de rejointe exploitable → insertion seule, rien barré.
    if first_exit is None or first_exit <= anchor:
        return insert_pos, -1

    # Grappe contiguë de la rue de rejointe après l'ancre.
    reg_after = [i for i in reg if i >= first_exit]
    bypass_end = first_exit
    gap = 0
    for i in reg_after[1:]:
        if matches(i, exit_street):
            bypass_end = i
            gap = 0
        else:
            gap += 1
            if gap > max_gap:
                break
    return insert_pos, bypass_end


def apply_gd_detours(rows: list, events: list) -> list:
    """
    Pour chaque événement avec une description_gd parseable :
    - Insère les étapes du détour avant le premier arrêt annulé (detour_added=True)
    - Marque les instructions G-D régulières contournées (detour_removed=True)

    Détour SANS arrêt annulé : ancrage par rues d'entrée/rejointe via
    _anchor_detour_span (le détour se place après l'étape correspondant à sa
    1re instruction et barre les étapes contournées jusqu'à la rejointe).
    """
    for event in events:
        desc = event.get("description_gd") or ""
        instructions = parse_description_gd(desc)
        if not instructions:
            continue

        cancelled_codes = {a["id"] for a in event.get("arrets_annules", [])}

        cancelled_positions = [
            i for i, r in enumerate(rows)
            if r.get("stop_code") in cancelled_codes
        ]

        if cancelled_positions:
            first_pos = cancelled_positions[0]
            last_pos  = cancelled_positions[-1]

            # Étendre last_pos pour inclure les instructions G-D sans arrêt GTFS
            # qui suivent immédiatement le dernier arrêt annulé.
            # Ex. : "Gauche - Clément" dont le stop a été consommé par une
            # instruction précédente ("Droite - Clément") et qui se retrouve
            # sans stop_code → tombe en dehors de la plage sans cette extension.
            i = last_pos + 1
            while i < len(rows):
                sc = rows[i].get("stop_code", "")
                if sc and sc not in cancelled_codes:
                    break  # premier arrêt régulier non annulé : fin de la zone
                last_pos = i
                i += 1
        else:
            first_pos, last_pos = _anchor_detour_span(rows, instructions)

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

def _parse_added_stop(name: str):
    """
    Extrait (rue_principale, rue_transversale) normalisées depuis le nom
    d'un arrêt ajouté.
    "Temp. - Clément / Lafleur"        → ("clement", "lafleur")
    "56472 - Notre-Dame / Saint-Pierre" → ("notre dame", "saint pierre")
    "Temp. - ST PATRICK / ST PATRICK"  → ("st patrick", "st patrick")
    """
    m = re.match(r'^(?:Temp\.|[\d]+)\s*[-–]\s*(.+)$', name, re.IGNORECASE)
    clean = m.group(1).strip() if m else name.strip()
    parts = [normalize_street(p) for p in clean.split("/")]
    main  = parts[0] if parts else None
    cross = parts[1] if len(parts) >= 2 else None
    return main, cross


def insert_added_stops_inline(rows: list, added: list) -> tuple:
    """
    Tente de placer chaque arrêt ajouté directement dans le tableau,
    après l'instruction de détour qui longe la rue principale de l'arrêt.

    Logique de placement :
      1. Cherche les lignes detour_added dont la rue correspond à la rue
         principale de l'arrêt.
      2. Parmi elles, préfère celle immédiatement suivie d'une instruction
         sur la rue transversale (= on est au bon coin de rue).
      3. Insère un arrêt vert juste après cette instruction.

    Retourne (rows_mis_à_jour, still_added) où still_added contient les
    arrêts qui n'ont pas pu être positionnés inline.
    """
    still_added = []

    for stop_info in added:
        name = stop_info["name"]
        main_street, cross_street = _parse_added_stop(name)
        if not main_street:
            still_added.append(stop_info)
            continue

        # Candidats : lignes detour_added du MÊME événement dont la rue ≈ main_street.
        # Restreindre à l'événement d'origine évite qu'un arrêt ajouté atterrisse
        # dans le détour d'un autre événement (deux détours peuvent partager un nom
        # de rue, ex. « Gauche Ste-Catherine »).
        ev_id = stop_info.get("evenement_id", "")
        candidates = []
        for i, r in enumerate(rows):
            if not r.get("detour_added") or not r.get("gd"):
                continue
            if ev_id and r.get("evenement_id", "") != ev_id:
                continue
            instr_street = normalize_street(extract_street(r["gd"]))
            if main_street in instr_street or instr_street in main_street:
                candidates.append(i)

        best_idx = None
        if candidates:
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
                            best_idx = idx
                            break
            if best_idx is None:
                best_idx = candidates[-1]  # dernier candidat sur cette rue

        if best_idx is not None:
            new_row = {
                "gd": "",
                "seq": None,
                "stop_id": None,
                "stop_code": "",
                "stop_name": name,
                "cancelled": [],
                "added_inline":  True,
                "added_label":   stop_info.get("label", ""),
                "effectif":      stop_info.get("effectif", ""),
                "evenement_id":  stop_info.get("evenement_id", ""),
            }
            rows = rows[: best_idx + 1] + [new_row] + rows[best_idx + 1 :]
        else:
            still_added.append(stop_info)

    return rows, still_added
