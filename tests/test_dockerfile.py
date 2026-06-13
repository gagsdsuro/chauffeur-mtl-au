#!/usr/bin/env python3
"""
test_dockerfile.py — Garde-fou de cohérence Dockerfile ↔ packages source

Empêche la régression « module ajouté mais pas COPY dans le Dockerfile » qui
casse l'app au démarrage (ModuleNotFoundError). Pour chaque package source de
premier niveau requis à l'exécution (dossier racine contenant des .py, hors
tests/), vérifie qu'une instruction COPY l'embarque dans l'image.

Léger : ne builde pas Docker, lit seulement le Dockerfile. À lancer dans la
suite avant tout déploiement.

Usage : python3 tests/test_dockerfile.py   (code de sortie 0 si tout est cohérent)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Dossiers de premier niveau NON embarqués dans l'image (par conception) :
#   tests/ ne tourne pas en prod ; data/ est monté via volume.
IGNORE = {"tests", "data"}


def runtime_packages() -> list:
    """Dossiers racine contenant des modules Python, requis à l'exécution."""
    pkgs = []
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name in IGNORE:
            continue
        if any(d.glob("*.py")):
            pkgs.append(d.name)
    return pkgs


def copied_dirs(dockerfile_text: str) -> set:
    """Dossiers copiés par une instruction COPY (ex. 'COPY app/ ./app/' → 'app')."""
    found = set()
    for m in re.finditer(r"^\s*COPY\s+\.?/?([^\s./]+)/\s", dockerfile_text, re.MULTILINE):
        found.add(m.group(1))
    return found


def main() -> int:
    dockerfile = ROOT / "Dockerfile"
    if not dockerfile.exists():
        print("✗ Dockerfile introuvable")
        return 1

    requis = runtime_packages()
    copies = copied_dirs(dockerfile.read_text(encoding="utf-8"))
    manquants = [p for p in requis if p not in copies]

    if manquants:
        print(f"✗ Le Dockerfile ne copie pas : {manquants}")
        print(f"    packages source requis : {requis}")
        print(f"    copiés par le Dockerfile : {sorted(copies)}")
        print(f"    → ajouter par ex. : COPY {manquants[0]}/  ./{manquants[0]}/")
        return 1

    print(f"✓ Le Dockerfile copie tous les packages source requis : {requis}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
