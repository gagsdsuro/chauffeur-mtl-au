#!/usr/bin/env python3
"""
test_migrate_data.py — Tests de scripts.migrate_data (isolation par matricule)

Couvre le déplacement des répertoires personnels vers data/<matricule>/,
le dry-run (aucune écriture), le refus en cas de conflit (cible non vide) et
la fusion --force (jamais d'écrasement). Hermétique : opère dans un
répertoire temporaire.

Usage : python3 tests/test_migrate_data.py   (code de sortie 0 si tout passe)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import migrate_data  # noqa: E402


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "data"
        (base / "journees").mkdir(parents=True)
        (base / "journees" / "journee-2026-06-15.json").write_text("{}", encoding="utf-8")
        (base / "ca").mkdir()
        (base / "ca" / "carte-agent-2026-06-18.pdf").write_bytes(b"x")
        (base / "notes").mkdir()
        (base / "notes" / "voiture.json").write_text("{}", encoding="utf-8")
        (base / "log").mkdir()   # journal commun (flotte) + résidus personnels
        (base / "log" / "parse_gd.log").write_text("flotte\n", encoding="utf-8")
        (base / "log" / "fetch_gtfs.log").write_text("flotte\n", encoding="utf-8")
        (base / "log" / "parse_journee.log").write_text("perso\n", encoding="utf-8")
        (base / "log" / "carte_agent.log").write_text("perso\n", encoding="utf-8")
        (base / "Gauche-Droite").mkdir()   # flotte : ne doit pas bouger
        (base / "Gauche-Droite" / "gd104_est.json").write_text("{}", encoding="utf-8")

        # ── Dry-run : aucune écriture ───────────────────────────────────────
        r = migrate_data.migrer(base, "40001", dry_run=True)
        check((base / "journees" / "journee-2026-06-15.json").exists(),
              "dry-run: l'original ne doit pas bouger")
        check((base / "log" / "parse_journee.log").exists(),
              "dry-run: le journal personnel ne doit pas bouger")
        check(len(r.deplacements) == 5,
              f"dry-run: 5 déplacements attendus (journees, ca, notes + "
              f"parse_journee.log, carte_agent.log), obtenu {len(r.deplacements)}")

        # ── Migration réelle ────────────────────────────────────────────────
        r = migrate_data.migrer(base, "40001")
        check(len(r.deplacements) == 5, f"migration: 5 déplacements attendus, "
              f"obtenu {len(r.deplacements)}")
        for dossier in ["journees", "ca", "notes", "session"]:
            check(not (base / dossier).exists(),
                  f"migration: data/{dossier} devrait avoir disparu")
        check((base / "40001" / "journees" / "journee-2026-06-15.json").exists(),
              "migration: journée déplacée vers data/40001/journees/")
        check((base / "40001" / "ca" / "carte-agent-2026-06-18.pdf").exists(),
              "migration: carte agent déplacée vers data/40001/ca/")
        check((base / "Gauche-Droite" / "gd104_est.json").exists(),
              "migration: la flotte (Gauche-Droite) ne doit pas bouger")

        # ── data/log reste commun : flotte en place, personnel rapatrié ──────
        check((base / "log").exists(),
              "migration: data/log (journal commun de la flotte) doit rester")
        check((base / "log" / "parse_gd.log").exists()
              and (base / "log" / "fetch_gtfs.log").exists(),
              "migration: les journaux de la flotte restent dans data/log")
        check(not (base / "log" / "parse_journee.log").exists()
              and not (base / "log" / "carte_agent.log").exists(),
              "migration: les journaux personnels quittent data/log")
        check((base / "40001" / "log" / "parse_journee.log").exists()
              and (base / "40001" / "log" / "carte_agent.log").exists(),
              "migration: journaux personnels rapatriés vers data/40001/log/")

        # ── Re-migration : rien à faire (côté personnels en place) ───────────
        r2 = migrate_data.migrer(base, "40001")
        check(r2.deplacements == [], "re-migration: aucun déplacement attendu")
        check(len(r2.ignores) == 5,
              f"re-migration: les 5 dossiers privés absents ignorés, "
              f"obtenu {len(r2.ignores)}")

        # ── Matricule invalide ──────────────────────────────────────────────
        try:
            migrate_data.migrer(base, "123")
            check(False, "migrer: matricule invalide doit lever ValueError")
        except ValueError:
            pass

    # ── Conflit puis fusion (dans un nouvel environnement) ───────────────────
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "data"
        (base / "journees").mkdir(parents=True)
        (base / "journees" / "journee-2026-06-15.json").write_text("a", encoding="utf-8")
        cible = base / "40001" / "journees"
        cible.mkdir(parents=True)
        (cible / "journee-2026-06-16.json").write_text("b", encoding="utf-8")
        (base / "log").mkdir()
        (base / "log" / "parse_journee.log").write_text("source\n", encoding="utf-8")
        cible_log = base / "40001" / "log"
        cible_log.mkdir(parents=True)
        (cible_log / "parse_journee.log").write_text("cible\n", encoding="utf-8")

        r = migrate_data.migrer(base, "40001")
        check(len(r.conflits) == 2 and r.deplacements == [],
              f"conflit: cibles non vides → refus sans --force, obtenu "
              f"conflits={len(r.conflits)}, déplacements={len(r.deplacements)}")
        check((base / "journees" / "journee-2026-06-15.json").exists(),
              "conflit: l'original ne doit pas rester intact")
        check((base / "log" / "parse_journee.log").exists(),
              "conflit: le journal personnel conflictuel doit rester en place")

        r = migrate_data.migrer(base, "40001", force=True)
        check((cible / "journee-2026-06-15.json").exists()
              and (cible / "journee-2026-06-16.json").exists(),
              "force: les deux journées doivent coexister, aucun écrasement")
        check(not (base / "journees").exists(),
              "force: le sous-dossier source doit disparaître une fois vidé")
        check(not (base / "log" / "parse_journee.log").exists(),
              "force: sans conflit le journal personnel est rapatrié")
        check((base / "log").exists(),
              "force: data/log reste en place (commun)")

        sonde = cible / "journee-2026-06-16.json"
        contenu_final = sonde.read_text(encoding="utf-8")
        check(contenu_final == "b",
              f"force: l'entrée existante ne doit jamais être écrasée, obtenu "
              f"{contenu_final!r}")
        check((cible_log / "parse_journee.log").read_text(encoding="utf-8") == "source\n",
              "force: le journal du chauffeur devient le fichier courant")
        check((cible_log / "parse_journee.1").read_text(encoding="utf-8") == "cible\n",
              "force: l'ancienne cible est conservée de côté (parse_journee.1)")

    if echecs:
        print("✗ test_migrate_data")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ migration vers data/<matricule>/ (déplacement, dry-run, "
          "conflit, fusion sans écrasement)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())