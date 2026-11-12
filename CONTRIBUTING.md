# Contribuer

Merci de votre intérêt. Langue de travail : **français** (champs, messages, documentation).

## Avant de commencer

- Lire [NOTICE.md](NOTICE.md) (projet indépendant, sources de données) et `CLAUDE.md` / `AGENTS.md`
  (architecture, commandes, conventions).
- **Ne jamais joindre ou committer de données réelles** : journées, cartes agent, cookies, matricules,
  noms de collègues, contenu du portail employé. Les jeux d'essai doivent être **synthétiques ou
  anonymisés**.
- En contribuant, vous acceptez que votre contribution soit publiée sous [AGPL-3.0](LICENSE).

## Flux de travail

- Une branche par sujet, créée depuis `main` : `feat/<sujet>`, `fix/<sujet>`, `docs/<sujet>`,
  `chore/<sujet>` ; pas de commit direct sur `main` ; ouvrir une demande de fusion.
- Lancer avant toute demande : `python3 tests/run_all.py` et `python3 tests/test_dockerfile.py`.
- Dépendances : modifier `requirements.in`, regénérer `requirements.txt` selon `docs/dependances.md`
  (jamais d'édition manuelle) et mettre à jour `THIRD_PARTY_NOTICES.md`.
- Un nouveau package Python de premier niveau doit être déclaré dans le `Dockerfile`.
