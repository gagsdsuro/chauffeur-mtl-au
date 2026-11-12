#!/usr/bin/env python3
"""
test_parse_journee.py — Régression du parseur de journée (scripts/parse_journee.py)

Rejoue des collages bruts figés dans tests/cas_journee/*.txt.

Régression couverte (juillet 2026) : le format du portail du texte « Sommaire…Horaire »
a changé pour les pièces sans bus assigné. L'ancien format compressait
l'absence de bus ET d'emplacement en un seul « -- » littéral
(ex. « Sommaire24 - 02--4:12Horaire »). Le nouveau format affiche deux
placeholders distincts « -- » (bus) + « -- » (emplacement)
(ex. « Sommaire769 - 01----7:02Horaire »). La regex ne reconnaissait que
l'ancien format à un seul « -- » → aucun sommaire trouvé, échec total du parsing.

Usage : python3 tests/test_parse_journee.py   (code de sortie 0 si tout passe)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from chauffeur.depots import charger_journee  # noqa: E402
from parse_journee import JourneeParser  # noqa: E402


def main() -> int:
    echecs = []
    txt = (ROOT / "tests" / "cas_journee" / "769-sans-bus-double-tiret.txt").read_text(encoding="utf-8")
    parser = JourneeParser(txt, date_str="2026-07-10")
    journee = parser.parse()

    if journee is None:
        echecs.append(f"parsing échoué — {parser.errors}")
    else:
        if len(journee.pieces) != 1:
            echecs.append(f"{len(journee.pieces)} pièce(s), attendu 1")
        else:
            p = journee.pieces[0]
            if p.id != "769-01":
                echecs.append(f"id={p.id!r}, attendu '769-01'")
            if p.numero_autobus is not None:
                echecs.append(f"numero_autobus={p.numero_autobus!r}, attendu None (bus non assigné)")
            if p.duree != "7:02":
                echecs.append(f"duree={p.duree!r}, attendu '7:02'")
            if p.debut != "17:30" or p.fin != "24:32":
                echecs.append(f"debut/fin={p.debut!r}/{p.fin!r}, attendu '17:30'/'24:32'")

        if journee.garage_id != "59200":
            echecs.append(f"garage_id={journee.garage_id!r}, attendu '59200'")

        # save() délègue à chauffeur.depots.sauvegarder_journee : vérifie que
        # le fichier écrit reste relisible et au bon format (répertoire
        # temporaire, hermétique).
        with tempfile.TemporaryDirectory() as tmp:
            original_dir = JourneeParser.JOURNEES_DIR
            JourneeParser.JOURNEES_DIR = Path(tmp)
            try:
                out = parser.save(journee)
            finally:
                JourneeParser.JOURNEES_DIR = original_dir

            contenu = out.read_text(encoding="utf-8")
            if not contenu.endswith("\n") or contenu.endswith("\n\n"):
                echecs.append("save(): un seul saut de ligne final attendu")
            relu = charger_journee(out)
            if relu.get("garage_id") != "59200":
                echecs.append(f"save()+charger_journee: garage_id={relu.get('garage_id')!r}")

    # Pièce continue/TS partageant le même identifiant que la pièce régulière.
    txt_continu = (
        ROOT / "tests" / "cas_journee" / "440-continu-id-duplique.txt"
    ).read_text(encoding="utf-8")
    parser_continu = JourneeParser(txt_continu)
    journee_continu = parser_continu.parse()
    if journee_continu is None:
        echecs.append(f"continu: parsing échoué — {parser_continu.errors}")
    else:
        pieces = journee_continu.pieces
        if len(pieces) != 3:
            echecs.append(f"continu: {len(pieces)} pièces, attendu 3")
        else:
            attendu = [
                ("136-01", "horaire", 5, 4, "13:08", "16:07"),
                ("85-07", "horaire", 6, 4, "16:48", "21:06"),
                ("85-07", "continu", 3, 2, "21:06", "23:20"),
            ]
            obtenu = [
                (p.id, p.type_horaire, len(p.trajets), len(p.trajets_service()), p.debut, p.fin)
                for p in pieces
            ]
            if obtenu != attendu:
                echecs.append(f"continu: pièces inattendues {obtenu}")
            releves = [(p.releve or {}).get("je_releve", {}).get("matricule") for p in pieces]
            if releves != [None, "10001", "10002"]:
                echecs.append(f"continu: détails dupliqués écrasés ou mal associés {releves}")

        if journee_continu.date != "2026-08-22":
            echecs.append(f"continu: date={journee_continu.date}, attendu 2026-08-22")

        # Le portail sépare les valeurs dans des éléments HTML et fournit une
        # date canonique indépendante des libellés Hier/Demain.
        sommaire_txt, details_txt = txt_continu.split("Détails 136 - 01", 1)
        en_html = lambda texte: "".join(
            f"<div>{ligne}</div>" for ligne in texte.splitlines() if ligne
        )
        portail_parser = JourneeParser.from_portal_json(
            {
                "date": "2026-08-22",
                "journeeHtml": en_html(sommaire_txt),
                "voyagesHtml": en_html("Détails 136 - 01\n" + details_txt),
            },
            "2026-08-22",
        )
        portail_journee = portail_parser.parse()
        if portail_journee is None or len(portail_journee.pieces) != 3:
            echecs.append(f"continu HTML: parsing échoué — {portail_parser.errors}")

        # Les ancres priment sur l'ordre si le portail livre les détails dans
        # un ordre différent de celui des sommaires.
        payload_ancres = {
            "date": "2026-08-22",
            "journeeHtml": """
              <div>59200 - Frontenac</div><div>Journée440</div>
              <a class="work-piece-summary-link" href="#idPt16-48">
                <span>Sommaire</span><span>85 - 07</span><span>31228</span>
                <span>--</span><span>4:18</span><span>Horaire</span>
              </a><div>Prise</div><div>16:48</div><div>Lieu</div><div>E137</div>
              <div>Début</div><div>16:48</div><div>Fin</div><div>21:06</div>
              <div>Lieu</div><div>E137</div>
              <a class="work-piece-summary-link" href="#idPt21-06">
                <span>Sommaire</span><span>85 - 07</span><span>31228</span>
                <span>--</span><span>2:14</span><span>Continu</span><span>Horaire</span>
              </a><div>Prise</div><div>21:06</div><div>Lieu</div><div>E137</div>
              <div>Début</div><div>21:06</div><div>Fin</div><div>23:20</div>
              <div>Lieu</div><div>E137</div>
            """,
            "voyagesHtml": """
              <h2 class="trips-item-heading" id="idPt21-06">Détails 85 - 07</h2>
              <div>Haut-le-pied</div><div>Départ et arrivé :</div>
              <div>Départ TS</div><span>21:06</span><div>Arrivée TS</div><span>21:09</span>
              <h2 class="trips-item-heading" id="idPt16-48">Détails 85 - 07</h2>
              <div>Haut-le-pied</div><div>Départ et arrivé :</div>
              <div>Départ régulier</div><span>16:48</span><div>Arrivée régulière</div><span>16:51</span>
            """,
        }
        parser_ancres = JourneeParser.from_portal_json(payload_ancres, "2026-08-22")
        journee_ancres = parser_ancres.parse()
        departs = [p.trajets[0].depart.arret for p in journee_ancres.pieces] if journee_ancres else []
        if departs != ["Départ régulier", "Départ TS"]:
            echecs.append(f"portail: appariement par ancres incorrect {departs}")

        # Le portail place le nom, le tiret et le matricule dans trois
        # éléments distincts. Ils doivent être recomposés pour la relève.
        payload_releve = {
            "date": "2026-09-05",
            "journeeHtml": """
              <div>59200 - Frontenac</div><div>Journée131</div>
              <a class="work-piece-summary-link" href="#idPt17-16">
                <span>Sommaire</span><span>131 - 02</span><span>--</span>
                <span>--</span><span>1:20</span><span>Horaire</span>
              </a><div>Prise</div><div>17:16</div><div>Lieu</div><div>E137</div>
              <div>Début</div><div>17:16</div><div>Fin</div><div>18:36</div>
              <div>Lieu</div><div>E137</div>
              <a class="work-piece-summary-link" href="#idPt22-36">
                <span>Sommaire</span><span>10 - 02</span><span>--</span>
                <span>--</span><span>3:40</span><span>Horaire</span>
              </a><div>Prise</div><div>22:36</div><div>Lieu</div><div>E137</div>
              <div>Début</div><div>22:36</div><div>Fin</div><div>26:16</div>
              <div>Lieu</div><div>E137</div>
            """,
            "voyagesHtml": """
              <h2 class="trips-item-heading" id="idPt17-16">Détails 131 - 02</h2>
              <dt>Je relève:</dt><dd><span>Reyes Aguilar Samuel Elias</span>
              - <span>40001</span></dd>
              <dt>Je suis relevé par:</dt><dd><span>Alexis Lesly</span>
              - <span>43116</span></dd>
              <h2 class="trips-item-heading" id="idPt22-36">Détails 10 - 02</h2>
              <dt>Je relève:</dt><dd><span>Relève à confirmer</span> - </dd>
            """,
        }
        parser_releve = JourneeParser.from_portal_json(payload_releve, "2026-09-05")
        journee_releve = parser_releve.parse()
        releve = journee_releve.pieces[0].releve if journee_releve else None
        attendu_releve = {
            "je_releve": {
                "nom": "Reyes Aguilar Samuel Elias",
                "matricule": "40001",
            },
            "je_suis_releve_par": {
                "nom": "Alexis Lesly",
                "matricule": "43116",
            },
        }
        if releve != attendu_releve:
            echecs.append(f"portail: relève HTML incorrecte {releve!r}")
        releve_a_confirmer = journee_releve.pieces[1].releve if journee_releve else None
        attendu_a_confirmer = {
            "je_releve": {"nom": "Relève à confirmer", "matricule": ""}
        }
        if releve_a_confirmer != attendu_a_confirmer:
            echecs.append(
                f"portail: relève à confirmer incorrecte {releve_a_confirmer!r}"
            )

        mauvaise_date = JourneeParser.from_portal_json(
            {"date": "2026-08-23", "journeeHtml": "<div></div>", "voyagesHtml": ""},
            "2026-08-22",
        )
        if mauvaise_date.parse() is not None or not mauvaise_date.errors:
            echecs.append("portail: une date retournée discordante devrait être refusée")

    # Rétrocompatibilité : les anciennes pièces sans type restent régulières.
    from chauffeur.modeles import Piece
    ancienne = Piece.from_dict({"id": "1", "duree": "1:00"})
    if ancienne.type_horaire != "horaire":
        echecs.append("type_horaire absent: repli 'horaire' attendu")

    # Les HLP (Haut-le-pied / Sortie / Entrée) doivent conserver leurs heures
    # début et fin à l'identique que l'import soit automatique (portail) ou un
    # collage manuel de secours. Le portail intercale les instructions du G-D
    # entre « Entrée » et « Départ et arrivé : » et sépare l'heure de l'arrêt
    # dans un <span> : l'import automatique perdait ces heures (régression
    # introduite le 4 septembre avec l'automatisation des imports).
    txt_entree = (
        ROOT / "tests" / "cas_journee" / "34-entree-heures.txt"
    ).read_text(encoding="utf-8")
    manuel_parser = JourneeParser(txt_entree, date_str="2026-09-13")
    manuel = manuel_parser.parse()
    if manuel is None:
        echecs.append(f"entrée: parsing manuel échoué — {manuel_parser.errors}")
    else:
        trajets_manuel = [
            t.to_dict() if hasattr(t, "to_dict") else t
            for p in manuel.pieces for t in p.trajets
        ]
        entrees_manuel = [
            t for t in trajets_manuel if t.get("type") == "entree"
        ]
        if entrees_manuel != [{
            "type": "entree", "ligne": None, "direction": None,
            "id_parcours": None, "detour": False,
            "depart": {"arret": "Station Viau", "heure": "25:33"},
            "arrivee": {"arret": "Frontenac", "heure": "25:44"},
        }]:
            echecs.append(f"entrée: HLP manuel incorrect {entrees_manuel}")

    payload_portail = {
        "date": "2026-09-13",
        "journeeHtml": """
            <div>59200 - Frontenac</div><div>Journée422</div>
            <a class="work-piece-summary-link" href="#idPt18-27">
              <span>Sommaire</span><span>34 - 02</span><span>31056</span>
              <span>--</span><span>7:17</span><span>Horaire</span>
            </a><div>Prise</div><div>18:27</div><div>Lieu</div><div>E082</div>
            <div>Début</div><div>18:27</div><div>Fin</div><div>25:44</div>
            <div>Lieu</div><div>FRT</div>
        """,
        "voyagesHtml": """
            <h2 class="trips-item-heading" id="idPt18-27">Détails 34 - 02</h2>
            <div>34 Est</div><div>ID 7</div>
            <div>Départ et arrivé :</div>
            <div>Ste-Catherine / Du Havre<span>18:27</span></div>
            <div>Station Viau<span>18:49</span></div>
            <div>Informations supplémentaires :</div><div>Information</div>
            <div>Entrée</div>
            <div>53753 - [V] Pierre-De Coubertin, [V] carrefour giratoire, [V] Pierre-De Coubertin, [D] carrefour giratoire, [D] Pierre-De Coubertin, [G] Pie-IX, [D] Hochelaga, [G] D'Iberville, [G] Ontario, [D] du Havre</div>
            <div>Départ et arrivé :</div>
            <div>Station Viau<span>25:33</span></div>
            <div>Frontenac<span>25:44</span></div>
        """,
    }
    portail = JourneeParser.from_portal_json(payload_portail, "2026-09-13").parse()
    if portail is None:
        echecs.append("entrée: parsing portail échoué")
    else:
        trajets_portail = [
            t.to_dict() if hasattr(t, "to_dict") else t
            for p in portail.pieces for t in p.trajets
        ]
        if trajets_portail != trajets_manuel:
            echecs.append(
                "entrée: import portail ≠ import manuel pour les trajets "
                f"(portail={trajets_portail}, manuel={trajets_manuel})"
            )

    if echecs:
        print("✗ test_parse_journee")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1
    print("✓ journées sans bus + pièce continue avec ID dupliqué + HLP (heures début/fin portail)")
    print("\n3/3 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
