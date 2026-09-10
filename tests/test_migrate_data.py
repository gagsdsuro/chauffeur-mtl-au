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
        (base / "Gauche-Droite").mkdir()   # flotte : ne doit pas bouger
        (base / "Gauche-Droite" / "gd104_est.json").write_text("{}", encoding="utf-8")

        # ── Dry-run : aucune écriture ───────────────────────────────────────
        r = migrate_data.migrer(base, "43863", dry_run=True)
        check((base / "journees" / "journee-2026-06-15.json").exists(),
              "dry-run: l'original ne doit pas bouger")
        check(len(r.deplacements) == 3,
              f"dry-run: 3 déplacements attendus (journees, ca, notes), "
              f"obtenu {len(r.deplacements)}")

        # ── Migration réelle ────────────────────────────────────────────────
        r = migrate_data.migrer(base, "43863")
        check(len(r.deplacements) == 3, f"migration: 3 déplacements attendus, "
              f"obtenu {len(r.deplacements)}")
        for dossier in ["journees", "ca", "notes", "log", "session"]:
            check(not (base / dossier).exists(),
                  f"migration: data/{dossier} devrait avoir disparu")
        check((base / "43863" / "journees" / "journee-2026-06-15.json").exists(),
              "migration: journée déplacée vers data/43863/journees/")
        check((base / "43863" / "ca" / "carte-agent-2026-06-18.pdf").exists(),
              "migration: carte agent déplacée vers data/43863/ca/")
        check((base / "Gauche-Droite" / "gd104_est.json").exists(),
              "migration: la flotte (Gauche-Droite) ne doit pas bouger")

        # ── Re-migration : rien à faire (absents) ───────────────────────────
        r2 = migrate_data.migrer(base, "43863")
        check(r2.deplacements == [], "re-migration: aucun déplacement attendu")
        check(len(r2.ignores) == 6,
              f"re-migration: 6 dossiers devraient être ignorés, "
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
        cible = base / "43863" / "journees"
        cible.mkdir(parents=True)
        (cible / "journee-2026-06-16.json").write_text("b", encoding="utf-8")

        r = migrate_data.migrer(base, "43863")
        check(len(r.conflits) == 1 and r.deplacements == [],
              f"conflit: dir non vide → refus sans --force, obtenu "
              f"conflits={len(r.conflits)}, déplacements={len(r.deplacements)}")
        check((base / "journees" / "journee-2026-06-15.json").exists(),
              "conflit: l'original doit rester intact")

        r = migrate_data.migrer(base, "43863", force=True)
        check((cible / "journee-2026-06-15.json").exists()
              and (cible / "journee-2026-06-16.json").exists(),
              "force: les deux journées doivent coexister, aucun écrasement")
        check(not (base / "journees").exists(),
              "force: le sous-dossier source doit disparaître une fois vidé")

        sonde = cible / "journee-2026-06-16.json"
        contenu_final = sonde.read_text(encoding="utf-8")
        check(contenu_final == "b",
              f"force: l'entrée existante ne doit jamais être écrasée, obtenu "
              f"{contenu_final!r}")

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