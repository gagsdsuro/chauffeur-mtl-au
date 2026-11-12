#!/usr/bin/env python3
"""
test_migrer_logs_flotte.py — Tests de scripts.migrer_logs_flotte

Couvre le rapatriement des journaux des sources de la flotte (parse_gd,
parse_event, fetch_gtfs, fetch_gtfs_rt) depuis data/<matricule>/log/ vers
data/log/ (commun), le dry-run (aucune écriture), la mise de côté d'une cible
existante (jamais d'écrasement), et la non-prise en compte des journaux
personnels. Hermétique : opère dans un répertoire temporaire.

Usage : python3 tests/test_migrer_logs_flotte.py   (code de sortie 0 si tout passe)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import migrer_logs_flotte  # noqa: E402


def main() -> int:
    echefs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echefs.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "data"
        (base / "40001" / "log").mkdir(parents=True)
        (base / "40001" / "log" / "parse_gd.log").write_text("gd\n", encoding="utf-8")
        (base / "40001" / "log" / "parse_event.log").write_text("event\n", encoding="utf-8")
        (base / "40001" / "log" / "parse_journee.log").write_text("perso\n", encoding="utf-8")
        (base / "40001" / "log" / "fetch_gtfs.log").write_text("gtfs\n", encoding="utf-8")
        (base / "123" / "log").mkdir(parents=True)          # pas un matricule valide
        (base / "123" / "log" / "parse_gd.log").write_text("x\n", encoding="utf-8")
        (base / "log").mkdir()                              # cible commune
        (base / "log" / "parse_event.log").write_text("existant\n", encoding="utf-8")

        # ── plan_deplacements : seulement 40001/log, sources de la flotte ────
        plan = migrer_logs_flotte.plan_deplacements(base)
        check(len(plan) == 3,
              f"plan: 3 journaux de flotte attendus (pas 123, pas parse_journee), "
              f"obtenu {[(a.name, b.name) for a, b in plan]}")

        # ── Dry-run : aucune écriture, cible de côté simulée ─────────────────
        r = migrer_logs_flotte.migrer(base, dry_run=True)
        check((base / "40001" / "log" / "parse_gd.log").exists(),
              "dry-run: le journal privé ne doit pas bouger")
        check((base / "log" / "parse_event.log").read_text(encoding="utf-8") == "existant\n",
              "dry-run: la cible existante ne doit pas être renommée")
        check(len(r.mises_de_cote) == 1,
              "dry-run: 1 cible existante à mettre de côté (parse_event.log)")

        # ── Migration réelle ─────────────────────────────────────────────────
        r = migrer_logs_flotte.migrer(base)
        check((base / "log" / "parse_gd.log").read_text(encoding="utf-8") == "gd\n",
              "migration: parse_gd.log rapatrié en commun avec son contenu")
        check((base / "log" / "fetch_gtfs.log").exists(),
              "migration: fetch_gtfs.log rapatrié en commun")
        check((base / "40001" / "log" / "parse_gd.log").exists() is False,
              "migration: le journal de flotte privé doit avoir disparu")
        check((base / "40001" / "log" / "parse_journee.log").exists(),
              "migration: parse_journee.log (personnel) doit rester en place")

        # Conflit : l'ancien parse_event.log commun a été mis de côté, aucune
        # perte, et le plus récent (celui du chauffeur) est le fichier courant.
        check((base / "log" / "parse_event.log").read_text(encoding="utf-8") == "event\n",
              "migration: le nouveau parse_event.log doit venir du dossier privé")
        logs_event = [p.name for p in (base / "log").glob("parse_event*")]
        check(set(logs_event) == {"parse_event.log", "parse_event.1"},
              f"migration: l'ancien et le nouveau coexistent (obtenu {logs_event})")
        check((base / "log" / "parse_event.1").read_text(encoding="utf-8") == "existant\n",
              "migration: l'ancien contenu est préservé dans parse_event.1")
        check(len(r.deplacements) == 3 and len(r.mises_de_cote) == 1,
              "migration: 3 déplacements et 1 mise de côté au bilan")

        # ── Re-exécution : rien à faire ──────────────────────────────────────
        r2 = migrer_logs_flotte.migrer(base)
        check(len(r2.deplacements) == 0 and len(r2.mises_de_cote) == 0,
              "idempotence: une seconde exécution ne doit rien déplacer")

    if echefs:
        print("✗ test_migrer_logs_flotte")
        for e in echefs:
            print(f"    {e}")
        print(f"\n0/1 cas réussis")
        return 1

    print("✓ rapatriement des journaux de flotte vers data/log/ (commun)")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())