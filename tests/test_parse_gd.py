#!/usr/bin/env python3
"""
test_parse_gd.py — Régression du parseur Gauche-Droite (scripts/parse_gd.py)

Rejoue des collages bruts figés dans tests/cas_gd/*.txt.

Régression couverte (ligne 24 est, juin 2026) : l'export du portail répète l'en-tête
« Gauche-Droite / <ligne> <direction> » devant CHAQUE parcours, même quand
plusieurs parcours appartiennent à la même ligne/direction (ex. Parcours
principal + Parcours secondaire collés l'un après l'autre). split_sections()
découpait alors en 2 sections distinctes qui s'écrasaient l'une l'autre →
1 seul parcours retenu au lieu de 2. Le correctif fusionne les sections d'un
même couple (ligne, direction), en retirant l'en-tête répété des sections
suivantes (sinon il se fait mal interpréter comme une instruction G-D, ex.
« Gauche-Droite / 24 Est » matche le pattern « Gauche - <rue> »).

Régression couverte (ligne 460 est, octobre 2026) : parcours présents en
double dans la source — doublon exact écarté, même id au contenu différent
conservé, les deux signalés dans [AVERTISSEMENTS] du rapport d'import.

Usage : python3 tests/test_parse_gd.py   (code de sortie 0 si tout passe)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from parse_gd import GDParser, split_sections  # noqa: E402


def _gd(tmp) -> Path:
    """Sous-dossier G-D du répertoire temporaire : appariements et détours sont
    écrits à côté du dossier G-D, donc dans `tmp` et non dans son parent (/tmp)."""
    dossier = Path(tmp) / "Gauche-Droite"
    dossier.mkdir(exist_ok=True)
    return dossier


def main() -> int:
    echecs = []
    txt = (ROOT / "tests" / "cas_gd" / "24_est_multi_parcours.txt").read_text(encoding="utf-8")
    sections = split_sections(txt)

    if len(sections) != 1:
        echecs.append(f"24 est: {len(sections)} section(s) après fusion, attendu 1")
    else:
        # GDParser.parse() écrit dans data/Gauche-Droite/ (effet de bord réel) —
        # on appelle directement les étapes de parsing pour rester hermétique.
        parser = GDParser(sections[0])
        ok = parser._extract_header() and parser._parse_parcours()
        json_data = parser._generate_json() if ok else None
        if json_data is None:
            echecs.append(f"24 est: parsing échoué — {parser.errors}")
        else:
            parcours = json_data["routes"][0]["parcours"]
            if len(parcours) != 2:
                echecs.append(f"24 est: {len(parcours)} parcours, attendu 2")
            else:
                principal, secondaire = parcours[0], parcours[1]
                if principal["name"] != "Parcours principal":
                    echecs.append(f"parcours[0]: nom={principal['name']!r}, attendu 'Parcours principal'")
                if any("Gauche-Droite" in d or "Imprimer" in d for d in principal["direction"]):
                    echecs.append(f"parcours principal: en-tête répété mal capté: {principal['direction']}")
                if secondaire["name"] != "Parcours secondaire":
                    echecs.append(f"parcours[1]: nom={secondaire['name']!r}, attendu 'Parcours secondaire'")
                if secondaire["start"] != "Station Sherbrooke (Édicule Est )":
                    echecs.append(f"parcours secondaire: start={secondaire['start']!r}")
                if len(secondaire["direction"]) != 6:
                    echecs.append(f"parcours secondaire: {len(secondaire['direction'])} directions, attendu 6")

        # parse() complet (répertoire GD temporaire, hermétique) → parser.report
        # doit contenir le rapport formaté (plus de _print_report interne).
        with tempfile.TemporaryDirectory() as tmp:
            original_gd_dir = GDParser.GD_DIR
            GDParser.GD_DIR = _gd(tmp)
            try:
                parser2 = GDParser(sections[0])
                result2 = parser2.parse()
            finally:
                GDParser.GD_DIR = original_gd_dir

        if result2 is None:
            echecs.append(f"report: parse() complet a échoué — {parser2.errors}")
        else:
            if "[OK]" not in parser2.report:
                echecs.append(f"report: '[OK]' absent du rapport : {parser2.report!r}")
            if "gd24_est.json" not in parser2.report:
                echecs.append(f"report: nom de fichier gd24_est.json absent du rapport")

    # Doublons (460 est, octobre 2026) : le fichier contenait les parcours 24 et
    # 25 deux fois chacun, à l'identique. Un doublon exact est écarté avec un
    # avertissement ; un même id au contenu différent est gardé et signalé.
    double = split_sections(txt + "\n" + txt)[0]
    parser3 = GDParser(double)
    if not (parser3._extract_header() and parser3._parse_parcours()):
        echecs.append(f"doublon exact: parsing échoué — {parser3.errors}")
    else:
        if [p["id"] for p in parser3.parcours] != [1, 4]:
            echecs.append(f"doublon exact: ids {[p['id'] for p in parser3.parcours]}, attendu [1, 4]")
        if len(parser3.avertissements) != 2 or "double" not in parser3.avertissements[0]:
            echecs.append(f"doublon exact: avertissements {parser3.avertissements}")

    variante = txt + "\n" + txt.split("Parcours secondaire")[0].replace(
        "Droite - Montgomery", "Droite - Saint-Laurent")
    parser4 = GDParser(split_sections(variante)[0])
    if not (parser4._extract_header() and parser4._parse_parcours()):
        echecs.append(f"même id différent: parsing échoué — {parser4.errors}")
    else:
        if [p["id"] for p in parser4.parcours] != [1, 4, 1]:
            echecs.append(f"même id différent: ids {[p['id'] for p in parser4.parcours]}, attendu [1, 4, 1]")
        if len(parser4.avertissements) != 1 or "different" not in parser4.avertissements[0]:
            echecs.append(f"même id différent: avertissements {parser4.avertissements}")
    with tempfile.TemporaryDirectory() as tmp:
        parser5 = GDParser(double, gd_dir=_gd(tmp))
        if parser5.parse() is None or "[AVERTISSEMENTS]" not in parser5.report:
            echecs.append("doublon exact: [AVERTISSEMENTS] absent du rapport d'import")

    # Réponse réelle simplifiée de /listeBus : le PDFMake caché doit être
    # ignoré au profit de la liste HTML sémantique multi-parcours.
    portail_html = """
      <h2>Gauche-Droite / 24 Est</h2>
      <div id="leftright-panel" style="display:none">
        {"content":[{"text":"G - NE DOIT PAS ÊTRE IMPORTÉ"}]}
      </div>
      <a id="btnLR">Imprimer</a>
      <ol>
        <li><span>Parcours principal</span><span>ID 24</span>
          <span>Date de mise à jour: 2026-09-03 12:45:15</span>
          <span>Station Villa-Maria</span><span class="stop-code">51241</span>
          <span>Via - Terminus Villa-Maria</span><span>Gauche - Décarie</span>
          <span>Montgomery / Sherbrooke</span><span class="stop-code">52819</span>
        </li>
        <li><span>Parcours secondaire</span><span>ID 21</span>
          <span>Date de mise à jour: 2026-09-03 12:45:15</span>
          <span>Station Sherbrooke</span><span class="stop-code">52508</span>
          <span>Droite - Cherrier</span><span>Gauche - Sherbrooke</span>
          <span>Montgomery / Sherbrooke</span><span class="stop-code">52819</span>
        </li>
      </ol>
      <script>pdfMake.createPdf({"text":"Droite - POLLUTION"});</script>
    """
    with tempfile.TemporaryDirectory() as tmp:
        portail = GDParser.from_portal_json(
            {"html": portail_html}, "24", "est", gd_dir=_gd(tmp)
        )
        resultat_portail = portail.parse()
        if resultat_portail is None:
            echecs.append(f"portail G-D: parsing échoué — {portail.errors}")
        else:
            parcours = resultat_portail["routes"][0]["parcours"]
            if [p["id"] for p in parcours] != [24, 21]:
                echecs.append(f"portail G-D: IDs inattendus {[p['id'] for p in parcours]}")
            if [p["start_code"] for p in parcours] != [51241, 52508]:
                echecs.append("portail G-D: codes de départ incorrects")
            instructions = [i for p in parcours for i in p["direction"]]
            if any("POLLUTION" in i or "NE DOIT" in i for i in instructions):
                echecs.append("portail G-D: contenu PDFMake/script importé par erreur")

        mauvais = GDParser.from_portal_json(
            {"html": portail_html}, "24", "ouest", gd_dir=_gd(tmp)
        )
        if mauvais.parse() is not None:
            echecs.append("portail G-D: direction discordante acceptée")

        chemin_existant = _gd(tmp) / "gd24_est.json"
        avant_indisponible = chemin_existant.read_bytes()
        indisponible = GDParser.from_portal_json(
            {
                "html": (
                    "<h2>Gauche-Droite / 24 Est</h2>"
                    "<p>Désolé, le gauche-droite n'est pas encore disponible.</p>"
                )
            },
            "24",
            "est",
            gd_dir=_gd(tmp),
        )
        if indisponible.parse() is not None:
            echecs.append("portail G-D: réponse indisponible acceptée")
        if chemin_existant.read_bytes() != avant_indisponible:
            echecs.append("portail G-D: réponse invalide a écrasé le fichier existant")

    if echecs:
        print("✗ test_parse_gd")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1
    print("✓ G-D manuel multi-parcours + HTML portail sans PDFMake")
    print("\n2/2 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
